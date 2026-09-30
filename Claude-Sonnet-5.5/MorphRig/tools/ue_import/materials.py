"""Textures, master materials and material instances.

Material contract (lead, Blender side):
  textures        source/textures/T_<Mat>_<BC|N|ORM|E|TM>.png   (BC sRGB, N DirectX tangent normal, ORM linear R=AO G=rough B=metal, E and TM linear)
  TeamIcon 0/1    0 = team A (cyan, circle icon), 1 = team B (magenta, diamond icon); TeamColor is linear
  base colour     (suit, armor, cyber) paintMask = saturate(TM.R + lerp(TM.G, TM.B, TeamIcon)); BaseColor = lerp(BC, BC * TeamColor * 1.8, paintMask)
  emissive        E.r * TeamColor * 2.5 (cyber), icon glow TeamColor * lerp(TM.G, TM.B, TeamIcon) * 0.35, plus rim: TeamColor * pow(1 - saturate(dot(N, V)), 3) * OutlineStrength (not on the eye)
  eye             glossy cornea: default lit with specular 1 and the ORM roughness
Secondary team marker (not colour): overlay material MI_Outline_TeamA (solid) / MI_Outline_TeamB (dashed), an inverted hull rendered as the
skeletal mesh OverlayMaterial. Fallback constants apply where a texture is missing.
"""
import os
import json
import unreal
import common as C

mel = unreal.MaterialEditingLibrary

SLOTS = ["suit", "skin", "eye", "mouth", "armor", "cyber", "hair"]
FALLBACK_SRGB = {
    "skin": (0.55, 0.40, 0.33), "eye": (0.9, 0.9, 0.92), "mouth": (0.85, 0.8, 0.75), "hair": (0.05, 0.04, 0.04),
    "suit": (0.05, 0.06, 0.08), "armor": (0.30, 0.32, 0.36), "cyber": (0.55, 0.60, 0.66)}
# roughness, metallic fallbacks
FALLBACK_SURFACE = {"skin": (0.55, 0.0), "eye": (0.05, 0.0), "mouth": (0.4, 0.0), "hair": (0.55, 0.0), "suit": (0.7, 0.0), "armor": (0.4, 0.7), "cyber": (0.3, 0.9)}
PAINT_SLOTS = {"suit", "armor", "cyber"}
TEAM_SRGB = {"A": (0.05, 0.85, 1.0), "B": (1.0, 0.10, 0.62)}


def srgb_to_linear(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def lin_color(rgb, a=1.0):
    return unreal.LinearColor(rgb[0], rgb[1], rgb[2], a)


# ---------------------------------------------------------------------------------------------------------------- graph helpers

class G(object):
    """Small helper to build material graphs."""

    def __init__(self, mat):
        self.mat = mat
        self.x = -1200
        self.y = 0

    def add(self, cls, x=None, y=None, **props):
        e = mel.create_material_expression(self.mat, cls, self.x if x is None else x, self.y if y is None else y)
        for k, v in props.items():
            e.set_editor_property(k, v)
        self.y += 140
        return e

    def scalar(self, name, default, group="Operative"):
        return self.add(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default, group=group)

    def vector(self, name, default, group="Operative"):
        return self.add(unreal.MaterialExpressionVectorParameter, parameter_name=name, default_value=default, group=group)

    def const(self, v):
        return self.add(unreal.MaterialExpressionConstant, r=v)

    def const3(self, r, g, b):
        return self.add(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(r, g, b, 1.0))

    def tex(self, name, default_path, sampler, group="Textures"):
        t = unreal.load_asset(default_path)
        return self.add(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name=name, texture=t, sampler_type=sampler, group=group)

    def link(self, src, dst, dst_input, src_output=""):
        ok = mel.connect_material_expressions(src, src_output, dst, dst_input)
        if not ok:
            C.warn("connect failed", src.get_name(), src_output, "->", dst.get_name(), dst_input)
        return dst

    def binop(self, cls, a, b, ao="", bo=""):
        e = self.add(cls)
        self.link(a, e, "A", ao)
        self.link(b, e, "B", bo)
        return e

    def mul(self, a, b, ao="", bo=""):
        return self.binop(unreal.MaterialExpressionMultiply, a, b, ao, bo)

    def add2(self, a, b, ao="", bo=""):
        return self.binop(unreal.MaterialExpressionAdd, a, b, ao, bo)

    def sub(self, a, b, ao="", bo=""):
        return self.binop(unreal.MaterialExpressionSubtract, a, b, ao, bo)

    def lerp(self, a, b, alpha, ao="", bo="", alpha_o=""):
        e = self.add(unreal.MaterialExpressionLinearInterpolate)
        self.link(a, e, "A", ao)
        self.link(b, e, "B", bo)
        self.link(alpha, e, "Alpha", alpha_o)
        return e

    def sat(self, a, ao=""):
        e = self.add(unreal.MaterialExpressionSaturate)
        self.link(a, e, "", ao)
        return e

    def prop(self, src, prop, src_output=""):
        if not mel.connect_material_property(src, src_output, prop):
            C.warn("connect property failed", prop)


def recreate(name, cls_factory, cls):
    path = C.MAT_DIR + "/" + name
    if C.eal().does_asset_exist(path):
        C.eal().delete_asset(path)
    return C.asset_tools().create_asset(name, C.MAT_DIR, cls, cls_factory)


# ---------------------------------------------------------------------------------------------------------------- masters

def write_png(path, rgba, size=4):
    """Minimal PNG writer (no image library inside the editor python)."""
    import zlib
    import struct
    raw = b"".join(b"\x00" + bytes(rgba) * size for _ in range(size))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def make_default_textures(ctx):
    """Linear (no sRGB) 4x4 white and black defaults for the mask style texture parameters (the engine ones are sRGB and fail the sampler check)."""
    out = {}
    tmp = os.path.join(ctx.root, "unreal", "Saved", "MorphRig")
    os.makedirs(tmp, exist_ok=True)
    for name, rgba in (("T_Default_White", (255, 255, 255, 255)), ("T_Default_Black", (0, 0, 0, 0))):
        path = os.path.join(tmp, name + ".png")
        write_png(path, rgba)
        C.run_tasks([C.import_task(path, C.TEX_DIR, name, None, save=False)])
        tex = unreal.load_asset(C.TEX_DIR + "/" + name)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        C.save(tex)
        out[name] = C.TEX_DIR + "/" + name + "." + name
    return out


def build_master(defaults):
    m = recreate("M_Operative_Master", unreal.MaterialFactoryNew(), unreal.Material)
    m.set_editor_property("used_with_skeletal_mesh", True)
    m.set_editor_property("used_with_morph_targets", True)
    m.set_editor_property("used_with_static_lighting", False)
    g = G(m)
    white_srgb = "/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture"
    white = defaults["T_Default_White"]
    flat_n = "/Engine/EngineMaterials/DefaultNormal.DefaultNormal"
    black = defaults["T_Default_Black"]
    S = unreal.MaterialSamplerType
    bc_const = g.vector("BaseColorConst", unreal.LinearColor(0.2, 0.2, 0.2, 1))
    bc_tex = g.tex("BC", white_srgb, S.SAMPLERTYPE_COLOR)
    use_bc = g.scalar("UseBC", 0.0)
    n_tex = g.tex("N", flat_n, S.SAMPLERTYPE_NORMAL)
    use_n = g.scalar("UseN", 0.0)
    orm_tex = g.tex("ORM", white, S.SAMPLERTYPE_MASKS)
    use_orm = g.scalar("UseORM", 0.0)
    e_tex = g.tex("E", black, S.SAMPLERTYPE_MASKS)
    use_e = g.scalar("UseE", 0.0)
    tm_tex = g.tex("TM", black, S.SAMPLERTYPE_MASKS)
    use_tm = g.scalar("UseTM", 0.0)
    rough_c = g.scalar("RoughnessConst", 0.5)
    metal_c = g.scalar("MetallicConst", 0.0)
    spec_c = g.scalar("SpecularConst", 0.5)
    team_color = g.vector("TeamColor", unreal.LinearColor(0.0039, 0.694, 1.0, 1))
    team_icon = g.scalar("TeamIcon", 0.0)
    paint_en = g.scalar("PaintEnable", 0.0)
    emis_boost = g.scalar("EmissiveBoost", 1.0)
    rim_str = g.scalar("OutlineStrength", 0.0)
    rim_en = g.scalar("RimEnable", 1.0)
    fallback_tint = g.scalar("FallbackTint", 0.0)

    # base colour
    base = g.lerp(bc_const, bc_tex, use_bc, bo="RGB")
    # team paint mask: saturate(TM.R + lerp(TM.G, TM.B, TeamIcon)) * PaintEnable * UseTM
    icon = g.lerp(tm_tex, tm_tex, team_icon, ao="G", bo="B")
    paint = g.sat(g.add2(tm_tex, icon, ao="R"))
    paint = g.mul(g.mul(paint, paint_en), use_tm)
    tinted = g.mul(g.mul(base, team_color), g.const(1.8))
    base_paint = g.lerp(base, tinted, paint)
    # fallback tint without a mask texture (keeps the team readable while textures are missing)
    base_final = g.lerp(base_paint, g.mul(base_paint, team_color), g.mul(fallback_tint, g.sub(g.const(1.0), use_tm)))
    g.prop(base_final, unreal.MaterialProperty.MP_BASE_COLOR)

    # normal
    normal = g.lerp(g.const3(0.0, 0.0, 1.0), n_tex, use_n, bo="RGB")
    g.prop(normal, unreal.MaterialProperty.MP_NORMAL)

    # orm
    rough = g.lerp(rough_c, orm_tex, use_orm, bo="G")
    metal = g.lerp(metal_c, orm_tex, use_orm, bo="B")
    ao = g.lerp(g.const(1.0), orm_tex, use_orm, bo="R")
    g.prop(rough, unreal.MaterialProperty.MP_ROUGHNESS)
    g.prop(metal, unreal.MaterialProperty.MP_METALLIC)
    g.prop(ao, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    g.prop(spec_c, unreal.MaterialProperty.MP_SPECULAR)

    # emissive: E.r * TeamColor * 2.5 * UseE * EmissiveBoost + rim
    em = g.mul(g.mul(g.mul(g.mul(e_tex, team_color, ao="R"), g.const(2.5)), use_e), emis_boost)
    fres = g.add(unreal.MaterialExpressionFresnel, exponent=3.0, base_reflect_fraction=0.0)
    rim = g.mul(g.mul(g.mul(team_color, fres), rim_str), rim_en)
    # icon glow: TeamColor * lerp(TM.G, TM.B, TeamIcon) * 0.35 on every material that has a TM texture
    icon_glow = g.mul(g.mul(g.mul(team_color, icon), g.const(0.35)), g.mul(use_tm, emis_boost))
    g.prop(g.add2(g.add2(em, rim), icon_glow), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    C.save(m)
    C.log("master material built", m.get_path_name())
    return m


def build_outline_master():
    m = recreate("M_TeamOutline", unreal.MaterialFactoryNew(), unreal.Material)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("used_with_skeletal_mesh", True)
    m.set_editor_property("used_with_morph_targets", True)
    m.set_editor_property("cast_dynamic_shadow_as_masked", False)
    g = G(m)
    color = g.vector("TeamColor", unreal.LinearColor(0.0039, 0.694, 1.0, 1))
    thick = g.scalar("OutlineThickness", 2.2)     # screen pixels
    dash = g.scalar("DashScale", 0.0)
    glow = g.scalar("Glow", 4.0)
    # world position offset along the normal: pixels * centimetres per pixel at the vertex distance (field of view and viewport width from the view),
    # so the line keeps its width on screen in every view
    vn = g.add(unreal.MaterialExpressionVertexNormalWS)
    vpos = g.add(unreal.MaterialExpressionWorldPosition)
    cam = g.add(unreal.MaterialExpressionCameraPositionWS)
    dist = g.add(unreal.MaterialExpressionDistance)
    g.link(vpos, dist, "A")
    g.link(cam, dist, "B")
    tan_half = g.add(unreal.MaterialExpressionViewProperty, property=unreal.MaterialExposedViewProperty.MEVP_TAN_HALF_FIELD_OF_VIEW)
    tan_x = g.add(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(tan_half, tan_x, "", "Property")
    view_size = g.add(unreal.MaterialExpressionViewProperty, property=unreal.MaterialExposedViewProperty.MEVP_VIEW_SIZE)
    size_x = g.add(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(view_size, size_x, "", "Property")
    cm_per_px = g.binop(unreal.MaterialExpressionDivide, g.mul(g.mul(dist, tan_x), g.const(2.0)), size_x)
    cm = g.add(unreal.MaterialExpressionClamp, min_default=0.01, max_default=3.0)
    g.link(g.mul(cm_per_px, thick), cm, "")
    g.prop(g.mul(vn, cm), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    # keep back faces only (inverted hull): TwoSidedSign is +1 front, -1 back
    sign = g.add(unreal.MaterialExpressionTwoSidedSign)
    back = g.sat(g.mul(sign, g.const(-1.0)))
    # dashed variant for team B: diagonal bands in world space
    wp = g.add(unreal.MaterialExpressionWorldPosition)
    z = g.add(unreal.MaterialExpressionComponentMask, r=False, g=False, b=True, a=False)
    g.link(wp, z, "", "")
    x = g.add(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(wp, x, "", "")
    diag = g.add2(z, g.mul(x, g.const(0.5)))
    fr = g.add(unreal.MaterialExpressionFrac)
    g.link(g.mul(diag, dash), fr, "")
    st = g.add(unreal.MaterialExpressionStep)
    g.link(g.const(0.6), st, "Y")
    g.link(fr, st, "X")
    pattern = g.sub(g.const(1.0), st)
    g.prop(g.mul(back, pattern), unreal.MaterialProperty.MP_OPACITY_MASK)
    g.prop(g.mul(color, glow), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    C.save(m)
    return m


def build_simple(name, setup):
    m = recreate(name, unreal.MaterialFactoryNew(), unreal.Material)
    g = G(m)
    setup(m, g)
    mel.recompile_material(m)
    C.save(m)
    return m


def build_utility_materials():
    def normal_vis(m, g):
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("used_with_skeletal_mesh", True)
        m.set_editor_property("used_with_morph_targets", True)
        n = g.add(unreal.MaterialExpressionPixelNormalWS)
        half = g.add2(g.mul(n, g.const(0.5)), g.const(0.5))
        g.prop(half, unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    def clay(m, g):
        m.set_editor_property("used_with_skeletal_mesh", True)
        m.set_editor_property("used_with_morph_targets", True)
        g.prop(g.const3(0.62, 0.62, 0.6), unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.75), unreal.MaterialProperty.MP_ROUGHNESS)

    def wire(m, g):
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("wireframe", True)
        m.set_editor_property("two_sided", True)
        m.set_editor_property("used_with_skeletal_mesh", True)
        m.set_editor_property("used_with_morph_targets", True)
        g.prop(g.const3(0.25, 0.95, 1.0), unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    def fx(m, g):
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        m.set_editor_property("two_sided", True)
        color = g.vector("Color", unreal.LinearColor(0.1, 0.9, 1.0, 1.0))
        opacity = g.scalar("Opacity", 1.0)
        g.prop(g.mul(g.mul(color, opacity), g.const(3.0)), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        g.prop(opacity, unreal.MaterialProperty.MP_OPACITY)

    def floor(m, g):
        # neutral grey studio floor with a 100 cm grid: quiet, no pattern that hides skating
        wp = g.add(unreal.MaterialExpressionWorldPosition)
        xy = g.add(unreal.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
        g.link(wp, xy, "")
        scaled = g.mul(xy, g.const(0.01))
        fr = g.add(unreal.MaterialExpressionFrac)
        g.link(scaled, fr, "")
        edge = g.add(unreal.MaterialExpressionAbs)
        g.link(g.sub(fr, g.const(0.5)), edge, "")
        # line where |frac - 0.5| > 0.485 (component wise -> use max of both axes via saturate of the sum)
        ex = g.add(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
        ey = g.add(unreal.MaterialExpressionComponentMask, r=False, g=True, b=False, a=False)
        g.link(edge, ex, "")
        g.link(edge, ey, "")
        st_x = g.add(unreal.MaterialExpressionStep)
        g.link(g.const(0.488), st_x, "X")
        g.link(ex, st_x, "Y")
        st_y = g.add(unreal.MaterialExpressionStep)
        g.link(g.const(0.488), st_y, "X")
        g.link(ey, st_y, "Y")
        line = g.sat(g.add2(st_x, st_y))
        base = g.lerp(g.const3(0.36, 0.37, 0.39), g.const3(0.16, 0.17, 0.19), line)
        g.prop(base, unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.62), unreal.MaterialProperty.MP_ROUGHNESS)

    def wall(m, g):
        g.prop(g.const3(0.20, 0.21, 0.23), unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)

    def prop_mat(m, g):
        g.prop(g.const3(0.28, 0.30, 0.34), unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.45), unreal.MaterialProperty.MP_ROUGHNESS)
        g.prop(g.const(0.6), unreal.MaterialProperty.MP_METALLIC)

    def target(m, g):
        flash = g.scalar("Flash", 0.0)
        base = g.lerp(g.const3(0.85, 0.32, 0.10), g.const3(1.0, 0.95, 0.6), flash)
        g.prop(base, unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.mul(g.const3(1.0, 0.4, 0.1), g.mul(flash, g.const(6.0))), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        g.prop(g.const(0.4), unreal.MaterialProperty.MP_ROUGHNESS)

    def studio_floor(m, g):
        # plain light grey floor that fades to the backdrop colour with the squared distance from the origin (turntable and face captures)
        wp = g.add(unreal.MaterialExpressionWorldPosition)
        xy = g.add(unreal.MaterialExpressionComponentMask, r=True, g=True, b=False, a=False)
        g.link(wp, xy, "")
        d2 = g.add(unreal.MaterialExpressionDotProduct)
        g.link(xy, d2, "A")
        g.link(xy, d2, "B")
        t = g.sat(g.mul(d2, g.const(1.0 / (1350.0 * 1350.0))))
        base = g.lerp(g.const3(0.30, 0.31, 0.33), g.const3(0.02, 0.022, 0.026), t)
        g.prop(base, unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.75), unreal.MaterialProperty.MP_ROUGHNESS)

    def studio_wall(m, g):
        m.set_editor_property("two_sided", True)     # seen from inside the backdrop cylinder
        wp = g.add(unreal.MaterialExpressionWorldPosition)
        z = g.add(unreal.MaterialExpressionComponentMask, r=False, g=False, b=True, a=False)
        g.link(wp, z, "")
        t = g.sat(g.mul(z, g.const(1.0 / 500.0)))
        base = g.lerp(g.const3(0.018, 0.02, 0.024), g.const3(0.085, 0.09, 0.10), t)
        g.prop(base, unreal.MaterialProperty.MP_BASE_COLOR)
        g.prop(g.const(0.9), unreal.MaterialProperty.MP_ROUGHNESS)

    out = {}
    for name, fn in (("M_StudioFloor", studio_floor), ("M_StudioWall", studio_wall), ("M_DebugNormal", normal_vis), ("M_Clay", clay), ("M_Wireframe", wire), ("M_Fx", fx), ("M_ShowcaseFloor", floor),
                     ("M_ShowcaseWall", wall), ("M_ShowcaseProp", prop_mat), ("M_ShowcaseTarget", target)):
        out[name] = build_simple(name, fn)
    return out


# ---------------------------------------------------------------------------------------------------------------- textures

TEX_SUFFIX = {"bc": "BC", "n": "N", "orm": "ORM", "e": "E", "tm": "TM"}


def import_textures(ctx):
    src = os.path.join(ctx.source, "textures")
    C.ensure_dir(C.TEX_DIR)
    found = {}
    tasks = []
    if not os.path.isdir(src):
        return found
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith(".png"):
            continue
        base = f[:-4]
        tasks.append(C.import_task(os.path.join(src, f), C.TEX_DIR, base, None, save=False))
    if tasks:
        C.run_tasks(tasks)
    for t in tasks:
        name = t.destination_name
        tex = unreal.load_asset(C.TEX_DIR + "/" + name)
        if not tex:
            C.warn("texture failed", name)
            continue
        kind = name.rsplit("_", 1)[-1]
        slot = name.split("_")[1].lower()
        if kind == "BC":
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        elif kind == "N":
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("flip_green_channel", False)
        else:   # ORM, E, TM are linear data
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
        C.save(tex)
        found.setdefault(slot, {})[kind] = tex
    C.log("textures imported:", {s: sorted(v) for s, v in found.items()})
    return found


# ---------------------------------------------------------------------------------------------------------------- instances

def make_instance(name, parent):
    path = C.MAT_DIR + "/" + name
    if C.eal().does_asset_exist(path):
        C.eal().delete_asset(path)
    mi = C.asset_tools().create_asset(name, C.MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    return mi


def run(ctx):
    C.ensure_dir(C.MAT_DIR)
    textures = import_textures(ctx)
    defaults = make_default_textures(ctx)
    master = build_master(defaults)
    outline = build_outline_master()
    util = build_utility_materials()
    C.log("utility materials:", sorted(util))
    for team, (idx, srgb) in (("A", (0, TEAM_SRGB["A"])), ("B", (1, TEAM_SRGB["B"]))):
        team_lin = lin_color(srgb_to_linear(srgb))
        for slot in SLOTS:
            mi = make_instance("MI_%s_Team%s" % (slot, team), master)
            mel.set_material_instance_vector_parameter_value(mi, "BaseColorConst", lin_color(srgb_to_linear(FALLBACK_SRGB[slot])))
            rough, metal = FALLBACK_SURFACE[slot]
            mel.set_material_instance_scalar_parameter_value(mi, "RoughnessConst", rough)
            mel.set_material_instance_scalar_parameter_value(mi, "MetallicConst", metal)
            mel.set_material_instance_vector_parameter_value(mi, "TeamColor", team_lin)
            mel.set_material_instance_scalar_parameter_value(mi, "TeamIcon", float(idx))
            mel.set_material_instance_scalar_parameter_value(mi, "PaintEnable", 1.0 if slot in PAINT_SLOTS else 0.0)
            mel.set_material_instance_scalar_parameter_value(mi, "RimEnable", 0.0 if slot == "eye" else 1.0)
            mel.set_material_instance_scalar_parameter_value(mi, "OutlineStrength", 0.0)
            mel.set_material_instance_scalar_parameter_value(mi, "EmissiveBoost", 1.0)
            if slot == "eye":
                mel.set_material_instance_scalar_parameter_value(mi, "SpecularConst", 1.0)
            have = textures.get(slot, {})
            for kind, use_name in (("BC", "UseBC"), ("N", "UseN"), ("ORM", "UseORM"), ("E", "UseE"), ("TM", "UseTM")):
                tex = have.get(kind)
                if tex is not None:
                    mel.set_material_instance_texture_parameter_value(mi, kind, tex)
                    mel.set_material_instance_scalar_parameter_value(mi, use_name, 1.0)
            if "TM" not in have and slot in PAINT_SLOTS:
                mel.set_material_instance_scalar_parameter_value(mi, "FallbackTint", 0.14)
            C.save(mi)
        oi = make_instance("MI_Outline_Team%s" % team, outline)
        mel.set_material_instance_vector_parameter_value(oi, "TeamColor", team_lin)
        mel.set_material_instance_scalar_parameter_value(oi, "DashScale", 0.0 if team == "A" else 0.16)
        mel.set_material_instance_scalar_parameter_value(oi, "OutlineThickness", 2.2)
        C.save(oi)
    C.log("material instances created for both teams")

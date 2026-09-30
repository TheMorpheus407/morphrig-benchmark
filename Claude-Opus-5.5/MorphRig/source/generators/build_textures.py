"""Stage T: bake geometry maps per texture set, author PBR textures procedurally, build materials.

Usage:
  blender -b --factory-startup -P build_textures.py -- --in stageB.blend --out stageB.blend
          --tex-dir MorphRig/source/textures [--sets skin,suit] [--scale 0.25]

For every texture set (see mr_uv.TEXSETS) Cycles bakes, in UV space: rest-pose world position,
world normal, part/shell ids (exact island coverage) and ambient occlusion.  mr_texdesign turns
these into base colour (sRGB), ORM, height (-> tangent-space normal, OpenGL +Y) and a mask
texture (R team accent, G emission, B team-A emblem, A team-B emblem).  The final materials use
a scene property 'mr_team' (0 = team A cyan, 1 = team B orange) to tint accents/emblems.
"""
import sys
import os
import json
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import bpy
import mr_uv
import mr_textures as T
import mr_texdesign as D

TEAM_A = (0.010, 0.672, 1.0)       # linear of sRGB #1AD6FF
TEAM_B = (1.0, 0.144, 0.010)       # linear of sRGB #FF6A1A
EMIT_STRENGTH = 4.0


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--sets", default="")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--materials-only", action="store_true",
                    help="rebuild the material node trees from existing PNGs (no bake)")
    return ap.parse_args(argv)


def setup_cycles():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = 'GPU'
    except Exception as e:           # CPU fallback keeps the stage reproducible anywhere
        print("CYCLES GPU unavailable:", e)
    sc.cycles.samples = 1
    sc.render.bake.margin = 0
    sc.render.bake.use_clear = True
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    sc.world.light_settings.distance = 0.25


def objects_of(mat_name):
    out = []
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and any(m and m.name == mat_name for m in ob.data.materials):
            out.append(ob)
    return out


def _bake_tree(mat, img, mode):
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(em.outputs[0], out.inputs[0])
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    if mode == "pos":
        nt.links.new(geo.outputs["Position"], em.inputs["Color"])
    elif mode == "nrm":
        vm = nt.nodes.new('ShaderNodeVectorMath')
        vm.operation = 'MULTIPLY_ADD'
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(geo.outputs["Normal"], vm.inputs[0])
        nt.links.new(vm.outputs[0], em.inputs["Color"])
    elif mode == "ids":
        ap = nt.nodes.new('ShaderNodeAttribute')
        ap.attribute_type = 'GEOMETRY'
        ap.attribute_name = "part"
        ash = nt.nodes.new('ShaderNodeAttribute')
        ash.attribute_type = 'GEOMETRY'
        ash.attribute_name = "shell"
        m1 = nt.nodes.new('ShaderNodeMath')
        m1.operation = 'DIVIDE'
        m1.inputs[1].default_value = 255.0
        nt.links.new(ap.outputs["Fac"], m1.inputs[0])
        m2 = nt.nodes.new('ShaderNodeMath')
        m2.operation = 'DIVIDE'
        m2.inputs[1].default_value = 8.0
        nt.links.new(ash.outputs["Fac"], m2.inputs[0])
        cc = nt.nodes.new('ShaderNodeCombineColor')
        nt.links.new(m1.outputs[0], cc.inputs[0])
        nt.links.new(m2.outputs[0], cc.inputs[1])
        cc.inputs[2].default_value = 1.0
        nt.links.new(cc.outputs[0], em.inputs["Color"])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.nodes.active = tex


def bake_maps(set_name, S):
    sc = bpy.context.scene
    mat_name = mr_uv.MATERIAL_NAME[set_name]
    obs = objects_of(mat_name)
    target = bpy.data.materials[mat_name]
    dummy = bpy.data.images.get("_bake_dummy") or bpy.data.images.new("_bake_dummy", 8, 8, float_buffer=True)
    others = {m for ob in obs for m in ob.data.materials if m and m != target}
    tmp_nodes = []
    for m in others:
        # keep their shading intact: only add a throw-away bake target and make it active
        m.use_nodes = True
        t = m.node_tree.nodes.new('ShaderNodeTexImage')
        t.name = "TMP_BAKE"
        t.image = dummy
        m.node_tree.nodes.active = t
        tmp_nodes.append((m, t))
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]
    maps = {}
    for mode in ("ids", "pos", "nrm", "ao"):
        img = bpy.data.images.new(f"_bake_{set_name}_{mode}", S, S, alpha=True, float_buffer=True)
        img.colorspace_settings.name = 'Non-Color'
        target.use_nodes = True
        _bake_tree(target, img, "pos" if mode == "ao" else mode)
        t0 = time.time()
        if mode == "ao":
            sc.cycles.samples = 64
            bpy.ops.object.bake(type='AO', margin=0, use_clear=True)
            sc.cycles.samples = 1
        else:
            bpy.ops.object.bake(type='EMIT', margin=0, use_clear=True)
        a = np.empty(S * S * 4, np.float32)
        img.pixels.foreach_get(a)
        maps[mode] = a.reshape(S, S, 4)
        bpy.data.images.remove(img)
        print(f"  bake {set_name}:{mode} {S}px {time.time() - t0:.1f}s")
    for m, t in tmp_nodes:
        m.node_tree.nodes.remove(t)
    ids = maps["ids"]
    cov = ids[..., 2] > 0.5
    return {"P": maps["pos"][..., :3], "N": maps["nrm"][..., :3] * 2.0 - 1.0, "AO": maps["ao"][..., 0],
            "PID": ids[..., 0] * 255.0, "SH": ids[..., 1] * 8.0, "COV": cov}


def author(set_name, maps, part_names, tex_dir, S):
    c = T.Ctx(maps, part_names)
    if set_name == "eye":
        rows, cols = np.divmod(c.idx, S)
        uv = np.stack([(cols + 0.5) / S, (rows + 0.5) / S], 1)
        D.eye(c, uv)
    else:
        D.DESIGNS[set_name](c)
    im = c.images()
    cov = maps["COV"]
    texel_m = 1.0 / (S * texel_density_scale(set_name))
    files = {}
    bc = T.dilate(im["BC"], cov, 16)
    files["BC"] = (bc, True)
    orm = T.dilate(im["ORM"], cov, 16)
    files["ORM"] = (orm, False)
    nrm = T.height_to_normal(im["H"], cov, texel_m)
    nrm = T.dilate(nrm, cov, 16)
    files["N"] = (nrm, False)
    msk = T.dilate(im["M"], cov, 16)
    files["M"] = (msk, False)
    paths = {}
    for k, (arr, is_srgb) in files.items():
        path = os.path.join(tex_dir, f"T_{set_name.capitalize()}_{k}.png")
        T.write_png(path, arr, srgb_encode=is_srgb)
        paths[k] = path
    return paths


_DENS = {}


def texel_density_scale(set_name):
    """Texels per metre / S for the set (measured from the UV layout; 3D metres per UV unit)."""
    return _DENS.get(set_name, 1.0)


def measure_density():
    import bmesh
    for s, mname in mr_uv.MATERIAL_NAME.items():
        a3 = au = 0.0
        for ob in objects_of(mname):
            me = ob.data
            uvl = me.uv_layers[0].data
            slots = [i for i, m in enumerate(me.materials) if m and m.name == mname]
            co = np.array([v.co for v in me.vertices])
            for poly in me.polygons:
                if poly.material_index not in slots:
                    continue
                li = list(poly.loop_indices)
                uv = np.array([uvl[i].uv for i in li])
                pp = co[[me.loops[i].vertex_index for i in li]]
                for k in range(1, len(li) - 1):
                    a3 += 0.5 * np.linalg.norm(np.cross(pp[k] - pp[0], pp[k + 1] - pp[0]))
                    au += 0.5 * abs(np.cross(uv[k] - uv[0], uv[k + 1] - uv[0]))
        _DENS[s] = float(np.sqrt(au / max(a3, 1e-9)))     # UV units per metre


def build_material(set_name, paths):
    mat = bpy.data.materials[mr_uv.MATERIAL_NAME[set_name]]
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (900, 0)
    bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bs.location = (600, 0)
    L(bs.outputs[0], out.inputs[0])

    def img(key, colorspace, y):
        n = nt.nodes.new('ShaderNodeTexImage')
        n.image = bpy.data.images.load(paths[key], check_existing=True)
        n.image.colorspace_settings.name = colorspace
        n.location = (-700, y)
        n.label = key
        return n
    bc = img("BC", 'sRGB', 300)
    orm = img("ORM", 'Non-Color', 0)
    nm = img("N", 'Non-Color', -300)
    mk = img("M", 'Non-Color', -600)
    sep_orm = nt.nodes.new('ShaderNodeSeparateColor')
    L(orm.outputs["Color"], sep_orm.inputs[0])
    L(sep_orm.outputs[1], bs.inputs["Roughness"])
    L(sep_orm.outputs[2], bs.inputs["Metallic"])
    nmap = nt.nodes.new('ShaderNodeNormalMap')
    L(nm.outputs["Color"], nmap.inputs["Color"])
    L(nmap.outputs[0], bs.inputs["Normal"])
    sep_m = nt.nodes.new('ShaderNodeSeparateColor')
    L(mk.outputs["Color"], sep_m.inputs[0])
    team = nt.nodes.new('ShaderNodeAttribute')
    team.attribute_type = 'VIEW_LAYER'
    team.attribute_name = "mr_team"
    tcol = nt.nodes.new('ShaderNodeMix')
    tcol.data_type = 'RGBA'
    tcol.inputs[6].default_value = TEAM_A + (1.0,)
    tcol.inputs[7].default_value = TEAM_B + (1.0,)
    L(team.outputs["Fac"], tcol.inputs[0])
    emb = nt.nodes.new('ShaderNodeMix')                 # emblem of the active team
    emb.data_type = 'FLOAT'
    L(team.outputs["Fac"], emb.inputs[0])
    L(sep_m.outputs[2], emb.inputs[2])
    L(mk.outputs["Alpha"], emb.inputs[3])
    acc = nt.nodes.new('ShaderNodeMath')
    acc.operation = 'MAXIMUM'
    L(sep_m.outputs[0], acc.inputs[0])
    L(emb.outputs[0], acc.inputs[1])
    tinted = nt.nodes.new('ShaderNodeMix')
    tinted.data_type = 'RGBA'
    tinted.blend_type = 'MULTIPLY'
    tinted.inputs[0].default_value = 1.0
    L(bc.outputs["Color"], tinted.inputs[6])
    L(tcol.outputs[2], tinted.inputs[7])
    base = nt.nodes.new('ShaderNodeMix')
    base.data_type = 'RGBA'
    L(acc.outputs[0], base.inputs[0])
    L(bc.outputs["Color"], base.inputs[6])
    L(tinted.outputs[2], base.inputs[7])
    L(base.outputs[2], bs.inputs["Base Color"])
    glow = nt.nodes.new('ShaderNodeMath')
    glow.operation = 'MAXIMUM'
    L(sep_m.outputs[1], glow.inputs[0])
    L(emb.outputs[0], glow.inputs[1])
    L(tcol.outputs[2], bs.inputs["Emission Color"])
    gs = nt.nodes.new('ShaderNodeMath')
    gs.operation = 'MULTIPLY'
    gs.inputs[1].default_value = EMIT_STRENGTH
    L(glow.outputs[0], gs.inputs[0])
    L(gs.outputs[0], bs.inputs["Emission Strength"])
    if set_name == "skin":
        bs.inputs["Subsurface Weight"].default_value = 0.12
        bs.inputs["Subsurface Radius"].default_value = (1.0, 0.40, 0.25)
        bs.inputs["Subsurface Scale"].default_value = 0.004
    if set_name == "eye":
        bs.inputs["Coat Weight"].default_value = 0.6
        bs.inputs["Coat Roughness"].default_value = 0.02
    mat["mr_textures"] = json.dumps({k: os.path.basename(v) for k, v in paths.items()})


def team_icons(path, S=256, ss=4):
    """Team icon texture: R = team-A chevron, G = team-B ring (anti-aliased), A = union."""
    n = S * ss
    y, x = np.mgrid[0:n, 0:n]
    u = (x + 0.5) / n * 2.0 - 1.0
    v = (y + 0.5) / n * 2.0 - 1.0
    chev = ((np.abs((v - 0.35) + 1.4 * np.abs(u)) < 0.22) & (np.abs(u) < 0.62) & (v > -0.62)) | \
           ((np.abs((v + 0.2) + 1.4 * np.abs(u)) < 0.14) & (np.abs(u) < 0.45) & (v > -0.9))
    r = np.hypot(u, v)
    ring = (np.abs(r - 0.55) < 0.14) | (r < 0.16)
    img = np.zeros((n, n, 4), np.float32)
    img[..., 0] = chev
    img[..., 1] = ring
    img[..., 3] = chev | ring
    img = img.reshape(S, ss, S, ss, 4).mean((1, 3))
    T.write_png(path, img, srgb_encode=False)


def main():
    args = parse()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.inp))
    sc = bpy.context.scene
    sc["mr_team"] = 0
    part_names = json.loads(sc["mr_part_names"])
    os.makedirs(args.tex_dir, exist_ok=True)
    team_icons(os.path.join(args.tex_dir, "T_TeamIcons.png"))
    setup_cycles()
    measure_density()
    sets = [s for s in (args.sets.split(",") if args.sets else list(mr_uv.TEXSETS))]
    for s in sets:
        S = max(64, int(mr_uv.TEXSETS[s] * args.scale))
        t0 = time.time()
        if args.materials_only:
            paths = {k: os.path.join(args.tex_dir, f"T_{s.capitalize()}_{k}.png") for k in ("BC", "ORM", "N", "M")}
            assert all(os.path.exists(p_) for p_ in paths.values()), paths
        else:
            maps = bake_maps(s, S)
            paths = author(s, maps, part_names, args.tex_dir, S)
        build_material(s, paths)
        print("TEXSET", s, S, "done", round(time.time() - t0, 1), "s")
    for img in list(bpy.data.images):
        if img.name.startswith("_bake"):
            bpy.data.images.remove(img)
    sc.render.engine = 'BLENDER_EEVEE'
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("SAVED", args.out)


if __name__ == "__main__":
    main()

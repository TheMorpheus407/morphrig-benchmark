"""Import the exported MorphRig Operative into the Unreal project (run headless, see tools/build_linux.sh).

UnrealEditor-Cmd MorphRig.uproject -run=pythonscript -script=<this file> -unattended -nullrhi
Environment: MR_ROOT = absolute path of the MorphRig delivery folder.

Creates under /Game/MorphRig:
  Textures/T_*                 (normal maps flipped to DirectX green, masks linear)
  Materials/M_Operative + MI_* (team accent / emblem / emission driven by the 'Team' parameter)
  Materials/M_Fx, M_Floor, M_Block, M_Target, M_TeamIcon, M_Outline (post-process, custom stencil)
  Character/SK_Operative       (+ LOD1/LOD2, sockets on the sock_* bones, morph-target curve metadata)
  Animations/A_<clip>          (notifies = UMorphEventNotify per Blender marker, face morph curves,
                                additive hits / face controls, root motion on dash_*)
  Audio/SW_Dialogue, Props/SM_Beacon, Maps/Showcase
  Data/clips.json              (runtime clip table, staged as a non-UFS file)
"""
import json
import os
import unreal

ROOT = os.environ.get("MR_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXP = os.path.join(ROOT, "export")
DST = "/Game/MorphRig"
CONTENT = os.path.join(ROOT, "unreal", "Content", "MorphRig")
at = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
anl = unreal.AnimationLibrary
mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
TEAM_A = unreal.LinearColor(0.010, 0.672, 1.0, 1.0)
TEAM_B = unreal.LinearColor(1.0, 0.144, 0.010, 1.0)
SETS = ["Skin", "Suit", "Armor", "Cyber", "Hair", "Eye", "Mouth"]


def log(*a):
    print("MR_IMPORT", *a)


def fresh(path):
    if eal.does_asset_exist(path):
        eal.delete_asset(path)


# ----------------------------------------------------------------------------------------------- textures
def import_textures():
    tex_dir = os.path.join(EXP, "textures")
    tasks = []
    for f in sorted(os.listdir(tex_dir)):
        if not f.endswith(".png"):
            continue
        t = unreal.AssetImportTask()
        t.filename = os.path.join(tex_dir, f)
        t.destination_path = DST + "/Textures"
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    at.import_asset_tasks(tasks)
    for f in sorted(os.listdir(tex_dir)):
        name = os.path.splitext(f)[0]
        tex = unreal.load_asset(f"{DST}/Textures/{name}")
        if tex is None:
            log("missing texture", name)
            continue
        if name.endswith("_N"):
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("flip_green_channel", True)     # authored OpenGL (+Y), Unreal is DirectX
        elif name.endswith("_BC"):
            tex.set_editor_property("srgb", True)
        else:
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
            tex.set_editor_property("srgb", False)
        # resident at full resolution: the showcase always shows the hero character up close
        tex.set_editor_property("never_stream", True)
        eal.save_loaded_asset(tex)
    log("textures", len(tasks))


# ----------------------------------------------------------------------------------------------- materials
def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    mel.connect_material_expressions(a, ao, b, bi)


def new_material(name):
    path = f"{DST}/Materials/{name}"
    fresh(path)
    return at.create_asset(name, DST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())


def make_master():
    m = new_material("M_Operative")
    m.set_editor_property("used_with_skeletal_mesh", True)
    m.set_editor_property("used_with_morph_targets", True)
    m.set_editor_property("used_with_static_lighting", False)
    dflt = unreal.load_asset(f"{DST}/Textures/T_Suit_BC")
    dnrm = unreal.load_asset(f"{DST}/Textures/T_Suit_N")
    dmsk = unreal.load_asset(f"{DST}/Textures/T_Suit_M")
    dorm = unreal.load_asset(f"{DST}/Textures/T_Suit_ORM")
    S = unreal.MaterialSamplerType
    bc = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1200, -400, parameter_name="BaseColor",
              texture=dflt, sampler_type=S.SAMPLERTYPE_COLOR)
    orm = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1200, 0, parameter_name="ORM",
               texture=dorm, sampler_type=S.SAMPLERTYPE_LINEAR_COLOR)
    nrm = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1200, 300, parameter_name="Normal",
               texture=dnrm, sampler_type=S.SAMPLERTYPE_NORMAL)
    msk = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1200, 650, parameter_name="Mask",
               texture=dmsk, sampler_type=S.SAMPLERTYPE_LINEAR_COLOR)
    team = expr(m, unreal.MaterialExpressionScalarParameter, -900, 900, parameter_name="Team", default_value=0.0)
    ca = expr(m, unreal.MaterialExpressionVectorParameter, -900, 1000, parameter_name="TeamColorA", default_value=TEAM_A)
    cb = expr(m, unreal.MaterialExpressionVectorParameter, -900, 1150, parameter_name="TeamColorB", default_value=TEAM_B)
    es = expr(m, unreal.MaterialExpressionScalarParameter, -600, 1150, parameter_name="EmissiveStrength", default_value=2.5)
    tcol = expr(m, unreal.MaterialExpressionLinearInterpolate, -600, 1000)
    link(ca, "", tcol, "A"); link(cb, "", tcol, "B"); link(team, "", tcol, "Alpha")
    emb = expr(m, unreal.MaterialExpressionLinearInterpolate, -700, 700)
    link(msk, "B", emb, "A"); link(msk, "A", emb, "B"); link(team, "", emb, "Alpha")
    acc = expr(m, unreal.MaterialExpressionMax, -500, 650)
    link(msk, "R", acc, "A"); link(emb, "", acc, "B")
    tint = expr(m, unreal.MaterialExpressionMultiply, -500, -300)
    link(bc, "RGB", tint, "A"); link(tcol, "", tint, "B")
    base = expr(m, unreal.MaterialExpressionLinearInterpolate, -300, -400)
    link(bc, "RGB", base, "A"); link(tint, "", base, "B"); link(acc, "", base, "Alpha")
    glow = expr(m, unreal.MaterialExpressionMax, -500, 800)
    link(msk, "G", glow, "A"); link(emb, "", glow, "B")
    em1 = expr(m, unreal.MaterialExpressionMultiply, -300, 900)
    link(tcol, "", em1, "A"); link(glow, "", em1, "B")
    em2 = expr(m, unreal.MaterialExpressionMultiply, -150, 900)
    link(em1, "", em2, "A"); link(es, "", em2, "B")
    P = unreal.MaterialProperty
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(orm, "R", P.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(orm, "G", P.MP_ROUGHNESS)
    mel.connect_material_property(orm, "B", P.MP_METALLIC)
    mel.connect_material_property(nrm, "RGB", P.MP_NORMAL)
    mel.connect_material_property(em2, "", P.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def make_instances(master):
    out = {}
    for s in SETS:
        name = f"MI_{s}"
        path = f"{DST}/Materials/{name}"
        fresh(path)
        mi = at.create_asset(name, DST + "/Materials", unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
        mi.set_editor_property("parent", master)
        for p, suffix in (("BaseColor", "BC"), ("ORM", "ORM"), ("Normal", "N"), ("Mask", "M")):
            tex = unreal.load_asset(f"{DST}/Textures/T_{s}_{suffix}")
            mel.set_material_instance_texture_parameter_value(mi, p, tex)
        if s == "Eye":
            mel.set_material_instance_scalar_parameter_value(mi, "EmissiveStrength", 2.0)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi)
        out["M_" + s] = mi
    return out


def make_simple_materials():
    P = unreal.MaterialProperty
    # emissive effect sphere
    m = new_material("M_Fx")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    c = expr(m, unreal.MaterialExpressionVectorParameter, -400, 0, parameter_name="Color",
             default_value=unreal.LinearColor(4, 4, 4, 1))
    mel.connect_material_property(c, "", P.MP_EMISSIVE_COLOR)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    # neutral blocks
    m = new_material("M_Block")
    c = expr(m, unreal.MaterialExpressionVectorParameter, -400, 0, parameter_name="Color",
             default_value=unreal.LinearColor(0.30, 0.31, 0.33, 1))
    r = expr(m, unreal.MaterialExpressionConstant, -400, 200, r=0.65)
    mel.connect_material_property(c, "", P.MP_BASE_COLOR)
    mel.connect_material_property(r, "", P.MP_ROUGHNESS)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    # targets
    m = new_material("M_Target")
    c = expr(m, unreal.MaterialExpressionConstant3Vector, -400, 0, constant=unreal.LinearColor(0.8, 0.1, 0.05, 1))
    e = expr(m, unreal.MaterialExpressionConstant3Vector, -400, 200, constant=unreal.LinearColor(3.0, 0.4, 0.1, 1))
    mel.connect_material_property(c, "", P.MP_BASE_COLOR)
    mel.connect_material_property(e, "", P.MP_EMISSIVE_COLOR)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    # floor with a 1 m / 25 cm grid (world aligned)
    m = new_material("M_Floor")
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -700, 0)
    cu = expr(m, unreal.MaterialExpressionCustom, -400, 0, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
              code=("float2 g = abs(frac(WP.xy / 100.0) - 0.5);\n"
                    "float2 h = abs(frac(WP.xy / 25.0) - 0.5);\n"
                    "float major = step(0.488, max(g.x, g.y));\n"
                    "float minor = step(0.475, max(h.x, h.y));\n"
                    "return lerp(float3(0.16, 0.17, 0.19), float3(0.34, 0.36, 0.40), saturate(major + 0.3 * minor));"))
    inp = unreal.CustomInput()
    inp.set_editor_property("input_name", "WP")
    cu.set_editor_property("inputs", [inp])
    link(wp, "", cu, "WP")
    r = expr(m, unreal.MaterialExpressionConstant, -400, 200, r=0.8)
    mel.connect_material_property(cu, "", P.MP_BASE_COLOR)
    mel.connect_material_property(r, "", P.MP_ROUGHNESS)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    # team icon (chevron / ring) for the billboard marker
    m = new_material("M_TeamIcon")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    tex = unreal.load_asset(f"{DST}/Textures/T_TeamIcons")
    t = expr(m, unreal.MaterialExpressionTextureSample, -700, 0, texture=tex,
             sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    team = expr(m, unreal.MaterialExpressionScalarParameter, -700, 300, parameter_name="Team", default_value=0.0)
    ca = expr(m, unreal.MaterialExpressionVectorParameter, -700, 400, parameter_name="TeamColorA", default_value=TEAM_A)
    cb = expr(m, unreal.MaterialExpressionVectorParameter, -700, 550, parameter_name="TeamColorB", default_value=TEAM_B)
    sel = expr(m, unreal.MaterialExpressionLinearInterpolate, -400, 100)
    link(t, "R", sel, "A"); link(t, "G", sel, "B"); link(team, "", sel, "Alpha")
    col = expr(m, unreal.MaterialExpressionLinearInterpolate, -400, 400)
    link(ca, "", col, "A"); link(cb, "", col, "B"); link(team, "", col, "Alpha")
    em = expr(m, unreal.MaterialExpressionMultiply, -200, 300)
    link(col, "", em, "A"); link(sel, "", em, "B")
    k = expr(m, unreal.MaterialExpressionConstant, -200, 450, r=8.0)
    em2 = expr(m, unreal.MaterialExpressionMultiply, -100, 350)
    link(em, "", em2, "A"); link(k, "", em2, "B")
    mel.connect_material_property(em2, "", P.MP_EMISSIVE_COLOR)
    mel.connect_material_property(sel, "", P.MP_OPACITY)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    # outline post process: stencil 1 = team A solid cyan, stencil 2 = team B dashed orange
    m = new_material("M_Outline")
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    m.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    sc = expr(m, unreal.MaterialExpressionSceneTexture, -700, -200,
              scene_texture_id=unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0)
    st = expr(m, unreal.MaterialExpressionSceneTexture, -700, 100, scene_texture_id=unreal.SceneTextureId.PPI_CUSTOM_STENCIL)
    uv = expr(m, unreal.MaterialExpressionScreenPosition, -700, 300)
    cu = expr(m, unreal.MaterialExpressionCustom, -400, 100, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT4,
              code=("float2 texel = View.ViewSizeAndInvSize.zw;\n"
                    "float s0 = SceneTextureLookup(UV, 25, false).r;\n"
                    "float sid = 0; float hit = 0;\n"
                    "for (int i = -2; i <= 2; i++) for (int j = -2; j <= 2; j++) {\n"
                    "  float s = SceneTextureLookup(UV + float2(i, j) * texel * 1.5, 25, false).r;\n"
                    "  if (s > 0.5 && s0 < 0.5) { hit = 1; sid = s; } }\n"
                    "float2 px = UV / texel;\n"
                    "float dash = sid > 1.5 ? step(0.45, frac((px.x + px.y) / 16.0)) : 1.0;\n"
                    "float3 col = sid > 1.5 ? float3(1.0, 0.45, 0.1) : float3(0.1, 0.85, 1.0);\n"
                    "return float4(col, hit * dash);"))
    i1 = unreal.CustomInput(); i1.set_editor_property("input_name", "UV")
    i2 = unreal.CustomInput(); i2.set_editor_property("input_name", "Stencil")
    cu.set_editor_property("inputs", [i1, i2])
    link(uv, "ViewportUV", cu, "UV")
    link(st, "Color", cu, "Stencil")
    msk = expr(m, unreal.MaterialExpressionComponentMask, -200, 200, r=False, g=False, b=False, a=True)
    link(cu, "", msk, "")
    rgb = expr(m, unreal.MaterialExpressionComponentMask, -200, 0, r=True, g=True, b=True, a=False)
    link(cu, "", rgb, "")
    scr = expr(m, unreal.MaterialExpressionComponentMask, -200, -200, r=True, g=True, b=True, a=False)
    link(sc, "Color", scr, "")
    lerp = expr(m, unreal.MaterialExpressionLinearInterpolate, 0, 0)
    link(scr, "", lerp, "A"); link(rgb, "", lerp, "B"); link(msk, "", lerp, "Alpha")
    mel.connect_material_property(lerp, "", P.MP_EMISSIVE_COLOR)
    mel.recompile_material(m); eal.save_loaded_asset(m)
    log("simple materials done")


# ----------------------------------------------------------------------------------------------- meshes
def interchange(fbx, dest, name, pipe):
    src = unreal.InterchangeManager.create_source_data(fbx)
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = True
    params.destination_name = name
    params.override_pipelines.append(unreal.SoftObjectPath(pipe.get_path_name()))
    ok = mgr.import_asset(dest, src, params)
    log("interchange", os.path.basename(fbx), ok)


def mesh_pipeline():
    p = unreal.InterchangeGenericAssetsPipeline()
    p.mesh_pipeline.import_skeletal_meshes = True
    p.mesh_pipeline.import_static_meshes = False
    p.mesh_pipeline.import_morph_targets = True
    p.mesh_pipeline.create_physics_asset = False    # the showcase uses capsule collision only
    p.mesh_pipeline.bone_influence_limit = 8
    c = p.common_meshes_properties
    c.force_all_mesh_as_type = unreal.InterchangeForceMeshType.IFMT_SKELETAL_MESH
    c.import_lods = False
    c.recompute_normals = False
    c.recompute_tangents = False
    c.use_mikk_t_space = True
    c.import_sockets = False
    p.common_skeletal_meshes_and_animations_properties.import_only_animations = False
    p.animation_pipeline.import_animations = False
    p.material_pipeline.import_materials = False
    p.material_pipeline.texture_pipeline.import_textures = False
    return p


def import_character(mis):
    # clean import: a merge into an existing skeleton would keep its old reference pose
    for a in ("Animations", "Character"):
        for path in eal.list_assets(f"{DST}/{a}", recursive=True, include_folder=False):
            eal.delete_asset(path.split(".")[0])
    interchange(os.path.join(EXP, "Operative.fbx"), DST + "/Character", "SK_Operative", mesh_pipeline())
    mesh = unreal.load_asset(DST + "/Character/SK_Operative")
    if mesh is None:
        raise RuntimeError("skeletal mesh import failed")
    mesh.set_editor_property("physics_asset", None)
    # LODs
    sub = unreal.SkeletalMeshEditorSubsystem
    for lv in (1, 2):
        fbx = os.path.join(EXP, f"Operative_LOD{lv}.fbx")
        try:
            r = sub.import_lod(mesh, lv, fbx)
        except Exception as e:          # older API location
            r = unreal.get_editor_subsystem(sub).import_lod(mesh, lv, fbx)
        log("lod", lv, r)
    log("lod screen sizes", unreal.MorphEditorTools.set_lod_screen_sizes(mesh, [1.0, 0.30, 0.12]))
    # materials by slot name
    # (array elements are struct copies in Python: rebuild the array and write it back)
    mats = []
    for sm in mesh.get_editor_property("materials"):
        slot = str(sm.get_editor_property("material_slot_name"))
        if slot in mis:
            sm.set_editor_property("material_interface", mis[slot])
        mats.append(sm)
    mesh.set_editor_property("materials", mats)
    for sm in mesh.get_editor_property("materials"):
        mi = sm.get_editor_property("material_interface")
        log("material", sm.get_editor_property("material_slot_name"), mi.get_name() if mi else None)
    # sockets on the socket bones
    skel = mesh.skeleton
    for b in skel_bone_names(skel):
        log("socket", b[5:], unreal.MorphEditorTools.add_socket(mesh, b[5:], b))
    # morph-target curve metadata so animation curves drive the morphs
    for name in mesh.get_all_morph_target_names():
        anl.add_curve_meta_data(skel, name)
        anl.set_curve_meta_data_morph_target(skel, name, True)
    eal.save_loaded_asset(mesh)
    eal.save_loaded_asset(skel)
    log("character", len(mesh.get_all_morph_target_names()), "morphs")
    return mesh


# socket bones exported with the skeleton (see source/generators/mr_skeleton.py SOCKET_PARENT)
SOCKET_BONES = ["hand_l_grip", "hand_r_grip", "muzzle_r", "cell_slot_r", "blade_base_r", "blade_tip_r",
                "beacon_holster", "fx_chest", "fx_head", "fx_ground", "fx_palm_l"]


def skel_bone_names(skel):
    return ["sock_" + s for s in SOCKET_BONES]


def import_static_beacon():
    p = unreal.InterchangeGenericAssetsPipeline()
    p.mesh_pipeline.import_skeletal_meshes = False
    p.mesh_pipeline.import_static_meshes = True
    p.common_meshes_properties.force_all_mesh_as_type = unreal.InterchangeForceMeshType.IFMT_STATIC_MESH
    try:
        p.mesh_pipeline.build_nanite = False        # a 10 cm prop: plain static mesh, material needs no Nanite usage
    except Exception as e:
        log("build_nanite not available", e)
    p.material_pipeline.import_materials = False
    p.animation_pipeline.import_animations = False
    interchange(os.path.join(EXP, "props", "SM_Beacon.fbx"), DST + "/Props", "SM_Beacon", p)
    sm = unreal.load_asset(DST + "/Props/SM_Beacon")
    if sm:
        try:
            ns = sm.get_editor_property("nanite_settings")
            ns.set_editor_property("enabled", False)
            sm.set_editor_property("nanite_settings", ns)
        except Exception as e:
            log("nanite settings", e)
        log("beacon nanite", sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
        sm.set_material(0, unreal.load_asset(DST + "/Materials/MI_Cyber"))
        eal.save_loaded_asset(sm)


# ----------------------------------------------------------------------------------------------- animations
def anim_pipeline(skel):
    p = unreal.InterchangeGenericAssetsPipeline()
    p.mesh_pipeline.import_skeletal_meshes = False
    p.mesh_pipeline.import_static_meshes = False
    p.material_pipeline.import_materials = False
    p.common_skeletal_meshes_and_animations_properties.import_only_animations = True
    p.common_skeletal_meshes_and_animations_properties.skeleton = skel
    p.animation_pipeline.import_animations = True
    p.animation_pipeline.import_bone_tracks = True
    return p


def import_animations(mesh, only=None):
    skel = mesh.skeleton
    with open(os.path.join(EXP, "animations", "clips_meta.json")) as fh:
        metas = json.load(fh)
    with open(os.path.join(EXP, "animations", "face_curves.json")) as fh:
        faces = json.load(fh)
    done = 0
    for cid, meta in sorted(metas.items()):
        if only and cid not in only:
            continue
        fbx = os.path.join(EXP, "animations", cid + ".fbx")
        fresh(f"{DST}/Animations/A_{cid}")     # a replacing import would keep (and then duplicate) old notifies
        interchange(fbx, DST + "/Animations", "A_" + cid, anim_pipeline(skel))
        seq = unreal.load_asset(f"{DST}/Animations/A_{cid}")
        if seq is None:
            log("anim import failed", cid)
            continue
        fps = 30.0
        # markers -> Morph event notifies (the track must exist before events can be added to it)
        if meta.get("markers") and not anl.is_valid_anim_notify_track_name(seq, "Morph"):
            anl.add_animation_notify_track(seq, "Morph")
        for f, name in meta.get("markers", []):
            n = anl.add_animation_notify_event(seq, "Morph", float(f) / fps, unreal.MorphEventNotify)
            if n:
                n.set_editor_property("event_name", name)
        # face morph curves
        fc = faces.get(cid, {}).get("curves", {})
        for name, vals in fc.items():
            anl.add_curve(seq, name, unreal.RawCurveTrackTypes.RCT_FLOAT, False)
            times = [i / fps for i in range(len(vals))]
            anl.add_float_curve_keys(seq, name, times, [float(v) for v in vals])
        # additive layers: directional hits and the face control poses (base = frame 0)
        if cid.startswith("hit_") or cid.startswith("ctl_"):
            seq.set_editor_property("additive_anim_type", unreal.AdditiveAnimationType.AAT_LOCAL_SPACE_BASE)
            seq.set_editor_property("ref_pose_type", unreal.AdditiveBasePoseType.ABPT_LOCAL_ANIM_FRAME)
            seq.set_editor_property("ref_frame_index", 0)
        if meta.get("root") == "root_motion":
            anl.set_root_motion_enabled(seq, True)
            anl.set_root_motion_lock_type(seq, getattr(unreal.RootMotionRootLock, "REF_POSE", None) or getattr(unreal.RootMotionRootLock, "RRL_REF_POSE"))
        n_ev = len(anl.get_animation_notify_events(seq))
        if n_ev != len(meta.get("markers", [])):
            log("notify mismatch", cid, n_ev, len(meta.get("markers", [])))
        eal.save_loaded_asset(seq)
        done += 1
    log("animations", done)


# ----------------------------------------------------------------------------------------------- data / audio / map
def read_csv():
    import csv
    rows = {}
    with open(os.path.join(ROOT, "docs", "required_animations.csv")) as fh:
        for r in csv.DictReader(fh):
            rows[r["id"]] = r
    return rows


def write_clip_table():
    with open(os.path.join(EXP, "animations", "clips_meta.json")) as fh:
        metas = json.load(fh)
    req = read_csv()
    clips = []
    for cid, m in sorted(metas.items()):
        clips.append({
            "id": cid, "asset": f"{DST}/Animations/A_{cid}.A_{cid}", "frames": int(m["frames"]),
            "loop": bool(m["loop"]), "form": m["form"], "root": m["root"], "layer": m["layer"],
            "speed_cms": float(m.get("speed_cms", 0.0)), "entry": m.get("entry", ""), "exit": m.get("exit", ""),
            "notes": m.get("notes", ""), "required": cid in req,
            "behavior": req.get(cid, {}).get("required_behavior", ""),
        })
    os.makedirs(os.path.join(CONTENT, "Data"), exist_ok=True)
    with open(os.path.join(CONTENT, "Data", "clips.json"), "w") as fh:
        json.dump({"clips": clips}, fh, indent=1)
    log("clip table", len(clips), "clips,", sum(1 for c in clips if c["required"]), "required")


def import_audio():
    t = unreal.AssetImportTask()
    t.filename = os.path.join(ROOT, "source", "audio", "dialogue.wav")
    t.destination_path = DST + "/Audio"
    t.destination_name = "SW_Dialogue"
    t.automated = True
    t.replace_existing = True
    t.save = True
    at.import_asset_tasks([t])
    log("audio", eal.does_asset_exist(DST + "/Audio/SW_Dialogue"))


def make_map():
    path = DST + "/Maps/Showcase"
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not eal.does_asset_exist(path):
        les.new_level(path)
    else:
        les.load_level(path)
    les.save_current_level()
    log("map", path)


def main():
    stage = os.environ.get("MR_STAGE", "all")
    only = [x for x in os.environ.get("MR_ONLY", "").split(",") if x]
    if stage in ("all", "assets"):
        import_textures()
        master = make_master()
        mis = make_instances(master)
        make_simple_materials()
        mesh = import_character(mis)
        import_static_beacon()
        import_audio()
    else:
        mesh = unreal.load_asset(DST + "/Character/SK_Operative")
    # the mesh import recreates the skeleton (and deletes the old animations), so it always re-imports them
    import_animations(mesh, only if stage == "anims" else None)
    write_clip_table()
    make_map()
    unreal.EditorAssetLibrary.save_directory(DST, only_if_is_dirty=True, recursive=True)
    log("DONE")


main()

"""Data asset registry (DA_OperativeAssets) and the showcase level."""
import os
import json
import time
import unreal
import common as C


def _load_or_none(path):
    return unreal.load_asset(path) if C.eal().does_asset_exist(path) else None


def _read(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def run_assets(ctx):
    """Create or update /Game/Operative/DA_OperativeAssets: hard references to everything the runtime needs plus the JSON texts."""
    C.ensure_dir(C.GAME)
    da = _load_or_none(C.DATA_ASSET)
    if da is None:
        factory = unreal.DataAssetFactory()
        da = C.asset_tools().create_asset("DA_OperativeAssets", C.GAME, unreal.OperativeAssets, factory)
    if da is None:
        raise RuntimeError("could not create DA_OperativeAssets")

    mesh = _load_or_none(C.MESH_PATH)
    clips = []
    missing = []
    for entry in ctx.manifest["clips"]:
        a = _load_or_none(entry["unreal_asset"])
        if isinstance(a, unreal.AnimSequence):
            clips.append(a)
        else:
            missing.append(entry["id"])
    if missing:
        C.warn("clips missing in the project:", missing)
    da.set_editor_property("mesh", mesh)
    da.set_editor_property("clips", clips)
    da.set_editor_property("power_cell_mesh", _load_or_none(C.PROP_DIR + "/SM_PowerCell"))
    da.set_editor_property("beacon_mesh", _load_or_none(C.PROP_DIR + "/SM_Beacon"))
    da.set_editor_property("dialogue_sound", _load_or_none(C.AUDIO_DIR + "/dialogue"))
    for prop, shape in (("cube_mesh", "Cube"), ("sphere_mesh", "Sphere"), ("cylinder_mesh", "Cylinder"), ("plane_mesh", "Plane")):
        da.set_editor_property(prop, unreal.load_asset("/Engine/BasicShapes/%s.%s" % (shape, shape)))
    slots = [str(m.material_slot_name) for m in mesh.materials] if mesh else []
    da.set_editor_property("material_slot_names", slots)
    team_a = [_load_or_none(C.MAT_DIR + "/MI_%s_TeamA" % s.replace("MI_", "")) for s in slots]
    team_b = [_load_or_none(C.MAT_DIR + "/MI_%s_TeamB" % s.replace("MI_", "")) for s in slots]
    da.set_editor_property("team_a_materials", team_a)
    da.set_editor_property("team_b_materials", team_b)
    da.set_editor_property("outline_materials", [m for m in (_load_or_none(C.MAT_DIR + "/MI_Outline_TeamA"), _load_or_none(C.MAT_DIR + "/MI_Outline_TeamB")) if m])
    extra = {}
    for key, name in (("Normal", "M_DebugNormal"), ("Clay", "M_Clay"), ("Wireframe", "M_Wireframe"), ("Fx", "M_Fx"), ("Floor", "M_ShowcaseFloor"),
                      ("Target", "M_ShowcaseTarget"), ("Wall", "M_ShowcaseWall"), ("Prop", "M_ShowcaseProp"),
                      ("StudioFloor", "M_StudioFloor"), ("StudioWall", "M_StudioWall")):
        m = _load_or_none(C.MAT_DIR + "/" + name)
        if m:
            extra[key] = m
    da.set_editor_property("extra_materials", extra)
    da.set_editor_property("manifest_json", _read(os.path.join(ctx.docs, "animation_manifest.json")))
    da.set_editor_property("sockets_json", _read(os.path.join(ctx.docs, "skeleton_and_sockets.json")))
    da.set_editor_property("alignment_json", _read(os.path.join(ctx.source, "audio", "dialogue_alignment.json")))
    da.set_editor_property("import_stamp", time.strftime("%Y-%m-%d %H:%M:%S"))
    C.save(da)
    C.log("data asset saved: clips=%d slots=%d extras=%s" % (len(clips), len(slots), sorted(extra)))


def run_level(ctx):
    """Create /Game/Showcase/L_Showcase: a ShowcaseRoom actor (builds the room at BeginPlay) and a PlayerStart."""
    C.ensure_dir(C.SHOWCASE_DIR)
    level_path = C.SHOWCASE_DIR + "/L_Showcase"
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    room = eas.spawn_actor_from_class(unreal.ShowcaseRoom, unreal.Vector(0, 0, 0))
    room.set_actor_label("ShowcaseRoom")
    start = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 92), unreal.Rotator(0, 0, 0))
    start.set_actor_label("PlayerStart")
    try:
        ws = world.get_world_settings()
        ws.set_editor_property("default_game_mode", unreal.ShowcaseGameMode)
    except Exception as e:  # the project default game mode covers this as well
        C.warn("world settings game mode not set:", e)
    ok = unreal.EditorLoadingAndSavingUtils.save_map(world, level_path)
    C.log("level saved", level_path, ok)

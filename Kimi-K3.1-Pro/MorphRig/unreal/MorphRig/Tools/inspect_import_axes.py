"""Import an isolated orientation probe without replacing the delivered asset."""
from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
namespace = {"__file__": str(ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py")}
source = (ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py").read_text()
exec(source[:source.index("\ntry:\n    main()")], namespace)
name = "SK_AxesUp_v6"
folder = "/Game/Operative/Diagnostics"
options = namespace["skeletal_options"]()
options.skeletal_mesh_import_data.force_front_x_axis = False
options.skeletal_mesh_import_data.import_mesh_lods = False
mesh = next(obj for obj in namespace["run_task"](ROOT / "export" / "Operative_LOD0.fbx", folder, name, options, unreal.FbxFactory()) if isinstance(obj, unreal.SkeletalMesh))
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
unreal.log_warning(f"PROBE_SKELETON {mesh.skeleton} mesh={mesh.get_path_name()} morphs={len(mesh.get_all_morph_target_names())}")
assert mesh.skeleton and len(mesh.skeleton.get_reference_pose().get_bone_names()) == 70
assert editor.save_asset(mesh.skeleton.get_path_name().split(".")[0], only_if_is_dirty=False)
mesh_editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
for lod in (1, 2):
    assert mesh_editor.import_lod(mesh, lod, str(ROOT / "export" / f"Operative_LOD{lod}.fbx")) == lod
slots = list(mesh.get_editor_property("materials"))
for slot in slots:
    slot.material_interface = unreal.load_asset("/Game/Operative/Materials/" + str(slot.material_slot_name))
mesh.set_editor_property("materials", slots)
assert mesh.skeleton
animation_options = namespace["animation_options"](mesh.skeleton)
animation_options.anim_sequence_import_data.force_front_x_axis = False
clip = next(obj for obj in namespace["run_task"](ROOT / "export" / "animations" / "idle_relaxed.fbx", folder, "idle_axes_up_v6", animation_options, unreal.FbxFactory()) if isinstance(obj, unreal.AnimSequence))
assert clip.get_editor_property("skeleton") == mesh.skeleton
assert mesh_editor.get_lod_count(mesh) == 3
assert all(unreal.MorphAuditLibrary.get_lod_morph_target_count(mesh, lod) == 26 for lod in range(3))
for asset in (mesh, mesh.skeleton, clip):
    assert editor.save_asset(asset.get_path_name().split(".")[0], only_if_is_dirty=False)

def tr(value):
    return {"location": namespace["vec"](value.translation), "rotation": str(value.rotation), "scale": namespace["vec"](value.scale3d)}

bind = json.loads(unreal.MorphAuditLibrary.describe_bind_pose(mesh))
names = [item["name"] for item in bind["bones"]]
poses = [unreal.AnimationLibrary.get_bone_pose_for_frame(clip, bone, 0, False) for bone in names]
world = []
for index, pose in enumerate(poses):
    parent = bind["bones"][index]["parent"]
    world.append(pose if parent < 0 else pose * world[parent])
result = {
    "mesh": mesh.get_path_name(), "clip": clip.get_path_name(),
    "height_cm": mesh.get_bounds().box_extent.z * 2,
    "bones": len(names), "lods": unreal.SkeletalMeshEditorSubsystem.get_lod_count(mesh),
    "morphs": len(mesh.get_all_morph_target_names()),
    "axis_evidence": namespace["infer_import_rotation"](mesh),
    "samples": {bone: {"reference": tr(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, bone)), "evaluated": tr(world[names.index(bone)]), "local_track": tr(poses[names.index(bone)])} for bone in ("root", "pelvis", "neck", "head", "eye_L", "hand_L", "foot_L")},
    "bind_pose": json.loads(unreal.MorphAuditLibrary.describe_bind_pose(mesh)),
}
path = ROOT / "docs" / "validation" / "import_axes_probe.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items() if key != "bind_pose"}, indent=2), flush=True)

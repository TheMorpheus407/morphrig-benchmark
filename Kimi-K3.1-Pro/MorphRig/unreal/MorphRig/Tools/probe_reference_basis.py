from pathlib import Path
import json
import math
import unreal

ROOT = Path(__file__).resolve().parents[3]
FOLDER = "/Game/Operative/Diagnostics"
NAME = "SK_AxesUp_v8"
CLIP_NAME = "idle_axes_up_v8"
namespace = {"__file__": str(ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py")}
source = (ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py").read_text()
exec(source[:source.index("\ntry:\n    main()")], namespace)


def transform(value):
    return {
        "location": namespace["vec"](value.translation),
        "rotation_quaternion": [value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w],
        "scale": namespace["vec"](value.scale3d),
    }


def forward_options(options):
    namespace["props"](options, {
        "convert_scene": True,
        "convert_scene_unit": False,
        "force_front_x_axis": True,
        "coordinate_system_policy": unreal.CoordinateSystemPolicy.MATCH_UP_FORWARD_AXES,
    })
    print("PROBE_OPTIONS", {name: str(options.get_editor_property(name)) for name in ("using_luf_coordinate_sysem", "convert_scene", "convert_scene_unit", "force_front_x_axis", "coordinate_system_policy", "import_uniform_scale")}, flush=True)


def snapshot(mesh, sequence):
    names = [str(name) for name in mesh.skeleton.get_reference_pose().get_bone_names()]
    local = {name: transform(mesh.skeleton.get_reference_pose().get_ref_bone_pose(name, unreal.AnimPoseSpaces.LOCAL)) for name in names}
    result = {
        "axis_evidence": namespace["infer_import_rotation"](mesh),
        "root_reference": local["root"],
        "mesh_root_reference": transform(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, "root")),
        "root_animation": transform(unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, "root", 0, False)) if sequence else None,
        "local_transforms": local,
        "height_cm": mesh.get_bounds().box_extent.z * 2,
        "bind": json.loads(unreal.MorphAuditLibrary.describe_bind_pose(mesh)),
    }
    return result


def summary(value):
    return {key: item for key, item in value.items() if key not in ("bind", "local_transforms")}


editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
options = namespace["skeletal_options"]()
options.skeletal_mesh_import_data.import_mesh_lods = False
forward_options(options.skeletal_mesh_import_data)
mesh = next(obj for obj in namespace["run_task"](ROOT / "export" / "Operative_LOD0.fbx", FOLDER, NAME, options, unreal.FbxFactory()) if isinstance(obj, unreal.SkeletalMesh))
assert mesh.skeleton and len(mesh.skeleton.get_reference_pose().get_bone_names()) == 70
stages = {"base": snapshot(mesh, None)}
print("PROBE_STAGE base", json.dumps(summary(stages["base"])), flush=True)
assert editor.save_asset(mesh.skeleton.get_path_name().split(".")[0], only_if_is_dirty=False)
mesh_editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
for lod in (1, 2):
    assert mesh_editor.import_lod(mesh, lod, str(ROOT / "export" / f"Operative_LOD{lod}.fbx")) == lod
    stages["lod" + str(lod)] = snapshot(mesh, None)
    print("PROBE_STAGE lod" + str(lod), json.dumps(summary(stages["lod" + str(lod)])), flush=True)
slots = list(mesh.get_editor_property("materials"))
for slot in slots:
    slot.material_interface = unreal.load_asset("/Game/Operative/Materials/" + str(slot.material_slot_name))
mesh.set_editor_property("materials", slots)
assert editor.save_asset(mesh.get_path_name().split(".")[0], only_if_is_dirty=False)
animation_options = namespace["animation_options"](mesh.skeleton)
forward_options(animation_options.anim_sequence_import_data)
clip = next(obj for obj in namespace["run_task"](ROOT / "export" / "animations" / "idle_relaxed.fbx", FOLDER, CLIP_NAME, animation_options, unreal.FbxFactory()) if isinstance(obj, unreal.AnimSequence))
assert editor.save_asset(clip.get_path_name().split(".")[0], only_if_is_dirty=False)
before = snapshot(mesh, clip)
assert unreal.MorphAuditLibrary.align_root_reference_to_animation(mesh, clip)
for asset in (mesh, mesh.skeleton, clip):
    assert editor.save_asset(asset.get_path_name().split(".")[0], only_if_is_dirty=False)
after = snapshot(mesh, clip)
non_root_changes = []
for name, a in before["local_transforms"].items():
    if name == "root":
        continue
    b = after["local_transforms"][name]
    quaternion_dot = min(1.0, abs(sum(x * y for x, y in zip(a["rotation_quaternion"], b["rotation_quaternion"]))))
    error = {
        "bone": name,
        "position_cm": math.dist(a["location"], b["location"]),
        "angle_degrees": math.degrees(2 * math.acos(quaternion_dot)),
        "scale_error": max(abs(x - y) for x, y in zip(a["scale"], b["scale"])),
    }
    if error["position_cm"] > .001 or error["angle_degrees"] > .001 or error["scale_error"] > .00001:
        error["before"] = a
        error["after"] = b
        non_root_changes.append(error)
hierarchy_unchanged = [bone["parent"] for bone in before["bind"]["bones"]] == [bone["parent"] for bone in after["bind"]["bones"]]
root_quaternion_dot = min(1.0, abs(sum(x * y for x, y in zip(after["root_reference"]["rotation_quaternion"], after["root_animation"]["rotation_quaternion"]))))
root_angle_degrees = math.degrees(2 * math.acos(root_quaternion_dot))

(ROOT / "docs" / "validation" / "reference_basis_probe.json").write_text(json.dumps({
    "stages": {name: summary(value) for name, value in stages.items()},
    "before": summary(before), "after": summary(after),
    "non_root_local_changes": non_root_changes,
    "root_angle_degrees": root_angle_degrees,
}, indent=2) + "\n")
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0))
try:
    component = actor.skeletal_mesh_component
    component.set_skeletal_mesh_asset(mesh)
    component.play_animation(clip, False)
    component.set_position(0.0, False)
    component.play(False)
    geometry = json.loads(unreal.MorphAuditLibrary.describe_skinned_geometry(component))
    (ROOT / "docs" / "validation" / "reference_basis_geometry.json").write_text(json.dumps(geometry, indent=2) + "\n")
    assert geometry.get("sections"), "No evaluated native geometry"
    for section in geometry["sections"]:
        for sample in section["samples"]:
            assert all(value == value for value in sample["skinned"])
finally:
    unreal.EditorLevelLibrary.destroy_actor(actor)
expected_matrix = [[0, -1, 0], [-1, 0, 0], [0, 0, 1]]
result = {
    "status": "EVALUATED_NOT_YET_VISUALLY_APPROVED",
    "mesh": mesh.get_path_name(), "clip": clip.get_path_name(),
    "bones": len(after["local_transforms"]),
    "lods": mesh_editor.get_lod_count(mesh),
    "morphs_per_lod": [unreal.MorphAuditLibrary.get_lod_morph_target_count(mesh, lod) for lod in range(3)],
    "triangles_per_lod": [unreal.MorphAuditLibrary.get_lod_triangle_count(mesh, lod) for lod in range(3)],
    "expected_original_matrix": expected_matrix,
    "original_matrix_recovered": before["axis_evidence"]["source_to_unreal_matrix"] == expected_matrix,
    "original_matrix_retained": after["axis_evidence"]["source_to_unreal_matrix"] == expected_matrix,
    "non_root_local_changes": non_root_changes,
    "hierarchy_unchanged": hierarchy_unchanged,
    "root_angle_degrees": root_angle_degrees,
    "root_location_preserved": before["root_reference"]["location"] == after["root_reference"]["location"],
    "root_scale_preserved": before["root_reference"]["scale"] == after["root_reference"]["scale"],
    "stages": {name: summary(value) for name, value in stages.items()},
    "before": summary(before), "after": summary(after),
    "evaluated_geometry": "docs/validation/reference_basis_geometry.json",
}
(ROOT / "docs" / "validation" / "reference_basis_probe.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2), flush=True)

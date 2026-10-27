from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
source = (ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py").read_text()
namespace = {"__file__": str(ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py")}
exec(source[:source.index("\ntry:\n    main()")], namespace)
options = namespace["skeletal_options"]()
options.skeletal_mesh_import_data.import_mesh_lods = False
objects = namespace["run_task"](ROOT / "export" / "Operative_LOD0.fbx", "/Game/Operative/Diagnostics", "UnitProbe", options, unreal.FbxFactory())
mesh = next(obj for obj in objects if isinstance(obj, unreal.SkeletalMesh))
result = {"skeleton": mesh.skeleton.get_path_name(), "height_cm": mesh.get_bounds().box_extent.z * 2, "morphs": len(mesh.get_all_morph_target_names()), "bones": {}, "lod_imports": []}
result["pose_api"] = mesh.skeleton.get_reference_pose().get_ref_bone_pose.__doc__
result["animation_pose_methods"] = {name: getattr(unreal.AnimationLibrary, name).__doc__ for name in dir(unreal.AnimationLibrary) if "bone_pose" in name or "root_motion" in name}
probe = namespace["run_task"](ROOT / "export" / "animations" / "dash_f.fbx", "/Game/Operative/Diagnostics", "DashProbe", namespace["animation_options"](mesh.skeleton), unreal.FbxFactory())
result["animation_imports"] = [obj.get_path_name() for obj in probe]
sequence = next(obj for obj in probe if isinstance(obj, unreal.AnimSequence))
result["import_settings"] = {name: str(mesh.get_editor_property("asset_import_data").get_editor_property(name)) for name in ("convert_scene_unit", "convert_scene", "import_uniform_scale")}
result["dash_samples"] = []
for frame in (0, 18):
    bones = [str(name) for name in mesh.skeleton.get_reference_pose().get_bone_names()]
    poses = unreal.AnimationLibrary.get_bone_poses_for_frame(sequence, bones, frame, False, preview_mesh=mesh)
    world = {}
    for name, pose in zip(bones, poses):
        parent = str(unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).get_bone_parent(mesh, name))
        world[name] = pose if parent == "None" else pose * world[parent]
    result["dash_samples"].append({"frame": frame, "local_root": {"translation": [poses[0].translation.x, poses[0].translation.y, poses[0].translation.z], "rotation": [poses[0].rotation.x, poses[0].rotation.y, poses[0].rotation.z, poses[0].rotation.w]}, "evaluated_world": {name: {"translation": [world[name].translation.x, world[name].translation.y, world[name].translation.z], "scale": [world[name].scale3d.x, world[name].scale3d.y, world[name].scale3d.z]} for name in ("root", "pelvis", "head", "hand_L", "eye_L")}})
result["curve_value_methods"] = {name: getattr(unreal.AnimationLibrary, name).__doc__ for name in dir(unreal.AnimationLibrary) if "curve" in name and "value" in name}
for name in ("root", "pelvis", "head", "eye_L", "hand_L", "hand_R"):
    for space in (unreal.AnimPoseSpaces.LOCAL, unreal.AnimPoseSpaces.WORLD):
        transform = mesh.skeleton.get_reference_pose().get_ref_bone_pose(name, space)
        result["bones"].setdefault(name, {})[str(space)] = {"translation": [transform.translation.x, transform.translation.y, transform.translation.z], "scale": [transform.scale3d.x, transform.scale3d.y, transform.scale3d.z], "rotation": [transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w]}
for index in (1, 2):
    imported = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).import_lod(mesh, index, str(ROOT / "export" / f"Operative_LOD{index}.fbx"))
    result["lod_imports"].append({"index": index, "returned": imported, "triangle_count": unreal.MorphAuditLibrary.get_lod_triangle_count(mesh, index)})
data = unreal.FbxImportUI().anim_sequence_import_data
result["pose_range_options"] = {}
for name in dir(data):
    if "range" in name or "frame" in name or "sample_rate" in name:
        try:
            result["pose_range_options"][name] = str(data.get_editor_property(name))
        except Exception as error:
            result["pose_range_options"][name] = str(error)
model = sequence.get_editor_property("data_model_interface")
result["model_curve_methods"] = {name: getattr(model, name).__doc__ for name in dir(model) if "curve" in name and callable(getattr(model, name))}
path = ROOT / "docs" / "validation" / "native_unit_probe.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print("MORPH_UNIT_PROBE", json.dumps(result), flush=True)

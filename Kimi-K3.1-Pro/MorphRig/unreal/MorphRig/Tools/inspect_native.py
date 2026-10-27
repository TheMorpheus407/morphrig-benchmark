from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
mesh = unreal.load_asset("/Game/Operative/SK_Operative_Production") or unreal.load_asset("/Game/Operative/SK_Operative")
result = {"mesh": str(mesh), "import_data": {}, "morphs": {}, "lods": []}
if mesh:
    result["height_cm"] = mesh.get_bounds().box_extent.z * 2
    result["lod_count"] = unreal.SkeletalMeshEditorSubsystem.get_lod_count(mesh)
    data = mesh.get_editor_property("asset_import_data")
    result["import_data_class"] = data.get_class().get_name() if data else None
    if data:
        for name in ("convert_scene_unit", "convert_scene", "import_uniform_scale", "import_morph_targets", "import_mesh_lods", "coordinate_system_policy", "force_front_x_axis", "using_luf_coordinate_system", "using_luf_coordinate_sysem"):
            try:
                result["import_data"][name] = str(data.get_editor_property(name))
            except Exception as error:
                result["import_data"][name] = str(error)
    result["morphs"] = {
        "all_names": [str(name) for name in mesh.get_all_morph_target_names()],
    }
    for index, model in enumerate(mesh.get_editor_property("source_models")):
        record = {"lod": index}
        for name in ("morph_targets", "triangle_count", "screen_size"):
            try:
                value = model.get_editor_property(name)
                record[name] = [str(item) for item in value] if name == "morph_targets" else str(value)
            except Exception as error:
                record[name] = str(error)
        result["lods"].append(record)
    result["bone_transforms"] = {}
    for name in ("root", "pelvis", "head", "eye_L"):
        pose = mesh.skeleton.get_reference_pose().get_ref_bone_pose(name, unreal.AnimPoseSpaces.WORLD)
        result["bone_transforms"][name] = {"location": [pose.translation.x, pose.translation.y, pose.translation.z], "scale": [pose.scale3d.x, pose.scale3d.y, pose.scale3d.z], "quaternion": [pose.rotation.x, pose.rotation.y, pose.rotation.z, pose.rotation.w]}
result["notify_api"] = unreal.AnimationLibrary.add_animation_notify_event.__doc__
result["notify_instances"] = []
sequence = unreal.load_asset("/Game/Operative/Animations/dash_f")
if sequence:
    for event in unreal.AnimationLibrary.get_animation_notify_events(sequence):
        notify = event.get_editor_property("notify")
        result["notify_instances"].append({"timeline_name": str(event.get_editor_property("notify_name")), "object": notify.get_path_name() if notify else None, "event_name": str(notify.get_editor_property("event_name")) if notify else None})
parent = unreal.Transform(location=unreal.Vector(10, 0, 0), rotation=unreal.Rotator(0, 0, 90))
local = unreal.Transform(location=unreal.Vector(1, 0, 0))
relative = local.make_relative(parent)
def xyz(transform):
    return [transform.translation.x, transform.translation.y, transform.translation.z]
result["composition_probe"] = {"parent_times_local": xyz(parent * local), "local_times_parent": xyz(local * parent), "relative": xyz(relative), "relative_times_parent": xyz(relative * parent), "parent_times_relative": xyz(parent * relative), "multiply_doc": unreal.Transform.__mul__.__doc__}
result["bind_pose"] = json.loads(unreal.MorphAuditLibrary.describe_bind_pose(mesh))
result["quaternion_probes"] = {}
sequence = unreal.load_asset("/Game/Operative/Animations/idle_relaxed")
model = sequence.get_editor_property("data_model_interface")
result["track_api"] = {"methods": [name for name in dir(model) if "bone" in name or "local" in name], "bone_pose_doc": unreal.AnimationLibrary.get_bone_pose_for_frame.__doc__}
for name in ("root", "pelvis", "head", "eye_L"):
    pose = unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, name, 0, False)
    q = pose.rotation
    result["quaternion_probes"][name] = {
        "transform": str(pose),
        "euler": str(q.rotator()),
        "x_rotated": str(q.rotate_vector(unreal.Vector(1, 0, 0))) if hasattr(q, "rotate_vector") else "unavailable",
        "y_rotated": str(q.rotate_vector(unreal.Vector(0, 1, 0))) if hasattr(q, "rotate_vector") else "unavailable",
        "z_rotated": str(q.rotate_vector(unreal.Vector(0, 0, 1))) if hasattr(q, "rotate_vector") else "unavailable",
    }
result["yaw90"] = str(unreal.Rotator(pitch=0, yaw=90, roll=0).quaternion())
result["roll90"] = str(unreal.Rotator(pitch=0, yaw=0, roll=90).quaternion())
result["pitch90"] = str(unreal.Rotator(pitch=90, yaw=0, roll=0).quaternion())
result["clip_rates"] = {}
for name in ("idle_relaxed", "dialogue", "deploy"):
    clip = unreal.load_asset("/Game/Operative/Animations/" + name)
    model = clip.get_editor_property("data_model_interface")
    result["clip_rates"][name] = {
        "play_length": clip.get_play_length(),
        "rate_scale": clip.get_editor_property("rate_scale"),
        "frame_rate": str(model.get_frame_rate()),
        "sampled_keys": unreal.AnimationLibrary.get_num_frames(clip),
        "frames": model.get_num_frames() if hasattr(model, "get_num_frames") else None,
    }
print(json.dumps(result, indent=2), flush=True)
(ROOT / "docs" / "validation" / "native_import_diagnosis.json").write_text(json.dumps(result, indent=2) + "\n")

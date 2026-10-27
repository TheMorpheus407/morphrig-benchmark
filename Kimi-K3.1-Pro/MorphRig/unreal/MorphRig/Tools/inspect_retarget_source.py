from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
base = "/Game/Operative/Diagnostics/BasisSource/"
source = unreal.load_asset("/Game/Operative/SK_Operative")
target = source
sequence = unreal.load_asset("/Game/Operative/Diagnostics/SourceProbe/original_idle")
if not source or not target or not sequence:
    raise RuntimeError("Required persisted staging mesh or clip is unavailable")
model = sequence.get_editor_property("data_model_interface")
record = {
    "clip": sequence.get_path_name(),
    "clip_skeleton": sequence.get_editor_property("skeleton").get_path_name(),
    "track_count": model.get_num_bone_tracks(),
    "track_names": [str(name) for name in model.get_bone_track_names()],
    "source_mesh": source.get_path_name(),
    "source_skeleton": source.skeleton.get_path_name(),
    "source_bones": [str(name) for name in source.skeleton.get_reference_pose().get_bone_names()],
    "source_reference": unreal.MorphAuditLibrary.describe_bind_pose(source),
    "target_mesh": target.get_path_name(),
    "target_skeleton": target.skeleton.get_path_name(),
    "target_bones": [str(name) for name in target.skeleton.get_reference_pose().get_bone_names()],
    "target_reference": unreal.MorphAuditLibrary.describe_bind_pose(target),
}
probe = unreal.EditorAssetLibrary.duplicate_asset(sequence.get_path_name().split(".")[0], "/Engine/Transient/MorphRetargetProbe")
if not probe:
    raise RuntimeError("Could not create transient retarget probe")
result = unreal.MorphAuditLibrary.align_animation_root_to_reference(source, target, [probe])
model = probe.get_editor_property("data_model_interface")
record["probe"] = {
    "result": result,
    "skeleton": probe.get_editor_property("skeleton").get_path_name(),
    "track_count": model.get_num_bone_tracks(),
    "track_names": [str(name) for name in model.get_bone_track_names()],
    "float_curve_count": len(unreal.AnimationLibrary.get_animation_curve_names(probe, unreal.RawCurveTrackTypes.RCT_FLOAT)),
    "root_pose": str(unreal.AnimationLibrary.get_bone_pose_for_frame(probe, "root", 0, False)),
    "target_root_reference": str(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(target, "root")),
}
print("MORPH_RETARGET_INSPECTION " + json.dumps(record), flush=True)
(ROOT / "docs" / "validation" / "retarget_source_inspection.json").write_text(json.dumps(record, indent=2) + "\n")
if not result or record["probe"]["track_count"] != 70 or record["probe"]["skeleton"] != target.skeleton.get_path_name():
    raise RuntimeError("Transient native retarget probe failed")

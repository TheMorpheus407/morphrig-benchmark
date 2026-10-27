from pathlib import Path
import json
import sys
import unreal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
import import_operative as ops

source = unreal.load_asset("/Game/Operative/Diagnostics/BasisSource/SK_Operative_BasisSource")
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
if not source:
    raise RuntimeError("Isolated original-basis source mesh is missing")
report = {}
for name in ("Pose_DirectAligned", "Pose_RootCorrected", "Pose_DirectIdle", "Pose_RootIdle"):
    path = "/Game/Operative/Diagnostics/" + name
    if unreal.load_asset(path) and not editor.delete_asset(path):
        raise RuntimeError("Could not reset comparison asset " + path)
for label, mesh_name, clip_name in (("direct_aligned", "Pose_DirectAligned", "Pose_DirectIdle"), ("root_corrected", "Pose_RootCorrected", "Pose_RootIdle")):
    mesh = unreal.EditorAssetLibrary.duplicate_asset(source.get_path_name().split(".")[0], "/Game/Operative/Diagnostics/" + mesh_name)
    if not mesh:
        raise RuntimeError("Could not duplicate the original mesh for " + label)
    objects = ops.run_task(ROOT / "export" / "animations" / "idle_relaxed.fbx", "/Game/Operative/Diagnostics", clip_name, ops.animation_options(source.skeleton), unreal.FbxFactory())
    sequence = next(obj for obj in objects if isinstance(obj, unreal.AnimSequence))
    if label == "direct_aligned":
        corrected = unreal.MorphAuditLibrary.align_root_reference_to_animation(mesh, sequence)
    else:
        corrected = unreal.MorphAuditLibrary.align_animation_root_to_reference(mesh, mesh, [sequence])
    record = {
        "corrected": corrected,
        "mesh": mesh.get_path_name(),
        "clip": sequence.get_path_name(),
        "mesh_skeleton": mesh.skeleton.get_path_name(),
        "clip_skeleton": sequence.get_editor_property("skeleton").get_path_name(),
        "root_reference": str(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, "root")),
        "root_animation": str(unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, "root", 0, False)),
        "basis": ops.infer_import_rotation(mesh),
        "tracks": sequence.get_editor_property("data_model_interface").get_num_bone_tracks(),
    }
    report[label] = record
    for asset in (mesh, mesh.skeleton, sequence):
        if not editor.save_asset(asset.get_path_name().split(".")[0], only_if_is_dirty=False):
            raise RuntimeError("Could not save isolated comparison " + asset.get_path_name())
(ROOT / "docs" / "validation" / "direct_import_comparison.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)

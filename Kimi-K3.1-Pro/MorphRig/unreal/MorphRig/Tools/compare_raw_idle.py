from pathlib import Path
import json
import sys
import unreal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
import import_operative as ops

mesh = unreal.load_asset("/Game/Operative/SK_Operative")
source = unreal.load_asset("/Game/Operative/Diagnostics/BasisSource/SK_AnimationSource")
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
report = {}
for kind, skeleton in (("diagonal", source.skeleton), ("original", mesh.skeleton)):
    path = "/Game/Operative/Diagnostics/SourceProbe/" + kind + "_idle"
    if unreal.load_asset(path) and not editor.delete_asset(path):
        raise RuntimeError("Cannot reset source comparison " + path)
    objects = ops.run_task(ROOT / "export" / "animations" / "idle_relaxed.fbx", "/Game/Operative/Diagnostics/SourceProbe", kind + "_idle", ops.animation_options(skeleton), unreal.FbxFactory())
    sequence = next(obj for obj in objects if isinstance(obj, unreal.AnimSequence))
    report[kind] = {
        "skeleton": skeleton.get_path_name(),
        "sequence_skeleton": sequence.get_editor_property("skeleton").get_path_name(),
        "reference_root_local": str(skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL)),
        "tracks": sequence.get_editor_property("data_model_interface").get_num_bone_tracks(),
        "poses": {},
    }
    for bone in ("root", "pelvis", "head", "eye_L"):
        report[kind]["poses"][bone] = str(unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, bone, 0, False))
report["target_reference_root"] = str(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, "root"))
report["source_mesh_reference_root"] = str(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(source, "root"))
report["source_skeleton_reference_root"] = str(source.skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL))
report["target_skeleton_reference_root"] = str(mesh.skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL))
report["source_reference"] = ops.infer_import_rotation(source)
report["target_reference"] = ops.infer_import_rotation(mesh)
print("MORPH_RAW_IDLE_COMPARISON " + json.dumps(report), flush=True)
(ROOT / "docs" / "validation" / "raw_idle_comparison.json").write_text(json.dumps(report, indent=2) + "\n")

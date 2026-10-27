from pathlib import Path
import json
import math
import sys
import unreal

ROOT = Path(__file__).resolve().parents[3]
mesh = unreal.load_asset("/Game/Operative/SK_Operative")
sequence = unreal.load_asset("/Game/Operative/Animations/idle_relaxed")
if not mesh or not sequence:
    raise RuntimeError("Production mesh or idle clip is missing")

def snapshot():
    record = {}
    for name in ("root", "pelvis", "head", "eye_L", "thigh_L", "hand_L"):
        rest = unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, name)
        local = mesh.skeleton.get_reference_pose().get_ref_bone_pose(name, unreal.AnimPoseSpaces.LOCAL)
        world = mesh.skeleton.get_reference_pose().get_ref_bone_pose(name, unreal.AnimPoseSpaces.WORLD)
        record[name] = {
            "mesh_rest": str(rest),
            "skeleton_local": str(local),
            "skeleton_world": str(world),
            "mesh_skeleton_angle": math.degrees(rest.rotation.angular_distance(world.rotation)),
            "mesh_skeleton_position_error": math.dist((rest.translation.x, rest.translation.y, rest.translation.z), (world.translation.x, world.translation.y, world.translation.z)),
        }
    return record

report = {
    "mesh_skeleton": mesh.skeleton.get_path_name(),
    "clip_skeleton": sequence.get_editor_property("skeleton").get_path_name(),
    "clip_tracks": sequence.get_editor_property("data_model_interface").get_num_bone_tracks(),
    "clip_root": str(unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, "root", 0, False)),
    "before": snapshot(),
}
print("MORPH_PRODUCTION_BASIS " + json.dumps(report), flush=True)
if "--align" in sys.argv:
    report["aligned"] = unreal.MorphAuditLibrary.align_root_reference_to_animation(mesh, sequence)
    report["after"] = snapshot()
    print("MORPH_ALIGNED_BASIS " + json.dumps(report), flush=True)
(ROOT / "docs" / "validation" / "production_basis_inspection.json").write_text(json.dumps(report, indent=2) + "\n")

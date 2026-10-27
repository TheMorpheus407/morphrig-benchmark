from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
LIB = unreal.AnimationLibrary
result = {"mesh": None, "clips": []}


def transform(value):
    rotation = value.rotation.rotator()
    return {
        "translation_cm": [value.translation.x, value.translation.y, value.translation.z],
        "rotation_quaternion": [value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w],
        "rotation_pitch_yaw_roll": [rotation.pitch, rotation.yaw, rotation.roll],
        "scale": [value.scale3d.x, value.scale3d.y, value.scale3d.z],
    }


mesh = unreal.load_asset("/Game/Operative/SK_Operative")
reference = mesh.skeleton.get_reference_pose()
result["mesh"] = {
    "skeleton_asset": mesh.skeleton.get_path_name(),
    "root_local": transform(reference.get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL)),
    "root_component": transform(reference.get_ref_bone_pose("root", unreal.AnimPoseSpaces.WORLD)),
    "pelvis_local": transform(reference.get_ref_bone_pose("pelvis", unreal.AnimPoseSpaces.LOCAL)),
    "pelvis_component": transform(reference.get_ref_bone_pose("pelvis", unreal.AnimPoseSpaces.WORLD)),
}
result["mesh"]["shared_skeleton_feet"] = {
    name: transform(reference.get_ref_bone_pose(name, unreal.AnimPoseSpaces.WORLD))
    for name in ("foot_L", "foot_R")
}
result["mesh"]["actual_mesh_rest"] = {
    name: transform(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, name))
    for name in ("root", "head", "eye_L", "eye_R", "hand_L", "hand_R", "foot_L", "foot_R")
}
head = result["mesh"]["actual_mesh_rest"]["head"]["translation_cm"]
left = result["mesh"]["actual_mesh_rest"]["eye_L"]["translation_cm"]
right = result["mesh"]["actual_mesh_rest"]["eye_R"]["translation_cm"]
result["mesh"]["eye_forward_xy"] = [(left[0] + right[0]) * .5 - head[0], (left[1] + right[1]) * .5 - head[1]]
for name in ("idle_relaxed", "idle_combat", "dialogue", "dash_f", "dash_b", "dash_l", "dash_r"):
    sequence = unreal.load_asset("/Game/Operative/Animations/" + name)
    clip = {"id": name, "root": [], "pelvis": [], "head": [], "neck": []}
    clip["head_reference_local"] = transform(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, "head").make_relative(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, "neck")))
    skeleton = sequence.get_editor_property("skeleton")
    clip["skeleton"] = skeleton.get_path_name()
    clip["root_reference_local"] = transform(skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL))
    clip["root_reference_component"] = transform(skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.WORLD))
    for frame in (0, 18):
        clip["root"].append(transform(LIB.get_bone_pose_for_frame(sequence, "root", frame, False)))
        clip["pelvis"].append(transform(LIB.get_bone_pose_for_frame(sequence, "pelvis", frame, False)))
        clip["head"].append(transform(LIB.get_bone_pose_for_frame(sequence, "head", frame, False)))
        clip["neck"].append(transform(LIB.get_bone_pose_for_frame(sequence, "neck", frame, False)))
    delta = unreal.MorphAuditLibrary.get_root_motion_delta(sequence, 0.0, sequence.get_play_length())
    clip["mesh_root_motion_delta"] = [delta.x, delta.y, delta.z]
    result["clips"].append(clip)
def rotation(pitch):
    rotator = unreal.Rotator(pitch=pitch)
    quat = rotator.quaternion()
    direction = unreal.MathLibrary.get_forward_vector(rotator)
    return {"forward": [direction.x, direction.y, direction.z], "quaternion": [quat.x, quat.y, quat.z, quat.w], "euler": [rotator.pitch, rotator.yaw, rotator.roll]}


result["prop_motion"] = {}
for name, frames in (("reload", (0, 15, 26, 34, 46, 53, 60)), ("deploy", (0, 8, 16, 30, 35, 44, 48))):
    sequence = unreal.load_asset("/Game/Operative/Animations/" + name)
    result["prop_motion"][name] = []
    for frame in frames:
        row = {"frame": frame, "bones": {}}
        for bone in ("root", "pelvis", "hand_L", "hand_R", "cell", "beacon"):
            row["bones"][bone] = {
                "local": transform(LIB.get_bone_pose_for_frame(sequence, bone, frame, False)),
                "with_root_motion": transform(LIB.get_bone_pose_for_frame(sequence, bone, frame, True)),
            }
        result["prop_motion"][name].append(row)
result["ramp_axes"] = {"minus_20": rotation(-20), "plus_20": rotation(20)}
(ROOT / "docs" / "validation" / "native_transform_audit.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2), flush=True)

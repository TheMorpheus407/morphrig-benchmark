import bpy, json, sys, math
sys.path.insert(0, "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/tools")
import rig_ops
from mathutils import Vector, Matrix

BLEND = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative_rig.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
out = {}
A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]

out["def_bone_names"] = sorted(pb.name for pb in A.pose.bones)
out["ctrl_parents"] = {pb.name: (pb.bone.parent.name if pb.bone.parent else None)
                       for pb in C.pose.bones}
out["def_parents"] = {pb.name: (pb.bone.parent.name if pb.bone.parent else None)
                      for pb in A.pose.bones}
# control rest matrices vs deformation rest matrices (FK chains should mirror)
mirror = {}
for side in ("L", "R"):
    for chain, ctrls in (
        (("clavicle", "upper_arm", "forearm", "hand"), ("fk_clavicle", "fk_upper_arm", "fk_forearm", "fk_hand")),
        (("thigh", "shin", "foot", "toe"), ("fk_thigh", "fk_shin", "fk_foot", "fk_toe")),
    ):
        for d, c in zip(chain, ctrls):
            dn = f"{d}_{side}"; cn = f"{c}_{side}"
            dM = A.pose.bones[dn].bone.matrix_local
            cM = C.pose.bones[cn].bone.matrix_local
            mirror[f"{dn}->{cn}"] = {
                "pos_equal": (dM.to_translation() - cM.to_translation()).length < 1e-6,
                "rot_equal": (dM.to_3x3() - cM.to_3x3()).determinant() > 0 and
                             max(abs((dM.to_3x3() @ cM.to_3x3().inverted()).to_euler()[i]) for i in range(3)) < 1e-4,
            }
for n in ("ctrl_root", "ctrl_pelvis", "ctrl_chest", "ctrl_neck", "ctrl_head"):
    dmap = {"ctrl_root": "root", "ctrl_pelvis": "pelvis", "ctrl_chest": "spine_02",
            "ctrl_neck": "neck_01", "ctrl_head": "head"}[n]
    dM = A.pose.bones[dmap].bone.matrix_local
    cM = C.pose.bones[n].bone.matrix_local
    mirror[f"{dmap}->{n}"] = {
        "pos_equal": (dM.to_translation() - cM.to_translation()).length < 1e-6,
        "rot_equal": max(abs((dM.to_3x3() @ cM.to_3x3().inverted()).to_euler()[i]) for i in range(3)) < 1e-4,
    }
out["ctrl_mirror_rest"] = mirror

# root rest orientation
out["root_rest"] = [list(r) for r in A.pose.bones["root"].bone.matrix_local]
out["ctrl_root_rest"] = [list(r) for r in C.pose.bones["ctrl_root"].bone.matrix_local]

# sockets after a real depsgraph update
bpy.context.view_layer.update()
out["sockets"] = {}
for e in bpy.data.objects:
    if e.type == 'EMPTY' and e.parent is not None and e.parent.name == "Armature":
        out["sockets"][e.name] = {
            "parent_bone": e.parent_bone,
            "world": list(e.matrix_world.to_translation()),
            "local": list(e.matrix_basis.to_translation()),
        }

# ---- IK detach test: translate pelvis, IK legs, measure thigh head vs pelvis
rig_ops.reset_pose()
C["ik_fk_leg_L"] = 1.0
C["ik_fk_leg_R"] = 1.0
C["ik_fk_arm_L"] = 1.0
C["ik_fk_arm_R"] = 1.0
cp = C.pose.bones["ctrl_pelvis"]
cp.location = (0.0, 0.0, -0.05)
rig_ops.apply_controls()
bpy.context.view_layer.update()
pelvis_head = A.pose.bones["pelvis"].matrix.to_translation().copy()
thighL_head = A.pose.bones["thigh_L"].matrix.to_translation().copy()
thighR_head = A.pose.bones["thigh_R"].matrix.to_translation().copy()
shL_head = A.pose.bones["spine_03"].matrix.to_translation().copy()
uaL_head = A.pose.bones["upper_arm_L"].matrix.to_translation().copy()
out["ik_detach_test"] = {
    "pelvis_head": list(pelvis_head),
    "thigh_L_head": list(thighL_head),
    "thigh_R_head": list(thighR_head),
    "rest_thigh_L_head": [-0.10499999672174454, -0.010000001639127731, 0.925000011920929],
    "spine_03_head": list(shL_head),
    "upper_arm_L_head": list(uaL_head),
    "rest_upper_arm_L_head": [-0.20500002801418304, -0.017999999225139618, 1.3849999904632568],
}
# also: where do ik targets sit at rest
out["ik_targets_rest"] = {n: list(C.pose.bones[n].matrix.to_translation())
                          for n in ("ik_hand_L", "ik_hand_R", "ik_foot_L", "ik_foot_R",
                                    "pole_elbow_L", "pole_elbow_R", "pole_knee_L", "pole_knee_R",
                                    "ctrl_look")}
# hand rest vs ik_hand rest (should coincide)
out["hand_rest"] = list(A.pose.bones["hand_L"].bone.matrix_local.to_translation())
out["foot_rest"] = list(A.pose.bones["foot_L"].bone.matrix_local.to_translation())

# ctrl_root basis -> root matrix test
rig_ops.reset_pose()
cr = C.pose.bones["ctrl_root"]
cr.location = (0.10, 0.20, 0.30)
cr.rotation_euler = (0.0, 0.0, math.radians(15))
rig_ops.apply_controls()
bpy.context.view_layer.update()
out["ctrl_root_test"] = {
    "root_matrix_trans": list(A.pose.bones["root"].matrix.to_translation()),
    "root_matrix_euler_z": A.pose.bones["root"].matrix.to_euler().z,
}
# global_scale test
rig_ops.reset_pose()
C["global_scale"] = 0.5
rig_ops.apply_controls()
bpy.context.view_layer.update()
out["global_scale_test"] = {
    "pelvis_head": list(A.pose.bones["pelvis"].matrix.to_translation()),
    "head_head": list(A.pose.bones["head"].matrix.to_translation()),
}
rig_ops.reset_pose()

with open("/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/work/rig_measure2.json", "w") as f:
    json.dump(out, f, indent=1)
print("PROBE2_DONE")
print("ctrl_parents:", json.dumps(out["ctrl_parents"], indent=0))
print("mirror:", json.dumps(out["ctrl_mirror_rest"], indent=0))
print("ik_detach:", json.dumps(out["ik_detach_test"], indent=1))
print("ik_targets_rest:", json.dumps(out["ik_targets_rest"], indent=1))
print("ctrl_root_test:", json.dumps(out["ctrl_root_test"], indent=1))
print("global_scale_test:", json.dumps(out["global_scale_test"], indent=1))
print("sockets:", json.dumps(out["sockets"], indent=0))

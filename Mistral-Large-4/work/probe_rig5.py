import bpy, json, sys, math
sys.path.insert(0, "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/tools")
import rig_ops
from mathutils import Vector, Matrix

BLEND = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative_rig.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]
fails = []

def check(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)

def ang_between(R, B):
    q = R.to_3x3().to_quaternion().rotation_difference(B.to_3x3().to_quaternion())
    return math.degrees(abs(q.angle))

# ---- 1. rest pose clean
rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()
dev = []
for pb in A.pose.bones:
    dpos = (pb.matrix.to_translation() - pb.bone.matrix_local.to_translation()).length
    if dpos > 1e-5 or ang_between(pb.matrix, pb.bone.matrix_local) > 1e-3:
        dev.append(pb.name)
check(not dev, "rest pose clean after reset+apply (deviations: %s)" % dev)

# ---- 2. IK legs follow posed pelvis
rig_ops.reset_pose()
C["ik_fk_leg_L"] = 1.0
C["ik_fk_leg_R"] = 1.0
C["ik_fk_arm_L"] = 1.0
C["ik_fk_arm_R"] = 1.0
cp = C.pose.bones["ctrl_pelvis"]
cp.location = (0.0, 0.0, -0.05)
rig_ops.apply_controls()
bpy.context.view_layer.update()
pelvis_head = A.pose.bones["pelvis"].matrix.to_translation()
thighL = A.pose.bones["thigh_L"].matrix.to_translation()
thighR = A.pose.bones["thigh_R"].matrix.to_translation()
hipL_rest = A.pose.bones["thigh_L"].bone.matrix_local.to_translation()
# thigh head should be at pelvis_pose @ rest_local(thigh) -> moved with pelvis
d = (thighL - (pelvis_head + (hipL_rest - A.pose.bones["pelvis"].bone.matrix_local.to_translation()))).length
check(d < 1e-4, "IK thigh_L head follows posed pelvis (err %.5f)" % d)
d = (thighR - (pelvis_head + (A.pose.bones["thigh_R"].bone.matrix_local.to_translation()
                              - A.pose.bones["pelvis"].bone.matrix_local.to_translation()))).length
check(d < 1e-4, "IK thigh_R head follows posed pelvis (err %.5f)" % d)
# knee/ankle: straight leg down from hip
ank = A.pose.bones["foot_L"].matrix.to_translation()
hip = thighL
straight = abs((ank - hip).length - 0.85043) < 2e-3
check(straight, "IK leg straight at rest target (hip-ankle %.4f ~ 0.850)" % (ank - hip).length)

# ---- 3. head follows posed chest
rig_ops.reset_pose()
cc = C.pose.bones["ctrl_chest"]
cc.location = (0.0, 0.0, 0.03)
cc.rotation_euler = (math.radians(8), 0.0, 0.0)
rig_ops.apply_controls()
bpy.context.view_layer.update()
sp3 = A.pose.bones["spine_03"].matrix.to_translation()
head = A.pose.bones["head"].matrix.to_translation()
neck1 = A.pose.bones["neck_01"].matrix.to_translation()
jaw = A.pose.bones["jaw"].matrix.to_translation()
eye = A.pose.bones["eye_L"].matrix.to_translation()
lid = A.pose.bones["lid_upper_L"].matrix.to_translation()
# neck_01 must keep its rest-relative transform to the posed spine_03:
# neck_01_pose = spine_03_pose @ spine_03_rest^-1 @ neck_01_rest
sp3_pb = A.pose.bones["spine_03"]
T = sp3_pb.matrix @ sp3_pb.bone.matrix_local.inverted()
expected_n1 = (T @ A.pose.bones["neck_01"].bone.matrix_local).to_translation()
d = (neck1 - expected_n1).length
check(d < 1e-4, "neck_01 follows posed spine_03 (err %.5f)" % d)
# head relative offset from neck_01 preserved (rest offsets rotated by neck chain, just check it moved)
head_rest = A.pose.bones["head"].bone.matrix_local.to_translation()
check((head - head_rest).length > 0.02, "head moved with posed chest (%.4f)" % (head - head_rest).length)
# jaw/eye/lid moved with head (they should be near their posed head-relative rest spots)
check((jaw - head).length < 0.15, "jaw stays attached to head")
check((eye - head).length < 0.15, "eye stays attached to head")
check((lid - head).length < 0.15, "lid stays attached to head")

# ---- 4. IK arms follow posed chest
rig_ops.reset_pose()
C["ik_fk_arm_L"] = 1.0
C["ik_fk_arm_R"] = 1.0
cc = C.pose.bones["ctrl_chest"]
cc.location = (0.0, 0.0, 0.03)
rig_ops.apply_controls()
bpy.context.view_layer.update()
clav = A.pose.bones["clavicle_R"].matrix.to_translation()
ua = A.pose.bones["upper_arm_R"].matrix.to_translation()
ua_rest = A.pose.bones["upper_arm_R"].bone.matrix_local.to_translation()
clav_rest = A.pose.bones["clavicle_R"].bone.matrix_local.to_translation()
d = (ua - (clav + (ua_rest - clav_rest))).length
check(d < 1e-4, "IK upper_arm_R follows posed clavicle (err %.5f)" % d)

# ---- 5. FK chains reproduce authored control matrices exactly
rig_ops.reset_pose()
bpy.context.view_layer.update()
# pose the FK legs: bend the left knee via fk controls
import math as m
fk_sh = C.pose.bones["fk_shin_L"]
fk_sh.rotation_euler = (m.radians(-30), 0.0, 0.0)
fk_ft = C.pose.bones["fk_foot_L"]
fk_ft.rotation_euler = (m.radians(10), 0.0, 0.0)
rig_ops.apply_controls()
bpy.context.view_layer.update()
ok = True
for dn, cn in (("shin_L", "fk_shin_L"), ("foot_L", "fk_foot_L")):
    R = A.pose.bones[dn].matrix
    B = C.pose.bones[cn].matrix
    if (R.to_translation() - B.to_translation()).length > 1e-6 or \
            ang_between(R, B) > 1e-4:
        ok = False
        print("    %s: def %s vs ctrl %s" % (dn, list(R.to_translation()), list(B.to_translation())))
check(ok, "FK deformation bones reproduce control matrices exactly")

# ---- 6. root motion moves everything (via control chain)
rig_ops.reset_pose()
cr = C.pose.bones["ctrl_root"]
cr.location = (0.0, 0.0, 0.10)   # root local +Z = world -Y (forward)
rig_ops.apply_controls()
bpy.context.view_layer.update()
root_t = A.pose.bones["root"].matrix.to_translation()
pelvis_t = A.pose.bones["pelvis"].matrix.to_translation()
head_t = A.pose.bones["head"].matrix.to_translation()
foot_t = A.pose.bones["foot_L"].matrix.to_translation()
check(abs(root_t.y - (-0.10)) < 1e-4, "root translates forward -Y by 0.10 (got %s)" % list(root_t))
check(abs(pelvis_t.y - (-0.10)) < 1e-4, "pelvis follows root motion")
check(abs(head_t.y - (0.015 - 0.10)) < 1e-4, "head follows root motion (%.4f)" % head_t.y)
check(abs(foot_t.y - (-0.035 - 0.10)) < 1e-4, "foot follows root motion")

# ---- 7. global_scale scales the whole body (root motion of scale through
# the inheritance chain; legs/arms included)
rig_ops.reset_pose()
C["global_scale"] = 0.5
rig_ops.apply_controls()
bpy.context.view_layer.update()
head_z = A.pose.bones["head"].matrix.to_translation().z
thigh_z = A.pose.bones["thigh_L"].matrix.to_translation().z
uarm = A.pose.bones["upper_arm_R"].matrix.to_translation()
check(abs(head_z - 0.78) < 1e-3,
      "global_scale 0.5 halves height (head z %.4f)" % head_z)
check(abs(thigh_z - 0.5 * 0.925) < 1e-3,
      "global_scale 0.5 scales legs (thigh_L z %.4f)" % thigh_z)
check((uarm - Vector((0.5 * 0.205, 0.5 * 0.018, 0.5 * 1.385))).length < 1e-3,
      "global_scale 0.5 scales arms (upper_arm_R %s)" % list(uarm))
# IK limbs must scale too
C["ik_fk_leg_L"] = 1.0
C["ik_fk_arm_R"] = 1.0
rig_ops.apply_controls()
bpy.context.view_layer.update()
thigh_ik_z = A.pose.bones["thigh_L"].matrix.to_translation().z
uarm_ik = A.pose.bones["upper_arm_R"].matrix.to_translation()
check(abs(thigh_ik_z - 0.5 * 0.925) < 1e-3,
      "global_scale 0.5 scales IK legs (thigh_L z %.4f)" % thigh_ik_z)
check((uarm_ik - Vector((0.5 * 0.205, 0.5 * 0.018, 0.5 * 1.385))).length < 1e-3,
      "global_scale 0.5 scales IK arms (upper_arm_R %s)" % list(uarm_ik))

# ---- 8. tongue fix
rig_ops.reset_pose()
C["tongue"] = 1.0
rig_ops.apply_controls()
check(abs(M.data.shape_keys.key_blocks["tongue_out"].value - 1.0) < 1e-6,
      "tongue prop drives tongue_out shape key")
rig_ops.reset_pose()

print()
if fails:
    print("FAILED %d" % len(fails))
    sys.exit(1)
print("ALL RIG CHECKS PASSED")

"""smoke_rig.py — control-rig smoke test for source/Operative_rig.blend.

Opens the delivered rig file headless and exercises tools/rig_ops.py
(reset / apply / match-FK) as plain functions, checking armature-space POSE
matrices against analytically expected values.

Checks:
 0. embedded rig_ops text == tools/rig_ops.py on disk (no stale embed)
 1. reset + apply   -> every deformation pose matrix == rest (matrix_local),
                       all shape keys 0
 2. FK arm          -> upper_arm_L pose == rest @ RotX(0.5)
 3. IK arm          -> hand reaches the ik target, limb lengths preserved
                       (|E-A|=L1, |T-E|=L2), upper arm rotated off rest,
                       elbow on the pole side of the shoulder
 4. blink           -> lid bones RotX(+/-56 deg) about rest, other side rest
 5. jaw             -> jaw pose == T(head) @ RotX(32.5 deg) @ rest_R
 6. shape keys      -> smile_L=0.8, pucker=-0.4 land on the key blocks
 7. eye look        -> eye_L == T(head) @ Rz(30 deg) @ Rx(-10 deg)
 8. match FK->IK    -> fk controls AND ik targets snap onto the skeleton pose
 9. finger curl     -> phalanx rotation_euler.x factors 1.0 / 1.2
10. mesh deforms    -> evaluated mesh follows the IK hand

Prints PASS/FAIL per check, then SMOKE_DONE (all pass) or SMOKE_FAILED.
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector, Matrix

TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

BLEND = os.path.join(TASK, "source", "Operative_rig.blend")
SPEC = json.load(open(os.path.join(TASK, "work", "rig_spec.json")))
BONES = {b["name"]: b for b in SPEC["bones"]}

bpy.ops.wm.open_mainfile(filepath=BLEND)
import rig_ops  # noqa: E402  (its register() guard avoids double registration)

A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]
pbs = A.pose.bones

results = []


def check(num, name, ok, detail=""):
    results.append(ok)
    print("CHECK %2d %-26s %s %s" % (num, name, "PASS" if ok else "FAIL", detail),
          flush=True)


def mdiff(M1, M2):
    return max(abs(M1[i][j] - M2[i][j]) for i in range(4) for j in range(4))


# ---- check 0: the embedded rig_ops text matches tools/rig_ops.py on disk
txt = bpy.data.texts.get("rig_ops.py")
disk = open(os.path.join(TASK, "tools", "rig_ops.py")).read()
ok = txt is not None and txt.as_string() == disk
check(0, "embedded rig_ops fresh", ok,
      "" if ok else "embedded text missing or stale")

# ---- check 1: reset + apply -> exact rest pose
rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()
worst = 0.0
worst_name = ""
for pb in pbs:
    d = mdiff(pb.matrix, pb.bone.matrix_local)
    if d > worst:
        worst, worst_name = d, pb.name
sk_max = max(abs(kb.value) for kb in M.data.shape_keys.key_blocks)
ok = worst < 1e-6 and sk_max == 0.0
check(1, "reset+apply == rest", ok,
      "worst=%.2e (%s) shapekeys=%.1e" % (worst, worst_name, sk_max))

# ---- check 2: FK arm rotation lands exactly on the deformation bone
rig_ops.reset_pose()
cb = C.pose.bones["fk_upper_arm_L"]
cb.rotation_mode = 'XYZ'
cb.rotation_euler = (0.5, 0.0, 0.0)
rig_ops.apply_controls()
bpy.context.view_layer.update()
ua = pbs["upper_arm_L"]
expect = ua.bone.matrix_local @ Matrix.Rotation(0.5, 4, 'X')
d = mdiff(ua.matrix, expect)
check(2, "FK arm RotX(0.5)", d < 1e-5, "diff=%.2e" % d)

# ---- check 3: IK arm — reach, limb lengths, elbow on the pole side
def pose_ik_arm():
    rig_ops.reset_pose()
    C["ik_fk_arm_L"] = 1.0
    ikc = C.pose.bones["ik_hand_L"]
    ikc.rotation_mode = 'XYZ'
    # ik_hand_L rest frame: X=+X, Y=-Y, Z=-Z world, so basis (0, 0.10, -0.075)
    # moves the target by (0, -0.10, +0.075) in world space
    ikc.location = (0.0, 0.10, -0.075)
    rig_ops.apply_controls()
    bpy.context.view_layer.update()


pose_ik_arm()
W0 = Vector(BONES["hand_L"]["head"])
target = W0 + Vector((0.0, -0.10, 0.075))
hw = pbs["hand_L"].matrix.to_translation()
d_hand = (hw - target).length
A0 = Vector(BONES["upper_arm_L"]["head"])
E0 = Vector(BONES["forearm_L"]["head"])
L1 = (E0 - A0).length
L2 = (W0 - E0).length
Ep = pbs["forearm_L"].matrix.to_translation()   # elbow (forearm head)
Ap = pbs["upper_arm_L"].matrix.to_translation()  # shoulder
len1 = (Ep - Ap).length
len2 = (hw - Ep).length
rest_d = mdiff(pbs["upper_arm_L"].matrix, pbs["upper_arm_L"].bone.matrix_local)
ok = (d_hand < 1e-4 and abs(len1 - L1) < 1e-6 and abs(len2 - L2) < 1e-6
      and rest_d > 0.05 and (Ep.y - A0.y) > 0.02)
check(3, "IK arm reach+lengths", ok,
      "hand_err=%.2e len1=%.6f/%.6f len2=%.6f/%.6f restdiff=%.3f elbow_dy=%+.4f"
      % (d_hand, len1, L1, len2, L2, rest_d, Ep.y - A0.y))

# ---- check 4: blink — lid bones rotate +/-56 deg about rest
rig_ops.reset_pose()
C["look_auto"] = False
C["blink_L"] = 1.0
rig_ops.apply_controls()
bpy.context.view_layer.update()
lb = pbs["lid_upper_L"].bone
expect = (Matrix.Translation(lb.matrix_local.to_translation())
          @ Matrix.Rotation(math.radians(56.0), 4, 'X')
          @ lb.matrix_local.to_3x3().to_4x4())
d1 = mdiff(pbs["lid_upper_L"].matrix, expect)
lb2 = pbs["lid_lower_L"].bone
expect2 = (Matrix.Translation(lb2.matrix_local.to_translation())
           @ Matrix.Rotation(math.radians(-56.0), 4, 'X')
           @ lb2.matrix_local.to_3x3().to_4x4())
d2 = mdiff(pbs["lid_lower_L"].matrix, expect2)
dR = mdiff(pbs["lid_upper_R"].matrix, pbs["lid_upper_R"].bone.matrix_local)
check(4, "blink L lids +/-56deg", d1 < 1e-5 and d2 < 1e-5 and dR < 1e-6,
      "upper=%.2e lower=%.2e right_rest=%.2e" % (d1, d2, dR))

# ---- check 5: jaw open 0.5 -> 32.5 deg about the jaw rest frame
rig_ops.reset_pose()
C["jaw_open"] = 0.5
rig_ops.apply_controls()
bpy.context.view_layer.update()
jb = pbs["jaw"].bone
expect = (Matrix.Translation(jb.matrix_local.to_translation())
          @ Matrix.Rotation(math.radians(32.5), 4, 'X')
          @ jb.matrix_local.to_3x3().to_4x4())
d = mdiff(pbs["jaw"].matrix, expect)
check(5, "jaw open -> 32.5deg", d < 1e-5, "diff=%.2e" % d)

# ---- check 6: shape keys land on the key blocks
rig_ops.reset_pose()
C["smile_L"] = 0.8
C["pucker"] = -0.4
rig_ops.apply_controls()
kbs = M.data.shape_keys.key_blocks
v1 = kbs["smile_L"].value
v2 = kbs["pucker"].value
check(6, "shape keys land", abs(v1 - 0.8) < 1e-6 and abs(v2 + 0.4) < 1e-6,
      "smile_L=%.3f pucker=%.3f" % (v1, v2))

# ---- check 7: manual eye look 30 deg yaw / 10 deg pitch
rig_ops.reset_pose()
C["look_auto"] = False
C["look_yaw"] = 30.0
C["look_pitch"] = 10.0
rig_ops.apply_controls()
bpy.context.view_layer.update()
eb = pbs["eye_L"].bone
expect = (Matrix.Translation(eb.matrix_local.to_translation())
          @ Matrix.Rotation(math.radians(30.0), 4, 'Z')
          @ Matrix.Rotation(math.radians(-10.0), 4, 'X'))
d = mdiff(pbs["eye_L"].matrix, expect)
check(7, "eye look 30/10", d < 1e-5, "diff=%.2e" % d)

# ---- check 8: match FK to IK — controls and IK targets snap onto the pose
pose_ik_arm()
rig_ops.match_fk_to_ik()
bpy.context.view_layer.update()
d_fk = mdiff(C.pose.bones["fk_upper_arm_L"].matrix, pbs["upper_arm_L"].matrix)
d_ik = (C.pose.bones["ik_hand_L"].matrix.to_translation()
        - pbs["hand_L"].matrix.to_translation()).length
check(8, "match FK->IK", d_fk < 1e-4 and d_ik < 1e-5,
      "fk_diff=%.2e ik_target_err=%.2e" % (d_fk, d_ik))

# ---- check 9: finger curl factors (1.0 / 1.1 / 1.2) * 1.25 rad
rig_ops.reset_pose()
C["curl_L"] = 0.5
rig_ops.apply_controls()
bpy.context.view_layer.update()
rx1 = pbs["f_index_01_L"].rotation_euler.x
rx3 = pbs["f_index_03_L"].rotation_euler.x
ok = abs(rx1 - 0.5 * 1.25) < 1e-9 and abs(rx3 - 0.5 * 1.25 * 1.2) < 1e-9
check(9, "finger curl factors", ok, "ph01=%.4f ph03=%.4f" % (rx1, rx3))

# ---- check 10: the mesh actually deforms with the armature modifier
pose_ik_arm()
dg = bpy.context.evaluated_depsgraph_get()
mev = M.evaluated_get(dg).to_mesh()
me = M.data
wrist_rest = Vector(BONES["hand_L"]["head"])
# index the vertex on the REST mesh (topology is identical in the eval mesh)
best = min(range(len(me.vertices)),
           key=lambda i: (me.vertices[i].co - wrist_rest).length)
v_rest = me.vertices[best].co
moved = (mev.vertices[best].co - v_rest).length
target = wrist_rest + Vector((0.0, -0.10, 0.075))
err = (mev.vertices[best].co - target).length
M.evaluated_get(dg).to_mesh_clear()
check(10, "mesh follows IK", moved > 0.03 and err < 0.06,
      "moved=%.4f target_err=%.4f" % (moved, err))

# ---- summary
n_fail = results.count(False)
print("SMOKE %d/%d checks passed" % (len(results) - n_fail, len(results)), flush=True)
print("SMOKE_DONE" if n_fail == 0 else "SMOKE_FAILED", flush=True)

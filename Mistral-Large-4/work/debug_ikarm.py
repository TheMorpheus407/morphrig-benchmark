"""Debug: why does combat_arm_ik differ from the FK combat arm?"""
import sys, os, math

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, combat_pose,
                      stance_legs, R_axis, lerp_params)
from morphrig_lib import lerp, smoothstep, FWD, UP, RIGHT

rig = Rig()


def mat_err(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))


def fk_arm(swing=0.0, lift=6.0, yaw=0.0, elbow=16.0, wrist=-8.0,
           curl=0.18, spread=0.05, w=(1.0, 0.0, 0.0)):
    return {"mode": "fk_param", "w": tuple(w), "swing": swing, "lift": lift,
            "yaw": yaw, "elbow": elbow, "wrist": wrist, "curl": curl,
            "spread": spread, "hand": None, "forearm": None, "target": None,
            "pole": None, "hand_R": None}


def ik_arm(target, hand_R, pole, curl=0.18, spread=0.05):
    if isinstance(hand_R, Matrix):
        hand_R = hand_R.to_3x3().to_4x4()
    return {"mode": "ik", "target": tuple(target), "hand_R": hand_R,
            "pole": tuple(pole), "curl": curl, "spread": spread,
            "w": (1.0, 0.0, 0.0), "swing": 0.0, "lift": 0.0, "yaw": 0.0,
            "elbow": 0.0, "wrist": 0.0, "hand": None, "forearm": None}


def fk_arm_matrices(rig, side, shoulder, arm):
    s = 1.0 if side == "L" else -1.0
    w = Vector(arm["w"]).normalized()
    R_swing = (R_axis(w, arm["swing"])
               @ Matrix.Rotation(math.radians(arm["lift"] * s), 4, 'Y')
               @ Matrix.Rotation(math.radians(arm["yaw"]), 4, 'Z'))
    M_ua = Matrix.Translation(shoulder) @ R_swing \
        @ rig.rest["upper_arm_%s" % side].to_3x3().to_4x4()
    M_fa = (M_ua @ rig.rl["forearm_%s" % side]) \
        @ Matrix.Rotation(math.radians(arm["elbow"]), 4, 'X')
    M_h = (M_fa @ rig.rl["hand_%s" % side]) \
        @ Matrix.Rotation(math.radians(arm["wrist"]), 4, 'X')
    return M_ua, M_fa, M_h


Pc = combat_pose(rig, pelvis_z=0.905, spread=0.075)
apply_pose(rig, Pc)
rig.apply()
rig.post_pose(Pc)
fk_def = {n: rig.def_m[n].copy() for n in
          ("clavicle_L", "upper_arm_L", "forearm_L", "hand_L",
           "upper_arm_R", "forearm_R", "hand_R")}
_, _, _, _, sh = body_matrices(rig, Pc)

# analytic FK matrices
for side in ("L", "R"):
    M_ua, M_fa, M_h = fk_arm_matrices(rig, side, sh[side], Pc["arms"][side])
    print("%s FK analytic vs def: ua=%.2e fa=%.2e h=%.2e" % (
        side, mat_err(M_ua, fk_def["upper_arm_%s" % side]),
        mat_err(M_fa, fk_def["forearm_%s" % side]),
        mat_err(M_h, fk_def["hand_%s" % side])))
    # segment checks
    print("   |E-A|=%.6f L1=%.6f   |W-E|=%.6f L2=%.6f" % (
        (M_fa.to_translation() - sh[side]).length, rig.arm_L1[side],
        (M_h.to_translation() - M_fa.to_translation()).length, rig.arm_L2[side]))
    ua_axis = rig.rest["upper_arm_%s" % side].to_3x3() @ Vector((0, 1, 0))
    e_off = rig.rest["forearm_%s" % side].to_translation() - rig.rest["upper_arm_%s" % side].to_translation()
    print("   ua axis=%s  E-A dir=%s  angle=%.3f deg" % (
        tuple(round(c, 4) for c in ua_axis),
        tuple(round(c, 4) for c in e_off.normalized()),
        math.degrees(ua_axis.angle(e_off))))
    ha_off = rig.rl["hand_%s" % side].to_translation()
    print("   rl[hand].t=%s  |.|==L2: %s  angle to (0,1,0)=%.3f deg" % (
        tuple(round(c, 5) for c in ha_off), abs(ha_off.length - rig.arm_L2[side]) < 1e-6,
        math.degrees(Vector((0, 1, 0)).angle(ha_off))))

# now the IK version
Pc2 = combat_pose(rig, pelvis_z=0.905, spread=0.075)
for side in ("L", "R"):
    M_ua, M_fa, M_h = fk_arm_matrices(rig, side, sh[side], Pc2["arms"][side])
    Pc2["arms"][side] = ik_arm(M_h.to_translation(), M_h, M_fa.to_translation())
apply_pose(rig, Pc2)
rig.apply()
rig.post_pose(Pc2)
for n in fk_def:
    print("%s IK-vs-FK def err=%.2e" % (n, mat_err(rig.def_m[n], fk_def[n])))

# where does the IK solve land?
for side in ("L", "R"):
    M_ua, M_fa, M_h = fk_arm_matrices(rig, side, sh[side], Pc["arms"][side])
    A0 = sh[side]
    E0 = A0 + (rig.rest["forearm_%s" % side].to_translation()
               - rig.rest["upper_arm_%s" % side].to_translation())
    W0 = A0 + (rig.rest["hand_%s" % side].to_translation()
               - rig.rest["upper_arm_%s" % side].to_translation())
    E_new, T_new = rig_ops.solve_2bone_ik(A0, E0, W0, M_h.to_translation(),
                                           M_fa.to_translation())
    print("%s E_new-E_fk=%.2e  T_new-W_fk=%.2e  d=%.6f clamp_hi=%.6f" % (
        side, (E_new - M_fa.to_translation()).length,
        (T_new - M_h.to_translation()).length,
        (M_h.to_translation() - A0).length,
        rig.arm_L1[side] + rig.arm_L2[side] - 1e-4))
    # forearm rotation difference: twist about the forearm axis?
    fa_fk = M_fa.to_3x3()
    fa_ik = rig.def_m["forearm_%s" % side].to_3x3()
    D = fa_ik.inverted() @ fa_fk
    axis = Vector((D[2][1] - D[1][2], D[0][2] - D[2][0], D[1][0] - D[0][1]))
    ang = math.degrees(2.0 * math.atan2(axis.length, D[0][0] + D[1][1] + D[2][2]))
    fa_axis = fa_fk @ Vector((0, 1, 0))
    print("   forearm rot diff: twist=%.3f deg  axis=%s  axis.fa_y=%.4f" % (
        ang, tuple(round(c, 4) for c in axis.normalized()), axis.normalized().dot(fa_axis)))
    ua_fk = M_ua.to_3x3()
    ua_ik = rig.def_m["upper_arm_%s" % side].to_3x3()
    D = ua_ik.inverted() @ ua_fk
    axis = Vector((D[2][1] - D[1][2], D[0][2] - D[2][0], D[1][0] - D[0][1]))
    ang = math.degrees(2.0 * math.atan2(axis.length, D[0][0] + D[1][1] + D[2][2]))
    ua_axis_w = ua_fk @ Vector((0, 1, 0))
    print("   upperarm rot diff: twist=%.3f deg  axis=%s  axis.ua_y=%.4f" % (
        ang, tuple(round(c, 4) for c in axis.normalized()), axis.normalized().dot(ua_axis_w)))

"""Probe the gen_03 helper designs before baking the 96 clips.

Run:  blender -b --factory-startup --python work/probe_gen3.py

  A  combat_hand_arm / combat_arm_ik reproduce combat_hand_matrices exactly
     (def matrices, both sides, default + swung params)
  B  build_aim over the 9-point grid: fire direction, elbow at L1, grip
     reach, IK error, palm contact on the R forearm, hover mode
  C  lying_pp (face-down/up x kinds x leg_s/arm_s extremes): floor contact
     (mesh min z), head height, IK error, arm reach; getup push phase
     (lerped floor palms, reach-clamped, t=0 == prone exactly)
  D  reload choreography reach: holster grip, cell seat grip, R catch,
     R pouch carry at the raised pouch slot
  E  deploy reach: rigid backpack grip (both heights) + pedestal spot at
     full crouch
  F  step_turn 90/180 deg: feet planted between steps, catch-up step lands
     both feet at the final yaw, pelvis xy
  G  dash: stance feet planted along the travel track (lateral gait shift
     reported separately), 2.0 m horizontal displacement, no root stretch
  H  console_pose s=1 reach + IK error
  I  ref_forearm 3-tuple mechanism (L hand rides the R forearm frame)
  J  dialogue gesture reach at extremes + lerp_params smoothness
  K  Action.use_cyclic exists in 5.1 but does NOT wrap evaluation
     (loop flag = manifest-only policy)
"""
import sys, os, math, time

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))
bpy.context.scene.render.fps = 30

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, hip_pos, gait_frame,
                      combat_pose, relaxed_pose, stance_legs, aim_arm_params,
                      aim_forearm_matrix, support_hand_params, blink_bump,
                      breathing, dir_of, mat_cols, lerp_params, R_axis,
                      DEFORM_BONES, SHAPE_KEYS, GAIT, DIR_ALPHA, ANKLE_Z,
                      THIGH_DROP, TWO_PI)
from morphrig_lib import lerp, lerp_v, smoothstep, cosine_ease, clamp, FPS, FWD, UP, RIGHT

# dash gait class: 2 m of root motion per 15-frame clip (SPEC section 8)
GAIT["dash"] = dict(n=15, stance=0.36, E=0.7714285714, lift=0.11,
                    v_app=4.2857142857, d_mid=0.90, arm_amp=30.0, elbow=34.0,
                    lean=12.0, heel=26.0, shift=0.020, yaw_sway=0.8, arc=0.02)

rig = Rig()

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# prop bones ride the PELVIS (they are root children, but every clip poses the
# pelvis; at rest  rest[prop] == rest[pelvis] @ PROP_OFF[prop]  holds exactly)
PROP_OFF = {p: rig.rest["pelvis"].inverted() @ rig.rest[p]
            for p in ("cell_new", "cell_spent", "beacon")}
# seated cell frame at the wrist emitter mount (cell long axis -> emitter +Z,
# i.e. sticking out the BACK of the wrist gadget at rest)
CELL_SEAT_WORLD = Matrix.Translation((0.245, 0.055, 0.85)) @ Matrix.Rotation(math.pi, 4, 'Z')
CELL_SEAT_LOCAL = rig.rest["emitter"].inverted() @ CELL_SEAT_WORLD
DEPLOY_SPOT = Vector((0.21, -0.11, 0.40))
DASH_DIRS = {"f": Vector((0.0, -1.0, 0.0)), "b": Vector((0.0, 1.0, 0.0)),
             "l": Vector((-1.0, 0.0, 0.0)), "r": Vector((1.0, 0.0, 0.0))}
DASH_ALPHA = {"f": 0.0, "b": 180.0, "l": -90.0, "r": 90.0}

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))
    sys.stdout.flush()


def mat_err(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))


def pose(Pp):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)


def mesh_min_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    z = min(v.co.z for v in mm.vertices)
    me.to_mesh_clear()
    return z


def mesh_max_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    z = max(v.co.z for v in mm.vertices)
    me.to_mesh_clear()
    return z


# ------------------------------------------------------------------ helpers
def rot_with_y(d, ref=None):
    """Proper rotation whose local +Y is d; local +Z is ref projected perp to d."""
    y = Vector(d).normalized()
    z = Vector(ref) if ref is not None else UP.copy()
    z = z - y * z.dot(y)
    if z.length < 1e-6:
        z = RIGHT - y * y.x
        if z.length < 1e-6:
            z = FWD - y * y.y
    z.normalize()
    x = y.cross(z)
    return mat_cols(x, y, z)


def hand_M(palm_pos, y_dir, z_dir):
    """Hand bone world matrix: palm CENTER at palm_pos, fingers along y_dir,
    palm normal along z_dir (palm on the +Z side)."""
    y = Vector(y_dir).normalized()
    z = Vector(z_dir) - y * Vector(z_dir).dot(y)
    if z.length < 1e-6:
        z = UP - y * y.z
        if z.length < 1e-6:
            z = RIGHT - y * y.x
    z.normalize()
    x = y.cross(z)
    R = mat_cols(x, y, z)
    head = Vector(palm_pos) - 0.06 * y - 0.025 * z
    return Matrix.Translation(head) @ R


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


def fk_hand_arm(M_hand, pole, curl=0.18, spread=0.05):
    return {"mode": "fk", "hand": M_hand, "pole": tuple(pole), "curl": curl,
            "spread": spread, "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 0.0, "yaw": 0.0, "elbow": 0.0, "wrist": 0.0,
            "forearm": None, "target": None, "hand_R": None}


def fk_forearm_arm(M_fa, M_hand, curl=0.18, spread=0.05):
    """Forearm pinned at M_fa, independent hand matrix (reload R arm)."""
    return {"mode": "fk", "forearm": M_fa, "hand": M_hand, "curl": curl,
            "spread": spread, "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 0.0, "yaw": 0.0, "elbow": 0.0, "wrist": 0.0,
            "target": None, "pole": None, "hand_R": None}


def ik_leg(ankle, yaw=0.0, pitch=0.0, toe=0.0, pole=None):
    return {"mode": "ik", "ankle": tuple(ankle), "yaw": yaw, "pitch": pitch,
            "toe": toe, "pole": tuple(pole)}


def planted(rig, M_pel, ankles, yaws=(0.0, 0.0), pitch=0.0, toe=0.0,
            pole_off=(0.30, -0.25)):
    """IK legs with explicit world ankles (ankles fixed -> feet stay planted)."""
    legs = {}
    for i, side in enumerate(("L", "R")):
        hip = hip_pos(rig, side, M_pel)
        u = dir_of(yaws[i], 0.0)
        pole = hip + u * pole_off[0] + Vector((0.0, 0.0, pole_off[1]))
        legs[side] = ik_leg(ankles[i], yaw=yaws[i], pitch=pitch, toe=toe, pole=pole)
    return legs


def air_legs(rig, M_pel, lift_L=0.0, lift_R=0.0, fwd_L=0.0, fwd_R=0.0,
             pitch=0.0, toe=0.0):
    """Tucked airborne legs; fwd>0 moves the foot back (+Y) off the ground.
    The pole sits IN FRONT of the hip so the knee folds forward (anatomical
    bend; a pole behind would fold the knee backward through the thigh)."""
    u = dir_of(0.0, 0.0)
    legs = {}
    for side, lift, fwd in (("L", lift_L, fwd_L), ("R", lift_R, fwd_R)):
        hip = hip_pos(rig, side, M_pel)
        ankle = Vector((hip.x - fwd * u.x, hip.y - fwd * u.y, ANKLE_Z + lift))
        pole = hip + u * 0.30 + Vector((0.0, 0.0, 0.10))
        legs[side] = ik_leg(ankle, pitch=pitch, toe=toe, pole=pole)
    return legs


def stance_at(rig, aL, aR, pelvis_z=0.905, lean=0.0, shift=0.0, yaw=0.0,
              chest_yaw=0.0, chest_lean=0.0, d_mid=0.93, foot_yaw=0.0,
              roll=0.0, w=(1.0, 0.0, 0.0), look=(0.0, 0.0), face=None):
    """Standing pose with explicit ankles; pelvis z rides the reachability
    ceiling so the IK legs never clamp."""
    Pp = P(pelvis__z=pelvis_z, pelvis__shift=shift, pelvis__lean=lean,
           pelvis__yaw=yaw, pelvis__roll=roll, chest__lean=chest_lean,
           chest__yaw=chest_yaw, look=tuple(look), w=tuple(w))
    if face:
        Pp["face"] = dict(face)
    L = rig.leg_len
    for _ in range(3):
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        R_pel = M_pel.to_3x3()
        pz = Pp["pelvis"]["z"]
        for side, a in (("L", aL), ("R", aR)):
            hip = hip_pos(rig, side, M_pel)
            dxy = math.hypot(hip.x - a.x, hip.y - a.y)
            hzoff = (R_pel @ rig.rl["thigh_%s" % side].to_translation()).z
            pz = min(pz, a.z + d_mid * math.sqrt(max(0.04, L * L - dxy * dxy)) - hzoff)
        if abs(pz - Pp["pelvis"]["z"]) < 1e-9:
            break
        Pp["pelvis"]["z"] = pz
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = planted(rig, M_pel, (Vector(aL), Vector(aR)),
                         yaws=(foot_yaw, foot_yaw))
    return Pp, M_pel, M_chest, M_spine03, sh


def eval_vec(wps, f):
    """Smoothstep-segment waypoint track [(frame, Vector), ...] at frame f."""
    if f <= wps[0][0]:
        return wps[0][1].copy()
    if f >= wps[-1][0]:
        return wps[-1][1].copy()
    for i in range(len(wps) - 1):
        f0, p0 = wps[i]
        f1, p1 = wps[i + 1]
        if f0 <= f <= f1:
            return lerp_v(p0, p1, smoothstep((f - f0) / float(f1 - f0)))
    return wps[-1][1].copy()


def eval_mat(wps, f):
    """Smoothstep-segment waypoint track [(frame, Matrix), ...] at frame f."""
    if f <= wps[0][0]:
        return wps[0][1].copy()
    if f >= wps[-1][0]:
        return wps[-1][1].copy()
    for i in range(len(wps) - 1):
        f0, p0 = wps[i]
        f1, p1 = wps[i + 1]
        if f0 <= f <= f1:
            return rig_ops.lerp_matrices(p0, p1, smoothstep((f - f0) / float(f1 - f0)))
    return wps[-1][1].copy()


def ride_props(rig, Pp, M_pel):
    """Props ride the pelvis; fill Pp['def'] for props the clip didn't set."""
    gs = Pp["scale"]
    M_pel_s = Matrix.Diagonal((gs, gs, gs, 1.0)) @ M_pel if abs(gs - 1.0) > 1e-9 else M_pel
    for p in ("cell_new", "cell_spent", "beacon"):
        if p not in Pp["def"]:
            Pp["def"][p] = M_pel_s @ PROP_OFF[p]


def ik_error(rig, Pp):
    """Max world error of IK-driven effectors vs their (scaled) targets."""
    gs = Pp["scale"]
    worst = 0.0
    for side in ("L", "R"):
        leg = Pp["legs"][side]
        if leg["mode"] == "ik":
            worst = max(worst, (rig.def_m["foot_%s" % side].to_translation()
                                - Vector(leg["ankle"]) * gs).length)
        arm = Pp["arms"][side]
        if arm["mode"] == "ik":
            worst = max(worst, (rig.def_m["hand_%s" % side].to_translation()
                                - Vector(arm["target"]) * gs).length)
            R_exp = arm["hand_R"].to_3x3()
            R_got = rig.def_m["hand_%s" % side].to_3x3()
            rerr = max(abs((R_got @ R_exp.inverted())[i][j] - (1.0 if i == j else 0.0))
                       for i in range(3) for j in range(3))
            worst = max(worst, rerr)
        elif arm["mode"] == "fk" and arm["hand"] is not None \
                and not isinstance(arm["hand"], (tuple, list)):
            worst = max(worst, (rig.def_m["hand_%s" % side].to_translation()
                                - arm["hand"].to_translation() * gs).length)
    return worst


def fk_arm_matrices(rig, side, shoulder, arm):
    """The exact world matrices build_arm's fk_param branch produces."""
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


def combat_hand_matrices(rig, side, shoulder, swing=0.0, lift=6.0, yaw=0.0,
                         elbow=16.0, wrist=-8.0, w=(1.0, 0.0, 0.0)):
    """(M_ua, M_fa, M_h) for the combat arm in hand/IK mode: the FK-param
    solution's positions with the minimal (twist-free) rotations the IK
    solver actually produces.  combat_hand_arm / combat_arm_ik reproduce
    these EXACTLY; fk_param combat arms differ by a ~1 deg twist about the
    forearm axis (invisible; lerp boundaries use the hand/IK variants)."""
    arm = fk_arm(swing=swing, lift=lift, yaw=yaw, elbow=elbow, wrist=wrist, w=w)
    M_ua_fk, M_fa_fk, M_h_fk = fk_arm_matrices(rig, side, shoulder, arm)
    E_fk = M_fa_fk.to_translation()
    W_fk = M_h_fk.to_translation()
    M_ua = rig_ops.dir_pose_matrix(rig.rest["upper_arm_%s" % side],
                                   E_fk - shoulder, shoulder)
    M_fa = rig_ops.dir_pose_matrix(rig.rest["forearm_%s" % side],
                                   W_fk - E_fk, E_fk)
    M_h = (M_fa @ rig.rl["hand_%s" % side]) \
        @ Matrix.Rotation(math.radians(wrist), 4, 'X')
    return M_ua, M_fa, M_h


def combat_hand_arm(rig, side, shoulder, swing=0.0, lift=6.0, yaw=0.0,
                    elbow=16.0, wrist=-8.0, curl=0.18, spread=0.05,
                    w=(1.0, 0.0, 0.0)):
    """FK hand-mode combat arm params == combat_hand_matrices exactly."""
    _, M_fa, M_h = combat_hand_matrices(rig, side, shoulder, swing=swing,
                                       lift=lift, yaw=yaw, elbow=elbow,
                                       wrist=wrist, w=w)
    return fk_hand_arm(M_h, M_fa.to_translation(), curl=curl, spread=spread)


def combat_arm_ik(rig, side, shoulder, swing=0.0, lift=6.0, yaw=0.0,
                  elbow=16.0, wrist=-8.0, curl=0.18, spread=0.05,
                  w=(1.0, 0.0, 0.0)):
    """IK combat arm params == combat_hand_matrices exactly (the analytic IK
    solve with target = FK wrist and pole = FK elbow returns the FK
    solution, so the minimal rotations coincide)."""
    _, M_fa, M_h = combat_hand_matrices(rig, side, shoulder, swing=swing,
                                       lift=lift, yaw=yaw, elbow=elbow,
                                       wrist=wrist, w=w)
    return ik_arm(M_h.to_translation(), M_h, M_fa.to_translation(),
                  curl=curl, spread=spread)


def inv_smoothstep(s):
    """Inverse of t -> t*t*(3-2t) on [0,1] (bisection)."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid * mid * (3.0 - 2.0 * mid) < s:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------ poses
def build_aim(rig, yaw, pitch, pelvis_z=0.905, spread=0.075, shift=0.0,
              lean=0.0, chest_lean=0.0, chest_yaw=0.0, grip_dist=0.23,
              curl=0.25, l_mode="grip", hover_off=None, look=(0.0, 0.0),
              face=None, foot_yaw=0.0, roll=0.0, w=(1.0, 0.0, 0.0)):
    """Two-handed weapon aim at (yaw, pitch) degrees.  The R forearm is pinned
    so the wrist emitter fires exactly along the aim direction; the L hand
    grips the R forearm (or hovers beside it).  muzzle distance 0.38 and
    grip_dist 0.23 keep the L grip reach inside the arm limit over the whole
    9-point grid (worst 0.604 at yaw +-60, pitch 0; clamp 0.6113)."""
    Pp = P(pelvis__z=pelvis_z, pelvis__shift=shift, pelvis__lean=lean,
           pelvis__roll=roll, chest__lean=chest_lean, chest__yaw=chest_yaw,
           look=tuple(look), w=tuple(w))
    if face:
        Pp["face"] = dict(face)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=foot_yaw, spread=spread)
    d = dir_of(yaw, pitch)
    R = aim_forearm_matrix(rig, yaw, pitch)
    em_off = R @ rig.rl["emitter"].to_translation()
    muzzle = M_chest.to_translation() + d * 0.38
    elbow_dir = muzzle - em_off - sh["R"]
    armR = aim_arm_params(rig, "R", sh["R"], yaw, pitch, elbow_dir,
                          curl=curl, spread=0.10)
    M_fa_R = armR["forearm"]
    emitter = (M_fa_R @ rig.rl["emitter"]).to_translation()
    fa_R = M_fa_R.to_3x3()
    grip_pt = M_fa_R @ Vector((0.0, grip_dist, 0.0))
    y_fa = fa_R @ Vector((0.0, 1.0, 0.0))
    z_fa = fa_R @ Vector((0.0, 0.0, 1.0))
    # palm center 2.2 cm inside the forearm surface (-Z side), pressing it
    grip_M = Matrix.Translation(grip_pt - 0.06 * y_fa - 0.047 * z_fa) @ fa_R.to_4x4()
    pole_L = sh["L"] + Vector((-0.15, -0.05, -0.45))
    if l_mode == "grip":
        armL = support_hand_params(rig, grip_M, curl=curl)
        armL["pole"] = tuple(pole_L)
        armL["spread"] = 0.10
    else:  # hover: L hand floats beside the forearm, same orientation
        if hover_off is None:
            hover_off = (-0.10, -0.02, 0.05)
        M_h_L = hand_M(grip_pt + fa_R @ Vector(hover_off), y_fa, z_fa)
        armL = fk_hand_arm(M_h_L, pole_L, curl=curl, spread=0.10)
    Pp["arms"]["R"] = armR
    Pp["arms"]["L"] = armL
    info = {"M_pel": M_pel, "M_chest": M_chest, "shoulders": sh,
            "M_fa_R": M_fa_R, "emitter": emitter, "grip": grip_M,
            "grip_pt": grip_pt, "M_h_L": armL["hand"] if l_mode == "hover" else grip_M,
            "d": d, "yaw": yaw, "pitch": pitch}
    return Pp, info


def aim_pose_blend(rig, s, yaw, pitch, pelvis_z=0.905, spread=0.075, lean=0.0,
                   shift=0.0, chest_lean=0.0, chest_yaw=0.0, roll=0.0,
                   w=(1.0, 0.0, 0.0), look=(0.0, 0.0), face=None,
                   foot_yaw=0.0, curl=0.25, l_mode="grip", grip_dist=0.23):
    """Combat <-> aim upper-body blend: s=0 hand-mode combat arms, s=1 full
    aim.  BOTH forearms are pinned and matrix-lerped (no mode snap, no IK
    twist); at s=0 exactly the hand-mode combat arm, at s=1 exactly the
    build_aim arm."""
    Pa, info = build_aim(rig, yaw, pitch, pelvis_z=pelvis_z, spread=spread,
                         shift=shift, lean=lean, chest_lean=chest_lean,
                         chest_yaw=chest_yaw, roll=roll, w=w, look=look,
                         face=face, foot_yaw=foot_yaw, curl=curl,
                         l_mode=l_mode, grip_dist=grip_dist)
    Pc = combat_pose(rig, pelvis_z=pelvis_z, spread=spread, lean=lean)
    Pc["pelvis"]["shift"] = shift
    Pc["pelvis"]["roll"] = roll
    Pc["chest"]["lean"] = chest_lean
    Pc["chest"]["yaw"] = chest_yaw
    Pc["look"] = tuple(look)
    Pc["w"] = tuple(w)
    if face:
        Pc["face"] = dict(face)
    # legs: rebuild from the shared body so the structures match exactly
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pc)
    Pc["legs"] = stance_legs(rig, M_pel, alpha=foot_yaw, spread=spread)
    Pp = P(lerp_params(Pc, Pa, s))  # deep copy: lerp_params returns b at s>=1
    for side in ("L", "R"):
        _, M_fa_c, M_h_c = combat_hand_matrices(rig, side, sh[side])
        if side == "R":
            M_fa_a = info["M_fa_R"]
            M_h_a = M_fa_a @ rig.rl["hand_R"]
        else:
            M_h_a = info["M_h_L"]
            # analytic IK forearm toward the L hand target (== build_arm's
            # internal solve, pinned so the blend is twist-free)
            E0 = sh["L"] + (rig.rest["forearm_L"].to_translation()
                            - rig.rest["upper_arm_L"].to_translation())
            W0 = sh["L"] + (rig.rest["hand_L"].to_translation()
                            - rig.rest["upper_arm_L"].to_translation())
            pole = sh["L"] + Vector((-0.15, -0.05, -0.45))
            E_new, T_new = rig_ops.solve_2bone_ik(sh["L"], E0, W0,
                                                  M_h_a.to_translation(), pole)
            M_fa_a = rig_ops.dir_pose_matrix(rig.rest["forearm_L"],
                                             T_new - E_new, E_new)
        M_fa = rig_ops.lerp_matrices(M_fa_c, M_fa_a, s)
        M_h = rig_ops.lerp_matrices(M_h_c, M_h_a, s)
        Pp["arms"][side] = fk_forearm_arm(M_fa, M_h, curl=lerp(0.18, curl, s),
                                          spread=lerp(0.05, 0.10, s))
    return Pp, info


def console_pose(rig, s, osc=Vector((0.0, 0.0, 0.0)), pelvis_z=0.905,
                 spread=0.075, look=(0.0, 0.0), face=None):
    """Both hands on an invisible console in front: s=0 hand-mode combat,
    s=1 console.  Forearms pinned (matrix-lerped) so there is no IK twist."""
    Pp = P(pelvis__z=pelvis_z, pelvis__shift=0.0, pelvis__lean=0.0,
           chest__lean=0.0, chest__yaw=0.0, look=tuple(look))
    if face:
        Pp["face"] = dict(face)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=spread)
    c = M_chest.to_translation()
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        _, M_fa_c, M_h_c = combat_hand_matrices(rig, side, sh[side])
        palm = c + Vector((sgn * 0.17, -0.22 if side == "L" else -0.24, -0.06)) + osc
        M_h_t = hand_M(palm, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
        M_h = rig_ops.lerp_matrices(M_h_c, M_h_t, s)
        pole = sh[side] + Vector((sgn * 0.10, -0.20, -0.40))
        # analytic IK forearm toward the lerped hand target, pinned
        E0 = sh[side] + (rig.rest["forearm_%s" % side].to_translation()
                         - rig.rest["upper_arm_%s" % side].to_translation())
        W0 = sh[side] + (rig.rest["hand_%s" % side].to_translation()
                         - rig.rest["upper_arm_%s" % side].to_translation())
        E_new, T_new = rig_ops.solve_2bone_ik(sh[side], E0, W0,
                                              M_h.to_translation(), pole)
        M_fa_t = rig_ops.dir_pose_matrix(rig.rest["forearm_%s" % side],
                                         T_new - E_new, E_new)
        M_fa = rig_ops.lerp_matrices(M_fa_c, M_fa_t, s)
        Pp["arms"][side] = fk_forearm_arm(M_fa, M_h, curl=lerp(0.18, 0.10, s),
                                          spread=lerp(0.05, 0.35, s))
    return Pp


def lying_hand_target(rig, M_pel, M_chest, face_down, kind, hand_floor_z=None):
    """{side: (M_h, palm)} palm targets for a lying body (kinds per the design
    notes).  Floor kinds anchor the palm at hand_floor_z so the hand mesh
    rests on the floor: the mesh extends ~0.02-0.04 (palm down) / ~0.11
    (palm up) below the palm center, measured; 0.05 / 0.12 put the lowest
    hand vert ~1 cm above the floor.  "side_out" is the palm-up sibling of
    "side" (the arm_s lerp base for kind "out"): lerping palm-down -> palm-up
    would swing the fingertips through the floor, so the lerp base shares the
    target's orientation class."""
    c = M_chest.to_translation()
    pel = M_pel.to_translation()
    ax = FWD if face_down else -FWD
    if hand_floor_z is None:
        hand_floor_z = 0.12 if kind in ("out", "side_out") else 0.05
    out = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        if kind == "side":            # limp on the floor beside the chest
            palm = Vector((c.x + sgn * 0.35, c.y + ax.y * 0.10, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "side_out":      # limp palm-up beside the chest
            palm = Vector((c.x + sgn * 0.35, c.y + 0.03, hand_floor_z))
            RH = rot_with_y(Vector((sgn, 0.0, 0.0)), UP)
        elif kind == "prone_fwd":     # prone, arms reaching forward
            palm = Vector((c.x + sgn * 0.13, c.y + ax.y * 0.30, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "push":          # push-up: palms under the shoulders
            palm = Vector((pel.x + sgn * 0.30, pel.y, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "out":           # arms spread, palms up
            palm = Vector((c.x + sgn * 0.42, c.y + 0.03, hand_floor_z))
            RH = rot_with_y(Vector((sgn, 0.0, 0.0)), UP)
        elif kind == "belly":         # hands resting on the belly
            palm = c + Vector((sgn * 0.09, ax.y * 0.02, 0.06))
            RH = rot_with_y(ax, -UP)
        else:
            raise ValueError(kind)
        out[side] = (hand_M(palm, RH @ Vector((0.0, 1.0, 0.0)),
                            RH @ Vector((0.0, 0.0, 1.0))), palm)
    return out


def lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0, pelvis_z=None, lean_deg=None,
             kind="prone_fwd", look=None, face=None, roll=0.0, shift=0.0,
             w=(1.0, 0.0, 0.0), chest_lean=0.0, chest_yaw=0.0,
             hand_over=None, hand_floor_z=None):
    """Lying pose params.  arm_s lerps the arms from the floor-side limp pose
    (arm_s=0) to the requested kind (arm_s=1); leg_s folds the legs: the
    ankle stays on the floor and slides back toward the hip, so the knee
    rises UP (pole above) instead of spearing the floor.  Default pelvis_z /
    look pitch are tuned per orientation so the lowest mesh vert rests on
    the floor (face-down: belly + skull; face-up: shoulder blades + occiput)."""
    if lean_deg is None:
        lean_deg = 93.18 if face_down else -86.82
    if pelvis_z is None:
        pelvis_z = 0.148 if face_down else 0.183
    if look is None:
        look = (0.0, 5.0) if face_down else (0.0, 26.0)
    back = 1.0 if face_down else -1.0
    ax = FWD if face_down else -FWD
    Pp = P(pelvis__z=pelvis_z, pelvis__lean=lean_deg, pelvis__roll=roll,
           pelvis__shift=shift, chest__lean=chest_lean, chest__yaw=chest_yaw,
           look=tuple(look), w=tuple(w))
    if face:
        Pp["face"] = dict(face)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    legs = {}
    for side in ("L", "R"):
        hip = hip_pos(rig, side, M_pel)
        ankle = Vector((hip.x, hip.y + back * (0.20 + 0.35 * leg_s), ANKLE_Z))
        pole = hip + Vector((0.0, back * 0.25, 0.35))
        legs[side] = ik_leg(ankle, yaw=180.0 if face_down else 0.0, pole=pole)
    Pp["legs"] = legs
    side_kind = "side_out" if kind == "out" else "side"
    side_M = lying_hand_target(rig, M_pel, M_chest, face_down, side_kind, hand_floor_z)
    kind_M = lying_hand_target(rig, M_pel, M_chest, face_down, kind, hand_floor_z)
    palms = {}
    for side in ("L", "R"):
        palms[side] = lerp_v(side_M[side][1], kind_M[side][1], arm_s)
        if hand_over is not None and side in hand_over:
            M_h_t = hand_over[side]
        else:
            M_h_t = rig_ops.lerp_matrices(side_M[side][0], kind_M[side][0], arm_s)
        pole = sh[side] + Vector((0.0, ax.y * 0.10, 0.30))
        Pp["arms"][side] = fk_hand_arm(M_h_t, pole, curl=0.0, spread=0.05)
    return Pp, {"M_pel": M_pel, "M_chest": M_chest, "shoulders": sh,
                "palms": palms}


def step_turn(rig, f, n, total_deg, pelvis_z=0.90, spread=0.075, arm_swing=8.0):
    """In-place turn by total_deg over n frames: the pelvis yaws smoothly and
    the feet re-plant every 45 deg (alternating, inside foot first)."""
    t = smoothstep((f - 1) / float(n - 1))
    yaw = total_deg * t
    Pp0 = P(pelvis__z=pelvis_z)
    _, M_pel0, _, _, _ = body_matrices(rig, Pp0)
    a0 = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        hip0 = hip_pos(rig, side, M_pel0)
        a0[side] = Vector((hip0.x + sgn * spread, hip0.y, ANKLE_Z))
    mag = abs(total_deg)
    cross_mag = sorted(set([22.5 + 45.0 * k for k in range(int(round(mag / 45.0)))])
                       | {mag})
    # per-foot step list: (window_center, old_ankle, new_ankle, old_fyaw, new_fyaw)
    steps = {"L": [], "R": []}
    for i, cm in enumerate(cross_mag):
        fc = 1.0 + (n - 1) * inv_smoothstep(cm / mag)
        side = ("L" if total_deg < 0 else "R") if i % 2 == 0 \
            else ("R" if total_deg < 0 else "L")
        steps[side].append(fc)
    ankles = {s: a0[s].copy() for s in ("L", "R")}
    fyaws = {"L": 0.0, "R": 0.0}
    foot_data = {"L": [], "R": []}
    for side in ("L", "R"):
        for fc in steps[side]:
            w1 = min(n, fc + 3.0)
            t_end = smoothstep((w1 - 1) / float(n - 1))
            tgt_yaw = total_deg * t_end
            R_z = Matrix.Rotation(math.radians(tgt_yaw - fyaws[side]), 4, 'Z')
            new_ankle = R_z @ ankles[side]
            foot_data[side].append((fc, ankles[side].copy(), new_ankle,
                                    fyaws[side], tgt_yaw))
            ankles[side] = new_ankle
            fyaws[side] = tgt_yaw
        # catch-up step: a turn ends with BOTH feet at the final yaw.  The
        # trailing foot's last regular step targets the pelvis yaw at its
        # window end, which lags total_deg; it takes one last short step in
        # the final 3 frames (window [n-3, n], lift arc included).
        if abs(fyaws[side] - total_deg) > 1e-9:
            R_z = Matrix.Rotation(math.radians(total_deg - fyaws[side]), 4, 'Z')
            new_ankle = R_z @ ankles[side]
            foot_data[side].append((float(n), ankles[side].copy(), new_ankle,
                                    fyaws[side], total_deg))
            ankles[side] = new_ankle
            fyaws[side] = total_deg
    # evaluate the feet at frame f
    cur = {}
    for side in ("L", "R"):
        ankle = a0[side].copy()
        fyaw = 0.0
        lift = 0.0
        for fc, a_old, a_new, y_old, y_new in foot_data[side]:
            w0 = max(1.0, fc - 3.0)
            w1 = min(float(n), fc + 3.0)
            if f < w0:
                break
            if f >= w1:
                ankle = a_new
                fyaw = y_new
            else:
                u = smoothstep((f - w0) / (w1 - w0))
                ankle = lerp_v(a_old, a_new, u) + UP * 0.07 * math.sin(math.pi * u)
                fyaw = lerp(y_old, y_new, u)
                lift = 0.07 * math.sin(math.pi * u)
                break
        cur[side] = (ankle, fyaw, lift)
    # pelvis z rides the ceiling for the current ankles
    Pp, M_pel, M_chest, M_spine03, sh = stance_at(
        rig, cur["L"][0], cur["R"][0], pelvis_z=pelvis_z, lean=2.0, yaw=yaw,
        chest_yaw=0.6 * yaw, d_mid=0.93,
        look=(clamp(0.5 * yaw, -75.0, 75.0), 0.0))
    for side in ("L", "R"):
        ankle, fyaw, _ = cur[side]
        hip = hip_pos(rig, side, M_pel)
        u = dir_of(fyaw, 0.0)
        pole = hip + u * 0.30 + Vector((0.0, 0.0, -0.25))
        Pp["legs"][side] = ik_leg(ankle, yaw=fyaw, pole=pole)
    nc = len(cross_mag)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        swing = sgn * arm_swing * math.sin(TWO_PI * (f - 1) / float(n) * nc)
        Pp["arms"][side] = fk_arm(swing=swing, lift=6.0, elbow=16.0)
    return Pp


# ================================================================== probes
t00 = time.time()

print("== A: combat hand/IK arms reproduce combat_hand_matrices")
# combat_arm_ik / combat_hand_arm are the lerp-boundary-exact combat arms;
# fk_param combat arms differ by a ~1.3 deg forearm twist (invisible), so the
# exactness target is combat_hand_matrices, not the fk_param result.
for params, tag in (({}, "default"),
                    (dict(swing=25.0, lift=30.0, elbow=40.0, wrist=-20.0), "swung")):
    for side in ("L", "R"):
        Pc = combat_pose(rig, pelvis_z=0.905, spread=0.075)
        _, _, _, _, sh = body_matrices(rig, Pc)
        M_ua, M_fa, M_h = combat_hand_matrices(rig, side, sh[side], **params)
        for ctor in (combat_hand_arm, combat_arm_ik):
            Pa = combat_pose(rig, pelvis_z=0.905, spread=0.075)
            Pa["arms"][side] = ctor(rig, side, sh[side], **params)
            pose(Pa)
            worst = 0.0
            for bn, M in (("upper_arm_%s" % side, M_ua),
                          ("forearm_%s" % side, M_fa),
                          ("hand_%s" % side, M_h)):
                worst = max(worst, mat_err(rig.def_m[bn], M))
            check("A %s %s %s == combat_hand_matrices" % (side, tag, ctor.__name__),
                  worst < 1e-5, "err=%.2e" % worst)

print("== B: build_aim 9-point grid")
worst_fire = worst_ik = 0.0
worst_reach = 0.0
worst_elbow = 0.0
worst_palm = 0.0
for yaw in (-60.0, 0.0, 60.0):
    for pitch in (-35.0, 0.0, 35.0):
        Pp, info = build_aim(rig, yaw, pitch)
        pose(Pp)
        fire = (rig.def_m["emitter"].to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
        ferr = (fire - info["d"]).length
        worst_fire = max(worst_fire, ferr)
        elbow = rig.def_m["forearm_R"].to_translation()
        e1 = abs((elbow - info["shoulders"]["R"]).length - rig.arm_L1["R"])
        worst_elbow = max(worst_elbow, e1)
        grip_t = info["grip"].to_translation()
        reach = (grip_t - info["shoulders"]["L"]).length
        worst_reach = max(worst_reach, reach)
        ikr = ik_error(rig, Pp)
        worst_ik = max(worst_ik, ikr)
        # palm contact: palm center sits 2.2 cm off the forearm axis, -Z side
        y_fa = info["M_fa_R"].to_3x3() @ Vector((0.0, 1.0, 0.0))
        z_fa = info["M_fa_R"].to_3x3() @ Vector((0.0, 0.0, 1.0))
        palm_c = info["grip_pt"] - 0.022 * z_fa
        rel = palm_c - elbow
        perp = (rel - y_fa * rel.dot(y_fa)).length
        side_z = rel.dot(z_fa)
        worst_palm = max(worst_palm, abs(perp - 0.022), abs(side_z + 0.022))
        print("   aim yaw=%5.1f pitch=%5.1f  fire=%.1e elbow=%.1e reach=%.3f ik=%.1e palm=%.3f/%.3f"
              % (yaw, pitch, ferr, e1, reach, ikr, perp, side_z))
check("B fire direction exact (9 grid points)", worst_fire < 1e-5, "err=%.2e" % worst_fire)
check("B elbow at L1 from shoulder", worst_elbow < 1e-5, "err=%.2e" % worst_elbow)
check("B L grip reach <= 0.605", worst_reach <= 0.605, "max=%.4f" % worst_reach)
check("B IK error small", worst_ik < 1e-4, "err=%.2e" % worst_ik)
check("B palm presses forearm surface", worst_palm < 0.006, "err=%.2e" % worst_palm)
# hover mode
Pp, info = build_aim(rig, 20.0, 15.0, l_mode="hover")
pose(Pp)
check("B hover mode IK error", ik_error(rig, Pp) < 1e-4,
      "err=%.2e reach=%.3f" % (ik_error(rig, Pp),
                               (info["M_h_L"].to_translation() - info["shoulders"]["L"]).length))
# aim_pose_blend endpoints + mid
for s in (0.0, 0.5, 1.0):
    Pp, info = aim_pose_blend(rig, s, 30.0, 10.0)
    pose(Pp)
    ikr = ik_error(rig, Pp)
    check("B aim_pose_blend s=%.1f IK error" % s, ikr < 1e-4, "err=%.2e" % ikr)
Pp, info = aim_pose_blend(rig, 1.0, 30.0, 10.0)
fire = (rig.def_m["emitter"].to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
check("B blend s=1 fires along aim", (fire - dir_of(30.0, 10.0)).length < 1e-5,
      "err=%.2e" % (fire - dir_of(30.0, 10.0)).length)

print("== C: lying_pp (floor contact / reach / IK)")
worst_ik = 0.0
min_z, max_z = 1e9, -1e9
worst_reach = 0.0
head_zs = []
for face_down in (True, False):
    for kind in ("side", "prone_fwd", "push", "out", "belly"):
        for leg_s, arm_s in ((1.0, 1.0), (0.0, 0.0), (0.35, 0.5)):
            Pp, info = lying_pp(rig, face_down, leg_s=leg_s, arm_s=arm_s, kind=kind)
            pose(Pp)
            ikr = ik_error(rig, Pp)
            worst_ik = max(worst_ik, ikr)
            mz = mesh_min_z()
            min_z = min(min_z, mz)
            max_z = max(max_z, mz)
            hz = rig.def_m["head"].to_translation().z
            head_zs.append(hz)
            reach = max((Pp["arms"][s]["hand"].to_translation()
                         - info["shoulders"][s]).length for s in ("L", "R"))
            worst_reach = max(worst_reach, reach)
print("   mesh min z over all lying poses: [%.4f, %.4f]  head z: [%.3f, %.3f]  worst reach=%.3f"
      % (min_z, max_z, min(head_zs), max(head_zs), worst_reach))
check("C lying floor contact (min z in [-0.005, 0.06])", -0.005 <= min_z and max_z <= 0.06,
      "min=%.4f max=%.4f" % (min_z, max_z))
check("C lying head rests low", max(head_zs) < 0.25, "max head z=%.3f" % max(head_zs))
check("C lying IK error", worst_ik < 1e-3, "err=%.2e" % worst_ik)
check("C lying arm reach", worst_reach < 0.611, "max=%.4f" % worst_reach)
# death_back turns the face-down head sideways (look yaw 30): the skull must
# not dip through the floor
Pp, info = lying_pp(rig, True, leg_s=1.0, arm_s=1.0, kind="prone_fwd",
                    look=(30.0, 5.0))
pose(Pp)
mz = mesh_min_z()
check("C lying head-turned (death_back look) floor contact", mz >= -0.005,
      "min z=%.4f" % mz)
# getup push phase: palms planted on the floor (palm center z = 0.05, the
# tuned floor height) while the body rises; the palms lerp from the prone
# forward palms (t=0 == the prone pose exactly) to under the shoulders, and
# the hand HEAD is reach-clamped to 0.585 so the IK never clamps.
Pp_prone, info_prone = lying_pp(rig, True, leg_s=1.0, arm_s=1.0, kind="prone_fwd")
pose(Pp_prone)
prone_def = {n: rig.def_m[n].copy() for n in DEFORM_BONES}
RH_push = rot_with_y(FWD, -UP)
worst_ik = 0.0
worst_reach = 0.0
worst_prone = 0.0
for t in (0.0, 0.25, 0.5, 0.75, 1.0):
    st = smoothstep(t)
    lean = lerp(93.18, 48.0, st)
    pz = lerp(0.148, 0.42, st)
    leg_s = lerp(1.0, 0.8, st)
    Pp_ref, info_ref = lying_pp(rig, True, leg_s=leg_s, arm_s=1.0, pelvis_z=pz,
                                lean_deg=lean, kind="push")
    hand_over = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        desired = Vector((sgn * 0.30, info_ref["shoulders"][side].y * 0.6, 0.05))
        palm = lerp_v(info_prone["palms"][side], desired, st)
        M_h = hand_M(palm, RH_push @ Vector((0.0, 1.0, 0.0)),
                     RH_push @ Vector((0.0, 0.0, 1.0)))
        head = M_h.to_translation()
        sh_s = info_ref["shoulders"][side]
        if (head - sh_s).length > 0.585:
            head = sh_s + (head - sh_s).normalized() * 0.585
            M_h = Matrix.Translation(head) @ M_h.to_3x3().to_4x4()
        hand_over[side] = M_h
    Pp, info = lying_pp(rig, True, leg_s=leg_s, arm_s=1.0, pelvis_z=pz,
                        lean_deg=lean, kind="push", hand_over=hand_over)
    pose(Pp)
    worst_ik = max(worst_ik, ik_error(rig, Pp))
    reach = max((Pp["arms"][s]["hand"].to_translation()
                 - info["shoulders"][s]).length for s in ("L", "R"))
    worst_reach = max(worst_reach, reach)
    if t == 0.0:
        worst_prone = max(mat_err(rig.def_m[n], prone_def[n]) for n in DEFORM_BONES)
check("C getup push phase IK error", worst_ik < 1e-3, "err=%.2e" % worst_ik)
check("C getup push phase reach", worst_reach < 0.611, "max=%.4f" % worst_reach)
check("C getup t=0 == prone_front pose exactly", worst_prone < 1e-9,
      "err=%.2e" % worst_prone)

print("== D: reload choreography reach")
HOLSTER_GRIP = hand_M(Vector((-0.227, 0.022, 0.945)), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
CELL_GRIP_L = rig.rest["cell_new"].inverted() @ HOLSTER_GRIP
Pc = combat_pose(rig, pelvis_z=0.905, spread=0.075)
_, _, _, _, sh_c = body_matrices(rig, Pc)
Pp = P(Pc)
Pp["arms"]["L"] = ik_arm(HOLSTER_GRIP.to_translation(), HOLSTER_GRIP,
                         sh_c["L"] + Vector((-0.15, -0.05, -0.45)), curl=0.55)
pose(Pp)
print("   L holster grip: reach=%.4f ik=%.2e"
      % ((HOLSTER_GRIP.to_translation() - sh_c["L"]).length, ik_error(rig, Pp)))
check("D L holster grip reach", (HOLSTER_GRIP.to_translation() - sh_c["L"]).length < 0.605)
check("D L holster grip IK", ik_error(rig, Pp) < 1e-4, "err=%.2e" % ik_error(rig, Pp))
Pp["def"]["cell_new"] = HOLSTER_GRIP @ CELL_GRIP_L.inverted()
pose(Pp)
check("D held cell_new == holster rest frame",
      mat_err(rig.def_m["cell_new"], rig.rest["cell_new"]) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["cell_new"], rig.rest["cell_new"]))
# seat grip on the aim body
Pa, info = build_aim(rig, 0.0, 0.0)
sh = info["shoulders"]
M_fa_R = info["M_fa_R"]
seat_M = (M_fa_R @ rig.rl["emitter"]) @ CELL_SEAT_LOCAL
M_h_seat = seat_M @ CELL_GRIP_L
reach_s = (M_h_seat.to_translation() - sh["L"]).length
Pp = P(Pa)
Pp["arms"]["L"] = ik_arm(M_h_seat.to_translation(), M_h_seat,
                         sh["L"] + Vector((-0.15, -0.05, -0.45)), curl=0.55)
Pp["def"]["cell_new"] = M_h_seat @ CELL_GRIP_L.inverted()
pose(Pp)
print("   L seat grip: reach=%.4f ik=%.2e  seat@%s"
      % (reach_s, ik_error(rig, Pp),
         tuple(round(c, 3) for c in seat_M.to_translation())))
check("D L seat grip reach", reach_s < 0.605, "reach=%.4f" % reach_s)
check("D L seat grip IK", ik_error(rig, Pp) < 1e-4, "err=%.2e" % ik_error(rig, Pp))
check("D seated cell == seat frame", mat_err(rig.def_m["cell_new"], seat_M) < 1e-5)
# R catch of the spent cell below the barrel
M_cell_catch = seat_M @ Matrix.Translation((0.0, -0.065, -0.025))
R_cell = M_cell_catch.to_3x3()
M_h_catch = hand_M(M_cell_catch.to_translation() + R_cell @ Vector((0.0, -0.012, -0.028)),
                   R_cell @ Vector((0.0, 1.0, 0.0)), (0.0, 0.0, 1.0))
CELL_GRIP_R = M_cell_catch.inverted() @ M_h_catch
reach_c = (M_h_catch.to_translation() - sh["R"]).length
Pp = P(Pa)
Pp["arms"]["R"] = fk_forearm_arm(M_fa_R, M_h_catch, curl=0.4)
Pp["def"]["cell_spent"] = M_h_catch @ CELL_GRIP_R.inverted()
pose(Pp)
print("   R catch: reach=%.4f ik=%.2e  catch@%s"
      % (reach_c, ik_error(rig, Pp),
         tuple(round(c, 3) for c in M_cell_catch.to_translation())))
check("D R catch reach", reach_c < 0.605, "reach=%.4f" % reach_c)
check("D R catch IK", ik_error(rig, Pp) < 1e-4, "err=%.2e" % ik_error(rig, Pp))
check("D caught cell == catch frame", mat_err(rig.def_m["cell_spent"], M_cell_catch) < 1e-5)
# R pouch carry: the cell is carried to a slot raised 6 cm above its rest
# pouch position (at rest the reach is 0.636 > the 0.611 arm limit; raised,
# ~0.576).  The hand releases before the cell presses down into the pouch.
pouch_hover = Matrix.Translation((0.0, 0.0, 0.06)) @ rig.rest["cell_spent"]
M_h_pouch = pouch_hover @ CELL_GRIP_R
reach_p = (M_h_pouch.to_translation() - sh["R"]).length
Pp = P(Pa)
Pp["arms"]["R"] = fk_hand_arm(M_h_pouch, sh["R"] + Vector((0.10, -0.05, -0.35)), curl=0.4)
Pp["def"]["cell_spent"] = pouch_hover.copy()
pose(Pp)
print("   R pouch carry: reach=%.4f ik=%.2e" % (reach_p, ik_error(rig, Pp)))
check("D R pouch carry reach", reach_p < 0.605, "reach=%.4f" % reach_p)
check("D R pouch carry IK", ik_error(rig, Pp) < 1e-4, "err=%.2e" % ik_error(rig, Pp))
check("D carried cell == pouch_hover frame",
      mat_err(rig.def_m["cell_spent"], pouch_hover) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["cell_spent"], pouch_hover))

print("== E: deploy reach")
BEACON_GRIP = rig.rest["beacon"].inverted() @ hand_M((0.0, 0.215, 1.382),
                                                    (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
for env in (0.0, 1.0):
    pz = 0.905 - 0.305 * env
    Pc = combat_pose(rig, pelvis_z=pz, spread=0.075, lean=4.0 * env)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pc)
    Pc["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=0.075)
    # the R hand holds the beacon rigidly at the posed backpack mount
    M_h_pack = (M_pel @ PROP_OFF["beacon"]) @ BEACON_GRIP
    reach_pack = (M_h_pack.to_translation() - sh["R"]).length
    Pp = P(Pc)
    Pp["arms"]["R"] = fk_hand_arm(M_h_pack, sh["R"] + Vector((0.15, -0.10, -0.40)))
    Pp["def"]["beacon"] = M_pel @ PROP_OFF["beacon"]
    pose(Pp)
    ikr = ik_error(rig, Pp)
    print("   env=%.1f backpack reach=%.4f ik=%.2e held-beacon err=%.2e"
          % (env, reach_pack, ikr, mat_err(rig.def_m["beacon"], M_pel @ PROP_OFF["beacon"])))
    check("E backpack grip reach (env=%.1f)" % env, reach_pack < 0.605,
          "reach=%.4f" % reach_pack)
    check("E backpack grip IK (env=%.1f)" % env, ikr < 1e-4, "err=%.2e" % ikr)
    check("E held beacon == posed backpack frame (env=%.1f)" % env,
          mat_err(rig.def_m["beacon"], M_pel @ PROP_OFF["beacon"]) < 1e-5)
    if env >= 1.0:
        # the spot is only reachable at full crouch (the hand gets there once
        # the body has descended), so the spot check runs at env=1 only
        M_h_spot = hand_M(DEPLOY_SPOT + UP * 0.031, (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
        reach_spot = (M_h_spot.to_translation() - sh["R"]).length
        Pp2 = P(Pc)
        Pp2["arms"]["R"] = ik_arm(M_h_spot.to_translation(), M_h_spot,
                                  sh["R"] + Vector((0.15, -0.10, -0.40)))
        pose(Pp2)
        ikr2 = ik_error(rig, Pp2)
        print("   env=1.0 spot reach=%.4f ik=%.2e" % (reach_spot, ikr2))
        check("E spot reach (full crouch)", reach_spot < 0.605, "reach=%.4f" % reach_spot)
        check("E spot IK (full crouch)", ikr2 < 1e-4, "err=%.2e" % ikr2)

print("== F: step_turn 90 deg")
n = 24
worst_ik = 0.0
foot_hist = {"L": [], "R": []}
pelvis_xy = []
for f in range(1, n + 1):
    Pp = step_turn(rig, f, n, -90.0)
    pose(Pp)
    worst_ik = max(worst_ik, ik_error(rig, Pp))
    for s in ("L", "R"):
        foot_hist[s].append(rig.def_m["foot_%s" % s].to_translation().copy())
    pelvis_xy.append(Vector((rig.def_m["pelvis"].to_translation().x,
                             rig.def_m["pelvis"].to_translation().y)))
# feet exactly planted between steps: consecutive on-ground positions identical
worst_jump = 0.0
for s in ("L", "R"):
    for i in range(n - 1):
        a, b = foot_hist[s][i], foot_hist[s][i + 1]
        if abs(a.z - ANKLE_Z) < 1e-4 and abs(b.z - ANKLE_Z) < 1e-4:
            worst_jump = max(worst_jump, (a - b).length)
check("F feet exactly planted between steps", worst_jump < 1e-6, "err=%.2e" % worst_jump)
check("F step_turn IK error", worst_ik < 1e-3, "err=%.2e" % worst_ik)
check("F pelvis stays at origin", max(p.length for p in pelvis_xy) < 0.02,
      "max=%.4f" % max(p.length for p in pelvis_xy))
# final yaw: pelvis spine axis horizontal dir == dir_of(-90)
spine_dir = (rig.def_m["pelvis"].to_3x3() @ Vector((0.0, 0.0, 1.0)))
spine_dir.z = 0.0
spine_dir.normalize()
want = dir_of(-90.0, 0.0)
yawerr = math.degrees(spine_dir.angle(want))
check("F final pelvis yaw = -90", yawerr < 1.0, "err=%.2f deg" % yawerr)
# final foot yaw = -90 and ankles rotated about origin
Pp = step_turn(rig, n, n, -90.0)
pose(Pp)
Pp0 = P(pelvis__z=0.90)
_, M_pel0, _, _, _ = body_matrices(rig, Pp0)
a0 = {}
for side, sgn in (("L", -1.0), ("R", 1.0)):
    hip0 = hip_pos(rig, side, M_pel0)
    a0[side] = Vector((hip0.x + sgn * 0.075, hip0.y, ANKLE_Z))
R_z = Matrix.Rotation(math.radians(-90.0), 4, 'Z')
worst_ank = 0.0
for s in ("L", "R"):
    want_ank = R_z @ a0[s]
    worst_ank = max(worst_ank, (rig.def_m["foot_%s" % s].to_translation() - want_ank).length)
check("F final ankles rotated -90 about origin", worst_ank < 1e-4, "err=%.2e" % worst_ank)
# 180 deg pivot sanity
worst_ik = 0.0
for f in range(1, 31):
    Pp = step_turn(rig, f, 30, 180.0, arm_swing=16.0)
    pose(Pp)
    worst_ik = max(worst_ik, ik_error(rig, Pp))
check("F pivot 180 IK error", worst_ik < 1e-3, "err=%.2e" % worst_ik)

print("== G: dash root motion (stance foot planted in world)")
g = GAIT["dash"]
n = g["n"]
s2pi = TWO_PI * g["stance"]
for d in ("f", "r"):
    alpha = DASH_ALPHA[d]
    u = DASH_DIRS[d].normalized()
    lat = Vector((-u.y, u.x, 0.0))
    stance_world = {"L": [], "R": []}
    travel = []
    for f in range(1, n + 1):
        off = DASH_DIRS[d] * 2.0 * (f - 1) / (n - 1)
        rig.root_off = off
        Pp = gait_frame(rig, "dash", alpha, f)
        Pp["root"] = (off.x, off.z, -off.y)
        pose(Pp)
        for side, offs in (("L", 0.0), ("R", math.pi)):
            ph = (TWO_PI * (f - 1) / n + offs) % TWO_PI
            if ph < s2pi:  # stance
                stance_world[side].append(
                    rig.def_m["foot_%s" % side].to_translation().copy())
        travel.append(rig.def_m["pelvis"].to_translation().copy())
    rig.root_off = Vector((0.0, 0.0, 0.0))
    # planting is judged ALONG the travel direction: the treadmill gait
    # cancels the linear root motion exactly (E = 2*stance*n/(n-1)), leaving
    # only the small pelvis yaw-sway wobble (~0.0015).  The lateral gait shift
    # (+-0.020) is inherent to the walk and is reported separately.
    worst_along = worst_lat = 0.0
    for s in ("L", "R"):
        along = [p.dot(u) for p in stance_world[s]]
        worst_along = max(worst_along, max(along) - min(along))
        latv = [p.dot(lat) for p in stance_world[s]]
        worst_lat = max(worst_lat, max(latv) - min(latv))
    disp_v = travel[-1] - travel[0]
    disp_v.z = 0.0
    disp = disp_v.length
    dir_err = math.degrees(disp_v.normalized().angle(u))
    check("G dash_%s stance feet planted along track" % d, worst_along < 0.005,
          "along spread=%.4f (%d stance frames/foot)" % (worst_along, len(stance_world["L"])))
    check("G dash_%s lateral gait shift bounded" % d, worst_lat < 0.02,
          "lateral spread=%.4f (inherent pelvis shift)" % worst_lat)
    check("G dash_%s body travels 2.0 m horizontally along %s" % (d, d),
          abs(disp - 2.0) < 1e-3 and dir_err < 0.5,
          "disp=%.4f dir_err=%.2f deg" % (disp, dir_err))
# root bone also travels; the pelvis keeps its exact offset from the root
# (the root bone's world translation IS the root offset: local (x, z, -y))
off = DASH_DIRS["f"] * 2.0
rig.root_off = off
Pp = gait_frame(rig, "dash", 0.0, n)
Pp["root"] = (off.x, off.z, -off.y)
M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
pose(Pp)
rel = rig.def_m["pelvis"].to_translation() - rig.def_m["root"].to_translation()
rel_exp = M_pel.to_translation() - off
rig.root_off = Vector((0.0, 0.0, 0.0))
err = (rel - rel_exp).length
check("G pelvis keeps its root offset (no stretch)", err < 1e-4, "err=%.2e" % err)
# loop seam (root_off excluded)
rig.root_off = Vector((0.0, 0.0, 0.0))
p1 = gait_frame(rig, "dash", 0.0, 1)
p2 = gait_frame(rig, "dash", 0.0, n + 1)


def params_close(a, b, tol=1e-9):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a.keys()) == set(b.keys()) and all(params_close(a[k], b[k], tol) for k in a)
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        return mat_err(a, b) < tol
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < tol
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b):
        return all(params_close(x, y, tol) for x, y in zip(a, b))
    return a == b


check("G dash loop seam", params_close(p1, p2), "")

print("== H: console_pose s=1")
Pp = console_pose(rig, 1.0, osc=Vector((0.02, -0.01, 0.03)))
pose(Pp)
ikr = ik_error(rig, Pp)
check("H console s=1 IK error", ikr < 1e-4, "err=%.2e" % ikr)
Pp = console_pose(rig, 0.5)
pose(Pp)
check("H console s=0.5 IK error", ik_error(rig, Pp) < 1e-4,
      "err=%.2e" % ik_error(rig, Pp))

print("== I: ref_forearm mechanism")
Pa, info = build_aim(rig, 0.0, 0.0)
Pp = P(Pa)
Pp["arms"]["L"] = {"mode": "fk", "hand": ("ref_forearm", (0.0, 0.27, 0.0), 0),
                   "pole": tuple(info["shoulders"]["L"] + Vector((-0.15, -0.05, -0.45))),
                   "curl": 0.25, "spread": 0.10, "w": (1.0, 0.0, 0.0),
                   "swing": 0.0, "lift": 0.0, "yaw": 0.0, "elbow": 0.0,
                   "wrist": 0.0, "forearm": None, "target": None, "hand_R": None}
pose(Pp)
ref = rig.arm_m["R"]["fa"] @ Vector((0.0, 0.27, 0.0))
err_t = (rig.def_m["hand_L"].to_translation() - ref).length
err_r = mat_err(rig.def_m["hand_L"],
                Matrix.Translation(ref) @ rig.arm_m["R"]["fa"].to_3x3().to_4x4())
check("I ref_forearm hand rides R forearm frame", err_t < 1e-4 and err_r < 1e-4,
      "t=%.2e r=%.2e" % (err_t, err_r))

print("== J: dialogue gestures")
GESTURE_DEFS = [
    ("open_r", {"R": ((0.10, -0.38, -0.02), (0, 0, 1), (0, -1, 0), None, 0.45)}),
    ("fist_r", {"R": ((0.12, -0.22, -0.10), (0, -1, 0), (0, 0, -1), "fist", 0.05)}),
    ("point_r", {"R": ((0.05, -0.42, 0.02), (0, -1, 0), (0, 0, -1), "point", 0.05)}),
    ("palm_l", {"L": ((-0.28, -0.18, -0.02), (0, -1, 0), (0, 0, 1), None, 0.45)}),
    ("palms", {"L": ((-0.20, -0.30, -0.08), (0, -1, 0), (0, 0, 1), None, 0.45),
               "R": ((0.20, -0.32, -0.08), (0, -1, 0), (0, 0, 1), None, 0.45)}),
    ("grim", {"L": ((-0.16, -0.30, -0.10), (0, 0, -1), (0, -1, 0), "soft", 0.65),
              "R": ((0.16, -0.30, -0.10), (0, 0, -1), (0, -1, 0), "soft", 0.65)}),
]
FINGER_PRESETS = {
    None: {f: 13.0 for f in FINGERS},
    "fist": {"thumb": 55.0, "index": 80.0, "middle": 80.0, "ring": 80.0, "pinky": 80.0},
    "point": {"thumb": 50.0, "index": 0.0, "middle": 80.0, "ring": 80.0, "pinky": 80.0},
    "soft": {f: 25.0 for f in FINGERS},
}
worst_ik = 0.0
worst_reach = 0.0
base_arms = {}
for gname, spec in GESTURE_DEFS:
    Pc = combat_pose(rig, pelvis_z=0.905 + 0.004, spread=0.075)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pc)
    Pc["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=0.075)
    c = M_chest.to_translation()
    for side in ("L", "R"):
        if side not in base_arms:
            base_arms[side] = combat_arm_ik(rig, side, sh[side])
        if side in spec:
            off, y_dir, z_dir, fkey, spread = spec[side]
            M_h = hand_M(c + Vector(off), y_dir, z_dir)
            pole = sh[side] + Vector((0.10 if side == "R" else -0.10, -0.05, -0.40))
            Pc["arms"][side] = ik_arm(M_h.to_translation(), M_h, pole,
                                      curl=0.25, spread=spread)
            Pc["fingers"][side] = dict(FINGER_PRESETS[fkey])
            worst_reach = max(worst_reach, (M_h.to_translation() - sh[side]).length)
    pose(Pc)
    ikr = ik_error(rig, Pc)
    worst_ik = max(worst_ik, ikr)
    print("   gesture %-8s ik=%.2e" % (gname, ikr))
check("J gesture reach", worst_reach < 0.605, "max=%.4f" % worst_reach)
check("J gesture IK error", worst_ik < 1e-4, "err=%.2e" % worst_ik)
# lerp smoothness between base and a gesture (structure + no snap)
Pc = combat_pose(rig, pelvis_z=0.905, spread=0.075)
_, M_pel_j, M_chest_j, _, sh = body_matrices(rig, Pc)
Pc["legs"] = stance_legs(rig, M_pel_j, alpha=0.0, spread=0.075)
c = M_chest_j.to_translation()
M_h = hand_M(c + Vector((0.10, -0.38, -0.02)), (0, 0, 1), (0, -1, 0))
gest = ik_arm(M_h.to_translation(), M_h, sh["R"] + Vector((0.10, -0.05, -0.40)),
              curl=0.25, spread=0.45)
base = combat_arm_ik(rig, "R", sh["R"])
mid = lerp_params(base, gest, 0.5)
check("J lerp base->gesture keeps IK structure",
      mid["mode"] == "ik" and isinstance(mid["target"], tuple)
      and isinstance(mid["hand_R"], Matrix) and isinstance(mid["pole"], tuple),
      "mode=%s" % mid["mode"])
Pp = P(Pc)
Pp["arms"]["R"] = mid
Pp["legs"] = stance_legs(rig, M_pel_j, alpha=0.0, spread=0.075)
pose(Pp)
check("J lerped gesture arm IK error", ik_error(rig, Pp) < 1e-4,
      "err=%.2e" % ik_error(rig, Pp))

print("== K: Action loop-flag behavior (Blender 5.1 slotted actions)")
props = [p.identifier for p in bpy.types.Action.bl_rna.properties]
print("   Action props:", props)
has_cyclic = any("cycl" in p.lower() for p in props)
# empirical: does Action.use_cyclic wrap fcurve evaluation?  Key a 3-frame
# ramp 0->1 on a shape key, set use_cyclic, and evaluate outside [1, 3].
kb = rig.sk.key_blocks["lip_close"]
act_k = bpy.data.actions.new("probe_k_tmp")
if rig.sk.animation_data is None:
    rig.sk.animation_data_create()
rig.sk.animation_data.action = act_k
kb.value = 0.0
kb.keyframe_insert("value", frame=1)
kb.value = 1.0
kb.keyframe_insert("value", frame=3)
act_k.use_cyclic = True
bpy.context.scene.frame_set(4)
v4 = kb.value
bpy.context.scene.frame_set(0)
v0 = kb.value
rig.sk.animation_data.action = None
bpy.data.actions.remove(act_k)
kb.value = 0.0
bpy.context.scene.frame_set(1)
# held (no wrap) => the loop flag cannot live on the Action; it is recorded in
# animation_manifest.json only, and no CYCLES fcurve modifiers are added.
check("K use_cyclic exists but does NOT wrap evaluation",
      has_cyclic and abs(v4 - 1.0) < 1e-6 and abs(v0 - 0.0) < 1e-6,
      "use_cyclic=%s frame4=%.3f (held) frame0=%.3f (held)" % (has_cyclic, v4, v0))

print("== L: victory hop + melee wrist path")
Pc = combat_pose(rig, pelvis_z=0.905 + 0.10, spread=0.075)
M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pc)
hop = 0.10
legs = {}
for side in ("L", "R"):
    hip = hip_pos(rig, side, M_pel)
    pole = hip + dir_of(0.0) * 0.30 + Vector((0.0, 0.0, -0.25 + hop))
    legs[side] = ik_leg((hip.x, hip.y, ANKLE_Z + hop), pole=pole)
Pc["legs"] = legs
pose(Pc)
check("L victory hop IK error", ik_error(rig, Pc) < 1e-4, "err=%.2e" % ik_error(rig, Pc))
# melee_3 two-handed chop: the R wrist rides a hand-driven path; check it at
# plain combat shoulders (the clip plays from combat, not from the hop)
Pc0 = combat_pose(rig, pelvis_z=0.905, spread=0.075)
_, _, _, _, sh0 = body_matrices(rig, Pc0)
worst = 0.0
for wrist in ((0.295, -0.082, 0.745), (0.15, -0.25, 1.75), (0.25, -0.45, 0.95)):
    reach = (Vector(wrist) - sh0["R"]).length
    worst = max(worst, reach)
    print("   melee wrist %s reach=%.4f" % (wrist, reach))
check("L melee_3 wrist path reachable", worst < 0.611, "max=%.4f" % worst)

print("")
print("== summary: %d passed, %d failed  (%.1f s)" % (len(PASS), len(FAIL), time.time() - t00))
if FAIL:
    print("FAILED:", FAIL)
print("PROBE %s" % ("OK" if not FAIL else "FAILED"))

"""gen_03_animations.py - author the 96 required MorphRig Operative clips.

Part of the MorphRig Operative production (SPEC.md section 8).  Bakes every
entry of required_animations.csv as an editable Blender action on the
deformation skeleton (Armature) plus a companion shape-key action
(<id>_face), verifies each clip (IK/chain closure, key range, markers,
action round-trip, loop seam, floor contact), writes
docs/animation_manifest.json (plus a copy at the task root) and saves
source/Operative_rig.blend.

Run:  blender -b --factory-startup --python source/generators/gen_03_animations.py

Conventions (mirrored in docs/animation_manifest.json):
  * 30 FPS, Blender meters, Z up, the character faces -Y (+yaw = right,
    +pitch = up).
  * Frame keys span exactly [1, n]; duration_seconds = n / 30.
  * Loop flags are manifest-only: Blender 5.1 Action.use_cyclic exists but
    does NOT wrap fcurve evaluation (verified empirically), so no CYCLES
    fcurve modifiers are added anywhere.
  * Gait clips are treadmill-authored: the stance foot moves backward
    relative to the body at v_app, so a controller moving the capsule at
    v_app keeps the world feet planted.  Nominal speeds: walk 150, run 400,
    sprint 650 cm/s.
  * dash_* are root-motion clips: the root bone carries a linear 2.0 m
    translation along the dash direction; the capsule/controller must track
    the root bone and the mesh must not drift away from the capsule.
  * blink_out/blink_in bake no actor travel; the teleport/arrive events are
    pose markers only.
  * Layers: full_body (whole-body clip), upper_body (reusable upper-body
    layer over a locomotion/idle base; the legs stay in the base stance and
    are never rotated through the floor), additive_upper (hit reactions
    authored over a neutral combat reference; add over idle/motion without
    snapping planted feet).
"""
import bpy
import csv
import json
import math
import os
import sys
import time

TASK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

from mathutils import Vector, Matrix

BLEND = os.path.join(TASK, "source", "Operative_rig.blend")
bpy.ops.wm.open_mainfile(filepath=BLEND)
bpy.context.scene.render.fps = 30

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, hip_pos, gait_frame,
                      gait_markers, combat_pose, relaxed_pose, stance_legs,
                      aim_arm_params, aim_forearm_matrix, support_hand_params,
                      blink_bump, breathing, dir_of, mat_cols, lerp_params,
                      R_axis, most_down_perp, DEFORM_BONES, SHAPE_KEYS, GAIT,
                      DIR_ALPHA, ANKLE_Z, THIGH_DROP, TWO_PI)
from morphrig_lib import lerp, lerp_v, smoothstep, cosine_ease, clamp, FPS, FWD, UP, RIGHT

# ---------------------------------------------------------------- inventory
REQUIRED = []
with open(os.path.join(TASK, "required_animations.csv"), newline="", encoding="utf-8") as fh:
    for i, row in enumerate(csv.DictReader(fh)):
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        dur = row["duration_seconds"]
        if dur == "pose":
            row["dur_lo"] = row["dur_hi"] = None
        else:
            a, b = dur.replace("\u2013", "-").replace("\u2014", "-").split("-")
            row["dur_lo"], row["dur_hi"] = float(a), float(b)
        row["csv_index"] = i
        REQUIRED.append(row)
REQ_BY_ID = {r["id"]: r for r in REQUIRED}
assert len(REQUIRED) == 96, len(REQUIRED)

with open(os.path.join(TASK, "source", "audio", "dialogue_alignment.json"), encoding="utf-8") as fh:
    ALIGN = json.load(fh)
assert ALIGN["fps"] == 30 and ALIGN["duration_frames"] == 408

# dash gait class: 2 m of root motion per 15-frame clip (SPEC section 8)
GAIT["dash"] = dict(n=15, stance=0.36, E=0.7714285714, lift=0.11,
                    v_app=4.2857142857, d_mid=0.90, arm_amp=30.0, elbow=34.0,
                    lean=12.0, heel=26.0, shift=0.020, yaw_sway=0.8, arc=0.02)
GAIT_TREADMILL_CM_S = {s: GAIT[s]["v_app"] * 100.0 for s in GAIT}

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
# leg IK segment lengths (head-to-head, matching solve_2bone_ik)
LEG_L1 = (rig.rest["shin_L"].to_translation() - rig.rest["thigh_L"].to_translation()).length
LEG_L2 = (rig.rest["foot_L"].to_translation() - rig.rest["shin_L"].to_translation()).length
PAIN = rig_ops.PRESETS["pain"]


# ------------------------------------------------------------------ helpers
def mat_err(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))


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


def slerp_rot(A, B, t):
    """Rotation-only slerp of two 3x3 rotation matrices."""
    if t <= 0.0:
        return A.copy().to_4x4()
    if t >= 1.0:
        return B.copy().to_4x4()
    q = A.to_quaternion().slerp(B.to_quaternion(), t)
    return q.to_matrix().to_4x4()


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
              roll=0.0, w=(1.0, 0.0, 0.0), look=(0.0, 0.0), face=None,
              pelvis_y=0.0):
    """Standing pose with explicit ankles; pelvis z rides the reachability
    ceiling so the IK legs never clamp."""
    Pp = P(pelvis__z=pelvis_z, pelvis__y=pelvis_y, pelvis__shift=shift,
           pelvis__lean=lean, pelvis__yaw=yaw, pelvis__roll=roll,
           chest__lean=chest_lean, chest__yaw=chest_yaw, look=tuple(look),
           w=tuple(w))
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


def stance_body(rig, pelvis_z=0.905, spread=0.075, lean=0.0, shift=0.0, yaw=0.0,
                chest_lean=0.0, chest_yaw=0.0, roll=0.0, w=(1.0, 0.0, 0.0),
                look=(0.0, 0.0), face=None, arm="fk", arm_kw=None):
    """Standing body with planted legs.  arm: 'fk' (combat fk_param arms),
    'hand' (combat_hand_arm, the lerp-boundary-exact hand-mode combat arm) or
    'ik' (combat_arm_ik)."""
    Pp = P(pelvis__z=pelvis_z, pelvis__shift=shift, pelvis__lean=lean,
           pelvis__yaw=yaw, pelvis__roll=roll, chest__lean=chest_lean,
           chest__yaw=chest_yaw, look=tuple(look), w=tuple(w))
    if face is not None:
        Pp["face"] = dict(face)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=spread)
    for side in ("L", "R"):
        if arm == "hand":
            Pp["arms"][side] = combat_hand_arm(rig, side, sh[side], **(arm_kw or {}))
        elif arm == "ik":
            Pp["arms"][side] = combat_arm_ik(rig, side, sh[side], **(arm_kw or {}))
        else:
            kw = dict(lift=6.0, elbow=16.0, wrist=-8.0, curl=0.18, spread=0.05)
            kw.update(arm_kw or {})
            Pp["arms"][side] = fk_arm(**kw)
    return Pp


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


def chain_error(rig, gs=1.0):
    """Worst limb-chain closure error: every arm/leg segment must keep its
    exact head-to-head length scaled by the clip's global scale (catches
    clamped IK dislocations that ik_error cannot see, e.g. an fk-hand arm
    whose forearm stops short of the hand)."""
    worst = 0.0
    for side in ("L", "R"):
        ua = rig.def_m["upper_arm_%s" % side].to_translation()
        fa = rig.def_m["forearm_%s" % side].to_translation()
        hd = rig.def_m["hand_%s" % side].to_translation()
        worst = max(worst, abs((fa - ua).length - rig.arm_L1[side] * gs))
        worst = max(worst, abs((hd - fa).length - rig.arm_L2[side] * gs))
        th = rig.def_m["thigh_%s" % side].to_translation()
        sh = rig.def_m["shin_%s" % side].to_translation()
        ft = rig.def_m["foot_%s" % side].to_translation()
        worst = max(worst, abs((sh - th).length - LEG_L1 * gs))
        worst = max(worst, abs((ft - sh).length - LEG_L2 * gs))
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


def pain_face(s, jaw=None):
    """The pain preset scaled by s (optionally overriding jaw_open)."""
    f = {k: v * s for k, v in PAIN.items()}
    if jaw is not None:
        f["jaw_open"] = jaw
    return f


def ss(x):
    """Clamped smoothstep (morphrig_lib.smoothstep is NOT clamped above 1)."""
    return smoothstep(clamp(x, 0.0, 1.0))


def blend_pinned_arm(rig, side, shoulder, M_fa_c, M_h_c, M_fa_a, M_h_a, s,
                     curl_c, curl_a, spread_c, spread_a):
    """Chain-exact arm blend between two pinned (M_fa, M_h) arm poses: the
    elbow stays exactly L1 from the shoulder and the wrist exactly L2 from
    the elbow at EVERY s (unit-vector interpolation on the sphere, not a
    matrix chord which sags off the chain), with twist-free slerp segment
    rotations.  s=0 reproduces (M_fa_c, M_h_c) exactly, s=1 reproduces
    (M_fa_a, M_h_a) exactly."""
    E_c = M_fa_c.to_translation()
    E_a = M_fa_a.to_translation()
    W_c = M_h_c.to_translation()
    W_a = M_h_a.to_translation()
    E = shoulder + (E_c - shoulder).lerp(E_a - shoulder, s).normalized() * rig.arm_L1[side]
    W = E + (W_c - E).lerp(W_a - E, s).normalized() * rig.arm_L2[side]
    R_fa = slerp_rot(M_fa_c.to_3x3(), M_fa_a.to_3x3(), s)
    R_h = slerp_rot(M_h_c.to_3x3(), M_h_a.to_3x3(), s)
    M_fa = Matrix.Translation(E) @ R_fa
    M_h = Matrix.Translation(W) @ R_h
    return fk_forearm_arm(M_fa, M_h, curl=lerp(curl_c, curl_a, s),
                          spread=lerp(spread_c, spread_a, s))


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
    """Combat <-> aim upper-body blend: s=0 combat arms, s=1 full aim.  Both
    arms are chain-exact at every s (unit-vector elbow/wrist interpolation +
    slerp segment rotations): no mode snap, no IK twist, no chord sag; at
    s=0 exactly the combat arm pose, at s=1 exactly the build_aim arm pose."""
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
        Pp["arms"][side] = blend_pinned_arm(rig, side, sh[side],
                                            M_fa_c, M_h_c, M_fa_a, M_h_a, s,
                                            0.18, curl, 0.05, 0.10)
    return Pp, info


def console_pose(rig, s, osc=Vector((0.0, 0.0, 0.0)), pelvis_z=0.905,
                 spread=0.075, look=(0.0, 0.0), face=None):
    """Both hands on an invisible console in front: s=0 combat arms, s=1
    console.  Chain-exact at every s (unit-vector elbow/wrist interpolation
    + slerp segment rotations); at s=1 the console arm exactly."""
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
        M_h_a = hand_M(palm, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
        pole = sh[side] + Vector((sgn * 0.10, -0.20, -0.40))
        # analytic IK forearm toward the console hand target (pinned)
        E0 = sh[side] + (rig.rest["forearm_%s" % side].to_translation()
                         - rig.rest["upper_arm_%s" % side].to_translation())
        W0 = sh[side] + (rig.rest["hand_%s" % side].to_translation()
                         - rig.rest["upper_arm_%s" % side].to_translation())
        E_new, T_new = rig_ops.solve_2bone_ik(sh[side], E0, W0,
                                              M_h_a.to_translation(), pole)
        M_fa_a = rig_ops.dir_pose_matrix(rig.rest["forearm_%s" % side],
                                         T_new - E_new, E_new)
        Pp["arms"][side] = blend_pinned_arm(rig, side, sh[side],
                                            M_fa_c, M_h_c, M_fa_a, M_h_a, s,
                                            0.18, 0.10, 0.05, 0.35)
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
             hand_over=None, hand_floor_z=None, plant=None):
    """Lying pose params.  arm_s lerps the arms from the floor-side limp pose
    (arm_s=0) to the requested kind (arm_s=1); leg_s folds the legs: the
    ankle stays on the floor and slides back toward the hip, so the knee
    rises UP (pole above) instead of spearing the floor.  Default pelvis_z /
    look pitch are tuned per orientation so the lowest mesh vert rests on
    the floor (face-down: belly + skull; face-up: the beacon on the back of
    the head, which hangs ~4 cm below the shoulder blades + occiput, sets
    the base 4 cm higher than the body surface alone would need).
    plant={"L": aL, "R": aR} pins the ankles to explicit world positions: the
    pelvis shifts along Y (horizontal only, floor contact unchanged) so the
    hip-to-ankle relation is preserved and the feet land exactly on the
    given ankles at leg_s=1 (zero foot slide across lying<->standing
    transitions)."""
    if lean_deg is None:
        lean_deg = 93.18 if face_down else -86.82
    if pelvis_z is None:
        pelvis_z = 0.148 if face_down else 0.2230
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
    if plant is not None:
        hip_avg_y = 0.5 * (hip_pos(rig, "L", M_pel).y + hip_pos(rig, "R", M_pel).y)
        Pp["pelvis"]["y"] = 0.5 * (plant["L"].y + plant["R"].y) \
            - (hip_avg_y + back * 0.55)
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    legs = {}
    for side in ("L", "R"):
        hip = hip_pos(rig, side, M_pel)
        if plant is not None:
            ankle = Vector((plant[side].x,
                            plant[side].y - back * 0.35 * (1.0 - leg_s),
                            ANKLE_Z))
        else:
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


# Combat-stance ankles: every lying pose plants its feet exactly here so
# transitions to/from standing never slide a foot (FIX: foot-slide).
_P_STAND = stance_body(rig, pelvis_z=0.905, spread=0.075, arm="hand")
PLANT = {"L": Vector(_P_STAND["legs"]["L"]["ankle"]),
         "R": Vector(_P_STAND["legs"]["R"]["ankle"])}


# ------------------------------------------------- dialogue gesture presets
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

# ------------------------------------------------------------- registration
SPECS = []


def spec(clip_id, form, n, gen, markers, loop=False, layer="full_body",
         entry="Any", exit_="Any", root_movement="in_place", note="",
         nominal_speed=None, treadmill=None, aim=None):
    """Register one clip spec and assert it matches required_animations.csv."""
    row = REQ_BY_ID[clip_id]
    assert row["form"] == form, (clip_id, "form", row["form"], form)
    assert row["root_movement"] == root_movement, (clip_id, "root_movement",
                                                   row["root_movement"], root_movement)
    if form == "pose":
        assert n == 2, (clip_id, "pose entries are 2 frames", n)
    else:
        d = n / 30.0
        assert row["dur_lo"] - 1e-9 <= d <= row["dur_hi"] + 1e-9, \
            (clip_id, "duration out of CSV range", d, row["dur_lo"], row["dur_hi"])
    for nm, fr, _nt in markers:
        assert 1 <= fr <= n, (clip_id, "marker frame out of range", nm, fr, n)
    SPECS.append(dict(id=clip_id, form=form, n=n, gen=gen, markers=list(markers),
                      loop=loop, layer=layer, entry=entry, exit=exit_,
                      root_movement=root_movement, note=note,
                      nominal_speed=nominal_speed, treadmill=treadmill, aim=aim,
                      csv_index=row["csv_index"], dur_text=row["duration_seconds"],
                      behavior=row["required_behavior"]))


print("gen_03: rig ready, %d required entries, arm limit %.5f m, leg %.5f m"
      % (len(REQUIRED), rig.arm_len["L"], rig.leg_len))


# ------------------------------------------------------------------ dialogue
# Lip-synced performance against source/audio/dialogue.wav (espeak-ng TTS,
# 13.5867 s = 408 frames @ 30 fps).  Visemes come from the alignment JSON
# (rig_ops.VISEMES presets, linearly crossfaded between entries); blinks,
# hand gestures and gaze are authored on the clause timeline.
CLAUSE_FRAMES = [int(round(c["start"] * 30.0)) + 1 for c in ALIGN["clauses"]]
assert CLAUSE_FRAMES == [1, 47, 105, 198, 287, 353], CLAUSE_FRAMES
BLINK_CENTERS = [36, 93, 186, 232, 276, 348, 397]
CLAUSE_GAZE = [(0.0, 0.0), (0.0, -10.0), ("sweep", 0.0), (0.0, 15.0), (0.0, -5.0), (0.0, -5.0)]
# (start frame, gesture A, gesture B, crossfade width): one crossfade per
# clause boundary; the last releases back to neutral exactly at frame 408
GEST_TIMELINE = [(1, None, 0, 12), (47, 0, 1, 12), (105, 1, 2, 12),
                 (198, 2, 3, 12), (287, 3, 4, 12), (353, 4, 5, 12),
                 (395, 5, None, 13)]


def viseme_props_at(f):
    """Face props from the alignment viseme track: the rig_ops.VISEMES preset
    of the active viseme (clamped to the first/last entry outside the track),
    linearly crossfaded across entry boundaries, plus a subtle continuous
    jaw flutter on top of the viseme jaw contour."""
    vs = ALIGN["visemes"]
    prev = nxt = None
    for v in vs:
        if v["start_frame"] <= f <= v["end_frame"]:
            prev = nxt = v
            break
        if v["end_frame"] < f:
            prev = v
        elif nxt is None:
            nxt = v
    if prev is None:
        prev = vs[0]
    if nxt is None:
        nxt = vs[-1]
    if prev is nxt:
        out = dict(rig_ops.VISEMES[prev["viseme"]])
    else:
        t = (f - prev["end_frame"]) / float(nxt["start_frame"] - prev["end_frame"])
        a = rig_ops.VISEMES[prev["viseme"]]
        b = rig_ops.VISEMES[nxt["viseme"]]
        out = {k: lerp(a.get(k, 0.0), b.get(k, 0.0), t)
               for k in set(a.keys()) | set(b.keys())}
    out["jaw_open"] = out.get("jaw_open", 0.0) \
        + 0.08 * math.sin(TWO_PI * (f - 1) / 24.0)
    return out


def dialogue_face(f):
    """Dialogue face: soft attentive base + viseme + late-clause frown +
    authored blinks."""
    face = {"squint": 0.15, "lip_close": 0.1}
    face.update(viseme_props_at(f))
    if f >= CLAUSE_FRAMES[5]:
        face["frown_L"] = 0.4
        face["frown_R"] = 0.4
    b = max(blink_bump(f, c) for c in BLINK_CENTERS)
    face["blink_L"] = b
    face["blink_R"] = b
    return face


def dialogue_gaze(f):
    """Clause-indexed gaze; clause 2 sweeps left-to-right with a slow bob."""
    ci = 0
    for i, f0 in enumerate(CLAUSE_FRAMES):
        if f >= f0:
            ci = i
    yaw, pitch = CLAUSE_GAZE[ci]
    if yaw == "sweep":
        yaw = lerp(-25.0, 25.0, ss((f - CLAUSE_FRAMES[2]) / 92.0))
        pitch = 8.0 * math.sin(TWO_PI * (f - 1) / 60.0)
    return (yaw, pitch)


def gest_at(f):
    """(gesture A index, gesture B index, crossfade s) at frame f."""
    ga, gb, s = None, 0, 1.0
    for f0, a, b, w in GEST_TIMELINE:
        if f >= f0:
            ga, gb, s = a, b, ss((f - f0) / float(w))
        else:
            break
    return ga, gb, s


def dialogue_pose(rig, f, gest_idx):
    """One side of the gesture crossfade: combat stance breathing, both arms
    in IK combat pose, the gesture arm(s) reaching to the preset."""
    dz, shift, lean_b = breathing(f, 90)
    Pp = combat_pose(rig, pelvis_z=0.905 + dz, spread=0.075, lean=lean_b)
    Pp["pelvis"]["shift"] = shift
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    for side in ("L", "R"):
        Pp["arms"][side] = combat_arm_ik(rig, side, sh[side])
    if gest_idx is not None:
        c = M_chest.to_translation()
        for side, (off, y_dir, z_dir, fkey, spread) in GESTURE_DEFS[gest_idx][1].items():
            M_h = hand_M(c + Vector(off), y_dir, z_dir)
            pole = sh[side] + Vector((0.10 if side == "R" else -0.10, -0.05, -0.40))
            Pp["arms"][side] = ik_arm(M_h.to_translation(), M_h, pole,
                                      curl=0.25, spread=spread)
            Pp["fingers"][side] = dict(FINGER_PRESETS[fkey])
    Pp["look"] = dialogue_gaze(f)
    Pp["face"] = dialogue_face(f)
    return Pp


def gen_dialogue(rig, f, n):
    ga, gb, s = gest_at(f)
    # both sides share f (identical body/face); only the arm targets differ
    return P(lerp_params(dialogue_pose(rig, f, ga), dialogue_pose(rig, f, gb), s))


DLG_MARKERS = ([("speech_start", 1, "dialogue begins"),
                ("speech_end", 408, "dialogue ends")]
               + [("clause_%d" % i, fr, "clause %d starts" % i)
                  for i, fr in enumerate(CLAUSE_FRAMES)])
spec("dialogue", "one_shot", 408, gen_dialogue, DLG_MARKERS,
     entry="Dialogue", exit_="Dialogue",
     note="Lip-synced dialogue: alignment visemes linearly interpolated, "
          "7 authored blinks, 6 hand gestures crossfaded on the clause "
          "timeline, clause-indexed gaze with a sweep during clause 2.")


# ------------------------------------------------------------------ loops
# Idle loops: breathing + weight shifts + blinks.  The stance legs are built
# from the un-leaned pelvis; the small lean/shift afterwards only re-bends
# the IK chains -- the ankle targets never move, so the feet stay planted.
def gen_idle_relaxed(rig, f, n):
    dz, shift, lean_b = breathing(f, n)
    Pp = relaxed_pose(rig, pelvis_z=0.930 + dz, spread=0.02)
    Pp["pelvis"]["shift"] = shift
    Pp["pelvis"]["lean"] = lean_b
    Pp["look"] = (6.0 * math.sin(TWO_PI * (f - 1) / float(n)),
                  3.0 * math.sin(TWO_PI * (f - 1) / (n / 2.0)))
    b = max(blink_bump(f, 35), blink_bump(f, 95))
    Pp["face"] = {"blink_L": b, "blink_R": b}
    return Pp


def gen_idle_combat(rig, f, n):
    dz, shift, lean_b = breathing(f, n)
    Pp = combat_pose(rig, 0.905 + dz, 0.075, lean_b)
    Pp["pelvis"]["shift"] = shift
    Pp["look"] = (5.0 * math.sin(TWO_PI * (f - 1) / float(n)),
                  4.0 * math.sin(TWO_PI * (f - 1) / (n / 2.0)))
    b = max(blink_bump(f, 45), blink_bump(f, 100))
    Pp["face"] = {"blink_L": b, "blink_R": b}
    return Pp


def gen_idle_wounded(rig, f, n):
    dz, shift, lean_b = breathing(f, n)
    Pp = combat_pose(rig, 0.890 + dz, 0.075, 5.0 + lean_b)
    Pp["pelvis"]["shift"] = shift
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    c = M_chest.to_translation()
    Pp["arms"]["L"] = fk_hand_arm(
        hand_M(c + Vector((-0.05, -0.06, -0.07)), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        sh["L"] + Vector((-0.10, -0.05, -0.35)), curl=0.3, spread=0.05)
    Pp["look"] = (4.0 * math.sin(TWO_PI * (f - 1) / float(n)),
                  -6.0 + 3.0 * math.sin(TWO_PI * (f - 1) / (n / 2.0)))
    b = blink_bump(f, 60)
    Pp["face"] = {"squint": 0.35, "frown_L": 0.25, "frown_R": 0.25,
                  "brow_raise": -0.3, "jaw_open": 0.10,
                  "blink_L": b, "blink_R": b}
    return Pp


spec("idle_relaxed", "loop", 120, gen_idle_relaxed, [], loop=True,
     entry="Idle", exit_="Idle",
     note="Relaxed breathing, attentive weight shifts and blinks; feet planted.")
spec("idle_combat", "loop", 120, gen_idle_combat, [], loop=True,
     entry="Combat", exit_="Combat",
     note="Combat-ready breathing stance with blinks; feet planted.")
spec("idle_wounded", "loop", 120, gen_idle_wounded, [], loop=True,
     entry="Combat", exit_="Combat",
     note="Injured combat stance: lowered pelvis, guarded left arm, pain face.")

# ---- gait loops (treadmill-authored: the stance foot moves backward relative
# to the body at v_app, so a controller moving the capsule at v_app keeps the
# world feet planted)
def make_gait_gen(speed, alpha):
    return lambda rig, f, n: gait_frame(rig, speed, alpha, f)


GAIT_NOTE = {
    "walk": "Treadmill-authored walk at 1.5 m/s apparent stance speed.",
    "run": "Treadmill-authored run at 4.0 m/s apparent stance speed.",
    "sprint": "Treadmill-authored sprint at 6.5 m/s apparent stance speed.",
}
for _d in ("f", "fl", "l", "bl", "b", "br", "r", "fr"):
    for _sp in ("walk", "run"):
        spec("%s_%s" % (_sp, _d), "loop", GAIT[_sp]["n"],
             make_gait_gen(_sp, DIR_ALPHA[_d]),
             gait_markers(_sp, DIR_ALPHA[_d]), loop=True,
             entry="Move", exit_="Move",
             nominal_speed=GAIT_TREADMILL_CM_S[_sp],
             treadmill=GAIT_TREADMILL_CM_S[_sp],
             note=GAIT_NOTE[_sp] + " Direction %s." % _d)
spec("sprint_f", "loop", GAIT["sprint"]["n"], make_gait_gen("sprint", 0.0),
     gait_markers("sprint", 0.0), loop=True, entry="Move", exit_="Move",
     nominal_speed=GAIT_TREADMILL_CM_S["sprint"],
     treadmill=GAIT_TREADMILL_CM_S["sprint"],
     note=GAIT_NOTE["sprint"] + " Direction f.")

# ---- airborne / channeling / grounded loops
def gen_jump_air(rig, f, n):
    ph = TWO_PI * (f - 1) / float(n)
    Pp = P(pelvis__z=1.08 + 0.01 * math.sin(ph), pelvis__lean=4.0,
           look=(0.0, 8.0 + 4.0 * math.sin(ph)))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = air_legs(rig, M_pel, 0.28, 0.28, 0.10, 0.10, -15.0, 25.0)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = fk_arm(lift=35.0, elbow=20.0,
                                  swing=sgn * 6.0 * math.sin(ph))
    return Pp


spec("jump_air", "loop", 15, gen_jump_air,
     [("airborne", 1, "airborne, feet tucked")],
     loop=True, entry="Jump", exit_="Jump",
     note="Airborne hang: tucked legs, slight pelvis bob; seamless loop.")


def gen_fall(rig, f, n):
    ph = TWO_PI * (f - 1) / float(n)
    Pp = P(pelvis__z=0.88 + 0.02 * math.sin(ph), pelvis__lean=-6.0,
           look=(0.0, -25.0))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = air_legs(rig, M_pel, 0.12, 0.12, 0.0, 0.0, 15.0, 0.0)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = fk_arm(lift=55.0, elbow=25.0,
                                  swing=sgn * 8.0 * math.sin(ph))
    return Pp


spec("fall", "loop", 18, gen_fall,
     [("airborne", 1, "falling, limbs flailing")],
     loop=True, entry="Fall", exit_="Fall",
     note="Controlled fall loop: flailing limbs, downward gaze; seamless loop.")


def gen_channel_loop(rig, f, n):
    Pp, info = build_aim(rig, 1.5 * math.sin(TWO_PI * (f - 1) / 36.0),
                         5.0 + 1.5 * math.sin(TWO_PI * (f - 1) / 18.0),
                         pelvis_z=0.895)
    Pp["face"] = {"squint": 0.4, "brow_raise": -0.4}
    return Pp


spec("channel_loop", "loop", 36, gen_channel_loop,
     [("beam_on", 1, "channeling, beam steady")],
     loop=True, layer="upper_body", entry="Channel", exit_="Channel",
     note="Channeling loop: steady aim with a slow sway; squinting effort face.")


def gen_charge_hold(rig, f, n):
    ph = TWO_PI * (f - 1) / 15.0
    Pp, info = build_aim(rig, 0.0, -12.0 + 1.2 * math.sin(ph),
                         pelvis_z=0.885, lean=-4.0 + 0.8 * math.sin(ph),
                         l_mode="hover")
    Pp["face"] = {"squint": 0.35, "jaw_open": 0.15}
    return Pp


spec("charge_hold", "loop", 30, gen_charge_hold,
     [("charge_full", 1, "charge held at full")],
     loop=True, layer="upper_body", entry="Charge", exit_="Charge",
     note="Charge held: steady low aim, hovering support hand, strain face.")


def gen_uplink_loop(rig, f, n):
    return console_pose(rig, 1.0,
                        osc=Vector((0.012 * math.sin(TWO_PI * (f - 1) / 45.0),
                                    0.0,
                                    0.010 * math.sin(TWO_PI * (f - 1) / 15.0))),
                        spread=0.075, look=(0.0, 0.0))


spec("uplink_loop", "loop", 45, gen_uplink_loop,
     [("uplink_sustain", 1, "uplink sustained, hands on console")],
     loop=True, layer="upper_body", entry="Uplink", exit_="Uplink",
     note="Uplink loop: both hands on the console with a slow sway; seamless.")


def gen_knockup_air(rig, f, n):
    ph = TWO_PI * (f - 1) / float(n)
    Pp = P(pelvis__z=0.95 + 0.01 * math.sin(ph), look=(0.0, 20.0))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = air_legs(rig, M_pel, 0.18, 0.18, 0.0, 0.0, 25.0, 0.0)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = fk_arm(lift=65.0, elbow=30.0,
                                  swing=sgn * 5.0 * math.sin(ph))
    Pp["face"] = {"squint": -0.3, "jaw_open": 0.3}
    return Pp


spec("knockup_air", "loop", 24, gen_knockup_air,
     [("airborne", 1, "launched upward, limbs trailing")],
     loop=True, entry="Knockup", exit_="Knockup",
     note="Knockup air loop: launched upward, arms windmilling; seamless loop.")

# ---- stunned loop (hand-mode arms match stance_body(arm='hand') so the
# stun_start/stun_end lerp boundaries are structure-exact)
def stun_body(rig, pz, shift, lean, look, face, arm_swing, arm_lift,
              w=(1.0, 0.0, 0.0), spread=0.05):
    """Stunned body: planted stance legs + hand-mode combat arms flailing."""
    Pp = P(pelvis__z=pz, pelvis__shift=shift, pelvis__lean=lean,
           look=tuple(look), w=tuple(w))
    if face is not None:
        Pp["face"] = dict(face)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=spread)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = combat_hand_arm(rig, side, sh[side],
                                           swing=sgn * arm_swing,
                                           lift=arm_lift, elbow=40.0,
                                           wrist=-20.0, curl=0.05,
                                           spread=0.05, w=w)
    return Pp


def gen_stun_loop(rig, f, n):
    ph45 = TWO_PI * (f - 1) / 45.0
    ph15 = TWO_PI * (f - 1) / 15.0
    return stun_body(rig, pz=0.872 + 0.006 * math.sin(ph45),
                     shift=0.04 * math.sin(ph45), lean=0.0,
                     look=(7.0 * math.sin(ph45), -6.0 + 4.0 * math.sin(ph15)),
                     face={"jaw_open": 0.25, "squint": 0.0},
                     arm_swing=0.0, arm_lift=2.0)


spec("stun_loop", "loop", 45, gen_stun_loop,
     [("stunned", 1, "stunned, swaying")],
     loop=True, entry="Stun", exit_="Stun",
     note="Stunned loop: swaying stance, slack jaw, lolling head; seamless loop.")

# ---- grounded loops (lying): feet planted exactly on the combat-stance
# ankles (PLANT) so transitions to/from standing never slide a foot
def gen_prone_front(rig, f, n):
    ph = TWO_PI * (f - 1) / 45.0
    Pp, info = lying_pp(rig, True, leg_s=1.0, arm_s=1.0,
                        pelvis_z=0.148 + 0.004 * math.sin(ph),
                        kind="prone_fwd", plant=PLANT)
    Pp["look"] = (10.0 * math.sin(ph), 5.0)
    b = blink_bump(f, 30)
    Pp["face"] = {"blink_L": b, "blink_R": b}
    return Pp


spec("prone_front", "loop", 45, gen_prone_front,
     [("breathing", 1, "prone, shallow breathing")],
     loop=True, entry="Prone(front)", exit_="Prone(front)",
     note="Prone loop: face-down, arms reaching forward, shallow breathing, "
          "occasional blink; feet planted on the combat-stance ankles.")


def gen_prone_back(rig, f, n):
    ph = TWO_PI * (f - 1) / 45.0
    Pp, info = lying_pp(rig, False, leg_s=1.0, arm_s=1.0,
                        pelvis_z=0.2230 + 0.004 * math.sin(ph),
                        kind="out", plant=PLANT)
    Pp["look"] = (0.0, 26.0)
    Pp["face"] = {"blink_L": 0.6, "blink_R": 0.6}
    return Pp


spec("prone_back", "loop", 45, gen_prone_back,
     [("breathing", 1, "prone, shallow breathing")],
     loop=True, entry="Prone(back)", exit_="Prone(back)",
     note="Prone loop: face-up, arms spread, eyes half closed; feet planted "
          "on the combat-stance ankles.")


def gen_sleep_loop(rig, f, n):
    ph = TWO_PI * (f - 1) / 60.0
    Pp, info = lying_pp(rig, False, leg_s=1.0, arm_s=1.0,
                        pelvis_z=0.2230 + 0.008 * math.sin(ph),
                        kind="belly", plant=PLANT)
    Pp["look"] = (0.0, 26.0)
    Pp["face"] = {"blink_L": 1.0, "blink_R": 1.0,
                  "jaw_open": 0.06 + 0.04 * math.sin(TWO_PI * (f - 1) / 20.0)}
    return Pp


spec("sleep_loop", "loop", 60, gen_sleep_loop,
     [("breathing", 1, "sleeping, slow breath")],
     loop=True, entry="Sleep", exit_="Sleep",
     note="Sleep loop: on the back, hands on the belly, eyes closed, slow "
          "breathing; feet planted on the combat-stance ankles.")


# ================================================================== one-shots
# ---- locomotion transitions: accelerate / brake -------------------------
# Pure param blends: start_f enters exactly at the combat stance and rides
# into walk frame f; stop_f enters exactly at walk frame 1 and brakes into
# exactly the combat stance.
def gen_start_f(rig, f, n):
    s = ss((f - 1) / 23.0)
    return P(lerp_params(combat_pose(rig, 0.905, 0.075),
                         gait_frame(rig, "walk", 0.0, f), s))


def gen_stop_f(rig, f, n):
    s = ss((f - 1) / 23.0)
    return P(lerp_params(gait_frame(rig, "walk", 0.0, f),
                         combat_pose(rig, 0.905, 0.075), s))


spec("start_f", "one_shot", 24, gen_start_f,
     gait_markers("walk", 0.0) + [("move_start", 1, "acceleration begins")],
     entry="Combat", exit_="Move",
     note="Acceleration from the combat stance into a forward walk: the body "
          "leans in, the arm swing fades in and the stance narrows into the "
          "gait stride.")
spec("stop_f", "one_shot", 24, gen_stop_f,
     gait_markers("walk", 0.0) + [("move_stop", 24, "brake into planted stance")],
     entry="Move", exit_="Combat",
     note="Braking from a forward walk into the planted combat stance; the "
          "stride shortens and the arm swing fades out.")


# ---- in-place turns / pivots ---------------------------------------------
def make_turn_gen(total_deg):
    return lambda rig, f, n: step_turn(rig, f, n, total_deg)


spec("turn_l90", "one_shot", 24, make_turn_gen(-90.0),
     [("pivot", 12, "halfway through the 90-degree left turn")],
     entry="Move", exit_="Move",
     note="In-place 90-degree left turn with alternating foot plants.")
spec("turn_r90", "one_shot", 24, make_turn_gen(90.0),
     [("pivot", 12, "halfway through the 90-degree right turn")],
     entry="Move", exit_="Move",
     note="In-place 90-degree right turn with alternating foot plants.")
spec("pivot_l180", "one_shot", 30, make_turn_gen(-180.0),
     [("pivot", 15, "halfway through the 180-degree left pivot")],
     entry="Move", exit_="Move",
     note="Left 180-degree moving direction change with foot re-plants.")
spec("pivot_r180", "one_shot", 30, make_turn_gen(180.0),
     [("pivot", 15, "halfway through the 180-degree right pivot")],
     entry="Move", exit_="Move",
     note="Right 180-degree moving direction change with foot re-plants.")


# ---- dashes (root motion): the root bone carries 2.0 m of travel --------
def make_dash_gen(d):
    def gen(rig, f, n):
        off = DASH_DIRS[d] * 2.0 * (f - 1) / (n - 1)
        rig.root_off = off
        Pp = gait_frame(rig, "dash", DASH_ALPHA[d], f)
        Pp["root"] = (off.x, off.z, -off.y)
        return Pp
    return gen


for _d in ("f", "b", "l", "r"):
    spec("dash_%s" % _d, "one_shot", 15, make_dash_gen(_d),
         [("dash_launch", 4, "dash leaves the ground"),
          ("dash_land", 13, "dash plants and recovers")],
         entry="Move", exit_="Move", root_movement="root_motion",
         nominal_speed=400.0, treadmill=GAIT_TREADMILL_CM_S["dash"],
         note="Ground dash %s: the root bone carries a linear 2.0 m "
              "translation along %s while the treadmill gait keeps the stance "
              "feet planted in the world; the controller/capsule must track "
              "the root bone." % (_d, _d))


# ---- teleport blink -------------------------------------------------------
def gen_blink_out(rig, f, n):
    s = ss((f - 1) / 10.0)
    Pp = combat_pose(rig, 0.905, 0.075)
    Pp["scale"] = lerp(1.0, 0.02, s)
    Pp["look"] = (0.0, lerp(0.0, 8.0, s))
    Pp["face"] = {"squint": 0.3 * s, "blink_L": 0.0, "blink_R": 0.0}
    return Pp


def gen_blink_in(rig, f, n):
    s = ss((f - 1) / 11.0)
    Pp = combat_pose(rig, 0.905, 0.075)
    Pp["scale"] = lerp(0.02, 1.0, s)
    Pp["look"] = (0.0, lerp(8.0, 0.0, s))
    Pp["face"] = {"squint": 0.3 * (1.0 - s), "blink_L": 0.0, "blink_R": 0.0}
    return Pp


spec("blink_out", "one_shot", 12, gen_blink_out,
     [("teleport", 11, "actor vanishes (event, not baked travel)")],
     entry="Any", exit_="Teleport",
     note="Anticipation and disappearance: the character squints, shrinks "
          "toward the origin and vanishes; no actor travel is baked.")
spec("blink_in", "one_shot", 12, gen_blink_in,
     [("arrive", 10, "actor reappears at the destination")],
     entry="Teleport", exit_="Combat",
     note="Reappearance: the actor grows back to full scale at the "
          "destination and settles into the combat stance.")


# ---- jump transitions -----------------------------------------------------
def jump_air_pose_at(rig, pz, lean, look, lift, elbow, swing_amp):
    """Airborne pose matching gen_jump_air's structure exactly at the
    boundary parameters (pz=1.08, lean=4, look=(0,8), lift=35, elbow=20,
    swing_amp=0 reproduces gen_jump_air(rig, 1, 15) exactly)."""
    Pp = P(pelvis__z=pz, pelvis__lean=lean, look=tuple(look))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = air_legs(rig, M_pel, 0.28, 0.28, 0.10, 0.10, -15.0, 25.0)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = fk_arm(lift=lift, elbow=elbow, swing=sgn * swing_amp)
    return Pp


def gen_jump_start(rig, f, n):
    if f <= 8:
        sc = ss((f - 1) / 7.0)
        Pp = stance_body(rig, pelvis_z=lerp(0.905, 0.78, sc), lean=12.0 * sc,
                         spread=0.0, look=(0.0, 8.0 * sc))
        for side in ("L", "R"):
            Pp["arms"][side] = fk_arm(lift=lerp(6.0, -10.0, sc))
        return Pp
    if f <= 13:
        sp = ss((f - 9) / 4.0)
        Pp = stance_body(rig, pelvis_z=lerp(0.78, 0.93, sp),
                         lean=lerp(12.0, 2.0, sp), spread=0.0,
                         look=(0.0, lerp(8.0, 0.0, sp)))
        for side in ("L", "R"):
            Pp["arms"][side] = fk_arm(lift=lerp(-10.0, 30.0, sp))
        return Pp
    st = ss((f - 14) / 4.0)
    P_plant = stance_body(rig, pelvis_z=lerp(0.93, 1.08, st),
                          lean=lerp(2.0, 4.0, st), spread=0.0, look=(0.0, 0.0))
    for side in ("L", "R"):
        P_plant["arms"][side] = fk_arm(lift=30.0)
    return P(lerp_params(P_plant, gen_jump_air(rig, 1, 15), st))


def gen_jump_land(rig, f, n):
    if f <= 7:
        sf = ss((f - 1) / 6.0)
        return jump_air_pose_at(rig, lerp(1.08, 0.93, sf), lerp(4.0, 2.0, sf),
                                (0.0, lerp(8.0, -10.0, sf)),
                                lerp(35.0, 25.0, sf), 20.0, 4.0 * sf)
    if f <= 12:
        si = ss((f - 8) / 4.0)
        pz = lerp(0.93, 0.76, si)
        P_air = jump_air_pose_at(rig, pz, 2.0, (0.0, -10.0), 25.0, 20.0, 4.0)
        P_st = stance_body(rig, pelvis_z=pz, lean=2.0, spread=0.075,
                           look=(0.0, -10.0))
        return P(lerp_params(P_air, P_st, si))
    sr = ss((f - 13) / 5.0)
    P_st = stance_body(rig, pelvis_z=0.76, lean=2.0, spread=0.075,
                       look=(0.0, -10.0))
    return P(lerp_params(P_st, combat_pose(rig, 0.905, 0.075), sr))


spec("jump_start", "one_shot", 18, gen_jump_start,
     [("takeoff", 18, "feet leave the ground")],
     entry="Combat", exit_="Jump",
     note="Visible anticipation (crouch, arms back) and takeoff; the exit "
          "pose is exactly jump_air frame 1.")
spec("jump_land", "one_shot", 18, gen_jump_land,
     [("land", 8, "feet touch down")],
     entry="Jump", exit_="Combat",
     note="Soft landing: airborne descent, compression on contact and a "
          "recovery into the combat stance; the entry pose is exactly "
          "jump_air frame 1.")


def gen_land_heavy(rig, f, n):
    P_h = P(pelvis__z=0.905)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, P_h)
    hL = hip_pos(rig, "L", M_pel)
    hR = hip_pos(rig, "R", M_pel)
    aL = Vector((hL.x, hL.y - 0.15, ANKLE_Z))
    aR = Vector((hR.x, hR.y + 0.10, ANKLE_Z))
    if f <= 7:
        sf = ss((f - 1) / 6.0)
        Pp = P(pelvis__z=lerp(0.90, 0.88, sf), pelvis__lean=-6.0,
               look=(0.0, -25.0))
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        Pp["legs"] = air_legs(rig, M_pel, 0.12, 0.12, 0.0, 0.0, 15.0, 0.0)
        for side in ("L", "R"):
            Pp["arms"][side] = fk_arm(lift=55.0, elbow=25.0)
        return Pp
    if f <= 13:
        si = ss((f - 8) / 5.0)
        amp = 90.0 * ss((f - 8) / 5.0)
        Pp, M_pel, M_chest, M_spine03, sh = stance_at(
            rig, aL, aR, pelvis_z=lerp(0.90, 0.72, si), d_mid=0.98,
            look=(0.0, -25.0))
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            Pp["arms"][side] = fk_arm(
                swing=sgn * amp * math.sin(TWO_PI * (f - 1) / 21.0),
                lift=lerp(55.0, 40.0, si), elbow=25.0)
        return Pp
    sr = ss((f - 14) / 7.0)
    amp = 90.0 * (1.0 - ss((f - 14) / 7.0))
    aLf = lerp_v(aL, PLANT["L"], sr)
    aRf = lerp_v(aR, PLANT["R"], sr)
    Pp, M_pel, M_chest, M_spine03, sh = stance_at(
        rig, aLf, aRf, pelvis_z=lerp(0.72, 0.905, sr), d_mid=0.98,
        look=(0.0, lerp(-25.0, 0.0, sr)))
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = fk_arm(
            swing=sgn * amp * math.sin(TWO_PI * (f - 1) / 21.0),
            lift=lerp(40.0, 6.0, sr), elbow=lerp(25.0, 16.0, sr))
    return Pp


spec("land_heavy", "one_shot", 21, gen_land_heavy,
     [("impact", 8, "hard contact with the ground")],
     entry="Fall", exit_="Combat",
     note="Hard landing: staggered foot plant, deep weight-forward compression "
          "with flailing arms, then recovery into the combat stance.")


# ---- melee ----------------------------------------------------------------
def gen_melee_1(rig, f, n):
    if f <= 10:
        s = ss((f - 1) / 9.0)
        swing = lerp(0.0, 48.0, s)
        lift = lerp(6.0, 55.0, s)
        wrist = lerp(-8.0, -32.0, s)
        cyaw = lerp(0.0, -18.0, s)
        shift = 0.0
    elif f <= 17:
        s = ss((f - 11) / 6.0)
        swing = lerp(48.0, -58.0, s)
        lift = lerp(55.0, 22.0, s)
        wrist = lerp(-32.0, 18.0, s)
        cyaw = lerp(-18.0, 26.0, s)
        shift = 0.04 * math.sin(math.pi * s)
    else:
        s = ss((f - 18) / 9.0)
        swing = lerp(-58.0, 0.0, s)
        lift = lerp(22.0, 6.0, s)
        wrist = lerp(18.0, -8.0, s)
        cyaw = lerp(26.0, 0.0, s)
        shift = 0.04 * math.sin(math.pi * s)
    Pp = stance_body(rig, pelvis_z=0.905, spread=0.075, chest_yaw=cyaw,
                     shift=shift)
    Pp["arms"]["R"] = fk_arm(swing=swing, lift=lift, wrist=wrist, w=(0.0, 0.0, 1.0))
    if 11 <= f <= 19:
        Pp["face"] = dict(rig_ops.PRESETS["focus"])
    return Pp


def gen_melee_2(rig, f, n):
    if f <= 10:
        s = ss((f - 1) / 9.0)
        swing = lerp(0.0, -45.0, s)
        lift = lerp(6.0, 20.0, s)
        elbow = lerp(16.0, 55.0, s)
        wrist = lerp(-8.0, 25.0, s)
        cyaw = lerp(0.0, 18.0, s)
        shift = 0.0
    elif f <= 17:
        s = ss((f - 11) / 6.0)
        swing = lerp(-45.0, 55.0, s)
        lift = lerp(20.0, 58.0, s)
        elbow = lerp(55.0, 25.0, s)
        wrist = lerp(25.0, -30.0, s)
        cyaw = lerp(18.0, -26.0, s)
        shift = -0.04 * math.sin(math.pi * s)
    else:
        s = ss((f - 18) / 9.0)
        swing = lerp(55.0, 0.0, s)
        lift = lerp(58.0, 6.0, s)
        elbow = lerp(25.0, 16.0, s)
        wrist = lerp(-30.0, -8.0, s)
        cyaw = lerp(-26.0, 0.0, s)
        shift = -0.04 * math.sin(math.pi * s)
    Pp = stance_body(rig, pelvis_z=0.905, spread=0.075, chest_yaw=cyaw,
                     shift=shift)
    Pp["arms"]["R"] = fk_arm(swing=swing, lift=lift, elbow=elbow, wrist=wrist,
                             w=(0.0, 0.0, 1.0))
    if 11 <= f <= 19:
        Pp["face"] = dict(rig_ops.PRESETS["focus"])
    return Pp


MELEE3_PATH = [(1, Vector((0.295, -0.082, 0.745))),
               (12, Vector((0.02, -0.28, 1.62))),
               (18, Vector((0.00, -0.34, 1.00))),
               (23, Vector((-0.03, -0.35, 0.97))),
               (33, Vector((0.295, -0.082, 0.745)))]
_M3_POLE_RAISE = Vector((0.0, 0.15, -0.55))   # elbow below the wrist: blade up
_M3_POLE_CHOP = Vector((-0.05, 0.30, 0.35))   # elbow above/behind: blade down-fwd


def melee3_pole(f, W, elbow_c):
    """R-arm elbow hint (world): exactly the combat elbow at the guard frames
    (entry/exit are the combat pose), blending to a fixed offset below the
    wrist while the blade is raised, above/behind it through the chop and
    follow-through."""
    if f <= 1 or f >= 33:
        return elbow_c
    if f <= 12:
        s = ss((f - 1) / 11.0)
        return elbow_c + ((W + _M3_POLE_RAISE) - elbow_c) * s
    if f <= 23:
        return W + _M3_POLE_CHOP
    s3 = ss((f - 23) / 10.0)
    base = W + _M3_POLE_CHOP
    return base + (elbow_c - base) * s3


def melee3_u(f):
    """L-hand grip distance along the R forearm axis from the R elbow.  The
    hand head rides the axis and its palm sits 0.06 further along, wrapping
    the forearm: the blade mesh spans 0.20-0.25 along the forearm (a short
    spike on top near the wrist) and the R wrist is at 0.30, so the grip
    stays ON the forearm.  Raised: the palm is on the blade; through the
    chop it slides toward the guard (the wrist) as the blade descends."""
    if f <= 12:
        return 0.16
    if f <= 18:
        return lerp(0.16, 0.21, ss((f - 12) / 6.0))
    return 0.21


def melee3_r_arm(rig, sh, W, pole_R):
    """R arm with the wrist on the blade path: the analytic 2-bone solve
    matches what build_arm's fk-hand solve produces (chain-exact).  The hand
    keeps its rest rotation relative to the forearm (no wrist articulation),
    so at the guard frames the arm hangs exactly like the combat arm.  The
    forearm frame is returned so the L grip can be built on the blade."""
    E0 = sh["R"] + (rig.rest["forearm_R"].to_translation()
                    - rig.rest["upper_arm_R"].to_translation())
    W0 = sh["R"] + (rig.rest["hand_R"].to_translation()
                    - rig.rest["upper_arm_R"].to_translation())
    E_new, T_new = rig_ops.solve_2bone_ik(sh["R"], E0, W0, W, pole_R)
    M_fa_R = rig_ops.dir_pose_matrix(rig.rest["forearm_R"], T_new - E_new, E_new)
    M_h_R = Matrix.Translation(W) \
        @ (M_fa_R @ rig.rl["hand_R"]).to_3x3().to_4x4()
    return fk_hand_arm(M_h_R, pole_R, curl=0.25, spread=0.10), M_fa_R


def gen_melee_3(rig, f, n):
    if f <= 12:
        s = ss((f - 1) / 11.0)
        shift = 0.03 * math.sin(math.pi * s)
        cyaw = lerp(0.0, 8.0, s)
    elif f <= 18:
        shift = 0.0
        cyaw = 8.0
    else:
        s3 = ss((f - 18) / 15.0)
        shift = 0.0
        cyaw = lerp(8.0, 0.0, s3)
    Pp = stance_body(rig, pelvis_z=0.905, spread=0.075, chest_yaw=cyaw,
                     shift=shift)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    _, M_fa_c_L, M_h_c_L = combat_hand_matrices(rig, "L", sh["L"])
    _, M_fa_c_R, M_h_c_R = combat_hand_matrices(rig, "R", sh["R"])
    W = eval_vec(MELEE3_PATH, float(f))
    pole_R = melee3_pole(f, W, M_fa_c_R.to_translation())
    pole_L = sh["L"] + Vector((-0.15, -0.05, -0.45))
    armR, M_fa_R = melee3_r_arm(rig, sh, W, pole_R)
    dir_R = M_fa_R.to_3x3() @ Vector((0.0, 1.0, 0.0))
    M_grip = Matrix.Translation(M_fa_R.to_translation() + dir_R * melee3_u(f)) \
        @ M_fa_R.to_3x3().to_4x4()
    if f <= 12:
        M_h_L = rig_ops.lerp_matrices(M_h_c_L, M_grip, s)
    elif f <= 23:
        M_h_L = M_grip
    else:
        M_h_L = rig_ops.lerp_matrices(M_grip, M_h_c_L, ss((f - 23) / 5.0))
    Pp["arms"]["L"] = fk_hand_arm(M_h_L, pole_L, curl=0.25, spread=0.10)
    Pp["arms"]["R"] = armR
    if 12 < f <= 22:
        Pp["face"] = dict(rig_ops.PRESETS["focus"])
    return Pp


spec("melee_1", "one_shot", 27, gen_melee_1,
     [("hit_start", 11, "slash hit window opens"),
      ("hit_end", 15, "slash hit window closes")],
     entry="Combat", exit_="Combat",
     note="Diagonal forearm-blade slash: wind-up, horizontal sweep with a "
          "weight shift, and recovery; hit window marked.")
spec("melee_2", "one_shot", 27, gen_melee_2,
     [("hit_start", 11, "reverse slash hit window opens"),
      ("hit_end", 15, "reverse slash hit window closes")],
     entry="Combat", exit_="Combat",
     note="Reverse slash: a different preparation (low elbow cock) and an "
          "opposite weight shift; hit window marked.")
spec("melee_3", "one_shot", 33, gen_melee_3,
     [("hit_start", 13, "finisher chop hit window opens"),
      ("hit_end", 16, "finisher chop hit window closes")],
     entry="Combat", exit_="Combat",
     note="Committed two-handed finisher: both hands close on the raised "
          "blade, a downward chop in front of the body while the support "
          "hand slides down the blade toward the guard, a low "
          "follow-through, and recovery to guard.")


# ---- ranged (upper-body layer over locomotion) ----------------------------
def ranged_pose(rig, pitch, rec):
    """Aim pose with recoil: the R forearm keeps its aim rotation but slides
    back along the aim direction by rec (rec=0 is exactly build_aim); the L
    hand re-grips the recoiled forearm."""
    Pp, info = build_aim(rig, 0.0, pitch, pelvis_z=0.905, spread=0.075)
    M_fa_R = info["M_fa_R"]
    d = info["d"]
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    elbow_rec = sh["R"] + (M_fa_R.to_translation() - d * rec
                           - sh["R"]).normalized() * rig.arm_L1["R"]
    M_fa_rec = Matrix.Translation(elbow_rec) @ M_fa_R.to_3x3().to_4x4()
    M_h_rec = M_fa_rec @ rig.rl["hand_R"]
    Pp["arms"]["R"] = fk_forearm_arm(M_fa_rec, M_h_rec, curl=0.25, spread=0.10)
    fa_R = M_fa_rec.to_3x3()
    grip_pt = M_fa_rec @ Vector((0.0, 0.23, 0.0))
    y_fa = fa_R @ Vector((0.0, 1.0, 0.0))
    z_fa = fa_R @ Vector((0.0, 0.0, 1.0))
    grip_M = Matrix.Translation(grip_pt - 0.06 * y_fa - 0.047 * z_fa) \
        @ fa_R.to_4x4()
    armL = support_hand_params(rig, grip_M, curl=0.25)
    armL["pole"] = tuple(sh["L"] + Vector((-0.15, -0.05, -0.45)))
    armL["spread"] = 0.10
    Pp["arms"]["L"] = armL
    return Pp


def ranged_rec_fire(f):
    if f <= 1:
        return -0.008
    if f <= 6:
        return 0.06 * ss((f - 2) / 4.0)
    return 0.06 * (1.0 - ss((f - 6) / 6.0))


def ranged_rec_burst(f):
    rec = 0.0
    for s in (5, 11, 17):
        rec += 0.05 * math.sin(math.pi * clamp((f - s) / 3.0, 0.0, 1.0)) ** 2
    return rec


def gen_ranged_fire(rig, f, n):
    return ranged_pose(rig, 0.0, ranged_rec_fire(f))


def gen_ranged_burst(rig, f, n):
    t = (f - 1) / 20.0
    return ranged_pose(rig, 3.0 * math.sin(math.pi * t), ranged_rec_burst(f))


spec("ranged_fire", "one_shot", 12, gen_ranged_fire,
     [("muzzle", 2, "single shot fires from the wrist emitter")],
     layer="upper_body", entry="Combat", exit_="Combat",
     note="Wrist-emitter single shot: recoil kicks the pinned forearm back "
          "along the aim line and recovers; upper-body layer.")
spec("ranged_burst", "one_shot", 21, gen_ranged_burst,
     [("muzzle", 5, "burst shot 1"), ("muzzle", 11, "burst shot 2"),
      ("muzzle", 17, "burst shot 3")],
     layer="upper_body", entry="Combat", exit_="Combat",
     note="Three-shot burst with three distinct muzzle events, a small aim "
          "wobble and one recoil bump per shot; upper-body layer.")


# ---- reload (upper-body) ---------------------------------------------------
# Ridden-rest prop frames: the props ride the posed pelvis, so their rest
# world frames are taken from the combat-posed pelvis (not bind rest) and
# every hand-over of a prop is seamless.
#
# Reload v2: the FIRING (R) hand performs the whole swap -- the L hand cannot
# reach the emitter seat (0.700 m, over the 0.611 m arm limit) and the R hand
# cannot fetch from the holster (0.624 m).  The R hand lowers the wrist
# emitter to a work pin, ejects the spent cell and pouches it, takes the new
# cell from the L hand at a front handoff, seats it in the emitter and
# returns to aim.  A seated cell rides the emitter's POSED frame (computed
# analytically per frame), so it is exactly in the emitter at every frame.
#
# The R grip on a cell is derived from the SEAT, not from an arbitrary pose:
# CELL_GRIP_R is the hand's rest world pose relative to the seat frame, i.e.
# the hand hanging on the forearm at its rest local transform (head exactly
# one forearm length L2 along the axis, forearm-relative rest rotation) --
# the natural "holding the emitter" pose (the cell is mounted on the
# forearm before the wrist, so a chain-closing grip must sit at the wrist
# sphere).  For ANY forearm pose, a hand built that way (melee3-style: head
# at the wrist, forearm-relative rest rotation) then grips the seated cell
# EXACTLY:
#   hand == (M_fa @ rl_emitter @ CELL_SEAT_LOCAL) @ CELL_GRIP_R
# because the seated cell is the seat frame carried by the forearm's motion
# from rest (seated_cell == M_fa @ rest_forearm^-1 @ CELL_SEAT_WORLD) and
# CELL_GRIP_R == CELL_SEAT_WORLD^-1 @ rest_hand_R.  The work pin below
# therefore needs no fixed-point iteration: solve the work wrist, build the
# hand melee3-style, and the grip is exact by construction.
_P_RELOAD = combat_pose(rig, 0.905, 0.075)
_M_PEL_RELOAD = body_matrices(rig, _P_RELOAD)[1]
CELL_REST_WORLD = _M_PEL_RELOAD @ PROP_OFF["cell_new"]
SPENT_REST_WORLD = _M_PEL_RELOAD @ PROP_OFF["cell_spent"]
SEAT_M = CELL_SEAT_WORLD
HOLSTER_GRIP = hand_M(Vector((-0.227, 0.022, 0.945)), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
CELL_GRIP_L = CELL_REST_WORLD.inverted() @ HOLSTER_GRIP
CELL_GRIP_R = CELL_SEAT_WORLD.inverted() @ rig.rest["hand_R"]
POUCH_HOVER = Matrix.Translation((0.0, 0.0, 0.10)) @ SPENT_REST_WORLD
M_h_pouch = POUCH_HOVER @ CELL_GRIP_R
_P_AIM0, _INFO_AIM0 = build_aim(rig, 0.0, 0.0, pelvis_z=0.905, spread=0.075)
_M_fa_R0 = _INFO_AIM0["M_fa_R"]
_y_fa0 = _M_fa_R0.to_3x3() @ Vector((0.0, 1.0, 0.0))
_z_fa0 = _M_fa_R0.to_3x3() @ Vector((0.0, 0.0, 1.0))
M_grip_L_support = Matrix.Translation(
    _M_fa_R0 @ Vector((0.0, 0.23, 0.0)) - 0.06 * _y_fa0 - 0.047 * _z_fa0) \
    @ _M_fa_R0.to_3x3().to_4x4()
M_h_rigid = _M_fa_R0 @ rig.rl["hand_R"]


def _reload_emitter(sh_R, M_h_R):
    """The emitter prop frame exactly as the posed R forearm carries it
    (mirrors build_arm's fk-hand branch: 2-bone IK to the hand pin with the
    pole at the aim elbow)."""
    E0 = sh_R + (rig.rest["forearm_R"].to_translation()
                 - rig.rest["upper_arm_R"].to_translation())
    W0 = sh_R + (rig.rest["hand_R"].to_translation()
                 - rig.rest["upper_arm_R"].to_translation())
    E_new, T_new = rig_ops.solve_2bone_ik(sh_R, E0, W0,
                                          M_h_R.to_translation(),
                                          _M_fa_R0.to_translation())
    M_fa = rig_ops.dir_pose_matrix(rig.rest["forearm_R"], T_new - E_new, E_new)
    return M_fa @ rig.rl["emitter"]


# R-hand work pin: the wrist lowered to the seat point; the hand is built
# melee3-style (head at the wrist, forearm-relative rest rotation), so it
# grips the cell seated in the posed emitter exactly (see the note above).
_sh_R0 = body_matrices(rig, _P_RELOAD)[4]["R"]
_E0 = _sh_R0 + (rig.rest["forearm_R"].to_translation()
                - rig.rest["upper_arm_R"].to_translation())
_W0 = _sh_R0 + (rig.rest["hand_R"].to_translation()
                - rig.rest["upper_arm_R"].to_translation())
_E_new, _T_new = rig_ops.solve_2bone_ik(_sh_R0, _E0, _W0,
                                        SEAT_M.to_translation(),
                                        _M_fa_R0.to_translation())
_M_fa_work = rig_ops.dir_pose_matrix(rig.rest["forearm_R"],
                                     _T_new - _E_new, _E_new)
M_h_work = Matrix.Translation(_T_new) \
    @ (_M_fa_work @ rig.rl["hand_R"]).to_3x3().to_4x4()

# Front handoff: the L hand presents the new cell at (0, -0.15, 1.0); both
# hands grip the SAME cell frame there, so the transfer L -> R is seamless.
CELL_HANDOFF = Matrix.Translation(
    Vector((0.0, -0.15, 1.00)) - CELL_REST_WORLD.to_translation()) \
    @ CELL_REST_WORLD
M_h_L_handoff = CELL_HANDOFF @ CELL_GRIP_L
M_h_R_handoff = M_h_L_handoff @ CELL_GRIP_L.inverted() @ CELL_GRIP_R


def gen_reload(rig, f, n):
    Pp = combat_pose(rig, 0.905, 0.075)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    # L (support) hand: support grip -> holster fetch -> front handoff
    # -> back to the support grip
    if f <= 8:
        M_h_L = M_grip_L_support
        curl_L = 0.25
    elif f <= 14:
        s = ss((f - 8) / 6.0)
        M_h_L = rig_ops.lerp_matrices(M_grip_L_support, HOLSTER_GRIP, s)
        curl_L = lerp(0.25, 0.55, s)
    elif f <= 19:
        M_h_L = HOLSTER_GRIP
        curl_L = 0.55
    elif f <= 26:
        M_h_L = rig_ops.lerp_matrices(HOLSTER_GRIP, M_h_L_handoff,
                                      ss((f - 19) / 7.0))
        curl_L = 0.55
    elif f <= 38:
        M_h_L = M_h_L_handoff
        curl_L = 0.55
    elif f <= 56:
        s = ss((f - 38) / 18.0)
        M_h_L = rig_ops.lerp_matrices(M_h_L_handoff, M_grip_L_support, s)
        curl_L = lerp(0.55, 0.25, min(1.0, 4.0 * s))
    else:
        M_h_L = M_grip_L_support
        curl_L = 0.25
    Pp["arms"]["L"] = ik_arm(M_h_L.to_translation(), M_h_L,
                             sh["L"] + Vector((-0.15, -0.05, -0.45)),
                             curl=curl_L, spread=0.10)
    # R (firing) hand: aim -> lower to the work pin -> eject and pouch the
    # spent cell -> take the new cell at the handoff -> seat it -> back to aim
    if f <= 8:
        M_h_R = M_h_rigid
        curl_R = 0.25
    elif f <= 14:
        M_h_R = rig_ops.lerp_matrices(M_h_rigid, M_h_work, ss((f - 8) / 6.0))
        curl_R = 0.25
    elif f <= 23:
        M_h_R = M_h_work
        curl_R = lerp(0.25, 0.40, ss((f - 14) / 9.0))
    elif f <= 30:
        M_h_R = rig_ops.lerp_matrices(M_h_work, M_h_pouch, ss((f - 23) / 7.0))
        curl_R = 0.40
    elif f <= 38:
        M_h_R = rig_ops.lerp_matrices(M_h_pouch, M_h_R_handoff,
                                      ss((f - 30) / 8.0))
        curl_R = lerp(0.40, 0.25, ss((f - 30) / 4.0))
    elif f <= 45:
        M_h_R = rig_ops.lerp_matrices(M_h_R_handoff, M_h_work,
                                      ss((f - 38) / 7.0))
        curl_R = lerp(0.25, 0.40, ss((f - 38) / 2.0))
    else:
        M_h_R = rig_ops.lerp_matrices(M_h_work, M_h_rigid, ss((f - 46) / 10.0))
        curl_R = lerp(0.40, 0.25, ss((f - 46) / 5.0))
    Pp["arms"]["R"] = fk_hand_arm(M_h_R, _M_fa_R0.to_translation(),
                                  curl=curl_R, spread=0.10)
    # props: both cells ride the emitter or a hand exactly at every hand-over
    M_em = _reload_emitter(sh["R"], M_h_R)
    if f <= 23:
        Pp["def"]["cell_spent"] = M_em @ CELL_SEAT_LOCAL
    elif f <= 29:
        Pp["def"]["cell_spent"] = M_h_R @ CELL_GRIP_R.inverted()
    elif f <= 33:
        Pp["def"]["cell_spent"] = rig_ops.lerp_matrices(
            M_h_pouch @ CELL_GRIP_R.inverted(), SPENT_REST_WORLD,
            ss((f - 30) / 3.0))
    else:
        Pp["def"]["cell_spent"] = SPENT_REST_WORLD
    if f <= 19:
        Pp["def"]["cell_new"] = CELL_REST_WORLD
    elif f <= 37:
        Pp["def"]["cell_new"] = M_h_L @ CELL_GRIP_L.inverted()
    elif f <= 45:
        Pp["def"]["cell_new"] = M_h_R @ CELL_GRIP_R.inverted()
    else:
        Pp["def"]["cell_new"] = M_em @ CELL_SEAT_LOCAL
    return Pp


spec("reload", "one_shot", 60, gen_reload,
     [("reload_start", 1, "reload begins"),
      ("cell_out", 20, "new cell leaves the holster"),
      ("cell_spent_out", 24, "spent cell ejected from the emitter"),
      ("cell_spent_pouched", 34, "spent cell settled in the pouch"),
      ("cell_seated", 46, "new cell seated at the emitter"),
      ("reload_end", 60, "reload complete")],
     layer="upper_body", entry="Aim", exit_="Aim",
     note="Physical emitter-cell reload while aiming: the firing hand lowers "
          "the wrist emitter, ejects and pouches the spent cell, takes the "
          "new cell from the support hand at a front handoff and seats it in "
          "the emitter; both cells ride the emitter or a hand exactly at "
          "every hand-over.")


# ---- casts (upper-body) ----------------------------------------------------
def gen_cast_directional(rig, f, n):
    s = ss((f - 1) / 17.0)
    yaw = lerp(-40.0, 40.0, s)
    Pp, info = build_aim(rig, yaw, lerp(0.0, 10.0, s),
                         grip_dist=lerp(0.23, 0.30, s))
    Pp["look"] = (yaw, 0.0)
    Pp["face"] = {"squint": 0.4}
    return Pp


def gen_cast_ground(rig, f, n):
    Pp = build_aim(rig, 0.0, lerp(0.0, -25.0, ss((f - 1) / 29.0)),
                   lean=6.0 * math.sin(math.pi * min((f - 1) / 21.0, 1.0)))[0]
    Pp["look"] = (0.0, lerp(0.0, -45.0, ss((f - 1) / 21.0)))
    return Pp


def gen_cast_self(rig, f, n):
    Pp = build_aim(rig, 0.0, lerp(0.0, 8.0, ss((f - 1) / 23.0)),
                   l_mode="grip")[0]
    Pp["face"] = {"squint": 0.5, "smile_L": 0.3, "smile_R": 0.3,
                  "cheek_L": 0.4, "cheek_R": 0.4}
    return Pp


spec("cast_directional", "one_shot", 18, gen_cast_directional,
     [("cast_release", 15, "direction-targeted release")],
     layer="upper_body", entry="Combat", exit_="Combat",
     note="Direction-targeted cast: the aim sweeps from left to right while "
          "rising, with the gaze tracking the aim direction.")
spec("cast_ground", "one_shot", 30, gen_cast_ground,
     [("cast_release", 22, "ground-targeted placement")],
     layer="upper_body", entry="Combat", exit_="Combat",
     note="Ground-targeted cast: the aim drops to the ground with a "
          "weight-forward lean and a downward gaze.")
spec("cast_self", "one_shot", 24, gen_cast_self,
     [("cast_release", 16, "self-centered emission")],
     layer="upper_body", entry="Combat", exit_="Combat",
     note="Self-centered defensive cast: the aim rises toward the caster "
          "with a confident expression.")


# ---- channeling (upper-body) ------------------------------------------------
def gen_channel_start(rig, f, n):
    s = ss((f - 1) / 17.0)
    Pp = aim_pose_blend(rig, s, 0.0, lerp(2.0, 5.0, s),
                        pelvis_z=lerp(0.905, 0.895, s))[0]
    Pp["face"] = {"squint": 0.4 * s, "brow_raise": -0.4 * s,
                  "jaw_open": 0.25 * s}
    return Pp


def gen_channel_end(rig, f, n):
    t = ss((f - 1) / 17.0)
    if t < 0.55:
        pitch = lerp(5.0, -22.0, clamp(t / 0.55, 0.0, 1.0))
    else:
        pitch = lerp(-22.0, 3.0, ss((t - 0.55) / 0.45))
    Pp = aim_pose_blend(rig, 1.0 - t, 0.0, pitch, pelvis_z=0.895)[0]
    Pp["face"] = {"squint": 0.4 * (1.0 - t), "brow_raise": -0.4 * (1.0 - t)}
    return Pp


def gen_channel_interrupt(rig, f, n):
    t = ss((f - 1) / 14.0)
    jerk = math.sin(math.pi * t)
    s = 1.0 if t < 0.5 else 1.0 - ss((t - 0.5) / 0.5)
    Pp = aim_pose_blend(rig, s, -20.0 * jerk, 5.0 + 13.0 * jerk,
                        pelvis_z=0.895)[0]
    Pp["face"] = {"squint": 0.6, "jaw_open": 0.3}
    return Pp


spec("channel_start", "one_shot", 18, gen_channel_start,
     [("channel_begin", 18, "channel pose established")],
     layer="upper_body", entry="Combat", exit_="Channel",
     note="Enter the sustainable channel pose: the aim rises from combat "
          "with a strain face; the exit pose is exactly channel_loop "
          "frame 1.")
spec("channel_end", "one_shot", 18, gen_channel_end,
     [("channel_release", 10, "deliberate successful release")],
     layer="upper_body", entry="Channel", exit_="Combat",
     note="Deliberate successful channel release: the beam aim dips and "
          "returns to combat; the entry pose is exactly channel_loop "
          "frame 1.")
spec("channel_interrupt", "one_shot", 15, gen_channel_interrupt,
     [("interrupt", 5, "forced interruption")],
     layer="upper_body", entry="Channel", exit_="Combat",
     note="Forced channel interruption: the aim jerks aside and collapses "
          "back to combat, distinct from the deliberate completion.")


# ---- charge (upper-body) ----------------------------------------------------
def gen_charge_start(rig, f, n):
    s = ss((f - 1) / 20.0)
    Pp = aim_pose_blend(rig, s, 0.0, lerp(2.0, -12.0, s),
                        pelvis_z=lerp(0.905, 0.885, s), lean=lerp(0.0, -4.0, s),
                        l_mode="hover")[0]
    Pp["face"] = {"squint": 0.35 * s, "jaw_open": 0.15 * s}
    return Pp


def gen_charge_release(rig, f, n):
    t = ss((f - 1) / 20.0)
    if t < 0.45:
        sp = clamp(t / 0.45, 0.0, 1.0)
        pitch = lerp(-12.0, 8.0, sp)
        lean = lerp(-4.0, 14.0, sp)
        shift = lerp(0.0, -0.09, sp)
        s = 1.0
    else:
        sp2 = ss((t - 0.45) / 0.55)
        pitch = 8.0
        lean = 14.0
        shift = -0.09
        s = 1.0 - sp2
    Pp, info = aim_pose_blend(rig, s, 0.0, pitch, pelvis_z=0.885, lean=lean,
                              shift=shift, l_mode="hover", w=(1.0, 0.0, 0.0))
    M_pel = body_matrices(rig, Pp)[1]
    Pp["legs"] = planted(rig, M_pel, (PLANT["L"], PLANT["R"]))
    Pp["face"] = {"squint": 0.35 * s, "jaw_open": 0.15 * s}
    return Pp


def gen_charge_cancel(rig, f, n):
    s = 1.0 - ss((f - 1) / 14.0)
    Pp = aim_pose_blend(rig, s, 0.0, -10.0, pelvis_z=0.885,
                        l_mode="hover")[0]
    Pp["face"] = {"squint": 0.35 * s, "jaw_open": 0.15 * s}
    return Pp


spec("charge_start", "one_shot", 21, gen_charge_start,
     [("charge_begin", 21, "charge established")],
     layer="upper_body", entry="Combat", exit_="Charge",
     note="Wind up and accumulate energy: the aim drops to the charge pose "
          "with a hovering support hand; the exit pose is exactly "
          "charge_hold frame 1.")
spec("charge_release", "one_shot", 21, gen_charge_release,
     [("release", 12, "forceful release")],
     layer="upper_body", entry="Charge", exit_="Combat",
     note="Forceful release with weight transfer: the aim swings up and the "
          "weight shifts back onto the planted feet; the entry pose is "
          "exactly charge_hold frame 1.")
spec("charge_cancel", "one_shot", 15, gen_charge_cancel,
     [("cancel", 15, "charge safely canceled")],
     layer="upper_body", entry="Charge", exit_="Combat",
     note="Safely cancel the stored charge: the aim relaxes back to "
          "combat.")


# ---- deploy (full body: crouches to place a beacon) ------------------------
BEACON_GRIP = rig.rest["beacon"].inverted() @ hand_M((0.0, 0.215, 1.382),
                                                    (0.0, -1.0, 0.0),
                                                    (0.0, 0.0, -1.0))


def gen_deploy(rig, f, n):
    env = ss((f - 1) / 20.0) if f < 22 else 1.0
    Pp = P(pelvis__z=0.905 - 0.305 * env, pelvis__lean=4.0 * env,
           look=(0.0, lerp(0.0, -12.0, env)))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=0.075)
    Pp["arms"]["L"] = fk_arm(lift=6.0, elbow=16.0, wrist=-8.0, curl=0.18,
                             spread=0.05)
    _, _, M_h_c = combat_hand_matrices(rig, "R", sh["R"])
    M_h_pack = (M_pel @ PROP_OFF["beacon"]) @ BEACON_GRIP
    M_h_spot = hand_M(DEPLOY_SPOT + UP * 0.031, (0.0, -1.0, 0.0),
                      (0.0, 0.0, -1.0))
    if f <= 8:
        M_h, curl_R = M_h_c, 0.25
    elif f <= 11:
        s = ss((f - 8) / 3.0)
        M_h = rig_ops.lerp_matrices(M_h_c, M_h_pack, s)
        curl_R = lerp(0.25, 0.45, s)
    elif f <= 24:
        M_h, curl_R = M_h_pack, 0.45
    elif f <= 28:
        M_h = rig_ops.lerp_matrices(M_h_pack, M_h_spot, ss((f - 24) / 4.0))
        curl_R = 0.45
    elif f <= 34:
        M_h, curl_R = M_h_spot, 0.45
    elif f <= 40:
        M_h = rig_ops.lerp_matrices(M_h_spot, M_h_c, ss((f - 34) / 6.0))
        curl_R = 0.45
    else:
        M_h, curl_R = M_h_c, 0.25
    Pp["arms"]["R"] = ik_arm(M_h.to_translation(), M_h,
                             sh["R"] + Vector((0.15, -0.10, -0.40)),
                             curl=curl_R, spread=0.10)
    if f <= 12:
        pass  # the beacon rides the pelvis (ride_props fills Pp["def"])
    elif f <= 28:
        Pp["def"]["beacon"] = M_h @ BEACON_GRIP.inverted()
    else:
        Pp["def"]["beacon"] = Matrix.Translation(DEPLOY_SPOT) \
            @ rig.rest["beacon"].to_3x3().to_4x4()
    Pp["face"] = {"squint": 0.3}
    return Pp


spec("deploy", "one_shot", 42, gen_deploy,
     [("grab", 11, "beacon taken from the backpack mount"),
      ("place", 28, "beacon pressed onto the deploy spot"),
      ("release", 34, "hand releases the beacon")],
     entry="Combat", exit_="Combat",
     note="Place a visible beacon: crouch down, take the beacon from the "
          "backpack mount, press it onto a ground spot and stand back up; "
          "hand/object contact is exact throughout.")


# ---- uplink (upper-body console gesture) ------------------------------------
def gen_uplink_start(rig, f, n):
    s = ss((f - 1) / 20.0)
    Pp = console_pose(rig, s, spread=0.075)
    Pp["face"] = {"squint": 0.4 * s}
    return Pp


def gen_uplink_end(rig, f, n):
    s = ss((f - 1) / 17.0)
    Pp = console_pose(rig, 1.0 - s,
                      osc=Vector((0.0, 0.0, 0.05 * math.sin(math.pi * s))),
                      spread=0.075)
    Pp["face"] = {"squint": 0.4 * (1.0 - s)}
    return Pp


def gen_uplink_cancel(rig, f, n):
    s = ss((f - 1) / 14.0)
    Pp = console_pose(rig, 1.0 - s,
                      osc=Vector((0.02 * math.sin(math.pi * s), 0.0, 0.0)),
                      spread=0.075)
    Pp["face"] = {"squint": 0.5, "jaw_open": 0.2}
    return Pp


spec("uplink_start", "one_shot", 21, gen_uplink_start,
     [("uplink_begin", 21, "console gesture established")],
     layer="upper_body", entry="Combat", exit_="Uplink",
     note="Begin the recall-like console gesture: both hands move onto the "
          "console; the exit pose is exactly uplink_loop frame 1.")
spec("uplink_end", "one_shot", 18, gen_uplink_end,
     [("uplink_done", 18, "recall complete")],
     layer="upper_body", entry="Uplink", exit_="Combat",
     note="Successful completion cue: the hands lift off the console with a "
          "small upward pulse; the entry pose is exactly uplink_loop "
          "frame 1.")
spec("uplink_cancel", "one_shot", 15, gen_uplink_cancel,
     [("uplink_abort", 6, "recall interrupted")],
     layer="upper_body", entry="Uplink", exit_="Combat",
     note="Interrupted recall: the hands jerk off the console and return to "
          "control; the entry pose is exactly uplink_loop frame 1.")


# ---- stun transitions (full body) -------------------------------------------
def gen_stun_start(rig, f, n):
    if f <= 6:
        si = ss((f - 1) / 5.0)
        return stun_body(rig, pz=0.905, shift=0.06 * si, lean=-10.0 * si,
                         w=(0.0, 1.0, 0.0), arm_swing=60.0 * si,
                         arm_lift=lerp(6.0, 35.0, si), look=(-8.0 * si, 6.0 * si),
                         face={"squint": 0.5 * si, "jaw_open": 0.25})
    if f <= 18:
        sb = ss((f - 7) / 11.0)
        return stun_body(rig, pz=lerp(0.905, 0.872, sb),
                         shift=0.06 * (1.0 - sb)
                         + 0.04 * sb * math.sin(TWO_PI * (f - 7) / 11.0),
                         lean=-10.0 * (1.0 - sb), w=(0.0, 1.0, 0.0),
                         arm_swing=60.0 * (1.0 - sb),
                         arm_lift=lerp(35.0, 2.0, sb),
                         look=(lerp(-8.0, 0.0, sb), lerp(6.0, -6.0, sb)),
                         face={"squint": 0.5, "jaw_open": 0.25})
    sr = ss((f - 19) / 11.0)
    return stun_body(rig, pz=0.872, shift=0.0, lean=0.0, w=(0.0, 1.0, 0.0),
                     arm_swing=0.0, arm_lift=2.0, look=(0.0, -6.0),
                     face={"squint": 0.5 * (1.0 - sr), "jaw_open": 0.25})


def gen_stun_end(rig, f, n):
    t = ss((f - 1) / 29.0)
    Pa = gen_stun_loop(rig, 1, 45)
    Pb = stance_body(rig, 0.905, 0.075, arm="hand")
    Pb["face"] = {"jaw_open": 0.0, "squint": 0.0}
    return P(lerp_params(Pa, Pb, t))


spec("stun_start", "one_shot", 30, gen_stun_start,
     [("stun", 24, "control lost, stunned posture established")],
     entry="Any", exit_="Stun",
     note="Lose control and enter stun: impact stagger with flailing arms, "
          "a swaying stumble, then settle; the exit pose is exactly "
          "stun_loop frame 1.")
spec("stun_end", "one_shot", 30, gen_stun_end,
     [("recover", 30, "control regained")],
     entry="Stun", exit_="Combat",
     note="Regain control without sliding: the sway settles back into the "
          "combat stance; the entry pose is exactly stun_loop frame 1.")


# ---- knockback / knockup -----------------------------------------------------
def gen_knockback(rig, f, n):
    if f <= 6:
        env = ss((f - 1) / 5.0)
    elif f <= 16:
        env = 1.0 - ss((f - 7) / 9.0)
    else:
        env = 0.0
    if f <= 6:
        si = ss((f - 1) / 5.0)
        Pp = stance_body(rig, 0.905, 0.075, lean=-16.0 * si, shift=0.05 * si)
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            Pp["arms"][side] = fk_arm(
                swing=sgn * 80.0 * math.sin(TWO_PI * (f - 1) / 6.0) * env,
                lift=lerp(6.0, 40.0, si))
        Pp["look"] = (0.0, 10.0 * si)
        Pp["face"] = pain_face(si)
        return Pp
    if f <= 16:
        sb = ss((f - 7) / 9.0)
        Pp = stance_body(rig, pelvis_z=lerp(0.905, 0.885, sb),
                         lean=lerp(-16.0, -4.0, sb)
                         + 3.0 * math.sin(TWO_PI * (f - 7) / 9.0) * sb,
                         shift=lerp(0.05, 0.02, sb))
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            Pp["arms"][side] = fk_arm(
                swing=sgn * 80.0 * math.sin(TWO_PI * (f - 1) / 6.0) * env,
                lift=lerp(40.0, 10.0, sb))
        Pp["look"] = (0.0, lerp(10.0, 2.0, sb))
        Pp["face"] = pain_face(lerp(1.0, 0.3, sb))
        return Pp
    sr = ss((f - 17) / 7.0)
    P_com = combat_pose(rig, 0.905, 0.075)
    P_com["face"] = {k: 0.0 for k in PAIN}
    return P(lerp_params(gen_knockback(rig, 16, n), P_com, sr))


def gen_knockup_start(rig, f, n):
    if f <= 7:
        sc = ss((f - 1) / 6.0)
        Pp = stance_body(rig, pelvis_z=lerp(0.905, 0.80, sc), lean=8.0 * sc,
                         spread=lerp(0.075, 0.0, sc))
        for side in ("L", "R"):
            Pp["arms"][side] = fk_arm(lift=lerp(6.0, 30.0, sc), elbow=25.0)
        Pp["face"] = {"squint": -0.3, "jaw_open": 0.3}
        return Pp
    sl = ss((f - 8) / 10.0)
    pz = lerp(0.80, 0.95, sl)
    lean = lerp(8.0, 0.0, sl)
    P_plant = stance_body(rig, pelvis_z=pz, lean=lean, spread=0.0)
    for side in ("L", "R"):
        arm = fk_arm(lift=lerp(30.0, 65.0, sl), elbow=lerp(25.0, 30.0, sl))
        P_plant["arms"][side] = arm
    P_air = P(pelvis__z=pz, pelvis__lean=lean, look=(0.0, 20.0 * sl))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, P_air)
    P_air["legs"] = air_legs(rig, M_pel, 0.18 * sl, 0.18 * sl, 0.0, 0.0,
                             25.0 * sl, 0.0)
    for side in ("L", "R"):
        P_air["arms"][side] = fk_arm(lift=lerp(30.0, 65.0, sl),
                                     elbow=lerp(25.0, 30.0, sl))
    Pp = P(lerp_params(P_plant, P_air, sl))
    Pp["face"] = {"squint": -0.3, "jaw_open": 0.3}
    return Pp


spec("knockback", "one_shot", 24, gen_knockback,
     [("impact", 4, "hit impact, backward travel begins")],
     entry="Any", exit_="Combat",
     note="Reaction to a backward hit: impact stagger with flailing arms, "
          "a stumbling recovery and a return to the combat stance; the "
          "backward travel itself is controlled by the host.")
spec("knockup_start", "one_shot", 18, gen_knockup_start,
     [("launch", 8, "forced launch off the ground")],
     entry="Any", exit_="Knockup",
     note="Forced launch, distinct from a voluntary jump: a deep crouch "
          "then an involuntary lift; the exit pose is exactly knockup_air "
          "frame 1.")


# ---- knockdown / getup (full body, floor contact) ---------------------------
def make_knockdown_gen(face_down):
    back = 1.0 if face_down else -1.0
    kind = "prone_fwd" if face_down else "out"

    def gen(rig, f, n):
        P_stand = stance_body(rig, 0.905, 0.075, arm="hand")
        P_stand["face"] = pain_face(1.0)
        P_ly = lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0, kind=kind,
                        plant=PLANT)[0]
        if f <= 7:
            # the stumble lean goes through stance_body so the FK guard arms
            # stay shoulder-relative (a post-hoc pelvis mutation would move
            # the shoulders off the fixed hand pins and clamp the forearms)
            Pp = stance_body(rig, 0.905, 0.075, arm="hand",
                             lean=back * 8.0 * math.sin(math.pi * (f - 1) / 6.0))
            Pp["face"] = pain_face(ss((f - 1) / 6.0))
            return Pp
        if f <= 22:
            Pp = P(lerp_params(P_stand, P_ly, ss((f - 8) / 14.0)))
            if f <= 12:
                # the arms windmill slightly as the body drops
                dz = 0.15 * math.sin(math.pi * (f - 8) / 4.0)
                M_h = Pp["arms"]["R"]["hand"]
                Pp["arms"]["R"]["hand"] = Matrix.Translation(
                    M_h.to_translation() + Vector((0.0, 0.0, dz))) \
                    @ M_h.to_3x3().to_4x4()
            Pp["face"] = pain_face(1.0)
            return Pp
        Pp = P(P_ly)
        Pp["face"] = pain_face(1.0)
        return Pp
    return gen


def getup_push_pose(rig, face_down, leg_s, lean, pz, st, info_ref, RH_push):
    """Push-up pose between prone and crouch: the palms slide from the prone
    palm positions (st=0 reproduces the prone hand positions exactly, so the
    prone -> getup entry never teleports a hand) to under the current
    shoulders.  The fk-hand head is clamped into the arm's reach sphere, so
    the target is reachable at every frame: the palm rides the floor while
    the arm can still close on it and lifts toward the shoulder once the
    arm would over-extend."""
    _, info_cur = lying_pp(rig, face_down, leg_s=leg_s, arm_s=1.0,
                           pelvis_z=pz, lean_deg=lean, kind="push",
                           plant=PLANT)
    y_dir = RH_push @ Vector((0.0, 1.0, 0.0))
    z_dir = RH_push @ Vector((0.0, 0.0, 1.0))
    hand_over = {}
    for side in ("L", "R"):
        sh = info_cur["shoulders"][side]
        lim = rig.arm_len[side] - 0.02
        palm = lerp_v(info_ref["palms"][side], Vector((sh.x, sh.y, 0.05)), st)
        head = palm - 0.06 * y_dir - 0.025 * z_dir
        d = (head - sh).length
        if d > lim:
            head = sh + (head - sh).normalized() * lim
            palm = head + 0.06 * y_dir + 0.025 * z_dir
        hand_over[side] = hand_M(palm, y_dir, z_dir)
    return lying_pp(rig, face_down, leg_s=leg_s, arm_s=1.0, pelvis_z=pz,
                    lean_deg=lean, kind="push", plant=PLANT, hand_over=hand_over)


def make_getup_gen(face_down):
    back = 1.0 if face_down else -1.0
    kind = "prone_fwd" if face_down else "out"
    if face_down:
        lean_ly, lean_mid0, lean_mid1 = 93.18, 48.0, 10.0
        pz_ly, pz_mid0, pz_mid1 = 0.148, 0.42, 0.66
        RH_push = rot_with_y(FWD, -UP)
    else:
        lean_ly, lean_mid0, lean_mid1 = -86.82, -38.0, -10.0
        pz_ly, pz_mid0, pz_mid1 = 0.2230, 0.34, 0.68
        RH_push = rot_with_y(-FWD, -UP)

    def gen(rig, f, n):
        info_prone = lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0, kind=kind,
                              plant=PLANT)[1]
        if f <= 22:
            st = ss((f - 1) / 21.0)
            return getup_push_pose(rig, face_down, lerp(1.0, 0.8, st),
                                   lerp(lean_ly, lean_mid0, st),
                                   lerp(pz_ly, pz_mid0, st), st, info_prone,
                                   RH_push)[0]
        if f <= 38:
            st = ss((f - 23) / 15.0)
            leg_s = lerp(0.8, 0.35, st)
            lean = lerp(lean_mid0, lean_mid1, st)
            pz = lerp(pz_mid0, pz_mid1, st)
            Pp, info = getup_push_pose(rig, face_down, leg_s, lean, pz, 1.0,
                                       info_prone, RH_push)
            M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
            for side in ("L", "R"):
                hip = hip_pos(rig, side, M_pel)
                ankle = Vector((PLANT[side].x,
                                PLANT[side].y - back * 0.35 * (1.0 - leg_s),
                                ANKLE_Z))
                pole = lerp_v(hip + Vector((0.0, back * 0.25, 0.35)),
                              hip + Vector((0.0, -0.30, -0.25)), st)
                Pp["legs"][side] = ik_leg(
                    ankle, yaw=180.0 if face_down else 0.0, pole=pole)
                arm_p = Pp["arms"][side]
                _, M_fa_c, M_h_c = combat_hand_matrices(rig, side, sh[side])
                M_h = rig_ops.lerp_matrices(arm_p["hand"], M_h_c, st)
                pole_a = lerp_v(Vector(arm_p["pole"]), M_fa_c.to_translation(),
                                st)
                Pp["arms"][side] = fk_hand_arm(
                    M_h, pole_a, curl=lerp(arm_p["curl"], 0.18, st),
                    spread=arm_p["spread"])
            return Pp
        st = ss((f - 39) / 15.0)
        lean = lerp(lean_mid1, 0.0, st)
        pz = lerp(pz_mid1, 0.905, st)
        P_crouch, _ = getup_push_pose(rig, face_down, 0.35, lean_mid1,
                                      pz_mid1, 1.0, info_prone, RH_push)
        dy = P_crouch["pelvis"]["y"]
        aLf = lerp_v(Vector(P_crouch["legs"]["L"]["ankle"]), PLANT["L"], st)
        aRf = lerp_v(Vector(P_crouch["legs"]["R"]["ankle"]), PLANT["R"], st)
        # the feet pivot from the lying orientation to the standing one while
        # the pelvis y rides from the lying offset back to the origin
        Pp, M_pel, M_chest, M_spine03, sh = stance_at(
            rig, aLf, aRf, pelvis_z=pz, lean=lean,
            pelvis_y=lerp(dy, 0.0, st), d_mid=0.98, look=(0.0, 0.0),
            foot_yaw=lerp(180.0 if face_down else 0.0, 0.0, st))
        for side in ("L", "R"):
            Pp["arms"][side] = combat_hand_arm(rig, side, sh[side])
        return Pp
    return gen


spec("knockdown_front", "one_shot", 36, make_knockdown_gen(True),
     [("floor_contact", 22, "body hits the floor face-down")],
     entry="Any", exit_="Prone(front)",
     note="Fall into a face-down position: stagger, drop with a slight arm "
          "windmill, land on the floor; the exit pose is exactly "
          "prone_front frame 1.")
spec("knockdown_back", "one_shot", 36, make_knockdown_gen(False),
     [("floor_contact", 22, "body hits the floor face-up")],
     entry="Any", exit_="Prone(back)",
     note="Fall into a face-up position with a plausible backward "
          "collapse; the exit pose is exactly prone_back frame 1.")
spec("getup_front", "one_shot", 54, make_getup_gen(True),
     [("floor_contact", 30, "push-off from the floor")],
     entry="Prone(front)", exit_="Combat",
     note="Stand up from face-down through plausible supporting contacts: "
          "push-up, knee tuck, crouch, stand; the exit pose is exactly the "
          "combat stance.")
spec("getup_back", "one_shot", 54, make_getup_gen(False),
     [("floor_contact", 30, "push-off from the floor")],
     entry="Prone(back)", exit_="Combat",
     note="Stand up from face-up through a roll-and-push: push-up, swing "
          "the legs under, crouch, stand; the exit pose is exactly the "
          "combat stance.")


# ---- sleep transitions (full body) -------------------------------------------
def gen_sleep_start(rig, f, n):
    Pa = stance_body(rig, 0.905, 0.075, arm="hand")
    Pa["face"] = {"blink_L": 0.0, "blink_R": 0.0, "jaw_open": 0.0}
    Pb = gen_sleep_loop(rig, 1, 60)
    return P(lerp_params(Pa, Pb, ss((f - 1) / 35.0)))


def gen_sleep_end(rig, f, n):
    Pa = gen_sleep_loop(rig, 1, 60)
    Pb = stance_body(rig, 0.905, 0.075, arm="hand")
    Pb["face"] = {"blink_L": 0.0, "blink_R": 0.0, "jaw_open": 0.0}
    return P(lerp_params(Pa, Pb, ss((f - 1) / 35.0)))


spec("sleep_start", "one_shot", 36, gen_sleep_start,
     [("sleep", 36, "stable sleep posture established")],
     entry="Combat", exit_="Sleep",
     note="Enter a stable sleep posture: the body lowers onto the back, "
          "the eyes close; the exit pose is exactly sleep_loop frame 1.")
spec("sleep_end", "one_shot", 36, gen_sleep_end,
     [("wake", 36, "awake and ready")],
     entry="Sleep", exit_="Combat",
     note="Awaken and return to readiness: the body rises from the sleeping "
          "posture with the eyes opening; the entry pose is exactly "
          "sleep_loop frame 1.")


# ---- death / respawn ----------------------------------------------------------
def death_stagger(rig, sb):
    Pp = stance_body(rig, pelvis_z=lerp(0.905, 0.85, sb), lean=-4.0 * sb,
                     spread=0.075, arm="hand")
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        Pp["arms"][side] = combat_hand_arm(rig, side, sh[side],
                                           swing=sgn * 40.0 * (1.0 - sb),
                                           lift=lerp(55.0, 20.0, sb))
    Pp["face"] = pain_face(1.0)
    return Pp


def make_death_gen(face_down):
    kind = "prone_fwd" if face_down else "out"
    pz_ly = 0.148 if face_down else 0.2230
    look_ly = (30.0, 5.0) if face_down else (0.0, 26.0)

    def gen(rig, f, n):
        if f <= 11:
            si = ss((f - 1) / 10.0)
            Pp = stance_body(rig, 0.905, 0.075, arm="hand")
            M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
            for side, sgn in (("L", 1.0), ("R", -1.0)):
                Pp["arms"][side] = combat_hand_arm(
                    rig, side, sh[side], swing=sgn * 40.0 * si,
                    lift=lerp(6.0, 55.0, si))
            Pp["face"] = pain_face(si)
            return Pp
        if f <= 30:
            return death_stagger(rig, ss((f - 11) / 19.0))
        if f <= 52:
            P_ly = lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0,
                            pelvis_z=pz_ly, kind=kind, look=look_ly,
                            plant=PLANT)[0]
            return P(lerp_params(death_stagger(rig, 1.0), P_ly,
                                 ss((f - 30) / 22.0)))
        s = ss((f - 52) / 23.0)
        Pp = lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0,
                      pelvis_z=pz_ly + 0.015 * math.sin(math.pi * s),
                      kind=kind, look=look_ly, plant=PLANT)[0]
        Pp["face"] = pain_face(1.0, jaw=lerp(0.3, 0.18, s))
        Pp["face"]["blink_L"] = Pp["face"]["blink_R"] = s
        return Pp
    return gen


gen_death_front = make_death_gen(False)   # hit from the front -> falls backward
gen_death_back = make_death_gen(True)     # hit from the back -> falls face-down


def gen_respawn(rig, f, n):
    P_dead = gen_death_front(rig, 75, 75)
    info_out = lying_pp(rig, False, leg_s=1.0, arm_s=1.0, kind="out",
                        plant=PLANT)[1]
    RH_push_back = rot_with_y(-FWD, -UP)
    if f <= 10:
        tw = math.sin(math.pi * (f - 1) / 9.0)
        Pp = P(P_dead)
        Pp["fingers"]["R"] = {fing: 40.0 * tw for fing in FINGERS}
        Pp["face"] = dict(P_dead["face"])
        Pp["face"]["blink_L"] = Pp["face"]["blink_R"] = 1.0 - 0.3 * tw
        return Pp
    if f <= 25:
        sp = math.sin(math.pi * (f - 11) / 15.0)
        Pp = lying_pp(rig, False, leg_s=1.0, arm_s=1.0,
                      pelvis_z=0.2230 + 0.01 * sp, kind="out", plant=PLANT)[0]
        Pp["face"] = dict(P_dead["face"])
        M_h = Pp["arms"]["R"]["hand"]
        Pp["arms"]["R"]["hand"] = Matrix.Translation(
            M_h.to_translation()
            + Vector((0.002 * math.sin(7.0 * (f - 1)),
                      0.002 * math.sin(5.0 * (f - 1)), 0.0))) \
            @ M_h.to_3x3().to_4x4()
        return Pp
    if f <= 55:
        st = ss((f - 26) / 29.0)
        Pp, _ = getup_push_pose(rig, False, lerp(1.0, 0.8, st),
                                lerp(-86.82, -38.0, st),
                                lerp(0.2230, 0.34, st), st, info_out,
                                RH_push_back)
        Pp["face"] = dict(P_dead["face"])
        return Pp
    if f <= 70:
        st = ss((f - 56) / 14.0)
        leg_s = lerp(0.8, 0.35, st)
        lean = lerp(-38.0, -10.0, st)
        pz = lerp(0.34, 0.68, st)
        Pp, info = getup_push_pose(rig, False, leg_s, lean, pz, 1.0, info_out,
                                   RH_push_back)
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        for side in ("L", "R"):
            hip = hip_pos(rig, side, M_pel)
            ankle = Vector((PLANT[side].x,
                            PLANT[side].y + 0.35 * (1.0 - leg_s), ANKLE_Z))
            pole = lerp_v(hip + Vector((0.0, -0.25, 0.35)),
                          hip + Vector((0.0, -0.30, -0.25)), st)
            Pp["legs"][side] = ik_leg(ankle, yaw=0.0, pole=pole)
            arm_p = Pp["arms"][side]
            _, M_fa_c, M_h_c = combat_hand_matrices(rig, side, sh[side])
            M_h = rig_ops.lerp_matrices(arm_p["hand"], M_h_c, st)
            pole_a = lerp_v(Vector(arm_p["pole"]), M_fa_c.to_translation(), st)
            Pp["arms"][side] = fk_hand_arm(
                M_h, pole_a, curl=lerp(arm_p["curl"], 0.18, st),
                spread=arm_p["spread"])
        Pp["face"] = dict(P_dead["face"])
        return Pp
    st = ss((f - 71) / 19.0)
    lean = lerp(-10.0, 0.0, st)
    pz = lerp(0.68, 0.905, st)
    P_crouch, _ = getup_push_pose(rig, False, 0.35, -10.0, 0.68, 1.0,
                                  info_out, RH_push_back)
    dy = P_crouch["pelvis"]["y"]
    aLf = lerp_v(Vector(P_crouch["legs"]["L"]["ankle"]), PLANT["L"], st)
    aRf = lerp_v(Vector(P_crouch["legs"]["R"]["ankle"]), PLANT["R"], st)
    Pp, M_pel, M_chest, M_spine03, sh = stance_at(
        rig, aLf, aRf, pelvis_z=pz, lean=lean, pelvis_y=lerp(dy, 0.0, st),
        d_mid=0.98, look=(0.0, 0.0))
    for side in ("L", "R"):
        Pp["arms"][side] = combat_hand_arm(rig, side, sh[side])
    Pp["face"] = {k: v * (1.0 - st) for k, v in P_dead["face"].items()}
    return Pp


spec("death_front", "one_shot", 75, gen_death_front,
     [("death", 30, "death: final body pose reached")],
     entry="Any", exit_="Dead(front)",
     note="Front-impact death: a rising stagger, collapse backward onto the "
          "back and a settle into the final face-up body pose; not a "
          "mirrored duplicate.")
spec("death_back", "one_shot", 75, gen_death_back,
     [("death", 30, "death: final body pose reached")],
     entry="Any", exit_="Dead(back)",
     note="Back-impact death: collapse forward onto the face with the head "
          "turned, ending in a clear stable face-down body pose.")
spec("respawn", "one_shot", 90, gen_respawn,
     [("respawn", 10, "reconstruction begins")],
     entry="Dead(front)", exit_="Combat",
     note="Reconstruct and activate: a twitch, a spasm, then a deliberate "
          "sit-up and stand into the ready stance; not reverse playback of "
          "a death.")


# ---- social -------------------------------------------------------------------
GREET_FACE = {"smile_L": 0.5, "smile_R": 0.5, "cheek_L": 0.5, "cheek_R": 0.5,
              "brow_raise": 0.4}


def gen_greet(rig, f, n):
    Pp = combat_pose(rig, 0.905, 0.075)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    for side in ("L", "R"):
        Pp["arms"][side] = combat_arm_ik(rig, side, sh[side])
    c = M_chest.to_translation()
    pole_greet = sh["R"] + Vector((0.15, -0.10, -0.35))
    M_h_greet = hand_M(c + Vector((0.34, -0.42, 0.10)), (0.0, -1.0, 0.0),
                       (0.0, 0.0, 1.0))
    _, M_fa_c_R, M_h_c_R = combat_hand_matrices(rig, "R", sh["R"])
    if f <= 12:
        s = ss((f - 1) / 11.0)
        M_h = rig_ops.lerp_matrices(M_h_c_R, M_h_greet, s)
        pole = lerp_v(M_fa_c_R.to_translation(), pole_greet, s)
        Pp["arms"]["R"] = ik_arm(M_h.to_translation(), M_h, pole, curl=0.25,
                                 spread=0.30)
        Pp["look"] = (lerp(0.0, 10.0, s), 0.0)
        Pp["face"] = dict(GREET_FACE)
        return Pp
    if f <= 25:
        M_h = hand_M(c + Vector((0.34 + 0.05 * math.sin(TWO_PI * (f - 13) / 6.0),
                                 -0.42, 0.10)), (0.0, -1.0, 0.0),
                     (0.0, 0.0, 1.0))
        Pp["arms"]["R"] = ik_arm(M_h.to_translation(), M_h, pole_greet,
                                 curl=0.25, spread=0.30)
        Pp["look"] = (10.0 + 6.0 * math.sin(TWO_PI * (f - 13) / 6.0), 0.0)
        Pp["face"] = dict(GREET_FACE)
        return Pp
    if f <= 36:
        Pp["arms"]["R"] = ik_arm(M_h_greet.to_translation(), M_h_greet,
                                 pole_greet, curl=0.25, spread=0.30)
        Pp["look"] = (10.0, 0.0)
        Pp["face"] = dict(GREET_FACE)
        return Pp
    s = ss((f - 37) / 11.0)
    P_hold = gen_greet(rig, 36, n)
    P_com = combat_pose(rig, 0.905, 0.075)
    sh_com = body_matrices(rig, P_com)[4]
    for side in ("L", "R"):
        P_com["arms"][side] = combat_arm_ik(rig, side, sh_com[side])
    P_com["face"] = {k: 0.0 for k in GREET_FACE}
    return P(lerp_params(P_hold, P_com, s))


VICTORY_FACE = {"smile_L": 0.9, "smile_R": 0.9, "cheek_L": 0.7, "cheek_R": 0.7,
                "brow_raise": 0.3, "squint": 0.25, "jaw_open": 0.1}


def gen_victory(rig, f, n):
    Pp = combat_pose(rig, 0.905, 0.075)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    c = M_chest.to_translation()
    s = ss((f - 1) / 14.0) if f <= 15 else 1.0
    pump = 0.04 * math.sin(TWO_PI * (f - 16) / 8.0) if 16 <= f <= 45 else 0.0
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        _, M_fa_c, M_h_c = combat_hand_matrices(rig, side, sh[side])
        M_h_up = hand_M(c + Vector((sgn * 0.30, -0.35, 0.55)), (0.0, 0.0, 1.0),
                        (0.0, 1.0, 0.0))
        M_h = rig_ops.lerp_matrices(M_h_c, M_h_up, s)
        if side == "R" and pump:
            M_h = Matrix.Translation(M_h.to_translation()
                                     + Vector((0.0, 0.0, pump))) \
                @ M_h.to_3x3().to_4x4()
        pole = lerp_v(M_fa_c.to_translation(),
                      sh[side] + Vector((sgn * 0.10, -0.10, -0.35)), s)
        Pp["arms"][side] = ik_arm(M_h.to_translation(), M_h, pole,
                                  curl=lerp(0.18, 0.3, s),
                                  spread=lerp(0.05, 0.25, s))
    if f <= 45:
        Pp["face"] = dict(VICTORY_FACE)
        return Pp
    s2 = ss((f - 46) / 14.0)
    P_end = gen_victory(rig, 45, n)
    P_com = combat_pose(rig, 0.905, 0.075)
    sh_com = body_matrices(rig, P_com)[4]
    for side in ("L", "R"):
        P_com["arms"][side] = combat_arm_ik(rig, side, sh_com[side])
    P_com["face"] = {k: 0.0 for k in VICTORY_FACE}
    return P(lerp_params(P_end, P_com, s2))


def gen_defeat(rig, f, n):
    P_com = stance_body(rig, 0.905, 0.075, arm="hand")
    P_com["face"] = {k: 0.0 for k in rig_ops.PRESETS["sadness"]}
    P_com["look"] = (0.0, 0.0)
    if f <= 15:
        s = ss((f - 1) / 14.0)
        Pp = stance_body(rig, pelvis_z=lerp(0.905, 0.845, s),
                         lean=lerp(0.0, 8.0, s), arm="hand")
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        for side in ("L", "R"):
            Pp["arms"][side] = combat_hand_arm(
                rig, side, sh[side], lift=lerp(6.0, 2.0, s),
                wrist=lerp(-8.0, -25.0, s))
        Pp["look"] = (0.0, lerp(0.0, -25.0, s))
        Pp["face"] = {k: v * s for k, v in rig_ops.PRESETS["sadness"].items()}
        return Pp
    if f <= 45:
        Pp = stance_body(rig, pelvis_z=0.845, lean=8.0, arm="hand")
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        for side in ("L", "R"):
            Pp["arms"][side] = combat_hand_arm(rig, side, sh[side], lift=2.0,
                                               wrist=-25.0)
        Pp["look"] = (0.0, -25.0)
        Pp["face"] = dict(rig_ops.PRESETS["sadness"])
        return Pp
    sr = ss((f - 46) / 14.0)
    return P(lerp_params(gen_defeat(rig, 45, n), P_com, sr))


spec("greet", "one_shot", 48, gen_greet,
     [("greeting", 1, "intentional social greeting")],
     layer="upper_body", entry="Social", exit_="Social",
     note="Short intentional greeting: raise the hand, a small wave, hold, "
          "then return to the combat stance with the smile fading.")
spec("victory", "one_shot", 60, gen_victory,
     [("celebrate", 1, "confident celebration")],
     layer="upper_body", entry="Social", exit_="Social",
     note="Confident celebration: both arms pump overhead with a readable "
          "victory face, a rhythmic fist pump, then a return to the "
          "combat stance.")
spec("defeat", "one_shot", 60, gen_defeat,
     [("defeated", 1, "nonfatal defeat")],
     entry="Social", exit_="Social",
     note="Disappointment, nonfatal and distinct from death: the body "
          "slumps into a low dejected stance with a sad face, holds, then "
          "recovers to the combat stance.")


# =================================================================== chunk 5
# ---- hits (additive_upper layer over the neutral combat reference) -------
def make_hit_gen(lean_f, shift_f, yaw_f, swing_amp, lift_end, elbow_end):
    """Additive hit reaction authored over the neutral combat reference:
    the torso flinches away from the hit, both arms flail up and out (the
    flail peaks just after the impact marker) and the pain face peaks with
    it.  The legs stay in the planted combat stance, so the clip layers
    over idle/motion without snapping the planted feet."""
    def gen(rig, f, n):
        st = ss((f - 1) / 11.0)
        Pp = stance_body(rig, pelvis_z=0.905, spread=0.075, lean=lean_f(st),
                         shift=shift_f(st), yaw=yaw_f(st), w=(1.0, 0.0, 0.0))
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            Pp["arms"][side] = combat_hand_arm(
                rig, side, sh[side],
                swing=sgn * swing_amp * math.sin(math.pi * st),
                lift=lerp(6.0, lift_end, st), elbow=lerp(16.0, elbow_end, st))
        Pp["face"] = pain_face(0.55 + 0.45 * st, jaw=0.3 * st)
        return Pp
    return gen


_HIT_VARIANTS = (
    ("hit_f", lambda st: -14.0 * st, lambda st: 0.05 * st, lambda st: 0.0,
     70.0, 38.0, 30.0, "front",
     "Hit from the front: the torso flinches backward off the planted "
     "stance, both arms flail up and out and the pain face peaks at the "
     "impact; additive over the neutral combat reference."),
    ("hit_b", lambda st: 10.0 * st, lambda st: -0.05 * st,
     lambda st: 180.0 * st, 70.0, 38.0, 30.0, "back",
     "Hit from the back: the torso pitches forward, the weight steps back "
     "and the body whips around to face the attacker behind; additive over "
     "the neutral combat reference."),
    ("hit_l", lambda st: 0.0, lambda st: 0.0, lambda st: 25.0 * st,
     60.0, 42.0, 34.0, "left",
     "Hit from the left: the body turns into the hit with a raised guard "
     "and a pain face; additive over the neutral combat reference."),
    ("hit_r", lambda st: 0.0, lambda st: 0.0, lambda st: -25.0 * st,
     60.0, 42.0, 34.0, "right",
     "Hit from the right: the mirrored side hit, turning away with a "
     "raised guard and a pain face; additive over the neutral combat "
     "reference."),
)
for _cid, _lean, _shift, _yaw, _amp, _lift, _elbow, _side, _note in _HIT_VARIANTS:
    spec(_cid, "additive", 12,
         make_hit_gen(_lean, _shift, _yaw, _amp, _lift, _elbow),
         [("impact", 5, "hit from the %s lands" % _side)],
         layer="additive_upper", entry="Any", exit_="Combat", note=_note)


# ---- held poses ------------------------------------------------------------
# dead_front / dead_back: the exact final frame of the death clips.
_P_DEAD_FRONT = gen_death_front(rig, 75, 75)
_P_DEAD_BACK = gen_death_back(rig, 75, 75)


def make_pose_gen(P_pose):
    """Held pose: every frame returns a deep copy of the same pose params."""
    def gen(rig, f, n):
        return P(P_pose)
    return gen


spec("dead_front", "pose", 2, make_pose_gen(_P_DEAD_FRONT),
     [("pose", 1, "held final pose of death_front")],
     layer="full_body", entry="Dead(front)", exit_="Dead(front)",
     note="Held final pose of death_front (face-up, eyes closed): a stable "
          "dead-body pose, keyed identically on both frames.")
spec("dead_back", "pose", 2, make_pose_gen(_P_DEAD_BACK),
     [("pose", 1, "held final pose of death_back")],
     layer="full_body", entry="Dead(back)", exit_="Dead(back)",
     note="Held final pose of death_back (face-down, head turned): a "
          "stable dead-body pose, keyed identically on both frames.")

# aim grid: nine calibrated two-handed aim poses (yaw x pitch) on the
# combat-stance legs with a focus face and the head turned halfway to the
# aim (the established body-yaw -> head-yaw fraction, clamped).
_AIM_GRID = []
for _pn, _pitch in (("down", -25.0), ("level", 0.0), ("up", 25.0)):
    for _yn, _yaw in (("left", -45.0), ("center", 0.0), ("right", 45.0)):
        _Pp = build_aim(rig, _yaw, _pitch, pelvis_z=0.905, spread=0.075,
                        face=rig_ops.PRESETS["focus"],
                        look=(clamp(0.5 * _yaw, -75.0, 75.0),
                              clamp(0.5 * _pitch, -40.0, 40.0)))[0]
        _AIM_GRID.append(("aim_%s_%s" % (_pn, _yn), _yaw, _pitch, _Pp))
for _cid, _yaw, _pitch, _Pp in _AIM_GRID:
    spec(_cid, "pose", 2, make_pose_gen(_Pp),
         [("pose", 1, "held aim pose at yaw %+.0f, pitch %+.0f deg"
            % (_yaw, _pitch))],
         layer="upper_body", entry="Aim", exit_="Aim", aim=(_yaw, _pitch),
         note="Calibrated two-handed aim pose at yaw %+.0f deg, pitch "
              "%+.0f deg: stable wrists and shoulders on the combat-stance "
              "legs, focus face, head turned halfway to the aim."
              % (_yaw, _pitch))

assert len(SPECS) == 96, len(SPECS)
assert {s["id"] for s in SPECS} == set(REQ_BY_ID), "spec/CSV id mismatch"


# ==================================================================== bake
# Bake every clip in CSV order.  Per clip: author frame by frame, then
# verify IK/chain closure, floor contact, markers, frame range, action
# round-trip, loop seam and dash root tracking; record everything for the
# manifest.
LYING_CLIPS = {"knockdown_front", "knockdown_back", "prone_front",
               "prone_back", "getup_front", "getup_back", "sleep_start",
               "sleep_loop", "sleep_end", "death_front", "death_back",
               "dead_front", "dead_back", "respawn"}
DASH_CLIPS = {"dash_f", "dash_b", "dash_l", "dash_r"}
BLINK_CLIPS = {"blink_out", "blink_in"}


def mesh_bbox_center():
    """(cx, cy) of the evaluated mesh bounding box (horizontal center)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    xs = [v.co.x for v in mm.vertices]
    ys = [v.co.y for v in mm.vertices]
    me.to_mesh_clear()
    return (0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys)))


BAKE_ORDER = sorted(SPECS, key=lambda s: s["csv_index"])
CLIP_ENTRIES = []
FAILURES = []
t_bake0 = time.time()
for _ci, sp in enumerate(BAKE_ORDER):
    cid, n = sp["id"], sp["n"]
    t0 = time.time()
    rig.reset()
    rig.begin_clip(cid, n)
    caps = {}
    ik_max = chain_max = 0.0
    floor_min = 1e9        # captured cap frames (asserted)
    floor_min_all = 1e9    # every frame (recorded; gross-penetration net)
    for f in range(1, n + 1):
        Pp = sp["gen"](rig, f, n)
        M_pel = body_matrices(rig, Pp)[1]
        ride_props(rig, Pp, M_pel)
        apply_pose(rig, Pp)
        rig.apply()
        rig.post_pose(Pp)
        rig.key(f, force=True)
        mz = mesh_min_z()
        floor_min_all = min(floor_min_all, mz)
        if f in (1, n // 2, n):
            cap = {"ik": ik_error(rig, Pp),
                   "chain": chain_error(rig, gs=Pp["scale"]),
                   "min_z": mz,
                   "def_m": {name: rig.def_m[name].copy() for name in DEFORM_BONES},
                   "shapes": {k: rig.sk.key_blocks[k].value for k in SHAPE_KEYS}}
            if cid in DASH_CLIPS:
                cap["bbox"] = mesh_bbox_center()
                cap["root_xy"] = rig.def_m["root"].to_translation()
            caps[f] = cap
            ik_max = max(ik_max, cap["ik"])
            chain_max = max(chain_max, cap["chain"])
            floor_min = min(floor_min, mz)
    rig.end_clip(n, sp["markers"], loop=sp["loop"])

    # ---- per-clip checks
    act = bpy.data.actions.get(cid)
    face_act = bpy.data.actions.get(cid + "_face")
    checks = {}
    checks["actions_exist"] = act is not None and face_act is not None
    checks["frame_range_ok"] = bool(
        act is not None and face_act is not None
        and act.frame_start == 1 and act.frame_end == n
        and face_act.frame_start == 1 and face_act.frame_end == n)
    got_mk = sorted((m.name, m.frame) for m in act.pose_markers) if act else []
    want_mk = sorted((nm, fr) for nm, fr, _nt in sp["markers"])
    checks["markers_ok"] = got_mk == want_mk
    chain_tol = 5e-3 if cid in BLINK_CLIPS else 2e-4
    checks["ik_ok"] = ik_max <= 1e-4
    checks["chain_ok"] = chain_max <= chain_tol
    checks["floor_ok"] = floor_min > -0.005
    checks["floor_all_ok"] = floor_min_all > -0.02
    checks["floor_final_ok"] = None
    if cid in LYING_CLIPS:
        checks["floor_final_ok"] = -0.005 < caps[n]["min_z"] < 0.02
    # action round-trip: re-assign both actions, evaluate the captured
    # frames and compare against the captured pose
    rt_err = 0.0
    if act is not None and face_act is not None:
        rig.A.animation_data.action = act
        rig.sk.animation_data.action = face_act
        for f in sorted(caps):
            bpy.context.scene.frame_set(f)
            cap = caps[f]
            for name in DEFORM_BONES:
                rt_err = max(rt_err, mat_err(rig.pbs[name].matrix,
                                             cap["def_m"][name]))
            for k in SHAPE_KEYS:
                rt_err = max(rt_err, abs(rig.sk.key_blocks[k].value
                                         - cap["shapes"][k]))
        rig.A.animation_data.action = None
        rig.sk.animation_data.action = None
    checks["roundtrip_ok"] = rt_err <= 1e-4
    checks["loop_seam_ok"] = None
    if sp["loop"]:
        rig.root_off = Vector((0.0, 0.0, 0.0))
        checks["loop_seam_ok"] = params_close(sp["gen"](rig, 1, n),
                                              sp["gen"](rig, n + 1, n), 1e-9)
    checks["dash_track_ok"] = None
    dash_max = dash_travel = None
    if cid in DASH_CLIPS:
        dash_max = max(math.hypot(cap["bbox"][0] - cap["root_xy"].x,
                                  cap["bbox"][1] - cap["root_xy"].y)
                       for cap in caps.values())
        b0, b1 = caps[1]["bbox"], caps[n]["bbox"]
        dash_travel = math.hypot(b1[0] - b0[0], b1[1] - b0[1])
        checks["dash_track_ok"] = dash_max <= 0.45
    clip_ok = all(v for v in checks.values() if v is not None)

    if sp["root_movement"] == "root_motion":
        policy = ("root_motion: the root bone carries the baked horizontal "
                  "translation; the controller/capsule must track the root "
                  "bone and the mesh must not drift away from it")
    elif sp["treadmill"]:
        policy = ("in_place treadmill: authored at %.0f cm/s apparent speed "
                  "(the stance foot moves backward relative to the body), "
                  "so a controller moving the capsule at the nominal speed "
                  "keeps the world feet planted" % sp["treadmill"])
    else:
        policy = ("in_place: no baked actor travel; the controller positions "
                  "the capsule (teleport/blink events are pose markers only)")

    CLIP_ENTRIES.append({
        "id": cid,
        "form": sp["form"],
        "csv_row": sp["csv_index"] + 2,
        "source_action": cid,
        "face_action": cid + "_face",
        "blend_file": "source/Operative_rig.blend",
        "export_file": "export/animations/%s.fbx" % cid,
        "export_take": cid,
        "unreal_asset_path": "/Game/Characters/Operative/Animations/%s" % cid,
        "frame_start": 1,
        "frame_end": n,
        "sample_rate": 30,
        "duration_seconds": n / 30.0,
        "duration_text": sp["dur_text"],
        "loop": sp["loop"],
        "root_movement": sp["root_movement"],
        "root_motion_policy": policy,
        "layer": sp["layer"],
        "entry_state": sp["entry"],
        "exit_state": sp["exit"],
        "markers": [{"name": nm, "frame": fr, "note": nt}
                    for nm, fr, nt in sp["markers"]],
        "nominal_speed_cm_s": sp["nominal_speed"],
        "treadmill_cm_s": sp["treadmill"],
        "aim_deg": ({"yaw": sp["aim"][0], "pitch": sp["aim"][1]}
                    if sp["aim"] else None),
        "required_behavior": sp["behavior"],
        "authoring_note": sp["note"],
        "checks": {
            "ik_max": ik_max,
            "chain_max": chain_max,
            "chain_tol": chain_tol,
            "floor_min_z": floor_min,
            "floor_min_z_all_frames": floor_min_all,
            "floor_final_z": caps[n]["min_z"] if cid in LYING_CLIPS else None,
            "roundtrip_max_err": rt_err,
            "dash_root_track_max_m": dash_max,
            "dash_mesh_travel_m": dash_travel,
            "actions_exist": checks["actions_exist"],
            "frame_range_ok": checks["frame_range_ok"],
            "markers_ok": checks["markers_ok"],
            "ik_ok": checks["ik_ok"],
            "chain_ok": checks["chain_ok"],
            "floor_ok": checks["floor_ok"],
            "floor_all_ok": checks["floor_all_ok"],
            "floor_final_ok": checks["floor_final_ok"],
            "roundtrip_ok": checks["roundtrip_ok"],
            "loop_seam_ok": checks["loop_seam_ok"],
            "dash_track_ok": checks["dash_track_ok"],
            "passed": clip_ok,
        },
    })
    if clip_ok:
        print("bake %3d/96 %-16s n=%3d ik=%.1e chain=%.1e floor=%.4f "
              "rt=%.1e %.1fs PASS"
              % (_ci + 1, cid, n, ik_max, chain_max, floor_min, rt_err,
                 time.time() - t0))
    else:
        bad = [k for k, v in checks.items() if v is False]
        print("bake %3d/96 %-16s n=%3d ik=%.1e chain=%.1e floor=%.4f "
              "rt=%.1e %.1fs FAIL %s"
              % (_ci + 1, cid, n, ik_max, chain_max, floor_min, rt_err,
                 time.time() - t0, ",".join(bad)))
        FAILURES.append((cid, bad))
    sys.stdout.flush()

print("baked %d clips in %.1f s" % (len(CLIP_ENTRIES), time.time() - t_bake0))
for sp in BAKE_ORDER:
    assert bpy.data.actions.get(sp["id"]) is not None, sp["id"]
    assert bpy.data.actions.get(sp["id"] + "_face") is not None, \
        sp["id"] + "_face"
print("actions in file: %d (96 clips x 2 = 192 expected)"
      % len(bpy.data.actions))

all_passed = not FAILURES
if FAILURES:
    print("GEN03: %d clip(s) failed checks:" % len(FAILURES))
    for _cid, _bad in FAILURES:
        print("  FAIL %-16s %s" % (_cid, ",".join(_bad)))

# ------------------------------------------------------------- manifest
STATE_VOCAB = sorted({s["entry"] for s in SPECS} | {s["exit"] for s in SPECS})
manifest = {
    "version": "1.0",
    "generated_by": "source/generators/gen_03_animations.py",
    "generated_with": "Blender %s (blender -b --factory-startup --python)"
                      % bpy.app.version_string,
    "generated_on": time.strftime("%Y-%m-%d"),
    "character": "Operative",
    "blend_file": "source/Operative_rig.blend",
    "fps": 30,
    "frame_range_convention": "frame keys span exactly [1, n]; every action "
                              "has frame_start=1 and frame_end=n",
    "duration_convention": "duration_seconds = n / 30",
    "conventions": [
        "30 FPS, Blender meters, Z up",
        "the character faces -Y; +yaw turns right, +pitch looks up",
        "frame keys span exactly [1, n]; duration_seconds = n / 30",
        "loop flags are manifest-only: Blender 5.1 Action.use_cyclic exists "
        "but does not wrap fcurve evaluation, so no CYCLES fcurve modifiers "
        "are added anywhere",
        "locomotion clips are treadmill-authored: the stance foot moves "
        "backward relative to the body at the nominal apparent speed, so a "
        "controller moving the capsule at the nominal speed keeps the world "
        "feet planted",
        "dash_* are root-motion clips: the root bone carries a linear 2.0 m "
        "translation along the dash direction; the controller/capsule must "
        "track the root bone and the mesh must not drift away from it",
        "blink_out/blink_in bake no actor travel; the teleport/arrive events "
        "are pose markers only",
        "layers: full_body (whole-body clip), upper_body (reusable "
        "upper-body layer over a locomotion/idle base), additive_upper (hit "
        "reactions authored over the neutral combat reference)",
        "face props not driven by a clip hold their previous value within "
        "the clip; every clip starts from zeroed (neutral) face props",
    ],
    "state_vocabulary": STATE_VOCAB,
    "nominal_speeds_cm_s": {"walk": 150.0, "run": 400.0, "sprint": 650.0},
    "lip_sync": {
        "clip": "dialogue",
        "audio": "source/audio/dialogue.wav",
        "transcript": "source/audio/dialogue.txt",
        "alignment": "source/audio/dialogue_alignment.json",
        "duration_seconds": 408 / 30.0,
        "duration_frames": 408,
        "fps": 30,
        "method": "espeak-ng TTS phoneme timing (dialogue_alignment.json) "
                  "drives the rig_ops.VISEMES shape-key presets; visemes "
                  "crossfade linearly at entry boundaries with a subtle "
                  "continuous jaw flutter; authored blinks, clause-indexed "
                  "gaze and hand gestures ride the clause timeline",
    },
    "export": {
        "status": "planned: tools/export_and_bake.py bakes each action to "
                  "export/animations/<id>.fbx (take <id>) and imports it as "
                  "an Unreal AnimSequence",
        "file_pattern": "export/animations/<id>.fbx",
        "take_pattern": "<id>",
        "unreal_asset_path_pattern": "/Game/Characters/Operative/Animations/<id>",
        "face_actions": "each <id>_face shape-key action exports with the "
                        "same take (blend-shape track)",
    },
    "clips": CLIP_ENTRIES,
    "clip_count": len(CLIP_ENTRIES),
    "all_passed": all_passed,
}
os.makedirs(os.path.join(TASK, "docs"), exist_ok=True)
for _mp in (os.path.join(TASK, "docs", "animation_manifest.json"),
            os.path.join(TASK, "animation_manifest.json")):
    with open(_mp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")
print("wrote docs/animation_manifest.json (+ copy at task root)")

if not all_passed:
    print("GEN03 FAIL (%d clip(s) with failed checks; manifest written, "
          "blend not saved)" % len(FAILURES))
    sys.exit(1)

# ---- back to rest, sync the embedded rig_ops, save
rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()
bpy.context.scene.frame_set(1)

with open(os.path.join(TASK, "tools", "rig_ops.py"), encoding="utf-8") as fh:
    _src = fh.read()
_txt = bpy.data.texts.get("rig_ops.py")
if _txt is None:
    _txt = bpy.data.texts.new("rig_ops.py")
_txt.clear()
_txt.write(_src)
_txt.use_module = True
print("embedded rig_ops.py synced (%d bytes, use_module=%s)"
      % (len(_src), _txt.use_module))

bpy.ops.wm.save_mainfile(filepath=BLEND)
print("saved %s" % BLEND)
print("GEN03 OK")

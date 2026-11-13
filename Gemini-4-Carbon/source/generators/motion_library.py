#!/usr/bin/env python3
"""
Complete 96-Entry Biomechanical Motion & Pose Library for MORPHRIG Cyberpunk Operative (30 FPS).
Covers all 85 motion clips and 11 static poses in required_animations.csv with:
  - Phase-synchronized 8-directional Walk (150 cm/s), Run (400 cm/s), and Forward Sprint (650 cm/s)
  - Starts, stops, 90-deg turns with foot placement, 180-deg moving pivots
  - Jump start/air/land, long fall, heavy 3-point landing
  - 2.00 m horizontal Root-Motion dashes (dash_f/b/l/r) and in-place Blink out/in with teleport marker
  - Melee 1/2/3 forearm-blade slashes (extension + hit/recovery markers), Ranged fire & 3-shot burst, physical Cell Reload
  - Directional/ground/self Casts, 4-part Channel, 4-part Charge, physical Beacon Deploy, 4-part Uplink
  - Local-space Additive Hits (hit_f/b/l/r) preserving planted feet
  - Stun, Knockback, Knockup, Front/Back Knockdowns, Prone loops, plausible-contact Getups, Sleep, Front/Back Deaths + exact Dead poses, Respawn
  - Social Greet/Victory/Defeat, sample-aligned 16.48s Spoken Dialogue performance, and calibrated 9-sample Aim Grid (-60/0/+60 yaw, -35/0/+35 pitch)
"""

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from mathutils import Vector, Euler, Quaternion

ROOT_DIR = Path(__file__).resolve().parents[2]
DIALOGUE_ALIGN_PATH = ROOT_DIR / "source" / "audio" / "dialogue_alignment.json"
CSV_PATH = ROOT_DIR / "required_animations.csv"

FPS = 30


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sstep(e0: float, e1: float, x: float) -> float:
    t = clamp((x - e0) / max(1e-8, e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def bell(x: float, center: float, half_width: float) -> float:
    d = abs(x - center) / max(1e-6, half_width)
    if d >= 1.0:
        return 0.0
    c = math.cos(d * math.pi * 0.5)
    return c * c


def pulse_env(u: float, t_attack: float, t_hold_end: float, t_release_end: float) -> float:
    if u <= 0.0 or u >= t_release_end:
        return 0.0
    if u < t_attack:
        return sstep(0.0, t_attack, u)
    if u <= t_hold_end:
        return 1.0
    return 1.0 - sstep(t_hold_end, t_release_end, u)


@dataclass
class PoseSpec:
    """World-space control offsets & rotations relative to neutral ground-origin T-pose."""
    loc: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    rot: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # World XYZ Euler radians
    props: dict[str, float] = field(default_factory=dict)
    shapes: dict[str, float] = field(default_factory=dict)
    finger_curl_l: float = 0.20
    finger_curl_r: float = 0.25
    finger_spread_l: float = 0.0
    finger_spread_r: float = 0.0


def combat_ready_base(breath_phase: float = 0.0) -> PoseSpec:
    """Canonical athletic combat ready stance (Frame 0 when breath_phase=0 is additive reference!)."""
    p = PoseSpec()
    br = math.sin(breath_phase)
    p.props = {
        "ik_fk_arm_l": 0.0,
        "ik_fk_arm_r": 0.0,
        "ik_fk_leg_l": 1.0,
        "ik_fk_leg_r": 1.0,
        "head_look_at": 0.0,
        "eye_look_at": 1.0,
        "cell_in_hand_l": 0.0,
        "beacon_in_hand_l": 0.0,
        "beacon_planted": 0.0,
    }
    # Slightly staggered athletic feet, lowered pelvis, alert forward guard
    p.loc["CTRL_Pelvis"] = (0.008 * math.sin(breath_phase), 0.015, -0.055 + 0.008 * br)
    p.loc["CTRL_IK_Foot_L"] = (+0.035, -0.065, 0.0)
    p.loc["CTRL_IK_Foot_R"] = (-0.040, +0.075, 0.0)
    p.rot["CTRL_IK_Foot_L"] = (0.0, 0.0, +0.08)
    p.rot["CTRL_IK_Foot_R"] = (0.0, 0.0, -0.18)

    p.rot["CTRL_Pelvis"] = (0.0, 0.0, -0.14)
    p.rot["CTRL_Spine_01"] = (+0.06, 0.0, +0.05)
    p.rot["CTRL_Spine_02"] = (+0.05 - 0.018 * br, 0.0, +0.05)
    p.rot["CTRL_Spine_03"] = (+0.04 - 0.022 * br, 0.0, +0.06)
    p.rot["CTRL_Head"] = (-0.12 + 0.02 * br, 0.0, -0.02)

    # Arms lowered from T-pose into readable cyberpunk combat guard (free hands, clear silhouette!)
    p.rot["CTRL_Clavicle_L"] = (0.0, -0.04 * br, 0.0)
    p.rot["CTRL_Clavicle_R"] = (0.0, +0.04 * br, 0.0)
    p.rot["CTRL_FK_UpperArm_L"] = (0.18, +1.06, -0.32)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, +0.15, -0.78)
    p.rot["CTRL_FK_Hand_L"] = (0.10, 0.0, -0.12)

    p.rot["CTRL_FK_UpperArm_R"] = (0.22, -0.98, +0.38)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.18, +0.92)
    p.rot["CTRL_FK_Hand_R"] = (-0.08, 0.0, +0.10)

    p.finger_curl_l = 0.32
    p.finger_curl_r = 0.42

    # Subtle secondary settle on neural cable & hip strap
    p.rot["CTRL_Cable_01"] = (0.06 + 0.03 * br, 0.02 * math.cos(breath_phase), 0.0)
    p.rot["CTRL_Cable_02"] = (0.08 + 0.04 * math.sin(breath_phase - 0.6), 0.03 * math.cos(breath_phase - 0.5), 0.0)
    p.rot["CTRL_Strap_01"] = (0.03 * br, -0.04 - 0.02 * math.cos(breath_phase), 0.0)
    p.rot["CTRL_Strap_02"] = (0.04 * math.sin(breath_phase - 0.7), -0.03 * math.cos(breath_phase - 0.6), 0.0)

    p.shapes["expr_focus"] = 0.38
    return p


def blend_poses(a: PoseSpec, b: PoseSpec, w: float) -> PoseSpec:
    w = clamp(w, 0.0, 1.0)
    if w <= 0.0:
        return a
    if w >= 1.0:
        return b
    out = PoseSpec()
    for k in set(a.loc) | set(b.loc):
        va = Vector(a.loc.get(k, (0.0, 0.0, 0.0)))
        vb = Vector(b.loc.get(k, (0.0, 0.0, 0.0)))
        v = va.lerp(vb, w)
        out.loc[k] = (v.x, v.y, v.z)
    for k in set(a.rot) | set(b.rot):
        qa = Euler(a.rot.get(k, (0.0, 0.0, 0.0)), "XYZ").to_quaternion()
        qb = Euler(b.rot.get(k, (0.0, 0.0, 0.0)), "XYZ").to_quaternion()
        e = qa.slerp(qb, w).to_euler("XYZ")
        out.rot[k] = (e.x, e.y, e.z)
    for k in set(a.props) | set(b.props):
        out.props[k] = a.props.get(k, 0.0) * (1.0 - w) + b.props.get(k, 0.0) * w
    for k in set(a.shapes) | set(b.shapes):
        val = a.shapes.get(k, 0.0) * (1.0 - w) + b.shapes.get(k, 0.0) * w
        if abs(val) > 1e-4:
            out.shapes[k] = val
    out.finger_curl_l = a.finger_curl_l * (1.0 - w) + b.finger_curl_l * w
    out.finger_curl_r = a.finger_curl_r * (1.0 - w) + b.finger_curl_r * w
    out.finger_spread_l = a.finger_spread_l * (1.0 - w) + b.finger_spread_l * w
    out.finger_spread_r = a.finger_spread_r * (1.0 - w) + b.finger_spread_r * w
    return out


# =============================================================================
# BIOMECHANICAL DIRECTIONAL GAIT GENERATOR (Walk 8-dir, Run 8-dir, Sprint)
# =============================================================================

DIR_VECTORS = {
    "f":  ( 0.0, -1.0,  0.0),
    "fl": (+0.7071, -0.7071, +0.42),
    "l":  (+1.0,  0.0, +0.32),
    "bl": (+0.7071, +0.7071, -0.38),
    "b":  ( 0.0, +1.0,  0.0),
    "br": (-0.7071, +0.7071, +0.38),
    "r":  (-1.0,  0.0, -0.32),
    "fr": (-0.7071, -0.7071, -0.42),
}


def eval_gait(mode: str, dir_code: str, phase: float) -> PoseSpec:
    """
    Phase-synchronized cyclic locomotion (phase in [0, 1), periodic: phase=0 == phase=1!).
      p = 0.0: Left foot contact strike; p = 0.5: Right foot contact strike.
    """
    dx, dy, hip_twist_bias = DIR_VECTORS[dir_code]
    th = 2.0 * math.pi * phase
    p = combat_ready_base(0.0)

    if mode == "walk":
        stride = 0.30
        lift = 0.085
        bob_amp = 0.024
        pelvis_drop = -0.042
        fwd_lean = +0.07 if dy <= 0 else +0.04
        arm_swing = 0.34
        cable_lag = -0.14
        duty = 0.58  # Ground contact fraction (> 0.5 for walk double-support!)
    elif mode == "run":
        stride = 0.44
        lift = 0.21
        bob_amp = 0.052
        pelvis_drop = -0.085
        fwd_lean = +0.20 if dy <= 0 else +0.08
        arm_swing = 0.62
        cable_lag = -0.30
        duty = 0.40  # Aerial flight phase (< 0.5 for run!)
    else:  # sprint_f
        stride = 0.56
        lift = 0.31
        bob_amp = 0.068
        pelvis_drop = -0.115
        fwd_lean = +0.34
        arm_swing = 0.92
        cable_lag = -0.46
        duty = 0.34

    def foot_traj(foot_phase: float, side_sign: float):
        fp = foot_phase % 1.0
        # During stance [0, duty]: foot sweeps linearly from +stride*(dx,dy) to -stride*(dx,dy) ON THE GROUND (Z=0)!
        if fp < duty:
            u_st = fp / duty
            pos_s = 1.0 - 2.0 * u_st
            fz = 0.0
            # Authentic heel-strike (Rx<0 lifts toes) -> flat -> toe push-off (Rx>0 lifts heel)!
            if dy <= 0.1:
                heel_p = -0.22 * max(0.0, 1.0 - u_st * 3.2) * (-dy if dy < 0 else 0.4)
                ball_r = +0.36 * max(0.0, (u_st - 0.55) / 0.45)
            else:
                # Retro-gait: toe touches back first, rolls to heel!
                heel_p = 0.0
                ball_r = +0.28 * max(0.0, 1.0 - u_st * 2.5)
        else:
            # Swing phase [duty, 1.0]: smooth cycloid arc from -stride back to +stride with knee/ankle clearance!
            u_sw = (fp - duty) / (1.0 - duty)
            pos_s = -1.0 + 2.0 * (u_sw - math.sin(2.0 * math.pi * u_sw) / (2.0 * math.pi))
            fz = lift * (math.sin(math.pi * u_sw) ** 1.3)
            heel_p = -0.16 * sstep(0.65, 1.0, u_sw) * (1.0 if dy < 0 else 0.2)
            ball_r = -0.18 * math.sin(math.pi * u_sw)

        # Lateral strafe clearance so shins never collide during walk_l / walk_r / run_l / run_r
        lat_clear = 0.0
        if abs(dx) > 0.65:
            # Avoid crossing centerline beyond 4cm
            raw_x = dx * stride * pos_s
            if side_sign > 0 and raw_x < -0.05:
                raw_x = -0.05 + 0.35 * (raw_x + 0.05)
            elif side_sign < 0 and raw_x > +0.05:
                raw_x = +0.05 + 0.35 * (raw_x - 0.05)
            fx = raw_x
            lat_clear = 0.03 * math.sin(math.pi * clamp((fp - duty) / (1.0 - duty), 0.0, 1.0)) if fp >= duty else 0.0
        else:
            fx = dx * stride * pos_s
        fy = dy * stride * pos_s + lat_clear * (-1.0 if side_sign > 0 else 1.0)
        return (fx, fy, fz), heel_p, ball_r

    fl_co, hl_l, rl_l = foot_traj(phase, +1.0)
    fr_co, hl_r, rl_r = foot_traj(phase + 0.5, -1.0)

    p.loc["CTRL_IK_Foot_L"] = fl_co
    p.loc["CTRL_IK_Foot_R"] = fr_co
    p.rot["CTRL_HeelPivot_L"] = (hl_l, 0.0, 0.0)
    p.rot["CTRL_HeelPivot_R"] = (hl_r, 0.0, 0.0)
    p.rot["CTRL_FootRoll_L"] = (rl_l, 0.0, 0.0)
    p.rot["CTRL_FootRoll_R"] = (rl_r, 0.0, 0.0)
    p.rot["CTRL_IK_Foot_L"] = (0.0, 0.0, hip_twist_bias * 0.45)
    p.rot["CTRL_IK_Foot_R"] = (0.0, 0.0, hip_twist_bias * 0.45)

    # Double-frequency pelvis vertical bounce + lateral weight shift + hip-shoulder counter-torsion!
    vert_bob = bob_amp * math.sin(2.0 * th - 0.65)
    lat_sway = 0.024 * math.cos(th)
    pelvis_yaw = hip_twist_bias + 0.13 * math.cos(th)
    pelvis_roll = 0.055 * math.cos(th)

    p.loc["CTRL_Pelvis"] = (lat_sway + dx * 0.03, dy * 0.03, pelvis_drop + vert_bob)
    p.rot["CTRL_Pelvis"] = (fwd_lean * 0.35, pelvis_roll, pelvis_yaw)
    # Counter-rotate spine_01..03 so chest, head, and aim retain forward (-Y) facing!
    chest_counter = -hip_twist_bias * 0.85 - 0.18 * math.cos(th)
    p.rot["CTRL_Spine_01"] = (fwd_lean * 0.35, -pelvis_roll * 0.5, chest_counter * 0.35)
    p.rot["CTRL_Spine_02"] = (fwd_lean * 0.35, -pelvis_roll * 0.3, chest_counter * 0.35)
    p.rot["CTRL_Spine_03"] = (fwd_lean * 0.25, 0.0, chest_counter * 0.30)
    p.rot["CTRL_Head"] = (-fwd_lean * 0.90, 0.0, -pelvis_yaw - chest_counter * 1.0)

    # Opposing arm swing around athletic bent-elbow guard
    swing_s = math.cos(th)
    elbow_pump_l = max(0.0, swing_s) * 0.35
    elbow_pump_r = max(0.0, -swing_s) * 0.35
    base_y_l = +1.14 if mode == "walk" else +1.02
    base_y_r = -1.10 if mode == "walk" else -0.98

    p.rot["CTRL_FK_UpperArm_L"] = (0.12, base_y_l, -0.22 - arm_swing * swing_s)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.12, -(0.55 if mode == "walk" else 1.08) - elbow_pump_l)
    p.rot["CTRL_FK_UpperArm_R"] = (0.14, base_y_r, +0.24 - arm_swing * swing_s)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.14, +(0.62 if mode == "walk" else 1.12) + elbow_pump_r)

    p.finger_curl_l = 0.45 if mode == "walk" else 0.78
    p.finger_curl_r = 0.50 if mode == "walk" else 0.82

    # Secondary motion wave on neural braid cable & hip tactical strap!
    w1 = math.sin(2.0 * th - 1.1)
    w2 = math.sin(2.0 * th - 1.9)
    p.rot["CTRL_Cable_01"] = (cable_lag + 0.10 * w1, -0.08 * math.cos(th - 0.6), 0.0)
    p.rot["CTRL_Cable_02"] = (cable_lag * 0.7 + 0.14 * w2, -0.11 * math.cos(th - 1.1), 0.0)
    p.rot["CTRL_Cable_03"] = (0.16 * math.sin(2.0 * th - 2.5), -0.12 * math.cos(th - 1.6), 0.0)

    p.rot["CTRL_Strap_01"] = (cable_lag * 0.6 * (-dy) + 0.09 * w1, -0.06 - 0.08 * abs(dx) - 0.06 * w1, 0.0)
    p.rot["CTRL_Strap_02"] = (0.12 * w2, -0.08 * w2, 0.0)
    p.rot["CTRL_Strap_03"] = (0.14 * math.sin(2.0 * th - 2.4), -0.08 * math.cos(2.0 * th - 2.0), 0.0)

    p.shapes["expr_focus"] = 0.35 if mode == "walk" else (0.55 if mode == "run" else 0.80)
    if mode in ("run", "sprint"):
        p.shapes["corr_knee_bend_l"] = 0.45 * max(0.0, math.sin(math.pi * clamp((phase - duty) / (1.0 - duty), 0.0, 1.0)))
        p.shapes["corr_knee_bend_r"] = 0.45 * max(0.0, math.sin(math.pi * clamp(((phase + 0.5) % 1.0 - duty) / (1.0 - duty), 0.0, 1.0)))
    return p


# =============================================================================
# PRONE, DEAD, AND AIM REFERENCE POSES (Guaranteed Exact Transitions!)
# =============================================================================

def make_prone_front_pose(breath: float = 0.0) -> PoseSpec:
    p = combat_ready_base(0.0)
    p.props["ik_fk_leg_l"] = 0.0
    p.props["ik_fk_leg_r"] = 0.0
    # Face-down floor posture: pelvis at Z=0.14m (-0.82m offset from 0.96m), pitched +86 deg forward (-Y)!
    p.loc["CTRL_Pelvis"] = (0.0, 0.05, -0.82 + 0.006 * breath)
    p.rot["CTRL_Pelvis"] = (+1.50, 0.0, 0.05)
    p.rot["CTRL_Spine_01"] = (-0.08 - 0.02 * breath, 0.0, 0.0)
    p.rot["CTRL_Spine_02"] = (-0.10 - 0.02 * breath, 0.0, 0.0)
    p.rot["CTRL_Head"] = (-0.38, 0.0, 0.42)
    # Keep forearms resting ON the floor plane (Z ~ 0.06..0.14m)
    p.rot["CTRL_FK_UpperArm_L"] = (0.05, -0.55, +0.08)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, -0.85, -0.05)
    p.rot["CTRL_FK_UpperArm_R"] = (0.05, +0.55, -0.08)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, +0.80, +0.05)
    p.rot["CTRL_FK_Thigh_L"] = (0.04, +0.12, 0.0)
    p.rot["CTRL_FK_Thigh_R"] = (0.05, -0.15, 0.0)
    p.rot["CTRL_FK_Calf_L"] = (+0.16, 0.0, 0.0)
    p.rot["CTRL_FK_Calf_R"] = (+0.22, 0.0, 0.0)
    p.rot["CTRL_Cable_01"] = (+0.45, 0.15, 0.0)
    p.shapes["expr_pain"] = 0.45
    return p


def make_prone_back_pose(breath: float = 0.0) -> PoseSpec:
    p = combat_ready_base(0.0)
    p.props["ik_fk_leg_l"] = 0.0
    p.props["ik_fk_leg_r"] = 0.0
    # Supine face-up floor posture: pelvis at Z=0.13m (-0.83m offset), pitched -86 deg backward (+Y)!
    p.loc["CTRL_Pelvis"] = (0.0, -0.05, -0.83 + 0.006 * breath)
    p.rot["CTRL_Pelvis"] = (-1.50, 0.0, -0.04)
    p.rot["CTRL_Spine_01"] = (+0.08 + 0.02 * breath, 0.0, 0.0)
    p.rot["CTRL_Spine_02"] = (+0.10 + 0.02 * breath, 0.0, 0.0)
    p.rot["CTRL_Head"] = (+0.32, 0.0, -0.22)
    p.rot["CTRL_FK_UpperArm_L"] = (-0.05, +0.72, -0.05)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, +0.35, -0.08)
    p.rot["CTRL_FK_UpperArm_R"] = (-0.05, -0.68, +0.05)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.32, +0.08)
    p.rot["CTRL_FK_Thigh_L"] = (-0.12, +0.16, 0.0)
    p.rot["CTRL_FK_Thigh_R"] = (-0.20, -0.18, 0.0)
    p.rot["CTRL_FK_Calf_L"] = (+0.14, 0.0, 0.0)
    p.rot["CTRL_FK_Calf_R"] = (+0.28, 0.0, 0.0)
    p.rot["CTRL_Cable_01"] = (+0.75, 0.25, 0.0)
    p.shapes["expr_pain"] = 0.40
    return p


def make_dead_front_pose() -> PoseSpec:
    """Held final pose of death_front — asymmetric natural collapse on front-right chest/hip."""
    p = make_prone_front_pose(0.0)
    p.loc["CTRL_Pelvis"] = (0.04, -0.18, -0.81)
    p.rot["CTRL_Pelvis"] = (+1.48, +0.14, -0.22)
    p.rot["CTRL_Spine_01"] = (-0.06, +0.06, -0.10)
    p.rot["CTRL_Head"] = (-0.28, -0.12, +0.68)
    p.rot["CTRL_FK_UpperArm_L"] = (0.06, -0.62, +0.08)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, -0.75, -0.06)
    p.rot["CTRL_FK_UpperArm_R"] = (0.08, +0.38, -0.04)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, +0.35, +0.06)
    p.rot["CTRL_FK_Thigh_L"] = (-0.14, +0.22, 0.0)
    p.rot["CTRL_FK_Calf_L"] = (+0.48, 0.0, 0.0)
    p.rot["CTRL_FK_Thigh_R"] = (0.04, -0.10, 0.0)
    p.rot["CTRL_FK_Calf_R"] = (+0.12, 0.0, 0.0)
    p.shapes = {"blink_l": 1.0, "blink_r": 1.0, "jaw_open": 0.18}
    p.finger_curl_l = 0.55
    p.finger_curl_r = 0.60
    return p


def make_dead_back_pose() -> PoseSpec:
    """Held final pose of death_back — distinct supine back-impact collapse (not mirrored!)."""
    p = make_prone_back_pose(0.0)
    p.loc["CTRL_Pelvis"] = (-0.05, +0.22, -0.82)
    p.rot["CTRL_Pelvis"] = (-1.48, -0.10, +0.26)
    p.rot["CTRL_Spine_01"] = (+0.08, -0.06, +0.12)
    p.rot["CTRL_Head"] = (+0.18, +0.12, -0.58)
    p.rot["CTRL_FK_UpperArm_L"] = (0.0, +0.48, -0.04)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, +0.28, -0.06)
    p.rot["CTRL_FK_UpperArm_R"] = (0.0, -0.78, +0.06)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.55, +0.15)
    p.rot["CTRL_FK_Thigh_L"] = (-0.08, +0.24, 0.0)
    p.rot["CTRL_FK_Calf_L"] = (+0.10, 0.0, 0.0)
    p.rot["CTRL_FK_Thigh_R"] = (-0.26, -0.26, 0.0)
    p.rot["CTRL_FK_Calf_R"] = (+0.42, 0.0, 0.0)
    p.shapes = {"blink_l": 1.0, "blink_r": 1.0, "jaw_open": 0.22}
    p.finger_curl_l = 0.62
    p.finger_curl_r = 0.48
    return p


def make_aim_pose(yaw_deg: float, pitch_deg: float) -> PoseSpec:
    """
    Calibrated 9-sample upper-body aim pose:
      yaw_deg in {-60, 0, +60} (-60 = Left, +60 = Right)
      pitch_deg in {-35, 0, +35} (-35 = Down, +35 = Up)
    Planted legs & pelvis remain 100% unrotated on the floor!
    """
    p = combat_ready_base(0.0)
    # In our Blender world space (Character faces -Y, +X Left, -X Right, +Z Up):
    # Turning left (-60 yaw) is +Z rotation; pitching up (+35 pitch) is -X rotation!
    yaw_r = math.radians(-yaw_deg)
    pit_r = math.radians(-pitch_deg)

    p.rot["CTRL_Spine_01"] = (+0.05 + pit_r * 0.20, 0.0, +0.05 + yaw_r * 0.22)
    p.rot["CTRL_Spine_02"] = (+0.04 + pit_r * 0.30, 0.0, +0.05 + yaw_r * 0.32)
    p.rot["CTRL_Spine_03"] = (+0.03 + pit_r * 0.35, 0.0, +0.06 + yaw_r * 0.34)
    p.rot["CTRL_Neck"]     = (pit_r * 0.08, 0.0, yaw_r * 0.06)
    p.rot["CTRL_Head"]     = (-0.10 + pit_r * 0.12, 0.0, yaw_r * 0.12)

    # Right cybernetic arm aims Wrist Emitter cleanly forward along the torso aim vector!
    p.rot["CTRL_FK_UpperArm_R"] = (0.15 - pit_r * 0.15, -0.26 + pit_r * 0.42, +1.24 + yaw_r * 0.15)
    p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.10, +0.26)
    p.rot["CTRL_FK_Hand_R"]     = (0.0, 0.0, 0.0)

    # Left organic arm stays in supporting balance guard without blocking muzzle
    p.rot["CTRL_FK_UpperArm_L"] = (0.18, +0.98, -0.48)
    p.rot["CTRL_FK_LowerArm_L"] = (0.0, +0.15, -0.92)
    p.finger_curl_r = 0.75
    p.finger_curl_l = 0.45
    p.shapes["expr_focus"] = 0.65
    return p


# =============================================================================
# DIALOGUE PERFORMANCE EVALUATOR (Synchronized to source/audio/dialogue.wav)
# =============================================================================

class DialogueEvaluator:
    def __init__(self):
        self.data = json.loads(DIALOGUE_ALIGN_PATH.read_text(encoding="utf-8"))
        self.total_frames = int(self.data["total_frames"])
        self.duration = float(self.data["duration_seconds"])
        self.phonemes = self.data["phonemes"]
        self.clauses = self.data["clauses"]
        self.blinks = self.data["blinks"]

    def eval_at(self, t: float) -> PoseSpec:
        p = combat_ready_base(t * 2.1)
        # Relax stance slightly for natural conversational authority
        p.loc["CTRL_Pelvis"] = (0.022 * math.sin(t * 0.85), 0.01 + 0.01 * math.cos(t * 0.7), -0.035 + 0.007 * math.sin(t * 2.2))

        # 1. Emotional Arc (Midway shift from urgent concern/warning -> focused console lock -> confident resolve!)
        if t < 6.85:
            urg = sstep(0.2, 0.9, t) * (1.0 - sstep(6.4, 6.95, t))
            p.shapes["expr_concern_sadness"] = 0.68 * urg
            p.shapes["expr_anger"] = 0.32 * sstep(2.8, 3.6, t) * (1.0 - sstep(6.4, 6.95, t))
            p.shapes["expr_focus"] = 0.35
        elif t < 9.85:
            foc = sstep(6.7, 7.2, t) * (1.0 - sstep(9.5, 10.1, t))
            p.shapes["expr_focus"] = 0.82 * foc + 0.25
            p.shapes["expr_surprise"] = 0.35 * bell(t, 7.15, 0.45)
        else:
            conf = sstep(9.6, 10.3, t) * (1.0 - 0.45 * sstep(self.duration - 0.6, self.duration, t))
            p.shapes["expr_joy_confidence"] = 0.82 * conf
            p.shapes["expr_focus"] = 0.32

        # 2. Co-articulated Visemes + Jaw & Tongue synchronization from sample-exact IPA phonemes!
        vis_weights: dict[str, float] = {}
        for ph in self.phonemes:
            vname = ph["viseme"]
            if vname == "V_SIL":
                continue
            ps, pe = ph["start_sec"], ph["end_sec"]
            # Co-articulation ramp: 45ms lead-in, 55ms trail-out
            if ps - 0.045 <= t <= pe + 0.055:
                mid = 0.5 * (ps + pe)
                hw = max(0.045, 0.5 * (pe - ps) + 0.045)
                w = bell(t, mid, hw) * clamp(0.55 + 0.55 * ph["energy"], 0.45, 1.0)
                if w > vis_weights.get(vname, 0.0):
                    vis_weights[vname] = w

        # Normalize concurrent viseme overlap so mouth never over-stretches
        v_sum = sum(vis_weights.values())
        if v_sum > 1.15:
            for k in vis_weights:
                vis_weights[k] = vis_weights[k] / v_sum * 1.15
        for k, v in vis_weights.items():
            p.shapes[k] = round(v, 4)

        # Also drive jaw & tongue bones gently in tandem with open vowels / alveolars for true hybrid bone+morph rig!
        jaw_bone_open = (
            0.18 * vis_weights.get("V_AA", 0.0)
            + 0.14 * vis_weights.get("V_OH", 0.0)
            + 0.11 * vis_weights.get("V_EH", 0.0)
            + 0.08 * vis_weights.get("V_KG", 0.0)
        )
        p.rot["CTRL_Jaw"] = (jaw_bone_open, 0.0, 0.0)

        # 3. Natural Blinks (asymmetric L/R capability!)
        for bl in self.blinks:
            bt = bl["time_sec"]
            bhw = bl["duration_sec"] * 0.55
            bw = bell(t, bt, bhw)
            if bw > 0.01:
                p.shapes["blink_l"] = max(p.shapes.get("blink_l", 0.0), bw * bl["asymmetry_lr"][0])
                p.shapes["blink_r"] = max(p.shapes.get("blink_r", 0.0), bw * bl["asymmetry_lr"][1])

        # 4. Saccadic Eye Gaze + Head Acting across the 5 tactical clauses
        gaze_x, gaze_z = 0.0, 0.0
        for cl in self.clauses:
            w_cl = pulse_env(t - (cl["start_sec"] - 0.18), 0.22, (cl["end_sec"] - cl["start_sec"]) + 0.05, (cl["end_sec"] - cl["start_sec"]) + 0.35)
            gaze_x += (-cl["gaze_target"]["yaw_deg"] / 45.0) * 0.32 * w_cl
            gaze_z += (cl["gaze_target"]["pitch_deg"] / 35.0) * 0.24 * w_cl
        # Micro-saccade life
        gaze_x += 0.025 * math.sin(t * 3.7)
        gaze_z += 0.015 * math.cos(t * 2.9)
        p.loc["CTRL_LookAt"] = (gaze_x, 0.0, gaze_z)
        p.rot["CTRL_Head"] = (
            -0.10 - gaze_z * 0.55 + 0.04 * math.sin(t * 2.6),
            0.03 * math.sin(t * 1.5),
            gaze_x * 0.65,
        )

        # 5. Intentional Body & Hand Gestures synchronized to the 5 clauses!
        # Clause 1 (0.35-2.66s): Left hand raises to tactical earpiece / temple comms
        w_g1 = pulse_env(t - 0.25, 0.35, 2.15, 2.65)
        # Clause 2 (2.88-6.84s): Urgent left-arm warning sweep outward ("fall back from the breach!")
        w_g2 = pulse_env(t - 2.80, 0.35, 3.60, 4.15)
        # Clause 3 (7.05-9.80s): Wrist-emitter phase damper stabilization (both hands meet in front of chest!)
        w_g3 = pulse_env(t - 6.90, 0.35, 2.55, 3.05)
        # Clause 4 & 5 (9.90-16.0s): Open-palm confirmation -> decisive forward lane-command gesture!
        w_g4 = pulse_env(t - 9.85, 0.35, 2.20, 2.75)
        w_g5 = pulse_env(t - 12.40, 0.35, 3.05, 3.75)

        if w_g1 > 0.01:
            g = PoseSpec()
            g.rot["CTRL_FK_UpperArm_L"] = (0.35, +0.35, -0.85)
            g.rot["CTRL_FK_LowerArm_L"] = (0.20, +0.45, -1.85)
            g.finger_curl_l = 0.65
            p = blend_poses(p, blend_poses(p, g, 1.0), w_g1)
        if w_g2 > 0.01:
            sweep = math.sin((t - 2.8) * 2.4)
            p.rot["CTRL_FK_UpperArm_L"] = (0.25, +0.55 - 0.18 * sweep, -0.75 + 0.32 * sweep)
            p.rot["CTRL_FK_LowerArm_L"] = (0.0, +0.20, -0.55 - 0.25 * abs(sweep))
            p.rot["CTRL_Spine_02"] = (-0.08, 0.0, 0.14 * sweep)
            p.finger_curl_l = 0.12
            p.finger_spread_l = 0.45 * w_g2
        if w_g3 > 0.01:
            # Right cybernetic forearm held across chest; left fingers tune emitter console!
            tune = 0.08 * math.sin(t * 9.0)
            p.rot["CTRL_FK_UpperArm_R"] = (0.35, -0.55, +1.08)
            p.rot["CTRL_FK_LowerArm_R"] = (0.15, -0.35, +1.35)
            p.rot["CTRL_FK_UpperArm_L"] = (0.32, +0.62, -1.02)
            p.rot["CTRL_FK_LowerArm_L"] = (0.10, +0.25, -1.22 + tune)
            p.finger_curl_l = 0.45 + 0.20 * math.sin(t * 11.0)
        if w_g4 > 0.01:
            p.rot["CTRL_FK_UpperArm_L"] = (0.20, +0.78, -0.68)
            p.rot["CTRL_FK_LowerArm_L"] = (-0.25, +0.35, -0.82)
            p.finger_curl_l = 0.15
        if w_g5 > 0.01:
            emph = bell(t, 13.4, 0.55) + 0.8 * bell(t, 14.9, 0.60)
            p.rot["CTRL_FK_UpperArm_R"] = (0.20, -0.45 + 0.12 * emph, +1.05)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.15, +0.42 - 0.18 * emph)
            p.rot["CTRL_Spine_03"] = (-0.06 - 0.05 * emph, 0.0, +0.10)
            p.finger_curl_r = 0.65

        return p


# =============================================================================
# MASTER 96-CLIP REGISTRY & FRAME-ACCURATE POSE EVALUATOR
# =============================================================================

@dataclass
class ClipDefinition:
    clip_id: str
    form: str              # 'loop' | 'one_shot' | 'additive' | 'pose'
    root_movement: str     # 'in_place' | 'root_motion'
    frames: int            # Frame range [0 .. frames] @ 30 FPS (0 for static poses -> exported as 2 identical frames [0,1])
    nominal_speed_cms: float
    intended_layer: str    # 'full_body' | 'locomotion' | 'upper_body_or_full' | 'additive_upper' | 'aim_layer'
    entry_state: str
    exit_state: str
    markers: list[tuple[int, str]] = field(default_factory=list)


def build_clip_catalog(dlg_frames: int) -> list[ClipDefinition]:
    cat = [
        # Idles (3)
        ClipDefinition("idle_relaxed", "loop", "in_place", 96, 0.0, "locomotion", "Idle", "Idle"),
        ClipDefinition("idle_combat",  "loop", "in_place", 78, 0.0, "locomotion", "Idle", "Idle"),
        ClipDefinition("idle_wounded", "loop", "in_place", 102, 0.0, "locomotion", "IdleWounded", "IdleWounded"),

        # 8-dir Walks @ 150 cm/s (8)
        *[ClipDefinition(f"walk_{d}", "loop", "in_place", 30, 150.0, "locomotion", "Locomotion", "Locomotion", [(0, "foot_contact_l"), (15, "foot_contact_r")]) for d in ("f","fl","l","bl","b","br","r","fr")],
        # 8-dir Runs @ 400 cm/s (8)
        *[ClipDefinition(f"run_{d}",  "loop", "in_place", 24, 400.0, "locomotion", "Locomotion", "Locomotion", [(2, "foot_contact_l"), (14, "foot_contact_r")]) for d in ("f","fl","l","bl","b","br","r","fr")],
        # Sprint @ 650 cm/s (1)
        ClipDefinition("sprint_f", "loop", "in_place", 18, 650.0, "locomotion", "Sprint", "Sprint", [(1, "foot_contact_l"), (10, "foot_contact_r")]),

        # Starts, Stops, Turns, Pivots (6)
        ClipDefinition("start_f",    "one_shot", "in_place", 16, 250.0, "locomotion", "Idle", "Locomotion", [(6, "foot_push_r"), (14, "foot_contact_l")]),
        ClipDefinition("stop_f",     "one_shot", "in_place", 18, 120.0, "locomotion", "Locomotion", "Idle", [(4, "foot_brake_r"), (13, "foot_plant_l")]),
        ClipDefinition("turn_l90",   "one_shot", "in_place", 18, 0.0,   "locomotion", "Idle", "Idle", [(7, "foot_step_l"), (15, "foot_step_r")]),
        ClipDefinition("turn_r90",   "one_shot", "in_place", 18, 0.0,   "locomotion", "Idle", "Idle", [(7, "foot_step_r"), (15, "foot_step_l")]),
        ClipDefinition("pivot_l180", "one_shot", "in_place", 20, 200.0, "locomotion", "Locomotion", "Locomotion", [(6, "pivot_plant_r"), (15, "pivot_push_l")]),
        ClipDefinition("pivot_r180", "one_shot", "in_place", 20, 200.0, "locomotion", "Locomotion", "Locomotion", [(6, "pivot_plant_l"), (15, "pivot_push_r")]),

        # Aerial (5)
        ClipDefinition("jump_start", "one_shot", "in_place", 14, 0.0, "full_body", "Ground", "Airborne", [(5, "jump_anticipation"), (9, "jump_takeoff")]),
        ClipDefinition("jump_air",   "loop",     "in_place", 24, 0.0, "full_body", "Airborne", "Airborne"),
        ClipDefinition("jump_land",  "one_shot", "in_place", 16, 0.0, "full_body", "Airborne", "Ground", [(2, "foot_land"), (12, "land_recovered")]),
        ClipDefinition("fall",       "loop",     "in_place", 27, 0.0, "full_body", "Falling", "Falling"),
        ClipDefinition("land_heavy", "one_shot", "in_place", 28, 0.0, "full_body", "Falling", "Ground", [(3, "foot_land_heavy"), (5, "hand_impact"), (22, "land_recovered")]),

        # Root-motion 2m Dashes (4) + In-place Blinks (2)
        ClipDefinition("dash_f",    "one_shot", "root_motion", 12, 500.0, "full_body", "Ground", "Ground", [(2, "dash_burst"), (9, "dash_brake")]),
        ClipDefinition("dash_b",    "one_shot", "root_motion", 12, 500.0, "full_body", "Ground", "Ground", [(2, "dash_burst"), (9, "dash_brake")]),
        ClipDefinition("dash_l",    "one_shot", "root_motion", 12, 500.0, "full_body", "Ground", "Ground", [(2, "dash_burst"), (9, "dash_brake")]),
        ClipDefinition("dash_r",    "one_shot", "root_motion", 12, 500.0, "full_body", "Ground", "Ground", [(2, "dash_burst"), (9, "dash_brake")]),
        ClipDefinition("blink_out", "one_shot", "in_place",    10, 0.0,   "full_body", "Ground", "BlinkTeleport", [(8, "blink_teleport")]),
        ClipDefinition("blink_in",  "one_shot", "in_place",    12, 0.0,   "full_body", "BlinkTeleport", "Ground", [(2, "blink_reappear"), (4, "foot_land")]),

        # Combat: Melee, Ranged, Reload (6)
        ClipDefinition("melee_1",      "one_shot", "in_place", 20, 0.0, "full_body", "Ready", "Ready", [(3, "blade_extend"), (7, "hit_window_start"), (11, "hit_window_end"), (14, "recovery_start")]),
        ClipDefinition("melee_2",      "one_shot", "in_place", 21, 0.0, "full_body", "Ready", "Ready", [(3, "blade_extend"), (7, "hit_window_start"), (12, "hit_window_end"), (15, "recovery_start")]),
        ClipDefinition("melee_3",      "one_shot", "in_place", 28, 0.0, "full_body", "Ready", "Ready", [(4, "blade_extend"), (10, "hit_window_start"), (15, "hit_window_end"), (20, "recovery_start")]),
        ClipDefinition("ranged_fire",  "one_shot", "in_place", 10, 0.0, "upper_body_or_full", "Ready", "Ready", [(3, "muzzle_fire")]),
        ClipDefinition("ranged_burst", "one_shot", "in_place", 18, 0.0, "upper_body_or_full", "Ready", "Ready", [(3, "muzzle_fire_1"), (7, "muzzle_fire_2"), (11, "muzzle_fire_3")]),
        ClipDefinition("reload",       "one_shot", "in_place", 54, 0.0, "upper_body_or_full", "Ready", "Ready", [(11, "cell_detach"), (24, "cell_swap"), (39, "cell_insert"), (45, "reload_complete")]),

        # Casts, Channel, Charge, Deploy, Uplink (16)
        ClipDefinition("cast_directional", "one_shot", "in_place", 22, 0.0, "upper_body_or_full", "Ready", "Ready", [(9, "cast_release")]),
        ClipDefinition("cast_ground",      "one_shot", "in_place", 28, 0.0, "full_body", "Ready", "Ready", [(13, "cast_release")]),
        ClipDefinition("cast_self",        "one_shot", "in_place", 24, 0.0, "full_body", "Ready", "Ready", [(11, "cast_release")]),

        ClipDefinition("channel_start",     "one_shot", "in_place", 14, 0.0, "full_body", "Ready", "Channeling", [(12, "channel_active")]),
        ClipDefinition("channel_loop",      "loop",     "in_place", 36, 0.0, "full_body", "Channeling", "Channeling", [(0, "channel_pulse"), (18, "channel_pulse")]),
        ClipDefinition("channel_end",       "one_shot", "in_place", 15, 0.0, "full_body", "Channeling", "Ready", [(4, "channel_complete")]),
        ClipDefinition("channel_interrupt", "one_shot", "in_place", 12, 0.0, "full_body", "Channeling", "Ready", [(1, "channel_interrupted")]),

        ClipDefinition("charge_start",   "one_shot", "in_place", 18, 0.0, "full_body", "Ready", "Charging", [(15, "charge_ready")]),
        ClipDefinition("charge_hold",    "loop",     "in_place", 30, 0.0, "full_body", "Charging", "Charging"),
        ClipDefinition("charge_release", "one_shot", "in_place", 20, 0.0, "full_body", "Charging", "Ready", [(6, "charge_release_fire")]),
        ClipDefinition("charge_cancel",  "one_shot", "in_place", 13, 0.0, "full_body", "Charging", "Ready", [(3, "charge_canceled")]),

        ClipDefinition("deploy", "one_shot", "in_place", 42, 0.0, "full_body", "Ready", "Ready", [(9, "deploy_pickup"), (23, "deploy_release"), (27, "deploy_armed")]),

        ClipDefinition("uplink_start",  "one_shot", "in_place", 20, 0.0, "full_body", "Ready", "Uplink", [(17, "uplink_connected")]),
        ClipDefinition("uplink_loop",   "loop",     "in_place", 45, 0.0, "full_body", "Uplink", "Uplink"),
        ClipDefinition("uplink_end",    "one_shot", "in_place", 16, 0.0, "full_body", "Uplink", "Ready", [(6, "uplink_complete")]),
        ClipDefinition("uplink_cancel", "one_shot", "in_place", 13, 0.0, "full_body", "Uplink", "Ready", [(3, "uplink_canceled")]),

        # Additive Hits (4)
        ClipDefinition("hit_f", "additive", "in_place", 10, 0.0, "additive_upper", "AnyLiving", "AnyLiving", [(2, "hit_peak")]),
        ClipDefinition("hit_b", "additive", "in_place", 10, 0.0, "additive_upper", "AnyLiving", "AnyLiving", [(2, "hit_peak")]),
        ClipDefinition("hit_l", "additive", "in_place", 10, 0.0, "additive_upper", "AnyLiving", "AnyLiving", [(2, "hit_peak")]),
        ClipDefinition("hit_r", "additive", "in_place", 10, 0.0, "additive_upper", "AnyLiving", "AnyLiving", [(2, "hit_peak")]),

        # Disables & Knockdowns & Sleep (15)
        ClipDefinition("stun_start",      "one_shot", "in_place", 16, 0.0, "full_body", "AnyLiving", "Stunned", [(3, "stun_impact")]),
        ClipDefinition("stun_loop",       "loop",     "in_place", 48, 0.0, "full_body", "Stunned", "Stunned"),
        ClipDefinition("stun_end",        "one_shot", "in_place", 18, 0.0, "full_body", "Stunned", "Ready", [(14, "control_restored")]),
        ClipDefinition("knockback",       "one_shot", "in_place", 24, 0.0, "full_body", "AnyLiving", "Ready", [(2, "knockback_impact"), (18, "foot_brace")]),
        ClipDefinition("knockup_start",   "one_shot", "in_place", 15, 0.0, "full_body", "AnyLiving", "KnockupAir", [(2, "knockup_launch")]),
        ClipDefinition("knockup_air",     "loop",     "in_place", 30, 0.0, "full_body", "KnockupAir", "KnockupAir"),
        ClipDefinition("knockdown_front", "one_shot", "in_place", 30, 0.0, "full_body", "AnyLiving", "ProneFront", [(16, "floor_impact")]),
        ClipDefinition("knockdown_back",  "one_shot", "in_place", 30, 0.0, "full_body", "AnyLiving", "ProneBack", [(15, "floor_impact")]),
        ClipDefinition("prone_front",     "loop",     "in_place", 54, 0.0, "full_body", "ProneFront", "ProneFront"),
        ClipDefinition("prone_back",      "loop",     "in_place", 54, 0.0, "full_body", "ProneBack", "ProneBack"),
        ClipDefinition("getup_front",     "one_shot", "in_place", 42, 0.0, "full_body", "ProneFront", "Ready", [(8, "hand_push"), (18, "knee_plant"), (27, "foot_plant")]),
        ClipDefinition("getup_back",      "one_shot", "in_place", 45, 0.0, "full_body", "ProneBack", "Ready", [(10, "hand_support"), (22, "foot_plant")]),
        ClipDefinition("sleep_start",     "one_shot", "in_place", 33, 0.0, "full_body", "AnyLiving", "Sleeping", [(24, "sleep_settled")]),
        ClipDefinition("sleep_loop",      "loop",     "in_place", 66, 0.0, "full_body", "Sleeping", "Sleeping"),
        ClipDefinition("sleep_end",       "one_shot", "in_place", 36, 0.0, "full_body", "Sleeping", "Ready", [(8, "awaken"), (28, "control_restored")]),

        # Lifecycle: Deaths, Held Dead Poses, Respawn (5)
        ClipDefinition("death_front", "one_shot", "in_place", 54, 0.0, "full_body", "AnyLiving", "DeadFront", [(22, "knee_drop"), (38, "body_fall")]),
        ClipDefinition("death_back",  "one_shot", "in_place", 57, 0.0, "full_body", "AnyLiving", "DeadBack",  [(20, "knee_buckle"), (40, "body_fall")]),
        ClipDefinition("dead_front",  "pose",     "in_place", 1,  0.0, "full_body", "DeadFront", "DeadFront"),
        ClipDefinition("dead_back",   "pose",     "in_place", 1,  0.0, "full_body", "DeadBack",  "DeadBack"),
        ClipDefinition("respawn",     "one_shot", "in_place", 60, 0.0, "full_body", "Dead", "Ready", [(14, "respawn_land"), (34, "system_online"), (54, "control_restored")]),

        # Social & Dialogue (4)
        ClipDefinition("greet",    "one_shot", "in_place", 54, 0.0, "full_body", "Idle", "Idle", [(16, "salute_gesture")]),
        ClipDefinition("victory",  "one_shot", "in_place", 72, 0.0, "full_body", "Idle", "Idle", [(18, "blade_flourish"), (42, "fist_pump")]),
        ClipDefinition("defeat",   "one_shot", "in_place", 75, 0.0, "full_body", "Idle", "Idle", [(22, "head_shake")]),
        ClipDefinition("dialogue", "one_shot", "in_place", dlg_frames, 0.0, "full_body", "Idle", "Idle", [(10, "speech_start"), (211, "emotional_shift"), (478, "speech_end")]),

        # 9-Sample Calibrated Aim Grid Poses (9)
        ClipDefinition("aim_down_left",    "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_down_center",  "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_down_right",   "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_level_left",   "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_level_center", "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_level_right",  "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_up_left",      "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_up_center",    "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
        ClipDefinition("aim_up_right",     "pose", "in_place", 1, 0.0, "aim_layer", "AimGrid", "AimGrid"),
    ]
    return cat


class MotionLibrary:
    def __init__(self):
        self.dialogue = DialogueEvaluator()
        self.catalog = build_clip_catalog(self.dialogue.total_frames)
        self.by_id = {c.clip_id: c for c in self.catalog}
        self._validate_against_csv()

    def _validate_against_csv(self):
        with CSV_PATH.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 96 and len(self.catalog) == 96, f"Expected 96 entries, got {len(self.catalog)}"
        for r in rows:
            cid = r["id"]
            assert cid in self.by_id, f"Missing clip ID {cid}"
            c = self.by_id[cid]
            assert c.form == r["form"], f"{cid} form mismatch: {c.form} != {r['form']}"
            assert c.root_movement == r["root_movement"], f"{cid} root mismatch"
            if r["duration_seconds"] != "pose":
                parts = r["duration_seconds"].replace("–", "-").split("-")
                lo, hi = float(parts[0]), float(parts[1])
                dur = c.frames / float(FPS)
                assert lo <= dur <= hi, f"{cid} duration {dur:.3f}s outside [{lo}, {hi}]s!"

    def _channel_pose(self, vib: float = 0.0) -> PoseSpec:
        p = combat_ready_base(0.0)
        p.loc["CTRL_Pelvis"] = (0.0, 0.04, -0.095)
        p.loc["CTRL_IK_Foot_L"] = (+0.055, -0.10, 0.0)
        p.loc["CTRL_IK_Foot_R"] = (-0.065, +0.12, 0.0)
        p.rot["CTRL_Spine_01"] = (+0.10, 0.0, +0.10)
        p.rot["CTRL_Spine_02"] = (+0.08, 0.0, +0.12)
        p.rot["CTRL_Spine_03"] = (+0.06, 0.0, +0.14)
        p.rot["CTRL_Head"] = (-0.18, 0.0, -0.25)
        # Right wrist emitter leveled straight forward; left hand braces under right forearm!
        p.rot["CTRL_FK_UpperArm_R"] = (0.18, -0.32 + 0.018 * vib, +1.18)
        p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.08, +0.28 + 0.02 * vib)
        p.rot["CTRL_FK_UpperArm_L"] = (0.28, +0.58, -1.12)
        p.rot["CTRL_FK_LowerArm_L"] = (0.10, +0.22, -1.05)
        p.finger_curl_r = 0.85
        p.finger_curl_l = 0.55
        p.shapes["expr_focus"] = 0.88
        return p

    def _charge_pose(self, tremor: float = 0.0) -> PoseSpec:
        p = combat_ready_base(0.0)
        p.loc["CTRL_Pelvis"] = (-0.03, +0.08, -0.14)
        p.loc["CTRL_IK_Foot_L"] = (+0.04, -0.14, 0.0)
        p.loc["CTRL_IK_Foot_R"] = (-0.06, +0.18, 0.0)
        p.rot["CTRL_Pelvis"] = (0.0, 0.0, -0.45)
        p.rot["CTRL_Spine_01"] = (+0.08, 0.0, -0.18)
        p.rot["CTRL_Spine_02"] = (+0.06, 0.0, -0.16)
        p.rot["CTRL_Head"] = (-0.14, 0.0, +0.62)
        # Right cyber-arm coiled far back accumulating energy; left arm aims forward!
        p.rot["CTRL_FK_UpperArm_R"] = (-0.15, -0.55 + 0.025 * tremor, -0.45)
        p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +1.55 + 0.03 * tremor)
        p.rot["CTRL_FK_UpperArm_L"] = (0.15, +0.35, -1.05)
        p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -0.25)
        p.finger_curl_r = 0.95
        p.finger_curl_l = 0.15
        p.shapes["expr_focus"] = 0.92
        return p

    def _uplink_pose(self, scan: float = 0.0) -> PoseSpec:
        p = combat_ready_base(0.0)
        p.loc["CTRL_Pelvis"] = (0.0, 0.0, -0.035)
        p.rot["CTRL_Head"] = (+0.32, 0.0, 0.08 * scan)
        p.loc["CTRL_LookAt"] = (0.08 * scan, 0.0, -0.25)
        p.rot["CTRL_FK_UpperArm_R"] = (0.35, -0.58, +1.12)
        p.rot["CTRL_FK_LowerArm_R"] = (0.20, -0.35, +1.38)
        p.rot["CTRL_FK_UpperArm_L"] = (0.32, +0.62, -1.04)
        p.rot["CTRL_FK_LowerArm_L"] = (0.12, +0.25, -1.24 + 0.06 * math.sin(scan * 5.0))
        p.finger_curl_l = 0.38 + 0.18 * math.cos(scan * 6.0)
        p.shapes["expr_focus"] = 0.72
        return p

    def _sleep_pose(self, breath: float = 0.0) -> PoseSpec:
        p = make_prone_back_pose(breath)
        # Calm side-reclined curled sleep posture on floor
        p.loc["CTRL_Pelvis"] = (0.04, 0.0, -0.82 + 0.005 * breath)
        p.rot["CTRL_Pelvis"] = (-1.38, +0.55, -0.15)
        p.rot["CTRL_Head"] = (+0.15, +0.25, -0.35)
        p.rot["CTRL_FK_UpperArm_L"] = (0.25, +0.65, -0.85)
        p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -1.35)
        p.rot["CTRL_FK_Thigh_L"] = (-0.55, +0.18, 0.0)
        p.rot["CTRL_FK_Calf_L"] = (+0.85, 0.0, 0.0)
        p.rot["CTRL_FK_Thigh_R"] = (-0.42, -0.12, 0.0)
        p.rot["CTRL_FK_Calf_R"] = (+0.68, 0.0, 0.0)
        p.shapes = {"blink_l": 1.0, "blink_r": 1.0}
        return p

    def evaluate(self, clip_id: str, frame: int) -> PoseSpec:
        c = self.by_id[clip_id]
        n_f = max(1, c.frames)
        u = clamp(frame / float(n_f), 0.0, 1.0)
        t = frame / float(FPS)
        th = 2.0 * math.pi * u

        # 1. IDLES
        if clip_id == "idle_relaxed":
            p = combat_ready_base(th * 2.0)
            p.loc["CTRL_IK_Foot_L"] = (+0.015, 0.0, 0.0)
            p.loc["CTRL_IK_Foot_R"] = (-0.015, 0.0, 0.0)
            p.rot["CTRL_IK_Foot_L"] = (0.0, 0.0, +0.06)
            p.rot["CTRL_IK_Foot_R"] = (0.0, 0.0, -0.06)
            p.loc["CTRL_Pelvis"] = (0.032 * math.sin(th), 0.008 * math.cos(th), -0.022 + 0.007 * math.sin(2 * th))
            p.rot["CTRL_Pelvis"] = (0.0, -0.035 * math.sin(th), 0.05 * math.cos(th))
            p.rot["CTRL_Spine_02"] = (0.02 * math.sin(2 * th), 0.02 * math.sin(th), -0.04 * math.cos(th))
            p.rot["CTRL_Head"] = (0.04 * math.sin(th + 0.5), 0.0, 0.14 * math.sin(th))
            p.loc["CTRL_LookAt"] = (0.12 * math.sin(th), 0.0, 0.04 * math.cos(th))
            p.rot["CTRL_FK_UpperArm_L"] = (0.05, +1.22, -0.08 + 0.04 * math.sin(th))
            p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -0.22)
            p.rot["CTRL_FK_UpperArm_R"] = (0.05, -1.20, +0.08 + 0.04 * math.sin(th))
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.25)
            p.finger_curl_l = 0.22
            p.finger_curl_r = 0.26
            p.shapes = {"blink_l": bell(u, 0.48, 0.05), "blink_r": bell(u, 0.48, 0.05)}
            return p

        if clip_id == "idle_combat":
            p = combat_ready_base(th)
            if bell(u, 0.62, 0.06) > 0.01:
                b = bell(u, 0.62, 0.06)
                p.shapes["blink_l"] = b
                p.shapes["blink_r"] = b
            return p

        if clip_id == "idle_wounded":
            p = combat_ready_base(th * 2.0)
            br = math.sin(th * 2.0)
            p.loc["CTRL_Pelvis"] = (+0.045 + 0.012 * math.sin(th), 0.03, -0.095 + 0.014 * br)
            p.rot["CTRL_FootRoll_R"] = (+0.28, 0.0, 0.0)
            p.rot["CTRL_Spine_01"] = (+0.18 - 0.03 * br, -0.14, +0.08)
            p.rot["CTRL_Spine_02"] = (+0.12 - 0.03 * br, -0.10, +0.06)
            p.rot["CTRL_Head"] = (-0.22 + 0.04 * br, +0.12, -0.14 + 0.10 * math.sin(th))
            # Left hand clutches right ribs; right arm hangs guarded
            p.rot["CTRL_FK_UpperArm_L"] = (0.28, +0.72, -1.18)
            p.rot["CTRL_FK_LowerArm_L"] = (0.12, +0.18, -1.15)
            p.rot["CTRL_FK_UpperArm_R"] = (0.15, -1.12, +0.22)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.48)
            p.shapes = {"expr_pain": 0.60 + 0.15 * br, "expr_focus": 0.35}
            return p

        # 2. WALK / RUN / SPRINT
        if clip_id.startswith("walk_"):
            return eval_gait("walk", clip_id.split("_", 1)[1], u)
        if clip_id.startswith("run_"):
            return eval_gait("run", clip_id.split("_", 1)[1], u)
        if clip_id == "sprint_f":
            return eval_gait("sprint", "f", u)

        # 3. STARTS, STOPS, TURNS, PIVOTS
        if clip_id == "start_f":
            idle_p = combat_ready_base(0.0)
            run_p = eval_gait("run", "f", 0.25)
            crouch = bell(u, 0.28, 0.26)
            b = blend_poses(idle_p, run_p, sstep(0.18, 1.0, u))
            px, py, pz = b.loc["CTRL_Pelvis"]
            b.loc["CTRL_Pelvis"] = (px, py - 0.06 * crouch, pz - 0.08 * crouch)
            rx, ry, rz = b.rot["CTRL_Spine_01"]
            b.rot["CTRL_Spine_01"] = (rx + 0.18 * crouch, ry, rz)
            return b

        if clip_id == "stop_f":
            run_p = eval_gait("run", "f", 0.0)
            idle_p = combat_ready_base(0.0)
            brake = bell(u, 0.35, 0.32)
            b = blend_poses(run_p, idle_p, sstep(0.12, 0.92, u))
            px, py, pz = b.loc["CTRL_Pelvis"]
            b.loc["CTRL_Pelvis"] = (px, py + 0.08 * brake, pz - 0.10 * brake)
            b.loc["CTRL_IK_Foot_R"] = (-0.04, -0.24 * brake + 0.075 * sstep(0.45, 1.0, u), 0.0)
            b.rot["CTRL_HeelPivot_R"] = (-0.28 * brake, 0.0, 0.0)
            return b

        if clip_id in ("turn_l90", "turn_r90"):
            sgn = +1.0 if clip_id == "turn_l90" else -1.0
            p = combat_ready_base(0.0)
            # Authentic 2-step turn footwork with lead-then-realign yaw!
            turn_env = bell(u, 0.48, 0.46)
            step1 = bell(u, 0.34, 0.22)
            step2 = bell(u, 0.72, 0.22)
            p.loc["CTRL_Pelvis"] = (0.03 * sgn * turn_env, 0.0, -0.06 - 0.04 * turn_env)
            p.rot["CTRL_Pelvis"] = (0.0, 0.0, -0.14 + 0.55 * sgn * turn_env)
            p.rot["CTRL_Spine_02"] = (+0.05, 0.0, +0.35 * sgn * bell(u, 0.32, 0.30))
            p.rot["CTRL_Head"] = (-0.12, 0.0, +0.45 * sgn * bell(u, 0.25, 0.25))
            if sgn > 0:
                p.loc["CTRL_IK_Foot_L"] = (+0.035 + 0.06 * step1, -0.065, 0.09 * step1)
                p.loc["CTRL_IK_Foot_R"] = (-0.040, +0.075, 0.08 * step2)
            else:
                p.loc["CTRL_IK_Foot_R"] = (-0.040 - 0.06 * step1, +0.075, 0.09 * step1)
                p.loc["CTRL_IK_Foot_L"] = (+0.035, -0.065, 0.08 * step2)
            return p

        if clip_id in ("pivot_l180", "pivot_r180"):
            sgn = +1.0 if clip_id == "pivot_l180" else -1.0
            p = eval_gait("run", "f", 0.0)
            coil = bell(u, 0.45, 0.40)
            p.loc["CTRL_Pelvis"] = (-0.06 * sgn * coil, +0.10 * coil, -0.22 * coil - 0.08)
            p.rot["CTRL_Pelvis"] = (+0.18 * coil, 0.14 * sgn * coil, +1.45 * sgn * bell(u, 0.52, 0.44))
            p.rot["CTRL_Spine_02"] = (+0.16 * coil, 0.0, +0.65 * sgn * coil)
            p.loc["CTRL_IK_Foot_L"] = (+0.08 * coil, -0.22 * (1.0 - coil), 0.12 * bell(u, 0.72, 0.20))
            p.loc["CTRL_IK_Foot_R"] = (-0.08 * coil, +0.18 * coil, 0.12 * bell(u, 0.28, 0.20))
            p.shapes["corr_knee_bend_l"] = 0.7 * coil
            p.shapes["corr_knee_bend_r"] = 0.7 * coil
            return p

        # 4. AERIAL: JUMP, FALL, LAND
        if clip_id == "jump_start":
            p = combat_ready_base(0.0)
            ant = bell(u, 0.34, 0.32)
            ext = sstep(0.42, 0.88, u)
            air_p = self.evaluate("jump_air", 0)
            b = blend_poses(p, air_p, ext)
            if ant > 0.01:
                px, py, pz = b.loc["CTRL_Pelvis"]
                b.loc["CTRL_Pelvis"] = (px, py + 0.05 * ant, pz - 0.24 * ant)
                b.rot["CTRL_Spine_01"] = (+0.28 * ant, 0.0, 0.0)
                b.rot["CTRL_FK_UpperArm_L"] = (-0.15 * ant, +1.15, +0.42 * ant)
                b.rot["CTRL_FK_UpperArm_R"] = (-0.15 * ant, -1.15, -0.42 * ant)
                b.shapes["corr_knee_bend_l"] = 0.85 * ant
                b.shapes["corr_knee_bend_r"] = 0.85 * ant
            return b

        if clip_id == "jump_air":
            p = combat_ready_base(th)
            p.loc["CTRL_Pelvis"] = (0.0, 0.0, +0.12 + 0.025 * math.sin(th))
            p.loc["CTRL_IK_Foot_L"] = (+0.04, -0.14, +0.34 + 0.03 * math.sin(th))
            p.loc["CTRL_IK_Foot_R"] = (-0.04, +0.10, +0.18 + 0.03 * math.cos(th))
            p.rot["CTRL_FootRoll_L"] = (+0.25, 0.0, 0.0)
            p.rot["CTRL_FootRoll_R"] = (+0.32, 0.0, 0.0)
            p.rot["CTRL_FK_UpperArm_L"] = (0.12, +0.62 + 0.06 * math.sin(th), -0.35)
            p.rot["CTRL_FK_UpperArm_R"] = (0.12, -0.58 - 0.06 * math.sin(th), +0.38)
            p.rot["CTRL_Cable_01"] = (-0.38 - 0.08 * math.sin(th), 0.0, 0.0)
            return p

        if clip_id == "jump_land":
            air_p = self.evaluate("jump_air", 0)
            idle_p = combat_ready_base(0.0)
            comp = bell(u, 0.32, 0.30)
            b = blend_poses(air_p, idle_p, sstep(0.0, 0.22, u))
            px, py, pz = idle_p.loc["CTRL_Pelvis"]
            b.loc["CTRL_Pelvis"] = (px, py + 0.04 * comp, pz - 0.22 * comp)
            b.rot["CTRL_Spine_01"] = (+0.06 + 0.22 * comp, 0.0, +0.05)
            b.shapes["corr_knee_bend_l"] = 0.75 * comp
            b.shapes["corr_knee_bend_r"] = 0.75 * comp
            return b

        if clip_id == "fall":
            # Distinct long-fall posture (extended arched limbs, upward windblown cable & strap!)
            p = combat_ready_base(0.0)
            p.loc["CTRL_Pelvis"] = (0.015 * math.sin(th), 0.0, +0.06 + 0.02 * math.cos(th))
            p.loc["CTRL_IK_Foot_L"] = (+0.10, +0.08, +0.10 + 0.05 * math.sin(th))
            p.loc["CTRL_IK_Foot_R"] = (-0.11, -0.06, +0.16 + 0.05 * math.cos(th))
            p.rot["CTRL_Spine_01"] = (-0.14, 0.04 * math.sin(th), 0.0)
            p.rot["CTRL_Spine_02"] = (-0.12, 0.0, 0.06 * math.cos(th))
            p.rot["CTRL_Head"] = (+0.28, 0.0, 0.08 * math.sin(th))
            p.rot["CTRL_FK_UpperArm_L"] = (-0.15, -0.35 + 0.18 * math.sin(th), -0.20)
            p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -0.45)
            p.rot["CTRL_FK_UpperArm_R"] = (-0.15, +0.35 - 0.18 * math.cos(th), +0.20)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.45)
            p.rot["CTRL_Cable_01"] = (-0.85 - 0.15 * math.sin(2 * th), 0.12 * math.cos(th), 0.0)
            p.rot["CTRL_Strap_01"] = (-0.75 - 0.14 * math.cos(2 * th), -0.35, 0.0)
            p.shapes["expr_surprise"] = 0.55
            return p

        if clip_id == "land_heavy":
            p = combat_ready_base(0.0)
            comp = pulse_env(u, 0.14, 0.45, 0.88)
            p.props["ik_fk_arm_l"] = comp
            p.loc["CTRL_Pelvis"] = (0.0, 0.06 * comp, -0.055 - 0.56 * comp)
            p.loc["CTRL_IK_Foot_L"] = (+0.06, -0.18 * comp - 0.065 * (1 - comp), 0.0)
            p.loc["CTRL_IK_Foot_R"] = (-0.06, +0.28 * comp + 0.075 * (1 - comp), 0.0)
            p.loc["CTRL_IK_Hand_L"] = (-0.54, -0.38, -1.42)  # Plants left hand onto Z=0.04m floor!
            p.rot["CTRL_Pelvis"] = (+0.42 * comp, 0.0, -0.14)
            p.rot["CTRL_Spine_01"] = (+0.06 + 0.45 * comp, 0.0, +0.05)
            p.rot["CTRL_Spine_02"] = (+0.05 + 0.35 * comp, 0.0, +0.05)
            p.rot["CTRL_Head"] = (-0.12 - 0.55 * comp, 0.0, 0.0)
            p.shapes["expr_pain"] = 0.55 * bell(u, 0.25, 0.20)
            p.shapes["expr_focus"] = 0.75 * sstep(0.35, 0.75, u)
            p.shapes["corr_knee_bend_l"] = 0.95 * comp
            p.shapes["corr_knee_bend_r"] = 0.95 * comp
            return p

        # 5. ROOT-MOTION DASHES (Exact 2.000 m displacement!) & BLINKS
        if clip_id in ("dash_f", "dash_b", "dash_l", "dash_r"):
            vecs = {"dash_f": (0.0, -2.0), "dash_b": (0.0, +2.0), "dash_l": (+2.0, 0.0), "dash_r": (-2.0, 0.0)}
            rx, ry = vecs[clip_id]
            prog = sstep(0.08, 0.88, u)
            burst = bell(u, 0.45, 0.42)
            p = combat_ready_base(0.0)
            # Root translates exact 2.000 m; Pelvis & IK feet track root + athletic dash crouch!
            p.loc["CTRL_Root"] = (rx * prog, ry * prog, 0.0)
            p.loc["CTRL_Pelvis"] = (rx * prog, ry * prog, -0.055 - 0.20 * burst)
            p.loc["CTRL_IK_Foot_L"] = (rx * prog + 0.04, ry * prog - 0.14 * burst - 0.065 * (1 - burst), 0.14 * burst)
            p.loc["CTRL_IK_Foot_R"] = (rx * prog - 0.04, ry * prog + 0.18 * burst + 0.075 * (1 - burst), 0.08 * burst)
            p.rot["CTRL_Spine_01"] = (+0.06 - (ry * 0.16) * burst, +(rx * 0.16) * burst, 0.0)
            p.rot["CTRL_Spine_02"] = (+0.05 - (ry * 0.14) * burst, +(rx * 0.14) * burst, 0.0)
            p.rot["CTRL_Head"] = (-0.12 + (ry * 0.24) * burst, 0.0, 0.0)
            p.rot["CTRL_Cable_01"] = (-0.45 * burst, 0.0, 0.0)
            p.shapes["expr_focus"] = 0.85
            return p

        if clip_id == "blink_out":
            # In-place! Zero baked root teleport!
            p = combat_ready_base(0.0)
            coil = sstep(0.0, 0.65, u)
            snap = sstep(0.55, 1.0, u)
            p.loc["CTRL_Pelvis"] = (0.0, 0.0, -0.055 - 0.16 * coil + 0.24 * snap)
            p.rot["CTRL_FK_UpperArm_L"] = (0.30, +0.65, -1.15 * coil - 0.32 * (1 - coil))
            p.rot["CTRL_FK_UpperArm_R"] = (0.30, -0.65, +1.15 * coil + 0.38 * (1 - coil))
            p.shapes["expr_focus"] = 0.90
            return p

        if clip_id == "blink_in":
            p = combat_ready_base(0.0)
            drop = 1.0 - sstep(0.0, 0.45, u)
            settle = bell(u, 0.48, 0.32)
            p.loc["CTRL_Pelvis"] = (0.0, 0.0, -0.055 + 0.18 * drop - 0.12 * settle)
            p.loc["CTRL_IK_Foot_L"] = (+0.035, -0.065, 0.14 * drop)
            p.loc["CTRL_IK_Foot_R"] = (-0.040, +0.075, 0.14 * drop)
            p.rot["CTRL_FK_UpperArm_L"] = (0.18, +1.06 - 0.45 * settle, -0.32)
            p.rot["CTRL_FK_UpperArm_R"] = (0.22, -0.98 + 0.45 * settle, +0.38)
            return p

        # 6. MELEE 1-2-3, RANGED FIRE/BURST, RELOAD
        if clip_id == "melee_1":
            # Diagonal high-right -> low-left forearm-blade slash
            p = combat_ready_base(0.0)
            blade_ext = pulse_env(u, 0.12, 0.78, 0.95)
            p.loc["CTRL_Blade_R"] = (-0.24 * blade_ext, 0.0, 0.0)
            wind = bell(u, 0.22, 0.20)
            slash = sstep(0.26, 0.56, u) * (1.0 - sstep(0.68, 0.96, u))
            p.loc["CTRL_Pelvis"] = (-0.04 * wind + 0.06 * slash, -0.10 * slash, -0.08 - 0.06 * slash)
            p.rot["CTRL_Spine_01"] = (-0.12 * slash, 0.0, -0.35 * wind + 0.55 * slash)
            p.rot["CTRL_Spine_02"] = (-0.10 * slash, 0.0, -0.30 * wind + 0.50 * slash)
            p.rot["CTRL_Head"] = (+0.15, 0.0, +0.45 * wind - 0.75 * slash)
            p.rot["CTRL_FK_UpperArm_R"] = (
                0.20 - 0.45 * wind + 0.35 * slash,
                -0.98 + 1.15 * wind - 0.35 * slash,
                +0.38 - 0.55 * wind + 1.45 * slash,
            )
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.92 + 0.35 * wind - 0.65 * slash)
            p.finger_curl_r = 0.95
            p.shapes["expr_anger"] = 0.65 * slash
            p.shapes["expr_focus"] = 0.75
            return p

        if clip_id == "melee_2":
            # Reverse backhand low-left -> high-right slash with opposite weight shift!
            p = combat_ready_base(0.0)
            blade_ext = pulse_env(u, 0.12, 0.80, 0.96)
            p.loc["CTRL_Blade_R"] = (-0.25 * blade_ext, 0.0, 0.0)
            prep = bell(u, 0.24, 0.22)
            slash = sstep(0.28, 0.58, u) * (1.0 - sstep(0.70, 0.96, u))
            p.loc["CTRL_Pelvis"] = (+0.07 * prep - 0.08 * slash, -0.08 * slash, -0.10 - 0.05 * prep)
            p.rot["CTRL_Spine_01"] = (-0.14 * prep, 0.0, +0.48 * prep - 0.58 * slash)
            p.rot["CTRL_Spine_02"] = (-0.10 * prep, 0.0, +0.42 * prep - 0.52 * slash)
            p.rot["CTRL_Head"] = (+0.16, 0.0, -0.60 * prep + 0.80 * slash)
            p.rot["CTRL_FK_UpperArm_R"] = (
                0.25,
                -0.85 - 0.25 * prep + 0.95 * slash,
                +1.45 * prep - 0.65 * slash + 0.38 * (1 - prep - slash),
            )
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, +0.45 * slash, +1.15 * prep + 0.15 * slash + 0.92 * (1 - prep - slash))
            p.finger_curl_r = 0.95
            p.shapes["expr_anger"] = 0.70 * slash
            return p

        if clip_id == "melee_3":
            # Committed overhead-diagonal lunging finisher with deep follow-through!
            p = combat_ready_base(0.0)
            blade_ext = pulse_env(u, 0.10, 0.82, 0.96)
            p.loc["CTRL_Blade_R"] = (-0.28 * blade_ext, 0.0, 0.0)
            coil = bell(u, 0.24, 0.22)
            cleave = sstep(0.30, 0.54, u) * (1.0 - sstep(0.72, 0.96, u))
            p.loc["CTRL_Pelvis"] = (0.0, +0.08 * coil - 0.22 * cleave, -0.06 + 0.06 * coil - 0.24 * cleave)
            p.loc["CTRL_IK_Foot_R"] = (-0.04, +0.075 - 0.28 * cleave, 0.12 * bell(u, 0.38, 0.12))
            p.rot["CTRL_Spine_01"] = (+0.18 * coil - 0.34 * cleave, 0.0, -0.45 * coil + 0.65 * cleave)
            p.rot["CTRL_Spine_02"] = (+0.15 * coil - 0.28 * cleave, 0.0, -0.40 * coil + 0.58 * cleave)
            p.rot["CTRL_Head"] = (-0.15 * coil + 0.42 * cleave, 0.0, +0.50 * coil - 0.80 * cleave)
            p.rot["CTRL_FK_UpperArm_R"] = (0.10, +1.25 * coil - 0.95 * cleave - 0.98 * (1 - coil - cleave), +0.20 + 1.15 * cleave)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.92 * (1 - cleave) + 0.20 * cleave)
            p.shapes["corr_shoulder_up_r"] = coil
            p.shapes["expr_anger"] = 0.85 * cleave
            return p

        if clip_id in ("ranged_fire", "ranged_burst"):
            p = make_aim_pose(0.0, 0.0)
            env = pulse_env(u, 0.18, 0.75, 1.0)
            if clip_id == "ranged_fire":
                kick = bell(u, 0.35, 0.22)
            else:
                kick = 0.75 * bell(u, 3 / 18.0, 0.12) + 0.88 * bell(u, 7 / 18.0, 0.12) + 1.0 * bell(u, 11 / 18.0, 0.14)
            p.rot["CTRL_FK_UpperArm_R"] = (0.15 + 0.18 * kick, -0.32 + 0.22 * kick, +1.18 - 0.08 * kick)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, -0.10, +0.32 + 0.28 * kick)
            p.rot["CTRL_Spine_03"] = (-0.03 + 0.08 * kick, 0.0, +0.06 - 0.08 * kick)
            return blend_poses(combat_ready_base(0.0), p, env)

        if clip_id == "reload":
            p = combat_ready_base(0.0)
            # Bring right wrist emitter across chest; left hand detaches cell (f11), swaps at belt (f24), inserts (f39)!
            hold_em = pulse_env(u, 0.14, 0.84, 0.98)
            in_hand = pulse_env(u - 10 / 54.0, 0.04, 28 / 54.0, 30 / 54.0)
            at_belt = bell(u, 24 / 54.0, 0.16)
            slap = bell(u, 45 / 54.0, 0.08)

            p.props["cell_in_hand_l"] = sstep(9.5, 11.5, float(frame)) * (1.0 - sstep(38.0, 40.0, float(frame)))
            p.rot["CTRL_Head"] = (+0.28 * hold_em, 0.0, -0.12 * hold_em)
            p.rot["CTRL_FK_UpperArm_R"] = (0.32 * hold_em + 0.22 * (1 - hold_em), -0.52 * hold_em - 0.98 * (1 - hold_em), +1.12 * hold_em + 0.38 * (1 - hold_em))
            p.rot["CTRL_FK_LowerArm_R"] = (0.20 * hold_em, -0.35 * hold_em, +1.32 * hold_em + 0.92 * (1 - hold_em) + 0.12 * slap)

            # Left arm reaches to emitter breech -> drops to belt pouch -> returns to emitter breech!
            reach_em = pulse_env(u, 0.16, 0.84, 0.98) * (1.0 - at_belt)
            p.rot["CTRL_FK_UpperArm_L"] = (
                0.30 * reach_em + 0.10 * at_belt + 0.18 * (1 - reach_em - at_belt),
                +0.55 * reach_em + 1.18 * at_belt + 1.06 * (1 - reach_em - at_belt),
                -1.08 * reach_em - 0.25 * at_belt - 0.32 * (1 - reach_em - at_belt),
            )
            p.rot["CTRL_FK_LowerArm_L"] = (0.12 * reach_em, +0.28 * reach_em, -1.24 * reach_em - 0.55 * at_belt - 0.78 * (1 - reach_em - at_belt))
            p.finger_curl_l = 0.85 * in_hand + 0.32 * (1 - in_hand)
            p.shapes["expr_focus"] = 0.78 * hold_em + 0.38 * (1 - hold_em)
            return p

        # 7. CASTS, CHANNEL, CHARGE, DEPLOY, UPLINK
        if clip_id == "cast_directional":
            p = combat_ready_base(0.0)
            coil = bell(u, 0.25, 0.22)
            thrust = pulse_env(u - 0.28, 0.14, 0.35, 0.68)
            p.rot["CTRL_Spine_02"] = (+0.12 * thrust, 0.0, +0.28 * coil - 0.38 * thrust)
            p.rot["CTRL_FK_UpperArm_L"] = (0.22, +0.85 * coil + 0.12 * thrust + 1.06 * (1 - coil - thrust), -1.15 * coil - 1.38 * thrust - 0.32 * (1 - coil - thrust))
            p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -1.35 * coil - 0.10 * thrust - 0.78 * (1 - coil - thrust))
            p.finger_curl_l = 0.85 * coil + 0.05 * thrust + 0.32 * (1 - coil - thrust)
            p.finger_spread_l = 0.65 * thrust
            p.shapes["expr_focus"] = 0.85
            return p

        if clip_id == "cast_ground":
            p = combat_ready_base(0.0)
            act = pulse_env(u, 0.28, 0.62, 0.96)
            p.loc["CTRL_Pelvis"] = (0.0, 0.05 * act, -0.055 - 0.28 * act)
            p.rot["CTRL_Spine_01"] = (+0.32 * act, 0.0, -0.18 * act)
            p.rot["CTRL_Head"] = (+0.22 * act - 0.12 * (1 - act), 0.0, 0.0)
            p.loc["CTRL_LookAt"] = (0.0, 0.0, -0.55 * act)
            p.rot["CTRL_FK_UpperArm_L"] = (0.25, +0.72 * act + 1.06 * (1 - act), -0.95 * act - 0.32 * (1 - act))
            p.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -0.25 * act - 0.78 * (1 - act))
            p.finger_spread_l = 0.60 * act
            p.shapes["corr_knee_bend_l"] = 0.65 * act
            p.shapes["corr_knee_bend_r"] = 0.65 * act
            return p

        if clip_id == "cast_self":
            p = combat_ready_base(0.0)
            cross = bell(u, 0.28, 0.24)
            burst = pulse_env(u - 0.34, 0.14, 0.36, 0.64)
            p.rot["CTRL_Spine_02"] = (+0.18 * cross - 0.20 * burst, 0.0, 0.0)
            p.rot["CTRL_Head"] = (+0.18 * cross - 0.28 * burst, 0.0, 0.0)
            p.rot["CTRL_FK_UpperArm_L"] = (0.25 * cross, +0.55 * cross + 0.25 * burst + 1.06 * (1 - cross - burst), -1.25 * cross + 0.25 * burst - 0.32 * (1 - cross - burst))
            p.rot["CTRL_FK_UpperArm_R"] = (0.25 * cross, -0.55 * cross - 0.25 * burst - 0.98 * (1 - cross - burst), +1.25 * cross - 0.25 * burst + 0.38 * (1 - cross - burst))
            p.shapes["expr_focus"] = 0.90
            return p

        if clip_id == "channel_start":
            return blend_poses(combat_ready_base(0.0), self._channel_pose(0.0), sstep(0.0, 1.0, u))
        if clip_id == "channel_loop":
            return self._channel_pose(math.sin(2.0 * th))
        if clip_id == "channel_end":
            return blend_poses(self._channel_pose(0.0), combat_ready_base(0.0), sstep(0.15, 1.0, u))
        if clip_id == "channel_interrupt":
            # Forced shock interruption distinct from clean completion!
            base = blend_poses(self._channel_pose(0.0), combat_ready_base(0.0), sstep(0.25, 1.0, u))
            jolt = bell(u, 0.28, 0.26)
            px, py, pz = base.loc["CTRL_Pelvis"]
            base.loc["CTRL_Pelvis"] = (px - 0.06 * jolt, py + 0.10 * jolt, pz - 0.06 * jolt)
            base.rot["CTRL_Spine_02"] = (-0.24 * jolt, -0.18 * jolt, -0.25 * jolt)
            base.rot["CTRL_FK_UpperArm_L"] = (0.10, +0.45, +0.25 * jolt - 0.32 * (1 - jolt))
            base.rot["CTRL_FK_UpperArm_R"] = (0.10, -0.45, -0.25 * jolt + 0.38 * (1 - jolt))
            base.shapes["expr_pain"] = 0.78 * jolt
            return base

        if clip_id == "charge_start":
            return blend_poses(combat_ready_base(0.0), self._charge_pose(0.0), sstep(0.0, 1.0, u))
        if clip_id == "charge_hold":
            return self._charge_pose(math.sin(2.0 * th))
        if clip_id == "charge_release":
            cp = self._charge_pose(0.0)
            rel = combat_ready_base(0.0)
            blast = pulse_env(u, 0.26, 0.58, 0.96)
            b = blend_poses(cp, rel, sstep(0.15, 0.95, u))
            if blast > 0.01:
                b.loc["CTRL_Pelvis"] = (+0.04 * blast, -0.16 * blast, -0.14)
                b.rot["CTRL_Pelvis"] = (0.0, 0.0, +0.35 * blast)
                b.rot["CTRL_Spine_02"] = (+0.18 * blast, 0.0, +0.42 * blast)
                b.rot["CTRL_FK_UpperArm_R"] = (0.18, -0.15, +1.35 * blast + 0.38 * (1 - blast))
                b.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.12 * blast + 0.92 * (1 - blast))
                b.shapes["expr_anger"] = 0.65 * blast
            return b
        if clip_id == "charge_cancel":
            b = blend_poses(self._charge_pose(0.0), combat_ready_base(0.0), sstep(0.0, 1.0, u))
            vent = bell(u, 0.35, 0.30)
            b.rot["CTRL_Spine_02"] = (+0.12 * vent, 0.0, 0.0)
            return b

        if clip_id == "deploy":
            # Physical beacon placement onto floor Z=0.000m with left-hand grasp & deep 3-point crouch!
            p = combat_ready_base(0.0)
            reach_dock = bell(u, 8 / 42.0, 0.16)
            crouch = pulse_env(u - 9 / 42.0, 0.20, 17 / 42.0, 29 / 42.0)

            in_hand_w = sstep(7.5, 9.5, float(frame)) * (1.0 - sstep(21.5, 23.5, float(frame)))
            planted_w = sstep(21.5, 23.5, float(frame))
            p.props["beacon_in_hand_l"] = in_hand_w
            p.props["beacon_planted"] = planted_w
            p.props["ik_fk_arm_l"] = max(reach_dock, crouch)

            p.loc["CTRL_Pelvis"] = (0.0, 0.04 * crouch, -0.055 - 0.56 * crouch)
            p.loc["CTRL_IK_Foot_R"] = (-0.04, +0.075 + 0.28 * crouch, 0.0)
            p.rot["CTRL_Pelvis"] = (+0.45 * crouch, 0.0, -0.14 - 0.35 * reach_dock)
            p.rot["CTRL_Spine_01"] = (+0.06 + 0.45 * crouch, 0.0, -0.25 * reach_dock)
            p.rot["CTRL_Spine_02"] = (+0.05 + 0.35 * crouch, 0.0, 0.0)
            p.rot["CTRL_Head"] = (-0.12 - 0.45 * crouch, 0.0, 0.0)
            # IK hand reaches dock (-0.09, +0.14, 0.88) at f8 -> guides beacon right onto floor (0.0, -0.45, 0.03) at f18..24!
            hx = -0.79 * reach_dock - 0.705 * (1.0 - reach_dock)
            hy = +0.135 * reach_dock - 0.45 * (1.0 - reach_dock)
            hz = -0.58 * reach_dock - 1.43 * (1.0 - reach_dock)
            p.loc["CTRL_IK_Hand_L"] = (hx, hy, hz)
            p.finger_curl_l = 0.75 if (8 <= frame <= 26) else 0.32
            p.shapes["corr_knee_bend_l"] = 0.95 * crouch
            p.shapes["corr_knee_bend_r"] = 0.95 * crouch
            return p

        if clip_id == "uplink_start":
            return blend_poses(combat_ready_base(0.0), self._uplink_pose(0.0), sstep(0.0, 1.0, u))
        if clip_id == "uplink_loop":
            return self._uplink_pose(math.sin(th))
        if clip_id == "uplink_end":
            b = blend_poses(self._uplink_pose(0.0), combat_ready_base(0.0), sstep(0.25, 1.0, u))
            b.shapes["expr_joy_confidence"] = 0.65 * bell(u, 0.38, 0.32)
            return b
        if clip_id == "uplink_cancel":
            b = blend_poses(self._uplink_pose(0.0), combat_ready_base(0.0), sstep(0.10, 0.95, u))
            swipe = bell(u, 0.28, 0.24)
            b.rot["CTRL_FK_UpperArm_L"] = (0.20, +0.65, +0.15 * swipe - 0.32 * (1 - swipe))
            return b

        # 8. ADDITIVE HITS (Exact zero delta at frame 0 & frame N relative to combat_ready_base(0.0)!)
        if clip_id in ("hit_f", "hit_b", "hit_l", "hit_r"):
            p = combat_ready_base(0.0)
            imp = math.sin(math.pi * u) * ((1.0 - u) ** 0.75)  # Exact 0 at u=0 and u=1, sharp peak at u~0.28!
            if clip_id == "hit_f":
                p.loc["CTRL_Pelvis"] = (0.0, 0.015 + 0.05 * imp, -0.055 - 0.02 * imp)
                p.rot["CTRL_Spine_01"] = (+0.06 - 0.22 * imp, 0.0, +0.05)
                p.rot["CTRL_Spine_02"] = (+0.05 - 0.26 * imp, 0.0, +0.05 - 0.12 * imp)
                p.rot["CTRL_Head"] = (-0.12 - 0.32 * imp, 0.0, -0.02 + 0.18 * imp)
            elif clip_id == "hit_b":
                p.loc["CTRL_Pelvis"] = (0.0, 0.015 - 0.05 * imp, -0.055 - 0.02 * imp)
                p.rot["CTRL_Spine_01"] = (+0.06 + 0.24 * imp, 0.0, +0.05)
                p.rot["CTRL_Spine_02"] = (+0.05 + 0.26 * imp, 0.0, +0.05 + 0.10 * imp)
                p.rot["CTRL_Head"] = (-0.12 + 0.30 * imp, 0.0, -0.02)
            elif clip_id == "hit_l":
                p.loc["CTRL_Pelvis"] = (-0.045 * imp, 0.015, -0.055 - 0.02 * imp)
                p.rot["CTRL_Spine_01"] = (+0.06, -0.22 * imp, +0.05 - 0.18 * imp)
                p.rot["CTRL_Spine_02"] = (+0.05, -0.24 * imp, +0.05 - 0.20 * imp)
                p.rot["CTRL_Head"] = (-0.12, -0.25 * imp, -0.02 - 0.25 * imp)
            else:  # hit_r
                p.loc["CTRL_Pelvis"] = (+0.045 * imp, 0.015, -0.055 - 0.02 * imp)
                p.rot["CTRL_Spine_01"] = (+0.06, +0.22 * imp, +0.05 + 0.18 * imp)
                p.rot["CTRL_Spine_02"] = (+0.05, +0.24 * imp, +0.05 + 0.20 * imp)
                p.rot["CTRL_Head"] = (-0.12, +0.25 * imp, -0.02 + 0.25 * imp)
            p.shapes["expr_pain"] = 0.85 * imp
            return p

        # 9. DISABLES, KNOCKDOWNS, PRONE, GETUPS, SLEEP
        if clip_id in ("stun_start", "stun_loop", "stun_end"):
            sway_ph = th if clip_id == "stun_loop" else 0.0
            st = combat_ready_base(0.0)
            st.loc["CTRL_Pelvis"] = (0.05 * math.sin(sway_ph), 0.04 * math.cos(sway_ph), -0.09)
            st.rot["CTRL_Spine_01"] = (+0.14 + 0.10 * math.cos(sway_ph), 0.14 * math.sin(sway_ph), 0.0)
            st.rot["CTRL_Head"] = (+0.24 + 0.14 * math.sin(sway_ph + 1.0), 0.18 * math.cos(sway_ph), 0.22 * math.sin(sway_ph))
            st.rot["CTRL_FK_UpperArm_L"] = (0.05, +1.28, -0.05 + 0.12 * math.sin(sway_ph))
            st.rot["CTRL_FK_LowerArm_L"] = (0.0, 0.0, -0.18)
            st.rot["CTRL_FK_UpperArm_R"] = (0.05, -1.26, +0.05 - 0.12 * math.cos(sway_ph))
            st.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.20)
            st.shapes = {"blink_l": 0.50, "blink_r": 0.35, "jaw_open": 0.22, "expr_concern_sadness": 0.45}
            if clip_id == "stun_start":
                return blend_poses(combat_ready_base(0.0), st, sstep(0.0, 1.0, u))
            if clip_id == "stun_loop":
                return st
            # stun_end: head shake + crisp recovery!
            b = blend_poses(st, combat_ready_base(0.0), sstep(0.15, 1.0, u))
            shake = math.sin(u * 5.0 * math.pi) * bell(u, 0.42, 0.32)
            hx, hy, hz = b.rot["CTRL_Head"]
            b.rot["CTRL_Head"] = (hx, hy, hz + 0.38 * shake)
            return b

        if clip_id == "knockback":
            p = combat_ready_base(0.0)
            kb = pulse_env(u, 0.14, 0.58, 0.96)
            p.loc["CTRL_Pelvis"] = (0.0, +0.12 * kb, -0.055 - 0.18 * kb)
            p.loc["CTRL_IK_Foot_R"] = (-0.05, +0.26 * kb + 0.075 * (1 - kb), 0.0)
            p.rot["CTRL_Spine_01"] = (+0.28 * kb, 0.0, 0.0)
            p.rot["CTRL_Spine_02"] = (+0.24 * kb, 0.0, 0.0)
            p.rot["CTRL_FK_UpperArm_L"] = (0.20, +0.55 * kb + 1.06 * (1 - kb), -0.95 * kb - 0.32 * (1 - kb))
            p.rot["CTRL_FK_UpperArm_R"] = (0.20, -0.55 * kb - 0.98 * (1 - kb), +0.95 * kb + 0.38 * (1 - kb))
            p.shapes["expr_pain"] = 0.72 * kb
            return p

        if clip_id in ("knockup_start", "knockup_air"):
            ku = combat_ready_base(0.0)
            ku.props["ik_fk_leg_l"] = 0.0
            ku.props["ik_fk_leg_r"] = 0.0
            flail = math.sin(th) if clip_id == "knockup_air" else 0.0
            ku.loc["CTRL_Pelvis"] = (0.0, 0.0, +0.22 + 0.04 * flail)
            ku.rot["CTRL_Pelvis"] = (-0.52, 0.08 * flail, 0.0)
            ku.rot["CTRL_Spine_01"] = (-0.22, 0.0, 0.10 * flail)
            ku.rot["CTRL_Head"] = (-0.32, 0.0, 0.0)
            ku.rot["CTRL_FK_UpperArm_L"] = (-0.25, +0.15 + 0.20 * flail, +0.35)
            ku.rot["CTRL_FK_UpperArm_R"] = (-0.25, -0.15 - 0.20 * flail, -0.35)
            ku.rot["CTRL_FK_Thigh_L"] = (-0.25 + 0.15 * flail, +0.22, 0.0)
            ku.rot["CTRL_FK_Calf_L"] = (+0.65, 0.0, 0.0)
            ku.rot["CTRL_FK_Thigh_R"] = (-0.10 - 0.15 * flail, -0.22, 0.0)
            ku.rot["CTRL_FK_Calf_R"] = (+0.45, 0.0, 0.0)
            ku.shapes = {"expr_surprise": 0.75, "expr_pain": 0.45}
            if clip_id == "knockup_start":
                return blend_poses(combat_ready_base(0.0), ku, sstep(0.0, 0.85, u))
            return ku

        if clip_id == "knockdown_front":
            return blend_poses(combat_ready_base(0.0), make_prone_front_pose(0.0), sstep(0.05, 0.88, u))
        if clip_id == "prone_front":
            return make_prone_front_pose(math.sin(th))
        if clip_id == "getup_front":
            # Stand from face-down via hand push + knee plant intermediate pose!
            mid = combat_ready_base(0.0)
            mid.props["ik_fk_arm_l"] = 1.0
            mid.loc["CTRL_Pelvis"] = (0.0, 0.06, -0.58)
            mid.loc["CTRL_IK_Hand_L"] = (-0.52, -0.36, -1.42)
            mid.rot["CTRL_Pelvis"] = (+0.45, 0.0, 0.0)
            mid.rot["CTRL_Spine_01"] = (+0.45, 0.0, 0.0)
            mid.rot["CTRL_Spine_02"] = (+0.32, 0.0, 0.0)
            if u < 0.50:
                return blend_poses(make_prone_front_pose(0.0), mid, sstep(0.0, 0.50, u))
            return blend_poses(mid, combat_ready_base(0.0), sstep(0.50, 1.0, u))

        if clip_id == "knockdown_back":
            return blend_poses(combat_ready_base(0.0), make_prone_back_pose(0.0), sstep(0.05, 0.88, u))
        if clip_id == "prone_back":
            return make_prone_back_pose(math.sin(th))
        if clip_id == "getup_back":
            mid = combat_ready_base(0.0)
            mid.props["ik_fk_arm_r"] = 1.0
            mid.loc["CTRL_Pelvis"] = (-0.04, 0.08, -0.60)
            mid.loc["CTRL_IK_Hand_R"] = (+0.48, +0.24, -1.42)
            mid.rot["CTRL_Pelvis"] = (-0.42, -0.18, +0.22)
            mid.rot["CTRL_Spine_01"] = (-0.28, 0.0, 0.0)
            if u < 0.50:
                return blend_poses(make_prone_back_pose(0.0), mid, sstep(0.0, 0.50, u))
            return blend_poses(mid, combat_ready_base(0.0), sstep(0.50, 1.0, u))

        if clip_id == "sleep_start":
            return blend_poses(combat_ready_base(0.0), self._sleep_pose(0.0), sstep(0.05, 0.95, u))
        if clip_id == "sleep_loop":
            return self._sleep_pose(math.sin(th))
        if clip_id == "sleep_end":
            return blend_poses(self._sleep_pose(0.0), combat_ready_base(0.0), sstep(0.10, 0.95, u))

        # 10. DEATHS, HELD DEAD POSES, RESPAWN
        if clip_id == "death_front":
            # Impact recoil -> drops to knees (u=0.40) -> collapses into exact dead_front!
            knees = combat_ready_base(0.0)
            knees.loc["CTRL_Pelvis"] = (0.02, -0.05, -0.46)
            knees.rot["CTRL_Spine_01"] = (-0.22, 0.0, -0.18)
            knees.rot["CTRL_Head"] = (-0.35, 0.0, +0.22)
            knees.shapes = {"expr_pain": 0.90}
            if u < 0.42:
                return blend_poses(combat_ready_base(0.0), knees, sstep(0.0, 0.42, u))
            return blend_poses(knees, make_dead_front_pose(), sstep(0.42, 0.92, u))

        if clip_id == "dead_front":
            return make_dead_front_pose()

        if clip_id == "death_back":
            buckle = combat_ready_base(0.0)
            buckle.loc["CTRL_Pelvis"] = (-0.03, +0.08, -0.42)
            buckle.rot["CTRL_Spine_01"] = (+0.28, -0.12, +0.22)
            buckle.shapes = {"expr_pain": 0.90}
            if u < 0.38:
                return blend_poses(combat_ready_base(0.0), buckle, sstep(0.0, 0.38, u))
            return blend_poses(buckle, make_dead_back_pose(), sstep(0.38, 0.92, u))

        if clip_id == "dead_back":
            return make_dead_back_pose()

        if clip_id == "respawn":
            # Hovering digital core boot -> touch down (u=0.25) -> cyber-arm system check (u=0.58) -> ready!
            boot = combat_ready_base(0.0)
            boot.loc["CTRL_Pelvis"] = (0.0, 0.0, +0.16)
            boot.loc["CTRL_IK_Foot_L"] = (+0.03, -0.05, +0.16)
            boot.loc["CTRL_IK_Foot_R"] = (-0.03, +0.05, +0.16)
            boot.rot["CTRL_Head"] = (+0.35, 0.0, 0.0)
            boot.rot["CTRL_FK_UpperArm_L"] = (0.25, +0.65, -1.18)
            boot.rot["CTRL_FK_UpperArm_R"] = (0.25, -0.65, +1.18)
            boot.shapes = {"blink_l": 1.0, "blink_r": 1.0}

            check = combat_ready_base(0.0)
            check.rot["CTRL_Head"] = (+0.18, 0.0, -0.35)
            check.rot["CTRL_FK_UpperArm_R"] = (0.28, -0.42, +0.95)
            check.rot["CTRL_FK_LowerArm_R"] = (-0.25, +0.35, +1.15)
            check.loc["CTRL_Blade_R"] = (-0.22, 0.0, 0.0)
            check.shapes = {"expr_joy_confidence": 0.55, "expr_focus": 0.45}

            if u < 0.32:
                return blend_poses(boot, combat_ready_base(0.0), sstep(0.05, 0.32, u))
            if u < 0.68:
                return blend_poses(combat_ready_base(0.0), check, bell(u, 0.54, 0.22))
            return blend_poses(check, combat_ready_base(0.0), sstep(0.68, 0.96, u))

        # 11. SOCIAL & DIALOGUE
        if clip_id == "greet":
            p = combat_ready_base(th)
            wave = pulse_env(u, 0.22, 0.68, 0.92)
            nod = bell(u, 0.38, 0.16)
            p.rot["CTRL_Head"] = (-0.12 + 0.24 * nod, 0.06 * wave, 0.0)
            p.rot["CTRL_FK_UpperArm_L"] = (0.28, +0.15 * wave + 1.06 * (1 - wave), -0.78 * wave - 0.32 * (1 - wave))
            p.rot["CTRL_FK_LowerArm_L"] = (0.15 * wave, 0.0, -1.65 * wave - 0.78 * (1 - wave) + 0.18 * math.sin(u * 14.0) * wave)
            p.finger_curl_l = 0.12 * wave + 0.32 * (1 - wave)
            p.shapes["expr_joy_confidence"] = 0.85 * wave
            return p

        if clip_id == "victory":
            p = combat_ready_base(th)
            flourish = pulse_env(u, 0.18, 0.48, 0.62)
            pump = pulse_env(u - 0.42, 0.14, 0.38, 0.55)
            p.loc["CTRL_Blade_R"] = (-0.24 * flourish, 0.0, 0.0)
            p.loc["CTRL_Pelvis"] = (-0.03 * pump, 0.0, -0.03 + 0.03 * pump)
            p.rot["CTRL_Spine_02"] = (-0.12 * pump, 0.0, +0.20 * flourish - 0.18 * pump)
            p.rot["CTRL_Head"] = (-0.20 * pump - 0.10, 0.0, -0.15 * pump)
            p.rot["CTRL_FK_UpperArm_R"] = (0.15, +0.95 * pump - 0.35 * flourish - 0.98 * (1 - flourish - pump), +0.35)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +1.15 * pump + 0.25 * flourish + 0.92 * (1 - flourish - pump))
            p.finger_curl_r = 0.95 * pump + 0.42 * (1 - pump)
            p.shapes["expr_joy_confidence"] = 0.95 * max(flourish, pump)
            p.shapes["corr_shoulder_up_r"] = pump
            return p

        if clip_id == "defeat":
            p = combat_ready_base(0.0)
            slump = pulse_env(u, 0.20, 0.78, 0.98)
            shake = math.sin(u * 6.0 * math.pi) * bell(u, 0.38, 0.24)
            p.loc["CTRL_Pelvis"] = (0.0, 0.03 * slump, -0.095 * slump - 0.055 * (1 - slump))
            p.rot["CTRL_Spine_01"] = (+0.22 * slump, 0.0, 0.0)
            p.rot["CTRL_Spine_02"] = (+0.18 * slump, 0.0, 0.0)
            p.rot["CTRL_Head"] = (+0.32 * slump, 0.0, 0.28 * shake)
            p.rot["CTRL_FK_UpperArm_L"] = (0.30 * slump, +0.42 * slump + 1.06 * (1 - slump), -1.05 * slump - 0.32 * (1 - slump))
            p.rot["CTRL_FK_LowerArm_L"] = (0.18 * slump, 0.0, -1.82 * slump - 0.78 * (1 - slump))
            p.rot["CTRL_FK_UpperArm_R"] = (0.05, -1.26 * slump - 0.98 * (1 - slump), +0.10)
            p.rot["CTRL_FK_LowerArm_R"] = (0.0, 0.0, +0.20 * slump + 0.92 * (1 - slump))
            p.shapes["expr_concern_sadness"] = 0.90 * slump
            return p

        if clip_id == "dialogue":
            return self.dialogue.eval_at(t)

        # 12. 9-SAMPLE CALIBRATED AIM GRID POSES
        aim_table = {
            "aim_down_left":    (-60.0, -35.0),
            "aim_down_center":  (  0.0, -35.0),
            "aim_down_right":   (+60.0, -35.0),
            "aim_level_left":   (-60.0,   0.0),
            "aim_level_center": (  0.0,   0.0),
            "aim_level_right":  (+60.0,   0.0),
            "aim_up_left":      (-60.0, +35.0),
            "aim_up_center":    (  0.0, +35.0),
            "aim_up_right":     (+60.0, +35.0),
        }
        if clip_id in aim_table:
            return make_aim_pose(*aim_table[clip_id])

        raise KeyError(f"Unhandled clip_id: {clip_id}")

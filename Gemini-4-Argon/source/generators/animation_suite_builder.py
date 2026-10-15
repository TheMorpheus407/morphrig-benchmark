#!/usr/bin/env python3
"""
Procedural Biomechanical Animation & Pose Suite Builder for MorphRig Operative ("Vex").

Generates all 96 required named animations and static poses (matching required_animations.csv
1-to-1 at 30 FPS) plus 7 deformation stress-test poses, keyframes both skeletal pose bones
and facial/corrective Shape Keys, embeds timeline PoseMarkers for all gameplay events,
and outputs docs/animation_manifest.json.
"""

import csv
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
import bpy
from mathutils import Euler, Matrix, Vector


FPS = 30


def deg2rad(d: float) -> float:
    return d * (math.pi / 180.0)


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def pulse_bell(t: float, center: float, half_width: float) -> float:
    d = abs(t - center)
    if d >= half_width or half_width <= 1e-6:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * d / half_width))


class RigPoseHelper:
    """
    Applies world-aligned character rotations (rx=Pitch around +X, ry=Roll around +Y,
    rz=Yaw around +Z) and world-space translations cleanly into each bone's rest-pose basis.
    """

    def __init__(self, arm_obj: bpy.types.Object):
        self.arm_obj = arm_obj
        self.pbones = arm_obj.pose.bones
        self.rest_rot: Dict[str, Matrix] = {}
        self.rest_rot_inv: Dict[str, Matrix] = {}
        for pb in self.pbones:
            m3 = pb.bone.matrix_local.to_3x3()
            self.rest_rot[pb.name] = m3
            self.rest_rot_inv[pb.name] = m3.inverted()

    def reset_all(self):
        for pb in self.pbones:
            pb.location = (0.0, 0.0, 0.0)
            pb.rotation_euler = (0.0, 0.0, 0.0)
            pb.scale = (1.0, 1.0, 1.0)

    def set_bone(
        self,
        bname: str,
        rx_deg: float = 0.0,
        ry_deg: float = 0.0,
        rz_deg: float = 0.0,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ):
        pb = self.pbones.get(bname)
        if pb is None:
            return
        r_inv = self.rest_rot_inv[bname]
        if abs(rx_deg) > 1e-5 or abs(ry_deg) > 1e-5 or abs(rz_deg) > 1e-5:
            r_world = Euler((deg2rad(rx_deg), deg2rad(ry_deg), deg2rad(rz_deg)), "XYZ").to_matrix()
            m_local = r_inv @ r_world @ self.rest_rot[bname]
            pb.rotation_euler = m_local.to_euler("XYZ")
        else:
            pb.rotation_euler = (0.0, 0.0, 0.0)

        if abs(dx) > 1e-6 or abs(dy) > 1e-6 or abs(dz) > 1e-6:
            pb.location = r_inv @ Vector((dx, dy, dz))
        else:
            pb.location = (0.0, 0.0, 0.0)

    def set_fingers_curl(self, side: str, curl_deg: float, thumb_curl_deg: float = None):
        if thumb_curl_deg is None:
            thumb_curl_deg = curl_deg * 0.65
        s_sign = 1.0 if side == "l" else -1.0
        # Curling fingers bends them around Y/Z toward the palm
        for fname in ("index", "middle", "ring", "pinky"):
            for pnum in ("01", "02", "03"):
                self.set_bone(f"{fname}_{pnum}_{side}", ry_deg=s_sign * curl_deg * 0.65, rz_deg=-s_sign * curl_deg * 0.45)
        for pnum in ("01", "02", "03"):
            self.set_bone(f"thumb_{pnum}_{side}", rx_deg=thumb_curl_deg * 0.5, rz_deg=-s_sign * thumb_curl_deg * 0.6)

    def apply_base_standing_arms(self, combat_ready: bool = False, breath_phase: float = 0.0):
        """Bring arms down from T-pose into a natural relaxed or combat-ready posture."""
        b_sin = math.sin(breath_phase)
        if not combat_ready:
            # Relaxed attentive stance: arms lowered (~62 deg from horizontal), slight elbow bend
            self.set_bone("clavicle_l", ry_deg=4.0 - 1.2 * b_sin)
            self.set_bone("upperarm_l", ry_deg=62.0, rz_deg=-6.0)
            self.set_bone("lowerarm_l", ry_deg=48.0, rz_deg=-22.0)
            self.set_bone("hand_l", ry_deg=52.0, rz_deg=-10.0)
            self.set_fingers_curl("l", 18.0)

            self.set_bone("clavicle_r", ry_deg=-4.0 + 1.2 * b_sin)
            self.set_bone("upperarm_r", ry_deg=-62.0, rz_deg=8.0)
            self.set_bone("lowerarm_r", ry_deg=-46.0, rz_deg=26.0)
            self.set_bone("hand_r", ry_deg=-50.0, rz_deg=12.0)
            self.set_fingers_curl("r", 22.0)
        else:
            # Combat ready stance: guard raised, clear silhouette, free hands
            self.set_bone("clavicle_l", ry_deg=2.0, rz_deg=-6.0)
            self.set_bone("upperarm_l", ry_deg=44.0, rz_deg=-24.0)
            self.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-68.0)
            self.set_bone("hand_l", ry_deg=12.0, rz_deg=-55.0)
            self.set_fingers_curl("l", 32.0)

            self.set_bone("clavicle_r", ry_deg=-2.0, rz_deg=8.0)
            self.set_bone("upperarm_r", ry_deg=-42.0, rz_deg=28.0)
            self.set_bone("lowerarm_r", ry_deg=-15.0, rz_deg=74.0)
            self.set_bone("hand_r", ry_deg=-10.0, rz_deg=60.0)
            self.set_fingers_curl("r", 45.0)

    def apply_secondary_follow_through(
        self,
        phase_rad: float,
        amp_deg: float = 8.0,
        sway_x_deg: float = 4.0,
        head_pitch_deg: float = 0.0,
    ):
        """Animate secondary motion on neural_tether_01..03 and belt_strap_01..02 with phase lag."""
        for idx, bname in enumerate(("neural_tether_01", "neural_tether_02", "neural_tether_03")):
            lag = idx * 0.65
            rx = -max(0.0, head_pitch_deg * 0.4) - amp_deg * (0.6 + 0.3 * idx) * (0.5 + 0.5 * math.sin(phase_rad - lag))
            ry = sway_x_deg * (0.5 + 0.4 * idx) * math.cos(phase_rad - lag)
            self.set_bone(bname, rx_deg=rx, ry_deg=ry)

        for idx, bname in enumerate(("belt_strap_01", "belt_strap_02")):
            lag = idx * 0.55
            rx = amp_deg * 0.6 * math.sin(phase_rad - lag)
            ry = -abs(sway_x_deg) * (0.5 + 0.5 * math.cos(phase_rad - lag))
            self.set_bone(bname, rx_deg=rx, ry_deg=ry)

    def apply_twist_bones(self):
        """Propagate 50% axial twist to upperarm_twist, lowerarm_twist, thigh_twist, calf_twist."""
        for s_side in ("l", "r"):
            for src, dst in [
                (f"upperarm_{s_side}", f"upperarm_twist_01_{s_side}"),
                (f"hand_{s_side}", f"lowerarm_twist_01_{s_side}"),
                (f"thigh_{s_side}", f"thigh_twist_01_{s_side}"),
                (f"foot_{s_side}", f"calf_twist_01_{s_side}"),
            ]:
                pb_src = self.pbones.get(src)
                pb_dst = self.pbones.get(dst)
                if pb_src and pb_dst:
                    pb_dst.rotation_euler = (
                        pb_src.rotation_euler.x * 0.35,
                        pb_src.rotation_euler.y * 0.50,
                        pb_src.rotation_euler.z * 0.35,
                    )


def pose_directional_gait(
    helper: RigPoseHelper,
    u: float,
    dir_angle_rad: float,
    is_run: bool = False,
    is_sprint: bool = False,
):
    """
    Generate genuine 8-directional locomotion gait relative to character forward (-Y):
      - dir_angle_rad: 0 = Forward (-Y), +pi/4 = FL, +pi/2 = Left (+X), +pi = Back (+Y), -pi/2 = Right (-X)
      - Retain upper-body forward facing while hips/legs execute true directional stride,
        crossover/strafe abduction, knee flexion, and heel-strike/toe-off foot roll.
    """
    phase = 2.0 * math.pi * u
    # Left leg phase = phase, Right leg phase = phase + pi
    cos_d = math.cos(dir_angle_rad)  # +1 forward, -1 backward
    sin_d = math.sin(dir_angle_rad)  # +1 left (+X), -1 right (-X)

    if is_sprint:
        hip_swing_deg = 48.0
        knee_stance_deg = 18.0
        knee_swing_deg = 78.0
        pelvis_bob_m = 0.042
        torso_lean_deg = 26.0
        arm_swing_deg = 52.0
    elif is_run:
        hip_swing_deg = 36.0
        knee_stance_deg = 16.0
        knee_swing_deg = 62.0
        pelvis_bob_m = 0.032
        torso_lean_deg = 14.0 * cos_d
        arm_swing_deg = 34.0
    else:
        hip_swing_deg = 24.0
        knee_stance_deg = 8.0
        knee_swing_deg = 38.0
        pelvis_bob_m = 0.018
        torso_lean_deg = 5.0 * cos_d
        arm_swing_deg = 18.0

    # Double-frequency vertical pelvis bob + lateral weight shift
    bob_z = pelvis_bob_m * math.sin(2.0 * phase - 0.3)
    sway_x = 0.015 * math.cos(phase) * (0.6 + 0.4 * abs(cos_d))
    pelvis_yaw = 10.0 * cos_d * math.sin(phase) + 12.0 * sin_d
    pelvis_roll = 4.0 * math.cos(phase)

    helper.set_bone("pelvis", rx_deg=torso_lean_deg * 0.35, ry_deg=pelvis_roll, rz_deg=pelvis_yaw, dx=sway_x, dz=bob_z)
    # Counter-rotate spine so chest and head remain oriented toward forward facing (-Y)!
    helper.set_bone("spine_01", rx_deg=torso_lean_deg * 0.25, ry_deg=-pelvis_roll * 0.5, rz_deg=-pelvis_yaw * 0.4)
    helper.set_bone("spine_02", rx_deg=torso_lean_deg * 0.25, rz_deg=-pelvis_yaw * 0.35)
    helper.set_bone("spine_03", rx_deg=torso_lean_deg * 0.20, rz_deg=-pelvis_yaw * 0.35)
    helper.set_bone("neck_01", rx_deg=-torso_lean_deg * 0.35, rz_deg=pelvis_yaw * 0.05)
    helper.set_bone("head", rx_deg=-torso_lean_deg * 0.45, rz_deg=pelvis_yaw * 0.05)

    # Legs (Left = phase, Right = phase + pi)
    for s_sign, s_side, l_phase in [(1.0, "l", phase), (-1.0, "r", phase + math.pi)]:
        s_val = math.sin(l_phase)       # +1 = forward swing apex, -1 = backward push-off apex
        c_val = math.cos(l_phase)       # >0 = swing phase (foot in air), <0 = stance phase (foot planted)
        swing_lift = max(0.0, c_val)    # 0 during stance, 0..1 during swing

        # Forward/backward hip pitch (rx < 0 lifts thigh forward -Y)
        thigh_rx = -hip_swing_deg * cos_d * s_val - 14.0 * swing_lift
        # Lateral strafe abduction/adduction (ry > 0 abducts left leg +X, ry < 0 abducts right leg -X)
        thigh_ry = hip_swing_deg * 0.72 * sin_d * s_val + s_sign * 4.0 * swing_lift
        thigh_rz = 8.0 * sin_d * c_val

        # Knee flexion (rx > 0 bends calf backward +Y)
        calf_rx = knee_stance_deg * max(0.0, -c_val) + knee_swing_deg * (swing_lift ** 1.2)

        # Foot & toe roll: heel strike at s_val > 0.6, flat during stance, toe push-off at s_val < -0.5
        foot_rx = -thigh_rx * 0.65 - calf_rx * 0.45 + 14.0 * s_val * cos_d
        foot_ry = -thigh_ry * 0.75
        ball_rx = -22.0 * max(0.0, -s_val) * max(0.2, abs(cos_d))

        helper.set_bone(f"thigh_{s_side}", rx_deg=thigh_rx, ry_deg=thigh_ry, rz_deg=thigh_rz)
        helper.set_bone(f"calf_{s_side}", rx_deg=calf_rx)
        helper.set_bone(f"foot_{s_side}", rx_deg=foot_rx, ry_deg=foot_ry)
        helper.set_bone(f"ball_{s_side}", rx_deg=ball_rx)

    # Arms counter-swing opposite to legs
    arm_s = math.sin(phase)
    elbow_base = 72.0 if (is_run or is_sprint) else 32.0
    arm_down = 46.0 if (is_run or is_sprint) else 58.0

    helper.set_bone("clavicle_l", rz_deg=5.0 * arm_s)
    helper.set_bone("upperarm_l", ry_deg=arm_down, rz_deg=-10.0 + arm_swing_deg * arm_s)
    helper.set_bone("lowerarm_l", ry_deg=24.0, rz_deg=-(elbow_base + 14.0 * max(0.0, -arm_s)))
    helper.set_bone("hand_l", ry_deg=20.0, rz_deg=-25.0)
    helper.set_fingers_curl("l", 45.0 if (is_run or is_sprint) else 22.0)

    helper.set_bone("clavicle_r", rz_deg=5.0 * arm_s)
    helper.set_bone("upperarm_r", ry_deg=-arm_down, rz_deg=10.0 + arm_swing_deg * arm_s)
    helper.set_bone("lowerarm_r", ry_deg=-24.0, rz_deg=(elbow_base + 14.0 * max(0.0, arm_s)))
    helper.set_bone("hand_r", ry_deg=-20.0, rz_deg=25.0)
    helper.set_fingers_curl("r", 50.0 if (is_run or is_sprint) else 26.0)

    helper.apply_secondary_follow_through(
        2.0 * phase,
        amp_deg=16.0 if is_sprint else (12.0 if is_run else 6.0),
        sway_x_deg=8.0 * sin_d + 4.0 * math.cos(phase),
        head_pitch_deg=torso_lean_deg,
    )


def apply_death_front_pose(helper: RigPoseHelper, w: float):
    """Interpolate from standing (w=0) to final face-down collapse (w=1). Shared by death_front and dead_front."""
    e = smoothstep(w)
    knee_drop = smoothstep(min(1.0, w * 1.6))
    face_plant = smoothstep(max(0.0, (w - 0.35) / 0.65))

    # Drop pelvis to floor Z = -0.78 m (so character lies at Z ~ 0.12 m on floor), pitch torso 86 deg forward
    pz = -0.42 * knee_drop - 0.37 * face_plant
    py = -0.10 * knee_drop - 0.38 * face_plant
    pitch = 28.0 * knee_drop + 58.0 * face_plant

    helper.set_bone("pelvis", rx_deg=pitch, ry_deg=4.0 * face_plant, rz_deg=-6.0 * face_plant, dy=py, dz=pz)
    helper.set_bone("spine_01", rx_deg=8.0 * knee_drop - 6.0 * face_plant)
    helper.set_bone("spine_02", rx_deg=10.0 * knee_drop - 8.0 * face_plant)
    helper.set_bone("spine_03", rx_deg=6.0 * knee_drop - 10.0 * face_plant, rz_deg=8.0 * face_plant)
    helper.set_bone("neck_01", rx_deg=-15.0 * face_plant, rz_deg=28.0 * face_plant)
    helper.set_bone("head", rx_deg=-18.0 * face_plant, ry_deg=12.0 * face_plant, rz_deg=32.0 * face_plant)

    # Legs fold onto knees then sprawl out behind (+Y)
    helper.set_bone("thigh_l", rx_deg=78.0 * face_plant - 35.0 * (knee_drop * (1.0 - face_plant)), ry_deg=12.0 * e)
    helper.set_bone("calf_l", rx_deg=95.0 * knee_drop * (1.0 - 0.75 * face_plant) + 18.0 * face_plant)
    helper.set_bone("foot_l", rx_deg=35.0 * e)

    helper.set_bone("thigh_r", rx_deg=82.0 * face_plant - 30.0 * (knee_drop * (1.0 - face_plant)), ry_deg=-16.0 * e)
    helper.set_bone("calf_r", rx_deg=90.0 * knee_drop * (1.0 - 0.65 * face_plant) + 28.0 * face_plant)
    helper.set_bone("foot_r", rx_deg=40.0 * e)

    # Asymmetric arms sprawled on floor beside head/torso
    helper.set_bone("upperarm_l", rx_deg=75.0 * face_plant, ry_deg=32.0 + 18.0 * (1.0 - e), rz_deg=-35.0 * e)
    helper.set_bone("lowerarm_l", rx_deg=65.0 * face_plant, ry_deg=20.0, rz_deg=-48.0 * e)
    helper.set_fingers_curl("l", 12.0)

    helper.set_bone("upperarm_r", rx_deg=70.0 * face_plant, ry_deg=-38.0 - 14.0 * (1.0 - e), rz_deg=22.0 * e)
    helper.set_bone("lowerarm_r", rx_deg=60.0 * face_plant, ry_deg=-25.0, rz_deg=35.0 * e)
    helper.set_fingers_curl("r", 16.0)
    helper.apply_secondary_follow_through(w * math.pi, amp_deg=4.0, head_pitch_deg=pitch)


def apply_death_back_pose(helper: RigPoseHelper, w: float):
    """Interpolate from standing (w=0) to final supine back-impact pose (w=1). Shared by death_back and dead_back."""
    stagger = smoothstep(min(1.0, w * 1.5))
    fall_back = smoothstep(max(0.0, (w - 0.30) / 0.70))

    # Pelvis drops to Z = -0.79 m and pitches backward -86 deg (lying face-up on back)
    pz = -0.32 * stagger - 0.47 * fall_back
    py = 0.14 * stagger + 0.34 * fall_back
    pitch = -24.0 * stagger - 62.0 * fall_back

    helper.set_bone("pelvis", rx_deg=pitch, ry_deg=-5.0 * fall_back, rz_deg=10.0 * fall_back, dy=py, dz=pz)
    helper.set_bone("spine_01", rx_deg=-6.0 * stagger + 4.0 * fall_back)
    helper.set_bone("spine_02", rx_deg=-8.0 * stagger + 6.0 * fall_back, rz_deg=-8.0 * fall_back)
    helper.set_bone("spine_03", rx_deg=12.0 * fall_back, rz_deg=-10.0 * fall_back)
    helper.set_bone("neck_01", rx_deg=18.0 * fall_back, rz_deg=-24.0 * fall_back)
    helper.set_bone("head", rx_deg=14.0 * fall_back, ry_deg=-15.0 * fall_back, rz_deg=-28.0 * fall_back)

    # Asymmetric leg placement (left leg extended out, right knee slightly bent outward)
    helper.set_bone("thigh_l", rx_deg=-82.0 * fall_back, ry_deg=14.0 * fall_back, rz_deg=12.0 * fall_back)
    helper.set_bone("calf_l", rx_deg=14.0 * fall_back + 35.0 * stagger * (1.0 - fall_back))
    helper.set_bone("foot_l", rx_deg=24.0 * fall_back)

    helper.set_bone("thigh_r", rx_deg=-68.0 * fall_back, ry_deg=-22.0 * fall_back, rz_deg=-18.0 * fall_back)
    helper.set_bone("calf_r", rx_deg=32.0 * fall_back + 40.0 * stagger * (1.0 - fall_back))
    helper.set_bone("foot_r", rx_deg=28.0 * fall_back)

    # Asymmetric arms: left arm resting out to side, right cyber-arm across lower ribs
    helper.set_bone("upperarm_l", rx_deg=-72.0 * fall_back, ry_deg=28.0, rz_deg=18.0 * fall_back)
    helper.set_bone("lowerarm_l", rx_deg=-68.0 * fall_back, ry_deg=18.0, rz_deg=-22.0 * fall_back)
    helper.set_fingers_curl("l", 14.0)

    helper.set_bone("upperarm_r", rx_deg=-65.0 * fall_back, ry_deg=-42.0, rz_deg=36.0 * fall_back)
    helper.set_bone("lowerarm_r", rx_deg=-55.0 * fall_back, ry_deg=-20.0, rz_deg=62.0 * fall_back)
    helper.set_fingers_curl("r", 20.0)


def apply_aim_pose(helper: RigPoseHelper, yaw_deg: float, pitch_deg: float):
    """
    Calibrated upper-body aim grid pose:
      yaw_deg in [-60, 0, +60] (+ is Left, - is Right)
      pitch_deg in [-35, 0, +35] (+ is Up, - is Down)
    Strictly upper-body (spine_01 and above) — pelvis and legs stay in exact neutral rest pose!
    """
    # Note: for spine/head pointing +Z, rx > 0 pitches forward/down, rx < 0 pitches backward/up!
    rx_spine = -pitch_deg
    rz_yaw = yaw_deg

    helper.set_bone("spine_01", rx_deg=rx_spine * 0.20, rz_deg=rz_yaw * 0.22)
    helper.set_bone("spine_02", rx_deg=rx_spine * 0.25, rz_deg=rz_yaw * 0.28)
    helper.set_bone("spine_03", rx_deg=rx_spine * 0.30, rz_deg=rz_yaw * 0.32)
    helper.set_bone("neck_01", rx_deg=rx_spine * 0.12, rz_deg=rz_yaw * 0.10)
    helper.set_bone("head", rx_deg=rx_spine * 0.13, rz_deg=rz_yaw * 0.08)

    # Right cybernetic arm aims wrist emitter forward along the target yaw & pitch
    helper.set_bone("clavicle_r", ry_deg=-4.0, rz_deg=12.0 + rz_yaw * 0.15)
    helper.set_bone("upperarm_r", rx_deg=rx_spine * 0.35, ry_deg=-18.0 + pitch_deg * 0.45, rz_deg=76.0 + rz_yaw * 0.20)
    helper.set_bone("lowerarm_r", rx_deg=rx_spine * 0.25, ry_deg=-8.0 + pitch_deg * 0.35, rz_deg=86.0 + rz_yaw * 0.15)
    helper.set_bone("hand_r", rx_deg=rx_spine * 0.20, ry_deg=-6.0, rz_deg=84.0)
    helper.set_fingers_curl("r", 65.0)

    # Left arm in balanced tactical support guard
    helper.set_bone("clavicle_l", ry_deg=4.0, rz_deg=-8.0)
    helper.set_bone("upperarm_l", ry_deg=42.0 - pitch_deg * 0.20, rz_deg=-32.0 + rz_yaw * 0.15)
    helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-74.0)
    helper.set_bone("hand_l", ry_deg=12.0, rz_deg=-60.0)
    helper.set_fingers_curl("l", 35.0)


def evaluate_clip_pose(
    clip_id: str,
    helper: RigPoseHelper,
    u: float,
    t_sec: float,
    dialogue_frames: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Evaluate skeletal pose and return active Shape Key weights for clip_id at normalized time u in [0, 1].
    """
    helper.reset_all()
    shape_weights: Dict[str, float] = {}
    phase = 2.0 * math.pi * u

    # --- 1. IDLES ---
    if clip_id == "idle_relaxed":
        b = math.sin(phase)
        sway = math.sin(phase * 0.5)
        helper.set_bone("pelvis", ry_deg=2.2 * sway, rz_deg=3.0 * sway, dx=0.012 * sway, dz=0.006 * b)
        helper.set_bone("spine_01", rx_deg=2.0 * b, ry_deg=-1.5 * sway)
        helper.set_bone("spine_02", rx_deg=2.5 * b, rz_deg=-2.0 * sway)
        helper.set_bone("spine_03", rx_deg=2.5 * b, rz_deg=-2.5 * sway)
        helper.set_bone("neck_01", rx_deg=-1.5 * b, rz_deg=4.0 * math.sin(phase + 0.5))
        helper.set_bone("head", rx_deg=-2.0 * b, rz_deg=6.0 * math.sin(phase + 0.5))
        helper.set_bone("thigh_l", rx_deg=-3.0, ry_deg=2.0 * sway)
        helper.set_bone("calf_l", rx_deg=6.0)
        helper.set_bone("foot_l", rx_deg=-3.0)
        helper.set_bone("thigh_r", rx_deg=-4.0, ry_deg=2.0 * sway)
        helper.set_bone("calf_r", rx_deg=8.0)
        helper.set_bone("foot_r", rx_deg=-4.0)
        helper.apply_base_standing_arms(combat_ready=False, breath_phase=phase)
        helper.apply_secondary_follow_through(phase, amp_deg=4.0, sway_x_deg=3.0 * sway)
        if 0.44 <= u <= 0.52:
            bl = pulse_bell(u, 0.48, 0.04)
            shape_weights["blink_l"] = bl
            shape_weights["blink_r"] = bl

    elif clip_id == "idle_combat":
        b = math.sin(2.0 * phase)
        shift = math.sin(phase)
        helper.set_bone("pelvis", rx_deg=8.0, rz_deg=-16.0 + 4.0 * shift, dx=0.016 * shift, dz=-0.035 + 0.010 * b)
        helper.set_bone("spine_01", rx_deg=4.0, rz_deg=6.0)
        helper.set_bone("spine_02", rx_deg=4.0 + 2.0 * b, rz_deg=6.0)
        helper.set_bone("spine_03", rx_deg=4.0 + 2.5 * b, rz_deg=6.0)
        helper.set_bone("neck_01", rx_deg=-6.0)
        helper.set_bone("head", rx_deg=-8.0, rz_deg=-2.0 * shift)
        helper.set_bone("thigh_l", rx_deg=-18.0 + 3.0 * b, ry_deg=6.0)
        helper.set_bone("calf_l", rx_deg=34.0 - 5.0 * b)
        helper.set_bone("foot_l", rx_deg=-16.0 + 2.0 * b)
        helper.set_bone("thigh_r", rx_deg=-12.0 + 3.0 * b, ry_deg=-8.0)
        helper.set_bone("calf_r", rx_deg=28.0 - 5.0 * b)
        helper.set_bone("foot_r", rx_deg=-16.0 + 2.0 * b)
        helper.apply_base_standing_arms(combat_ready=True, breath_phase=2.0 * phase)
        helper.apply_secondary_follow_through(2.0 * phase, amp_deg=6.0, sway_x_deg=4.0 * shift, head_pitch_deg=8.0)
        shape_weights["expr_focus"] = 0.65

    elif clip_id == "idle_wounded":
        b = math.sin(2.0 * phase)
        helper.set_bone("pelvis", rx_deg=18.0 + 3.0 * b, ry_deg=-7.0, rz_deg=10.0, dx=-0.025, dz=-0.065 + 0.008 * b)
        helper.set_bone("spine_01", rx_deg=10.0 + 2.5 * b, ry_deg=-5.0)
        helper.set_bone("spine_02", rx_deg=8.0 + 2.5 * b, ry_deg=-4.0)
        helper.set_bone("spine_03", rx_deg=6.0 + 2.0 * b, rz_deg=-8.0)
        helper.set_bone("neck_01", rx_deg=-12.0, ry_deg=8.0)
        helper.set_bone("head", rx_deg=-10.0 + 3.0 * b, rz_deg=8.0 * math.sin(phase))
        # Left arm clutches injured right ribs; right arm hangs guarded
        helper.set_bone("upperarm_l", ry_deg=48.0, rz_deg=-42.0)
        helper.set_bone("lowerarm_l", ry_deg=25.0, rz_deg=-95.0)
        helper.set_bone("hand_l", ry_deg=15.0, rz_deg=-75.0)
        helper.set_fingers_curl("l", 25.0)
        helper.set_bone("upperarm_r", ry_deg=-56.0, rz_deg=14.0)
        helper.set_bone("lowerarm_r", ry_deg=-38.0, rz_deg=35.0)
        helper.set_bone("thigh_l", rx_deg=-24.0, ry_deg=5.0)
        helper.set_bone("calf_l", rx_deg=42.0)
        helper.set_bone("foot_l", rx_deg=-18.0)
        helper.set_bone("thigh_r", rx_deg=-16.0, ry_deg=-4.0)
        helper.set_bone("calf_r", rx_deg=36.0)
        helper.set_bone("foot_r", rx_deg=-20.0)
        helper.apply_secondary_follow_through(2.0 * phase, amp_deg=5.0, head_pitch_deg=18.0)
        shape_weights["expr_pain"] = 0.65

    # --- 2. 8-WAY WALKS, 8-WAY RUNS, SPRINT ---
    elif clip_id.startswith("walk_") or clip_id.startswith("run_") or clip_id == "sprint_f":
        dir_map = {
            "f": 0.0,
            "fl": 0.25 * math.pi,
            "l": 0.50 * math.pi,
            "bl": 0.75 * math.pi,
            "b": math.pi,
            "br": -0.75 * math.pi,
            "r": -0.50 * math.pi,
            "fr": -0.25 * math.pi,
        }
        suffix = clip_id.split("_")[1]
        ang = dir_map[suffix]
        pose_directional_gait(
            helper,
            u,
            dir_angle_rad=ang,
            is_run=clip_id.startswith("run_"),
            is_sprint=(clip_id == "sprint_f"),
        )
        shape_weights["expr_focus"] = 0.45 if not (clip_id == "sprint_f") else 0.80

    # --- 3. STARTS, STOPS, TURNS, PIVOTS ---
    elif clip_id == "start_f":
        e = smoothstep(u)
        crouch = pulse_bell(u, 0.25, 0.25)
        helper.set_bone("pelvis", rx_deg=18.0 * e + 8.0 * crouch, dz=-0.05 * crouch - 0.02 * e)
        helper.set_bone("spine_02", rx_deg=10.0 * e)
        helper.set_bone("head", rx_deg=-14.0 * e)
        helper.set_bone("thigh_l", rx_deg=-38.0 * math.sin(u * math.pi))
        helper.set_bone("calf_l", rx_deg=48.0 * math.sin(u * math.pi))
        helper.set_bone("thigh_r", rx_deg=24.0 * math.sin(u * math.pi) - 18.0 * e)
        helper.set_bone("calf_r", rx_deg=25.0 * crouch + 22.0 * e)
        helper.apply_base_standing_arms(combat_ready=True, breath_phase=phase)

    elif clip_id == "stop_f":
        brake = pulse_bell(u, 0.35, 0.35)
        settle = smoothstep(max(0.0, (u - 0.4) / 0.6))
        helper.set_bone("pelvis", rx_deg=-14.0 * brake + 6.0 * settle, dz=-0.07 * brake - 0.02 * settle)
        helper.set_bone("spine_02", rx_deg=-10.0 * brake + 4.0 * settle)
        helper.set_bone("thigh_l", rx_deg=-32.0 * brake - 14.0 * settle)
        helper.set_bone("calf_l", rx_deg=54.0 * brake + 28.0 * settle)
        helper.set_bone("foot_l", rx_deg=-22.0 * brake - 14.0 * settle)
        helper.set_bone("thigh_r", rx_deg=-18.0 * brake - 12.0 * settle)
        helper.set_bone("calf_r", rx_deg=38.0 * brake + 24.0 * settle)
        helper.apply_base_standing_arms(combat_ready=True, breath_phase=phase)

    elif clip_id in ("turn_l90", "turn_r90"):
        s_sign = 1.0 if clip_id == "turn_l90" else -1.0
        step_lead = pulse_bell(u, 0.35, 0.32)
        step_follow = pulse_bell(u, 0.70, 0.28)
        yaw = s_sign * 90.0 * smoothstep(u) * (1.0 - smoothstep(max(0.0, (u - 0.75) / 0.25)))
        helper.set_bone("pelvis", rz_deg=yaw * 0.5, dz=-0.03 * (step_lead + step_follow))
        helper.set_bone("spine_02", rz_deg=yaw * 0.3)
        helper.set_bone("head", rz_deg=yaw * 0.2)
        helper.set_bone("thigh_l", rx_deg=-26.0 * (step_lead if s_sign > 0 else step_follow), rz_deg=s_sign * 18.0 * step_lead)
        helper.set_bone("calf_l", rx_deg=44.0 * (step_lead if s_sign > 0 else step_follow))
        helper.set_bone("thigh_r", rx_deg=-26.0 * (step_follow if s_sign > 0 else step_lead), rz_deg=s_sign * 18.0 * step_follow)
        helper.set_bone("calf_r", rx_deg=44.0 * (step_follow if s_sign > 0 else step_lead))
        helper.apply_base_standing_arms(combat_ready=True)

    elif clip_id in ("pivot_l180", "pivot_r180"):
        s_sign = 1.0 if clip_id == "pivot_l180" else -1.0
        plant = pulse_bell(u, 0.45, 0.40)
        helper.set_bone("pelvis", rx_deg=14.0 * plant, ry_deg=s_sign * 12.0 * plant, rz_deg=s_sign * 75.0 * math.sin(u * math.pi), dz=-0.08 * plant)
        helper.set_bone("spine_02", rx_deg=10.0 * plant, rz_deg=s_sign * 35.0 * math.sin(u * math.pi))
        helper.set_bone("thigh_l", rx_deg=-35.0 * plant, ry_deg=10.0 * plant)
        helper.set_bone("calf_l", rx_deg=62.0 * plant)
        helper.set_bone("thigh_r", rx_deg=-28.0 * plant, ry_deg=-10.0 * plant)
        helper.set_bone("calf_r", rx_deg=52.0 * plant)
        helper.apply_base_standing_arms(combat_ready=True)

    # --- 4. JUMP, AIR, FALL, LAND ---
    elif clip_id == "jump_start":
        antic = pulse_bell(u, 0.32, 0.32)
        launch = smoothstep(max(0.0, (u - 0.35) / 0.65))
        helper.set_bone("pelvis", rx_deg=24.0 * antic - 8.0 * launch, dz=-0.16 * antic + 0.14 * launch)
        helper.set_bone("spine_02", rx_deg=16.0 * antic - 10.0 * launch)
        helper.set_bone("thigh_l", rx_deg=-52.0 * antic - 28.0 * launch)
        helper.set_bone("calf_l", rx_deg=88.0 * antic + 18.0 * launch)
        helper.set_bone("foot_l", rx_deg=-32.0 * antic + 28.0 * launch)
        helper.set_bone("thigh_r", rx_deg=-48.0 * antic - 12.0 * launch)
        helper.set_bone("calf_r", rx_deg=84.0 * antic + 38.0 * launch)
        helper.set_bone("foot_r", rx_deg=-30.0 * antic + 32.0 * launch)
        helper.set_bone("upperarm_l", ry_deg=55.0 - 35.0 * launch, rz_deg=25.0 * antic - 45.0 * launch)
        helper.set_bone("upperarm_r", ry_deg=-55.0 + 35.0 * launch, rz_deg=-25.0 * antic + 45.0 * launch)
        helper.set_bone("lowerarm_l", ry_deg=20.0, rz_deg=-55.0)
        helper.set_bone("lowerarm_r", ry_deg=-20.0, rz_deg=55.0)

    elif clip_id == "jump_air":
        osc = math.sin(phase)
        helper.set_bone("pelvis", rx_deg=6.0 + 3.0 * osc, dz=0.12 + 0.015 * osc)
        helper.set_bone("spine_02", rx_deg=6.0)
        helper.set_bone("thigh_l", rx_deg=-38.0 + 4.0 * osc, ry_deg=8.0)
        helper.set_bone("calf_l", rx_deg=52.0 + 5.0 * osc)
        helper.set_bone("foot_l", rx_deg=18.0)
        helper.set_bone("thigh_r", rx_deg=-22.0 - 4.0 * osc, ry_deg=-8.0)
        helper.set_bone("calf_r", rx_deg=68.0 - 5.0 * osc)
        helper.set_bone("foot_r", rx_deg=24.0)
        helper.set_bone("upperarm_l", ry_deg=28.0 + 5.0 * osc, rz_deg=-24.0)
        helper.set_bone("lowerarm_l", ry_deg=15.0, rz_deg=-52.0)
        helper.set_bone("upperarm_r", ry_deg=-28.0 - 5.0 * osc, rz_deg=24.0)
        helper.set_bone("lowerarm_r", ry_deg=-15.0, rz_deg=52.0)
        helper.apply_secondary_follow_through(phase, amp_deg=14.0, head_pitch_deg=-12.0)

    elif clip_id == "fall":
        # Distinct long-fall posture: arched spine, arms raised wide above shoulders, legs cycling
        osc = math.sin(phase)
        helper.set_bone("pelvis", rx_deg=-12.0 + 4.0 * osc, dz=0.15)
        helper.set_bone("spine_02", rx_deg=-10.0)
        helper.set_bone("head", rx_deg=18.0)  # Looking down toward ground!
        helper.set_bone("thigh_l", rx_deg=-26.0 + 14.0 * osc, ry_deg=16.0)
        helper.set_bone("calf_l", rx_deg=42.0 + 12.0 * osc)
        helper.set_bone("thigh_r", rx_deg=-26.0 - 14.0 * osc, ry_deg=-16.0)
        helper.set_bone("calf_r", rx_deg=42.0 - 12.0 * osc)
        helper.set_bone("upperarm_l", ry_deg=-18.0 + 8.0 * osc, rz_deg=-12.0)
        helper.set_bone("lowerarm_l", ry_deg=-10.0, rz_deg=-35.0)
        helper.set_bone("upperarm_r", ry_deg=18.0 - 8.0 * osc, rz_deg=12.0)
        helper.set_bone("lowerarm_r", ry_deg=10.0, rz_deg=35.0)
        helper.apply_secondary_follow_through(phase, amp_deg=24.0, head_pitch_deg=-24.0)
        shape_weights["expr_surprise"] = 0.70

    elif clip_id == "jump_land":
        comp = pulse_bell(u, 0.28, 0.28)
        helper.set_bone("pelvis", rx_deg=22.0 * comp, dz=-0.16 * comp)
        helper.set_bone("spine_02", rx_deg=14.0 * comp)
        helper.set_bone("head", rx_deg=-12.0 * comp)
        helper.set_bone("thigh_l", rx_deg=-48.0 * comp, ry_deg=8.0 * comp)
        helper.set_bone("calf_l", rx_deg=84.0 * comp)
        helper.set_bone("foot_l", rx_deg=-34.0 * comp)
        helper.set_bone("thigh_r", rx_deg=-44.0 * comp, ry_deg=-8.0 * comp)
        helper.set_bone("calf_r", rx_deg=78.0 * comp)
        helper.set_bone("foot_r", rx_deg=-32.0 * comp)
        helper.apply_base_standing_arms(combat_ready=True, breath_phase=phase)
        shape_weights["corr_knee_bend_l"] = comp * 0.8
        shape_weights["corr_knee_bend_r"] = comp * 0.8

    elif clip_id == "land_heavy":
        comp = pulse_bell(u, 0.35, 0.35)
        helper.set_bone("pelvis", rx_deg=42.0 * comp, dz=-0.34 * comp)
        helper.set_bone("spine_01", rx_deg=18.0 * comp)
        helper.set_bone("spine_02", rx_deg=18.0 * comp)
        helper.set_bone("head", rx_deg=-24.0 * comp)
        helper.set_bone("thigh_l", rx_deg=-76.0 * comp, ry_deg=14.0 * comp)
        helper.set_bone("calf_l", rx_deg=112.0 * comp)
        helper.set_bone("foot_l", rx_deg=-36.0 * comp)
        helper.set_bone("thigh_r", rx_deg=-68.0 * comp, ry_deg=-12.0 * comp)
        helper.set_bone("calf_r", rx_deg=105.0 * comp)
        helper.set_bone("foot_r", rx_deg=-36.0 * comp)
        # Left hand reaches down to brace against the floor at apex of heavy landing!
        helper.set_bone("upperarm_l", rx_deg=52.0 * comp, ry_deg=45.0, rz_deg=-48.0 * comp)
        helper.set_bone("lowerarm_l", rx_deg=35.0 * comp, ry_deg=20.0, rz_deg=-25.0)
        helper.set_bone("upperarm_r", ry_deg=-35.0, rz_deg=-32.0 * comp)
        helper.set_bone("lowerarm_r", ry_deg=-20.0, rz_deg=45.0)
        shape_weights["corr_knee_bend_l"] = comp
        shape_weights["corr_knee_bend_r"] = comp
        shape_weights["corr_hip_bend_l"] = comp
        shape_weights["corr_hip_bend_r"] = comp

    # --- 5. ROOT-MOTION DASHES (2.00 m nominal displacement on root bone!) ---
    elif clip_id in ("dash_f", "dash_b", "dash_l", "dash_r"):
        dist = 2.00 * ease_out_cubic(u)
        burst = math.sin(u * math.pi)
        dx, dy = 0.0, 0.0
        lean_rx, lean_ry = 0.0, 0.0
        if clip_id == "dash_f":
            dy = -dist  # -Y is Forward (2.0 m)
            lean_rx = 34.0 * burst
        elif clip_id == "dash_b":
            dy = dist   # +Y is Backward (2.0 m)
            lean_rx = -28.0 * burst
        elif clip_id == "dash_l":
            dx = dist   # +X is Left (2.0 m)
            lean_ry = 32.0 * burst
        elif clip_id == "dash_r":
            dx = -dist  # -X is Right (2.0 m)
            lean_ry = -32.0 * burst

        helper.set_bone("root", dx=dx, dy=dy)
        helper.set_bone("pelvis", rx_deg=lean_rx * 0.5, ry_deg=lean_ry * 0.5, dz=-0.12 * burst)
        helper.set_bone("spine_02", rx_deg=lean_rx * 0.35, ry_deg=lean_ry * 0.35)
        helper.set_bone("spine_03", rx_deg=lean_rx * 0.25, ry_deg=lean_ry * 0.25)
        helper.set_bone("head", rx_deg=-lean_rx * 0.6, ry_deg=-lean_ry * 0.5)
        helper.set_bone("thigh_l", rx_deg=-42.0 * burst)
        helper.set_bone("calf_l", rx_deg=72.0 * burst)
        helper.set_bone("thigh_r", rx_deg=-18.0 * burst)
        helper.set_bone("calf_r", rx_deg=54.0 * burst)
        helper.apply_base_standing_arms(combat_ready=True)
        helper.apply_secondary_follow_through(u * math.pi, amp_deg=22.0, head_pitch_deg=lean_rx)

    # --- 6. BLINK OUT / BLINK IN (in-place, zero baked root travel!) ---
    elif clip_id == "blink_out":
        fold = smoothstep(u)
        helper.set_bone("pelvis", rx_deg=28.0 * fold, dz=-0.18 * fold)
        helper.set_bone("spine_02", rx_deg=18.0 * fold)
        helper.set_bone("upperarm_l", ry_deg=35.0, rz_deg=-72.0 * fold)
        helper.set_bone("lowerarm_l", ry_deg=15.0, rz_deg=-95.0 * fold)
        helper.set_bone("upperarm_r", ry_deg=-35.0, rz_deg=72.0 * fold)
        helper.set_bone("lowerarm_r", ry_deg=-15.0, rz_deg=95.0 * fold)
        helper.set_bone("thigh_l", rx_deg=-45.0 * fold)
        helper.set_bone("calf_l", rx_deg=78.0 * fold)
        helper.set_bone("thigh_r", rx_deg=-45.0 * fold)
        helper.set_bone("calf_r", rx_deg=78.0 * fold)

    elif clip_id == "blink_in":
        unfold = 1.0 - smoothstep(u)
        helper.set_bone("pelvis", rx_deg=24.0 * unfold, dz=-0.15 * unfold)
        helper.set_bone("spine_02", rx_deg=14.0 * unfold)
        helper.set_bone("upperarm_l", ry_deg=42.0, rz_deg=-25.0 - 40.0 * unfold)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-68.0)
        helper.set_bone("upperarm_r", ry_deg=-42.0, rz_deg=25.0 + 40.0 * unfold)
        helper.set_bone("lowerarm_r", ry_deg=-18.0, rz_deg=68.0)
        helper.set_bone("thigh_l", rx_deg=-38.0 * unfold - 12.0)
        helper.set_bone("calf_l", rx_deg=65.0 * unfold + 24.0)
        helper.set_bone("thigh_r", rx_deg=-38.0 * unfold - 12.0)
        helper.set_bone("calf_r", rx_deg=65.0 * unfold + 24.0)

    # --- 7. MELEE COMBO (melee_1, melee_2, melee_3 with extended forearm blade!) ---
    elif clip_id == "melee_1":
        # Diagonal inward high-to-low forearm-blade slash
        prep = pulse_bell(u, 0.20, 0.20)
        slash = smoothstep(max(0.0, min(1.0, (u - 0.20) / 0.35))) * (1.0 - smoothstep(max(0.0, (u - 0.65) / 0.35)))
        ext = 1.0 if 0.08 <= u <= 0.88 else 0.0
        helper.set_bone("blade_extend_r", dx=-0.24 * ext)
        helper.set_bone("pelvis", rx_deg=14.0 * slash, rz_deg=-28.0 * prep + 42.0 * slash, dz=-0.06 * slash)
        helper.set_bone("spine_02", rx_deg=12.0 * slash, rz_deg=-22.0 * prep + 36.0 * slash)
        helper.set_bone("spine_03", rz_deg=-18.0 * prep + 32.0 * slash)
        helper.set_bone("head", rz_deg=15.0 * prep - 25.0 * slash)
        helper.set_bone("upperarm_r", ry_deg=24.0 * prep - 45.0 * slash, rz_deg=-28.0 * prep + 108.0 * slash)
        helper.set_bone("lowerarm_r", ry_deg=15.0 * prep - 28.0 * slash, rz_deg=75.0 * prep + 35.0 * slash)
        helper.set_fingers_curl("r", 85.0)
        helper.set_bone("upperarm_l", ry_deg=45.0, rz_deg=-35.0 + 25.0 * slash)
        helper.set_bone("lowerarm_l", ry_deg=20.0, rz_deg=-65.0)
        helper.set_bone("thigh_l", rx_deg=-28.0 * slash)
        helper.set_bone("calf_l", rx_deg=45.0 * slash)
        helper.set_bone("thigh_r", rx_deg=-18.0 * prep + 15.0 * slash)
        helper.set_bone("calf_r", rx_deg=32.0)
        shape_weights["expr_anger"] = 0.75 * slash

    elif clip_id == "melee_2":
        # Reverse backhand outward slash with left-to-right weight transfer
        prep = pulse_bell(u, 0.22, 0.22)
        slash = smoothstep(max(0.0, min(1.0, (u - 0.22) / 0.36))) * (1.0 - smoothstep(max(0.0, (u - 0.68) / 0.32)))
        ext = 1.0 if 0.05 <= u <= 0.90 else 0.0
        helper.set_bone("blade_extend_r", dx=-0.26 * ext)
        helper.set_bone("pelvis", rx_deg=10.0 * slash, rz_deg=38.0 * prep - 48.0 * slash, dx=-0.06 * slash, dz=-0.07 * slash)
        helper.set_bone("spine_02", rz_deg=32.0 * prep - 42.0 * slash)
        helper.set_bone("spine_03", rz_deg=28.0 * prep - 38.0 * slash)
        helper.set_bone("upperarm_r", ry_deg=-22.0, rz_deg=112.0 * prep - 25.0 * slash)
        helper.set_bone("lowerarm_r", ry_deg=-12.0, rz_deg=95.0 * prep + 10.0 * slash)
        helper.set_fingers_curl("r", 85.0)
        helper.set_bone("upperarm_l", ry_deg=38.0, rz_deg=-55.0 * prep - 15.0 * slash)
        helper.set_bone("lowerarm_l", ry_deg=20.0, rz_deg=-70.0)
        helper.set_bone("thigh_l", rx_deg=-22.0, ry_deg=12.0 * slash)
        helper.set_bone("calf_l", rx_deg=38.0)
        helper.set_bone("thigh_r", rx_deg=-32.0 * slash, ry_deg=-14.0 * slash)
        helper.set_bone("calf_r", rx_deg=54.0 * slash)
        shape_weights["expr_anger"] = 0.85 * slash

    elif clip_id == "melee_3":
        # Committed overhead leap/lunge finisher with heavy follow-through
        windup = pulse_bell(u, 0.26, 0.24)
        strike = smoothstep(max(0.0, min(1.0, (u - 0.28) / 0.28))) * (1.0 - smoothstep(max(0.0, (u - 0.74) / 0.26)))
        helper.set_bone("blade_extend_r", dx=-0.28 * (1.0 if 0.05 <= u <= 0.92 else 0.0))
        helper.set_bone("pelvis", rx_deg=-14.0 * windup + 32.0 * strike, rz_deg=-30.0 * windup + 48.0 * strike, dz=0.08 * windup - 0.16 * strike)
        helper.set_bone("spine_02", rx_deg=-12.0 * windup + 22.0 * strike, rz_deg=-24.0 * windup + 38.0 * strike)
        helper.set_bone("spine_03", rx_deg=-10.0 * windup + 18.0 * strike, rz_deg=-20.0 * windup + 34.0 * strike)
        helper.set_bone("upperarm_r", ry_deg=48.0 * windup - 52.0 * strike, rz_deg=25.0 * windup + 98.0 * strike)
        helper.set_bone("lowerarm_r", ry_deg=22.0 * windup - 24.0 * strike, rz_deg=65.0 * windup + 35.0 * strike)
        helper.set_fingers_curl("r", 90.0)
        helper.set_bone("upperarm_l", ry_deg=35.0, rz_deg=-45.0 * windup + 20.0 * strike)
        helper.set_bone("thigh_l", rx_deg=-48.0 * strike - 20.0 * windup)
        helper.set_bone("calf_l", rx_deg=76.0 * strike + 35.0 * windup)
        helper.set_bone("thigh_r", rx_deg=22.0 * strike - 25.0 * windup)
        helper.set_bone("calf_r", rx_deg=42.0 * strike + 35.0 * windup)
        shape_weights["expr_anger"] = 0.95 * strike

    # --- 8. RANGED FIRE, RANGED BURST, RELOAD ---
    elif clip_id == "ranged_fire":
        kick = pulse_bell(u, 0.28, 0.22)
        aim_w = math.sin(u * math.pi) ** 0.4
        helper.set_bone("spine_02", rx_deg=-4.0 * kick, rz_deg=12.0 * aim_w)
        helper.set_bone("spine_03", rx_deg=-6.0 * kick, rz_deg=16.0 * aim_w)
        helper.set_bone("upperarm_r", ry_deg=-14.0 + 10.0 * kick, rz_deg=78.0 * aim_w - 12.0 * kick)
        helper.set_bone("lowerarm_r", ry_deg=-6.0 + 14.0 * kick, rz_deg=86.0 * aim_w - 16.0 * kick)
        helper.set_bone("hand_r", ry_deg=12.0 * kick, rz_deg=82.0 * aim_w)
        helper.set_fingers_curl("r", 70.0)
        helper.set_bone("upperarm_l", ry_deg=44.0, rz_deg=-28.0)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-68.0)
        shape_weights["expr_focus"] = 0.80

    elif clip_id == "ranged_burst":
        k1 = pulse_bell(u, 0.22, 0.10)
        k2 = pulse_bell(u, 0.45, 0.10)
        k3 = pulse_bell(u, 0.68, 0.12)
        kick = min(1.0, k1 + k2 + k3)
        aim_w = math.sin(u * math.pi) ** 0.35
        helper.set_bone("spine_02", rx_deg=-5.0 * kick, rz_deg=14.0 * aim_w)
        helper.set_bone("spine_03", rx_deg=-7.0 * kick, rz_deg=18.0 * aim_w)
        helper.set_bone("upperarm_r", ry_deg=-14.0 + 12.0 * kick, rz_deg=80.0 * aim_w - 14.0 * kick)
        helper.set_bone("lowerarm_r", ry_deg=-6.0 + 16.0 * kick, rz_deg=88.0 * aim_w - 18.0 * kick)
        helper.set_bone("hand_r", ry_deg=14.0 * kick, rz_deg=84.0 * aim_w)
        helper.set_fingers_curl("r", 75.0)
        helper.set_bone("upperarm_l", ry_deg=42.0, rz_deg=-32.0)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-72.0)
        shape_weights["expr_focus"] = 0.85

    elif clip_id == "reload":
        # Physical emitter-cell manipulation with hand-to-object contact on prop_cell!
        active = math.sin(u * math.pi) ** 0.5
        extract = pulse_bell(u, 0.38, 0.18)
        insert = pulse_bell(u, 0.68, 0.16)
        helper.set_bone("spine_02", rx_deg=8.0 * active, rz_deg=-8.0 * active)
        helper.set_bone("spine_03", rx_deg=10.0 * active, rz_deg=-10.0 * active)
        helper.set_bone("head", rx_deg=18.0 * active, rz_deg=-12.0 * active)  # Looking directly at wrist emitter cell slot
        # Right arm brings wrist emitter across chest
        helper.set_bone("upperarm_r", ry_deg=-28.0, rz_deg=68.0 * active)
        helper.set_bone("lowerarm_r", ry_deg=-14.0, rz_deg=104.0 * active)
        helper.set_bone("hand_r", ry_deg=-10.0, rz_deg=85.0 * active)
        helper.set_fingers_curl("r", 40.0)
        # Left hand reaches across to grasp prop_cell, extracts it, and inserts fresh cell
        helper.set_bone("upperarm_l", ry_deg=32.0, rz_deg=-64.0 * active - 14.0 * extract)
        helper.set_bone("lowerarm_l", ry_deg=16.0, rz_deg=-98.0 * active + 18.0 * extract - 8.0 * insert)
        helper.set_bone("hand_l", ry_deg=10.0, rz_deg=-80.0 * active)
        helper.set_fingers_curl("l", 68.0 * active)
        # Translate prop_cell along with left hand during extraction/insertion
        helper.set_bone("prop_cell", dx=0.14 * extract, dy=-0.06 * extract, dz=0.04 * extract - 0.015 * insert)
        shape_weights["expr_focus"] = 0.75 * active

    # --- 9. CASTS, CHANNEL, CHARGE, DEPLOY, UPLINK ---
    elif clip_id == "cast_directional":
        wind = pulse_bell(u, 0.25, 0.22)
        rel = smoothstep(max(0.0, min(1.0, (u - 0.28) / 0.25))) * (1.0 - smoothstep(max(0.0, (u - 0.72) / 0.28)))
        helper.set_bone("pelvis", rx_deg=10.0 * rel, rz_deg=22.0 * wind - 28.0 * rel, dz=-0.04 * rel)
        helper.set_bone("spine_03", rx_deg=8.0 * rel, rz_deg=18.0 * wind - 24.0 * rel)
        helper.set_bone("upperarm_l", ry_deg=35.0 * (1.0 - rel) + 8.0 * rel, rz_deg=20.0 * wind - 86.0 * rel)
        helper.set_bone("lowerarm_l", ry_deg=15.0 * (1.0 - rel), rz_deg=-75.0 * wind - 88.0 * rel)
        helper.set_bone("hand_l", ry_deg=-25.0 * rel, rz_deg=-85.0 * rel)
        helper.set_fingers_curl("l", 70.0 * wind - 10.0 * rel)
        helper.set_bone("upperarm_r", ry_deg=-48.0, rz_deg=24.0)
        helper.set_bone("lowerarm_r", ry_deg=-25.0, rz_deg=58.0)

    elif clip_id == "cast_ground":
        press = pulse_bell(u, 0.52, 0.36)
        helper.set_bone("pelvis", rx_deg=32.0 * press, dz=-0.24 * press)
        helper.set_bone("spine_02", rx_deg=18.0 * press)
        helper.set_bone("head", rx_deg=14.0 * press)  # Looking at target ground zone
        helper.set_bone("thigh_l", rx_deg=-58.0 * press)
        helper.set_bone("calf_l", rx_deg=92.0 * press)
        helper.set_bone("thigh_r", rx_deg=-42.0 * press)
        helper.set_bone("calf_r", rx_deg=78.0 * press)
        helper.set_bone("upperarm_l", rx_deg=45.0 * press, ry_deg=36.0, rz_deg=-62.0 * press)
        helper.set_bone("lowerarm_l", rx_deg=35.0 * press, ry_deg=18.0, rz_deg=-45.0 * press)
        helper.set_bone("upperarm_r", rx_deg=45.0 * press, ry_deg=-36.0, rz_deg=62.0 * press)
        helper.set_bone("lowerarm_r", rx_deg=35.0 * press, ry_deg=-18.0, rz_deg=45.0 * press)

    elif clip_id == "cast_self":
        gather = pulse_bell(u, 0.30, 0.25)
        burst = pulse_bell(u, 0.65, 0.28)
        helper.set_bone("pelvis", rx_deg=12.0 * gather - 14.0 * burst, dz=-0.06 * gather + 0.04 * burst)
        helper.set_bone("spine_03", rx_deg=14.0 * gather - 18.0 * burst)
        helper.set_bone("head", rx_deg=12.0 * gather - 20.0 * burst)
        helper.set_bone("upperarm_l", ry_deg=38.0 - 22.0 * burst, rz_deg=-68.0 * gather + 28.0 * burst)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-98.0 * gather - 15.0 * burst)
        helper.set_bone("upperarm_r", ry_deg=-38.0 + 22.0 * burst, rz_deg=68.0 * gather - 28.0 * burst)
        helper.set_bone("lowerarm_r", ry_deg=-18.0, rz_deg=98.0 * gather + 15.0 * burst)

    elif clip_id in ("channel_start", "channel_loop", "channel_end", "channel_interrupt"):
        if clip_id == "channel_start":
            w = smoothstep(u)
            osc = 0.0
            jolt = 0.0
        elif clip_id == "channel_loop":
            w = 1.0
            osc = math.sin(phase)
            jolt = 0.0
        elif clip_id == "channel_end":
            w = 1.0 - smoothstep(u)
            osc = 0.0
            jolt = 0.0
        else:  # channel_interrupt
            w = 1.0 - smoothstep(u)
            osc = 0.0
            jolt = pulse_bell(u, 0.32, 0.28)

        helper.set_bone("pelvis", rx_deg=10.0 * w - 18.0 * jolt, rz_deg=8.0 * jolt, dz=-0.05 * w - 0.04 * jolt)
        helper.set_bone("spine_02", rx_deg=8.0 * w - 16.0 * jolt)
        helper.set_bone("spine_03", rx_deg=8.0 * w + 2.0 * osc - 14.0 * jolt, rz_deg=14.0 * jolt)
        helper.set_bone("head", rx_deg=-10.0 * w - 18.0 * jolt, rz_deg=18.0 * jolt)
        # Dual-hand sustained forward beam emission
        helper.set_bone("upperarm_l", ry_deg=52.0 - 38.0 * w + 25.0 * jolt, rz_deg=-12.0 - 66.0 * w + 35.0 * jolt)
        helper.set_bone("lowerarm_l", ry_deg=35.0 - 28.0 * w, rz_deg=-30.0 - 52.0 * w + 2.0 * osc)
        helper.set_bone("upperarm_r", ry_deg=-52.0 + 38.0 * w - 25.0 * jolt, rz_deg=12.0 + 68.0 * w - 35.0 * jolt)
        helper.set_bone("lowerarm_r", ry_deg=-35.0 + 28.0 * w, rz_deg=30.0 + 54.0 * w - 2.0 * osc)
        helper.set_bone("thigh_l", rx_deg=-20.0 * w, ry_deg=6.0 * w)
        helper.set_bone("calf_l", rx_deg=36.0 * w)
        helper.set_bone("thigh_r", rx_deg=-18.0 * w, ry_deg=-6.0 * w)
        helper.set_bone("calf_r", rx_deg=34.0 * w)
        shape_weights["expr_pain" if jolt > 0.1 else "expr_focus"] = max(w * 0.75, jolt)

    elif clip_id in ("charge_start", "charge_hold", "charge_release", "charge_cancel"):
        if clip_id == "charge_start":
            w = smoothstep(u)
            rel = 0.0
            vib = 0.0
        elif clip_id == "charge_hold":
            w = 1.0
            rel = 0.0
            vib = math.sin(2.0 * phase)
        elif clip_id == "charge_release":
            w = 1.0 - smoothstep(min(1.0, u * 2.2))
            rel = pulse_bell(u, 0.42, 0.35)
            vib = 0.0
        else:  # charge_cancel
            w = 1.0 - smoothstep(u)
            rel = 0.0
            vib = 0.0

        helper.set_bone("pelvis", rx_deg=16.0 * w + 24.0 * rel, rz_deg=-32.0 * w + 38.0 * rel, dz=-0.10 * w - 0.08 * rel + 0.008 * vib)
        helper.set_bone("spine_02", rx_deg=10.0 * w + 16.0 * rel, rz_deg=-24.0 * w + 30.0 * rel)
        helper.set_bone("spine_03", rx_deg=8.0 * w + 14.0 * rel, rz_deg=-22.0 * w + 28.0 * rel + 3.0 * vib)
        helper.set_bone("upperarm_r", ry_deg=-48.0 + 28.0 * w + 32.0 * rel, rz_deg=-28.0 * w + 92.0 * rel + 4.0 * vib)
        helper.set_bone("lowerarm_r", ry_deg=-32.0 + 22.0 * w, rz_deg=88.0 * w + 82.0 * rel)
        helper.set_fingers_curl("r", 85.0 * w + 10.0 * rel)
        helper.set_bone("upperarm_l", ry_deg=44.0 - 16.0 * w, rz_deg=-48.0 * w + 24.0 * rel)
        helper.set_bone("lowerarm_l", ry_deg=22.0, rz_deg=-72.0 * w - 35.0 * rel)
        helper.set_bone("thigh_l", rx_deg=-28.0 * w - 36.0 * rel)
        helper.set_bone("calf_l", rx_deg=48.0 * w + 58.0 * rel)
        helper.set_bone("thigh_r", rx_deg=-34.0 * w + 18.0 * rel)
        helper.set_bone("calf_r", rx_deg=56.0 * w + 24.0 * rel)
        shape_weights["expr_focus"] = max(w, rel) * 0.85

    elif clip_id == "deploy":
        # Grab prop_beacon from right thigh holster and kneel to place it on the floor in front
        grab = pulse_bell(u, 0.22, 0.16)
        place = pulse_bell(u, 0.58, 0.26)
        deployed = smoothstep(max(0.0, (u - 0.48) / 0.15))
        kneel = grab * 0.3 + place
        helper.set_bone("pelvis", rx_deg=28.0 * place, dz=-0.28 * place)
        helper.set_bone("spine_02", rx_deg=18.0 * place)
        helper.set_bone("head", rx_deg=20.0 * kneel)
        helper.set_bone("thigh_l", rx_deg=-64.0 * place)
        helper.set_bone("calf_l", rx_deg=102.0 * place)
        helper.set_bone("thigh_r", rx_deg=-38.0 * place)
        helper.set_bone("calf_r", rx_deg=82.0 * place)
        helper.set_bone("upperarm_r", rx_deg=42.0 * place, ry_deg=-52.0 + 18.0 * place, rz_deg=15.0 * grab + 68.0 * place)
        helper.set_bone("lowerarm_r", rx_deg=35.0 * place, ry_deg=-24.0, rz_deg=45.0 * grab + 52.0 * place)
        helper.set_bone("hand_r", ry_deg=-15.0, rz_deg=45.0 * place)
        helper.set_fingers_curl("r", 65.0 * (grab + place * 0.5))
        # Translate prop_beacon from holster to floor placement point in front of operative
        helper.set_bone("prop_beacon", dx=0.12 * deployed, dy=-0.42 * deployed, dz=-0.52 * deployed)

    elif clip_id in ("uplink_start", "uplink_loop", "uplink_end", "uplink_cancel"):
        if clip_id == "uplink_start":
            w = smoothstep(u)
            tap = 0.0
        elif clip_id == "uplink_loop":
            w = 1.0
            tap = math.sin(2.0 * phase)
        else:
            w = 1.0 - smoothstep(u)
            tap = 0.0

        # Feet remain strictly planted while left hand operates holographic console on right wrist
        helper.set_bone("spine_02", rx_deg=8.0 * w)
        helper.set_bone("spine_03", rx_deg=10.0 * w)
        helper.set_bone("head", rx_deg=22.0 * w, rz_deg=-8.0 * w + 3.0 * tap)
        helper.set_bone("upperarm_r", ry_deg=-34.0, rz_deg=64.0 * w)
        helper.set_bone("lowerarm_r", ry_deg=-18.0, rz_deg=98.0 * w)
        helper.set_bone("upperarm_l", ry_deg=36.0, rz_deg=-58.0 * w)
        helper.set_bone("lowerarm_l", ry_deg=20.0 + 6.0 * tap, rz_deg=-92.0 * w + 8.0 * tap)
        helper.set_fingers_curl("l", 25.0 + 15.0 * tap)

    # --- 10. ADDITIVE HIT REACTIONS (hit_f, hit_b, hit_l, hit_r) ---
    elif clip_id in ("hit_f", "hit_b", "hit_l", "hit_r"):
        imp = math.sin(u * math.pi) ** 0.7
        rx, ry, rz = 0.0, 0.0, 0.0
        if clip_id == "hit_f":
            rx = -22.0 * imp  # Knocked backward (+Y) from front impact
        elif clip_id == "hit_b":
            rx = 22.0 * imp   # Knocked forward (-Y) from back impact
        elif clip_id == "hit_l":
            ry = -22.0 * imp  # Knocked right (-X) from left impact
            rz = -16.0 * imp
        elif clip_id == "hit_r":
            ry = 22.0 * imp   # Knocked left (+X) from right impact
            rz = 16.0 * imp

        # Only upper-body impulse — feet remain 100% planted at neutral rest!
        helper.set_bone("spine_01", rx_deg=rx * 0.35, ry_deg=ry * 0.35, rz_deg=rz * 0.35)
        helper.set_bone("spine_02", rx_deg=rx * 0.45, ry_deg=ry * 0.45, rz_deg=rz * 0.45)
        helper.set_bone("spine_03", rx_deg=rx * 0.55, ry_deg=ry * 0.55, rz_deg=rz * 0.55)
        helper.set_bone("neck_01", rx_deg=rx * 0.40, ry_deg=ry * 0.40)
        helper.set_bone("head", rx_deg=rx * 0.65, ry_deg=ry * 0.65, rz_deg=rz * 0.50)
        shape_weights["expr_pain"] = imp * 0.90

    # --- 11. CROWD CONTROL: STUN, KNOCKBACK, KNOCKUP, KNOCKDOWN, PRONE, GETUP, SLEEP ---
    elif clip_id in ("stun_start", "stun_loop", "stun_end"):
        w = smoothstep(u) if clip_id == "stun_start" else ((1.0 - smoothstep(u)) if clip_id == "stun_end" else 1.0)
        sway_x = math.sin(phase) * w
        sway_y = math.cos(phase) * w
        helper.set_bone("pelvis", rx_deg=12.0 * w + 6.0 * sway_y, ry_deg=8.0 * sway_x, dx=0.04 * sway_x, dz=-0.06 * w)
        helper.set_bone("spine_02", rx_deg=10.0 * w + 8.0 * sway_y, ry_deg=10.0 * sway_x)
        helper.set_bone("head", rx_deg=14.0 * w + 12.0 * sway_y, ry_deg=14.0 * sway_x, rz_deg=16.0 * sway_x)
        helper.set_bone("upperarm_l", ry_deg=56.0, rz_deg=14.0 * sway_y)
        helper.set_bone("lowerarm_l", ry_deg=42.0, rz_deg=-25.0)
        helper.set_bone("upperarm_r", ry_deg=-56.0, rz_deg=-14.0 * sway_y)
        helper.set_bone("lowerarm_r", ry_deg=-42.0, rz_deg=25.0)
        helper.set_bone("thigh_l", rx_deg=-20.0 * w)
        helper.set_bone("calf_l", rx_deg=36.0 * w)
        helper.set_bone("thigh_r", rx_deg=-20.0 * w)
        helper.set_bone("calf_r", rx_deg=36.0 * w)
        shape_weights["expr_concern_sadness"] = 0.75 * w

    elif clip_id == "knockback":
        br = math.sin(u * math.pi)
        helper.set_bone("pelvis", rx_deg=24.0 * br, dz=-0.14 * br)
        helper.set_bone("spine_02", rx_deg=18.0 * br)
        helper.set_bone("head", rx_deg=-16.0 * br)
        helper.set_bone("upperarm_l", ry_deg=35.0, rz_deg=-65.0 * br)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-85.0 * br)
        helper.set_bone("upperarm_r", ry_deg=-35.0, rz_deg=65.0 * br)
        helper.set_bone("lowerarm_r", ry_deg=-18.0, rz_deg=85.0 * br)
        helper.set_bone("thigh_l", rx_deg=-46.0 * br)
        helper.set_bone("calf_l", rx_deg=72.0 * br)
        helper.set_bone("thigh_r", rx_deg=16.0 * br)
        helper.set_bone("calf_r", rx_deg=38.0 * br)
        shape_weights["expr_pain"] = 0.80 * br

    elif clip_id in ("knockup_start", "knockup_air"):
        w = smoothstep(u) if clip_id == "knockup_start" else 1.0
        flail = math.sin(phase) if clip_id == "knockup_air" else 0.0
        # Distinct from voluntary jump: pelvis tilted back (-36 deg), limbs helplessly splayed
        helper.set_bone("pelvis", rx_deg=-36.0 * w + 8.0 * flail, dz=0.22 * w + 0.03 * flail)
        helper.set_bone("spine_02", rx_deg=-18.0 * w)
        helper.set_bone("head", rx_deg=-22.0 * w + 10.0 * flail)
        helper.set_bone("upperarm_l", ry_deg=-12.0 * w + 14.0 * flail, rz_deg=24.0 * w)
        helper.set_bone("lowerarm_l", ry_deg=-8.0, rz_deg=-28.0)
        helper.set_bone("upperarm_r", ry_deg=12.0 * w - 14.0 * flail, rz_deg=-24.0 * w)
        helper.set_bone("lowerarm_r", ry_deg=8.0, rz_deg=28.0)
        helper.set_bone("thigh_l", rx_deg=-12.0 * w + 16.0 * flail, ry_deg=18.0 * w)
        helper.set_bone("calf_l", rx_deg=54.0 * w)
        helper.set_bone("thigh_r", rx_deg=-12.0 * w - 16.0 * flail, ry_deg=-18.0 * w)
        helper.set_bone("calf_r", rx_deg=54.0 * w)
        shape_weights["expr_surprise"] = 0.85 * w

    elif clip_id in ("knockdown_front", "prone_front", "getup_front"):
        if clip_id == "knockdown_front":
            apply_death_front_pose(helper, u)
        elif clip_id == "prone_front":
            apply_death_front_pose(helper, 1.0)
            b = math.sin(phase)
            helper.set_bone("spine_02", rx_deg=2.0 + 3.0 * b)
            helper.set_bone("head", rx_deg=-24.0 + 4.0 * b, rz_deg=18.0)
        else:  # getup_front: push up with hands -> right knee support -> stand ready
            push = pulse_bell(u, 0.35, 0.30)
            apply_death_front_pose(helper, 1.0 - smoothstep(u))
            if push > 0.05:
                helper.set_bone("thigh_r", rx_deg=-55.0 * push)
                helper.set_bone("calf_r", rx_deg=92.0 * push)

    elif clip_id in ("knockdown_back", "prone_back", "getup_back"):
        if clip_id == "knockdown_back":
            apply_death_back_pose(helper, u)
        elif clip_id == "prone_back":
            apply_death_back_pose(helper, 1.0)
            b = math.sin(phase)
            helper.set_bone("spine_02", rx_deg=-2.0 + 3.0 * b)
            helper.set_bone("head", rx_deg=22.0 + 3.0 * b, rz_deg=-14.0)
        else:  # getup_back: sit up -> plant hand -> push onto feet
            apply_death_back_pose(helper, 1.0 - smoothstep(u))

    elif clip_id in ("sleep_start", "sleep_loop", "sleep_end"):
        w = smoothstep(u) if clip_id == "sleep_start" else ((1.0 - smoothstep(u)) if clip_id == "sleep_end" else 1.0)
        b = math.sin(phase) if clip_id == "sleep_loop" else 0.0
        # Resting kneeling/seated slumber posture with closed eyelids and steady breathing
        helper.set_bone("pelvis", rx_deg=24.0 * w + 2.0 * b, dz=-0.38 * w)
        helper.set_bone("spine_01", rx_deg=14.0 * w + 2.5 * b)
        helper.set_bone("spine_02", rx_deg=16.0 * w + 2.5 * b)
        helper.set_bone("head", rx_deg=28.0 * w + 3.0 * b, ry_deg=10.0 * w)
        helper.set_bone("thigh_l", rx_deg=-68.0 * w, ry_deg=10.0 * w)
        helper.set_bone("calf_l", rx_deg=118.0 * w)
        helper.set_bone("thigh_r", rx_deg=-64.0 * w, ry_deg=-10.0 * w)
        helper.set_bone("calf_r", rx_deg=115.0 * w)
        helper.set_bone("upperarm_l", ry_deg=52.0, rz_deg=-38.0 * w)
        helper.set_bone("lowerarm_l", ry_deg=24.0, rz_deg=-76.0 * w)
        helper.set_bone("upperarm_r", ry_deg=-52.0, rz_deg=38.0 * w)
        helper.set_bone("lowerarm_r", ry_deg=-24.0, rz_deg=76.0 * w)
        shape_weights["blink_l"] = w
        shape_weights["blink_r"] = w

    # --- 12. DEATH, DEAD POSES, RESPAWN ---
    elif clip_id == "death_front":
        apply_death_front_pose(helper, u)
        shape_weights["blink_l"] = smoothstep(u)
        shape_weights["blink_r"] = smoothstep(u)
        shape_weights["expr_pain"] = 1.0 - smoothstep(u)

    elif clip_id == "dead_front":
        apply_death_front_pose(helper, 1.0)
        shape_weights["blink_l"] = 1.0
        shape_weights["blink_r"] = 1.0

    elif clip_id == "death_back":
        apply_death_back_pose(helper, u)
        shape_weights["blink_l"] = smoothstep(u)
        shape_weights["blink_r"] = smoothstep(u)
        shape_weights["expr_pain"] = 1.0 - smoothstep(u)

    elif clip_id == "dead_back":
        apply_death_back_pose(helper, 1.0)
        shape_weights["blink_l"] = 1.0
        shape_weights["blink_r"] = 1.0

    elif clip_id == "respawn":
        # Reconstruct from levitating energy crouch -> inspect cyber-arm -> lock into ready stance
        hover = pulse_bell(u, 0.25, 0.25)
        check_arm = pulse_bell(u, 0.62, 0.22)
        settle = smoothstep(max(0.0, (u - 0.55) / 0.45))
        helper.set_bone("pelvis", rx_deg=-12.0 * hover + 6.0 * settle, dz=0.18 * hover - 0.03 * settle)
        helper.set_bone("spine_02", rx_deg=-10.0 * hover + 6.0 * check_arm)
        helper.set_bone("head", rx_deg=-16.0 * hover + 16.0 * check_arm, rz_deg=-14.0 * check_arm)
        helper.set_bone("upperarm_r", ry_deg=-25.0 * hover - 38.0 * settle, rz_deg=72.0 * check_arm + 28.0 * settle)
        helper.set_bone("lowerarm_r", ry_deg=-15.0, rz_deg=96.0 * check_arm + 68.0 * settle)
        helper.set_bone("upperarm_l", ry_deg=25.0 * hover + 42.0 * settle, rz_deg=-25.0 * settle)
        helper.set_bone("lowerarm_l", ry_deg=18.0, rz_deg=-65.0 * settle)
        helper.set_bone("thigh_l", rx_deg=-32.0 * hover - 16.0 * settle)
        helper.set_bone("calf_l", rx_deg=58.0 * hover + 30.0 * settle)
        helper.set_bone("thigh_r", rx_deg=-24.0 * hover - 12.0 * settle)
        helper.set_bone("calf_r", rx_deg=48.0 * hover + 26.0 * settle)
        shape_weights["expr_focus"] = settle * 0.75

    # --- 13. SOCIAL & SPOKEN PERFORMANCE (greet, victory, defeat, dialogue) ---
    elif clip_id == "greet":
        salute = pulse_bell(u, 0.35, 0.25)
        wave = pulse_bell(u, 0.62, 0.22) * math.sin(u * 6.0 * math.pi)
        helper.apply_base_standing_arms(combat_ready=False)
        helper.set_bone("spine_02", rz_deg=-8.0 * salute)
        helper.set_bone("head", rx_deg=8.0 * salute, ry_deg=6.0 * salute)
        helper.set_bone("upperarm_l", ry_deg=62.0 * (1.0 - salute) - 12.0 * salute, rz_deg=-52.0 * salute + 14.0 * wave)
        helper.set_bone("lowerarm_l", ry_deg=48.0 * (1.0 - salute) - 18.0 * salute, rz_deg=-22.0 - 88.0 * salute + 18.0 * wave)
        helper.set_fingers_curl("l", 10.0 * (1.0 - salute))
        shape_weights["expr_joy_confidence"] = 0.80 * salute

    elif clip_id == "victory":
        slash = pulse_bell(u, 0.28, 0.20)
        pump = pulse_bell(u, 0.68, 0.26)
        helper.set_bone("blade_extend_r", dx=-0.26 * (slash + pump))
        helper.set_bone("pelvis", rx_deg=-8.0 * pump, rz_deg=24.0 * slash - 18.0 * pump, dz=-0.04 * slash + 0.02 * pump)
        helper.set_bone("spine_03", rx_deg=-10.0 * pump, rz_deg=20.0 * slash - 14.0 * pump)
        helper.set_bone("head", rx_deg=-12.0 * pump, rz_deg=-10.0 * pump)
        helper.set_bone("upperarm_r", ry_deg=-45.0 * (1.0 - pump) + 38.0 * pump, rz_deg=85.0 * slash + 22.0 * pump)
        helper.set_bone("lowerarm_r", ry_deg=-20.0 * (1.0 - pump) + 25.0 * pump, rz_deg=45.0 * slash + 78.0 * pump)
        helper.set_fingers_curl("r", 90.0 * (slash + pump))
        helper.set_bone("upperarm_l", ry_deg=48.0, rz_deg=-20.0)
        helper.set_bone("lowerarm_l", ry_deg=25.0, rz_deg=-55.0)
        shape_weights["expr_joy_confidence"] = max(slash, pump) * 0.95

    elif clip_id == "defeat":
        drop = smoothstep(min(1.0, u * 1.8)) * (1.0 - smoothstep(max(0.0, (u - 0.82) / 0.18)))
        sigh = math.sin(u * 4.0 * math.pi) * drop
        helper.set_bone("pelvis", rx_deg=26.0 * drop, dz=-0.34 * drop)
        helper.set_bone("spine_02", rx_deg=18.0 * drop + 3.0 * sigh)
        helper.set_bone("head", rx_deg=28.0 * drop + 4.0 * sigh, rz_deg=12.0 * math.sin(u * 2.0 * math.pi) * drop)
        helper.set_bone("thigh_l", rx_deg=-72.0 * drop)
        helper.set_bone("calf_l", rx_deg=98.0 * drop)
        helper.set_bone("thigh_r", rx_deg=-24.0 * drop)
        helper.set_bone("calf_r", rx_deg=92.0 * drop)
        helper.set_bone("upperarm_l", ry_deg=54.0, rz_deg=-35.0 * drop)
        helper.set_bone("lowerarm_l", ry_deg=25.0, rz_deg=-65.0 * drop)
        helper.set_bone("upperarm_r", ry_deg=-54.0, rz_deg=25.0 * drop)
        helper.set_bone("lowerarm_r", ry_deg=-35.0, rz_deg=45.0 * drop)
        shape_weights["expr_concern_sadness"] = 0.90 * drop

    elif clip_id == "dialogue":
        # 14.50s (435 frames) spoken performance synchronized to dialogue_alignment.json
        f_idx = min(len(dialogue_frames) - 1, max(0, int(round(t_sec * FPS))))
        f_data = dialogue_frames[f_idx]

        # Copy visemes, jaw, tongue, blinks, and emotions to shape_weights
        for v_k, v_val in f_data["visemes"].items():
            if v_val > 0.001:
                shape_weights[v_k] = v_val
        shape_weights["jaw_open"] = f_data["jaw_open"]
        shape_weights["tongue_up"] = f_data["tongue_up"]
        shape_weights["tongue_out"] = f_data["tongue_out"]
        shape_weights["blink_l"] = f_data["blink_l"]
        shape_weights["blink_r"] = f_data["blink_r"]

        em = f_data["emotions"]
        shape_weights["expr_focus"] = em.get("focus", 0.0)
        shape_weights["expr_surprise"] = em.get("surprise", 0.0)
        shape_weights["expr_concern_sadness"] = em.get("concern_sadness", 0.0)
        shape_weights["expr_joy_confidence"] = em.get("joy_confidence", 0.0)
        shape_weights["expr_anger"] = em.get("anger", 0.0)

        # Also drive facial bones (jaw, tongue, eyes, eyelids, brows, lips) so bone-only and hybrid playback both work!
        jaw_deg = f_data["jaw_open"] * 18.0
        helper.set_bone("jaw", rx_deg=jaw_deg)
        helper.set_bone("tongue_01", rx_deg=-f_data["tongue_up"] * 12.0, dy=-f_data["tongue_out"] * 0.006)
        helper.set_bone("tongue_02", rx_deg=-f_data["tongue_up"] * 18.0, dy=-f_data["tongue_out"] * 0.008)

        gyaw = f_data["gaze_yaw_deg"]
        gpitch = f_data["gaze_pitch_deg"]
        helper.set_bone("eye_l", rx_deg=-gpitch * 0.65, rz_deg=gyaw * 0.65)
        helper.set_bone("eye_r", rx_deg=-gpitch * 0.65, rz_deg=gyaw * 0.65)
        # Eyelids follow eyeballs + blink closure
        lid_follow = -gpitch * 0.30
        helper.set_bone("eyelid_upper_l", rx_deg=lid_follow + 28.0 * f_data["blink_l"])
        helper.set_bone("eyelid_upper_r", rx_deg=lid_follow + 28.0 * f_data["blink_r"])
        helper.set_bone("eyelid_lower_l", rx_deg=lid_follow * 0.5 - 10.0 * f_data["blink_l"])
        helper.set_bone("eyelid_lower_r", rx_deg=lid_follow * 0.5 - 10.0 * f_data["blink_r"])

        brow_lift = (em.get("surprise", 0.0) * 0.007 + em.get("concern_sadness", 0.0) * 0.004 - em.get("focus", 0.0) * 0.003)
        for b_b in ("brow_inner_l", "brow_mid_l", "brow_outer_l", "brow_inner_r", "brow_mid_r", "brow_outer_r"):
            helper.set_bone(b_b, dz=brow_lift)

        smile_w = em.get("joy_confidence", 0.0) - 0.6 * em.get("concern_sadness", 0.0)
        helper.set_bone("lip_corner_l", dx=0.004 * smile_w, dz=0.005 * smile_w)
        helper.set_bone("lip_corner_r", dx=-0.004 * smile_w, dz=0.005 * smile_w)

        # Expressive Body Acting & Intentional Hand Gestures across the 6 segments of the 14.5s speech
        b_slow = math.sin(t_sec * 1.8)
        helper.set_bone("pelvis", rz_deg=gyaw * 0.15 + 3.0 * b_slow, dz=0.006 * b_slow)
        helper.set_bone("spine_02", rx_deg=3.0 * em.get("concern_sadness", 0.0), rz_deg=gyaw * 0.25)
        helper.set_bone("spine_03", rx_deg=4.0 * em.get("concern_sadness", 0.0), rz_deg=gyaw * 0.30)
        helper.set_bone("neck_01", rx_deg=-gpitch * 0.25, rz_deg=gyaw * 0.25)
        helper.set_bone("head", rx_deg=-gpitch * 0.35 + 3.0 * math.sin(t_sec * 3.2), rz_deg=gyaw * 0.35)

        gesture = f_data["gesture"]
        if gesture == "comms_ear_tap_and_scan":
            helper.set_bone("upperarm_l", ry_deg=10.0, rz_deg=-48.0)
            helper.set_bone("lowerarm_l", ry_deg=-22.0, rz_deg=-108.0)
            helper.set_bone("upperarm_r", ry_deg=-54.0, rz_deg=18.0)
            helper.set_bone("lowerarm_r", ry_deg=-32.0, rz_deg=42.0)
        elif gesture == "inspect_wrist_emitter_holo":
            helper.set_bone("upperarm_r", ry_deg=-32.0, rz_deg=62.0)
            helper.set_bone("lowerarm_r", ry_deg=-16.0, rz_deg=95.0)
            helper.set_bone("upperarm_l", ry_deg=46.0, rz_deg=-35.0)
            helper.set_bone("lowerarm_l", ry_deg=22.0, rz_deg=-68.0)
        elif gesture == "alert_recoil_and_point_conduit":
            helper.set_bone("upperarm_l", ry_deg=14.0, rz_deg=-72.0)
            helper.set_bone("lowerarm_l", ry_deg=6.0, rz_deg=-24.0)
            helper.set_bone("upperarm_r", ry_deg=-38.0, rz_deg=45.0)
            helper.set_bone("lowerarm_r", ry_deg=-18.0, rz_deg=76.0)
        elif gesture == "urgent_two_hand_stabilize":
            helper.set_bone("upperarm_l", ry_deg=32.0, rz_deg=-58.0)
            helper.set_bone("lowerarm_l", ry_deg=16.0, rz_deg=-86.0)
            helper.set_bone("upperarm_r", ry_deg=-32.0, rz_deg=58.0)
            helper.set_bone("lowerarm_r", ry_deg=-16.0, rz_deg=86.0)
        elif gesture == "lock_power_cell_and_channel":
            helper.set_bone("upperarm_r", ry_deg=-28.0, rz_deg=68.0)
            helper.set_bone("lowerarm_r", ry_deg=-14.0, rz_deg=102.0)
            helper.set_bone("upperarm_l", ry_deg=30.0, rz_deg=-64.0)
            helper.set_bone("lowerarm_l", ry_deg=15.0, rz_deg=-96.0)
        else:  # confident_fist_clench_and_nod
            helper.set_bone("upperarm_r", ry_deg=-34.0, rz_deg=48.0)
            helper.set_bone("lowerarm_r", ry_deg=-12.0, rz_deg=92.0)
            helper.set_fingers_curl("r", 85.0)
            helper.set_bone("upperarm_l", ry_deg=50.0, rz_deg=-22.0)
            helper.set_bone("lowerarm_l", ry_deg=28.0, rz_deg=-52.0)

        helper.apply_secondary_follow_through(t_sec * 2.5, amp_deg=5.0, sway_x_deg=gyaw * 0.15)

    # --- 14. 9 CALIBRATED AIM GRID POSES ---
    elif clip_id.startswith("aim_"):
        pitch_map = {"down": -35.0, "level": 0.0, "up": 35.0}
        yaw_map = {"left": 60.0, "center": 0.0, "right": -60.0}
        parts = clip_id.split("_")
        apply_aim_pose(helper, yaw_deg=yaw_map[parts[2]], pitch_deg=pitch_map[parts[1]])

    # --- 15. DEFORMATION STRESS-TEST POSES (§6) ---
    elif clip_id == "pose_overhead_reach":
        helper.set_bone("clavicle_l", ry_deg=-18.0)
        helper.set_bone("upperarm_l", ry_deg=-72.0, rz_deg=-15.0)
        helper.set_bone("lowerarm_l", ry_deg=-68.0, rz_deg=-12.0)
        helper.set_bone("clavicle_r", ry_deg=18.0)
        helper.set_bone("upperarm_r", ry_deg=72.0, rz_deg=15.0)
        helper.set_bone("lowerarm_r", ry_deg=68.0, rz_deg=12.0)
        shape_weights["corr_shoulder_up_l"] = 1.0
        shape_weights["corr_shoulder_up_r"] = 1.0

    elif clip_id == "pose_deep_squat":
        helper.set_bone("pelvis", rx_deg=28.0, dz=-0.38)
        helper.set_bone("spine_02", rx_deg=16.0)
        helper.set_bone("thigh_l", rx_deg=-86.0, ry_deg=16.0)
        helper.set_bone("calf_l", rx_deg=118.0)
        helper.set_bone("foot_l", rx_deg=-32.0)
        helper.set_bone("thigh_r", rx_deg=-86.0, ry_deg=-16.0)
        helper.set_bone("calf_r", rx_deg=118.0)
        helper.set_bone("foot_r", rx_deg=-32.0)
        helper.apply_base_standing_arms(combat_ready=True)
        shape_weights["corr_knee_bend_l"] = 1.0
        shape_weights["corr_knee_bend_r"] = 1.0
        shape_weights["corr_hip_bend_l"] = 1.0
        shape_weights["corr_hip_bend_r"] = 1.0

    elif clip_id == "pose_crossed_arm_reach":
        helper.set_bone("upperarm_l", ry_deg=28.0, rz_deg=-78.0)
        helper.set_bone("lowerarm_l", ry_deg=14.0, rz_deg=-96.0)
        helper.set_bone("upperarm_r", ry_deg=-28.0, rz_deg=78.0)
        helper.set_bone("lowerarm_r", ry_deg=-14.0, rz_deg=96.0)

    elif clip_id == "pose_torso_twist":
        helper.set_bone("spine_01", rz_deg=22.0)
        helper.set_bone("spine_02", rz_deg=26.0)
        helper.set_bone("spine_03", rz_deg=28.0)
        helper.set_bone("head", rz_deg=18.0)
        helper.apply_base_standing_arms(combat_ready=True)

    elif clip_id == "pose_kneeling":
        helper.set_bone("pelvis", rx_deg=12.0, dz=-0.36)
        helper.set_bone("thigh_l", rx_deg=-78.0)
        helper.set_bone("calf_l", rx_deg=82.0)
        helper.set_bone("thigh_r", rx_deg=-12.0)
        helper.set_bone("calf_r", rx_deg=96.0)
        helper.apply_base_standing_arms(combat_ready=True)

    elif clip_id == "pose_planted_hand_support":
        helper.set_bone("pelvis", rx_deg=44.0, dz=-0.35)
        helper.set_bone("spine_02", rx_deg=20.0)
        helper.set_bone("thigh_l", rx_deg=-76.0)
        helper.set_bone("calf_l", rx_deg=110.0)
        helper.set_bone("thigh_r", rx_deg=-68.0)
        helper.set_bone("calf_r", rx_deg=102.0)
        helper.set_bone("upperarm_l", rx_deg=54.0, ry_deg=44.0, rz_deg=-48.0)
        helper.set_bone("lowerarm_l", rx_deg=36.0, ry_deg=20.0, rz_deg=-24.0)

    elif clip_id == "pose_closed_grip":
        helper.apply_base_standing_arms(combat_ready=True)
        helper.set_fingers_curl("l", 88.0, 75.0)
        helper.set_fingers_curl("r", 88.0, 75.0)

    helper.apply_twist_bones()
    return shape_weights


CLIP_DURATION_AND_META: Dict[str, Dict[str, Any]] = {
    "idle_relaxed": {"dur": 3.0, "layer": "FullBody", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": []},
    "idle_combat": {"dur": 3.0, "layer": "FullBody", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": []},
    "idle_wounded": {"dur": 3.0, "layer": "FullBody", "speed_cms": 0.0, "entry": "IdleWounded", "exit": "IdleWounded", "markers": []},
    "walk_f": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_fl": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_l": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_bl": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_b": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_br": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_r": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "walk_fr": {"dur": 1.0, "layer": "Locomotion", "speed_cms": 150.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 7), ("foot_r_down", 22)]},
    "run_f": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_fl": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_l": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_bl": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_b": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_br": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_r": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "run_fr": {"dur": 0.8, "layer": "Locomotion", "speed_cms": 400.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("foot_l_down", 6), ("foot_r_down", 18)]},
    "sprint_f": {"dur": 0.6, "layer": "Locomotion", "speed_cms": 650.0, "entry": "Sprint", "exit": "Sprint", "markers": [("foot_l_down", 4), ("foot_r_down", 13)]},
    "start_f": {"dur": 0.5, "layer": "Locomotion", "speed_cms": 200.0, "entry": "Idle", "exit": "Locomotion", "markers": [("foot_l_down", 8), ("foot_r_down", 14)]},
    "stop_f": {"dur": 0.5, "layer": "Locomotion", "speed_cms": 100.0, "entry": "Locomotion", "exit": "Idle", "markers": [("foot_l_down", 5), ("foot_r_down", 11)]},
    "turn_l90": {"dur": 0.6, "layer": "Locomotion", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("foot_l_down", 8), ("foot_r_down", 15)]},
    "turn_r90": {"dur": 0.6, "layer": "Locomotion", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("foot_r_down", 8), ("foot_l_down", 15)]},
    "pivot_l180": {"dur": 0.6, "layer": "Locomotion", "speed_cms": 250.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("pivot_plant", 8), ("foot_r_down", 16)]},
    "pivot_r180": {"dur": 0.6, "layer": "Locomotion", "speed_cms": 250.0, "entry": "Locomotion", "exit": "Locomotion", "markers": [("pivot_plant", 8), ("foot_l_down", 16)]},
    "jump_start": {"dur": 0.4, "layer": "Airborne", "speed_cms": 0.0, "entry": "Locomotion", "exit": "JumpAir", "markers": [("jump_takeoff", 6)]},
    "jump_air": {"dur": 0.6, "layer": "Airborne", "speed_cms": 0.0, "entry": "JumpAir", "exit": "JumpAir", "markers": []},
    "jump_land": {"dur": 0.5, "layer": "Airborne", "speed_cms": 0.0, "entry": "JumpAir", "exit": "Idle", "markers": [("land_contact", 2), ("recovery", 11)]},
    "fall": {"dur": 0.8, "layer": "Airborne", "speed_cms": 0.0, "entry": "Fall", "exit": "Fall", "markers": []},
    "land_heavy": {"dur": 0.8, "layer": "Airborne", "speed_cms": 0.0, "entry": "Fall", "exit": "Idle", "markers": [("land_contact", 2), ("hand_plant", 8), ("recovery", 19)]},
    "dash_f": {"dur": 0.45, "layer": "FullBodyRootMotion", "speed_cms": 444.4, "entry": "Any", "exit": "Locomotion", "markers": [("dash_burst", 2), ("dash_end", 12)]},
    "dash_b": {"dur": 0.45, "layer": "FullBodyRootMotion", "speed_cms": 444.4, "entry": "Any", "exit": "Locomotion", "markers": [("dash_burst", 2), ("dash_end", 12)]},
    "dash_l": {"dur": 0.45, "layer": "FullBodyRootMotion", "speed_cms": 444.4, "entry": "Any", "exit": "Locomotion", "markers": [("dash_burst", 2), ("dash_end", 12)]},
    "dash_r": {"dur": 0.45, "layer": "FullBodyRootMotion", "speed_cms": 444.4, "entry": "Any", "exit": "Locomotion", "markers": [("dash_burst", 2), ("dash_end", 12)]},
    "blink_out": {"dur": 0.35, "layer": "FullBody", "speed_cms": 0.0, "entry": "Any", "exit": "BlinkTeleport", "markers": [("blink_teleport", 9)]},
    "blink_in": {"dur": 0.35, "layer": "FullBody", "speed_cms": 0.0, "entry": "BlinkTeleport", "exit": "Idle", "markers": [("blink_arrive", 1), ("foot_plant", 7)]},
    "melee_1": {"dur": 0.7, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "MeleeCombo1", "markers": [("hit_window_start", 6), ("hit_window_end", 12), ("recovery", 16)]},
    "melee_2": {"dur": 0.75, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "MeleeCombo1", "exit": "MeleeCombo2", "markers": [("hit_window_start", 6), ("hit_window_end", 13), ("recovery", 17)]},
    "melee_3": {"dur": 0.9, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "MeleeCombo2", "exit": "Ready", "markers": [("hit_window_start", 9), ("hit_window_end", 17), ("recovery", 22)]},
    "ranged_fire": {"dur": 0.35, "layer": "UpperBody", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("muzzle_fire", 3), ("recovery", 8)]},
    "ranged_burst": {"dur": 0.6, "layer": "UpperBody", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("muzzle_fire_1", 4), ("muzzle_fire_2", 8), ("muzzle_fire_3", 12), ("recovery", 16)]},
    "reload": {"dur": 1.8, "layer": "UpperBody", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("cell_grab", 12), ("cell_extract", 21), ("cell_insert", 37), ("reload_complete", 48)]},
    "cast_directional": {"dur": 0.7, "layer": "UpperBody", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("cast_release", 9), ("recovery", 16)]},
    "cast_ground": {"dur": 0.9, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("cast_release", 14), ("recovery", 22)]},
    "cast_self": {"dur": 0.8, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("cast_release", 15), ("recovery", 20)]},
    "channel_start": {"dur": 0.45, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "ChannelLoop", "markers": [("channel_begin", 11)]},
    "channel_loop": {"dur": 1.0, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChannelLoop", "exit": "ChannelLoop", "markers": [("channel_pulse", 15)]},
    "channel_end": {"dur": 0.45, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChannelLoop", "exit": "Ready", "markers": [("channel_complete", 6)]},
    "channel_interrupt": {"dur": 0.4, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChannelLoop", "exit": "Ready", "markers": [("channel_broken", 3)]},
    "charge_start": {"dur": 0.55, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "ChargeHold", "markers": [("charge_accumulate", 10)]},
    "charge_hold": {"dur": 0.9, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChargeHold", "exit": "ChargeHold", "markers": [("charge_ready", 13)]},
    "charge_release": {"dur": 0.6, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChargeHold", "exit": "Ready", "markers": [("charge_fire", 7), ("recovery", 14)]},
    "charge_cancel": {"dur": 0.45, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "ChargeHold", "exit": "Ready", "markers": [("charge_dissipate", 5)]},
    "deploy": {"dur": 1.1, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "Ready", "markers": [("beacon_grab", 7), ("beacon_release", 19), ("recovery", 28)]},
    "uplink_start": {"dur": 0.6, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "Ready", "exit": "UplinkLoop", "markers": [("uplink_open", 12)]},
    "uplink_loop": {"dur": 1.2, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "UplinkLoop", "exit": "UplinkLoop", "markers": [("uplink_sync", 18)]},
    "uplink_end": {"dur": 0.5, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "UplinkLoop", "exit": "Ready", "markers": [("uplink_complete", 8)]},
    "uplink_cancel": {"dur": 0.45, "layer": "FullBodyAction", "speed_cms": 0.0, "entry": "UplinkLoop", "exit": "Ready", "markers": [("uplink_abort", 4)]},
    "hit_f": {"dur": 0.35, "layer": "AdditiveHit", "speed_cms": 0.0, "entry": "Any", "exit": "Any", "markers": [("hit_peak", 4)]},
    "hit_b": {"dur": 0.35, "layer": "AdditiveHit", "speed_cms": 0.0, "entry": "Any", "exit": "Any", "markers": [("hit_peak", 4)]},
    "hit_l": {"dur": 0.35, "layer": "AdditiveHit", "speed_cms": 0.0, "entry": "Any", "exit": "Any", "markers": [("hit_peak", 4)]},
    "hit_r": {"dur": 0.35, "layer": "AdditiveHit", "speed_cms": 0.0, "entry": "Any", "exit": "Any", "markers": [("hit_peak", 4)]},
    "stun_start": {"dur": 0.5, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "StunLoop", "markers": [("stun_enter", 4)]},
    "stun_loop": {"dur": 1.2, "layer": "Disable", "speed_cms": 0.0, "entry": "StunLoop", "exit": "StunLoop", "markers": []},
    "stun_end": {"dur": 0.55, "layer": "Disable", "speed_cms": 0.0, "entry": "StunLoop", "exit": "Ready", "markers": [("stun_recover", 12)]},
    "knockback": {"dur": 0.7, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "Ready", "markers": [("knockback_slide", 4), ("foot_plant", 16)]},
    "knockup_start": {"dur": 0.5, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "KnockupAir", "markers": [("launch_air", 3)]},
    "knockup_air": {"dur": 0.9, "layer": "Disable", "speed_cms": 0.0, "entry": "KnockupAir", "exit": "KnockupAir", "markers": []},
    "knockdown_front": {"dur": 0.85, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "ProneFront", "markers": [("knee_impact", 10), ("body_impact", 20)]},
    "knockdown_back": {"dur": 0.85, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "ProneBack", "markers": [("hip_impact", 11), ("back_impact", 21)]},
    "prone_front": {"dur": 1.2, "layer": "Disable", "speed_cms": 0.0, "entry": "ProneFront", "exit": "ProneFront", "markers": []},
    "prone_back": {"dur": 1.2, "layer": "Disable", "speed_cms": 0.0, "entry": "ProneBack", "exit": "ProneBack", "markers": []},
    "getup_front": {"dur": 1.1, "layer": "Disable", "speed_cms": 0.0, "entry": "ProneFront", "exit": "Ready", "markers": [("hand_push", 8), ("foot_plant", 20), ("recovery", 30)]},
    "getup_back": {"dur": 1.1, "layer": "Disable", "speed_cms": 0.0, "entry": "ProneBack", "exit": "Ready", "markers": [("hand_push", 9), ("foot_plant", 21), ("recovery", 30)]},
    "sleep_start": {"dur": 0.9, "layer": "Disable", "speed_cms": 0.0, "entry": "Any", "exit": "SleepLoop", "markers": [("knee_rest", 16)]},
    "sleep_loop": {"dur": 1.5, "layer": "Disable", "speed_cms": 0.0, "entry": "SleepLoop", "exit": "SleepLoop", "markers": []},
    "sleep_end": {"dur": 0.9, "layer": "Disable", "speed_cms": 0.0, "entry": "SleepLoop", "exit": "Ready", "markers": [("wake_stand", 18)]},
    "death_front": {"dur": 1.5, "layer": "Terminal", "speed_cms": 0.0, "entry": "Any", "exit": "DeadFront", "markers": [("fatal_hit", 2), ("knee_drop", 18), ("body_collapse", 36)]},
    "death_back": {"dur": 1.5, "layer": "Terminal", "speed_cms": 0.0, "entry": "Any", "exit": "DeadBack", "markers": [("fatal_hit", 2), ("back_collapse", 35)]},
    "dead_front": {"dur": 0.0, "layer": "Terminal", "speed_cms": 0.0, "entry": "DeadFront", "exit": "DeadFront", "markers": []},
    "dead_back": {"dur": 0.0, "layer": "Terminal", "speed_cms": 0.0, "entry": "DeadBack", "exit": "DeadBack", "markers": []},
    "respawn": {"dur": 1.6, "layer": "Terminal", "speed_cms": 0.0, "entry": "Dead", "exit": "Ready", "markers": [("reconstruct_start", 2), ("feet_touchdown", 24), ("ready_lock", 42)]},
    "greet": {"dur": 1.4, "layer": "Social", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("salute_tap", 14)]},
    "victory": {"dur": 1.8, "layer": "Social", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("blade_flourish", 15), ("fist_pump", 36)]},
    "defeat": {"dur": 1.8, "layer": "Social", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("knee_drop", 18)]},
    "dialogue": {"dur": 14.5, "layer": "FullBodyPerformance", "speed_cms": 0.0, "entry": "Idle", "exit": "Idle", "markers": [("speech_start", 10), ("emotional_shift_spike", 160), ("emitter_reroute", 313), ("network_stabilized", 384)]},
    "aim_down_left": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_down_center": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_down_right": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_level_left": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_level_center": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_level_right": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_up_left": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_up_center": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
    "aim_up_right": {"dur": 0.0, "layer": "AimOffset", "speed_cms": 0.0, "entry": "AimGrid", "exit": "AimGrid", "markers": []},
}


def build_all_animations(
    arm_obj: bpy.types.Object,
    lod0_obj: bpy.types.Object,
    csv_path: Path,
    dialogue_align_path: Path,
    manifest_out_path: Path,
) -> List[Dict[str, Any]]:
    """
    Build all 96 required actions + 7 deformation stress-test actions in Blender 5.1,
    and write docs/animation_manifest.json.
    """
    bpy.context.scene.render.fps = FPS
    dialogue_data = json.loads(dialogue_align_path.read_text(encoding="utf-8"))
    dialogue_frames = dialogue_data["frames_30fps"]

    rows = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    assert len(rows) == 96, f"Expected 96 rows in required_animations.csv, got {len(rows)}"

    helper = RigPoseHelper(arm_obj)
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()

    # Only keyframe bones that actually move or deform to keep action creation fast & clean
    deform_bone_names = [pb.name for pb in arm_obj.pose.bones if pb.bone.use_deform]

    manifest_entries = []

    for idx, row in enumerate(rows):
        clip_id = row["id"].strip()
        form = row["form"].strip()
        root_mov = row["root_movement"].strip()
        req_beh = row["required_behavior"].strip()
        meta = CLIP_DURATION_AND_META[clip_id]

        dur_sec = meta["dur"]
        is_pose = form == "pose"
        n_frames = 1 if is_pose else int(round(dur_sec * FPS))

        act = bpy.data.actions.new(name=clip_id)
        act.use_fake_user = True
        arm_obj.animation_data.action = act
        # In Blender 5.0/5.1 Layered Actions, assign the slot if present
        if hasattr(arm_obj.animation_data, "action_slot") and act.slots:
            arm_obj.animation_data.action_slot = act.slots[0]

        # Sample frames; for longer clips (>2.0s) other than dialogue, sample every 2 frames; for dialogue every 2 frames (6.6ms resolution)
        step = 1
        if clip_id == "dialogue":
            step = 2
        elif n_frames >= 60:
            step = 2

        sample_frames = list(range(0, n_frames + 1, step))
        if sample_frames[-1] != n_frames:
            sample_frames.append(n_frames)
        if is_pose:
            sample_frames = [0, 1]

        for f_num in sample_frames:
            u = 0.0 if is_pose else (f_num / float(max(1, n_frames)))
            t_sec = f_num / float(FPS)
            evaluate_clip_pose(clip_id, helper, u, t_sec, dialogue_frames)

            for bname in deform_bone_names:
                pb = arm_obj.pose.bones[bname]
                if bname in ("root", "pelvis", "prop_cell", "prop_beacon", "blade_extend_r") or bname.startswith("brow_") or bname.startswith("lip_") or bname.startswith("tongue_"):
                    pb.keyframe_insert(data_path="location", frame=f_num)
                pb.keyframe_insert(data_path="rotation_euler", frame=f_num)

        # Add Pose Markers to Action
        marker_records = []
        for m_name, m_frame in meta["markers"]:
            pm = act.pose_markers.new(name=m_name)
            pm.frame = m_frame
            marker_records.append({
                "name": m_name,
                "frame": m_frame,
                "time_sec": round(m_frame / float(FPS), 4),
            })

        manifest_entries.append({
            "id": clip_id,
            "index": idx + 1,
            "form": form,
            "source_action": clip_id,
            "exported_fbx": f"export/animations/{clip_id}.fbx",
            "unreal_asset_path": f"/Game/MorphRig/Animations/{clip_id}.{clip_id}",
            "frame_range": [0, 1 if is_pose else n_frames],
            "frame_count": 1 if is_pose else (n_frames + 1),
            "sample_rate_fps": FPS,
            "duration_seconds": 0.0 if is_pose else round(dur_sec, 4),
            "loop": (form == "loop"),
            "is_additive": (form == "additive"),
            "is_static_pose": is_pose,
            "root_motion_policy": root_mov,
            "nominal_travel_speed_cms": meta["speed_cms"],
            "intended_layer": meta["layer"],
            "entry_state": meta["entry"],
            "exit_state": meta["exit"],
            "event_markers": marker_records,
            "required_behavior": req_beh,
        })

    # Also build the 7 Deformation Demonstration Poses (§6) inside Operative.blend
    demo_poses = [
        "pose_overhead_reach",
        "pose_deep_squat",
        "pose_crossed_arm_reach",
        "pose_torso_twist",
        "pose_kneeling",
        "pose_planted_hand_support",
        "pose_closed_grip",
    ]
    for dp_name in demo_poses:
        act = bpy.data.actions.new(name=dp_name)
        act.use_fake_user = True
        arm_obj.animation_data.action = act
        if hasattr(arm_obj.animation_data, "action_slot") and act.slots:
            arm_obj.animation_data.action_slot = act.slots[0]
        evaluate_clip_pose(dp_name, helper, 1.0, 0.0, dialogue_frames)
        for bname in deform_bone_names:
            pb = arm_obj.pose.bones[bname]
            pb.keyframe_insert(data_path="location", frame=0)
            pb.keyframe_insert(data_path="rotation_euler", frame=0)

    # Restore neutral rest pose on the armature so Operative.blend opens in clean ground-origin neutral pose!
    helper.reset_all()
    arm_obj.animation_data.action = bpy.data.actions.get("idle_relaxed")
    helper.reset_all()

    manifest_doc = {
        "project": "MorphRig",
        "character": "Operative (Vex)",
        "sample_rate_fps": FPS,
        "total_required_entries": len(manifest_entries),
        "motion_entries_count": sum(1 for e in manifest_entries if not e["is_static_pose"]),
        "static_pose_entries_count": sum(1 for e in manifest_entries if e["is_static_pose"]),
        "extra_deformation_demo_poses": demo_poses,
        "locomotion_reference_speeds_cms": {
            "walk": 150.0,
            "run": 400.0,
            "sprint_f": 650.0,
            "dash_displacement_cm": 200.0,
        },
        "aim_offset_grid_conventions": {
            "yaw_degrees": [-60.0, 0.0, 60.0],
            "pitch_degrees": [-35.0, 0.0, 35.0],
            "yaw_sign": "-60 is aim_right, 0 is aim_center, +60 is aim_left",
            "pitch_sign": "-35 is aim_down, 0 is aim_level, +35 is aim_up",
        },
        "animations": manifest_entries,
    }
    manifest_out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_out_path.write_text(json.dumps(manifest_doc, indent=2), encoding="utf-8")
    return manifest_entries

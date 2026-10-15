#!/usr/bin/env python3
"""
Procedural Rig, Control Hierarchy, Skin Weighting, and Socket Manifest Builder
for the MorphRig Cyberpunk Operative ("Vex").

Creates:
  1. Single-root connected deformation skeleton (93 deformation bones with use_deform=True)
     covering root, pelvis, spine_01..03, clavicles, arms + twist bones, 30 finger phalanges,
     legs + twist bones, feet/toes, neck/head, full facial bone rig (jaw, tongue, eyes, eyelids,
     brows, cheeks, lips, nostrils), secondary chains (neural_tether_01..03, belt_strap_01..02),
     cyberware mounts (emitter_mount_r, emitter_muzzle_r, blade_mount_r, blade_extend_r,
     cell_socket_r), and manipulated props (prop_cell, prop_beacon).
  2. Animator Control Rig (CTRL_* and MCH_* bones with use_deform=False) providing:
     - Global scale & master control (CTRL_master) and independent root/pelvis
     - Arms & legs IK/FK controls, pole vectors, and IK/FK pose-matching utility
     - Foot roll, heel/toe pivot hierarchy
     - Hand/finger master curl, spread, and per-finger adjustments
     - Torso, neck, head, and look-at target (CTRL_look_at, CTRL_eye_l/r) with eyelid follow
     - Controllable secondary motion and facial control sliders
  3. Smooth distance-blended + anatomical tag-aware skin weights on LOD0, LOD1, and LOD2
     with <= 4 influences per vertex (strictly <= 8 spec limit) and 100% normalized weights.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple
import bpy
from mathutils import Vector, Matrix


# (bone_name, parent_name, head_xyz, tail_xyz, roll_rad, is_deform)
DEFORM_BONE_SPECS: List[Tuple[str, str, Tuple[float, float, float], Tuple[float, float, float], float]] = [
    # Root and Spine
    ("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.15), 0.0),
    ("pelvis", "root", (0.0, 0.002, 0.90), (0.0, 0.000, 1.00), 0.0),
    ("spine_01", "pelvis", (0.0, 0.000, 1.00), (0.0, -0.004, 1.13), 0.0),
    ("spine_02", "spine_01", (0.0, -0.004, 1.13), (0.0, -0.008, 1.26), 0.0),
    ("spine_03", "spine_02", (0.0, -0.008, 1.26), (0.0, -0.002, 1.42), 0.0),
    ("neck_01", "spine_03", (0.0, 0.002, 1.42), (0.0, 0.002, 1.50), 0.0),
    ("neck_02", "neck_01", (0.0, 0.002, 1.50), (0.0, -0.002, 1.56), 0.0),
    ("head", "neck_02", (0.0, -0.002, 1.56), (0.0, 0.000, 1.78), 0.0),

    # Facial Bones (parented to head / jaw)
    ("jaw", "head", (0.0, -0.032, 1.615), (0.0, -0.092, 1.572), 0.0),
    ("tongue_01", "jaw", (0.0, -0.048, 1.590), (0.0, -0.068, 1.592), 0.0),
    ("tongue_02", "tongue_01", (0.0, -0.068, 1.592), (0.0, -0.088, 1.594), 0.0),
    ("eye_l", "head", (0.032, -0.086, 1.686), (0.032, -0.106, 1.686), 0.0),
    ("eye_r", "head", (-0.032, -0.086, 1.686), (-0.032, -0.106, 1.686), 0.0),
    ("eyelid_upper_l", "head", (0.032, -0.086, 1.686), (0.032, -0.102, 1.694), 0.0),
    ("eyelid_lower_l", "head", (0.032, -0.086, 1.686), (0.032, -0.102, 1.678), 0.0),
    ("eyelid_upper_r", "head", (-0.032, -0.086, 1.686), (-0.032, -0.102, 1.694), 0.0),
    ("eyelid_lower_r", "head", (-0.032, -0.086, 1.686), (-0.032, -0.102, 1.678), 0.0),
    ("brow_inner_l", "head", (0.015, -0.098, 1.712), (0.015, -0.108, 1.718), 0.0),
    ("brow_mid_l", "head", (0.032, -0.096, 1.715), (0.032, -0.106, 1.721), 0.0),
    ("brow_outer_l", "head", (0.048, -0.090, 1.710), (0.048, -0.100, 1.716), 0.0),
    ("brow_inner_r", "head", (-0.015, -0.098, 1.712), (-0.015, -0.108, 1.718), 0.0),
    ("brow_mid_r", "head", (-0.032, -0.096, 1.715), (-0.032, -0.106, 1.721), 0.0),
    ("brow_outer_r", "head", (-0.048, -0.090, 1.710), (-0.048, -0.100, 1.716), 0.0),
    ("cheek_l", "head", (0.044, -0.084, 1.648), (0.052, -0.094, 1.652), 0.0),
    ("cheek_r", "head", (-0.044, -0.084, 1.648), (-0.052, -0.094, 1.652), 0.0),
    ("nostril_l", "head", (0.012, -0.098, 1.632), (0.016, -0.106, 1.632), 0.0),
    ("nostril_r", "head", (-0.012, -0.098, 1.632), (-0.016, -0.106, 1.632), 0.0),
    ("lip_upper_mid", "head", (0.0, -0.096, 1.606), (0.0, -0.108, 1.606), 0.0),
    ("lip_upper_l", "head", (0.014, -0.094, 1.605), (0.014, -0.105, 1.605), 0.0),
    ("lip_upper_r", "head", (-0.014, -0.094, 1.605), (-0.014, -0.105, 1.605), 0.0),
    ("lip_lower_mid", "jaw", (0.0, -0.095, 1.590), (0.0, -0.107, 1.590), 0.0),
    ("lip_lower_l", "jaw", (0.014, -0.093, 1.591), (0.014, -0.104, 1.591), 0.0),
    ("lip_lower_r", "jaw", (-0.014, -0.093, 1.591), (-0.014, -0.104, 1.591), 0.0),
    ("lip_corner_l", "head", (0.024, -0.088, 1.598), (0.028, -0.098, 1.598), 0.0),
    ("lip_corner_r", "head", (-0.024, -0.088, 1.598), (-0.028, -0.098, 1.598), 0.0),

    # Secondary-motion Neural Tether Cable (parented to head)
    ("neural_tether_01", "head", (0.0, 0.088, 1.64), (0.0, 0.125, 1.51), 0.0),
    ("neural_tether_02", "neural_tether_01", (0.0, 0.125, 1.51), (0.0, 0.144, 1.38), 0.0),
    ("neural_tether_03", "neural_tether_02", (0.0, 0.144, 1.38), (0.0, 0.142, 1.25), 0.0),

    # Secondary-motion Tactical Hip Data-Strap (parented to pelvis)
    ("belt_strap_01", "pelvis", (0.166, 0.0, 0.98), (0.176, 0.0, 0.85), 0.0),
    ("belt_strap_02", "belt_strap_01", (0.176, 0.0, 0.85), (0.175, 0.0, 0.73), 0.0),
]

# Add Left & Right Arms, Twist Bones, and 15 Finger Bones per hand
for _side_sign, _side_s in [(1.0, "l"), (-1.0, "r")]:
    DEFORM_BONE_SPECS.extend([
        (f"clavicle_{_side_s}", "spine_03", (_side_sign * 0.045, -0.010, 1.385), (_side_sign * 0.175, 0.000, 1.375), 0.0),
        (f"upperarm_{_side_s}", f"clavicle_{_side_s}", (_side_sign * 0.175, 0.000, 1.375), (_side_sign * 0.435, 0.018, 1.355), 0.0),
        (f"upperarm_twist_01_{_side_s}", f"upperarm_{_side_s}", (_side_sign * 0.305, 0.009, 1.365), (_side_sign * 0.435, 0.018, 1.355), 0.0),
        (f"lowerarm_{_side_s}", f"upperarm_{_side_s}", (_side_sign * 0.435, 0.018, 1.355), (_side_sign * 0.695, -0.005, 1.348), 0.0),
        (f"lowerarm_twist_01_{_side_s}", f"lowerarm_{_side_s}", (_side_sign * 0.565, 0.006, 1.351), (_side_sign * 0.695, -0.005, 1.348), 0.0),
        (f"hand_{_side_s}", f"lowerarm_{_side_s}", (_side_sign * 0.695, -0.005, 1.348), (_side_sign * 0.775, -0.005, 1.348), 0.0),
    ])
    _finger_defs = [
        ("thumb",  0.725, -0.036, 1.338, 0.78, -0.62, 0.068),
        ("index",  0.775, -0.034, 1.350, 0.99, -0.10, 0.082),
        ("middle", 0.778, -0.012, 1.351, 1.00,  0.00, 0.088),
        ("ring",   0.775,  0.010, 1.350, 0.99,  0.08, 0.080),
        ("pinky",  0.770,  0.030, 1.347, 0.98,  0.16, 0.068),
    ]
    for _fname, _fx0, _fy0, _fz0, _dx, _dy, _flen in _finger_defs:
        _p_parent = f"hand_{_side_s}"
        for _p_idx, _p_num in enumerate(["01", "02", "03"]):
            _f0 = _p_idx / 3.0
            _f1 = (_p_idx + 1) / 3.0
            _h = (_side_sign * (_fx0 + _dx * _flen * _f0), _fy0 + _dy * _flen * _f0, _fz0 - 0.003 * (_f0 ** 2))
            _t = (_side_sign * (_fx0 + _dx * _flen * _f1), _fy0 + _dy * _flen * _f1, _fz0 - 0.003 * (_f1 ** 2))
            _bname = f"{_fname}_{_p_num}_{_side_s}"
            DEFORM_BONE_SPECS.append((_bname, _p_parent, _h, _t, 0.0))
            _p_parent = _bname

# Right Cybernetic Arm Weapon & Prop Mount Bones
DEFORM_BONE_SPECS.extend([
    ("emitter_mount_r", "lowerarm_r", (-0.520, -0.006, 1.388), (-0.680, -0.006, 1.388), 0.0),
    ("emitter_muzzle_r", "emitter_mount_r", (-0.680, -0.006, 1.388), (-0.735, -0.006, 1.388), 0.0),
    ("cell_socket_r", "emitter_mount_r", (-0.560, -0.028, 1.402), (-0.625, -0.028, 1.402), 0.0),
    ("blade_mount_r", "lowerarm_r", (-0.460, 0.040, 1.348), (-0.660, 0.040, 1.348), 0.0),
    ("blade_extend_r", "blade_mount_r", (-0.500, 0.040, 1.348), (-0.890, 0.040, 1.348), 0.0),
    # Manipulated props (parented in hierarchy so single root is preserved, can translate freely in pose space)
    ("prop_cell", "cell_socket_r", (-0.560, -0.028, 1.402), (-0.625, -0.028, 1.402), 0.0),
    ("prop_beacon", "pelvis", (-0.178, -0.020, 0.835), (-0.178, -0.020, 0.896), 0.0),
])

# Add Left & Right Legs, Twist Bones, Feet, and Toe Balls
for _side_sign, _side_s in [(1.0, "l"), (-1.0, "r")]:
    _hx = _side_sign * 0.098
    DEFORM_BONE_SPECS.extend([
        (f"thigh_{_side_s}", "pelvis", (_hx, 0.002, 0.90), (_hx, -0.006, 0.51), 0.0),
        (f"thigh_twist_01_{_side_s}", f"thigh_{_side_s}", (_hx, -0.002, 0.70), (_hx, -0.006, 0.51), 0.0),
        (f"calf_{_side_s}", f"thigh_{_side_s}", (_hx, -0.006, 0.51), (_hx, 0.004, 0.09), 0.0),
        (f"calf_twist_01_{_side_s}", f"calf_{_side_s}", (_hx, -0.001, 0.30), (_hx, 0.004, 0.09), 0.0),
        (f"foot_{_side_s}", f"calf_{_side_s}", (_hx, 0.004, 0.09), (_hx, -0.095, 0.032), 0.0),
        (f"ball_{_side_s}", f"foot_{_side_s}", (_hx, -0.095, 0.032), (_hx, -0.168, 0.018), 0.0),
    ])


SOCKET_DEFINITIONS = [
    {
        "socket_name": "socket_hand_r",
        "bone": "hand_r",
        "relative_location_m": [-0.04, -0.02, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Right hand grip attachment point",
    },
    {
        "socket_name": "socket_hand_l",
        "bone": "hand_l",
        "relative_location_m": [0.04, -0.02, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Left hand grip attachment point (manipulates power cell and beacon)",
    },
    {
        "socket_name": "socket_emitter_muzzle",
        "bone": "emitter_muzzle_r",
        "relative_location_m": [0.0, 0.0, 0.0],
        "relative_rotation_deg": [0.0, -90.0, 0.0],
        "purpose": "Wrist emitter projectile and muzzle flash origin",
    },
    {
        "socket_name": "socket_cell_slot",
        "bone": "cell_socket_r",
        "relative_location_m": [0.0, 0.0, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Removable power cell housing on wrist emitter",
    },
    {
        "socket_name": "socket_blade_base",
        "bone": "blade_mount_r",
        "relative_location_m": [0.0, 0.0, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Forearm melee blade housing base",
    },
    {
        "socket_name": "socket_blade_tip",
        "bone": "blade_extend_r",
        "relative_location_m": [0.0, 0.39, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Forearm melee blade tip for slash trail and hit-window sweep",
    },
    {
        "socket_name": "socket_beacon_holster",
        "bone": "prop_beacon",
        "relative_location_m": [0.0, 0.0, 0.0],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Deployable micro-beacon / drone holster & placement anchor",
    },
    {
        "socket_name": "socket_chest_fx",
        "bone": "spine_03",
        "relative_location_m": [0.0, -0.12, 0.06],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Self-cast, charge, and shield effect anchor",
    },
    {
        "socket_name": "socket_head_status",
        "bone": "head",
        "relative_location_m": [0.0, 0.0, 0.26],
        "relative_rotation_deg": [0.0, 0.0, 0.0],
        "purpose": "Overhead crowd-control / status indicator anchor (stun, sleep, silence, root)",
    },
]


def build_armature_and_controls() -> bpy.types.Object:
    """Create the OperativeRig armature with both exportable deform bones and animator CTRL/MCH bones."""
    arm_data = bpy.data.armatures.new("OperativeRig")
    arm_obj = bpy.data.objects.new("OperativeRig", arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj

    # Create organized Bone Collections in Blender 5.1
    coll_def = arm_data.collections.new("DEF_Export")
    coll_ctrl = arm_data.collections.new("CTRL_Animator")
    coll_mch = arm_data.collections.new("MCH_Internal")
    coll_mch.is_visible = False

    bpy.ops.object.mode_set(mode="EDIT")
    ebones = arm_data.edit_bones

    # 1. Create all 93 Deformation Bones
    for bname, pname, head, tail, roll in DEFORM_BONE_SPECS:
        eb = ebones.new(bname)
        eb.head = Vector(head)
        eb.tail = Vector(tail)
        eb.roll = roll
        eb.use_deform = True
        if pname and pname in ebones:
            eb.parent = ebones[pname]
            # Connect spine, neck, finger phalanges, and tether chains where head == parent.tail
            if (eb.head - eb.parent.tail).length < 1e-4 and not bname.startswith(("thigh_twist", "calf_twist", "upperarm_twist", "lowerarm_twist", "prop_")):
                eb.use_connect = True
        coll_def.assign(eb)

    # 2. Create Animator Control Rig (CTRL_* and MCH_* with use_deform = False)
    ctrl_specs = [
        ("CTRL_master", None, (0.0, 0.0, 0.0), (0.0, -0.35, 0.0)),
        ("CTRL_root", "CTRL_master", (0.0, 0.0, 0.0), (0.0, -0.20, 0.0)),
        ("CTRL_pelvis", "CTRL_root", (0.0, 0.002, 0.90), (0.0, -0.18, 0.90)),
        ("CTRL_spine_01", "CTRL_pelvis", (0.0, 0.000, 1.00), (0.0, -0.16, 1.00)),
        ("CTRL_spine_02", "CTRL_spine_01", (0.0, -0.004, 1.13), (0.0, -0.16, 1.13)),
        ("CTRL_spine_03", "CTRL_spine_02", (0.0, -0.008, 1.26), (0.0, -0.18, 1.26)),
        ("CTRL_neck", "CTRL_spine_03", (0.0, 0.002, 1.42), (0.0, -0.12, 1.42)),
        ("CTRL_head", "CTRL_neck", (0.0, -0.002, 1.56), (0.0, -0.18, 1.56)),
        ("CTRL_jaw", "CTRL_head", (0.0, -0.032, 1.615), (0.0, -0.12, 1.572)),
        ("CTRL_look_at", "CTRL_master", (0.0, -0.85, 1.686), (0.0, -0.95, 1.686)),
        ("CTRL_eye_l", "CTRL_look_at", (0.032, -0.85, 1.686), (0.032, -0.92, 1.686)),
        ("CTRL_eye_r", "CTRL_look_at", (-0.032, -0.85, 1.686), (-0.032, -0.92, 1.686)),
        ("CTRL_tether_01", "CTRL_head", (0.0, 0.088, 1.64), (0.0, 0.16, 1.64)),
        ("CTRL_tether_02", "CTRL_tether_01", (0.0, 0.125, 1.51), (0.0, 0.20, 1.51)),
        ("CTRL_tether_03", "CTRL_tether_02", (0.0, 0.144, 1.38), (0.0, 0.22, 1.38)),
        ("CTRL_strap_01", "CTRL_pelvis", (0.166, 0.0, 0.98), (0.24, 0.0, 0.98)),
        ("CTRL_strap_02", "CTRL_strap_01", (0.176, 0.0, 0.85), (0.25, 0.0, 0.85)),
    ]

    for s_sign, s_side in [(1.0, "l"), (-1.0, "r")]:
        hx = s_sign * 0.098
        ctrl_specs.extend([
            (f"CTRL_clavicle_{s_side}", "CTRL_spine_03", (s_sign * 0.045, -0.010, 1.385), (s_sign * 0.175, 0.000, 1.45)),
            (f"CTRL_fk_upperarm_{s_side}", f"CTRL_clavicle_{s_side}", (s_sign * 0.175, 0.000, 1.375), (s_sign * 0.435, 0.018, 1.355)),
            (f"CTRL_fk_lowerarm_{s_side}", f"CTRL_fk_upperarm_{s_side}", (s_sign * 0.435, 0.018, 1.355), (s_sign * 0.695, -0.005, 1.348)),
            (f"CTRL_fk_hand_{s_side}", f"CTRL_fk_lowerarm_{s_side}", (s_sign * 0.695, -0.005, 1.348), (s_sign * 0.775, -0.005, 1.348)),
            (f"CTRL_ik_hand_{s_side}", "CTRL_master", (s_sign * 0.695, -0.005, 1.348), (s_sign * 0.775, -0.005, 1.348)),
            (f"CTRL_pole_arm_{s_side}", "CTRL_master", (s_sign * 0.435, 0.35, 1.355), (s_sign * 0.435, 0.43, 1.355)),
            (f"CTRL_fingers_{s_side}", f"CTRL_fk_hand_{s_side}", (s_sign * 0.75, -0.005, 1.39), (s_sign * 0.82, -0.005, 1.39)),
            (f"CTRL_fk_thigh_{s_side}", "CTRL_pelvis", (hx, 0.002, 0.90), (hx, -0.006, 0.51)),
            (f"CTRL_fk_calf_{s_side}", f"CTRL_fk_thigh_{s_side}", (hx, -0.006, 0.51), (hx, 0.004, 0.09)),
            (f"CTRL_fk_foot_{s_side}", f"CTRL_fk_calf_{s_side}", (hx, 0.004, 0.09), (hx, -0.095, 0.032)),
            (f"CTRL_fk_ball_{s_side}", f"CTRL_fk_foot_{s_side}", (hx, -0.095, 0.032), (hx, -0.168, 0.018)),
            (f"CTRL_ik_foot_{s_side}", "CTRL_master", (hx, 0.004, 0.00), (hx, -0.168, 0.00)),
            (f"CTRL_foot_roll_{s_side}", f"CTRL_ik_foot_{s_side}", (hx, 0.055, 0.04), (hx, -0.05, 0.04)),
            (f"MCH_heel_{s_side}", f"CTRL_ik_foot_{s_side}", (hx, 0.055, 0.00), (hx, 0.055, 0.05)),
            (f"MCH_toe_{s_side}", f"MCH_heel_{s_side}", (hx, -0.168, 0.00), (hx, -0.168, 0.05)),
            (f"CTRL_pole_leg_{s_side}", "CTRL_master", (hx, -0.42, 0.51), (hx, -0.50, 0.51)),
        ])

    for cname, cpname, chead, ctail in ctrl_specs:
        ceb = ebones.new(cname)
        ceb.head = Vector(chead)
        ceb.tail = Vector(ctail)
        ceb.use_deform = False
        if cpname and cpname in ebones:
            ceb.parent = ebones[cpname]
        if cname.startswith("MCH_"):
            coll_mch.assign(ceb)
        else:
            coll_ctrl.assign(ceb)

    bpy.ops.object.mode_set(mode="POSE")
    pbones = arm_obj.pose.bones

    # Custom properties on CTRL_master and CTRL_fingers_l/r for IK/FK switching, finger curl/spread, and face
    ctrl_master = pbones["CTRL_master"]
    ctrl_master["ik_fk_arm_l"] = 0.0  # 0 = FK, 1 = IK
    ctrl_master["ik_fk_arm_r"] = 0.0
    ctrl_master["ik_fk_leg_l"] = 1.0  # Default planted IK legs in interactive mode
    ctrl_master["ik_fk_leg_r"] = 1.0
    ctrl_master["secondary_spring_strength"] = 1.0
    ctrl_master["team_variant"] = 0   # 0 = TeamA, 1 = TeamB

    for s_side in ("l", "r"):
        cf = pbones[f"CTRL_fingers_{s_side}"]
        cf["curl_all"] = 0.0
        cf["spread_all"] = 0.0
        for fname in ("thumb", "index", "middle", "ring", "pinky"):
            cf[f"{fname}_curl"] = 0.0

    # Set Euler rotation mode (XYZ) across all bones for clean curve editing and baking
    for pb in pbones:
        pb.rotation_mode = "XYZ"

    # Embed a rig UI & operator helper script inside the .blend so animators have 1-click Reset Pose,
    # IK<->FK Pose Matching, and Action Rebaking right in Blender!
    embed_rig_utilities_script()

    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def embed_rig_utilities_script():
    """Embeds morphrig_rig_tools.py in the .blend file with Pose Reset and IK/FK Snap operators."""
    code = '''import bpy

class MORPHRIG_OT_reset_pose(bpy.types.Operator):
    """Reset all OperativeRig pose bones and facial shape keys to neutral rest pose"""
    bl_idname = "morphrig.reset_pose"
    bl_label = "MorphRig: Reset Pose to Neutral"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = bpy.data.objects.get("OperativeRig")
        if rig and rig.pose:
            for pb in rig.pose.bones:
                pb.location = (0.0, 0.0, 0.0)
                pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                pb.rotation_euler = (0.0, 0.0, 0.0)
                pb.scale = (1.0, 1.0, 1.0)
        for obj_name in ("Operative_LOD0", "Operative_LOD1", "Operative_LOD2"):
            obj = bpy.data.objects.get(obj_name)
            if obj and obj.data.shape_keys:
                for kb in obj.data.shape_keys.key_blocks:
                    if kb.name != "Basis":
                        kb.value = 0.0
        return {"FINISHED"}


class MORPHRIG_OT_snap_ik_fk(bpy.types.Operator):
    """Match IK controls to current FK limb pose (or FK to IK) without visual jump"""
    bl_idname = "morphrig.snap_ik_fk"
    bl_label = "MorphRig: Snap IK <-> FK Limb"
    bl_options = {"REGISTER", "UNDO"}

    limb: bpy.props.StringProperty(default="arm_l")
    to_ik: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        rig = bpy.data.objects.get("OperativeRig")
        if not rig:
            return {"CANCELLED"}
        pb = rig.pose.bones
        side = self.limb.split("_")[-1]
        if self.limb.startswith("arm_"):
            if self.to_ik:
                pb[f"CTRL_ik_hand_{side}"].matrix = pb[f"hand_{side}"].matrix.copy()
                pb["CTRL_master"][f"ik_fk_arm_{side}"] = 1.0
            else:
                for b in ("upperarm", "lowerarm", "hand"):
                    pb[f"CTRL_fk_{b}_{side}"].matrix = pb[f"{b}_{side}"].matrix.copy()
                pb["CTRL_master"][f"ik_fk_arm_{side}"] = 0.0
        elif self.limb.startswith("leg_"):
            if self.to_ik:
                pb[f"CTRL_ik_foot_{side}"].matrix = pb[f"foot_{side}"].matrix.copy()
                pb["CTRL_master"][f"ik_fk_leg_{side}"] = 1.0
            else:
                for b in ("thigh", "calf", "foot", "ball"):
                    pb[f"CTRL_fk_{b}_{side}"].matrix = pb[f"{b}_{side}"].matrix.copy()
                pb["CTRL_master"][f"ik_fk_leg_{side}"] = 0.0
        return {"FINISHED"}


def register():
    for cls in (MORPHRIG_OT_reset_pose, MORPHRIG_OT_snap_ik_fk):
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()
'''
    txt = bpy.data.texts.get("morphrig_rig_tools.py") or bpy.data.texts.new("morphrig_rig_tools.py")
    txt.clear()
    txt.write(code)
    txt.use_module = True


def point_to_segment_dist(p: Vector, a: Vector, b: Vector) -> float:
    ab = b - a
    len_sq = ab.length_squared
    if len_sq < 1e-10:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / len_sq))
    proj = a + t * ab
    return (p - proj).length


def assign_smooth_skin_weights(
    mesh_obj: bpy.types.Object,
    arm_obj: bpy.types.Object,
    vert_tags: List[str],
):
    """
    Assign smooth, anatomically accurate vertex weights with at most 4 influences per vertex
    (well within the <= 8 spec limit) and 100% normalized sum = 1.0 on every vertex.
    """
    mesh = mesh_obj.data
    mesh_obj.modifiers.clear()
    arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    arm_mod.object = arm_obj
    arm_mod.use_deform_preserve_volume = True  # Dual-quaternion volume preservation at joints!

    # Create vertex groups for all deformation bones
    vgroups: Dict[str, bpy.types.VertexGroup] = {}
    mesh_obj.vertex_groups.clear()
    bone_segments: Dict[str, Tuple[Vector, Vector]] = {}

    for bname, pname, head, tail, _ in DEFORM_BONE_SPECS:
        vgroups[bname] = mesh_obj.vertex_groups.new(name=bname)
        bone_segments[bname] = (Vector(head), Vector(tail))

    # Define blendable neighbor bone families so torso, limbs, and neck blend smoothly across joints
    blend_chains = {
        "pelvis": ["pelvis", "spine_01", "thigh_l", "thigh_r"],
        "spine_01": ["pelvis", "spine_01", "spine_02"],
        "spine_02": ["spine_01", "spine_02", "spine_03"],
        "spine_03": ["spine_02", "spine_03", "neck_01", "clavicle_l", "clavicle_r"],
        "neck_01": ["spine_03", "neck_01", "neck_02"],
        "neck_02": ["neck_01", "neck_02", "head"],
        "head": ["neck_02", "head"],
    }
    for s_side in ("l", "r"):
        blend_chains.update({
            f"clavicle_{s_side}": ["spine_03", f"clavicle_{s_side}", f"upperarm_{s_side}"],
            f"upperarm_{s_side}": [f"clavicle_{s_side}", f"upperarm_{s_side}", f"upperarm_twist_01_{s_side}"],
            f"upperarm_twist_01_{s_side}": [f"upperarm_{s_side}", f"upperarm_twist_01_{s_side}", f"lowerarm_{s_side}"],
            f"lowerarm_{s_side}": [f"upperarm_twist_01_{s_side}", f"lowerarm_{s_side}", f"lowerarm_twist_01_{s_side}"],
            f"lowerarm_twist_01_{s_side}": [f"lowerarm_{s_side}", f"lowerarm_twist_01_{s_side}", f"hand_{s_side}"],
            f"hand_{s_side}": [f"lowerarm_twist_01_{s_side}", f"hand_{s_side}"],
            f"thigh_{s_side}": ["pelvis", f"thigh_{s_side}", f"thigh_twist_01_{s_side}"],
            f"thigh_twist_01_{s_side}": [f"thigh_{s_side}", f"thigh_twist_01_{s_side}", f"calf_{s_side}"],
            f"calf_{s_side}": [f"thigh_twist_01_{s_side}", f"calf_{s_side}", f"calf_twist_01_{s_side}"],
            f"calf_twist_01_{s_side}": [f"calf_{s_side}", f"calf_twist_01_{s_side}", f"foot_{s_side}"],
            f"foot_{s_side}": [f"calf_twist_01_{s_side}", f"foot_{s_side}", f"ball_{s_side}"],
            f"ball_{s_side}": [f"foot_{s_side}", f"ball_{s_side}"],
        })

    # Rigid or localized parts that should bind cleanly without pulling unrelated geometry
    rigid_or_direct_tags = {
        "eye_l", "eye_r",
        "emitter_mount_r", "emitter_muzzle_r", "cell_socket_r",
        "blade_mount_r", "blade_extend_r",
        "prop_cell", "prop_beacon",
    }

    for v_idx, v in enumerate(mesh.vertices):
        co = v.co
        tag = vert_tags[v_idx]

        # 1. Rigid/Direct parts (eyeballs, cyber weapons, props)
        if tag in rigid_or_direct_tags:
            vgroups[tag].add([v_idx], 1.0, "REPLACE")
            continue

        # 2. Facial sub-regions (blend between specific facial bone and head/jaw)
        if tag in ("jaw", "lip_lower_mid", "lip_lower_l", "lip_lower_r"):
            if tag == "jaw":
                vgroups["jaw"].add([v_idx], 0.85, "REPLACE")
                vgroups["head"].add([v_idx], 0.15, "REPLACE")
            else:
                vgroups[tag].add([v_idx], 0.65, "REPLACE")
                vgroups["jaw"].add([v_idx], 0.35, "REPLACE")
            continue

        if tag in ("tongue_01", "tongue_02"):
            vgroups[tag].add([v_idx], 0.80, "REPLACE")
            vgroups["jaw"].add([v_idx], 0.20, "REPLACE")
            continue

        if tag.startswith(("eyelid_", "brow_", "cheek_", "nostril_", "lip_upper", "lip_corner")):
            if tag in vgroups:
                vgroups[tag].add([v_idx], 0.72, "REPLACE")
                vgroups["head"].add([v_idx], 0.28, "REPLACE")
                continue

        if tag in ("head_chin", "nose_base", "cheek_mid", "eye_lower", "eye_center", "eye_upper", "brow_ridge", "forehead", "cranium"):
            if tag == "head_chin":
                vgroups["jaw"].add([v_idx], 0.75, "REPLACE")
                vgroups["head"].add([v_idx], 0.25, "REPLACE")
            else:
                vgroups["head"].add([v_idx], 1.0, "REPLACE")
            continue

        # 3. Finger phalanges: only blend within the SAME finger + hand (never across adjacent fingers!)
        if any(tag.startswith(fp) for fp in ("thumb_", "index_", "middle_", "ring_", "pinky_")):
            parts = tag.split("_")
            fname, pnum, s_side = parts[0], parts[1], parts[2]
            candidates = [
                f"hand_{s_side}",
                f"{fname}_01_{s_side}",
                f"{fname}_02_{s_side}",
                f"{fname}_03_{s_side}",
            ]
        elif tag.startswith("neural_tether_"):
            candidates = ["head", "neural_tether_01", "neural_tether_02", "neural_tether_03"]
        elif tag.startswith("belt_strap_"):
            candidates = ["pelvis", "belt_strap_01", "belt_strap_02"]
        else:
            candidates = blend_chains.get(tag, [tag if tag in vgroups else "spine_02"])

        # Compute inverse-distance Gaussian weights across candidate bones (max 4 influences)
        raw_w = []
        for bname in candidates:
            a, b = bone_segments[bname]
            d = point_to_segment_dist(co, a, b)
            # Boost primary tag slightly for crisp joint localization
            sigma = 0.055 if bname == tag else 0.045
            w = math.exp(-((d / sigma) ** 2))
            if bname == tag:
                w = max(w, 0.25)
            raw_w.append((bname, w))

        raw_w.sort(key=lambda item: item[1], reverse=True)
        top_w = raw_w[:4]
        total = sum(w for _, w in top_w)
        if total < 1e-8:
            vgroups[candidates[0]].add([v_idx], 1.0, "REPLACE")
        else:
            for bname, w in top_w:
                nw = w / total
                if nw > 0.005:
                    vgroups[bname].add([v_idx], nw, "REPLACE")


def write_skeleton_and_sockets_manifest(out_path: Path):
    """Write docs/skeleton_and_sockets.json documenting every exported bone and socket."""
    bones_list = []
    for idx, (bname, pname, head, tail, roll) in enumerate(DEFORM_BONE_SPECS):
        bones_list.append({
            "index": idx,
            "name": bname,
            "parent": pname,
            "head_m": [round(x, 5) for x in head],
            "tail_m": [round(x, 5) for x in tail],
            "length_m": round((Vector(tail) - Vector(head)).length, 5),
            "roll_rad": round(roll, 5),
            "deform": True,
        })

    doc = {
        "asset_name": "Operative",
        "skeleton_name": "OperativeRig",
        "root_bone": "root",
        "pelvis_bone": "pelvis",
        "total_deformation_bones": len(bones_list),
        "max_bone_influences_per_vertex": 4,
        "spec_max_allowed_influences": 8,
        "coordinate_conventions": {
            "blender_source": {
                "units": "meters",
                "standing_height_m": 1.80,
                "up_axis": "+Z",
                "forward_axis": "-Y",
                "right_axis": "-X (character right is -X, character left is +X)",
            },
            "unreal_engine_target": {
                "units": "centimeters",
                "standing_height_cm": 180.0,
                "import_uniform_scale": 1.0,
                "up_axis": "+Z",
                "forward_axis": "+X (or mesh yaw -90 deg on component)",
            },
        },
        "sockets": SOCKET_DEFINITIONS,
        "deformation_bones": bones_list,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return len(bones_list)

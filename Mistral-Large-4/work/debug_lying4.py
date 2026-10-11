"""Debug: which lying combo sinks below the floor (per-region min z), plus
face-up/down pitch sweeps and an aim muzzle/grip reach sweep.

Run:  blender -b --factory-startup --python work/debug_lying4.py
"""
import sys, os, math

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
                      combat_pose, stance_legs, aim_arm_params,
                      aim_forearm_matrix, support_hand_params,
                      dir_of, mat_cols, ANKLE_Z)
from morphrig_lib import lerp, lerp_v, smoothstep, clamp, FWD, UP, RIGHT

rig = Rig()


# ---------------------------------------------------------------- helpers (copied from probe_gen3)
def rot_with_y(d, ref=None):
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


def fk_hand_arm(M_hand, pole, curl=0.0, spread=0.05):
    return {"mode": "fk", "hand": M_hand, "pole": tuple(pole), "curl": curl,
            "spread": spread, "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 0.0, "yaw": 0.0, "elbow": 0.0, "wrist": 0.0,
            "forearm": None, "target": None, "hand_R": None}


def ik_leg(ankle, yaw=0.0, pitch=0.0, toe=0.0, pole=None):
    return {"mode": "ik", "ankle": tuple(ankle), "yaw": yaw, "pitch": pitch,
            "toe": toe, "pole": tuple(pole)}


def lying_hand_target(rig, M_pel, M_chest, face_down, kind, hand_floor_z=None):
    c = M_chest.to_translation()
    pel = M_pel.to_translation()
    ax = FWD if face_down else -FWD
    if hand_floor_z is None:
        hand_floor_z = 0.12 if kind == "out" else 0.05
    out = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        if kind == "side":
            palm = Vector((c.x + sgn * 0.35, c.y + ax.y * 0.10, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "prone_fwd":
            palm = Vector((c.x + sgn * 0.13, c.y + ax.y * 0.30, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "push":
            palm = Vector((pel.x + sgn * 0.30, pel.y, hand_floor_z))
            RH = rot_with_y(ax, -UP)
        elif kind == "out":
            palm = Vector((c.x + sgn * 0.42, c.y + 0.03, hand_floor_z))
            RH = rot_with_y(Vector((sgn, 0.0, 0.0)), UP)
        elif kind == "belly":
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
    if lean_deg is None:
        lean_deg = 93.18 if face_down else -86.82
    if pelvis_z is None:
        pelvis_z = 0.148 if face_down else 0.183
    if look is None:
        look = (0.0, 5.0) if face_down else (0.0, 27.0)
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
    side_M = lying_hand_target(rig, M_pel, M_chest, face_down, "side", hand_floor_z)
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


def pose(Pp):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)


# ---------------------------------------------------------------- region measurement
def region_of(gname):
    if gname.endswith("_L"):
        base, side = gname[:-2], "L"
    elif gname.endswith("_R"):
        base, side = gname[:-2], "R"
    else:
        base, side = gname, ""
    if base == "hand" or base.startswith("f_"):
        return "hand" + side
    if base.startswith("upper_arm") or base.startswith("forearm"):
        return "chain" + side
    if base.startswith("thigh") or base.startswith("shin"):
        return "leg" + side
    if base in ("foot", "toe"):
        return "foot" + side
    if base in ("pelvis",):
        return "pelvis"
    if base.startswith("spine") or base == "clavicle" or base.startswith("clavicle"):
        return "chest"
    if base in ("neck_01", "neck_02", "head", "jaw", "eye", "lid_upper", "lid_lower", "brow"):
        return "head"
    if base.startswith("cable"):
        return "cable"
    if base in ("emitter", "blade", "cell_new", "cell_spent", "beacon"):
        return "prop"
    if base == "root":
        return "root"
    return None


def region_min_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    vg_name = {vg.index: vg.name for vg in rig.M.vertex_groups}
    mins = {}
    glob = 1e9
    glob_v = None
    for v in mm.vertices:
        best, bw = None, 0.0
        for g in v.groups:
            if g.weight > bw:
                bw = g.weight
                best = g.group
        r = region_of(vg_name.get(best, ""))
        if v.co.z < glob:
            glob = v.co.z
            glob_v = (r, tuple(round(c, 3) for c in v.co))
        if r is not None and v.co.z < mins.get(r, 1e9):
            mins[r] = v.co.z
    me.to_mesh_clear()
    return glob, glob_v, mins


print("== PART 1: per-combo region breakdown (current lying_pp defaults)")
for face_down in (True, False):
    for kind in ("side", "prone_fwd", "push", "out", "belly"):
        for leg_s, arm_s in ((1.0, 1.0), (0.0, 0.0), (0.35, 0.5)):
            Pp, info = lying_pp(rig, face_down, leg_s=leg_s, arm_s=arm_s, kind=kind)
            pose(Pp)
            glob, glob_v, mins = region_min_z()
            flag = "OK  " if glob >= -0.005 else "SINK"
            lows = {r: round(z, 4) for r, z in sorted(mins.items()) if z < 0.02}
            print("   %s %-9s leg_s=%.2f arm_s=%.1f | glob=%7.4f %s at %s | %s"
                  % ("down" if face_down else "up  ", kind, leg_s, arm_s,
                     glob, flag, glob_v, lows))

print("")
print("== PART 2: pitch sweeps (glob + head-region min)")
for face_down, pz, pitches in ((True, 0.148, [x * 1.0 for x in range(-2, 13)]),
                               (False, 0.183, [x * 1.0 for x in range(20, 33)])):
    for kind in ("prone_fwd", "belly"):
        for pitch in pitches:
            Pp, info = lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0,
                                pelvis_z=pz, kind=kind, look=(0.0, pitch))
            pose(Pp)
            glob, glob_v, mins = region_min_z()
            print("   %s %-9s pitch=%4.1f | glob=%7.4f head=%7.4f chest=%7.4f pelvis=%7.4f at %s"
                  % ("down" if face_down else "up  ", kind, pitch,
                     glob, mins.get("head", 9), mins.get("chest", 9),
                     mins.get("pelvis", 9), glob_v))

print("")
print("== PART 3: aim grid L-grip reach vs muzzle_dist x grip_dist")


def build_aim2(rig, yaw, pitch, pelvis_z=0.905, spread=0.075, grip_dist=0.25,
               muzzle_dist=0.40, curl=0.25):
    Pp = P(pelvis__z=pelvis_z, pelvis__shift=0.0, pelvis__lean=0.0,
           pelvis__roll=0.0, chest__lean=0.0, chest__yaw=0.0,
           look=(0.0, 0.0), w=(1.0, 0.0, 0.0))
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    Pp["legs"] = stance_legs(rig, M_pel, alpha=0.0, spread=spread)
    d = dir_of(yaw, pitch)
    R = aim_forearm_matrix(rig, yaw, pitch)
    em_off = R @ rig.rl["emitter"].to_translation()
    muzzle = M_chest.to_translation() + d * muzzle_dist
    elbow_dir = muzzle - em_off - sh["R"]
    armR = aim_arm_params(rig, "R", sh["R"], yaw, pitch, elbow_dir,
                          curl=curl, spread=0.10)
    M_fa_R = armR["forearm"]
    fa_R = M_fa_R.to_3x3()
    grip_pt = M_fa_R @ Vector((0.0, grip_dist, 0.0))
    y_fa = fa_R @ Vector((0.0, 1.0, 0.0))
    z_fa = fa_R @ Vector((0.0, 0.0, 1.0))
    grip_M = Matrix.Translation(grip_pt - 0.06 * y_fa - 0.047 * z_fa) @ fa_R.to_4x4()
    return grip_M, sh


for muzzle_dist in (0.40, 0.38, 0.36):
    for grip_dist in (0.25, 0.23, 0.21):
        worst = 0.0
        worst_at = None
        for yaw in (-60.0, 0.0, 60.0):
            for pitch in (-35.0, 0.0, 35.0):
                grip_M, sh = build_aim2(rig, yaw, pitch, grip_dist=grip_dist,
                                        muzzle_dist=muzzle_dist)
                reach = (grip_M.to_translation() - sh["L"]).length
                if reach > worst:
                    worst = reach
                    worst_at = (yaw, pitch)
        print("   muzzle=%.2f grip=%.2f | worst L reach=%.4f at yaw=%s pitch=%s (limit 0.6113)"
              % (muzzle_dist, grip_dist, worst, worst_at[0], worst_at[1]))

print("")
print("DEBUG4 DONE")

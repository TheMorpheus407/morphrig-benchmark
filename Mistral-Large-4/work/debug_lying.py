"""Debug: which mesh vertices are below the floor in lying poses, and the
step_turn final-ankle mismatch."""
import sys, os, math

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, hip_pos, combat_pose,
                      stance_legs, dir_of, mat_cols, R_axis, ANKLE_Z)
from morphrig_lib import lerp, lerp_v, smoothstep, FWD, UP, RIGHT

rig = Rig()
PROP_OFF = {p: rig.rest["pelvis"].inverted() @ rig.rest[p]
            for p in ("cell_new", "cell_spent", "beacon")}


def mat_err(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))


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


def fk_hand_arm(M_hand, pole, curl=0.18, spread=0.05):
    return {"mode": "fk", "hand": M_hand, "pole": tuple(pole), "curl": curl,
            "spread": spread, "w": (1.0, 0.0, 0.0), "swing": 0.0,
            "lift": 0.0, "yaw": 0.0, "elbow": 0.0, "wrist": 0.0,
            "forearm": None, "target": None, "hand_R": None}


def ik_leg(ankle, yaw=0.0, pitch=0.0, toe=0.0, pole=None):
    return {"mode": "ik", "ankle": tuple(ankle), "yaw": yaw, "pitch": pitch,
            "toe": toe, "pole": tuple(pole)}


def lying_hand_target(rig, M_pel, M_chest, face_down, kind):
    c = M_chest.to_translation()
    pel = M_pel.to_translation()
    ax = FWD if face_down else -FWD
    out = {}
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        if kind == "side":
            palm = c + Vector((sgn * 0.35, ax.y * 0.10, 0.0)) - UP * 0.10
            RH = rot_with_y(ax, -UP)
        elif kind == "prone_fwd":
            palm = c + ax * (0.30 if side == "L" else 0.32) \
                + Vector((sgn * 0.13, 0.0, 0.0)) - UP * 0.10
            RH = rot_with_y(ax, -UP)
        elif kind == "push":
            palm = pel + Vector((sgn * 0.30, 0.0, -0.10))
            RH = rot_with_y(ax, -UP)
        elif kind == "out":
            palm = c + Vector((sgn * 0.42, 0.03, 0.0)) - UP * 0.11
            RH = rot_with_y(Vector((sgn, 0.0, 0.0)), UP)
        elif kind == "belly":
            palm = c + Vector((sgn * 0.09, ax.y * 0.02, 0.06))
            RH = rot_with_y(ax, -UP)
        out[side] = hand_M(palm, RH @ Vector((0.0, 1.0, 0.0)),
                           RH @ Vector((0.0, 0.0, 1.0)))
    return out


def lying_pp(rig, face_down, leg_s=1.0, arm_s=1.0, pelvis_z=0.13, lean_deg=None,
             kind="prone_fwd", look=(0.0, 0.0), face=None, roll=0.0, shift=0.0,
             w=(1.0, 0.0, 0.0), chest_lean=0.0, chest_yaw=0.0, hand_over=None):
    if lean_deg is None:
        lean_deg = 93.18 if face_down else -86.82
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
        ankle = Vector((hip.x, hip.y + back * 0.55 * leg_s,
                        ANKLE_Z + 0.32 * math.sin(math.pi * min(leg_s * 1.3, 1.0))
                        * (1.0 - 0.5 * leg_s)))
        pole = hip + Vector((0.0, back * 0.25, 0.35))
        legs[side] = ik_leg(ankle, yaw=180.0 if face_down else 0.0, pole=pole)
    Pp["legs"] = legs
    side_M = lying_hand_target(rig, M_pel, M_chest, face_down, "side")
    kind_M = lying_hand_target(rig, M_pel, M_chest, face_down, kind)
    for side in ("L", "R"):
        if hand_over is not None and side in hand_over:
            M_h_t = hand_over[side]
        else:
            M_h_t = rig_ops.lerp_matrices(side_M[side], kind_M[side], arm_s)
        pole = sh[side] + Vector((0.0, ax.y * 0.10, 0.30))
        Pp["arms"][side] = fk_hand_arm(M_h_t, pole, curl=0.15, spread=0.05)
    return Pp, {"M_pel": M_pel, "M_chest": M_chest, "shoulders": sh}


def ride_props(rig, Pp, M_pel):
    gs = Pp["scale"]
    M_pel_s = Matrix.Diagonal((gs, gs, gs, 1.0)) @ M_pel if abs(gs - 1.0) > 1e-9 else M_pel
    for p in ("cell_new", "cell_spent", "beacon"):
        if p not in Pp["def"]:
            Pp["def"][p] = M_pel_s @ PROP_OFF[p]


def pose(Pp):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)


def lowest_verts(k=8):
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    vs = sorted(mm.vertices, key=lambda v: v.co.z)[:k]
    out = [(round(v.co.x, 3), round(v.co.y, 3), round(v.co.z, 4)) for v in vs]
    me.to_mesh_clear()
    return out


def mesh_min_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    z = min(v.co.z for v in mm.vertices)
    me.to_mesh_clear()
    return z


print("== lowest verts per lying pose")
for face_down in (True, False):
    for kind in ("side", "prone_fwd", "push", "out", "belly"):
        for leg_s, arm_s in ((1.0, 1.0), (0.0, 0.0), (0.35, 0.5)):
            Pp, info = lying_pp(rig, face_down, leg_s=leg_s, arm_s=arm_s, kind=kind)
            ride_props(rig, Pp, info["M_pel"])
            pose(Pp)
            mz = mesh_min_z()
            print("face_down=%d kind=%-9s leg_s=%.2f arm_s=%.2f  min_z=%8.4f  lowest=%s"
                  % (face_down, kind, leg_s, arm_s, mz, lowest_verts(3)))

print("")
print("== prop bone positions in a lying pose (face-down, prone_fwd)")
Pp, info = lying_pp(rig, True, leg_s=1.0, arm_s=1.0, kind="prone_fwd")
ride_props(rig, Pp, info["M_pel"])
pose(Pp)
for p in ("cell_new", "cell_spent", "beacon"):
    print("   %s at %s" % (p, tuple(round(c, 3) for c in rig.def_m[p].to_translation())))
print("   head at %s  chest at %s  pelvis at %s" % (
    tuple(round(c, 3) for c in rig.def_m["head"].to_translation()),
    tuple(round(c, 3) for c in rig.def_m["spine_02"].to_translation()),
    tuple(round(c, 3) for c in rig.def_m["pelvis"].to_translation())))
print("   foot_L at %s  foot_R at %s" % (
    tuple(round(c, 3) for c in rig.def_m["foot_L"].to_translation()),
    tuple(round(c, 3) for c in rig.def_m["foot_R"].to_translation())))
print("   knee_L(shin_L head) at %s" % (
    tuple(round(c, 3) for c in rig.def_m["shin_L"].to_translation()),))

"""Tuning probe 2: hand-only droop at chosen lying heights + use_cyclic v2.

Run:  blender -b --factory-startup --python work/tune_lying2.py
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
from anim_lib import (Rig, P, apply_pose, body_matrices, hip_pos,
                      mat_cols, ANKLE_Z)
from morphrig_lib import lerp, lerp_v, smoothstep, clamp, FWD, UP, RIGHT

rig = Rig()


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


def lying_hand_target2(rig, M_pel, M_chest, face_down, kind, hand_floor_z=0.115):
    c = M_chest.to_translation()
    pel = M_pel.to_translation()
    ax = FWD if face_down else -FWD
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
        out[side] = hand_M(palm, RH @ Vector((0.0, 1.0, 0.0)),
                           RH @ Vector((0.0, 0.0, 1.0)))
    return out


def lying_pp2(rig, face_down, leg_s=1.0, arm_s=1.0, pelvis_z=0.13, lean_deg=None,
              kind="prone_fwd", look=(0.0, 0.0), face=None, roll=0.0, shift=0.0,
              w=(1.0, 0.0, 0.0), chest_lean=0.0, chest_yaw=0.0,
              hand_over=None, hand_floor_z=0.115):
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
        ankle = Vector((hip.x, hip.y + back * (0.20 + 0.35 * leg_s), ANKLE_Z))
        pole = hip + Vector((0.0, back * 0.25, 0.35))
        legs[side] = ik_leg(ankle, yaw=180.0 if face_down else 0.0, pole=pole)
    Pp["legs"] = legs
    side_M = lying_hand_target2(rig, M_pel, M_chest, face_down, "side", hand_floor_z)
    kind_M = lying_hand_target2(rig, M_pel, M_chest, face_down, kind, hand_floor_z)
    for side in ("L", "R"):
        if hand_over is not None and side in hand_over:
            M_h_t = hand_over[side]
        else:
            M_h_t = rig_ops.lerp_matrices(side_M[side], kind_M[side], arm_s)
        pole = sh[side] + Vector((0.0, ax.y * 0.10, 0.30))
        Pp["arms"][side] = fk_hand_arm(M_h_t, pole, curl=0.0, spread=0.05)
    return Pp, {"M_pel": M_pel, "M_chest": M_chest, "shoulders": sh}


def pose(Pp):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)


def bucket_of(gname):
    if gname.endswith("_L"):
        base, side = gname[:-2], "L"
    elif gname.endswith("_R"):
        base, side = gname[:-2], "R"
    else:
        return None
    if base == "hand" or base.startswith("f_"):
        return "hand" + side
    if base.startswith("upper_arm") or base.startswith("forearm"):
        return "chain" + side
    return None


def region_min_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    vg_name = {vg.index: vg.name for vg in rig.M.vertex_groups}
    mins = {}
    glob = 1e9
    for v in mm.vertices:
        best, bw = None, 0.0
        for g in v.groups:
            if g.weight > bw:
                bw = g.weight
                best = g.group
        b = bucket_of(vg_name.get(best, ""))
        if v.co.z < glob:
            glob = v.co.z
        if b is not None and v.co.z < mins.get(b, 1e9):
            mins[b] = v.co.z
    me.to_mesh_clear()
    return glob, mins


def ik_error2(rig, Pp):
    worst = 0.0
    for side in ("L", "R"):
        leg = Pp["legs"][side]
        worst = max(worst, (rig.def_m["foot_%s" % side].to_translation()
                            - Vector(leg["ankle"])).length)
        arm = Pp["arms"][side]
        worst = max(worst, (rig.def_m["hand_%s" % side].to_translation()
                            - arm["hand"].to_translation()).length)
    return worst


print("== PART A: hand-only droop at chosen lying heights")
print("   face-down pz=0.148 pitch=+5 | face-up pz=0.183 pitch=+30")
for face_down, pz, pitch in ((True, 0.148, 5.0), (False, 0.183, 30.0)):
    for kind in ("side", "prone_fwd", "push", "out"):
        for hfz in (0.03, 0.05, 0.08, 0.10, 0.12, 0.14):
            Pp, info = lying_pp2(rig, face_down, leg_s=1.0, arm_s=1.0,
                                 pelvis_z=pz, kind=kind, look=(0.0, pitch),
                                 hand_floor_z=hfz)
            pose(Pp)
            glob, mins = region_min_z()
            reach = max((Pp["arms"][s]["hand"].to_translation()
                         - info["shoulders"][s]).length for s in ("L", "R"))
            print("   %s %-9s hfz=%.2f | handL=%7.4f handR=%7.4f chainL=%7.4f chainR=%7.4f glob=%7.4f ik=%.1e reach=%.3f"
                  % ("down" if face_down else "up  ", kind, hfz,
                     mins.get("handL", 9), mins.get("handR", 9),
                     mins.get("chainL", 9), mins.get("chainR", 9),
                     glob, ik_error2(rig, Pp), reach))

print("")
print("== PART B: full contact matrix at chosen heights (all kinds/extremes)")
for face_down, pz, pitch in ((True, 0.148, 5.0), (False, 0.183, 30.0)):
    hfz = 0.05 if True else 0.12
    for kind in ("side", "prone_fwd", "push", "out", "belly"):
        for leg_s, arm_s in ((1.0, 1.0), (0.0, 0.0), (0.35, 0.5)):
            # per-kind floor height: palm-down kinds 0.05, palm-up 0.12
            hfz_k = 0.12 if kind == "out" else 0.05
            Pp, info = lying_pp2(rig, face_down, leg_s=leg_s, arm_s=arm_s,
                                 pelvis_z=pz, kind=kind, look=(0.0, pitch),
                                 hand_floor_z=hfz_k)
            pose(Pp)
            glob, mins = region_min_z()
            ikr = ik_error2(rig, Pp)
            reach = max((Pp["arms"][s]["hand"].to_translation()
                         - info["shoulders"][s]).length for s in ("L", "R"))
            hz = rig.def_m["head"].to_translation().z
            flag = "OK " if glob >= -0.005 else "SINK"
            print("   %s %-9s leg_s=%.2f arm_s=%.1f | glob=%7.4f %s ik=%.1e reach=%.3f head_z=%.3f"
                  % ("down" if face_down else "up  ", kind, leg_s, arm_s,
                     glob, flag, ikr, reach, hz))

print("")
print("== PART C: use_cyclic wrap test (shape-key action, 5.1 slotted API)")
sk = rig.M.data.shape_keys
if sk.animation_data is None:
    sk.animation_data_create()
act = bpy.data.actions.new("cyc_test")
sk.animation_data.action = act
kb = sk.key_blocks["lip_close"]
kb.value = 0.0
kb.keyframe_insert("value", frame=1)
kb.value = 1.0
kb.keyframe_insert("value", frame=3)
nfc = 0
for layer in act.layers:
    for strip in layer.strips:
        for cb in strip.channelbags:
            for fc in cb.fcurves:
                nfc += 1
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
print("   fcurves found via layers: %d" % nfc)
try:
    act.frame_start = 1
    act.frame_end = 3
    act.use_cyclic = True
    print("   use_cyclic=True OK; frame_range=[%d,%d] use_frame_range=%s"
          % (act.frame_start, act.frame_end, getattr(act, "use_frame_range", None)))
except Exception as e:
    print("   use_cyclic FAILED:", repr(e))
for f in (0, 1, 2, 3, 4, 5, 6):
    bpy.context.scene.frame_set(f)
    print("   frame %d -> lip_close = %.4f" % (f, kb.value))
sk.animation_data.action = None
bpy.data.actions.remove(act)

print("")
print("TUNE2 DONE")

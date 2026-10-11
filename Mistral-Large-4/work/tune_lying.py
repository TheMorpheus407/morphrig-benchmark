"""Tuning probe: lying floor contact per region, hand droop, leg_s=0 fold,
Action.use_cyclic wrap, step_turn final-ankle fix.

Run:  blender -b --factory-startup --python work/tune_lying.py
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
                      combat_pose, stance_legs, dir_of, mat_cols, R_axis,
                      ANKLE_Z, TWO_PI)
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
        # folded legs: ankle stays on the floor, slides back toward the hip;
        # the knee rises UP (pole above) instead of spearing the floor
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


def region_of(gname):
    if gname in ("head", "jaw", "neck_01", "neck_02", "eye_L", "eye_R",
                 "lid_upper_L", "lid_lower_L", "brow_L",
                 "lid_upper_R", "lid_lower_R", "brow_R"):
        return "head"
    if gname == "pelvis":
        return "butt"
    if gname.startswith("spine") or gname.startswith("clavicle"):
        return "chest"
    if gname in ("cell_new", "cell_spent", "beacon", "emitter", "blade") \
            or gname.startswith("cable"):
        return "prop"
    if gname.endswith("_L"):
        base = gname[:-2]
    elif gname.endswith("_R"):
        base = gname[:-2]
    else:
        return "other"
    if base.startswith("f_") or base in ("hand", "upper_arm", "forearm",
                                         "upper_arm_twist", "forearm_twist"):
        return "arm" + gname[-1]
    if base.startswith("thigh") or base.startswith("shin") \
            or base in ("foot", "toe"):
        return "leg" + gname[-1]
    return "other"


REGIONS = ("head", "butt", "chest", "armL", "armR", "legL", "legR", "prop", "other")


def region_min_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    vg_name = {vg.index: vg.name for vg in rig.M.vertex_groups}
    mins = {r: 1e9 for r in REGIONS}
    for v in mm.vertices:
        best, bw = None, 0.0
        for g in v.groups:
            if g.weight > bw:
                bw = g.weight
                best = g.group
        r = region_of(vg_name.get(best, ""))
        if v.co.z < mins[r]:
            mins[r] = v.co.z
    me.to_mesh_clear()
    return mins


print("== PART 1: lying floor contact sweep (kind=prone_fwd, leg_s=1, arm_s=1)")
print("   rows: face_down pz pitch | head butt chest armL armR legL legR | global argmin")
for face_down in (True, False):
    for pz in (0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22):
        for pitch in (-40.0, -20.0, 0.0, 20.0, 40.0):
            Pp, info = lying_pp2(rig, face_down, leg_s=1.0, arm_s=1.0,
                                 pelvis_z=pz, kind="prone_fwd",
                                 look=(0.0, pitch))
            pose(Pp)
            mins = region_min_z()
            g = min(mins.values())
            arg = min(mins, key=lambda r: mins[r])
            print("   %s pz=%.2f pitch=%5.1f | %s | g=%.4f (%s)" % (
                "down" if face_down else "up  ", pz, pitch,
                " ".join("%s=%7.4f" % (r[:4], mins[r]) for r in REGIONS),
                g, arg))

print("")
print("== PART 2: hand droop per kind (pz=0.13, pitch=0, leg_s=1, arm_s=1)")
print("   droop = hand_floor_z - arm_min  (want final mesh bottom ~ +0.005)")
for face_down in (True, False):
    for kind in ("side", "prone_fwd", "push", "out"):
        row = []
        for hfz in (0.05, 0.115):
            Pp, info = lying_pp2(rig, face_down, leg_s=1.0, arm_s=1.0,
                                 pelvis_z=0.13, kind=kind, hand_floor_z=hfz)
            pose(Pp)
            mins = region_min_z()
            arm_min = min(mins["armL"], mins["armR"])
            row.append("hfz=%.3f arm_min=%7.4f droop=%.4f" % (hfz, arm_min, hfz - arm_min))
        print("   %s %-9s | %s" % ("down" if face_down else "up  ", kind, " | ".join(row)))

print("")
print("== PART 3: leg_s=0 fold (new formula) + leg_s=0.35")
for face_down in (True, False):
    for leg_s in (0.0, 0.35):
        Pp, info = lying_pp2(rig, face_down, leg_s=leg_s, arm_s=1.0,
                             pelvis_z=0.13, kind="prone_fwd")
        pose(Pp)
        mins = region_min_z()
        g = min(mins.values())
        kneeL = rig.def_m["shin_L"].to_translation()
        kneeR = rig.def_m["shin_R"].to_translation()
        print("   %s leg_s=%.2f global=%.4f legL=%.4f legR=%.4f kneeL=(%.3f,%.3f,%.3f) kneeR=(%.3f,%.3f,%.3f)"
              % ("down" if face_down else "up  ", leg_s, g,
                 mins["legL"], mins["legR"],
                 kneeL.x, kneeL.y, kneeL.z, kneeR.x, kneeR.y, kneeR.z))

print("")
print("== PART 4: Action.use_cyclic wrap test")
pb = rig.A.pose.bones["root"]
if rig.A.animation_data is None:
    rig.A.animation_data_create()
act = bpy.data.actions.new("cyc_test")
rig.A.animation_data.action = act
fc = act.fcurves.new('pose.bones["root"].location', index=2)
fc.keyframe_points.add(2)
fc.keyframe_points[0].co = (1.0, 0.0)
fc.keyframe_points[1].co = (3.0, 2.0)
for kp in fc.keyframe_points:
    kp.interpolation = 'LINEAR'
try:
    act.frame_start = 1
    act.frame_end = 3
    act.use_cyclic = True
    print("   use_cyclic set OK; frame_range=[%d, %d]" % (act.frame_start, act.frame_end))
except Exception as e:
    print("   use_cyclic FAILED:", e)
for f in (0, 1, 2, 3, 4, 5):
    bpy.context.scene.frame_set(f)
    print("   frame %d -> root.location.z = %.4f" % (f, pb.location.z))
rig.A.animation_data.action = None
bpy.data.actions.remove(act)

print("")
print("== PART 5: step_turn fixed final ankle")


def inv_smoothstep(s):
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if mid * mid * (3.0 - 2.0 * mid) < s:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def step_turn2(rig, f, n, total_deg, pelvis_z=0.90, spread=0.075, arm_swing=8.0):
    """Faithful copy of probe_gen3.step_turn + the final-ankle fix: if a
    foot's last planned step does not reach the final yaw, append a small
    catch-up step at f=n targeting total_deg (how a real turn ends)."""
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
        if abs(fyaws[side] - total_deg) > 1e-9:
            fc = float(n)
            R_z = Matrix.Rotation(math.radians(total_deg - fyaws[side]), 4, 'Z')
            new_ankle = R_z @ ankles[side]
            foot_data[side].append((fc, ankles[side].copy(), new_ankle,
                                    fyaws[side], total_deg))
            ankles[side] = new_ankle
            fyaws[side] = total_deg
    cur = {}
    for side in ("L", "R"):
        ankle = a0[side].copy()
        fyaw = 0.0
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
                break
        cur[side] = (ankle, fyaw)
    aL, fyL = cur["L"]
    aR, fyR = cur["R"]
    Pp = P(pelvis__z=pelvis_z, pelvis__yaw=yaw, pelvis__lean=2.0,
           chest__yaw=0.6 * yaw, look=(clamp(0.5 * yaw, -75.0, 75.0), 0.0))
    L = rig.leg_len
    for _ in range(3):
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        pz = Pp["pelvis"]["z"]
        for side, a in (("L", aL), ("R", aR)):
            hip = hip_pos(rig, side, M_pel)
            dxy = math.hypot(hip.x - a.x, hip.y - a.y)
            R_pel = M_pel.to_3x3()
            hzoff = (R_pel @ rig.rl["thigh_%s" % side].to_translation()).z
            pz = min(pz, a.z + 0.93 * math.sqrt(max(0.04, L * L - dxy * dxy)) - hzoff)
        if abs(pz - Pp["pelvis"]["z"]) < 1e-9:
            break
        Pp["pelvis"]["z"] = pz
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    for side, a, fy in (("L", aL, fyL), ("R", aR, fyR)):
        hip = hip_pos(rig, side, M_pel)
        u = dir_of(fy, 0.0)
        pole = hip + u * 0.30 + Vector((0.0, 0.0, -0.25))
        Pp["legs"][side] = ik_leg(a, yaw=fy, pole=pole)
    nc = len(cross_mag)
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        swing = sgn * arm_swing * math.sin(TWO_PI * (f - 1) / float(n) * nc)
        Pp["arms"][side] = {"mode": "fk_param", "w": (1.0, 0.0, 0.0),
                            "swing": swing, "lift": 6.0, "yaw": 0.0,
                            "elbow": 16.0, "wrist": -8.0, "curl": 0.18,
                            "spread": 0.05, "hand": None, "forearm": None,
                            "target": None, "pole": None, "hand_R": None}
    return Pp


def ik_error2(rig, Pp):
    worst = 0.0
    for side in ("L", "R"):
        leg = Pp["legs"][side]
        if leg["mode"] == "ik":
            worst = max(worst, (rig.def_m["foot_%s" % side].to_translation()
                                - Vector(leg["ankle"])).length)
    return worst


for total, nn in ((-90.0, 24), (90.0, 24), (-180.0, 30), (180.0, 30)):
    worst_ik = 0.0
    foot_hist = {"L": [], "R": []}
    for f in range(1, nn + 1):
        Pp = step_turn2(rig, f, nn, total)
        pose(Pp)
        worst_ik = max(worst_ik, ik_error2(rig, Pp))
        for s in ("L", "R"):
            foot_hist[s].append(rig.def_m["foot_%s" % s].to_translation().copy())
    worst_jump = 0.0
    for s in ("L", "R"):
        for i in range(nn - 1):
            a, b = foot_hist[s][i], foot_hist[s][i + 1]
            if abs(a.z - ANKLE_Z) < 1e-4 and abs(b.z - ANKLE_Z) < 1e-4:
                worst_jump = max(worst_jump, (a - b).length)
    Pp0 = P(pelvis__z=0.90)
    _, M_pel0, _, _, _ = body_matrices(rig, Pp0)
    R_z = Matrix.Rotation(math.radians(total), 4, 'Z')
    worst_ank = 0.0
    for side, sgn in (("L", -1.0), ("R", 1.0)):
        hip0 = hip_pos(rig, side, M_pel0)
        a0 = Vector((hip0.x + sgn * 0.075, hip0.y, ANKLE_Z))
        want = R_z @ a0
        worst_ank = max(worst_ank,
                        (foot_hist[side][-1] - want).length)
    print("   turn %6.1f n=%d: ik=%.2e planted_jump=%.2e final_ankle_err=%.2e"
          % (total, nn, worst_ik, worst_jump, worst_ank))

print("")
print("TUNE DONE")

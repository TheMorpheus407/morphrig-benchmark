"""Probe v4: diagnose the gen_03 bake failures in clips 71-86 (floor
penetration on face-up lying, chain clamp on getup) and the dialogue
CLAUSE_GAZE arity crash.

Section G: getup_front / getup_back at EVERY frame -- per-limb chain
           errors (which limb clamps, where, by how much) and the arm
           target vs shoulder distance vs the arm reach limit.
Section L: face-up lying floor diagnosis -- mesh min z at the cap frames
           of every failing lying clip, the lowest mesh vert and its
           vertex group, and the same metrics with the candidate raised
           face-up pelvis base (0.183 -> 0.2230) for the plain lying
           poses (kinds out / belly / prone_fwd / push).

Run: blender -b --factory-startup --python work/probe_v4.py
"""
import math
import os
import sys

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(TASK, "source", "generators", "gen_03_animations.py")

import bpy
from mathutils import Vector, Matrix

src = open(GEN, encoding="utf-8").read()
head = src.split("# ==================================================================== bake")[0]
ns = {"__file__": GEN, "__name__": "probe_head"}
exec(compile(head, GEN, "exec"), ns)

rig = ns["rig"]
apply_pose = ns["apply_pose"]
body_matrices = ns["body_matrices"]
ride_props = ns["ride_props"]
mesh_min_z = ns["mesh_min_z"]
ik_error = ns["ik_error"]
chain_error = ns["chain_error"]
lying_pp = ns["lying_pp"]
getup_push_pose = ns["getup_push_pose"]
rot_with_y = ns["rot_with_y"]
FWD = ns["FWD"]
UP = ns["UP"]
PLANT = ns["PLANT"]
LEG_L1 = ns["LEG_L1"]
LEG_L2 = ns["LEG_L2"]
SPECS = ns["SPECS"]


def spec_of(cid):
    return next(s for s in SPECS if s["id"] == cid)


def V(v):
    return tuple(round(c, 4) for c in v)


def run_clip(gen, f, n):
    Pp = gen(rig, f, n)
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    return Pp


def limb_chains():
    out = {}
    for side in ("L", "R"):
        ua = rig.def_m["upper_arm_%s" % side].to_translation()
        fa = rig.def_m["forearm_%s" % side].to_translation()
        hd = rig.def_m["hand_%s" % side].to_translation()
        out["arm_" + side] = max(abs((fa - ua).length - rig.arm_L1[side]),
                                 abs((hd - fa).length - rig.arm_L2[side]))
        th = rig.def_m["thigh_%s" % side].to_translation()
        sh = rig.def_m["shin_%s" % side].to_translation()
        ft = rig.def_m["foot_%s" % side].to_translation()
        out["leg_" + side] = max(abs((sh - th).length - LEG_L1),
                                 abs((ft - sh).length - LEG_L2))
    return out


def lowest_vert():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    mesh_obj = bpy.data.objects["Operative"]
    groups = mesh_obj.vertex_groups
    best = None
    for v in mm.vertices:
        if best is None or v.co.z < best[0]:
            w, gname = 0.0, "?"
            for g in v.groups:
                if g.weight > w and g.group < len(groups):
                    w = g.weight
                    gname = groups[g.group].name
            best = (v.co.z, tuple(round(c, 4) for c in v.co), gname)
    me.to_mesh_clear()
    return best


print("== G: getup chain diagnosis (every frame)")
for cid in ("getup_front", "getup_back"):
    sp = spec_of(cid)
    gen, n = sp["gen"], sp["n"]
    worst = {}
    nbad = 0
    for f in range(1, n + 1):
        rig.reset()
        Pp = run_clip(gen, f, n)
        lc = limb_chains()
        for k, val in lc.items():
            if val > worst.get(k, (0.0, 0))[0]:
                worst[k] = (val, f)
        bad = {k: round(v, 5) for k, v in lc.items() if v > 1e-4}
        if bad:
            nbad += 1
            info = []
            for side in ("L", "R"):
                arm = Pp["arms"][side]
                sh = rig.def_m["upper_arm_%s" % side].to_translation()
                tgt = arm.get("target")
                if tgt is None and arm.get("hand") is not None:
                    tgt = arm["hand"].to_translation()
                if tgt is not None:
                    d = (Vector(tgt) - sh).length
                    info.append("%s tgt=%s sh=%s d=%.4f/%.4f"
                                % (side, V(tgt), V(sh), d, rig.arm_len[side]))
            print("   %s f=%2d bad=%s" % (cid, f, bad))
            for line in info:
                print("        %s" % line)
    print("   %s: %d frames with chain>1e-4; worst per limb: %s"
          % (cid, nbad, {k: (round(v[0], 5), v[1]) for k, v in worst.items()}))

print("== L: face-up lying floor diagnosis (cap frames)")
LYING_TESTS = [
    ("prone_back", (1, 23, 45)),
    ("sleep_loop", (1, 30, 46, 60)),
    ("knockdown_back", (1, 22, 36)),
    ("death_front", (1, 37, 64, 75)),
    ("dead_front", (1, 2)),
    ("respawn", (1, 10, 25, 45, 70, 90)),
    ("getup_back", (1, 27, 54)),
]
for cid, frames in LYING_TESTS:
    sp = spec_of(cid)
    gen, n = sp["gen"], sp["n"]
    for f in frames:
        rig.reset()
        Pp = run_clip(gen, f, n)
        mz = mesh_min_z()
        lv = lowest_vert()
        print("   %-14s f=%2d min_z=%+.4f lowest vert z=%+.4f at %s grp=%s"
              " chain=%.2e ik=%.2e"
              % (cid, f, mz, lv[0], lv[1], lv[2],
                 chain_error(rig), ik_error(rig, Pp)))

print("== L2: plain face-up lying with raised base pelvis_z=0.2230")
for kind in ("out", "belly", "prone_fwd", "push"):
    rig.reset()
    Pp, info = lying_pp(rig, False, leg_s=1.0, arm_s=1.0, pelvis_z=0.2230,
                        kind=kind, plant=PLANT)
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    print("   kind=%-9s min_z=%+.4f chain=%.2e ik=%.2e"
          % (kind, mesh_min_z(), chain_error(rig), ik_error(rig, Pp)))

print("== L3: getup push pose, raised base, st=1 (palms under shoulders)")
rig.reset()
info_ref = lying_pp(rig, False, leg_s=1.0, arm_s=1.0, kind="out",
                    plant=PLANT, pelvis_z=0.2230)[1]
for lean, pz in ((-86.82, 0.2230), (-38.0, 0.34), (-10.0, 0.68)):
    rig.reset()
    Pp = getup_push_pose(rig, False, 0.8, lean, pz, 1.0, info_ref,
                         rot_with_y(-FWD, -UP))[0]
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    lc = limb_chains()
    print("   lean=%6.2f pz=%.3f min_z=%+.4f chain=%.2e ik=%.2e worst_limb=%s"
          % (lean, pz, mesh_min_z(), chain_error(rig), ik_error(rig, Pp),
             max(lc, key=lc.get)))
    for side in ("L", "R"):
        arm = Pp["arms"][side]
        sh = rig.def_m["upper_arm_%s" % side].to_translation()
        tgt = arm["hand"].to_translation()
        print("        %s tgt=%s sh=%s d=%.4f/%.4f"
              % (side, V(tgt), V(sh), (tgt - sh).length, rig.arm_len[side]))

print("PROBE V4 DONE")

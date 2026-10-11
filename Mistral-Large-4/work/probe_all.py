"""Probe ALL: every frame of all 96 clips -- chain/ik/floor, stricter than
the bake's cap-frame sampling.  Reports per-clip worst values and any
frame where chain > 2e-4, ik > 1e-4 or min_z < -0.005 (floor_ok band;
floor_all_ok band is -0.02, checked separately as the all-frame minimum).

Run: blender -b --factory-startup --python work/probe_all.py
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
SPECS = ns["SPECS"]

BAKE_ORDER = sorted(SPECS, key=lambda s: s["csv_index"])
print("== every frame of all %d clips" % len(BAKE_ORDER))
nflag = 0
for sp in BAKE_ORDER:
    cid, n, gen = sp["id"], sp["n"], sp["gen"]
    chain_max = ik_max = 0.0
    floor_min = 1e9
    f_chain = f_ik = f_floor = 0
    for f in range(1, n + 1):
        rig.reset()
        Pp = gen(rig, f, n)
        M_pel = body_matrices(rig, Pp)[1]
        ride_props(rig, Pp, M_pel)
        apply_pose(rig, Pp)
        rig.apply()
        rig.post_pose(Pp)
        ch = chain_error(rig, gs=Pp["scale"])
        ik = ik_error(rig, Pp)
        mz = mesh_min_z()
        if ch > chain_max:
            chain_max, f_chain = ch, f
        if ik > ik_max:
            ik_max, f_ik = ik, f
        if mz < floor_min:
            floor_min, f_floor = mz, f
    flags = []
    if chain_max > 2e-4:
        flags.append("chain %.2e @%d" % (chain_max, f_chain))
    if ik_max > 1e-4:
        flags.append("ik %.2e @%d" % (ik_max, f_ik))
    if floor_min < -0.02:
        flags.append("floor_all %.4f @%d" % (floor_min, f_floor))
    if flags:
        nflag += 1
    print("   %-18s n=%3d chain=%.2e ik=%.2e floor_min=%+.4f @%d %s"
          % (cid, n, chain_max, ik_max, floor_min, f_floor,
             "FLAGS: " + "; ".join(flags) if flags else ""))
print("PROBE ALL DONE, clips flagged: %d" % nflag)

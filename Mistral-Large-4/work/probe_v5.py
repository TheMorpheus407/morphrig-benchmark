"""Probe v5: verify the clip 71-96 fixes at EVERY frame before the bake.

Section L: the 14 lying/getup clips (knockdown_*, prone_*, getup_*,
           sleep_*, death_*, dead_*, respawn) at every frame -- mesh min z
           vs the bake's floor thresholds (cap frames 1/n//2/n for floor_ok,
           every frame for floor_all_ok, frame n for the LYING floor_final
           band), chain and ik error at every frame (stricter than the
           bake's cap-frame sampling).
Section D: dialogue at the clause boundaries, the sweep clause and the cap
           frames -- chain/ik/floor (the crash site: CLAUSE_GAZE arity).
Section A: the nine aim grid poses (clips 88-96, never baked yet).

Run: blender -b --factory-startup --python work/probe_v5.py
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

LYING_CLIPS = {"knockdown_front", "knockdown_back", "prone_front",
               "prone_back", "getup_front", "getup_back", "sleep_start",
               "sleep_loop", "sleep_end", "death_front", "death_back",
               "dead_front", "dead_back", "respawn"}


def spec_of(cid):
    return next(s for s in SPECS if s["id"] == cid)


def run_clip(gen, f, n):
    Pp = gen(rig, f, n)
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    return Pp


print("== L: lying/getup clips, every frame")
LYING_ORDER = ["knockdown_front", "knockdown_back", "prone_front", "prone_back",
               "getup_front", "getup_back", "sleep_start", "sleep_loop",
               "sleep_end", "death_front", "death_back", "dead_front",
               "dead_back", "respawn"]
for cid in LYING_ORDER:
    sp = spec_of(cid)
    gen, n = sp["gen"], sp["n"]
    caps = (1, n // 2, n)
    floor_caps = 1e9
    floor_all = 1e9
    chain_max = 0.0
    ik_max = 0.0
    worst_f = {}
    for f in range(1, n + 1):
        rig.reset()
        Pp = run_clip(gen, f, n)
        mz = mesh_min_z()
        ch = chain_error(rig)
        ik = ik_error(rig, Pp)
        floor_all = min(floor_all, mz)
        if f in caps:
            floor_caps = min(floor_caps, mz)
        if ch > chain_max:
            chain_max, worst_f["chain"] = ch, f
        if ik > ik_max:
            ik_max, worst_f["ik"] = ik, f
        if mz < worst_f.get("floor", (1e9, 0))[0]:
            worst_f["floor"] = (mz, f)
    flags = []
    if not floor_caps > -0.005:
        flags.append("floor_ok(%.4f)" % floor_caps)
    if not floor_all > -0.02:
        flags.append("floor_all_ok(%.4f)" % floor_all)
    if cid in LYING_CLIPS:
        rig.reset()
        Pp = run_clip(gen, n, n)
        mz_n = mesh_min_z()
        if not (-0.005 < mz_n < 0.02):
            flags.append("floor_final(%.4f)" % mz_n)
    if chain_max > 2e-4:
        flags.append("chain(%.2e@%d)" % (chain_max, worst_f["chain"]))
    if ik_max > 1e-4:
        flags.append("ik(%.2e@%d)" % (ik_max, worst_f["ik"]))
    print("   %-15s n=%2d floor_caps=%+.4f floor_all=%+.4f (f=%d) "
          "chain=%.2e (f=%d) ik=%.2e (f=%d)  %s"
          % (cid, n, floor_caps, floor_all, worst_f["floor"][1],
             chain_max, worst_f["chain"], ik_max, worst_f["ik"],
             "FLAGS: " + ",".join(flags) if flags else "ok"))

print("== D: dialogue, sampled frames")
sp = spec_of("dialogue")
gen, n = sp["gen"], sp["n"]
frames = sorted(set([1, n // 2, n, 46, 47, 48, 104, 105, 106, 150, 196, 197,
                     198, 286, 287, 288, 352, 353, 354, 394, 395, 396]))
worst = {"chain": (0.0, 0), "ik": (0.0, 0), "floor": (1e9, 0)}
for f in frames:
    rig.reset()
    Pp = run_clip(gen, f, n)
    ch = chain_error(rig)
    ik = ik_error(rig, Pp)
    mz = mesh_min_z()
    if ch > worst["chain"][0]:
        worst["chain"] = (ch, f)
    if ik > worst["ik"][0]:
        worst["ik"] = (ik, f)
    if mz < worst["floor"][0]:
        worst["floor"] = (mz, f)
    print("   dialogue f=%3d chain=%.2e ik=%.2e floor=%+.4f"
          % (f, ch, ik, mz))
print("   dialogue worst: chain=%.2e (f=%d) ik=%.2e (f=%d) floor=%+.4f (f=%d)"
      % (worst["chain"][0], worst["chain"][1], worst["ik"][0],
         worst["ik"][1], worst["floor"][0], worst["floor"][1]))

print("== A: aim grid poses (clips 88-96)")
for sp in SPECS:
    if not sp["id"].startswith("aim_"):
        continue
    gen, n = sp["gen"], sp["n"]
    for f in (1, 2):
        rig.reset()
        Pp = run_clip(gen, f, n)
        print("   %-16s f=%d chain=%.2e ik=%.2e floor=%+.4f"
              % (sp["id"], f, chain_error(rig), ik_error(rig, Pp),
                 mesh_min_z()))

print("PROBE V5 DONE")

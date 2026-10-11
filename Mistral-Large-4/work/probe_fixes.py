"""Diagnostics for the gen_03 bake fixes (probe v2).

Section 0: rig constants for the melee_3 / reload v2 redesigns
           (shoulders, combat hands, aim frame, emitter vs the fixed seat,
            holster / pouch / support-grip / handoff / work-pin reaches,
            the reload fixed point, blade mounting).
Section A: verify the blink IK-scale fix (mesh floor + bone lengths at
           global_scale 1.0 / 0.51 / 0.02).
Section D: melee_3 v2 at EVERY frame -- L/R pin reaches vs the per-frame
           shoulders, chain/ik errors, both hands on the blade segment.
Section E: reload v2 at EVERY frame -- L target / R pin reaches, chain/ik,
           posed emitter vs the analytic _reload_emitter (must match
           exactly), cell contact exactness at every carrier, and the
           carrier-switch continuities.

Run: blender -b --factory-startup --python work/probe_fixes.py
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
ss = ns["ss"]
lerp = ns["lerp"]
combat_pose = ns["combat_pose"]
combat_hand_matrices = ns["combat_hand_matrices"]
build_aim = ns["build_aim"]
gen_blink_out = ns["gen_blink_out"]
gen_melee_3 = ns["gen_melee_3"]
gen_reload = ns["gen_reload"]
mesh_min_z = ns["mesh_min_z"]
ik_error = ns["ik_error"]
chain_error = ns["chain_error"]
LEG_L1 = ns["LEG_L1"]
LEG_L2 = ns["LEG_L2"]
PROP_OFF = ns["PROP_OFF"]
CELL_SEAT_WORLD = ns["CELL_SEAT_WORLD"]
CELL_SEAT_LOCAL = ns["CELL_SEAT_LOCAL"]
CELL_REST_WORLD = ns["CELL_REST_WORLD"]
SPENT_REST_WORLD = ns["SPENT_REST_WORLD"]
HOLSTER_GRIP = ns["HOLSTER_GRIP"]
CELL_GRIP_L = ns["CELL_GRIP_L"]
CELL_GRIP_R = ns["CELL_GRIP_R"]
M_h_pouch = ns["M_h_pouch"]
M_grip_L_support = ns["M_grip_L_support"]
M_h_rigid = ns["M_h_rigid"]
M_h_work = ns["M_h_work"]
M_h_L_handoff = ns["M_h_L_handoff"]
M_h_R_handoff = ns["M_h_R_handoff"]
CELL_HANDOFF = ns["CELL_HANDOFF"]
POUCH_HOVER = ns["POUCH_HOVER"]
_reload_emitter = ns["_reload_emitter"]
_sh_R0 = ns["_sh_R0"]
_M_fa_R0 = ns["_M_fa_R0"]
_INFO_AIM0 = ns["_INFO_AIM0"]
rig_ops = ns["rig_ops"]

ARM_LIM = {s: rig.arm_len[s] for s in ("L", "R")}
ARM_CAP = {s: rig.arm_len[s] - 1e-4 for s in ("L", "R")}


def T(M):
    return tuple(round(c, 4) for c in M.to_translation())


def V(v):
    return tuple(round(c, 4) for c in v)


def reach(p, sh):
    return (Vector(p) - Vector(sh)).length


def rot_err(A, B):
    return max(abs((A.to_3x3() @ B.to_3x3().inverted())[i][j]
                   - (1.0 if i == j else 0.0))
               for i in range(3) for j in range(3))


def mat_err(A, B):
    return max((A.to_translation() - B.to_translation()).length, rot_err(A, B))


def run_clip(gen, f, n):
    Pp = gen(rig, f, n)
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    return Pp


def prop_mesh_bbox_forearm(bone):
    """Rest bbox of the Operative-mesh verts weighted to a prop bone, in
    forearm_R local space (the blade/emitter are mounted on the forearm)."""
    mesh_obj = bpy.data.objects["Operative"]
    gi = {g.name: g.index for g in mesh_obj.vertex_groups}.get(bone)
    if gi is None:
        return None
    inv = rig.rest["forearm_R"].inverted()
    xs, ys, zs = [], [], []
    for v in mesh_obj.data.vertices:
        w = 0.0
        for g in v.groups:
            if g.group == gi:
                w = max(w, g.weight)
        if w > 0.5:
            p = inv @ v.co
            xs.append(p.x)
            ys.append(p.y)
            zs.append(p.z)
    if not xs:
        return None
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


print("== 0: constants")
print("   arm limit L=%.5f R=%.5f (L1 %.4f/%.4f, L2 %.4f/%.4f) leg L1=%.4f L2=%.4f"
      % (ARM_LIM["L"], ARM_LIM["R"], rig.arm_L1["L"], rig.arm_L1["R"],
         rig.arm_L2["L"], rig.arm_L2["R"], LEG_L1, LEG_L2))
Pp = combat_pose(rig, 0.905, 0.075)
M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
print("   combat sh_L=%s sh_R=%s" % (V(sh["L"]), V(sh["R"])))
_, _, M_h_c_L = combat_hand_matrices(rig, "L", sh["L"])
_, _, M_h_c_R = combat_hand_matrices(rig, "R", sh["R"])
print("   combat hand L=%s reachL=%.4f | R=%s reachR=%.4f"
      % (T(M_h_c_L), reach(M_h_c_L.to_translation(), sh["L"]),
         T(M_h_c_R), reach(M_h_c_R.to_translation(), sh["R"])))
print("   aim: elbow=%s wrist=%s emitter=%s" % (
    V(_M_fa_R0.to_translation()),
    V(_M_fa_R0 @ rig.rl["hand_R"].to_translation()),
    V(_INFO_AIM0["emitter"])))
print("   aim hand (M_h_rigid)=%s reachR=%.4f"
      % (T(M_h_rigid), reach(M_h_rigid.to_translation(), sh["R"])))
print("   rest emitter=%s" % (T(rig.rest["emitter"]),))
print("   seat CELL_SEAT_WORLD=%s  d_trans=%.4f"
      % (T(CELL_SEAT_WORLD),
         (CELL_SEAT_WORLD.to_translation()
          - rig.rest["emitter"].to_translation()).length))
rerr = rot_err(CELL_SEAT_WORLD, rig.rest["emitter"])
print("   seat vs rest-emitter rotation err=%.4f" % rerr)
print("   holster CELL_REST_WORLD=%s reachL=%.4f reachR=%.4f"
      % (T(CELL_REST_WORLD), reach(CELL_REST_WORLD.to_translation(), sh["L"]),
         reach(CELL_REST_WORLD.to_translation(), sh["R"])))
print("   pouch  SPENT_REST_WORLD=%s reachL=%.4f reachR=%.4f"
      % (T(SPENT_REST_WORLD), reach(SPENT_REST_WORLD.to_translation(), sh["L"]),
         reach(SPENT_REST_WORLD.to_translation(), sh["R"])))
print("   HOLSTER_GRIP=%s reachL=%.4f" % (T(HOLSTER_GRIP),
                                         reach(HOLSTER_GRIP.to_translation(),
                                               sh["L"])))
print("   support grip=%s reachL=%.4f" % (T(M_grip_L_support),
                                           reach(M_grip_L_support.to_translation(),
                                                 sh["L"])))
print("   handoff CELL_HANDOFF=%s" % (T(CELL_HANDOFF),))
print("   M_h_L_handoff=%s reachL=%.4f" % (T(M_h_L_handoff),
                                           reach(M_h_L_handoff.to_translation(),
                                                 sh["L"])))
print("   M_h_R_handoff=%s reachR=%.4f" % (T(M_h_R_handoff),
                                           reach(M_h_R_handoff.to_translation(),
                                                 sh["R"])))
M_h_seat_R = CELL_SEAT_WORLD @ CELL_GRIP_R
print("   M_h_seat(R)=%s reachR=%.4f" % (T(M_h_seat_R),
                                         reach(M_h_seat_R.to_translation(),
                                               sh["R"])))
print("   M_h_pouch=%s reachR=%.4f" % (T(M_h_pouch),
                                      reach(M_h_pouch.to_translation(),
                                            sh["R"])))
print("   M_h_work (work pin)=%s reachR=%.4f"
      % (T(M_h_work), reach(M_h_work.to_translation(), sh["R"])))
print("   rl[hand_R] trans=%s (L2=%.4f)  rl[emitter] trans=%s"
      % (V(rig.rl["hand_R"].to_translation()), rig.arm_L2["R"],
         V(rig.rl["emitter"].to_translation())))
print("   CELL_GRIP_R trans=%s" % (V(CELL_GRIP_R.to_translation()),))
_seated = _reload_emitter(_sh_R0, M_h_work) @ CELL_SEAT_LOCAL
_grip_w = _seated @ CELL_GRIP_R
print("   work-pin grip residual: d_tr=%.3e d_rot=%.3e"
      % ((_grip_w.to_translation() - M_h_work.to_translation()).length,
         rot_err(_grip_w, M_h_work)))
_rb = rig.rl["forearm_R"].inverted() @ rig.rl["blade"]
print("   blade: blen=%.4f rl_trans=%s mount_trans(forearm frame)=%s "
      "mount_rot_err=%.4f"
      % (rig.blen["blade"], V(rig.rl["blade"].to_translation()),
         V(_rb.to_translation()), rot_err(_rb, Matrix.Identity(4))))
for _bn in ("blade", "emitter"):
    _bb = prop_mesh_bbox_forearm(_bn)
    print("   %s mesh forearm-local bbox: min=%s max=%s"
          % (_bn, tuple(round(c, 4) for c in _bb[0]),
             tuple(round(c, 4) for c in _bb[1])))

# emitter posed position for a pinned R hand (same solve build_arm does)
E0 = sh["R"] + (rig.rest["forearm_R"].to_translation()
                 - rig.rest["upper_arm_R"].to_translation())
W0 = sh["R"] + (rig.rest["hand_R"].to_translation()
                - rig.rest["upper_arm_R"].to_translation())
pole_aim = _M_fa_R0.to_translation()


def emitter_at_pin(pin_M):
    E_new, T_new = rig_ops.solve_2bone_ik(sh["R"], E0, W0,
                                           pin_M.to_translation(), pole_aim)
    M_fa = rig_ops.dir_pose_matrix(rig.rest["forearm_R"], T_new - E_new, E_new)
    return (M_fa @ rig.rl["emitter"]).to_translation(), M_fa


for tag, pin in (("aim", M_h_rigid), ("seat_R", M_h_seat_R),
                 ("pouch", M_h_pouch), ("work", M_h_work)):
    em, M_fa = emitter_at_pin(pin)
    print("   pin %-6s -> emitter=%s  |em-seat|=%.4f  wrist=%s chainL1=%.4f"
          % (tag, V(em), (em - CELL_SEAT_WORLD.to_translation()).length,
             V(M_fa @ rig.rl["hand_R"].to_translation()),
             (M_fa.to_translation() - sh["R"]).length))

print("== A: blink floor after the IK-scale fix")
for f in (1, 6, 12):
    Pp = gen_blink_out(rig, f, 12)
    gs = Pp["scale"]
    M_pel = body_matrices(rig, Pp)[1]
    ride_props(rig, Pp, M_pel)
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    th = rig.def_m["thigh_L"].to_3x3().col[1].length
    shn = rig.def_m["shin_L"].to_3x3().col[1].length
    ua = rig.def_m["upper_arm_L"].to_3x3().col[1].length
    fa = rig.def_m["forearm_L"].to_3x3().col[1].length
    print("   f=%2d gs=%.3f minz=%.5f chain=%.2e ik=%.2e thigh_y=%.5f "
          "(want %.5f) shin_y=%.5f (want %.5f) ua_y=%.5f fa_y=%.5f"
          % (f, gs, mesh_min_z(), chain_error(rig, gs), ik_error(rig, Pp),
             th, LEG_L1 * gs, shn, LEG_L2 * gs, ua, fa))

print("== D: melee_3 v2, per frame (pin reaches, chain, ik, forearm grip)")
worst = {"rL": 0.0, "rR": 0.0, "chain": 0.0, "ik": 0.0,
         "uL_min": 9.0, "uL_max": 0.0, "latL": 0.0, "uR_err": 0.0}
bad = []
for f in range(1, 34):
    Pp = run_clip(gen_melee_3, f, 33)
    shf = body_matrices(rig, Pp)[4]
    pinL = Pp["arms"]["L"]["hand"].to_translation()
    pinR = Pp["arms"]["R"]["hand"].to_translation()
    rL = (pinL - shf["L"]).length
    rR = (pinR - shf["R"]).length
    ch = chain_error(rig, 1.0)
    ik = ik_error(rig, Pp)
    # hand heads in the R forearm's local space: the R hand rides the wrist
    # (y = L2, on the axis); the L hand grips the forearm near the blade
    # (0.10 <= y <= 0.28, on the axis -- never past the wrist).
    fa_inv = rig.def_m["forearm_R"].inverted()
    hL_l = fa_inv @ rig.def_m["hand_L"].to_translation()
    hR_l = fa_inv @ rig.def_m["hand_R"].to_translation()
    latL = math.hypot(hL_l.x, hL_l.z)
    latR = math.hypot(hR_l.x, hR_l.z)
    uR_err = abs(hR_l.y - rig.arm_L2["R"])
    worst["rL"] = max(worst["rL"], rL)
    worst["rR"] = max(worst["rR"], rR)
    worst["chain"] = max(worst["chain"], ch)
    worst["ik"] = max(worst["ik"], ik)
    if 12 <= f <= 23:
        worst["uL_min"] = min(worst["uL_min"], hL_l.y)
        worst["uL_max"] = max(worst["uL_max"], hL_l.y)
    worst["latL"] = max(worst["latL"], latL)
    worst["uR_err"] = max(worst["uR_err"], uR_err)
    # the L grip on the R forearm is only expected during the grip phase
    offL = 12 <= f <= 23 and (hL_l.y < 0.10 or hL_l.y > 0.28 or latL > 0.02)
    offR = uR_err > 0.01 or latR > 0.02
    if (rL > ARM_CAP["L"] - 1e-4 or rR > ARM_CAP["R"] - 1e-4
            or ch > 2e-4 or ik > 1e-4 or offL or offR):
        bad.append(f)
    if f in (1, 6, 12, 13, 16, 18, 23, 28, 33) or bad and f == bad[-1]:
        print("   f=%2d reachL=%.4f reachR=%.4f chain=%.2e ik=%.2e | forearm-"
              "local L(y=%.3f lat=%.4f palm_y=%.3f) R(y=%.4f lat=%.4f)%s"
              % (f, rL, rR, ch, ik, hL_l.y, latL, hL_l.y + 0.06, hR_l.y,
                 latR, "  <-- CHECK" if f in bad else ""))
print("   worst: reachL=%.4f reachR=%.4f (cap %.5f) chain=%.2e ik=%.2e | "
      "L grip y in [%.3f, %.3f] (want [0.10, 0.28]), latL=%.4f, "
      "R wrist y err=%.4f" % (worst["rL"], worst["rR"], ARM_CAP["L"],
                              worst["chain"], worst["ik"], worst["uL_min"],
                              worst["uL_max"], worst["latL"],
                              worst["uR_err"]))
print("   frames flagged: %s" % (bad if bad else "none"))

print("== E: reload v2, per frame (reaches, chain, ik, emitter, contacts)")
G_L = CELL_GRIP_L.inverted()
G_R = CELL_GRIP_R.inverted()
worst = {"rL": 0.0, "rR": 0.0, "chain": 0.0, "ik": 0.0, "em": 0.0,
         "contact": 0.0}
bad = []
prev_cells = {}
for f in range(1, 61):
    Pp = run_clip(gen_reload, f, 60)
    shf = body_matrices(rig, Pp)[4]
    tgtL = Vector(Pp["arms"]["L"]["target"])
    rL = (tgtL - shf["L"]).length
    pinR = Pp["arms"]["R"]["hand"]
    rR = (pinR.to_translation() - shf["R"]).length
    ch = chain_error(rig, 1.0)
    ik = ik_error(rig, Pp)
    M_em_an = _reload_emitter(shf["R"], pinR)
    em_err = mat_err(rig.def_m["emitter"], M_em_an)
    hL = rig.def_m["hand_L"]
    hR = rig.def_m["hand_R"]
    em = rig.def_m["emitter"]
    c_new = rig.def_m["cell_new"]
    c_spent = rig.def_m["cell_spent"]
    if f <= 19:
        exp_new = CELL_REST_WORLD
    elif f <= 37:
        exp_new = hL @ G_L
    elif f <= 45:
        exp_new = hR @ G_R
    else:
        exp_new = em @ CELL_SEAT_LOCAL
    if f <= 23:
        exp_spent = em @ CELL_SEAT_LOCAL
    elif f <= 29:
        exp_spent = hR @ G_R
    elif f == 30:
        exp_spent = M_h_pouch @ G_R
    elif f == 33:
        exp_spent = SPENT_REST_WORLD
    elif f >= 34:
        exp_spent = SPENT_REST_WORLD
    else:
        exp_spent = None  # lerp interior: no exact expectation
    c_err = mat_err(c_new, exp_new)
    if exp_spent is not None:
        c_err = max(c_err, mat_err(c_spent, exp_spent))
    # the work-pin grip: hand at M_h_work must grip the seated cell exactly
    if 15 <= f <= 23 or f in (45, 46):
        grip = (em @ CELL_SEAT_LOCAL) @ CELL_GRIP_R
        c_err = max(c_err, mat_err(hR, grip))
    # handoff: the cell sits at the handoff frame while the L hand holds it
    # (27-38); both hands grip it exactly at f=38
    if 27 <= f <= 38:
        c_err = max(c_err, mat_err(c_new, CELL_HANDOFF))
    if f == 38:
        c_err = max(c_err, mat_err(hL @ G_L, hR @ G_R))
    # holster hold: L hand at the holster grip, cell at rest
    if 15 <= f <= 19:
        c_err = max(c_err, mat_err(hL, HOLSTER_GRIP))
    worst["rL"] = max(worst["rL"], rL)
    worst["rR"] = max(worst["rR"], rR)
    worst["chain"] = max(worst["chain"], ch)
    worst["ik"] = max(worst["ik"], ik)
    worst["em"] = max(worst["em"], em_err)
    worst["contact"] = max(worst["contact"], c_err)
    flag = (rL > ARM_CAP["L"] - 1e-4 or rR > ARM_CAP["R"] - 1e-4
            or ch > 2e-4 or ik > 1e-4 or em_err > 1e-5 or c_err > 1e-5)
    if flag:
        bad.append(f)
    if f in (1, 8, 9, 14, 15, 19, 20, 23, 24, 26, 27, 30, 31, 33, 34, 37, 38,
              39, 45, 46, 55, 56, 57, 60) or flag:
        d_new = (c_new.to_translation()
                 - prev_cells["new"]).length if "new" in prev_cells else 0.0
        d_spent = (c_spent.to_translation()
                   - prev_cells["spent"]).length if "spent" in prev_cells else 0.0
        print("   f=%2d rL=%.4f rR=%.4f chain=%.1e ik=%.1e em=%.1e "
              "contact=%.1e | d_cell_new=%.4f d_cell_spent=%.4f%s"
              % (f, rL, rR, ch, ik, em_err, c_err, d_new, d_spent,
                 "  <-- CHECK" if flag else ""))
    prev_cells = {"new": c_new.to_translation(),
                  "spent": c_spent.to_translation()}
    if f == 1:
        entry = (T(hR), T(M_h_rigid), T(hL), T(M_grip_L_support))
    if f == 60:
        exitp = (T(hR), T(M_h_rigid), T(hL), T(M_grip_L_support))
print("   worst: rL=%.4f rR=%.4f (cap %.5f) chain=%.2e ik=%.2e em=%.2e "
      "contact=%.2e" % (worst["rL"], worst["rR"], ARM_CAP["L"],
                        worst["chain"], worst["ik"], worst["em"],
                        worst["contact"]))
print("   frames flagged: %s" % (bad if bad else "none"))
print("   entry f=1:  hand_R=%s (M_h_rigid %s) hand_L=%s (support %s)"
      % entry)
print("   exit  f=60: hand_R=%s (M_h_rigid %s) hand_L=%s (support %s)"
      % exitp)
print("PROBE V2 DONE")

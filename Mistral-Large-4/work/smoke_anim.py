"""Smoke test for source/generators/anim_lib.py against source/Operative_rig.blend.

Run:  blender -b --factory-startup --python work/smoke_anim.py

  A  combat pose exactness (body chain, FK arms, IK legs, toe, prop bones)
  B  gait frames (foot-at-target, chain lengths, knee direction, treadmill
     speed, swing lift, loop seam) for walk/run/sprint x 4 directions
  C  wrist-emitter aim (firing direction, chain closure, support hand)
  D  keying round-trip (actions + markers + frame_set evaluation)
  E  preview renders (combat / walk / aim) with ASCII display
"""
import sys, os, math, time

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, gait_frame, combat_pose,
                      relaxed_pose, stance_legs, aim_arm_params, support_hand_params,
                      aim_forearm_matrix, dir_of, most_down_perp, gait_markers,
                      DEFORM_BONES, SHAPE_KEYS, GAIT, DIR_ALPHA, ANKLE_Z, THIGH_DROP)

TWO_PI = 2.0 * math.pi
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))


def mat_err(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))


def params_close(a, b, tol=1e-9):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a.keys()) == set(b.keys()) and all(params_close(a[k], b[k], tol) for k in a)
    if isinstance(a, Matrix) and isinstance(b, Matrix):
        return mat_err(a, b) < tol
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < tol
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b):
        return all(params_close(x, y, tol) for x, y in zip(a, b))
    return a == b


rig = Rig()

print("== rig facts")
print("bones=%d  DEFORM_BONES matches: %s" % (len(rig.pbs), set(DEFORM_BONES) == set(rig.pbs.keys())))
order_ok = True
seen = set()
for name in DEFORM_BONES:
    parent = rig.pbs[name].bone.parent
    if parent is not None and parent.name not in seen:
        order_ok = False
    seen.add(name)
check("A DEFORM_BONES hierarchy order", order_ok)
print("leg_len=%.4f  arm L1 L/R=%.4f/%.4f  L2 L/R=%.4f/%.4f" % (
    rig.leg_len, rig.arm_L1["L"], rig.arm_L1["R"], rig.arm_L2["L"], rig.arm_L2["R"]))
print("FIRE_LOCAL=%s  |dot with forearm +Y|=%.2e" % (
    tuple(round(c, 5) for c in rig.FIRE_LOCAL),
    abs(rig.FIRE_LOCAL.dot(Vector((0.0, 1.0, 0.0))))))
print("rl(emitter).t=%s" % (tuple(round(c, 5) for c in rig.rl["emitter"].to_translation()),))
print("rl(hand_R).t=%s  hand len=%.4f" % (
    tuple(round(c, 5) for c in rig.rl["hand_R"].to_translation()), rig.blen["hand_R"]))
for s, g in GAIT.items():
    print("gait %-6s n=%2d stance=%.2f E=%.2f v_app=%.2f z_hi=%.4f" %
          (s, g["n"], g["stance"], g["E"], g["v_app"], g["z_hi"]))
print("objects:", sorted(o.name for o in bpy.data.objects))

def seg(a, b):
    return (rig.rest[b].to_translation() - rig.rest[a].to_translation()).length


SEG_THIGH = {s: seg("thigh_%s" % s, "shin_%s" % s) for s in ("L", "R")}
SEG_SHIN = {s: seg("shin_%s" % s, "foot_%s" % s) for s in ("L", "R")}

# ---------------------------------------------------------------- A: combat pose
print("== A: combat pose exactness")
Pp = combat_pose(rig, pelvis_z=0.905, spread=0.075)
apply_pose(rig, Pp)
rig.apply()
rig.post_pose(Pp)
M_root, M_pel, M_chest, M_spine03, shoulders = body_matrices(rig, Pp)
check("A root == authored", mat_err(rig.def_m["root"], M_root) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["root"], M_root))
check("A pelvis == authored", mat_err(rig.def_m["pelvis"], M_pel) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["pelvis"], M_pel))
check("A spine_01 rigid follow", mat_err(rig.def_m["spine_01"], M_pel @ rig.rl["spine_01"]) < 1e-5)
check("A spine_02 == ctrl_chest target", mat_err(rig.def_m["spine_02"], M_chest) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["spine_02"], M_chest))
check("A spine_03 rigid follow", mat_err(rig.def_m["spine_03"], M_chest @ rig.rl["spine_03"]) < 1e-5)
M_head_rigid = (M_chest @ rig.rl["spine_03"] @ rig.rl["neck_01"]
                @ rig.rl["neck_02"] @ rig.rl["head"])
check("A head rigid at look=0", mat_err(rig.def_m["head"], M_head_rigid) < 1e-5,
      "err=%.2e" % mat_err(rig.def_m["head"], M_head_rigid))
for side in ("L", "R"):
    M_clav = M_spine03 @ rig.rl["clavicle_%s" % side]
    am = rig.arm_m[side]
    check("A clavicle_%s" % side, mat_err(rig.def_m["clavicle_%s" % side], M_clav) < 1e-5,
          "err=%.2e" % mat_err(rig.def_m["clavicle_%s" % side], M_clav))
    check("A upper_arm_%s" % side, mat_err(rig.def_m["upper_arm_%s" % side], am["ua"]) < 1e-5)
    check("A forearm_%s" % side, mat_err(rig.def_m["forearm_%s" % side], am["fa"]) < 1e-5)
    check("A hand_%s" % side, mat_err(rig.def_m["hand_%s" % side], am["hand"]) < 1e-5)
    leg = Pp["legs"][side]
    ankle = Vector(leg["ankle"])
    ferr = (rig.def_m["foot_%s" % side].to_translation() - ankle).length
    check("A foot_%s at IK target" % side, ferr < 1e-4, "err=%.2e" % ferr)
    hip = (M_pel @ rig.rl["thigh_%s" % side]).to_translation()
    knee = rig.def_m["shin_%s" % side].to_translation()
    l1 = (knee - hip).length
    l2 = (ankle - knee).length
    check("A leg_%s chain lengths" % side,
          abs(l1 - SEG_THIGH[side]) < 1e-4 and abs(l2 - SEG_SHIN[side]) < 1e-4,
          "l1=%.4f (%.4f)  l2=%.4f (%.4f)" % (l1, SEG_THIGH[side], l2, SEG_SHIN[side]))
    tc = float(leg["toe"]) * math.radians(55.0)
    M_toe_exp = rig.def_m["foot_%s" % side] @ rig.rl["toe_%s" % side] @ Matrix.Rotation(tc, 4, 'X')
    check("A toe_%s curl" % side, mat_err(rig.def_m["toe_%s" % side], M_toe_exp) < 1e-5)
check("A emitter follows forearm_R",
      mat_err(rig.def_m["emitter"], rig.def_m["forearm_R"] @ rig.rl["emitter"]) < 1e-5)
check("A blade follows forearm_R",
      mat_err(rig.def_m["blade"], rig.def_m["forearm_R"] @ rig.rl["blade"]) < 1e-5)
for prop in ("cell_new", "cell_spent", "beacon"):
    check("A %s follows root" % prop,
          mat_err(rig.def_m[prop], rig.def_m["root"] @ rig.rl[prop]) < 1e-5)
check("A FIRE_LOCAL unit + rest firing ~forward",
      abs(rig.FIRE_LOCAL.length - 1.0) < 1e-6
      and math.degrees((rig.rest["forearm_R"].to_3x3() @ rig.FIRE_LOCAL).normalized()
                       .angle(Vector((0.0, -1.0, 0.0)))) < 5.0,
      "|FIRE_LOCAL|=%.6f  angle to -Y at rest=%.2f deg"
      % (rig.FIRE_LOCAL.length,
         math.degrees((rig.rest["forearm_R"].to_3x3() @ rig.FIRE_LOCAL).normalized()
                      .angle(Vector((0.0, -1.0, 0.0))))))

# ---------------------------------------------------------------- B: gait
print("== B: gait frames")
t0 = time.time()
for speed in ("walk", "run", "sprint"):
    g = GAIT[speed]
    n = g["n"]
    s2pi = TWO_PI * g["stance"]
    for alpha_name in ("f", "r", "b", "l"):
        alpha = DIR_ALPHA[alpha_name]
        u = dir_of(alpha, 0.0)
        max_ferr = 0.0
        min_knee_fwd = 1e9
        max_swing_lift = 0.0
        pz_lo, pz_hi = 1e9, -1e9
        for f in range(1, n + 1):
            Pp = gait_frame(rig, speed, alpha, f)
            apply_pose(rig, Pp)
            rig.apply()
            M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
            pz_lo = min(pz_lo, Pp["pelvis"]["z"])
            pz_hi = max(pz_hi, Pp["pelvis"]["z"])
            for side in ("L", "R"):
                leg = Pp["legs"][side]
                ankle = Vector(leg["ankle"])
                ferr = (rig.def_m["foot_%s" % side].to_translation() - ankle).length
                max_ferr = max(max_ferr, ferr)
                hip = (M_pel @ rig.rl["thigh_%s" % side]).to_translation()
                knee = rig.def_m["shin_%s" % side].to_translation()
                l1 = (knee - hip).length
                l2 = (ankle - knee).length
                if abs(l1 - SEG_THIGH[side]) > 2e-4 or abs(l2 - SEG_SHIN[side]) > 2e-4:
                    check("B %s_%s leg_%s chain f%d" % (speed, alpha_name, side, f), False,
                          "l1=%.4f (%.4f) l2=%.4f (%.4f)" % (l1, SEG_THIGH[side], l2, SEG_SHIN[side]))
                kf = (knee - hip).dot(u)
                min_knee_fwd = min(min_knee_fwd, kf)
                ph = (TWO_PI * (f - 1) / n + (0.0 if side == "L" else math.pi)) % TWO_PI
                if ph >= s2pi:  # swing: measure lift
                    max_swing_lift = max(max_swing_lift, ankle.z - ANKLE_Z)
        check("B %s_%-1s foot-at-target" % (speed, alpha_name), max_ferr < 1e-4,
              "max err=%.2e  pz=[%.4f, %.4f]  swing lift=%.3f (want ~%.3f)"
              % (max_ferr, pz_lo, pz_hi, max_swing_lift, g["lift"]))
        check("B %s_%-1s knee never behind hip" % (speed, alpha_name), min_knee_fwd < 0.02,
              "min knee-fwd=%.4f" % min_knee_fwd)
    p1 = gait_frame(rig, speed, 0.0, 1)
    p2 = gait_frame(rig, speed, 0.0, n + 1)
    check("B %s loop seam (params f=1 == f=n+1)" % speed, params_close(p1, p2, 1e-9))
    mk = gait_markers(speed, 0.0)
    check("B %s markers" % speed,
          len(mk) == 4 and all(1 <= fr <= n for _, fr, _ in mk),
          str([(nm, fr) for nm, fr, _ in mk]))
print("   gait sweep: %.1f s for %d applies" % (time.time() - t0, 3 * 4 * sum(g["n"] for g in GAIT.values())))

# ---------------------------------------------------------------- C: aim
print("== C: wrist-emitter aim")


def build_aim_pose(yaw, pitch):
    Pp = combat_pose(rig, pelvis_z=0.905, spread=0.075)
    M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
    d = dir_of(yaw, pitch)
    R = aim_forearm_matrix(rig, yaw, pitch)
    # proper rotation?
    det = R.to_3x3().determinant()
    ortho = max(abs(R.col[i].length - 1.0) for i in range(3))
    check("C aim_forearm proper rotation (yaw=%g pitch=%g)" % (yaw, pitch),
          abs(det - 1.0) < 1e-5 and ortho < 1e-5, "det=%.6f ortho=%.2e" % (det, ortho))
    # emitter sits at elbow + R @ rl(emitter).t; aim the upper arm so the
    # emitter lands in front of the chest along d
    em_off = R @ rig.rl["emitter"].to_translation()
    muzzle = M_chest.to_translation() + d * 0.42
    elbow_dir = muzzle - em_off - sh["R"]
    armR = aim_arm_params(rig, "R", sh["R"], yaw, pitch, elbow_dir)
    Pp["arms"]["R"] = armR
    M_fa_R = armR["forearm"]
    grip_pt = M_fa_R @ Vector((0.0, 0.27, 0.0))
    grip_M = Matrix.Translation(grip_pt) @ M_fa_R.to_3x3().to_4x4()
    armL = support_hand_params(rig, grip_M, curl=0.3)
    armL["pole"] = tuple(sh["L"] + Vector((-0.15, -0.05, -0.45)))
    Pp["arms"]["L"] = armL
    return Pp, d, sh, grip_pt, M_fa_R


Pp_aim, d_aim, sh_aim, grip_aim, M_fa_aim = build_aim_pose(30.0, 10.0)
apply_pose(rig, Pp_aim)
rig.apply()
rig.post_pose(Pp_aim)
fire = (rig.def_m["emitter"].to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
ferr = (fire - d_aim).length
check("C emitter fires along aim dir", ferr < 1e-5, "err=%.2e  fire=%s d=%s" %
      (ferr, tuple(round(c, 4) for c in fire), tuple(round(c, 4) for c in d_aim)))
elbow_actual = rig.def_m["forearm_R"].to_translation()
e1 = abs((elbow_actual - sh_aim["R"]).length - rig.arm_L1["R"])
check("C elbow at L1 from shoulder", e1 < 1e-5, "err=%.2e" % e1)
wrist_exp = M_fa_aim @ rig.rl["hand_R"].to_translation()
we = (rig.def_m["hand_R"].to_translation() - wrist_exp).length
check("C wrist rigid on forearm", we < 1e-5, "err=%.2e" % we)
fa_axis = (rig.def_m["forearm_R"].to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
perp = abs(fa_axis.dot(d_aim))
check("C forearm axis ~perp to aim (mounting tolerance)", perp < 0.035, "dot=%.4f" % perp)
le = (rig.def_m["hand_L"].to_translation() - grip_aim).length
check("C support hand at grip", le < 1e-4, "err=%.2e" % le)
ge = abs((grip_aim - elbow_actual).length - 0.27)
check("C grip on forearm 0.27 from elbow", ge < 1e-4, "err=%.2e" % ge)
em_pos = rig.def_m["emitter"].to_translation()
print("   shoulder_R=%s elbow=%s emitter=%s" % (
    tuple(round(c, 3) for c in sh_aim["R"]),
    tuple(round(c, 3) for c in elbow_actual),
    tuple(round(c, 3) for c in em_pos)))
# firing direction independent of elbow choice
Pp_aim2, d2, sh2, grip2, _ = build_aim_pose(30.0, 10.0)
Pp_aim2["arms"]["R"] = aim_arm_params(rig, "R", sh2["R"], 30.0, 10.0,
                                      Vector((0.1, -0.5, -0.8)))
apply_pose(rig, Pp_aim2)
rig.apply()
fire2 = (rig.def_m["emitter"].to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
check("C firing dir independent of elbow", (fire2 - d2).length < 1e-5,
      "err=%.2e" % (fire2 - d2).length)

# ---------------------------------------------------------------- D: keying
print("== D: keying round-trip")
rig.reset()
n = 5
clip = "smoke_test"
rig.begin_clip(clip, n)
captured = {}
t0 = time.time()
for f in range(1, n + 1):
    Pp = combat_pose(rig, pelvis_z=0.905 + 0.01 * f)
    Pp["face"]["lip_close"] = 0.05 * f
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    rig.key(f)
    captured[f] = {name: rig.def_m[name].copy() for name in
                   ("root", "pelvis", "spine_02", "head", "clavicle_L", "upper_arm_L",
                    "forearm_L", "hand_L", "thigh_L", "shin_L", "foot_L", "toe_L",
                    "forearm_R", "emitter", "cell_new")}
    captured[f]["lip"] = rig.sk.key_blocks["lip_close"].value
t_key = (time.time() - t0) / n
rig.end_clip(n, [("test_marker", 3, "smoke")], loop=False)
act = bpy.data.actions.get(clip)
fact = bpy.data.actions.get(clip + "_face")
check("D actions exist", act is not None and fact is not None)
check("D unassigned after end_clip",
      rig.A.animation_data.action is None and rig.sk.animation_data.action is None)
check("D fake user", bool(act.use_fake_user) and bool(fact.use_fake_user))
check("D marker", any(m.name == "test_marker" and m.frame == 3 for m in act.pose_markers))
fcs = act.layers[0].strips[0].channelbags[0].fcurves
check("D fcurve count == 79*9", len(fcs) == 79 * 9, "got %d" % len(fcs))
ffcs = fact.layers[0].strips[0].channelbags[0].fcurves
check("D face fcurves == 10", len(ffcs) == len(SHAPE_KEYS), "got %d" % len(ffcs))
rig.A.animation_data.action = act
rig.sk.animation_data.action = fact
worst = 0.0
for f in (1, 3, 5):
    bpy.context.scene.frame_set(f)
    for name, M in captured[f].items():
        if name == "lip":
            worst = max(worst, abs(rig.sk.key_blocks["lip_close"].value - M))
        else:
            worst = max(worst, mat_err(rig.pbs[name].matrix, M))
check("D round-trip evaluation", worst < 1e-4, "worst err=%.2e (%.1f ms/frame)" % (worst, 1000 * t_key))
rig.A.animation_data.action = None
rig.sk.animation_data.action = None
for a in (act, fact):
    if a is not None:
        bpy.data.actions.remove(a)
rig_ops.reset_pose()

# ---------------------------------------------------------------- E: renders
print("== E: preview renders")
scene = bpy.context.scene
keep = {"Armature", "Operative", "Operative_Controls"}
for o in list(bpy.data.objects):
    if o.name not in keep:
        bpy.data.objects.remove(o)
for c in list(bpy.data.cameras):
    bpy.data.cameras.remove(c)
for l in list(bpy.data.lights):
    bpy.data.lights.remove(l)
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = False
world.color = (0.08, 0.08, 0.11)


def add_camera(name, loc, target, lens=50.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cam = bpy.data.objects.new(name, cd)
    scene.collection.objects.link(cam)
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return cam


def add_sun(name, energy, euler):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = energy
    o = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(o)
    o.rotation_euler = euler
    return o


def add_area(name, loc, energy, size=2.0):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.shape = 'DISK'
    ld.size = size
    o = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(o)
    o.location = loc
    d = Vector((0.0, 0.0, 1.0)) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return o


scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.cycles.use_denoising = False
scene.render.resolution_x = 800
scene.render.resolution_y = 450
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'

OUT = os.path.join(TASK, "work", "preview")
os.makedirs(OUT, exist_ok=True)


def head_top_z():
    dg = bpy.context.evaluated_depsgraph_get()
    me = rig.M.evaluated_get(dg)
    mm = me.to_mesh()
    z = max(v.co.z for v in mm.vertices)
    me.to_mesh_clear()
    return z


rig_ops.reset_pose()
rig.apply()
z_rest = head_top_z()
Pp_combat = combat_pose(rig, pelvis_z=0.905, spread=0.075)
apply_pose(rig, Pp_combat)
rig.apply()
rig.post_pose(Pp_combat)
z_combat = head_top_z()
check("E skinning: head top follows pose", abs(z_combat - z_rest) > 0.005,
      "rest=%.4f combat=%.4f" % (z_rest, z_combat))

cam_side = add_camera("cam_side", (2.6, -2.6, 1.35), (0.0, 0.0, 0.92))
cam_front = add_camera("cam_front", (0.0, -3.0, 1.15), (0.0, 0.0, 0.95))
add_sun("sun", 3.0, (math.radians(55.0), 0.0, math.radians(30.0)))
add_area("fill", (2.5, -1.0, 2.5), 150.0, 2.0)


def render_pose(name, Pp, cams):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)
    for cam, suffix in cams:
        scene.camera = cam
        path = os.path.join(OUT, "smoke_%s_%s.png" % (name, suffix))
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print("   rendered %s (%d bytes)" % (path, os.path.getsize(path)))


Pp_walk = gait_frame(rig, "walk", 0.0, 8)
render_pose("combat", Pp_combat, [(cam_side, "side"), (cam_front, "front")])
render_pose("walk", Pp_walk, [(cam_side, "side")])
render_pose("aim", Pp_aim, [(cam_front, "front"), (cam_side, "side")])

# ASCII display of the renders
import numpy as np
CH = " .:-=+*#%@"
for name in ("combat_side", "combat_front", "walk_side", "aim_front", "aim_side"):
    path = os.path.join(OUT, "smoke_%s.png" % name)
    if not os.path.exists(path):
        continue
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
    lum = (0.2126 * px[:, :, 0] + 0.7152 * px[:, :, 1] + 0.0722 * px[:, :, 2]) * px[:, :, 3]
    h, w = img.size[1], 100
    nh = max(1, int(h * (w / img.size[0]) * 0.5))
    ys = np.linspace(0, h - 1, nh).astype(int)
    xs = np.linspace(0, img.size[0] - 1, w).astype(int)
    small = lum[np.ix_(ys, xs)]
    lo, hi = np.percentile(small, 5), np.percentile(small, 98)
    norm = np.clip((small - lo) / max(hi - lo, 1e-6), 0, 1)
    print("== %s" % name)
    for row in norm:
        print("".join(CH[min(9, int(v * 9.999))] for v in row))
    bpy.data.images.remove(img)
    print()

print("== summary: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
print("SMOKE OK")

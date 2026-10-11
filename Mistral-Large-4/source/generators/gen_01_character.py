"""MorphRig generator stage 1: build the Operative character (mesh, face parts, props,
materials, procedural textures). Saves source/Operative.blend (rig is stage 2).

Character: original adult humanoid cyberpunk 'Operative', 1.80 m tall, faces -Y, Z up,
right = +X. Right forearm is cybernetic (wrist emitter + retractable forearm blade);
left arm organic. Props: removable power cell + hip holster (left hip), deployable
beacon (backpack), cable (secondary motion), armor plates, straps, headset.

Everything is one mesh object ("Operative") with 8 material slots so the exported
FBX yields a single UE skeletal mesh with <= 8 material slots.
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from morphrig_lib import *  # noqa

ROOT = os.path.dirname(HERE)                           # <task>/source
TEXDIR = os.path.join(ROOT, "textures")
BLEND = os.path.join(ROOT, "Operative.blend")
TASK = os.path.dirname(ROOT)
WORK = os.path.join(TASK, "work")
os.makedirs(TEXDIR, exist_ok=True)
os.makedirs(WORK, exist_ok=True)

sc = reset_scene()

# ===================================================================== UV islands
ISLANDS = {m: [] for m in range(8)}
ISLAND_GRID = {}

def register_island(mat, island_id, cols, rows, size):
    idx = len(ISLANDS[mat])
    assert idx < cols * rows, f"UV grid overflow adding island {island_id}"
    ISLANDS[mat].append(island_id)
    ISLAND_GRID[island_id] = dict(mat=mat, col=idx % cols, row=idx // cols,
                                  cols=cols, rows=rows, size=size)
    return island_id

def cell_of(island_id):
    g = ISLAND_GRID[island_id]
    return g["col"], g["row"], g["cols"], g["rows"]

ISLAND_DEFS = [
    (MAT_SKIN,  "skin_head",    3, 3, 2048),
    (MAT_SKIN,  "skin_nose",    3, 3, 2048),
    (MAT_SKIN,  "skin_lips",    3, 3, 2048),
    (MAT_SKIN,  "skin_brow_L",  3, 3, 2048),
    (MAT_SKIN,  "skin_brow_R",  3, 3, 2048),
    (MAT_SKIN,  "skin_lid_u_L", 3, 3, 2048),
    (MAT_SKIN,  "skin_lid_u_R", 3, 3, 2048),
    (MAT_SKIN,  "skin_lid_l_L", 3, 3, 2048),
    (MAT_SKIN,  "skin_lid_l_R", 3, 3, 2048),
    (MAT_SUIT,  "suit_torso",       4, 4, 2048),
    (MAT_SUIT,  "suit_arm_L",       4, 4, 2048),
    (MAT_SUIT,  "suit_leg_L",       4, 4, 2048),
    (MAT_SUIT,  "suit_leg_R",       4, 4, 2048),
    (MAT_SUIT,  "suit_palm_L",      4, 4, 2048),
    (MAT_SUIT,  "suit_f_thumb_L",   4, 4, 2048),
    (MAT_SUIT,  "suit_f_index_L",   4, 4, 2048),
    (MAT_SUIT,  "suit_f_middle_L",  4, 4, 2048),
    (MAT_SUIT,  "suit_f_ring_L",    4, 4, 2048),
    (MAT_SUIT,  "suit_f_pinky_L",   4, 4, 2048),
    (MAT_SUIT,  "suit_cable",       4, 4, 2048),
    (MAT_SUIT,  "suit_strap_chest", 4, 4, 2048),
    (MAT_SUIT,  "suit_strap_thigh", 4, 4, 2048),
    (MAT_ARMOR, "armor_pauldron_L", 4, 4, 1024),
    (MAT_ARMOR, "armor_pauldron_R", 4, 4, 1024),
    (MAT_ARMOR, "armor_chest",      4, 4, 1024),
    (MAT_ARMOR, "armor_belt",       4, 4, 1024),
    (MAT_ARMOR, "armor_knee_L",     4, 4, 1024),
    (MAT_ARMOR, "armor_knee_R",     4, 4, 1024),
    (MAT_ARMOR, "armor_shin_L",     4, 4, 1024),
    (MAT_ARMOR, "armor_shin_R",     4, 4, 1024),
    (MAT_ARMOR, "armor_backpack",   4, 4, 1024),
    (MAT_ARMOR, "armor_blade",      4, 4, 1024),
    (MAT_ARMOR, "armor_holster",    4, 4, 1024),
    (MAT_ARMOR, "armor_beacon",     4, 4, 1024),
    (MAT_ARMOR, "armor_headset",    4, 4, 1024),
    (MAT_CYBER, "cyber_forearm_R",    4, 4, 1024),
    (MAT_CYBER, "cyber_palm_R",       4, 4, 1024),
    (MAT_CYBER, "cyber_f_thumb_R",    4, 4, 1024),
    (MAT_CYBER, "cyber_f_index_R",    4, 4, 1024),
    (MAT_CYBER, "cyber_f_middle_R",   4, 4, 1024),
    (MAT_CYBER, "cyber_f_ring_R",     4, 4, 1024),
    (MAT_CYBER, "cyber_f_pinky_R",    4, 4, 1024),
    (MAT_CYBER, "cyber_emitter_body", 4, 4, 1024),
    (MAT_CYBER, "cyber_shroud",       4, 4, 1024),
    (MAT_CYBER, "cyber_cell_body",    4, 4, 1024),
    (MAT_CYBER, "cyber_earpiece",     4, 4, 1024),
    (MAT_EMISSIVE, "emis_emitter",    3, 3, 1024),
    (MAT_EMISSIVE, "emis_cell_core",  3, 3, 1024),
    (MAT_EMISSIVE, "emis_beacon",     3, 3, 1024),
    (MAT_EMISSIVE, "emis_visor",      3, 3, 1024),
    (MAT_EMISSIVE, "emis_blade_edge", 3, 3, 1024),
    (MAT_HAIR,  "hair_cap", 1, 1, 1024),
    (MAT_EYE,   "eye_ball", 1, 1, 512),
    (MAT_MOUTH, "mouth_cavity", 2, 2, 512),
    (MAT_MOUTH, "mouth_teeth",  2, 2, 512),
    (MAT_MOUTH, "mouth_tongue", 2, 2, 512),
]
for mat, iid, cols, rows, size in ISLAND_DEFS:
    register_island(mat, iid, cols, rows, size)

CHEVRON_ISLANDS = {"suit_torso", "suit_arm_L", "suit_leg_L", "suit_leg_R",
                   "armor_chest", "armor_pauldron_L", "armor_pauldron_R"}

# ===================================================================== helpers
def w_two(a, b, t):
    return {a: 1.0 - t, b: t}

def sample_path(points, ts):
    pts = [Vector(p) for p in points]
    seglens = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seglens)
    cum = [0.0]
    for l in seglens:
        cum.append(cum[-1] + l)
    out = []
    for t in ts:
        d = t * total
        for i in range(len(seglens)):
            if cum[i + 1] >= d or i == len(seglens) - 1:
                u = 0.0 if seglens[i] == 0 else (d - cum[i]) / seglens[i]
                out.append(pts[i].lerp(pts[i + 1], u))
                break
    return out

def path_rings(points, ts, radii_fn, mat, weights_fn, island=None, v_scale=1.0):
    rings = []
    positions = sample_path(points, ts)
    for t, c in zip(ts, positions):
        rx, rz = radii_fn(t)
        rings.append(dict(c=c, rx=rx, rz=rz, mat=mat, w=weights_fn(t),
                          island=island, t=t))
    return rings

# ===================================================================== body geometry
def leg_rings(side):
    s = -1.0 if side == 'L' else 1.0
    x = 0.105 * s
    pts = [(x, -0.010, 0.925), (x, -0.018, 0.720), (x, -0.022, 0.478),
           (x, -0.030, 0.300), (x, -0.035, 0.105), (x, 0.010, 0.030),
           (x, -0.090, 0.026), (x, -0.185, 0.026)]
    ts = [0.0, 0.15, 0.28, 0.407, 0.52, 0.63, 0.747, 0.822, 0.913, 1.0]
    def radii(t):
        if t < 0.407:
            u = t / 0.407
            return (lerp(0.096, 0.070, smoothstep(u)), lerp(0.078, 0.060, smoothstep(u)))
        if t < 0.52:
            return (0.066, 0.056)
        if t < 0.66:
            u = (t - 0.52) / 0.14
            return (lerp(0.060, 0.052, u), lerp(0.050, 0.042, u))
        if t < 0.747:
            return (0.054, 0.040)
        if t < 0.913:
            return (0.062, 0.030)
        return (0.066, 0.026)
    def weights(t):
        thigh, thigh_tw = f"thigh_{side}", f"thigh_twist_{side}"
        shin, shin_tw = f"shin_{side}", f"shin_twist_{side}"
        foot, toe = f"foot_{side}", f"toe_{side}"
        if t < 0.05:
            return w_two("pelvis", thigh, t / 0.05)
        if t < 0.28:
            return {thigh: 1.0}
        if t < 0.40:
            return w_two(thigh, thigh_tw, 0.5)
        if t < 0.48:
            return w_two(thigh, shin, (t - 0.40) / 0.08)
        if t < 0.62:
            return w_two(shin, shin_tw, 0.5)
        if t < 0.70:
            return {shin: 1.0}
        if t < 0.78:
            return w_two(shin, foot, (t - 0.70) / 0.08)
        if t < 0.90:
            return {foot: 1.0}
        if t < 0.95:
            return w_two(foot, toe, (t - 0.90) / 0.05)
        return {toe: 1.0}
    return path_rings(pts, ts, radii, MAT_SUIT, weights, island=f"suit_leg_{side}")

def torso_rings():
    pts = [(0.0, 0.000, 0.885), (0.0, 0.004, 0.955), (0.0, 0.008, 1.03),
           (0.0, 0.012, 1.11), (0.0, 0.016, 1.20), (0.0, 0.020, 1.29),
           (0.0, 0.022, 1.36), (0.0, 0.026, 1.395), (0.0, 0.030, 1.415),
           (0.0, 0.032, 1.435)]
    ts = [0.0, 0.10, 0.20, 0.32, 0.45, 0.58, 0.70, 0.80, 0.90, 1.0]
    def radii(t):
        if t < 0.14:
            u = t / 0.14
            return (lerp(0.185, 0.175, u), lerp(0.125, 0.118, u))
        if t < 0.45:
            u = (t - 0.14) / 0.31
            return (lerp(0.175, 0.165, smoothstep(u)), lerp(0.118, 0.112, smoothstep(u)))
        if t < 0.70:
            u = (t - 0.45) / 0.25
            return (lerp(0.165, 0.215, smoothstep(u)), lerp(0.112, 0.128, smoothstep(u)))
        if t < 0.86:
            u = (t - 0.70) / 0.16
            return (lerp(0.215, 0.205, u), lerp(0.128, 0.124, u))
        u = (t - 0.86) / 0.14
        return (lerp(0.205, 0.100, smoothstep(u)), lerp(0.124, 0.085, smoothstep(u)))
    def weights(t):
        if t < 0.12:
            return w_two("pelvis", "spine_01", t / 0.12)
        if t < 0.30:
            return {"spine_01": 1.0}
        if t < 0.45:
            return w_two("spine_01", "spine_02", (t - 0.30) / 0.15)
        if t < 0.62:
            return {"spine_02": 1.0}
        if t < 0.78:
            return w_two("spine_02", "spine_03", (t - 0.62) / 0.16)
        if t < 0.88:
            return {"spine_03": 0.7, "clavicle_L": 0.15, "clavicle_R": 0.15}
        return {"spine_03": 0.6, "clavicle_L": 0.2, "clavicle_R": 0.2}
    return path_rings(pts, ts, radii, MAT_SUIT, weights, island="suit_torso")

HEAD_PTS = [(0.0, 0.018, 1.435), (0.0, 0.016, 1.50), (0.0, 0.012, 1.545),
            (0.0, 0.008, 1.556), (0.0, 0.016, 1.565), (0.0, -0.005, 1.60),
            (0.0, -0.015, 1.63), (0.0, -0.025, 1.66), (0.0, -0.028, 1.70),
            (0.0, -0.020, 1.74), (0.0, -0.005, 1.775), (0.0, 0.010, 1.800)]
HEAD_TS = [0.0, 0.09, 0.18, 0.24, 0.30, 0.38, 0.47, 0.56, 0.65, 0.78, 0.89, 1.0]

def head_radii(t):
    if t < 0.18:
        u = t / 0.18
        return (lerp(0.048, 0.056, u), lerp(0.052, 0.072, u))
    if t < 0.24:
        u = (t - 0.18) / 0.06
        return (lerp(0.056, 0.068, u), lerp(0.072, 0.088, u))
    if t < 0.30:
        u = (t - 0.24) / 0.06
        return (lerp(0.068, 0.060, u), lerp(0.088, 0.058, smoothstep(u)))
    if t < 0.38:
        u = (t - 0.30) / 0.08
        return (lerp(0.060, 0.079, u), lerp(0.058, 0.094, smoothstep(u)))
    if t < 0.65:
        u = (t - 0.38) / 0.27
        return (lerp(0.079, 0.087, smoothstep(u)), lerp(0.094, 0.096, smoothstep(u)))
    if t < 0.89:
        u = (t - 0.65) / 0.24
        return (lerp(0.087, 0.082, u), lerp(0.096, 0.086, u))
    u = (t - 0.89) / 0.11
    return (lerp(0.082, 0.032, smoothstep(u)), lerp(0.086, 0.038, smoothstep(u)))

def head_weights(t):
    if t < 0.10:
        return w_two("neck_01", "neck_02", t / 0.10)
    if t < 0.18:
        return {"neck_02": 1.0}
    if t < 0.28:
        return w_two("neck_02", "jaw", (t - 0.18) / 0.10)
    if t < 0.34:
        return w_two("jaw", "head", (t - 0.28) / 0.06)
    return {"head": 1.0}

def head_rings():
    rings = path_rings(HEAD_PTS, HEAD_TS, head_radii, MAT_SKIN, head_weights,
                       island="skin_head")
    rings[-1]["T"] = (0.0, 0.0, 1.0)  # vertical tangent: crown ring is a horizontal circle at z=1.800
    return rings

def head_ring_at(t):
    """Virtual head-tube ring at arc-length parameter t (any t in [0, 1], not just
    control ts): center from sample_path, radii from head_radii."""
    c = sample_path(HEAD_PTS, [t])[0]
    rx, rz = head_radii(t)
    return dict(c=c, rx=rx, rz=rz)

def ring_arc_band(name, base_c, base_rx, base_rz, T, th_lo, th_hi, n, push,
                  rx, rz, segs, mat, island, weight, cap_start=True, cap_end=True):
    """Curved strap following an elliptical arc of a base ring: arc points
    p(th) = base_c + A*(base_rx*cos th) + B*(base_rz*sin th), each pushed `push`
    meters outward along (p - base_c). (A, B) = ring_frame(T) - the same frame
    convention bm_tube uses for rings of the head tube."""
    A, B = ring_frame(Vector(T))
    rings = []
    for i in range(n):
        th = math.radians(th_lo + (th_hi - th_lo) * i / (n - 1))
        p = base_c + A * (base_rx * math.cos(th)) + B * (base_rz * math.sin(th))
        d = p - base_c
        if d.length > 1e-9:
            p = p + d.normalized() * push
        rings.append(dict(c=p, rx=rx, rz=rz, mat=mat, w=weight, t=0.0))
    MB.tube(name, rings, segs, mat, island, cap_start=cap_start, cap_end=cap_end)

def arm_rings(side, cyber_forearm):
    """Returns (upper_rings, forearm_rings). The right arm splits at the elbow into a
    SUIT upper arm and a CYBER forearm (two coincident rings at the elbow seam)."""
    s = -1.0 if side == 'L' else 1.0
    pts = [(0.205 * s, 0.018 * s, 1.385), (0.222 * s, 0.013 * s, 1.20),
           (0.232 * s, 0.008 * s, 1.075), (0.234 * s, 0.004 * s, 0.95),
           (0.233 * s, 0.0, 0.775)]
    ts_all = [0.0, 0.12, 0.26, 0.40, 0.509, 0.62, 0.74, 0.86, 1.0]
    def radii(t):
        if t < 0.42:
            u = t / 0.42
            return (lerp(0.062, 0.052, smoothstep(u)), lerp(0.058, 0.050, smoothstep(u)))
        if t < 0.52:
            return (0.050, 0.047)
        u = (t - 0.52) / 0.48
        return (lerp(0.047, 0.038, smoothstep(u)), lerp(0.045, 0.036, smoothstep(u)))
    def weights(t):
        ua, uat = f"upper_arm_{side}", f"upper_arm_twist_{side}"
        fa, fat = f"forearm_{side}", f"forearm_twist_{side}"
        hand = f"hand_{side}"
        if t < 0.06:
            return w_two(f"clavicle_{side}", ua, 0.5)
        if t < 0.20:
            return {ua: 1.0}
        if t < 0.40:
            return w_two(ua, uat, 0.5)
        if t < 0.50:
            return w_two(ua, fa, (t - 0.40) / 0.10)
        if t < 0.68:
            return w_two(fa, fat, 0.5)
        if t < 0.78:
            return w_two(fa, hand, (t - 0.68) / 0.10)
        return {hand: 1.0}
    rings = path_rings(pts, ts_all, radii, MAT_SUIT, weights, island="suit_arm_L")
    if cyber_forearm:
        upper = [r for r in rings if r["t"] <= 0.509 + 1e-9]
        fore = []
        for r in rings:
            if r["t"] >= 0.509 - 1e-9:
                r2 = dict(r)
                r2["mat"] = MAT_CYBER
                r2["island"] = "cyber_forearm_R"
                fore.append(r2)
        # The elbow ring is shared by both tubes: force one identical ring frame
        # (central-difference tangent) so the coincident rims close the seam exactly.
        t_elbow = (rings[4]["c"] - rings[3]["c"]).lerp(rings[5]["c"] - rings[4]["c"], 0.5)
        upper[-1]["T"] = t_elbow
        fore[0]["T"] = t_elbow.copy()
        return upper, fore
    return rings, None

FINGER_SPECS = {
    "thumb":  dict(bx=0.268, by=-0.028, bz=0.694, tx=0.232, ty=-0.080, tz=0.690, r0=0.011, curls=(20, 30, 18)),
    "index":  dict(bx=0.256, by=-0.050, bz=0.702, tx=0.252, ty=-0.116, tz=0.698, r0=0.0095, curls=(16, 24, 14)),
    "middle": dict(bx=0.248, by=-0.046, bz=0.698, tx=0.246, ty=-0.120, tz=0.694, r0=0.010, curls=(16, 26, 14)),
    "ring":   dict(bx=0.240, by=-0.040, bz=0.688, tx=0.238, ty=-0.108, tz=0.682, r0=0.0095, curls=(16, 24, 14)),
    "pinky":  dict(bx=0.230, by=-0.034, bz=0.690, tx=0.227, ty=-0.086, tz=0.672, r0=0.0080, curls=(14, 22, 12)),
}

def finger_path(side, spec):
    s = -1.0 if side == 'L' else 1.0
    base = Vector((spec["bx"] * s, spec["by"] * s, spec["bz"]))
    tip = Vector((spec["tx"] * s, spec["ty"] * s, spec["tz"]))
    n = 3
    seg_len = (tip - base).length / n
    dir0 = (tip - base).normalized()
    pts = [base]
    for k in range(1, n + 1):
        cum = sum(math.radians(c) for c in spec["curls"][:k])
        d = (Matrix.Rotation(cum, 4, 'X') @ dir0).normalized()
        pts.append(pts[-1] + d * seg_len)
    return pts

def palm_rings(side, cyber):
    s = -1.0 if side == 'L' else 1.0
    wrist = Vector((0.245 * s, 0.004 * s, 0.775))
    knuckle = Vector((0.250 * s, -0.038 * s, 0.685))
    mat = MAT_CYBER if cyber else MAT_SUIT
    rings = []
    for t in (0.0, 0.3, 0.6, 1.0):
        rings.append(dict(c=wrist.lerp(knuckle, t), rx=lerp(0.038, 0.042, t),
                          rz=lerp(0.020, 0.024, t), mat=mat,
                          w={f"hand_{side}": 1.0}, t=t))
    return rings

def finger_rings(side, fname, spec, cyber):
    mat = MAT_CYBER if cyber else MAT_SUIT
    pts = finger_path(side, spec)
    ts = [0.0, 0.18, 0.34, 0.5, 0.66, 0.82, 1.0]
    r0 = spec["r0"]
    def radii(t):
        return (lerp(r0, r0 * 0.55, smoothstep(t)), lerp(r0 * 0.9, r0 * 0.5, smoothstep(t)))
    def weights(t):
        bones = [f"f_{fname}_0{i}_{side}" for i in (1, 2, 3)]
        hand = f"hand_{side}"
        if t < 0.12:
            return w_two(hand, bones[0], t / 0.12)
        if t < 0.40:
            return {bones[0]: 1.0}
        if t < 0.55:
            return w_two(bones[0], bones[1], (t - 0.40) / 0.15)
        if t < 0.75:
            return {bones[1]: 1.0}
        if t < 0.88:
            return w_two(bones[1], bones[2], (t - 0.75) / 0.13)
        return {bones[2]: 1.0}
    return path_rings(pts, ts, radii, mat, weights)

# ===================================================================== mesh builder
class MeshBuilder:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.vert_weights = {}
        self.uv_parts = []
        self.part_log = []

    # NOTE: all bookkeeping uses bmesh element REFERENCES, never .index — indices are
    # invalid (-1) until index_update() and shift when sphere_cap_bm deletes verts.
    def tube(self, name, rings, segs, mat, island, cap_start=False, cap_end=False,
             v_scale=1.0):
        before_f = set(self.bm.faces)
        rvl, caps = bm_tube(self.bm, rings, segs, mat,
                            cap_start=cap_start, cap_end=cap_end)
        new_faces = [f for f in self.bm.faces if f not in before_f]
        ring_vi = []
        nverts = 0
        for verts, ring in rvl:
            for v in verts:
                self.vert_weights[v] = ring["w"]
            ring_vi.append((verts, ring))
            nverts += len(verts)
        cap_vi = {}
        for key, ring in (("start", rings[0]), ("end", rings[-1])):
            cv = caps[key]
            if cv is not None:
                self.vert_weights[cv] = ring["w"]
                cap_vi[key] = cv
        self.uv_parts.append(dict(kind="tube", rings=ring_vi, segs=segs,
                                  island=island, v_scale=v_scale, faces=new_faces,
                                  caps=cap_vi))
        self.part_log.append((name, nverts, len(new_faces)))
        return rvl, caps

    def prim(self, name, build_fn, island, weight, uv_mode="planar", mat_islands=None):
        before_v = set(self.bm.verts)
        before_f = set(self.bm.faces)
        build_fn(self.bm)
        new_verts = [v for v in self.bm.verts if v not in before_v]
        new_faces = [f for f in self.bm.faces if f not in before_f]
        for v in new_verts:
            self.vert_weights[v] = weight
        self.uv_parts.append(dict(kind="prim", faces=new_faces, verts=new_verts,
                                  island=island, uv_mode=uv_mode,
                                  mat_islands=mat_islands or {}))
        self.part_log.append((name, len(new_verts), len(new_faces)))

    # after finish() remaps, part["faces"] is a list of mesh polygon indices,
    # tube part["rings"] holds mesh vertex indices, prim part["verts"] likewise.
    def _tube_uv(self, me, uv, part):
        rings = part["rings"]
        segs = part["segs"]
        vert_uv = {}
        v = 0.0
        prev_c = None
        for ri, (vis, ring) in enumerate(rings):
            c = ring["c"]
            if ri > 0:
                v += (c - prev_c).length * part["v_scale"]
            prev_c = c
            for j, vi in enumerate(vis):
                vert_uv[vi] = (j / segs, v)
        total_v = max(x[1] for x in vert_uv.values()) or 1.0
        if "start" in part["caps"]:
            vert_uv[part["caps"]["start"]] = (0.5, 0.0)
        if "end" in part["caps"]:
            vert_uv[part["caps"]["end"]] = (0.5, total_v)
        col, row, cols, rows = cell_of(part["island"])
        for vi, (lu, lv) in vert_uv.items():
            vert_uv[vi] = ((col + lu) / cols, (row + lv / total_v) / rows)
        for fi in part["faces"]:
            p = me.polygons[fi]
            for li in p.loop_indices:
                vi = me.loops[li].vertex_index
                if vi in vert_uv:
                    uv.data[li].uv = vert_uv[vi]

    def _prim_uv(self, me, uv, part):
        vlist = part["verts"]
        if not vlist:
            return
        vs = [me.vertices[i].co for i in vlist]
        mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
        mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
        d = Vector((max(mx.x - mn.x, 1e-6), max(mx.y - mn.y, 1e-6), max(mx.z - mn.z, 1e-6)))
        ctr = (mn + mx) * 0.5
        r = max(d.x, d.y, d.z) * 0.5
        mode = part["uv_mode"]
        for fi in part["faces"]:
            p = me.polygons[fi]
            iid = part["mat_islands"].get(p.material_index, part["island"])
            col, row, cols, rows = cell_of(iid)
            n = p.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for li in p.loop_indices:
                v = me.vertices[me.loops[li].vertex_index].co
                if mode == "planar":
                    if ax >= ay and ax >= az:
                        u, vc = (v.y - mn.y) / d.y, (v.z - mn.z) / d.z
                    elif ay >= az:
                        u, vc = (v.x - mn.x) / d.x, (v.z - mn.z) / d.z
                    else:
                        u, vc = (v.x - mn.x) / d.x, (v.y - mn.y) / d.y
                elif mode == "cyl_z":
                    u = (math.atan2(v.y - ctr.y, v.x - ctr.x) / (2 * math.pi)) % 1.0
                    vc = (v.z - mn.z) / d.z
                elif mode == "cyl_y":
                    u = (math.atan2(v.x - ctr.x, v.z - ctr.z) / (2 * math.pi)) % 1.0
                    vc = (v.y - mn.y) / d.y
                elif mode == "cyl_x":
                    u = (math.atan2(v.y - ctr.y, v.z - ctr.z) / (2 * math.pi)) % 1.0
                    vc = (v.x - mn.x) / d.x
                else:  # sphere
                    u = (math.atan2(v.y - ctr.y, v.x - ctr.x) / (2 * math.pi) + 0.5) % 1.0
                    vc = (math.asin(clamp((v.z - ctr.z) / r, -1, 1)) / math.pi + 0.5) % 1.0
                uv.data[li].uv = ((col + clamp(u, 0, 1)) / cols, (row + clamp(vc, 0, 1)) / rows)

    def finish(self, obj_name):
        me = bpy.data.meshes.new(self.name)
        self.bm.verts.index_update()
        self.bm.faces.index_update()
        self.bm.to_mesh(me)
        # mesh element k == bmesh element with index k (to_mesh preserves list order)
        vmap = {v: i for i, v in enumerate(self.bm.verts)}
        fmap = {f: i for i, f in enumerate(self.bm.faces)}
        iw = {vmap[vref]: wmap for vref, wmap in self.vert_weights.items()}
        for part in self.uv_parts:
            part["faces"] = [fmap[f] for f in part["faces"]]
            if part["kind"] == "tube":
                part["rings"] = [([vmap[v] for v in verts], ring)
                                 for verts, ring in part["rings"]]
                part["caps"] = {k: vmap[v] for k, v in part["caps"].items()}
            else:
                part["verts"] = [vmap[v] for v in part["verts"]]
        self.bm.free()
        obj = bpy.data.objects.new(obj_name, me)
        bpy.context.scene.collection.objects.link(obj)
        for p in me.polygons:
            p.use_smooth = True
        assign_weights(obj, iw)
        cap_weights(obj, 8)
        normalize_weights(obj)
        uv = me.uv_layers.new(name="UVMap")
        for part in self.uv_parts:
            if part["kind"] == "tube":
                self._tube_uv(me, uv, part)
            else:
                self._prim_uv(me, uv, part)
        return obj

# ===================================================================== build
MB = MeshBuilder("OperativeMesh")

# ---- legs
for side in ('L', 'R'):
    MB.tube(f"leg_{side}", leg_rings(side), 26, MAT_SUIT, f"suit_leg_{side}",
            cap_end=True)

# ---- torso (capped both ends: pelvis bottom + shoulder top)
MB.tube("torso", torso_rings(), 32, MAT_SUIT, "suit_torso", cap_start=True, cap_end=True)

# ---- head (capped crown; the mouth cavity is an indented ring in the tube)
head_r = head_rings()
MB.tube("head", head_r, 34, MAT_SKIN, "skin_head", cap_end=True)

# ---- hair: shell over the skull's upper rings (bottom ring coincides with the
#      head ring at t=0.78 -> fringe at z~1.739 front / 1.723 sides / 1.706 back,
#      above the brow tubes and clear of the visor band)
hair_src = [r for r in head_r if r["t"] >= 0.78 - 1e-9]
hair_rings = []
first = head_r[[r["t"] for r in head_r].index(0.78)]
hair_rings.append(dict(c=first["c"].copy(), rx=first["rx"], rz=first["rz"],
                       mat=MAT_HAIR, w={"head": 1.0}, t=0.78))
for r in hair_src:
    hair_rings.append(dict(c=r["c"].copy(), rx=r["rx"] * 1.07, rz=r["rz"] * 1.07,
                           mat=MAT_HAIR, w={"head": 1.0}, t=r["t"]))
hair_rings[-1]["T"] = (0.0, 0.0, 1.0)  # horizontal crown ring at z=1.800
MB.tube("hair", hair_rings, 28, MAT_HAIR, "hair_cap", cap_end=True)

# ---- arms
for side, cyber in (('L', False), ('R', True)):
    upper, fore = arm_rings(side, cyber)
    MB.tube(f"arm_upper_{side}", upper, 22, MAT_SUIT, "suit_arm_L", cap_end=(side == 'L'))
    if fore is not None:
        MB.tube(f"arm_forearm_{side}", fore, 22, MAT_CYBER, "cyber_forearm_R", cap_end=True)

# ---- hands
for side, cyber in (('L', False), ('R', True)):
    mat = MAT_CYBER if cyber else MAT_SUIT
    palm_iid = f"cyber_palm_R" if cyber else "suit_palm_L"
    MB.tube(f"palm_{side}", palm_rings(side, cyber), 12, mat, palm_iid, cap_end=True)
    for fname, spec in FINGER_SPECS.items():
        iid = (f"cyber_f_{fname}_R" if cyber else f"suit_f_{fname}_L")
        MB.tube(f"finger_{fname}_{side}", finger_rings(side, fname, spec, cyber),
                10, mat, iid, cap_end=True)

# ---- face prims
def _move(verts, M):
    for v in verts:
        v.co = M @ v.co

def prim_box(name, sx, sy, sz, loc, rot, mat, island, weight, uv_mode="planar",
             mat_islands=None):
    def build(bm):
        nv, nf = box_mesh_bm(bm, sx, sy, sz, mat)
        R = Euler(rot).to_matrix().to_4x4()
        _move(nv, Matrix.Translation(Vector(loc)) @ R)
    MB.prim(name, build, island, weight, uv_mode=uv_mode, mat_islands=mat_islands)

def prim_cyl(name, radius, length, segs, loc, axis, mat, island, weight,
             uv_mode=None, mat_caps=None, mat_side=None, mat_islands=None):
    def build(bm):
        nv, nf = cylinder_mesh_bm(bm, radius, length, segs, mat, axis=axis,
                                  mat_caps=mat_caps, mat_side=mat_side)
        _move(nv, Matrix.Translation(Vector(loc)))
    if uv_mode is None:
        uv_mode = {"Z": "cyl_z", "Y": "cyl_y", "X": "cyl_x"}[axis]
    MB.prim(name, build, island, weight, uv_mode=uv_mode, mat_islands=mat_islands)

def prim_sphere(name, radius, loc, segs, rings, mat, island, weight, uv_mode="sphere"):
    def build(bm):
        nv, nf = sphere_mesh_bm(bm, radius, segs=segs, rings=rings)
        for f in nf:
            f.material_index = mat
        _move(nv, Matrix.Translation(Vector(loc)))
    MB.prim(name, build, island, weight, uv_mode=uv_mode)

def prim_cap(name, radius, loc, euler, half_angle, segs, rings, mat, island, weight):
    def build(bm):
        cv, cf = sphere_cap_bm(bm, radius, half_angle, segs=segs, rings=rings,
                               mat_index=mat)
        R = Euler(euler).to_matrix().to_4x4()
        _move(cv, Matrix.Translation(Vector(loc)) @ R)
    MB.prim(name, build, island, weight, uv_mode="planar")

# nose (skin): squashed sphere embedded in the nose-bridge surface, protruding ~2 cm
def build_nose(bm):
    nv, nf = sphere_mesh_bm(bm, 1.0, segs=18, rings=12)
    for v in nv:
        v.co.x *= 0.018
        v.co.y *= 0.024
        v.co.z *= 0.032
    _move(nv, Matrix.Translation(Vector((0.0, -0.098, 1.615))))
    for f in nf:
        f.material_index = MAT_SKIN
MB.prim("nose", build_nose, "skin_nose", {"head": 1.0}, uv_mode="planar")

# brows: curved ridge tubes following the measured brow ridge (skin y at z=1.682
# per x, axis 4.5 mm forward of the surface). 12 mm tall (z 1.676..1.688), clear
# of the visor band (>= 13 mm gap) and of the fringe (front z 1.739).
BROW_X = (0.018, 0.030, 0.045, 0.060, 0.075)
BROW_Y = (-0.12190, -0.11807, -0.11010, -0.09745, -0.07643)
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    rings = [dict(c=Vector((x * s, y, 1.682)), rx=0.0035, rz=0.0060,
                  mat=MAT_SKIN, w={f"brow_{side}": 1.0}, t=0.0)
             for x, y in zip(BROW_X, BROW_Y)]
    MB.tube(f"brow_{side}", rings, 8, MAT_SKIN, f"skin_brow_{side}",
            cap_start=True, cap_end=True)

# eyes (both share the single eye island - intentional overlap of identical geometry)
# Eye at x=0.042: the face recedes ~19 mm from x=0.055 to x=0.07 at eye height, so
# at x=0.055 an eyeball bulges ~10 mm out of the skin on its outer side and no
# concentric lid cap can cover it. At x=0.042 the eyeball front is 3 mm proud of
# the skin (skin(0.042, 1.645) = -0.10422; eye front = -0.0947 - 0.0125 = -0.1072).
EYE_X, EYE_CY, EYE_CZ = 0.042, -0.0947, 1.645
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    prim_sphere(f"eye_{side}", 0.0125, (EYE_X * s, EYE_CY, EYE_CZ), 20, 12,
                MAT_EYE, "eye_ball", {f"eye_{side}": 1.0})

# eyelids: spherical caps around the eye centers. sphere_cap_bm keeps the region
# within half_angle of the cap's local +Z, so euler X=+22 deg puts the upper cap
# pole 22 deg from up toward the face (-Y) -> pole ELEVATION +68 deg. The discrete
# cap rim is the last uvsphere row kept by the half_angle filter: with rings=18
# the rows sit every 10 deg, so half_angle=45 keeps rows up to 40 deg -> the rim
# lands at 68-40 = +/-28 deg elevation = the resting eye-slit edge (with rings=12
# the rim would fall at 30 deg from the pole and the slit would be too tall).
# Blink: rotate the lid bone +56 deg about X (upper) / -56 deg (lower) -> rims
# swing to -/+28 deg, lids close.
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    loc = (EYE_X * s, EYE_CY, EYE_CZ)
    prim_cap(f"lid_upper_{side}", 0.0138, loc, (math.radians(22), 0, 0), 45, 20, 18,
             MAT_SKIN, f"skin_lid_u_{side}", {f"lid_upper_{side}": 1.0})
    prim_cap(f"lid_lower_{side}", 0.0138, loc, (math.radians(158), 0, 0), 45, 20, 18,
             MAT_SKIN, f"skin_lid_l_{side}", {f"lid_lower_{side}": 1.0})

# ---- mouth: closed lip torus around a flat oval + cavity + teeth + tongue
MOUTH_C = Vector((0.0, -0.080, 1.565))
LIP_RX, LIP_RZ = 0.046, 0.0075
N_OVAL = 32
oval_pts = []
for i in range(N_OVAL):
    a = 2 * math.pi * i / N_OVAL
    oval_pts.append(Vector((LIP_RX * math.cos(a), MOUTH_C.y, MOUTH_C.z + LIP_RZ * math.sin(a))))
lip_rings = []
for i, c in enumerate(oval_pts):
    nxt = oval_pts[(i + 1) % N_OVAL]
    prv = oval_pts[(i - 1) % N_OVAL]
    T = (nxt - prv).normalized()          # oval tangent: identical frame for all 3 rings
    out = Vector((c.x - MOUTH_C.x, 0.0, c.z - MOUTH_C.z))
    if out.length > 1e-6:
        out.normalize()
    for thickness, bulge in ((0.0075, 0.0), (0.0095, 0.004), (0.0075, 0.0)):
        p = Vector((c.x + out.x * bulge, c.y, c.z + out.z * bulge))
        lip_rings.append(dict(c=p, rx=thickness, rz=thickness * 0.8, mat=MAT_SKIN,
                              w=None, t=0.0, T=T))
lip_rings.append(dict(lip_rings[0]))  # duplicate first ring: bm_tube closes the loop
# emit lip torus as a tube part (the duplicated ring closes it; no manual faces)
def emit_lips(bm):
    rvl, caps = bm_tube(bm, lip_rings, 13, MAT_SKIN)
    return rvl, caps

# weights for the lip torus: upper lip -> head, lower lip -> jaw (by z)
def lip_weight_for(co):
    return {"head": 1.0} if co.z > MOUTH_C.z else {"jaw": 1.0}

# custom part: lip torus tube, weights by vertex z (upper lip -> head, lower -> jaw)
before_f = set(MB.bm.faces)
rvl_lips, caps_lips = emit_lips(MB.bm)
lip_faces = [f for f in MB.bm.faces if f not in before_f]
ring_vi = []
for verts, ring in rvl_lips:
    for v in verts:
        MB.vert_weights[v] = lip_weight_for(v.co)
    ring_vi.append((verts, ring))
MB.uv_parts.append(dict(kind="tube", rings=ring_vi, segs=13, island="skin_lips",
                        v_scale=1.0, faces=lip_faces, caps={}))
MB.part_log.append(("lips_torus", sum(len(vs) for vs, _ in ring_vi), len(lip_faces)))

# cavity disc (dark back wall of the mouth void, faces -Y toward the viewer)
def build_cavity(bm):
    verts = []
    for i in range(N_OVAL):
        a = 2 * math.pi * i / N_OVAL
        sa = math.sin(a)
        r = 0.056 if sa > 0 else 0.048
        verts.append(bm.verts.new(Vector((r * math.cos(a), -0.046,
                                          MOUTH_C.z + (0.020 if sa > 0 else 0.017) * sa))))
    center = bm.verts.new(Vector((0.0, -0.046, MOUTH_C.z)))
    for i in range(N_OVAL):
        i2 = (i + 1) % N_OVAL
        try:
            f = bm.faces.new((verts[i], verts[i2], center))
            f.material_index = MAT_MOUTH
        except ValueError:
            pass
MB.prim("mouth_cavity", build_cavity, "mouth_cavity", {"head": 1.0})

# teeth rows (face -Y). Upper row hangs from the head, lower row rises from the jaw.
def build_teeth_upper(bm):
    n = 10
    y = -0.072
    z = MOUTH_C.z + 0.016
    dz = -0.006
    verts = []
    for i in range(n):
        x = -0.030 + 0.060 * (i / (n - 1))
        verts.append(bm.verts.new(Vector((x, y, z))))
    for i in range(n - 1):
        x0 = verts[i].co.x; x1 = verts[i + 1].co.x
        v0 = verts[i]; v1 = verts[i + 1]
        v2 = bm.verts.new(Vector((x1, y - 0.002, z + dz)))
        v3 = bm.verts.new(Vector((x0, y - 0.002, z + dz)))
        try:
            f = bm.faces.new((v0, v3, v2, v1))
            f.material_index = MAT_MOUTH
        except ValueError:
            pass
MB.prim("mouth_teeth_upper", build_teeth_upper, "mouth_teeth", {"head": 1.0})

def build_teeth_lower(bm):
    n = 10
    y = -0.072
    z = MOUTH_C.z - 0.016
    dz = 0.006
    verts = []
    for i in range(n):
        x = -0.030 + 0.060 * (i / (n - 1))
        verts.append(bm.verts.new(Vector((x, y, z))))
    for i in range(n - 1):
        x0 = verts[i].co.x; x1 = verts[i + 1].co.x
        v0 = verts[i]; v1 = verts[i + 1]
        v2 = bm.verts.new(Vector((x1, y - 0.002, z + dz)))
        v3 = bm.verts.new(Vector((x0, y - 0.002, z + dz)))
        try:
            f = bm.faces.new((v0, v1, v2, v3))
            f.material_index = MAT_MOUTH
        except ValueError:
            pass
MB.prim("mouth_teeth_lower", build_teeth_lower, "mouth_teeth", {"jaw": 1.0})

# tongue (fan facing -Y, rides the lower jaw)
def build_tongue(bm):
    n = 10
    y = -0.055
    verts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        verts.append(bm.verts.new(Vector((0.016 * math.cos(a), y,
                                          1.556 + 0.009 * math.sin(a)))))
    center = bm.verts.new(Vector((0.0, y, 1.556)))
    for i in range(n):
        i2 = (i + 1) % n
        try:
            f = bm.faces.new((verts[i], verts[i2], center))
            f.material_index = MAT_MOUTH
        except ValueError:
            pass
MB.prim("mouth_tongue", build_tongue, "mouth_tongue", {"jaw": 1.0})

# ---- cable (secondary motion), backpack -> right hip
def cable_rings():
    pts = [(0.020, 0.100, 1.280), (0.045, 0.075, 1.150),
           (0.075, 0.045, 1.020), (0.095, 0.010, 0.940)]
    ts = [0.0, 0.33, 0.66, 1.0]
    def radii(t):
        return (0.006, 0.006)
    def weights(t):
        if t < 0.33:
            return w_two("cable_01", "cable_02", t / 0.33)
        if t < 0.66:
            return w_two("cable_02", "cable_03", (t - 0.33) / 0.33)
        return {"cable_03": 1.0}
    return path_rings(pts, ts, radii, MAT_SUIT, weights, island="suit_cable")
MB.tube("cable", cable_rings(), 10, MAT_SUIT, "suit_cable")

# ---- chest strap (diagonal bandolier)
def strap_rings():
    pts = [(-0.10, -0.108, 1.30), (-0.02, -0.110, 1.21), (0.10, -0.107, 1.12)]
    ts = [0.0, 0.5, 1.0]
    def radii(t):
        return (0.018, 0.006)
    def weights(t):
        return w_two("spine_03", "spine_02", t)
    return path_rings(pts, ts, radii, MAT_SUIT, weights, island="suit_strap_chest")
MB.tube("strap_chest", strap_rings(), 10, MAT_SUIT, "suit_strap_chest")

# ---- thigh strap (closed elliptical band hugging the left thigh)
def thigh_band_rings():
    rings = []
    cx, cy, cz = -0.105, -0.018, 0.72
    rx, rz = 0.0865, 0.0715
    n = 24
    pts = [Vector((cx + rx * math.cos(2 * math.pi * i / n),
                   cy + rz * math.sin(2 * math.pi * i / n), cz)) for i in range(n)]
    pts.append(pts[0].copy())
    for p in pts:
        rings.append(dict(c=p, rx=0.004, rz=0.009, mat=MAT_SUIT,
                          w={"thigh_L": 1.0}, t=0.0))
    return rings
MB.tube("strap_thigh", thigh_band_rings(), 8, MAT_SUIT, "suit_strap_thigh")

# ---- belt (closed elliptical band hugging the waist)
def belt_rings():
    rings = []
    cx, cy, cz = 0.0, 0.008, 1.035
    rx, rz = 0.176, 0.119
    n = 28
    pts = [Vector((cx + rx * math.cos(2 * math.pi * i / n),
                   cy + rz * math.sin(2 * math.pi * i / n), cz)) for i in range(n)]
    pts.append(pts[0].copy())
    for p in pts:
        rings.append(dict(c=p, rx=0.005, rz=0.011, mat=MAT_ARMOR,
                          w={"pelvis": 1.0}, t=0.0))
    return rings
MB.tube("belt", belt_rings(), 8, MAT_ARMOR, "armor_belt")

# ---- pauldrons (closed elliptical bands hugging the upper arms)
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    rings = []
    cx, cy, cz = 0.2087 * s, 0.0169 * s, 1.345
    rx, rz = 0.0645, 0.0605
    n = 24
    pts = [Vector((cx + rx * math.cos(2 * math.pi * i / n),
                   cy + rz * math.sin(2 * math.pi * i / n), cz)) for i in range(n)]
    pts.append(pts[0].copy())
    for p in pts:
        rings.append(dict(c=p, rx=0.005, rz=0.045, mat=MAT_ARMOR,
                          w={f"upper_arm_{side}": 1.0}, t=0.0))
    MB.tube(f"pauldron_{side}", rings, 8, MAT_ARMOR, f"armor_pauldron_{side}")

# ---- props (prims)
# chest plate
prim_box("chest_plate", 0.30, 0.040, 0.26, (0.0, -0.120, 1.27),
         (math.radians(-4), 0, 0), MAT_ARMOR, "armor_chest", {"spine_03": 1.0})
# backpack
prim_box("backpack", 0.26, 0.09, 0.30, (0.0, 0.175, 1.24),
         (math.radians(-6), 0, 0), MAT_ARMOR, "armor_backpack", {"spine_03": 1.0})
# knee pads (discs hugging the knee front, blended thigh/shin)
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    prim_cyl(f"knee_pad_{side}", 0.050, 0.08, 18, (0.105 * s, -0.055, 0.47), 'Z',
             MAT_ARMOR, f"armor_knee_{side}",
             {f"shin_{side}": 0.65, f"thigh_{side}": 0.35})
# shin guards
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    prim_box(f"shin_guard_{side}", 0.070, 0.026, 0.18, (0.105 * s, -0.075, 0.34),
             (math.radians(-6), 0, 0), MAT_ARMOR, f"armor_shin_{side}",
             {f"shin_{side}": 1.0})
# cell holster (left hip) + fresh cell + its core
prim_box("cell_holster", 0.036, 0.026, 0.042, (-0.196, 0.020, 0.905),
         (0, 0, math.radians(15)), MAT_ARMOR, "armor_holster", {"pelvis": 1.0})
prim_box("cell_new", 0.028, 0.018, 0.045, (-0.199, 0.022, 0.933),
         (0, 0, 0), MAT_CYBER, "cyber_cell_body", {"cell_new": 1.0})
prim_box("cell_new_core", 0.012, 0.006, 0.018, (-0.199, 0.022, 0.9645),
         (0, 0, 0), MAT_EMISSIVE, "emis_cell_core", {"cell_new": 1.0})
# spent cell in the emitter slot (lateral right forearm) + its core
prim_box("cell_spent", 0.018, 0.028, 0.045, (0.282, 0.015, 0.80),
         (0, 0, 0), MAT_CYBER, "cyber_cell_body", {"cell_spent": 1.0})
prim_box("cell_spent_core", 0.006, 0.012, 0.030, (0.291, 0.015, 0.80),
         (0, 0, 0), MAT_EMISSIVE, "emis_cell_core", {"cell_spent": 1.0})
# wrist emitter: barrel hugging the dorsal (+Y) side of the distal forearm, axis Z,
# muzzle distal (low z). Emissive caps.
prim_cyl("emitter", 0.022, 0.075, 16, (0.245, 0.055, 0.815), 'Z',
         MAT_CYBER, "cyber_emitter_body", {"emitter": 1.0},
         mat_caps=MAT_EMISSIVE, mat_islands={MAT_EMISSIVE: "emis_emitter"})
# emitter muzzle core (just distal of the barrel face)
prim_cyl("emitter_core", 0.013, 0.014, 12, (0.245, 0.055, 0.770), 'Z',
         MAT_EMISSIVE, "emis_emitter", {"emitter": 1.0})
# blade shroud (ventral -Y side of the forearm, axis Z) + retracted blade + edge
prim_cyl("blade_shroud", 0.017, 0.10, 12, (0.245, -0.050, 0.85), 'Z',
         MAT_CYBER, "cyber_shroud", {"forearm_R": 1.0})
prim_box("blade", 0.012, 0.007, 0.09, (0.245, -0.050, 0.85),
         (0, 0, 0), MAT_ARMOR, "armor_blade", {"blade": 1.0})
prim_box("blade_edge", 0.014, 0.0015, 0.08, (0.245, -0.0545, 0.85),
         (0, 0, 0), MAT_EMISSIVE, "emis_blade_edge", {"blade": 1.0})
# beacon on the backpack + core
prim_cyl("beacon", 0.030, 0.018, 14, (0.0, 0.215, 1.36), 'Z',
         MAT_ARMOR, "armor_beacon", {"beacon": 1.0})
prim_cyl("beacon_core", 0.014, 0.008, 10, (0.0, 0.215, 1.373), 'Z',
         MAT_EMISSIVE, "emis_beacon", {"beacon": 1.0})
# headset band: curved strap hugging the skull +6 mm, following the head ring at
# t=0.56 (same frame the head tube uses there) over the back of the head,
# theta 12..168 deg (back 90 +/- 78). The arc ends embed inside the earpieces.
_idx56 = [r["t"] for r in head_r].index(0.56)
_b56 = head_r[_idx56]
_T56 = head_r[_idx56 + 1]["c"] - head_r[_idx56 - 1]["c"]
ring_arc_band("headset_band", _b56["c"], _b56["rx"], _b56["rz"], _T56,
              12.0, 168.0, 15, 0.006, 0.0045, 0.0055, 8, MAT_ARMOR,
              "armor_headset", {"head": 1.0})
# visor: curved emissive band following a virtual head ring at t=0.71 (forehead),
# using the t=0.78 ring's frame (T = c(0.89) - c(0.65), the central difference
# bm_tube uses for that ring), theta 198..342 deg (front 270 +/- 72), pushed 2.5 mm
# off the skull. Front center lands at z~1.7126, between brow top (1.688) and
# fringe front (1.739).
_v71 = head_ring_at(0.71)
_idx78 = [r["t"] for r in head_r].index(0.78)
_T78 = head_r[_idx78 + 1]["c"] - head_r[_idx78 - 1]["c"]
ring_arc_band("visor", _v71["c"], _v71["rx"], _v71["rz"], _T78,
              198.0, 342.0, 15, 0.0025, 0.0035, 0.0090, 8, MAT_EMISSIVE,
              "emis_visor", {"head": 1.0})
for side in ('L', 'R'):
    s = -1.0 if side == 'L' else 1.0
    prim_cyl(f"earpiece_{side}", 0.018, 0.012, 12, (0.088 * s, 0.005, 1.655), 'X',
             MAT_CYBER, "cyber_earpiece", {"head": 1.0})

print("PARTS:", len(MB.part_log))

# ===================================================================== textures
def ones_like(x):
    return np.ones_like(x) if HAVE_NUMPY else 1.0

def paint_island_np(mat):
    """Return painter(lu, lv, iid) -> (r,g,b,a) numpy arrays (lu, lv in [0,1])."""
    if mat == MAT_SKIN:
        def skin_p(lu, lv, iid):
            n = vnoise(lu * 24, lv * 24, seed=stable_hash(iid) % 1000)
            n2 = vnoise(lu * 90, lv * 90, seed=(stable_hash(iid + "x") % 977) + 7)
            r = 0.72 * (0.96 + 0.08 * n)
            g = 0.55 * (0.94 + 0.10 * n2)
            b = 0.44 * (0.92 + 0.12 * n)
            if iid == "skin_lips":
                r = r * 1.18; g = g * 0.80; b = b * 0.76
            a = np.ones_like(r)
            return r, g, b, a
        return skin_p
    if mat == MAT_SUIT:
        def suit_p(lu, lv, iid):
            n = vnoise(lu * 30, lv * 30, seed=stable_hash(iid) % 1000)
            r = 0.075 * (0.9 + 0.25 * n)
            g = 0.085 * (0.9 + 0.25 * n)
            b = 0.105 * (0.9 + 0.3 * n)
            if iid == "suit_torso":
                vshape = np.abs(lu - 0.5) * 2.0
                m = (lv > 0.45) & (lv < 0.75) & (vshape < 0.35)
                r = np.where(m, r * 1.35, r)
                g = np.where(m, g * 1.30, g)
                b = np.where(m, b * 1.25, b)
            a = np.ones_like(r)
            return r, g, b, a
        return suit_p
    if mat == MAT_ARMOR:
        def armor_p(lu, lv, iid):
            n = vnoise(lu * 20, lv * 20, seed=stable_hash(iid) % 1000)
            edge = vnoise(lu * 60, lv * 60, seed=(stable_hash(iid) % 877) + 5)
            panel = (((lu * 8) % 1.0 < 0.06) | ((lv * 8) % 1.0 < 0.06)).astype(np.float64)
            k = (0.85 + 0.3 * n) * (0.6 + 0.4 * (1 - panel))
            r = 0.16 * k; g = 0.17 * k; b = 0.19 * k
            hi = edge > 0.97
            r = np.where(hi, 0.35, r); g = np.where(hi, 0.36, g); b = np.where(hi, 0.38, b)
            a = np.ones_like(r)
            return r, g, b, a
        return armor_p
    if mat == MAT_CYBER:
        def cyber_p(lu, lv, iid):
            n = vnoise(lu * 26, lv * 26, seed=stable_hash(iid) % 1000)
            groove = ((lv * 12) % 1.0 < 0.05).astype(np.float64)
            k = (0.9 + 0.2 * n) * (0.55 + 0.45 * (1 - groove))
            r = 0.13 * k; g = 0.15 * k; b = 0.17 * k
            if iid.startswith("cyber_forearm"):
                seam = ((lu * 10) % 1.0 < 0.03)
                r = np.where(seam, 0.20, r)
                g = np.where(seam, 0.90, g)
                b = np.where(seam, 0.85, b)
            a = np.ones_like(r)
            return r, g, b, a
        return cyber_p
    if mat == MAT_EMISSIVE:
        def emis_p(lu, lv, iid):
            n = vnoise(lu * 10, lv * 10, seed=stable_hash(iid) % 1000)
            pul = 0.85 + 0.15 * n
            if "beacon" in iid or "cell" in iid:
                col = (0.20, 0.95, 0.90)
            elif "blade" in iid:
                col = (0.35, 0.95, 1.00)
            else:
                col = (0.25, 0.90, 0.85)
            a = np.ones_like(pul)
            return col[0] * pul, col[1] * pul, col[2] * pul, a
        return emis_p
    if mat == MAT_HAIR:
        def hair_p(lu, lv, iid):
            n = vnoise(lu * 40, lv * 40, seed=3)
            strand = vnoise(lu * 200, lv * 8, seed=11)
            f = (0.8 + 0.5 * n) * (0.7 + 0.6 * strand)
            a = np.ones_like(f)
            return 0.09 * f, 0.065 * f, 0.045 * f, a
        return hair_p
    if mat == MAT_EYE:
        def eye_p(lu, lv, iid):
            # sphere UV: u=0.25 is the -Y (front) direction where the iris belongs
            du = ((lu - 0.25 + 0.5) % 1.0) - 0.5
            dv = lv - 0.5
            rad = np.sqrt(du * du + dv * dv) * 2.0
            n = vnoise(lu * 60, lv * 60, seed=5)
            r = np.full_like(rad, 0.92); g = np.full_like(rad, 0.90); b = np.full_like(rad, 0.88)
            iris = (rad >= 0.10) & (rad < 0.24)
            r = np.where(iris, 0.15 + 0.1 * n, r)
            g = np.where(iris, 0.75, g)
            b = np.where(iris, 0.85, b)
            pupil = rad < 0.10
            r = np.where(pupil, 0.02, r); g = np.where(pupil, 0.02, g); b = np.where(pupil, 0.03, b)
            limbal = (rad >= 0.24) & (rad < 0.29)
            r = np.where(limbal, 0.05, r); g = np.where(limbal, 0.05, g); b = np.where(limbal, 0.06, b)
            a = np.ones_like(rad)
            return r, g, b, a
        return eye_p
    if mat == MAT_MOUTH:
        def mouth_p(lu, lv, iid):
            if iid == "mouth_tongue":
                n = vnoise(lu * 30, lv * 30, seed=9)
                return 0.55 * (0.9 + 0.2 * n), np.full_like(n, 0.16), np.full_like(n, 0.14), np.ones_like(n)
            if iid == "mouth_teeth":
                n = vnoise(lu * 80, lv * 40, seed=13)
                v = 0.85 * (0.95 + 0.05 * n)
                return v, 0.82 * (0.95 + 0.05 * n), 0.78 * (0.95 + 0.05 * n), np.ones_like(n)
            return (np.full_like(lu, 0.05), np.full_like(lu, 0.02),
                    np.full_like(lu, 0.025), np.ones_like(lu))
        return mouth_p
    return lambda lu, lv, iid: (np.full_like(lu, 0.5), np.full_like(lu, 0.5),
                                np.full_like(lu, 0.5), np.ones_like(lu))

def rough_painter(mat):
    base = {MAT_SKIN: 0.55, MAT_SUIT: 0.78, MAT_ARMOR: 0.42, MAT_CYBER: 0.30,
            MAT_EMISSIVE: 0.15, MAT_HAIR: 0.92, MAT_EYE: 0.12, MAT_MOUTH: 0.5}[mat]
    def rough_p(lu, lv, iid):
        n = vnoise(lu * 40, lv * 40, seed=(stable_hash(iid) % 500) + mat * 31)
        v = base * (0.9 + 0.2 * n)
        return v, v, v, np.ones_like(v)
    return rough_p

def norm_painter(lu, lv, iid):
    n1 = vnoise(lu * 50, lv * 50, seed=1)
    n2 = vnoise(lu * 50 + 100, lv * 50, seed=2)
    r = 0.5 + (n1 - 0.5) * 0.06
    g = 0.5 + (n2 - 0.5) * 0.06
    return r, g, np.ones_like(r), np.ones_like(r)

def team_painter(lu, lv, iid):
    vshape = np.abs(lu - 0.5) * 2.0
    band = (lv > 0.35) & (lv < 0.85)
    if iid in CHEVRON_ISLANDS:
        a = np.where(band & (vshape < (lv - 0.35) / 0.5 * 0.5 + 0.1), 1.0, 0.0)
        b = np.where(band & (vshape < (0.85 - lv) / 0.5 * 0.5 + 0.1), 1.0, 0.0)
    else:
        a = np.zeros_like(lu); b = np.zeros_like(lu)
    return a, b, np.zeros_like(lu), np.ones_like(lu)

def save_png_array(path, arr):
    """arr: (size, size, 4) float32 array, row 0 = image bottom."""
    size = arr.shape[0]
    img = bpy.data.images.new(os.path.basename(path), width=size, height=size,
                              alpha=True, float_buffer=False)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return path

def gen_material_textures():
    texinfo = {}
    for mat in range(8):
        name = MAT_NAMES[mat]
        islands = ISLANDS[mat]
        if not islands:
            continue
        g0 = ISLAND_GRID[islands[0]]
        cols, rows, size = g0["cols"], g0["rows"], g0["size"]
        cw, ch = size // cols, size // rows
        painter = paint_island_np(mat)
        rp = rough_painter(mat)
        bc = np.zeros((size, size, 4), dtype=np.float32)
        rg = np.zeros((size, size, 4), dtype=np.float32)
        nm = np.zeros((size, size, 4), dtype=np.float32)
        for idx, iid in enumerate(islands):
            col, row = idx % cols, idx // cols
            ys, xs = np.mgrid[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw].astype(np.float64)
            lu = (xs - col * cw) / cw
            lv = (ys - row * ch) / ch
            r, g, b, a = painter(lu, lv, iid)
            bc[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 0] = r
            bc[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 1] = g
            bc[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 2] = b
            bc[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 3] = a
            r, g, b, a = rp(lu, lv, iid)
            rg[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 0] = r
            rg[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 1] = g
            rg[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 2] = b
            rg[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 3] = a
            if mat != MAT_EMISSIVE:
                r, g, b, a = norm_painter(lu, lv, iid)
                nm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 0] = r
                nm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 1] = g
                nm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 2] = b
                nm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 3] = a
        save_png_array(os.path.join(TEXDIR, f"{name}_BC.png"), bc)
        save_png_array(os.path.join(TEXDIR, f"{name}_R.png"), rg)
        if mat != MAT_EMISSIVE:
            save_png_array(os.path.join(TEXDIR, f"{name}_N.png"), nm)
        texinfo[name] = dict(size=size, cols=cols, rows=rows,
                             islands=islands,
                             raw_bytes=size * size * 4 * (3 if mat != MAT_EMISSIVE else 2))
    # team mask textures (R = team A chevron, G = team B chevron)
    for name, mat in (("Suit", MAT_SUIT), ("Armor", MAT_ARMOR)):
        islands = ISLANDS[mat]
        g0 = ISLAND_GRID[islands[0]]
        cols, rows, size = g0["cols"], g0["rows"], g0["size"]
        cw, ch = size // cols, size // rows
        tm = np.zeros((size, size, 4), dtype=np.float32)
        for idx, iid in enumerate(islands):
            col, row = idx % cols, idx // cols
            ys, xs = np.mgrid[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw].astype(np.float64)
            lu = (xs - col * cw) / cw
            lv = (ys - row * ch) / ch
            r, g, b, a = team_painter(lu, lv, iid)
            tm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 0] = r
            tm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 1] = g
            tm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 2] = b
            tm[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw, 3] = a
        save_png_array(os.path.join(TEXDIR, f"{name}_TeamMask.png"), tm)
        texinfo[name + "_TeamMask"] = dict(size=size, cols=cols, rows=rows,
                                           raw_bytes=size * size * 4)
    return texinfo

texinfo = gen_material_textures()
print("TEXTURES done", {k: v["size"] for k, v in texinfo.items()})

# ===================================================================== materials
mat_defs = [
    (MAT_SKIN, "Skin", (0.72, 0.55, 0.44), 0.55, 0.0, None, 0.0, None),
    (MAT_SUIT, "Suit", (0.075, 0.085, 0.105), 0.78, 0.0, None, 0.0, "Suit_TeamMask.png"),
    (MAT_ARMOR, "Armor", (0.16, 0.17, 0.19), 0.42, 0.35, None, 0.0, "Armor_TeamMask.png"),
    (MAT_CYBER, "CyberMetal", (0.13, 0.15, 0.17), 0.30, 0.6, None, 0.0, None),
    (MAT_EMISSIVE, "Emissive", (0.25, 0.9, 0.85), 0.15, 0.0, (0.25, 0.9, 0.85), 4.0, None),
    (MAT_HAIR, "Hair", (0.09, 0.065, 0.045), 0.92, 0.0, None, 0.0, None),
    (MAT_EYE, "Eye", (0.9, 0.9, 0.88), 0.12, 0.0, None, 0.0, None),
    (MAT_MOUTH, "Mouth", (0.8, 0.75, 0.7), 0.5, 0.0, None, 0.0, None),
]
materials = {}
for idx, name, bc, rough, metal, emis, estr, teammask in mat_defs:
    m = make_material(name, bc, rough, metallic=metal, emissive_color=emis,
                      emissive_strength=estr, tex_prefix=name, tex_dir=TEXDIR,
                      team_mask=teammask, team_color=TEAM_COLORS["A"])
    materials[idx] = m

# ===================================================================== finish mesh
obj = MB.finish("Operative")
me = obj.data
for i in range(8):
    me.materials.append(materials[i])
vgroup(obj, "root")  # empty group so vertex groups match the 79 bone names exactly
print("MESH verts:", len(me.vertices), "faces:", len(me.polygons))

# ===================================================================== rig spec + verify
def build_bone_spec():
    B = []
    def add(name, head, tail, parent):
        B.append(dict(name=name, head=[round(x, 6) for x in head],
                      tail=[round(x, 6) for x in tail], parent=parent))
    add("root", (0, 0, 0), (0, 0, 0.10), None)
    add("pelvis", (0, 0, 0.955), (0, 0.005, 1.045), "root")
    add("spine_01", (0, 0.005, 1.045), (0, 0.010, 1.175), "pelvis")
    add("spine_02", (0, 0.010, 1.175), (0, 0.015, 1.315), "spine_01")
    add("spine_03", (0, 0.015, 1.315), (0, 0.022, 1.420), "spine_02")
    add("neck_01", (0, 0.020, 1.435), (0, 0.022, 1.500), "spine_03")
    add("neck_02", (0, 0.022, 1.500), (0, 0.018, 1.552), "neck_01")
    add("head", (0, 0.015, 1.560), (0, -0.005, 1.720), "neck_02")
    add("jaw", (0, -0.030, 1.590), (0, -0.062, 1.548), "head")
    for side, s in (("L", -1.0), ("R", 1.0)):
        # eye/lid bones: identity rotation (local X = world X, Y = world +Y along a
        # +Y tail into the head, length 0.014) so pose rotation_euler.x = world-X
        # rotation (blink / eye pitch) and rotation_euler.z = yaw when the head is
        # unrotated. Brow bones: tail +Z (local Y = world +Z) for translate
        # raise/lower (pose location).
        add(f"eye_{side}", (EYE_X * s, EYE_CY, EYE_CZ), (EYE_X * s, EYE_CY + 0.014, EYE_CZ), "head")
        add(f"lid_upper_{side}", (EYE_X * s, EYE_CY, EYE_CZ), (EYE_X * s, EYE_CY + 0.014, EYE_CZ), "head")
        add(f"lid_lower_{side}", (EYE_X * s, EYE_CY, EYE_CZ), (EYE_X * s, EYE_CY + 0.014, EYE_CZ), "head")
        add(f"brow_{side}", (0.0465 * s, -0.109, 1.682), (0.0465 * s, -0.109, 1.702), "head")
        add(f"clavicle_{side}", (0.0, 0.018, 1.420), (0.16 * s, 0.020, 1.415), "spine_03")
        ua_h = Vector((0.205 * s, 0.018 * s, 1.385)); ua_t = Vector((0.232 * s, 0.008 * s, 1.075))
        add(f"upper_arm_{side}", ua_h, ua_t, f"clavicle_{side}")
        add(f"upper_arm_twist_{side}", ua_h.lerp(ua_t, 0.35), ua_h.lerp(ua_t, 0.65),
            f"upper_arm_{side}")
        fa_h = ua_t; fa_t = Vector((0.233 * s, 0.0, 0.775))
        add(f"forearm_{side}", fa_h, fa_t, f"upper_arm_{side}")
        add(f"forearm_twist_{side}", fa_h.lerp(fa_t, 0.35), fa_h.lerp(fa_t, 0.65),
            f"forearm_{side}")
        hand_h = fa_t; hand_t = Vector((0.248 * s, -0.030 * s, 0.700))
        add(f"hand_{side}", hand_h, hand_t, f"forearm_{side}")
        for fname, spec in FINGER_SPECS.items():
            p0, p1, p2, p3 = finger_path(side, spec)
            add(f"f_{fname}_01_{side}", p0, p1, f"hand_{side}")
            add(f"f_{fname}_02_{side}", p1, p2, f"f_{fname}_01_{side}")
            add(f"f_{fname}_03_{side}", p2, p3, f"f_{fname}_02_{side}")
        th_h = Vector((0.105 * s, -0.010, 0.925)); th_t = Vector((0.105 * s, -0.022, 0.478))
        add(f"thigh_{side}", th_h, th_t, "pelvis")
        add(f"thigh_twist_{side}", th_h.lerp(th_t, 0.35), th_h.lerp(th_t, 0.65), f"thigh_{side}")
        sh_h = th_t; sh_t = Vector((0.105 * s, -0.035, 0.105))
        add(f"shin_{side}", sh_h, sh_t, f"thigh_{side}")
        add(f"shin_twist_{side}", sh_h.lerp(sh_t, 0.35), sh_h.lerp(sh_t, 0.65), f"shin_{side}")
        ft_h = Vector((0.105 * s, -0.035, 0.075)); ft_t = Vector((0.105 * s, -0.175, 0.040))
        add(f"foot_{side}", ft_h, ft_t, f"shin_{side}")
        add(f"toe_{side}", ft_t, Vector((0.105 * s, -0.205, 0.028)), f"foot_{side}")
    add("emitter", (0.245, 0.055, 0.850), (0.245, 0.055, 0.780), "forearm_R")
    add("blade", (0.245, -0.050, 0.850), (0.245, -0.050, 0.800), "forearm_R")
    add("cell_new", (-0.199, 0.022, 0.910), (-0.199, 0.022, 0.955), "root")
    add("cell_spent", (0.282, 0.015, 0.7775), (0.282, 0.015, 0.8225), "root")
    add("beacon", (0, 0.215, 1.351), (0, 0.215, 1.369), "root")
    add("cable_01", (0.020, 0.100, 1.280), (0.045, 0.075, 1.150), "spine_03")
    add("cable_02", (0.045, 0.075, 1.150), (0.075, 0.045, 1.020), "cable_01")
    add("cable_03", (0.075, 0.045, 1.020), (0.095, 0.010, 0.940), "pelvis")
    return B

BONES = build_bone_spec()
BONE_NAMES = {b["name"] for b in BONES}

SOCKETS = [
    dict(name="weapon_r", bone="emitter", offset=(0.0, 0.0, -0.0725),
         note="emitter muzzle face; +Y of the socket points along the barrel (distal)"),
    dict(name="blade_base", bone="blade", offset=(0.0, 0.0, 0.0)),
    dict(name="blade_tip", bone="blade", offset=(0.0, 0.0, -0.045)),
    dict(name="hand_l", bone="hand_L", offset=(0.0, -0.015, -0.045)),
    dict(name="hand_r", bone="hand_R", offset=(0.0, -0.015, -0.045)),
    dict(name="head", bone="head", offset=(0.0, 0.0, 0.0)),
    dict(name="eye", bone="head", offset=(0.0, -0.110, 0.085)),
    dict(name="cell_holster", bone="cell_new", offset=(0.0, 0.0, 0.0)),
    dict(name="cell_emitter", bone="cell_spent", offset=(0.0, 0.0, 0.0)),
    dict(name="beacon", bone="beacon", offset=(0.0, 0.0, 0.0)),
    dict(name="backpack", bone="spine_03", offset=(0.0, 0.160, -0.075)),
    dict(name="muzzle_flash", bone="emitter", offset=(0.0, 0.0, -0.080)),
]

rig_spec = {
    "units": "meters (Blender) -> centimeters (Unreal, x100)",
    "convention": "character faces -Y, up +Z, right +X; feet at Z=0; height ~1.80 m",
    "fps": FPS,
    "materials": [dict(index=i, name=MAT_NAMES[i]) for i in range(8)],
    "bones": BONES,
    "sockets": SOCKETS,
    "islands": {iid: ISLAND_GRID[iid] for iid in ISLAND_GRID},
    "finger_paths": {side: {fn: [list(p) for p in finger_path(side, spec)]
                            for fn, spec in FINGER_SPECS.items()}
                     for side in ('L', 'R')},
    "mouth_center": list(MOUTH_C),
    "texture_info": texinfo,
}
with open(os.path.join(WORK, "rig_spec.json"), "w") as f:
    json.dump(rig_spec, f, indent=1)
print("RIG SPEC bones:", len(BONES))

# ===================================================================== verification
report = {"objects": {}, "checks": {}}
total_tris = 0
total_verts = 0
groups = set()
for o in [obj]:
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    total_tris += tris
    total_verts += len(me.vertices)
    # weights
    max_infl = 0
    bad_weight = 0
    wmin, wmax = 9.0, -9.0
    for v in me.vertices:
        tot = 0.0
        cnt = 0
        for g in o.vertex_groups:
            try:
                w = g.weight(v.index)
            except RuntimeError:
                continue
            if w > 1e-6:
                tot += w
                cnt += 1
        max_infl = max(max_infl, cnt)
        wmin = min(wmin, tot); wmax = max(wmax, tot)
        if abs(tot - 1.0) > 1e-3:
            bad_weight += 1
    groups = {g.name for g in o.vertex_groups}
    # uvs
    uv = me.uv_layers.active
    uvs = [tuple(uv.data[li].uv) for li in range(len(me.loops))]
    umin = min(min(u, v) for u, v in uvs)
    umax = max(max(u, v) for u, v in uvs)
    # degenerate faces
    degen = sum(1 for p in me.polygons if p.area < 1e-10)
    # bounds
    vs = [v.co for v in me.vertices]
    bmin = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    bmax = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    # material slots used
    mats_used = sorted({p.material_index for p in me.polygons})
    report["objects"][o.name] = dict(
        verts=len(me.vertices), faces=len(me.polygons), triangles=tris,
        material_slots=len(me.materials), materials_used=mats_used,
        weight_min=round(wmin, 5), weight_max=round(wmax, 5),
        verts_off_weight=bad_weight, max_influences=max_infl,
        uv_min=round(umin, 5), uv_max=round(umax, 5),
        degenerate_faces=degen,
        bounds_min=[round(x, 4) for x in bmin], bounds_max=[round(x, 4) for x in bmax])

# bmesh-level topology checks on a fresh bmesh from the mesh
import bmesh as _bm
bmc = _bm.new()
bmc.from_mesh(me)
boundary = sum(1 for e in bmc.edges if e.is_boundary)
nonmanifold = sum(1 for e in bmc.edges if len(e.link_faces) > 2)
loose = sum(1 for v in bmc.verts if not v.link_faces)
bmc.free()

# group check
extra_groups = sorted(groups - BONE_NAMES)
missing_groups = sorted(BONE_NAMES - groups)
report["checks"] = dict(
    total_triangles=total_tris, total_verts=total_verts,
    boundary_edges=boundary, nonmanifold_edges=nonmanifold, loose_verts=loose,
    vertex_groups=len(groups), extra_groups=extra_groups,
    groups_without_weights=missing_groups,
    material_slots=len(me.materials),
    tri_cap_LOD0=80000, tri_ok_LOD0=total_tris <= 80000,
    height_m=round(report["objects"]["Operative"]["bounds_max"][2], 4),
)
report["parts"] = MB.part_log
with open(os.path.join(WORK, "gen01_report.json"), "w") as f:
    json.dump(report, f, indent=1)

print("TOTAL tris:", total_tris, "verts:", total_verts)
print("BOUNDARY edges:", boundary, "NONMANIFOLD:", nonmanifold, "LOOSE:", loose)
print("GROUPS:", len(groups), "extra:", extra_groups, "missing:", missing_groups)
print("UV range:", umin, umax, "weights:", wmin, wmax, "max infl:", max_infl)
print("BOUNDS:", report["objects"]["Operative"]["bounds_min"],
      report["objects"]["Operative"]["bounds_max"])

# ===================================================================== save
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print("SAVED", BLEND)
print("GEN1_DONE")

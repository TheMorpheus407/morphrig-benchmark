"""Measure the Operative head-skin surface profile (head tube only, no face prims)
to place the eyes/lids/brows, and check the crown height (SPEC: 1.80 m exactly).

Builds the head tube (and hair shell) exactly as gen_01 does, in two variants:
  current   - as gen_01 currently builds it
  fix_crown - with horizontal (T=+Z) rings for t >= 0.78 so nothing exceeds z=1.80
Raycasts a grid of horizontal rays from -Y and reports the skin surface y(x, z).
Then opens source/Operative.blend and reports the full-mesh bounds + first hits.
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(HERE)
GEN = os.path.join(TASK, "source", "generators")
sys.path.insert(0, GEN)
from morphrig_lib import (lerp, smoothstep, bm_tube,
                          MAT_SKIN, MAT_HAIR, reset_scene)


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


def head_rings(fix_crown):
    pts = [(0.0, 0.018, 1.435), (0.0, 0.016, 1.50), (0.0, 0.012, 1.545),
           (0.0, 0.008, 1.556), (0.0, 0.016, 1.565), (0.0, -0.005, 1.60),
           (0.0, -0.015, 1.63), (0.0, -0.025, 1.66), (0.0, -0.028, 1.70),
           (0.0, -0.020, 1.74), (0.0, -0.005, 1.775), (0.0, 0.010, 1.800)]
    ts = [0.0, 0.09, 0.18, 0.24, 0.30, 0.38, 0.47, 0.56, 0.65, 0.78, 0.89, 1.0]

    def radii(t):
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

    def weights(t):
        if t < 0.10:
            return w_two("neck_01", "neck_02", t / 0.10)
        if t < 0.18:
            return {"neck_02": 1.0}
        if t < 0.28:
            return w_two("neck_02", "jaw", (t - 0.18) / 0.10)
        if t < 0.34:
            return w_two("jaw", "head", (t - 0.28) / 0.06)
        return {"head": 1.0}

    rings = path_rings(pts, ts, radii, MAT_SKIN, weights, island="skin_head")
    rings[-1]["T"] = (0.0, 0.0, 1.0)
    if fix_crown:
        for r in rings:
            if r["t"] >= 0.78 - 1e-9:
                r["T"] = (0.0, 0.0, 1.0)
    return rings


def hair_rings_of(head_r, fix_crown):
    hair_src = [r for r in head_r if r["t"] >= 0.65 - 1e-9]
    first = head_r[[r["t"] for r in head_r].index(0.65)]
    hair_rings = [dict(c=first["c"].copy(), rx=first["rx"], rz=first["rz"],
                       mat=MAT_HAIR, w={"head": 1.0}, t=0.65)]
    for r in hair_src:
        hair_rings.append(dict(c=r["c"].copy(), rx=r["rx"] * 1.07, rz=r["rz"] * 1.07,
                               mat=MAT_HAIR, w={"head": 1.0}, t=r["t"]))
    hair_rings[-1]["T"] = (0.0, 0.0, 1.0)
    if fix_crown:
        for r in hair_rings:
            if r["t"] >= 0.78 - 1e-9:
                r["T"] = (0.0, 0.0, 1.0)
    return hair_rings


sc = reset_scene()


def build_obj(name, rings, segs, mat, cap_end):
    bm = bmesh.new()
    bm_tube(bm, rings, segs, mat, cap_end=cap_end)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    sc.collection.objects.link(obj)
    return obj


XS = [0.0, 0.02, 0.04, 0.052, 0.055, 0.07, 0.085]
ZS = [1.556, 1.565, 1.575, 1.590, 1.605, 1.615, 1.630, 1.640, 1.645, 1.650,
      1.655, 1.660, 1.665, 1.670, 1.675, 1.680, 1.682, 1.685, 1.690, 1.695,
      1.700, 1.705, 1.710, 1.740, 1.775, 1.795]


def profile(obj, xs, zs):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, dg)
    out = {}
    for z in zs:
        row = []
        for x in xs:
            loc, nrm, idx, dist = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)))
            row.append(None if loc is None else round(loc.y, 5))
        out[round(z, 4)] = row
    return out


def bounds(obj):
    vs = [v.co for v in obj.data.vertices]
    return [round(min(v.x for v in vs), 4), round(max(v.x for v in vs), 4),
            round(min(v.y for v in vs), 4), round(max(v.y for v in vs), 4),
            round(min(v.z for v in vs), 4), round(max(v.z for v in vs), 4)]


result = {}
for fix in (False, True):
    hr = head_rings(fix)
    hair_r = hair_rings_of(hr, fix)
    ho = build_obj("HeadFix%d" % int(fix), hr, 34, MAT_SKIN, True)
    ha = build_obj("HairFix%d" % int(fix), hair_r, 28, MAT_HAIR, True)
    prof = profile(ho, XS, ZS)
    key = "fix_crown" if fix else "current"
    result[key] = dict(head_bounds=bounds(ho), hair_bounds=bounds(ha), profile=prof)

    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(ho, dg)

    def at(x, z):
        loc, nrm, idx, dist = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)))
        return None if loc is None else round(loc.y, 5)

    result[key]["key"] = dict(
        S_eye=at(0.055, 1.645), S_brow=at(0.052, 1.682),
        skin_eye_top_1p6515=at(0.055, 1.6515), skin_eye_top_1p6548=at(0.055, 1.6548),
        skin_eye_top_1p6578=at(0.055, 1.6578), skin_eye_bot_1p6325=at(0.055, 1.6325),
        skin_visor=at(0.0, 1.688), skin_forehead=at(0.0, 1.70),
        skin_hairline=at(0.0, 1.705), skin_brow_top=at(0.052, 1.689),
        skin_brow_bot=at(0.052, 1.675))
    result[key]["brow_pts"] = {str(x): at(x, 1.682)
                               for x in (0.018, 0.030, 0.045, 0.060, 0.075, 0.0465)}
    result[key]["lid_pts"] = {str(z): at(0.055, z)
                              for z in (1.6385, 1.6391, 1.6352, 1.6322, 1.6507)}
    for o in (ho, ha):
        bpy.data.objects.remove(o, do_unlink=True)

print("MEASURE_HEAD_JSON=" + json.dumps(result, indent=1))

# ---- full mesh checks on the saved blend
BLEND = os.path.join(TASK, "source", "Operative.blend")
bpy.ops.wm.open_mainfile(filepath=BLEND)
obj = bpy.data.objects["Operative"]
me = obj.data
vs = [v.co for v in me.vertices]
print("FULL bounds", [round(min(v.x for v in vs), 4), round(max(v.x for v in vs), 4),
      round(min(v.y for v in vs), 4), round(max(v.y for v in vs), 4),
      round(min(v.z for v in vs), 4), round(max(v.z for v in vs), 4)])
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
bvh = BVHTree.FromObject(obj, dg)
for (x, z) in [(0.055, 1.645), (0.052, 1.682), (0.0, 1.688), (0.0, 1.565),
               (0.055, 1.6515), (0.075, 1.645), (0.0, 1.645)]:
    loc, nrm, idx, dist = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)))
    mat = me.polygons[idx].material_index if (idx is not None and idx >= 0) else None
    print("FULL first hit", (x, z), None if loc is None else round(loc.y, 5), "mat", mat)
print("MEASURE_HEAD_DONE")

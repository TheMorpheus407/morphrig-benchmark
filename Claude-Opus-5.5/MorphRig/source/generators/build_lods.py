"""Stage L: generate LOD1 / LOD2 of every character mesh (runs after build_textures).

Usage:
  blender -b --factory-startup -P build_lods.py -- --in stageB.blend --out stageB.blend

* Collapse decimation of copies of all MR_* meshes.  Per object ratios; the face (eye patches,
  lid rings, lips, mouth interior) is protected through a vertex-group factor so eyelids and lip
  closure keep working.
* UVs, material slots and vertex-group weights survive decimation; weights are renormalised
  and limited to 4 influences.
* Facial shape keys are transferred to the decimated head: every LOD vertex takes the
  barycentric interpolation of the key deltas on its nearest LOD0 triangle.
Objects end up in collections MR_LOD1 / MR_LOD2 (hidden), named <name>_LOD1 / _LOD2, parented
to MR_Skeleton with an Armature modifier, so they animate and export exactly like LOD0.
"""
import sys
import os
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# target fraction of LOD0 triangles per object and level
RATIOS = {
    "MR_Head": (0.62, 0.30), "MR_Suit": (0.50, 0.24), "MR_Gear": (0.45, 0.20), "MR_CyberArm": (0.45, 0.20),
    "MR_HandL": (0.60, 0.32), "MR_Boot_L": (0.50, 0.25), "MR_Boot_R": (0.50, 0.25), "MR_Hair": (0.50, 0.25),
    "MR_HairTail": (0.55, 0.30), "MR_Mouth": (0.40, 0.18), "MR_Eye_L": (0.45, 0.22), "MR_Eye_R": (0.45, 0.22),
    "MR_PropCell": (0.55, 0.30), "MR_PropBeacon": (0.45, 0.22),
}
MAX_INF = 4


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def face_protect_group(ob, lod0):
    """Weight 1 around eyes / lids / lips / mouth interior (head only)."""
    from mr_params import H
    vg = ob.vertex_groups.new(name="_lod_protect")
    co = np.array([v.co for v in ob.data.vertices])
    w = np.zeros(len(co))
    for c, r in ((H["eye_l"], 0.024), (H["eye_r"], 0.024), (H["mouth"], 0.034)):
        d = np.linalg.norm(co - np.asarray(c), axis=1)
        w = np.maximum(w, np.clip(1.0 - (d - r) / 0.012, 0.0, 1.0))
    for i, val in enumerate(w):
        if val > 0:
            vg.add([i], float(val), 'REPLACE')
    return vg


def decimate(ob, ratio, protect=None):
    mod = ob.modifiers.new("lod", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = False
    if protect is not None:
        mod.vertex_group = protect.name
        mod.invert_vertex_group = True
        mod.vertex_group_factor = 6.0
    bpy.context.view_layer.objects.active = ob
    # the decimate must run before the armature modifier
    while ob.modifiers[0].name != "lod":
        bpy.ops.object.modifier_move_up(modifier="lod")
    bpy.ops.object.modifier_apply(modifier="lod")


def clean_weights(ob):
    names = [g.name for g in ob.vertex_groups if not g.name.startswith("_")]
    idx = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        ws = [(g.group, g.weight) for g in v.groups if not idx[g.group].startswith("_")]
        ws.sort(key=lambda t: -t[1])
        keep = [(gi, w) for gi, w in ws[:MAX_INF] if w > 0.005]
        tot = sum(w for _, w in keep) or 1.0
        drop = {gi for gi, _ in ws} - {gi for gi, _ in keep}
        for gi in drop:
            ob.vertex_groups[gi].remove([v.index])
        for gi, w in keep:
            ob.vertex_groups[gi].add([v.index], w / tot, 'REPLACE')
    for g in list(ob.vertex_groups):
        if g.name.startswith("_"):
            ob.vertex_groups.remove(g)


def transfer_shape_keys(src, dst):
    """Barycentric transfer of all shape keys from src (LOD0 head) to dst (decimated copy)."""
    sk = src.data.shape_keys
    if sk is None:
        return 0
    basis = np.array([p.co for p in sk.key_blocks[0].data])
    tris = []
    for poly in src.data.polygons:
        vs = list(poly.vertices)
        for k in range(1, len(vs) - 1):
            tris.append((vs[0], vs[k], vs[k + 1]))
    tris = np.array(tris)
    tree = BVHTree.FromPolygons([Vector(p) for p in basis], [tuple(t) for t in tris])
    dco = np.array([v.co for v in dst.data.vertices])
    bary = np.zeros((len(dco), 3))
    tid = np.zeros(len(dco), int)
    for i, p in enumerate(dco):
        loc, nrm_, fi, dist = tree.find_nearest(Vector(p))
        a, b, c = basis[tris[fi]]
        v0, v1, v2 = b - a, c - a, np.array(loc) - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        vv = (d11 * d20 - d01 * d21) / den if den else 0.0
        ww = (d00 * d21 - d01 * d20) / den if den else 0.0
        bary[i] = (1 - vv - ww, vv, ww)
        tid[i] = fi
    if dst.data.shape_keys is None:
        dst.shape_key_add(name="Basis", from_mix=False)
    corners = tris[tid]
    for kb in sk.key_blocks[1:]:
        D = np.array([p.co for p in kb.data]) - basis
        d = (D[corners] * bary[:, :, None]).sum(1)
        nk = dst.shape_key_add(name=kb.name, from_mix=False)
        nk.data.foreach_set("co", (dco + d).ravel())
        nk.slider_min, nk.slider_max, nk.value = 0.0, 1.0, 0.0
    return len(sk.key_blocks) - 1


def main():
    args = parse()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.inp))
    sc = bpy.context.scene
    arm = bpy.data.objects["MR_Skeleton"]
    report = {"LOD0": {}, "LOD1": {}, "LOD2": {}}
    for lvl in (1, 2):
        cname = f"MR_LOD{lvl}"
        old = bpy.data.collections.get(cname)
        if old:
            for o in list(old.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)
        col = bpy.data.collections.new(cname)
        sc.collection.children.link(col)
        for name, ratios in RATIOS.items():
            src = bpy.data.objects.get(name)
            if src is None:
                continue
            report["LOD0"][name] = tri_count(src)
            dup = src.copy()
            dup.data = src.data.copy()
            dup.name = f"{name}_LOD{lvl}"
            dup.data.name = dup.name
            col.objects.link(dup)
            dup.parent = arm
            if dup.data.shape_keys:
                dup.shape_key_clear()
            protect = face_protect_group(dup, src) if name == "MR_Head" else None
            # decimate in a few steps (more stable than one big collapse)
            target = ratios[lvl - 1]
            decimate(dup, target, protect)
            clean_weights(dup)
            if name == "MR_Head":
                n = transfer_shape_keys(src, dup)
                print("  shape keys transferred", n)
            report[f"LOD{lvl}"][name] = tri_count(dup)
            print(f"LOD{lvl} {name}: {report['LOD0'][name]} -> {report[f'LOD{lvl}'][name]} tris")
        col.hide_viewport = True
        col.hide_render = True
    tot = {k: int(sum(v.values())) for k, v in report.items()}
    print("LOD TOTALS", tot)
    sc["mr_lod_report"] = json.dumps({"per_object": report, "totals": tot})
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    print("SAVED", args.out)


if __name__ == "__main__":
    main()

"""Geometry helpers for the MorphRig generators (numpy + Blender bmesh). Meshes are plain arrays:
verts: (N,3) float64, faces: list of tuples of vertex indices. Attribute arrays are per-vertex numpy arrays."""
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector


# ----------------------------------------------------------------------------- conversion


def eval_mesh(ob):
    """Evaluated (modifiers applied) mesh of an object as (verts, faces)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    verts = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get('co', verts)
    verts = verts.reshape(-1, 3)
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get('vertex_index', loops)
    starts = np.empty(len(me.polygons), dtype=np.int64)
    sizes = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get('loop_start', starts)
    me.polygons.foreach_get('loop_total', sizes)
    faces = [tuple(loops[s:s + n]) for s, n in zip(starts, sizes)]
    ev.to_mesh_clear()
    return verts, faces


def make_object(name, verts, faces, collection=None, smooth=True, shade_auto=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in verts], [], [tuple(int(i) for i in f) for f in faces])
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def normals(verts, faces):
    """Area-weighted vertex normals."""
    n = np.zeros_like(verts)
    for f in faces:
        f = list(f)
        p = verts[f]
        # Newell normal
        nx = np.sum((p[:, 1] - np.roll(p[:, 1], -1)) * (p[:, 2] + np.roll(p[:, 2], -1)))
        ny = np.sum((p[:, 2] - np.roll(p[:, 2], -1)) * (p[:, 0] + np.roll(p[:, 0], -1)))
        nz = np.sum((p[:, 0] - np.roll(p[:, 0], -1)) * (p[:, 1] + np.roll(p[:, 1], -1)))
        fn = np.array([nx, ny, nz])
        for i in f:
            n[i] += fn
    l = np.linalg.norm(n, axis=1, keepdims=True)
    l[l < 1e-12] = 1.0
    return n / l


def adjacency(nverts, faces):
    adj = [set() for _ in range(nverts)]
    for f in faces:
        k = len(f)
        for i in range(k):
            a, b = f[i], f[(i + 1) % k]
            adj[a].add(b)
            adj[b].add(a)
    return [sorted(s) for s in adj]


def boundary_loops(nverts, faces):
    """Ordered boundary loops (lists of vertex indices) of an open mesh."""
    edge_count = {}
    directed = {}
    for f in faces:
        k = len(f)
        for i in range(k):
            a, b = f[i], f[(i + 1) % k]
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
            directed[(a, b)] = True
    nxt = {}
    for (a, b) in directed:
        key = (min(a, b), max(a, b))
        if edge_count[key] == 1:
            nxt[a] = b
    loops = []
    seen = set()
    for s in list(nxt.keys()):
        if s in seen:
            continue
        loop = [s]
        seen.add(s)
        cur = nxt[s]
        while cur != s and cur in nxt and cur not in seen:
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        loops.append(loop)
    return loops


def remove_faces(faces, kill):
    kill = set(kill)
    return [f for i, f in enumerate(faces) if i not in kill]


def compact(verts, faces, *attrs):
    """Drop unused vertices, remap faces and attribute arrays."""
    used = np.zeros(len(verts), dtype=bool)
    for f in faces:
        used[list(f)] = True
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(used.sum())
    nf = [tuple(int(remap[i]) for i in f) for f in faces]
    out = [verts[used]] + [a[used] for a in attrs]
    return (out[0], nf) + tuple(out[1:])


def merge(meshes):
    """Concatenate (verts, faces) pairs; returns verts, faces, offsets."""
    vs, fs, offs, o = [], [], [], 0
    for v, f in meshes:
        vs.append(v)
        fs.extend([tuple(i + o for i in face) for face in f])
        offs.append(o)
        o += len(v)
    return np.concatenate(vs), fs, offs


def weld(verts, faces, tol=1e-5, *attrs):
    """Merge coincident vertices (grid hashing)."""
    key = np.round(verts / tol).astype(np.int64)
    uniq = {}
    remap = np.empty(len(verts), dtype=np.int64)
    keep = []
    for i, k in enumerate(map(tuple, key)):
        j = uniq.get(k)
        if j is None:
            j = len(keep)
            uniq[k] = j
            keep.append(i)
        remap[i] = j
    nv = verts[keep]
    nf = []
    for f in faces:
        g = tuple(int(remap[i]) for i in f)
        if len(set(g)) == len(g):
            nf.append(g)
    return (nv, nf) + tuple(a[keep] for a in attrs)


def bridge_loops(verts, loop_a, loop_b, flip=None):
    """Quads bridging two equal-length loops; picks the rotation/orientation with the smallest total distance.
    Returns list of faces. Winding follows loop_a order (caller fixes global normals afterwards)."""
    n = len(loop_a)
    assert n == len(loop_b), f'loop length mismatch {n} vs {len(loop_b)}'
    a = np.array(loop_a)
    best = None
    for rev in (False, True):
        b = np.array(loop_b[::-1] if rev else loop_b)
        for k in range(n):
            bb = np.roll(b, -k)
            d = np.linalg.norm(verts[a] - verts[bb], axis=1).sum()
            if best is None or d < best[0]:
                best = (d, bb.copy(), rev)
    _, bb, rev = best
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((int(a[i]), int(a[j]), int(bb[j]), int(bb[i])))
    return faces


def fix_winding(verts, faces, ref_point=None):
    """Make face normals consistently outward using BFS over shared edges (closed/open manifold pieces)."""
    bm = bmesh.new()
    bvs = [bm.verts.new(tuple(p)) for p in verts]
    for f in faces:
        try:
            bm.faces.new([bvs[i] for i in f])
        except ValueError:
            pass
    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    newf = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return newf


def laplacian_smooth(verts, faces, iters=5, lam=0.5, pinned=None, adj=None):
    adj = adj or adjacency(len(verts), faces)
    pinned = np.zeros(len(verts), dtype=bool) if pinned is None else pinned
    v = verts.copy()
    for _ in range(iters):
        nv = v.copy()
        for i, nb in enumerate(adj):
            if pinned[i] or not nb:
                continue
            nv[i] = v[i] + lam * (v[nb].mean(axis=0) - v[i])
        v = nv
    return v


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def gauss_bump(points, center, radii, strength_dir, amount, normals_=None):
    """Displacement field: ellipsoidal gaussian bump. strength_dir: 'normal' (uses normals_) or a 3-vector."""
    c = np.asarray(center, dtype=np.float64)
    r = np.asarray(radii, dtype=np.float64)
    d = ((points - c) / r)
    w = np.exp(-np.sum(d * d, axis=1) * 1.5)
    if isinstance(strength_dir, str):
        return normals_ * (amount * w)[:, None]
    return np.asarray(strength_dir)[None, :] * (amount * w)[:, None]

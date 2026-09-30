"""Body base mesh: Skin-modifier graph fitted to skeleton_def (trunk, limbs, neck stump).

Pipeline: isotropic skin graph (+ leaf extensions) -> Subsurf level 2 -> bisect at exact cut planes (clean 16-vertex rings)
-> masked per-height warp so the trunk gets elliptical cross-sections -> anatomy bumps (body_shape.py).
Head, hands, boots and hard-surface parts are separate generators welded or attached at the returned rings.
Run inside Blender."""
import numpy as np
import bpy
import bmesh
import skeleton_def as S
import mr_geo as G

# name, position, radius (isotropic; CC subdivision shrinks ~8%)
TRUNK = [
    ('pelvis', (-0.006, 0.0, 0.985), 0.135),
    ('waist', (-0.003, 0.0, 1.110), 0.112),
    ('ribs', (0.000, 0.0, 1.230), 0.118),
    ('chest', (0.003, 0.0, 1.335), 0.128),
    ('upperchest', (0.004, 0.0, 1.425), 0.125),
    ('neckbase', (0.008, 0.0, 1.500), 0.060),
    ('necktop', (0.010, 0.0, 1.545), 0.052),
]

# trunk warp targets: z -> (half-width along Y, half-depth along X, centre shift along X)
TRUNK_TARGETS = [
    (0.86, (0.150, 0.112, -0.010)),
    (0.93, (0.160, 0.118, -0.010)),
    (1.00, (0.160, 0.116, -0.006)),
    (1.06, (0.148, 0.105, -0.003)),
    (1.12, (0.134, 0.093, 0.000)),
    (1.20, (0.138, 0.098, 0.002)),
    (1.28, (0.147, 0.105, 0.004)),
    (1.35, (0.154, 0.110, 0.006)),
    (1.42, (0.160, 0.098, 0.004)),
]


def limb_stations(sy):
    m = lambda p: (p[0], sy * p[1], p[2])
    arm = [
        ('shoulder', m(S.SHOULDER), 0.068),
        ('ua1', m(S.lerp(S.SHOULDER, S.ELBOW, 0.30)), 0.055),
        ('ua2', m(S.lerp(S.SHOULDER, S.ELBOW, 0.62)), 0.051),
        ('elbow', m(S.ELBOW), 0.045),
        ('fa1', m(S.lerp(S.ELBOW, S.WRIST, 0.30)), 0.046),
        ('fa2', m(S.lerp(S.ELBOW, S.WRIST, 0.65)), 0.038),
        ('wrist', m(S.WRIST), 0.026),
    ]
    leg = [
        ('hip', m(S.HIP), 0.100),
        ('th1', m(S.lerp(S.HIP, S.KNEE, 0.30)), 0.090),
        ('th2', m(S.lerp(S.HIP, S.KNEE, 0.62)), 0.075),
        ('knee1', m(S.lerp(S.HIP, S.KNEE, 0.90)), 0.057),
        ('knee', m(S.KNEE), 0.053),
        ('ca1', m(S.lerp(S.KNEE, S.ANKLE, 0.28)), 0.059),
        ('ca2', m(S.lerp(S.KNEE, S.ANKLE, 0.65)), 0.043),
        ('ankle', m(S.lerp(S.KNEE, S.ANKLE, 0.98)), 0.036),
    ]
    return arm, leg


def _ext(p_prev, p_leaf, dist=0.06):
    d = np.array(p_leaf) - np.array(p_prev)
    d /= np.linalg.norm(d)
    return tuple(np.array(p_leaf) + d * dist), d


def build_graph(left_arm_end='ua2', right_arm_end='wrist'):
    verts, edges, rad, names, kind = [], [], [], [], []

    def V(name, p, r, k):
        verts.append(tuple(p))
        rad.append(r)
        names.append(name)
        kind.append(k)
        return len(verts) - 1

    idx = {}
    leaves = []  # (ring_name, cut_position, cut_normal)
    prev = None
    for n, p, r in TRUNK:
        i = V(n, p, r, 'trunk')
        idx[n] = i
        if prev is not None:
            edges.append((prev, i))
        prev = i
    p_ext, d = _ext(TRUNK[-2][1], TRUNK[-1][1])
    e = V('necktop_ext', p_ext, TRUNK[-1][2], 'neck')
    edges.append((idx['necktop'], e))
    leaves.append(('neck', TRUNK[-1][1], d))
    for side, sy, arm_end in (('l', 1.0, left_arm_end), ('r', -1.0, right_arm_end)):
        arm, leg = limb_stations(sy)
        prev = idx['upperchest']
        prev_pos = TRUNK[4][1]
        for n, p, r in arm:
            i = V(f'{n}_{side}', p, r, f'arm_{side}')
            edges.append((prev, i))
            idx[f'{n}_{side}'] = i
            prev_pos_before = verts[prev]
            prev = i
            if n == arm_end:
                pe, d = _ext(prev_pos_before, p)
                e = V(f'{n}_ext_{side}', pe, r, f'arm_{side}')
                edges.append((i, e))
                leaves.append((f'arm_{side}', p, d))
                break
        prev = idx['pelvis']
        for n, p, r in leg:
            i = V(f'{n}_{side}', p, r, f'leg_{side}')
            edges.append((prev, i))
            idx[f'{n}_{side}'] = i
            prev_before = verts[prev]
            prev = i
        pe, d = _ext(verts[idx[f'ca2_{side}']], verts[prev])
        e = V(f'ankle_ext_{side}', pe, leg[-1][2], f'leg_{side}')
        edges.append((prev, e))
        leaves.append((f'leg_{side}', verts[prev], d))
    return verts, edges, rad, names, kind, idx, leaves


def build_body_base(levels=2, left_arm_end='ua2', right_arm_end='wrist'):
    verts, edges, rad, names, kind, idx, leaves = build_graph(left_arm_end, right_arm_end)
    me = bpy.data.meshes.new('body_skin_tmp')
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new('body_skin_tmp', me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    sk = ob.modifiers.new('Skin', 'SKIN')
    sk.branch_smoothing = 0.7
    sk.use_smooth_shade = True
    sub = ob.modifiers.new('Sub', 'SUBSURF')
    sub.levels = levels
    sub.render_levels = levels
    layer = me.skin_vertices[0]
    for i, r in enumerate(rad):
        layer.data[i].radius = (r, r)
    layer.data[idx['pelvis']].use_root = True
    bpy.context.view_layer.update()
    v, f = G.eval_mesh(ob)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)

    # bisect at the cut planes, delete the far side near each leaf, collect rings
    bm = bmesh.new()
    bv = [bm.verts.new(tuple(p)) for p in v]
    for face in f:
        bm.faces.new([bv[i] for i in face])
    bm.verts.ensure_lookup_table()
    for lname, pos, d in leaves:
        pos = np.array(pos, dtype=np.float64)
        d = np.array(d, dtype=np.float64)
        gs = {x for x in bm.verts if np.linalg.norm(np.array(x.co) - pos) < 0.16}
        geom_e = [e for e in bm.edges if e.verts[0] in gs and e.verts[1] in gs]
        geom_f = [fc for fc in bm.faces if all(x in gs for x in fc.verts)]
        bmesh.ops.bisect_plane(bm, geom=list(gs) + geom_e + geom_f, dist=1e-6, plane_co=tuple(pos), plane_no=tuple(d))
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        # far-side faces, flood-filled from the extension tip so only the leaf tube beyond the plane is removed
        far = [fc for fc in bm.faces if (np.array(fc.calc_center_median()) - pos) @ d > 1e-4]
        far_set = set(far)
        tip = pos + d * 0.06
        start = min(far, key=lambda fc: np.linalg.norm(np.array(fc.calc_center_median()) - tip))
        comp, stack = {start}, [start]
        while stack:
            fc = stack.pop()
            for e in fc.edges:
                for nb in e.link_faces:
                    if nb in far_set and nb not in comp:
                        comp.add(nb)
                        stack.append(nb)
        kill = list(comp)
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.verts.ensure_lookup_table()
    loose = [x for x in bm.verts if not x.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.verts.ensure_lookup_table()
    nv = np.array([tuple(x.co) for x in bm.verts])
    nf = [tuple(x.index for x in fc.verts) for fc in bm.faces]
    bm.free()
    loops = G.boundary_loops(len(nv), nf)
    rings = {}
    for lname, pos, d in leaves:
        best = min(loops, key=lambda lp: np.linalg.norm(nv[lp].mean(axis=0) - np.array(pos)))
        rings[lname] = best
    info = {'graph_verts': np.array(verts), 'graph_edges': edges, 'graph_radii': rad, 'graph_names': names,
            'graph_kind': kind, 'leaves': leaves}
    return nv, nf, rings, info


def part_labels(v, info):
    """Label each vertex with the kind of the nearest graph edge (distance normalised by radius)."""
    gv = info['graph_verts']
    kind = info['graph_kind']
    rad = info['graph_radii']
    best = np.full(len(v), 1e9)
    lab = np.zeros(len(v), dtype=np.int64)
    kinds = sorted(set(kind))
    kid = {k: i for i, k in enumerate(kinds)}
    for a, b in info['graph_edges']:
        pa, pb = gv[a], gv[b]
        ab = pb - pa
        t = np.clip(((v - pa) @ ab) / (ab @ ab), 0, 1)
        proj = pa + np.outer(t, ab)
        r = rad[a] * (1 - t) + rad[b] * t
        d = np.linalg.norm(v - proj, axis=1) / r
        m = d < best
        best[m] = d[m]
        lab[m] = kid[kind[b]]
    return lab, kinds


def trunk_warp(v, f, info, smooth_iters=8):
    """Give the round trunk elliptical cross-sections following TRUNK_TARGETS via a masked per-height scale."""
    lab, kinds = part_labels(v, info)
    m = (lab == kinds.index('trunk')).astype(np.float64)
    adj = G.adjacency(len(v), f)
    zt = v[:, 2]
    m *= G.smoothstep((1.47 - zt) / 0.05) * G.smoothstep((zt - 0.84) / 0.04)
    for _ in range(smooth_iters):
        nm = m.copy()
        for i, nb in enumerate(adj):
            nm[i] = 0.5 * m[i] + 0.5 * np.mean(m[nb])
        m = nm
    zs = np.array([z for z, _ in TRUNK_TARGETS])
    sy = np.ones(len(zs))
    sx = np.ones(len(zs))
    cx0 = np.zeros(len(zs))
    for k, (z, (hw, hd, cs)) in enumerate(TRUNK_TARGETS):
        sel = (np.abs(v[:, 2] - z) < 0.02) & (m > 0.85)
        if sel.sum() < 4:
            continue
        pts = v[sel]
        ymax = np.abs(pts[:, 1]).max()
        xr = (pts[:, 0].max() - pts[:, 0].min()) / 2
        cx0[k] = (pts[:, 0].max() + pts[:, 0].min()) / 2
        sy[k] = hw / ymax
        sx[k] = hd / xr
    SY = np.interp(zt, zs, sy)
    SX = np.interp(zt, zs, sx)
    CX = np.interp(zt, zs, cx0)
    SH = np.interp(zt, zs, np.array([c for _, (_, _, c) in TRUNK_TARGETS]))
    out = v.copy()
    out[:, 1] = v[:, 1] * (1 + (SY - 1) * m)
    out[:, 0] = CX + (v[:, 0] - CX) * (1 + (SX - 1) * m) + SH * m
    return out, m


def slice_extents(v, faces, axis, value, where=None):
    """Points where mesh edges cross the plane coordinate[axis] == value."""
    pts = []
    seen = set()
    for f in faces:
        k = len(f)
        for i in range(k):
            a, b = f[i], f[(i + 1) % k]
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            da, db = v[a][axis] - value, v[b][axis] - value
            if da * db < 0:
                t = da / (da - db)
                pts.append(v[a] + (v[b] - v[a]) * t)
    pts = np.array(pts) if pts else np.zeros((0, 3))
    if where is not None and len(pts):
        pts = pts[where(pts)]
    return pts

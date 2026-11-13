"""Mesh assembly container used by every geometry generator.

Geometry is authored as plain python/numpy data (positions, quads/tris, per-vertex bone weights,
per-face material / region tags, seam edges) and converted to a Blender mesh object at the end.
"""
import numpy as np


class MeshData:
    def __init__(self, name):
        self.name = name
        self.v = []        # [x, y, z]
        self.w = []        # {bone: weight}
        self.f = []        # tuple of vertex indices
        self.fmat = []     # material name per face
        self.ftag = []     # region tag per face
        self.seams = set()  # frozenset({a, b})
        self.sharp = set()
        self.vtag = []     # free-form per-vertex tag (string)
        self.vcol = {}     # name -> {vertex index: value}

    # ------------------------------------------------------------------ vertices
    def vert(self, p, w=None, tag=''):
        self.v.append([float(p[0]), float(p[1]), float(p[2])])
        self.w.append(dict(w) if w else {})
        self.vtag.append(tag)
        return len(self.v) - 1

    def ring(self, pts, w=None, tag=''):
        """Add a ring of points. w may be a dict (shared) or list of dicts."""
        out = []
        for i, p in enumerate(pts):
            wi = w[i] if isinstance(w, (list, tuple)) else w
            out.append(self.vert(p, wi, tag))
        return out

    def pos(self, idx):
        return np.array([self.v[i] for i in idx], dtype=np.float64)

    def P(self):
        return np.array(self.v, dtype=np.float64)

    def set_pos(self, idx, pts):
        for i, p in zip(idx, pts):
            self.v[i] = [float(p[0]), float(p[1]), float(p[2])]

    # ------------------------------------------------------------------ faces
    def face(self, idx, mat='', tag='', flip=False):
        idx = [int(i) for i in idx]
        # drop consecutive duplicates (degenerate quads become tris)
        clean = []
        for i in idx:
            if not clean or clean[-1] != i:
                clean.append(i)
        if len(clean) > 1 and clean[0] == clean[-1]:
            clean.pop()
        if len(clean) < 3:
            return -1
        if flip:
            clean = clean[::-1]
        self.f.append(tuple(clean))
        self.fmat.append(mat)
        self.ftag.append(tag)
        return len(self.f) - 1

    def strip(self, ra, rb, mat='', tag='', closed=True, flip=False, skip=None):
        """Quads between two equally sized vertex rings/rows. skip: set of segment indices to leave open."""
        n = len(ra)
        assert n == len(rb), (n, len(rb))
        m = n if closed else n - 1
        out = []
        for j in range(m):
            if skip and j in skip:
                continue
            k = (j + 1) % n
            mt = mat[j] if isinstance(mat, (list, tuple)) else mat
            tg = tag[j] if isinstance(tag, (list, tuple)) else tag
            out.append(self.face([ra[j], ra[k], rb[k], rb[j]], mt, tg, flip))
        return out

    def loft(self, rings, mat='', tag='', closed=True, flip=False):
        for a, b in zip(rings[:-1], rings[1:]):
            self.strip(a, b, mat, tag, closed, flip)

    def fan_cap(self, ring, center_pt, w=None, mat='', tag='', flip=False):
        c = self.vert(center_pt, w)
        n = len(ring)
        for j in range(n):
            self.face([ring[j], ring[(j + 1) % n], c], mat, tag, flip)
        return c

    def grid_cap(self, ring, mat='', tag='', flip=False, w=None, bulge=None):
        """Cap a ring with an even vertex count using a quad grid (rows across).
        ring is split into two halves that are bridged by rows of quads."""
        n = len(ring)
        assert n % 2 == 0 and n >= 4
        if n == 4:
            self.face(ring, mat, tag, flip)
            return
        h = n // 2
        # pair vertex k with vertex n-k ; rows between pairs
        prev = None
        for k in range(1, h):
            a, b = ring[k], ring[n - k]
            if prev is None:
                self.face([ring[0], a, b], mat, tag, flip)
            else:
                self.face([prev[0], a, b, prev[1]], mat, tag, flip)
            prev = (a, b)
        self.face([prev[0], ring[h], prev[1]], mat, tag, flip)

    def seam(self, a, b):
        self.seams.add(frozenset((int(a), int(b))))

    def seam_path(self, idx, closed=False):
        for a, b in zip(idx[:-1], idx[1:]):
            self.seam(a, b)
        if closed:
            self.seam(idx[-1], idx[0])

    # ------------------------------------------------------------------ combination
    def append(self, other, mat=None, tag_prefix=''):
        """Append another MeshData; returns vertex index offset."""
        off = len(self.v)
        self.v.extend([list(p) for p in other.v])
        self.w.extend([dict(w) for w in other.w])
        self.vtag.extend(other.vtag)
        for f, m, t in zip(other.f, other.fmat, other.ftag):
            self.f.append(tuple(i + off for i in f))
            self.fmat.append(mat if mat is not None else m)
            self.ftag.append(tag_prefix + t)
        for e in other.seams:
            self.seams.add(frozenset(i + off for i in e))
        for e in other.sharp:
            self.sharp.add(frozenset(i + off for i in e))
        for name, d in other.vcol.items():
            dst = self.vcol.setdefault(name, {})
            for k, val in d.items():
                dst[k + off] = val
        return off

    def remove_unused(self):
        """Drop vertices that no face references (construction helpers such as grid points inside cut-out
        openings). Vertex indices change, so call it only when nothing else holds indices into this mesh.
        Returns the number of removed vertices."""
        import numpy as _np
        used = _np.zeros(len(self.v), dtype=bool)
        for f in self.f:
            used[list(f)] = True
        if used.all():
            return 0
        remap = _np.cumsum(used) - 1
        keep = _np.nonzero(used)[0]
        self.v = [self.v[i] for i in keep]
        self.w = [self.w[i] for i in keep]
        self.vtag = [self.vtag[i] for i in keep]
        self.f = [tuple(int(remap[i]) for i in f) for f in self.f]
        self.seams = {frozenset(int(remap[i]) for i in e) for e in self.seams if all(used[i] for i in e)}
        self.sharp = {frozenset(int(remap[i]) for i in e) for e in self.sharp if all(used[i] for i in e)}
        self.vcol = {name: {int(remap[k]): val for k, val in d.items() if used[k]} for name, d in self.vcol.items()}
        return int((~used).sum())

    def unused_count(self):
        used = set()
        for f in self.f:
            used.update(f)
        return len(self.v) - len(used)

    def mirrored(self, name=None, swap=True):
        """X-mirrored copy with reversed winding and _l/_r swapped weights and tags."""
        from .skel import mirror_name
        m = MeshData(name or self.name)
        m.v = [[-p[0], p[1], p[2]] for p in self.v]
        m.w = [{(mirror_name(b) if swap else b): val for b, val in w.items()} for w in self.w]
        m.vtag = [_swap_tag(t) if swap else t for t in self.vtag]
        m.f = [tuple(reversed(f)) for f in self.f]
        m.fmat = list(self.fmat)
        m.ftag = [_swap_tag(t) if swap else t for t in self.ftag]
        m.seams = set(self.seams)
        m.sharp = set(self.sharp)
        m.vcol = {k: dict(d) for k, d in self.vcol.items()}
        return m

    def transform(self, mat4):
        P = self.P()
        P = P @ mat4[:3, :3].T + mat4[:3, 3]
        self.v = P.tolist()
        if np.linalg.det(mat4[:3, :3]) < 0:
            self.f = [tuple(reversed(f)) for f in self.f]
        return self

    def set_weights_all(self, w):
        self.w = [dict(w) for _ in self.v]
        return self

    # ------------------------------------------------------------------ topology helpers
    def vert_neighbors(self):
        nb = [set() for _ in self.v]
        for f in self.f:
            n = len(f)
            for i in range(n):
                a, b = f[i], f[(i + 1) % n]
                nb[a].add(b)
                nb[b].add(a)
        return nb

    def boundary_verts(self):
        cnt = {}
        for f in self.f:
            n = len(f)
            for i in range(n):
                e = frozenset((f[i], f[(i + 1) % n]))
                cnt[e] = cnt.get(e, 0) + 1
        out = set()
        for e, c in cnt.items():
            if c == 1:
                out.update(e)
        return out

    def smooth(self, idx_weights, iters=4, lam=0.5, lock=None):
        """Laplacian smoothing of selected vertices. idx_weights: {vertex: strength 0..1}."""
        nb = self.vert_neighbors()
        P = self.P()
        idx = np.array(sorted(idx_weights.keys()), dtype=np.int64)
        if len(idx) == 0:
            return
        st = np.array([idx_weights[i] for i in idx])
        lock = lock or set()
        for _ in range(iters):
            new = P.copy()
            for k, i in enumerate(idx):
                if i in lock or not nb[i]:
                    continue
                avg = P[list(nb[i])].mean(axis=0)
                new[i] = P[i] + (avg - P[i]) * lam * st[k]
            P = new
        self.v = P.tolist()

    def smooth_weights(self, iters=2, lam=0.5, only=None, lock_tags=()):
        """Laplacian smoothing of bone weights over mesh connectivity (keeps partitions of unity)."""
        nb = self.vert_neighbors()
        idx = range(len(self.v)) if only is None else only
        for _ in range(iters):
            new = [None] * len(self.v)
            for i in idx:
                if not nb[i] or (lock_tags and self.vtag[i] in lock_tags):
                    continue
                acc = {}
                for j in nb[i]:
                    for b, val in self.w[j].items():
                        acc[b] = acc.get(b, 0.0) + val
                k = len(nb[i])
                mix = {}
                for b in set(acc) | set(self.w[i]):
                    mix[b] = self.w[i].get(b, 0.0) * (1 - lam) + acc.get(b, 0.0) / k * lam
                new[i] = mix
            for i in idx:
                if new[i] is not None:
                    self.w[i] = new[i]
        self.normalize_weights()

    def normalize_weights(self, max_inf=8, eps=1e-4):
        for i, w in enumerate(self.w):
            items = [(b, val) for b, val in w.items() if val > eps]
            if not items:
                continue
            items.sort(key=lambda t: -t[1])
            items = items[:max_inf]
            s = sum(val for _, val in items)
            self.w[i] = {b: val / s for b, val in items}

    def stats(self):
        tris = sum(len(f) - 2 for f in self.f)
        return dict(verts=len(self.v), faces=len(self.f), tris=tris)


def _swap_tag(t):
    if t.endswith('_l'):
        return t[:-2] + '_r'
    if t.endswith('_r'):
        return t[:-2] + '_l'
    return t


# ---------------------------------------------------------------------------------- blender side
def to_object(md, collection=None, materials=None, smooth=True):
    """Create a Blender mesh object from MeshData (vertex groups, materials, seams, tags)."""
    import bpy
    me = bpy.data.meshes.new(md.name)
    me.from_pydata(md.v, [], [list(f) for f in md.f])
    me.update()
    ob = bpy.data.objects.new(md.name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    # materials
    names = []
    for m in md.fmat:
        if m not in names:
            names.append(m)
    for n in names:
        mat = None
        if materials and n in materials:
            mat = materials[n]
        elif n:
            mat = bpy.data.materials.get(n) or bpy.data.materials.new(n)
        me.materials.append(mat)
    for poly, m in zip(me.polygons, md.fmat):
        poly.material_index = names.index(m)
        poly.use_smooth = smooth
    # region tags as an integer face attribute + json legend
    tags = []
    for t in md.ftag:
        if t not in tags:
            tags.append(t)
    attr = me.attributes.new('region', 'INT', 'FACE')
    attr.data.foreach_set('value', [tags.index(t) for t in md.ftag])
    me['region_names'] = tags
    # vertex groups
    groups = {}
    for i, w in enumerate(md.w):
        for b, val in w.items():
            g = groups.get(b)
            if g is None:
                g = ob.vertex_groups.new(name=b)
                groups[b] = g
            g.add([i], float(val), 'REPLACE')
    # seams / sharp
    if md.seams or md.sharp:
        emap = {frozenset(e.vertices): e for e in me.edges}
        for s in md.seams:
            e = emap.get(s)
            if e is not None:
                e.use_seam = True
        for s in md.sharp:
            e = emap.get(s)
            if e is not None:
                e.use_edge_sharp = True
    for name, d in md.vcol.items():
        a = me.attributes.new(name, 'FLOAT', 'POINT')
        vals = [0.0] * len(md.v)
        for k, val in d.items():
            vals[k] = float(val)
        a.data.foreach_set('value', vals)
    return ob

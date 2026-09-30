"""MorphRig polygon mesh kit (numpy): construction, Catmull-Clark, relax/projection.

A Mesh is a vertex array plus a list of polygon index tuples.  Named vertex
groups (boolean masks) and float attributes are carried through subdivision so
feature loops (lid margins, lip lines, seams) stay addressable.
"""
import numpy as np
from mr_sdf import normalize, length, project


class Mesh:
    def __init__(self, verts=None, faces=None):
        self.v = np.zeros((0, 3)) if verts is None else np.asarray(verts, dtype=np.float64).reshape(-1, 3)
        self.f = [] if faces is None else [tuple(int(i) for i in f) for f in faces]
        self.groups = {}      # name -> bool array (len nv)
        self.attrs = {}       # name -> float array (len nv) or (nv,k)
        self.face_attrs = {}  # name -> list/array per face (material index, part id...)
        self.seams = set()    # set of (a,b) sorted vertex pairs marked as UV seams
        self.sharp = set()    # set of (a,b) sharp edges

    # -- building -----------------------------------------------------------
    @property
    def nv(self):
        return len(self.v)

    def add_verts(self, pts):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
        start = len(self.v)
        self.v = np.vstack([self.v, pts]) if len(self.v) else pts.copy()
        for k, g in self.groups.items():
            self.groups[k] = np.concatenate([g, np.zeros(len(pts), bool)])
        for k, a in self.attrs.items():
            pad = np.zeros((len(pts),) + a.shape[1:])
            self.attrs[k] = np.concatenate([a, pad])
        return np.arange(start, start + len(pts))

    def add_face(self, f, **fattrs):
        self.f.append(tuple(int(i) for i in f))
        for k, val in fattrs.items():
            self.face_attrs.setdefault(k, [None] * (len(self.f) - 1))
        for k in self.face_attrs:
            self.face_attrs[k].append(fattrs.get(k, self.face_attrs[k][-1] if self.face_attrs[k] else 0))

    def set_face_attr_all(self, name, value):
        self.face_attrs[name] = [value] * len(self.f)

    def group(self, name, idx=None):
        if name not in self.groups:
            self.groups[name] = np.zeros(self.nv, bool)
        if idx is not None:
            self.groups[name][np.asarray(idx, dtype=int)] = True
        return self.groups[name]

    def attr(self, name, default=0.0, dim=None):
        if name not in self.attrs:
            shape = (self.nv,) if dim is None else (self.nv, dim)
            self.attrs[name] = np.full(shape, default, dtype=np.float64)
        return self.attrs[name]

    def mark_seam_loop(self, idx, closed=True):
        idx = list(idx)
        n = len(idx)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            a, b = idx[i], idx[(i + 1) % n]
            self.seams.add((min(a, b), max(a, b)))

    def mark_seam_path(self, idx):
        self.mark_seam_loop(idx, closed=False)

    # -- topology -----------------------------------------------------------
    def edges(self):
        emap = {}
        e_list = []
        e_faces = []
        for fi, f in enumerate(self.f):
            n = len(f)
            for i in range(n):
                a, b = f[i], f[(i + 1) % n]
                key = (a, b) if a < b else (b, a)
                ei = emap.get(key)
                if ei is None:
                    ei = len(e_list)
                    emap[key] = ei
                    e_list.append(key)
                    e_faces.append([fi])
                else:
                    e_faces[ei].append(fi)
        return np.array(e_list, dtype=np.int64).reshape(-1, 2), e_faces, emap

    def neighbor_lists(self):
        E, _, _ = self.edges()
        nb = [[] for _ in range(self.nv)]
        for a, b in E:
            nb[a].append(b)
            nb[b].append(a)
        return nb

    def boundary_mask(self):
        E, EF, _ = self.edges()
        m = np.zeros(self.nv, bool)
        for (a, b), fl in zip(E, EF):
            if len(fl) == 1:
                m[a] = m[b] = True
        return m

    def compact(self):
        used = np.zeros(self.nv, bool)
        for f in self.f:
            used[list(f)] = True
        remap = -np.ones(self.nv, dtype=np.int64)
        remap[used] = np.arange(used.sum())
        self.v = self.v[used]
        self.f = [tuple(int(remap[i]) for i in f) for f in self.f]
        for k in list(self.groups):
            self.groups[k] = self.groups[k][used]
        for k in list(self.attrs):
            self.attrs[k] = self.attrs[k][used]
        self.seams = {(int(remap[a]), int(remap[b])) for a, b in self.seams if used[a] and used[b]}
        self.seams = {(min(a, b), max(a, b)) for a, b in self.seams}
        self.sharp = {(min(int(remap[a]), int(remap[b])), max(int(remap[a]), int(remap[b])))
                      for a, b in self.sharp if used[a] and used[b]}
        return remap

    def delete_faces(self, face_ids):
        s = set(int(i) for i in face_ids)
        keep = [i for i in range(len(self.f)) if i not in s]
        self.f = [self.f[i] for i in keep]
        for k in self.face_attrs:
            self.face_attrs[k] = [self.face_attrs[k][i] for i in keep]

    def append(self, other):
        """Append another Mesh (indices offset). Returns index offset."""
        off = self.nv
        allg = set(self.groups) | set(other.groups)
        alla = set(self.attrs) | set(other.attrs)
        newv = np.vstack([self.v, other.v]) if self.nv else other.v.copy()
        for k in allg:
            a = self.groups.get(k, np.zeros(self.nv, bool))
            b = other.groups.get(k, np.zeros(other.nv, bool))
            self.groups[k] = np.concatenate([a, b])
        for k in alla:
            a = self.attrs.get(k)
            b = other.attrs.get(k)
            if a is None:
                a = np.zeros((self.nv,) + b.shape[1:])
            if b is None:
                b = np.zeros((other.nv,) + a.shape[1:])
            self.attrs[k] = np.concatenate([a, b])
        self.v = newv
        fa_keys = set(self.face_attrs) | set(other.face_attrs)
        n_self_f = len(self.f)
        for k in fa_keys:
            a = self.face_attrs.get(k, [0] * n_self_f)
            b = other.face_attrs.get(k, [0] * len(other.f))
            self.face_attrs[k] = list(a) + list(b)
        self.f += [tuple(i + off for i in f) for f in other.f]
        self.seams |= {(a + off, b + off) for a, b in other.seams}
        self.sharp |= {(a + off, b + off) for a, b in other.sharp}
        return off

    # -- geometry -----------------------------------------------------------
    def face_normals(self):
        out = np.zeros((len(self.f), 3))
        for i, f in enumerate(self.f):
            p = self.v[list(f)]
            c = p.mean(0)
            n = np.zeros(3)
            for j in range(len(f)):
                n += np.cross(p[j] - c, p[(j + 1) % len(f)] - c)
            out[i] = n
        return normalize(out)

    def vertex_normals(self):
        fn = self.face_normals()
        vn = np.zeros_like(self.v)
        for i, f in enumerate(self.f):
            vn[list(f)] += fn[i]
        return normalize(vn)

    def tri_count(self):
        return sum(len(f) - 2 for f in self.f)


def catmull_clark(m, fixed=None, levels=1):
    """Catmull-Clark subdivision; groups become AND-propagated, attrs averaged.

    fixed: optional bool mask of vertices that keep their position (corners).
    Returns new Mesh.  Vertex order: old verts, edge verts, face verts.
    """
    for _ in range(levels):
        m = _cc_once(m, fixed)
        fixed = None if fixed is None else np.concatenate([fixed, np.zeros(m.nv - len(fixed), bool)])
    return m


def _cc_once(m, fixed=None):
    V = m.v
    nv = len(V)
    E, EF, emap = m.edges()
    ne = len(E)
    nf = len(m.f)
    fp = np.array([V[list(f)].mean(0) for f in m.f])
    ep = np.zeros((ne, 3))
    is_b = np.array([len(fl) == 1 for fl in EF])
    mid = 0.5 * (V[E[:, 0]] + V[E[:, 1]])
    for ei in range(ne):
        fl = EF[ei]
        if len(fl) == 2 and not ((E[ei][0], E[ei][1]) in m.sharp or tuple(E[ei]) in m.sharp):
            ep[ei] = 0.25 * (V[E[ei, 0]] + V[E[ei, 1]] + fp[fl[0]] + fp[fl[1]])
        else:
            ep[ei] = mid[ei]
    # vertex points
    vf = [[] for _ in range(nv)]
    for fi, f in enumerate(m.f):
        for i in f:
            vf[i].append(fi)
    ve = [[] for _ in range(nv)]
    for ei, (a, b) in enumerate(E):
        ve[a].append(ei)
        ve[b].append(ei)
    sharpset = m.sharp
    vp = V.copy()
    for i in range(nv):
        edges_i = ve[i]
        if not edges_i:
            continue
        bnd = [ei for ei in edges_i if is_b[ei] or tuple(E[ei]) in sharpset]
        if fixed is not None and fixed[i]:
            vp[i] = V[i]
        elif len(bnd) == 2:
            a = [E[ei, 0] if E[ei, 1] == i else E[ei, 1] for ei in bnd]
            vp[i] = 0.75 * V[i] + 0.125 * (V[a[0]] + V[a[1]])
        elif len(bnd) > 2:
            vp[i] = V[i]
        else:
            n = len(edges_i)
            Q = fp[vf[i]].mean(0)
            R = mid[edges_i].mean(0)
            vp[i] = (Q + 2 * R + (n - 3) * V[i]) / n
    newv = np.vstack([vp, ep, fp])
    out = Mesh(newv, [])
    faces = []
    fmat = {k: [] for k in m.face_attrs}
    for fi, f in enumerate(m.f):
        k = len(f)
        fcent = nv + ne + fi
        for j in range(k):
            a = f[j]
            b = f[(j + 1) % k]
            c = f[(j - 1) % k]
            e_ab = emap[(a, b) if a < b else (b, a)]
            e_ca = emap[(c, a) if c < a else (a, c)]
            faces.append((a, nv + e_ab, fcent, nv + e_ca))
            for key in m.face_attrs:
                fmat[key].append(m.face_attrs[key][fi])
    out.f = faces
    out.face_attrs = fmat
    # groups: vertex keeps; edge if both; face if all
    for key, g in m.groups.items():
        ge = g[E[:, 0]] & g[E[:, 1]]
        gf = np.array([g[list(f)].all() for f in m.f], bool)
        out.groups[key] = np.concatenate([g, ge, gf])
    for key, a in m.attrs.items():
        ae = 0.5 * (a[E[:, 0]] + a[E[:, 1]])
        af = np.array([a[list(f)].mean(0) for f in m.f])
        out.attrs[key] = np.concatenate([a, ae, af.reshape((nf,) + a.shape[1:])])
    # seams/sharp: split each marked edge into two
    for src, dst in ((m.seams, out.seams), (m.sharp, out.sharp)):
        for a, b in src:
            ei = emap.get((a, b))
            if ei is None:
                continue
            e = nv + ei
            dst.add((min(a, e), max(a, e)))
            dst.add((min(b, e), max(b, e)))
    return out


def neighbor_arrays(m):
    E, _, _ = m.edges()
    return E


def laplacian(m, E=None, weights=None):
    if E is None:
        E = neighbor_arrays(m)
    acc = np.zeros_like(m.v)
    cnt = np.zeros(m.nv)
    np.add.at(acc, E[:, 0], m.v[E[:, 1]])
    np.add.at(acc, E[:, 1], m.v[E[:, 0]])
    np.add.at(cnt, E[:, 0], 1)
    np.add.at(cnt, E[:, 1], 1)
    avg = acc / np.maximum(cnt, 1)[:, None]
    return avg - m.v


def mirror_pairs(m, tol=2e-3):
    """Index of the X-mirrored partner of every vertex (-1 if none within tol)."""
    V = m.v
    mv = V * np.array([-1.0, 1.0, 1.0])
    pairs = -np.ones(len(V), dtype=np.int64)
    chunk = 2048
    for s in range(0, len(V), chunk):
        d = ((mv[s:s + chunk, None, :] - V[None, :, :]) ** 2).sum(-1)
        j = np.argmin(d, axis=1)
        ok = d[np.arange(len(j)), j] < tol * tol
        pairs[s:s + chunk][ok] = j[ok]
    return pairs


def enforce_symmetry(m, pairs):
    ok = pairs >= 0
    idx = np.nonzero(ok)[0]
    mirrored = m.v[pairs[idx]] * np.array([-1.0, 1.0, 1.0])
    m.v[idx] = 0.5 * (m.v[idx] + mirrored)
    centre = idx[pairs[idx] == idx]
    m.v[centre, 0] = 0.0


def relax_on_sdf(m, sdf, iters=10, lam=0.5, pinned=None, project_iters=3, tangential=True, sym_pairs=None):
    """Tangential smoothing + reprojection onto the sdf zero set."""
    E = neighbor_arrays(m)
    bnd = m.boundary_mask()
    free = ~bnd if pinned is None else (~bnd & ~pinned)
    for _ in range(iters):
        L = laplacian(m, E)
        if tangential:
            n = normalize(sdf.grad(m.v))
            L = L - (L * n).sum(-1)[:, None] * n
        m.v[free] += lam * L[free]
        m.v[free] = project(sdf, m.v[free], iters=project_iters)
        if sym_pairs is not None:
            enforce_symmetry(m, sym_pairs)
    return m


def smooth_free(m, iters=5, lam=0.5, pinned=None, keep_boundary=True):
    """Plain Laplacian smoothing (no sdf)."""
    E = neighbor_arrays(m)
    free = np.ones(m.nv, bool)
    if keep_boundary:
        free &= ~m.boundary_mask()
    if pinned is not None:
        free &= ~pinned
    for _ in range(iters):
        L = laplacian(m, E)
        m.v[free] += lam * L[free]
    return m


def ring_quads(ring_a, ring_b, closed=True, flip=False):
    """Quads bridging two equal-length index rings."""
    n = len(ring_a)
    assert n == len(ring_b), (n, len(ring_b))
    faces = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        j = (i + 1) % n
        f = (ring_a[i], ring_a[j], ring_b[j], ring_b[i])
        faces.append(f[::-1] if flip else f)
    return faces


def make_consistent(m, seed_face=0, outward_point=None, outward_dir=None):
    """Propagate a consistent winding over each connected face region (BFS).

    If outward_point is given, the seed face is flipped so its normal points away
    from that point.
    """
    from collections import deque
    E, EF, emap = m.edges()
    nf = len(m.f)
    visited = np.zeros(nf, bool)

    def directed(f):
        return {(f[i], f[(i + 1) % len(f)]) for i in range(len(f))}

    comps = 0
    for start in range(nf):
        if visited[start]:
            continue
        comps += 1
        if outward_point is not None and start == seed_face or (outward_point is not None and comps > 0 and start != seed_face and False):
            pass
        q = deque([start])
        visited[start] = True
        while q:
            fi = q.popleft()
            f = m.f[fi]
            dset = directed(f)
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                ei = emap[(a, b) if a < b else (b, a)]
                for gj in EF[ei]:
                    if gj == fi or visited[gj]:
                        continue
                    g = m.f[gj]
                    # neighbour must traverse the edge as (b, a)
                    if (a, b) in directed(g):
                        m.f[gj] = tuple(reversed(g))
                    visited[gj] = True
                    q.append(gj)
    if outward_point is not None:
        # decide global flip per mesh by majority vote of normals vs outward point
        fn = m.face_normals()
        cents = np.array([m.v[list(f)].mean(0) for f in m.f])
        votes = ((cents - outward_point) * fn).sum(-1)
        if np.sum(votes > 0) < np.sum(votes < 0):
            m.f = [tuple(reversed(f)) for f in m.f]
    return comps

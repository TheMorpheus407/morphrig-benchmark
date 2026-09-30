"""Hard-surface primitive kit for the Operative accessories (numpy). Every primitive returns a Part: verts (N,3), faces,
plus per-vertex mask attributes used later for texturing/weights. All units metres, character space (+X forward, +Y left)."""
import math
import numpy as np
import mr_geo as G


class Part:
    def __init__(self, name, verts, faces, mat='cyber', bone=None, emit=0.0, accent=0.0, flex=None):
        self.name = name
        self.verts = np.asarray(verts, dtype=np.float64)
        self.faces = [tuple(int(i) for i in f) for f in faces]
        self.mat = mat
        self.bone = bone            # rigid parent bone, or None -> 'flex' rule
        self.emit = emit            # 0..1 emissive mask
        self.accent = accent        # 0..1 team-accent mask
        self.flex = flex            # callable / tag for flexible weighting

    def transformed(self, R=None, t=None):
        v = self.verts
        if R is not None:
            v = v @ np.asarray(R).T
        if t is not None:
            v = v + np.asarray(t)
        return v


def frame(y_axis, z_hint=(0, 0, 1)):
    """Right-handed frame with Y along y_axis, Z as close to z_hint as possible. Returns 3x3 with columns X,Y,Z."""
    y = np.asarray(y_axis, dtype=np.float64)
    y = y / np.linalg.norm(y)
    z = np.asarray(z_hint, dtype=np.float64)
    z = z - y * (z @ y)
    if np.linalg.norm(z) < 1e-6:
        z = np.array([1.0, 0, 0]) - y * y[0]
    z /= np.linalg.norm(z)
    x = np.cross(y, z)
    return np.column_stack([x, y, z])


def rounded_box(size, R=None, center=(0, 0, 0), seg=4, round_=0.3):
    """Box with rounded corners. size=(sx,sy,sz) along the local X,Y,Z; R is the 3x3 frame."""
    n = seg
    verts, faces, idx = [], [], {}

    def V(i, j, k):
        key = (i, j, k)
        if key not in idx:
            idx[key] = len(verts)
            verts.append((2.0 * i / n - 1, 2.0 * j / n - 1, 2.0 * k / n - 1))
        return idx[key]
    for a in range(n):
        for b in range(n):
            faces += [(V(n, a, b), V(n, a + 1, b), V(n, a + 1, b + 1), V(n, a, b + 1)),
                      (V(0, a, b), V(0, a, b + 1), V(0, a + 1, b + 1), V(0, a + 1, b)),
                      (V(a, n, b), V(a, n, b + 1), V(a + 1, n, b + 1), V(a + 1, n, b)),
                      (V(a, 0, b), V(a + 1, 0, b), V(a + 1, 0, b + 1), V(a, 0, b + 1)),
                      (V(a, b, n), V(a + 1, b, n), V(a + 1, b + 1, n), V(a, b + 1, n)),
                      (V(a, b, 0), V(a, b + 1, 0), V(a + 1, b + 1, 0), V(a + 1, b, 0))]
    q = np.array(verts)
    # superellipsoid-style rounding: pull corners toward the sphere by round_ but keep flat faces
    r = np.abs(q).max(axis=1, keepdims=True)
    sph = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-9) * r
    m = q * (1 - round_) + sph * round_
    v = m * (np.asarray(size) / 2.0)
    if R is not None:
        v = v @ np.asarray(R).T
    v = v + np.asarray(center)
    return v, G.fix_winding(v, faces)


def cylinder(p0, p1, r0, r1=None, n=16, caps=True, rings=1, z_hint=(0, 0, 1), profile=None):
    """Cylinder/cone between p0 and p1. rings: number of segments along the axis. profile: optional f(t)->radius scale."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    r1 = r0 if r1 is None else r1
    R = frame(p1 - p0, z_hint)
    L = np.linalg.norm(p1 - p0)
    verts, faces, rows = [], [], []
    for k in range(rings + 1):
        t = k / rings
        rad = (r0 + (r1 - r0) * t) * (profile(t) if profile else 1.0)
        row = []
        for m in range(n):
            a = 2 * math.pi * m / n
            row.append(len(verts))
            verts.append(R @ np.array([rad * math.cos(a), t * L, rad * math.sin(a)]) + p0)
        rows.append(row)
    for k in range(rings):
        for m in range(n):
            faces.append((rows[k][m], rows[k][(m + 1) % n], rows[k + 1][(m + 1) % n], rows[k + 1][m]))
    if caps:
        for row, top in ((rows[0], False), (rows[-1], True)):
            c = len(verts)
            verts.append(p1 if top else p0)
            for m in range(n):
                faces.append((row[m], row[(m + 1) % n], c) if top else (row[(m + 1) % n], row[m], c))
    v = np.array(verts)
    return v, G.fix_winding(v, faces)


def sphere(center, radii, n_lon=16, n_lat=10, R=None):
    verts, faces = [], []
    for i in range(n_lat + 1):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            verts.append((math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)))
    for i in range(n_lat):
        for j in range(n_lon):
            a, b = i * n_lon + j, i * n_lon + (j + 1) % n_lon
            c, d = (i + 1) * n_lon + (j + 1) % n_lon, (i + 1) * n_lon + j
            if i == 0:
                faces.append((a, c, d))
            elif i == n_lat - 1:
                faces.append((a, b, d))
            else:
                faces.append((a, b, c, d))
    v = np.array(verts) * np.asarray(radii)
    if R is not None:
        v = v @ np.asarray(R).T
    v = v + np.asarray(center)
    return v, G.fix_winding(v, faces)


def loft(rings, close_start=True, close_end=True):
    """rings: list of (N,3) arrays with equal N. Returns verts, faces."""
    n = len(rings[0])
    verts = np.concatenate(rings)
    faces = []
    for k in range(len(rings) - 1):
        for m in range(n):
            faces.append((k * n + m, k * n + (m + 1) % n, (k + 1) * n + (m + 1) % n, (k + 1) * n + m))
    extra = []
    if close_start:
        c = len(verts) + len(extra)
        extra.append(rings[0].mean(axis=0))
        for m in range(n):
            faces.append((((m + 1) % n), m, c))
    if close_end:
        c = len(verts) + len(extra)
        extra.append(rings[-1].mean(axis=0))
        off = (len(rings) - 1) * n
        for m in range(n):
            faces.append((off + m, off + (m + 1) % n, c))
    if extra:
        verts = np.concatenate([verts, np.array(extra)])
    return verts, G.fix_winding(verts, faces)


def ring_points(center, R, rx, rz, n=16, exp=2.0, phase=0.0):
    """Superellipse ring in the local XZ plane of frame R (Y is the axis). Returns (n,3)."""
    pts = []
    for m in range(n):
        a = 2 * math.pi * m / n + phase
        c, s = math.cos(a), math.sin(a)
        x = rx * math.copysign(abs(c) ** (2.0 / exp), c)
        z = rz * math.copysign(abs(s) ** (2.0 / exp), s)
        pts.append(np.asarray(center) + R @ np.array([x, 0.0, z]))
    return np.array(pts)


def tube_along(points, radii, n=12, z_hint=(0, 0, 1), caps=True, exp=2.0, rz_scale=None):
    """Sweep a superellipse along a polyline. radii: per-point scalar or (rx, rz)."""
    pts = [np.asarray(p, float) for p in points]
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            d = pts[1] - pts[0]
        elif i == len(pts) - 1:
            d = pts[-1] - pts[-2]
        else:
            d = pts[i + 1] - pts[i - 1]
        R = frame(d, z_hint)
        r = radii[i]
        rx, rz = (r, r) if np.isscalar(r) else r
        rings.append(ring_points(p, R, rx, rz, n, exp))
    return loft(rings, caps, caps)


def merge_parts(parts):
    """Merge Part objects into arrays: verts, faces, and per-vertex arrays: part index, emit, accent."""
    vs, fs, part_idx, emit, accent, offs = [], [], [], [], [], []
    o = 0
    for k, p in enumerate(parts):
        vs.append(p.verts)
        fs.extend([tuple(i + o for i in f) for f in p.faces])
        part_idx.append(np.full(len(p.verts), k, dtype=np.int64))
        emit.append(np.full(len(p.verts), p.emit))
        accent.append(np.full(len(p.verts), p.accent))
        offs.append(o)
        o += len(p.verts)
    return np.concatenate(vs), fs, np.concatenate(part_idx), np.concatenate(emit), np.concatenate(accent)

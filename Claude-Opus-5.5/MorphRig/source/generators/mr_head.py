"""MorphRig Operative head: SDF anatomy, lat-long cage with eye/mouth openings,
Catmull-Clark refinement and explicit eyelid / lip / mouth-bag construction.

Topology summary (after subdivision):
  * 96 longitudes around the head, concentric loops of 28 vertices around each
    eye (2 canthus vertices + 13 upper + 13 lower lid vertices),
  * 36-vertex loops around the mouth (2 commissures + 17 upper + 17 lower),
    the lip contact line is a zero-width slit (closed lips at rest),
  * a mouth bag behind the lips encloses teeth and tongue,
  * the neck continues into the collar where it overlaps the body suit.
"""
import numpy as np
from mr_sdf import (Ellipsoid, Sphere, Capsule, RoundCone, Union, Mirror, Subtract, Plane,
                    ray_exit, project, normalize, length, gauss_bump, Displace, ProfileSolid)
from mr_meshkit import (Mesh, catmull_clark, relax_on_sdf, ring_quads, mirror_pairs,
                        enforce_symmetry, smooth_free, make_consistent)
from mr_params import H, EYE_R, v, nrm

HC = v(0.0, 0.0, 1.650)          # ray origin for the head cage
N_LON = 48                        # coarse longitudes (96 after subdivision)
LATS = [-77, -70, -62, -53, -45, -38, -30, -23, -16, -6, 5, 16, 28, 38, 48, 58, 68]
EYE_COLS = (1, 6)                 # coarse column range [1,6) -> 7.5..45 deg
EYE_ROWS = (10, 12)               # coarse face rows between lat rows 10..12 (5..28 deg)
MOUTH_COLS = (-3, 3)              # -22.5..22.5 deg
MOUTH_ROWS = (5, 8)               # lat rows 5..8 (-38..-16 deg)


# ------------------------------------------------------------------ anatomy
# Silhouette table: z, y_front, y_back, half width, y of widest point, n_front, n_back
HEAD_PROFILE = [
    (1.430, -0.047, 0.068, 0.0580, 0.012, 2.0, 2.0),
    (1.500, -0.045, 0.066, 0.0565, 0.012, 2.0, 2.0),
    (1.527, -0.047, 0.065, 0.0560, 0.012, 2.0, 2.1),
    (1.550, -0.060, 0.065, 0.0555, 0.010, 2.1, 2.1),
    (1.561, -0.074, 0.065, 0.0540, 0.006, 2.3, 2.1),
    (1.571, -0.081, 0.066, 0.0545, 0.002, 2.4, 2.1),
    (1.580, -0.077, 0.068, 0.0560, 0.000, 2.5, 2.1),
    (1.595, -0.078, 0.071, 0.0590, -0.002, 2.5, 2.1),
    (1.612, -0.079, 0.078, 0.0620, -0.003, 2.5, 2.1),
    (1.630, -0.079, 0.088, 0.0660, -0.002, 2.5, 2.1),
    (1.648, -0.078, 0.098, 0.0695, 0.000, 2.5, 2.1),
    (1.664, -0.081, 0.105, 0.0715, 0.004, 2.4, 2.1),
    (1.680, -0.086, 0.110, 0.0730, 0.008, 2.4, 2.1),
    (1.696, -0.089, 0.113, 0.0745, 0.012, 2.3, 2.1),
    (1.715, -0.087, 0.113, 0.0750, 0.016, 2.2, 2.1),
    (1.730, -0.083, 0.111, 0.0745, 0.018, 2.15, 2.1),
]
HEAD_DOME = (1.730, 1.786)


def face_parts():
    eye = H["eye_l"]
    feat = [
        Mirror(Capsule((0.011, -0.0822, 1.6950), (0.045, -0.0725, 1.6990), 0.0070)),  # brow ridge
        Mirror(Capsule((0.0575, 0.0010, 1.6250), (0.0548, -0.0020, 1.5890), 0.0085)),  # ramus
        Mirror(Capsule((0.0548, -0.0020, 1.5920), (0.0160, -0.0740, 1.5650), 0.0085)),  # mandible body
        Ellipsoid((0, -0.0795, 1.5710), (0.0190, 0.0120, 0.0140)),             # chin
        Ellipsoid((0, -0.0680, 1.6040), (0.0330, 0.0220, 0.0250)),             # muzzle / dental arch
        Ellipsoid((0, -0.0870, 1.6500), (0.0125, 0.0160, 0.0260), axis=(0, -0.45, -1.0), hint=(0, -1, 0)),  # nose body
        Capsule((0, -0.0885, 1.6800), (0, -0.1040, 1.6435), 0.0072),           # nose bridge
        Sphere((0, -0.1050, 1.6375), 0.0098),                                  # nose tip
        Mirror(Ellipsoid((0.0140, -0.0960, 1.6300), (0.0090, 0.0095, 0.0075))),  # alae
        Capsule((0, -0.1030, 1.6300), (0, -0.0940, 1.6235), 0.0047),           # columella
        Mirror(Ellipsoid((0.0712, 0.0040, 1.6480), (0.0090, 0.0180, 0.0270))),  # ear mass (under comm plate)
        Mirror(Sphere(eye, EYE_R + 0.0026)),                                   # eyeball + lids bulge
    ]
    return feat


def head_sdf(with_neck=True):
    eye = H["eye_l"]
    base = ProfileSolid(HEAD_PROFILE, dome_start=HEAD_DOME[0], ztop=HEAD_DOME[1])
    feat = face_parts()
    shell = Union([base] + [(f_, 0.010) for f_ in feat], k=0.010)
    # subtle hollows: temples and under the cheekbones
    hollows = Union([Mirror(Ellipsoid((0.078, -0.030, 1.683), (0.010, 0.022, 0.018))),
                     Mirror(Ellipsoid((0.058, -0.066, 1.616), (0.010, 0.014, 0.016)))], k=0.0)
    carved = Subtract(shell, hollows, k=0.012)
    sulcus = Mirror(Ellipsoid(eye + v(0.003, -0.012, 0.0125), (0.013, 0.006, 0.0045)))
    carved = Subtract(carved, sulcus, k=0.004)
    eyes = Mirror(Sphere(eye, EYE_R + 0.0030))
    return Union([carved, eyes], k=0.010)


# ------------------------------------------------------------------ helpers
def _lon_dirs(n):
    phi = 2 * np.pi * np.arange(n) / n
    return phi


def quad_cap(m, ring, n):
    """Fill a closed ring of 4n vertices with an n x n quad grid (Coons patch)."""
    ring = list(ring)
    assert len(ring) == 4 * n
    G = [[None] * (n + 1) for _ in range(n + 1)]
    for u in range(n + 1):
        G[u][0] = ring[u]
    for w in range(n + 1):
        G[n][w] = ring[n + w]
    for u in range(n + 1):
        G[n - u][n] = ring[(2 * n + u) % (4 * n)]
    for w in range(n + 1):
        G[0][n - w] = ring[(3 * n + w) % (4 * n)]
    P = lambda idx: m.v[idx]
    for u in range(1, n):
        for w in range(1, n):
            s, t = u / n, w / n
            p = ((1 - t) * P(G[u][0]) + t * P(G[u][n]) + (1 - s) * P(G[0][w]) + s * P(G[n][w])
                 - ((1 - s) * (1 - t) * P(G[0][0]) + s * (1 - t) * P(G[n][0])
                    + (1 - s) * t * P(G[0][n]) + s * t * P(G[n][n])))
            G[u][w] = int(m.add_verts(p[None])[0])
    faces = []
    for u in range(n):
        for w in range(n):
            faces.append((G[u][w], G[u + 1][w], G[u + 1][w + 1], G[u][w + 1]))
    return faces


def _chain_loop(m, mask):
    """Order boundary vertices in mask into a closed loop following boundary edges."""
    E, EF, _ = m.edges()
    adj = {}
    for (a, b), fl in zip(E, EF):
        if len(fl) == 1 and mask[a] and mask[b]:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
    start = next(iter(adj))
    loop = [start]
    prev, cur = None, start
    while True:
        nx = [x for x in adj[cur] if x != prev][0]
        if nx == start:
            break
        loop.append(nx)
        prev, cur = cur, nx
        if len(loop) > 5000:
            raise RuntimeError("loop chaining failed")
    return np.array(loop)


def _roll_to(loop, idx):
    k = int(np.nonzero(loop == idx)[0][0])
    return np.roll(loop, -k)


# ------------------------------------------------------------------ cage
def build_cage(sdf):
    m = Mesh()
    phi = _lon_dirs(N_LON)
    rows = []
    for th in LATS:
        t = np.radians(th)
        D = np.stack([np.sin(phi) * np.cos(t), -np.cos(phi) * np.cos(t), np.full_like(phi, np.sin(t))], -1)
        O = np.tile(HC, (N_LON, 1))
        d = ray_exit(sdf, O, D, tmax=0.4)
        rows.append(m.add_verts(O + d[:, None] * D))
    skip = set()

    def cols(rng):
        a, b = rng
        return [c % N_LON for c in range(a, b)]

    holes = {"eye_l": (EYE_ROWS, cols(EYE_COLS)),
             "eye_r": (EYE_ROWS, cols((N_LON - EYE_COLS[1], N_LON - EYE_COLS[0]))),
             "mouth": (MOUTH_ROWS, cols(MOUTH_COLS))}
    for name, (rr, cc) in holes.items():
        for i in range(rr[0], rr[1]):
            for j in cc:
                skip.add((i, j))
    for i in range(len(rows) - 1):
        for j in range(N_LON):
            if (i, j) in skip:
                continue
            m.add_face((rows[i][j], rows[i][(j + 1) % N_LON], rows[i + 1][(j + 1) % N_LON], rows[i + 1][j]))
    # crown cap (48 -> 12x12)
    for f in quad_cap(m, rows[-1], N_LON // 4):
        m.add_face(f)
    # mark hole boundaries and canthus/commissure markers
    for name, (rr, cc) in holes.items():
        g = m.group("hole_" + name)
        for i in range(rr[0], rr[1] + 1):
            for j in cc + [(cc[-1] + 1) % N_LON]:
                g[rows[i][j]] = True
        # corners: side midpoints of the hole rectangle
        side_cols = (cc[0], (cc[-1] + 1) % N_LON)
        if (rr[1] - rr[0]) % 2 == 0:
            mid = (rr[0] + rr[1]) // 2
            for c in side_cols:
                m.group("corner_" + name)[rows[mid][c]] = True
        else:
            lo = rr[0] + (rr[1] - rr[0]) // 2
            for c in side_cols:
                m.group("cornerseg_" + name)[rows[lo][c]] = True
                m.group("cornerseg_" + name)[rows[lo + 1][c]] = True
    m.group("neck_bottom", rows[0])
    return m, rows


def _fix_orientation(m, center=HC):
    fn = m.face_normals()
    for i, f in enumerate(m.f):
        c = m.v[list(f)].mean(0)
        if np.dot(fn[i], c - center) < 0:
            m.f[i] = tuple(reversed(f))


def _loop_with_corners(m, name, nv_coarse):
    hole = m.groups["hole_" + name]
    bnd = m.boundary_mask()
    loop = _chain_loop(m, hole & bnd)
    if ("corner_" + name) in m.groups:
        cm = m.groups["corner_" + name]
        corners = [i for i in loop if cm[i]]
    else:
        cm = m.groups["cornerseg_" + name]
        corners = [i for i in loop if cm[i] and i >= nv_coarse]
    assert len(corners) == 2, (name, corners)
    return loop, corners


# ------------------------------------------------------------------ eye patch
def eye_frame(side):
    C = H["eye_" + side]
    f = v(0, -1, 0)
    u = v(0, 0, 1)
    lat = v(1, 0, 0) if side == "l" else v(-1, 0, 0)
    return C, f, u, lat


def sph(C, f, u, lat, alpha, beta, r):
    """Point on sphere around eye centre: alpha yaw toward lateral, beta pitch."""
    alpha = np.asarray(alpha)
    beta = np.asarray(beta)
    d = (np.cos(beta) * np.sin(alpha))[..., None] * lat + (np.cos(beta) * np.cos(alpha))[..., None] * f \
        + np.sin(beta)[..., None] * u
    return C + np.asarray(r)[..., None] * d


EYE_SHAPE = dict(a_in=np.radians(-76.0), b_in=np.radians(-4.0), a_out=np.radians(64.0), b_out=np.radians(2.5),
                 up=np.radians(25.0), lo=np.radians(21.0), up_peak=-0.16, lo_peak=0.22)


def lid_curve(n_half, upper, shape=EYE_SHAPE, open_scale=1.0, grow=0.0):
    """Angles (alpha, beta) of the upper/lower margin incl. both corners (n_half+2 pts).

    grow (rad) expands the curve away from the opening (rings further out on the lid).
    """
    s = np.linspace(-1, 1, n_half + 2)
    a_in = shape["a_in"] - 0.30 * grow
    a_out = shape["a_out"] + 0.40 * grow
    a = a_in + (s + 1) / 2 * (a_out - a_in)
    base = shape["b_in"] + (s + 1) / 2 * (shape["b_out"] - shape["b_in"])
    if upper:
        pk = shape["up_peak"]
        q = np.clip((s - pk) / (1 + np.sign(s - pk) * pk), -1, 1)
        h = (shape["up"] * open_scale + grow) * (1 - q * q) ** 0.75
        return a, base + h
    pk = shape["lo_peak"]
    q = np.clip((s - pk) / (1 + np.sign(s - pk) * pk), -1, 1)
    h = (shape["lo"] * open_scale + grow) * (1 - q * q) ** 0.85
    return a, base - h


def build_eye_patch(m, side, loop, corners, sdf):
    """Replace the eye hole with explicit lid rings. loop: ordered boundary of hole."""
    C, f, u, lat = eye_frame(side)
    n = len(loop)
    half = n // 2 - 1
    # orient loop so it starts at the medial corner and runs over the upper lid
    medial = corners[0] if abs(m.v[corners[0]][0]) < abs(m.v[corners[1]][0]) else corners[1]
    lateral = corners[1] if medial == corners[0] else corners[0]
    loop = _roll_to(loop, medial)
    k_lat = int(np.nonzero(loop == lateral)[0][0])
    assert k_lat == half + 1, (k_lat, half)
    # upper half = vertices 1..half; check they are above the lower half
    zu = m.v[loop[1:half + 1]][:, 2].mean()
    zl = m.v[loop[half + 2:]][:, 2].mean()
    if zu < zl:
        loop = np.concatenate([[loop[0]], loop[1:][::-1]])
    G = m.v[loop].copy()   # outer boundary positions (fixed)

    def ring_points(grow, radius_fn, open_scale=1.0):
        au, bu = lid_curve(half, True, open_scale=open_scale, grow=grow)
        al, bl = lid_curve(half, False, open_scale=open_scale, grow=grow)
        # loop order: medial corner, upper (medial->lateral), lateral corner, lower (lateral->medial)
        A = np.concatenate([[au[0]], au[1:-1], [au[-1]], al[1:-1][::-1]])
        Bt = np.concatenate([[bu[0]], bu[1:-1], [bu[-1]], bl[1:-1][::-1]])
        is_up = np.concatenate([[0], np.ones(half), [0], np.zeros(half)])
        r = radius_fn(is_up) + 0.0024 * np.clip(-(A + np.radians(52)) / np.radians(26), 0, 1.4) ** 1.5
        return sph(C, f, u, lat, A, Bt, r)

    R = EYE_R
    specs = [
        # (angular growth rad, radius upper, radius lower)
        (0.000, R + 0.0010, R + 0.0010),   # A: inner lid edge against the eyeball
        (0.000, R + 0.0027, R + 0.0024),   # B: lid margin (lash line)
        (0.070, R + 0.0033, R + 0.0029),   # C: lid surface
        (0.170, R + 0.0034, R + 0.0033),   # D: tarsal plate / lid crease start
    ]
    rings = []
    for gi, ru, rl in specs:
        P = ring_points(gi, lambda up: np.where(up > 0, ru, rl))
        rings.append(m.add_verts(P))
    # E, F: interpolate D -> boundary in eye-centred spherical coordinates, then settle on the sdf
    D = m.v[rings[-1]] - C
    Gc = G - C

    def to_sph(X):
        r = length(X)
        xl, yf, zu = X @ lat, X @ f, X @ u
        al = np.arctan2(xl, yf)
        be = np.arcsin(np.clip(zu / r, -1, 1))
        return al, be, r

    aD, bD, rD = to_sph(D)
    aG, bG, rG = to_sph(Gc)
    aG = aD + (aG - aD + np.pi) % (2 * np.pi) - np.pi
    for t, proj in ((1 / 3.0, 0.55), (2 / 3.0, 0.85)):
        a = (1 - t) * aD + t * aG
        b = (1 - t) * bD + t * bG
        r = (1 - t) * rD + t * rG
        P = sph(C, f, u, lat, a, b, r)
        Q = project(sdf, P.copy(), iters=4)
        P = (1 - proj) * P + proj * Q
        rings.append(m.add_verts(P))
    rings.append(loop)
    faces = []
    for k in range(len(rings) - 1):
        faces += ring_quads(rings[k], rings[k + 1], closed=True)
    for fc in faces:
        m.add_face(fc)
    names = ["lid_A", "lid_B", "lid_C", "lid_D", "lid_E", "lid_F"]
    for nm, rg in zip(names, rings):
        m.group(f"{nm}_{side}", rg)
        up = m.group(f"{nm}_up_{side}")
        up[rg[1:half + 1]] = True
        lo = m.group(f"{nm}_lo_{side}")
        lo[rg[half + 2:]] = True
        cor = m.group(f"canthus_{side}")
        cor[[rg[0], rg[half + 1]]] = True
    m.group("eye_patch_" + side, np.concatenate(rings[:-1]))
    return rings


# ------------------------------------------------------------------ mouth patch
MOUTH = dict(half_w=0.0252, z0=H["mouth"][2])

# ring specs: (upper dz mm, upper protrusion mm, lower dz mm, lower protrusion mm, widen, bow)
LIP_SPECS = [
    (0.0, 1.2, 0.0, 1.2, 0.00, 0.0),    # L0 contact line (zero-width slit at rest)
    (1.9, 2.4, 2.1, 2.5, 0.03, 0.0),    # L1 lip front near the contact line
    (4.6, 3.2, 5.4, 3.3, 0.07, 0.3),    # L2 vermilion bulge
    (7.8, 2.2, 9.4, 1.9, 0.12, 1.1),    # L3 vermilion border ("white roll")
    (10.6, 0.9, 12.6, 0.6, 0.18, 0.8),  # L4 skin just outside the lips
    (14.0, 0.3, 16.4, 0.2, 0.26, 0.4),  # L5 blend ring
]


def _surface_y(sdf, x, z, y_start=0.0):
    """Front surface depth (y) of the sdf at (x, z), ray toward -Y."""
    O = np.stack([x, np.full_like(x, y_start), z], -1)
    D = np.tile(v(0, -1, 0), (len(x), 1))
    t = ray_exit(sdf, O, D, tmax=0.2)
    return y_start - t


def build_mouth_patch(m, loop, corners, sdf):
    n = len(loop)
    half = n // 2 - 1
    right = corners[0] if m.v[corners[0]][0] < m.v[corners[1]][0] else corners[1]
    left = corners[1] if right == corners[0] else corners[0]
    loop = _roll_to(loop, right)
    zu = m.v[loop[1:half + 1]][:, 2].mean()
    zl = m.v[loop[half + 2:]][:, 2].mean()
    if zu < zl:
        loop = np.concatenate([[loop[0]], loop[1:][::-1]])
    assert int(np.nonzero(loop == left)[0][0]) == half + 1
    G = m.v[loop].copy()
    base_sdf = head_sdf(with_neck=False)
    s = np.linspace(-1, 1, half + 2)          # right corner -> left corner
    W = MOUTH["half_w"]
    z0 = MOUTH["z0"]
    taper = (1 - np.abs(s) ** 2.2) ** 0.8
    z_line = z0 - 0.0011 * np.abs(s) ** 2.0 + 0.0003 * (1 - s * s)
    bow_shape = np.exp(-((np.abs(s) - 0.22) / 0.10) ** 2) - 0.6 * np.exp(-(s / 0.07) ** 2)

    def ring(spec, blend):
        duz, dup, dlz, dlp, wd, bw = spec
        x = s * W * (1 + wd)
        zu_ = z_line + duz * 1e-3 * taper + bw * 1e-3 * bow_shape * taper
        zl_ = z_line - dlz * 1e-3 * taper
        yu = _surface_y(base_sdf, x, zu_) - dup * 1e-3 * (0.25 + 0.75 * taper)
        yl = _surface_y(base_sdf, x, zl_) - dlp * 1e-3 * (0.25 + 0.75 * taper)
        up = np.stack([x, yu, zu_], -1)
        lo = np.stack([x, yl, zl_], -1)
        corner_r = 0.5 * (up[0] + lo[0])
        corner_l = 0.5 * (up[-1] + lo[-1])
        P = np.concatenate([[corner_r], up[1:-1], [corner_l], lo[1:-1][::-1]])
        if blend > 0:
            tgt = (1 - blend) * P + blend * G
            Q = project(sdf, tgt.copy(), iters=4)
            P = (1 - blend) * P + blend * Q
        return P

    blends = [0, 0, 0, 0, 0.12, 0.42]
    rings = []
    for spec, bl in zip(LIP_SPECS, blends):
        rings.append(m.add_verts(ring(spec, bl)))
    rings.append(loop)
    for k in range(len(rings) - 1):
        for fc in ring_quads(rings[k], rings[k + 1], closed=True):
            m.add_face(fc)
    # inner mouth: from the contact line into a bag enclosing teeth and tongue
    L0 = rings[0]
    P0 = m.v[L0].copy()
    is_up = np.concatenate([[0], np.ones(half), [0], np.zeros(half)])
    is_lo = np.concatenate([[0], np.zeros(half), [0], np.ones(half)])
    sx = np.concatenate([[s[0]], s[1:-1], [s[-1]], s[1:-1][::-1]])
    inner_specs = [
        # (up_z, lo_z, back, width scale)
        (0.0032, 0.0034, 0.0035, 0.99),
        (0.0080, 0.0090, 0.0085, 0.99),
        (0.0140, 0.0175, 0.0180, 1.06),
        (0.0160, 0.0215, 0.0330, 1.10),
        (0.0120, 0.0170, 0.0480, 0.86),
    ]
    inner = [L0]
    for (uz, lz, back, ws) in inner_specs:
        P = P0.copy()
        tp = 1 - 0.55 * np.abs(sx) ** 2
        P[:, 2] += is_up * uz * tp - is_lo * lz * tp
        P[:, 1] += back * (0.6 + 0.4 * (1 - np.abs(sx) ** 2)) + 0.004 * np.abs(sx) ** 2 * (back > 0.01)
        P[:, 0] *= ws
        inner.append(m.add_verts(P))
    for k in range(len(inner) - 1):
        for fc in ring_quads(inner[k + 1], inner[k], closed=True):
            m.add_face(fc)
    last = inner[-1]
    cap_start = m.nv
    for fc in quad_cap(m, last, len(last) // 4):
        m.add_face(fc[::-1])
    names = ["lip_L0", "lip_L1", "lip_L2", "lip_L3", "lip_L4", "lip_L5"]
    for nm, rg in zip(names, rings):
        m.group(nm, rg)
        m.group(nm + "_up")[rg[1:half + 1]] = True
        m.group(nm + "_lo")[rg[half + 2:]] = True
        m.group("mouth_corner")[[rg[0], rg[half + 1]]] = True
    for k, rg in enumerate(inner[1:]):
        m.group(f"mouth_in{k + 1}", rg)
        m.group(f"mouth_in{k + 1}_up")[rg[1:half + 1]] = True
        m.group(f"mouth_in{k + 1}_lo")[rg[half + 2:]] = True
    bag = m.group("mouth_bag")
    for rg in inner[1:]:
        bag[rg] = True
    bag[cap_start:] = True
    return rings, inner


# ------------------------------------------------------------------ build
def build_head():
    sdf = head_sdf()
    cage, rows = build_cage(sdf)
    remap = cage.compact()
    rows = [remap[np.asarray(r)] for r in rows]
    _fix_orientation(cage)
    nvc = cage.nv
    m = catmull_clark(cage)
    # reproject and relax the subdivided surface
    m.v = project(sdf, m.v, iters=5)
    pairs = mirror_pairs(m, tol=2e-3)
    relax_on_sdf(m, sdf, iters=8, lam=0.4, sym_pairs=pairs)
    enforce_symmetry(m, pairs)
    loops = {}
    for name in ("eye_l", "eye_r", "mouth"):
        loops[name] = _loop_with_corners(m, name, nvc)
    eye_rings = {}
    for side in ("l", "r"):
        lp, cr = loops["eye_" + side]
        eye_rings[side] = build_eye_patch(m, side, lp, cr, sdf)
    lp, cr = loops["mouth"]
    lip_rings, inner = build_mouth_patch(m, lp, cr, sdf)
    # final relax of the surrounding skin (feature rings pinned)
    pinned = np.zeros(m.nv, bool)
    for side in ("l", "r"):
        for rg in eye_rings[side][:4]:
            pinned[rg] = True
    for rg in lip_rings[:4]:
        pinned[rg] = True
    for rg in inner[1:]:
        pinned[rg] = True
    pinned[m.groups["mouth_bag"]] = True
    pairs = mirror_pairs(m, tol=1.5e-3)
    free_region = ~pinned
    relax_on_sdf(m, sdf, iters=6, lam=0.35, pinned=pinned, sym_pairs=pairs)
    enforce_symmetry(m, pairs)
    make_consistent(m, outward_point=HC)
    m.compact()
    pairs = mirror_pairs(m, tol=1.5e-3)
    m.sym_pairs = pairs
    m.eye_rings = eye_rings
    m.lip_rings = lip_rings
    m.mouth_inner = inner
    m.cage_rows = rows
    return m, sdf

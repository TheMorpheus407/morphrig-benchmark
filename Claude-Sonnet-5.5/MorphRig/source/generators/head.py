"""Operative head: structured box-grid 'cube-sphere' with per-axis non-uniform spacing so eye, nose and mouth patches
can be addressed by index and carry dense loops. Features are added with displacement fields; eyelid and mouth openings,
ears, neck tube, eyeballs, teeth and tongue are added by functions below. Blender + numpy; character faces +X, left = +Y.
"""
import math
import numpy as np
import skeleton_def as S
import mr_geo as G

CENTER = np.array([-0.004, 0.0, 1.6875])
RADII = np.array([0.100, 0.080, 0.113])
BOX = np.array([1.0, 1.1, 1.3])        # box half extents: controls the angular size of each patch
NX, NY = 16, 26


def _front_q_for_z(zs):
    """Invert z_real(qz) on the front face centre line: z = Cz + Rz*c*qz/sqrt(a^2 + c^2 qz^2)."""
    a, c = BOX[0], BOX[2]
    out = []
    for z in zs:
        s = (z - CENTER[2]) / RADII[2]      # = c*q/sqrt(a^2+c^2 q^2)
        s = max(min(s, 0.999), -0.999)
        # s^2 (a^2 + c^2 q^2) = c^2 q^2 -> q^2 (c^2 - s^2 c^2) = s^2 a^2
        q = math.copysign(math.sqrt((s * s * a * a) / (c * c * (1 - s * s))), s)
        out.append(q)
    return np.array(out)


# real-world z lines across the face (bottom -> top) between the front face edges
FACE_Z = [1.606, 1.6125, 1.618, 1.6235, 1.629, 1.6345, 1.641, 1.648, 1.6555, 1.663, 1.670, 1.6765, 1.681, 1.6855,
          1.690, 1.6945, 1.700, 1.7065, 1.714, 1.723, 1.733, 1.745, 1.758]


def axis_lines():
    cy_half = np.array([(i / (NY // 2)) ** 1.30 for i in range(NY // 2 + 1)])   # 0 .. 1, dense at the centre
    cy = np.concatenate([-cy_half[::-1][:-1], cy_half])
    qz = _front_q_for_z(FACE_Z)
    cz = np.concatenate([[-1.0], qz, [1.0]])
    cx = np.linspace(-1.0, 1.0, NX + 1)
    return cx, cy, cz


class HeadGrid:
    def __init__(self):
        self.cx, self.cy, self.cz = axis_lines()
        self.nx, self.ny, self.nz = len(self.cx) - 1, len(self.cy) - 1, len(self.cz) - 1
        self.vid = {}
        self.verts = []
        self.faces = []
        self.cell_face = {}     # (side, a, b) -> face index
        self._build()

    def _v(self, i, j, k):
        key = (i, j, k)
        if key not in self.vid:
            self.vid[key] = len(self.verts)
            self.verts.append((self.cx[i], self.cy[j], self.cz[k]))
        return self.vid[key]

    def _quad(self, side, a, b, vs):
        self.cell_face[(side, a, b)] = len(self.faces)
        self.faces.append(tuple(vs))

    def _build(self):
        nx, ny, nz = self.nx, self.ny, self.nz
        v = self._v
        for j in range(ny):
            for k in range(nz):
                self._quad('+x', j, k, [v(nx, j, k), v(nx, j + 1, k), v(nx, j + 1, k + 1), v(nx, j, k + 1)])
                self._quad('-x', j, k, [v(0, j, k), v(0, j, k + 1), v(0, j + 1, k + 1), v(0, j + 1, k)])
        for i in range(nx):
            for k in range(nz):
                self._quad('+y', i, k, [v(i, ny, k), v(i, ny, k + 1), v(i + 1, ny, k + 1), v(i + 1, ny, k)])
                self._quad('-y', i, k, [v(i, 0, k), v(i + 1, 0, k), v(i + 1, 0, k + 1), v(i, 0, k + 1)])
            for j in range(ny):
                self._quad('+z', i, j, [v(i, j, nz), v(i + 1, j, nz), v(i + 1, j + 1, nz), v(i, j + 1, nz)])
                self._quad('-z', i, j, [v(i, j, 0), v(i, j + 1, 0), v(i + 1, j + 1, 0), v(i + 1, j, 0)])
        q = np.array(self.verts)
        d = q * BOX[None, :]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        self.q = q
        self.P = CENTER + RADII * d


def front_cells(grid, y_lo, y_hi, z_lo, z_hi):
    """Front-face cell index ranges whose corner lines are nearest to the given real-space extents (metres)."""
    nx = grid.nx
    ys = np.array([grid.P[grid.vid[(nx, j, grid.nz // 2)]][1] for j in range(grid.ny + 1)])
    zs = np.array([grid.P[grid.vid[(nx, grid.ny // 2, k)]][2] for k in range(grid.nz + 1)])
    j0, j1 = int(np.argmin(abs(ys - y_lo))), int(np.argmin(abs(ys - y_hi)))
    k0, k1 = int(np.argmin(abs(zs - z_lo))), int(np.argmin(abs(zs - z_hi)))
    return j0, j1, k0, k1


def head_arrays(grid):
    return np.array(grid.P), list(grid.faces)


# ----------------------------------------------------------------------------- shaping

EYE_C = np.array([0.0715, 0.031, 1.6855])

# (name, centre, radii, amount along the surface normal); mirrored across Y unless centre y == 0
BUMPS = [
    ('brow_ridge', (0.082, 0.030, 1.710), (0.018, 0.030, 0.008), 0.0055),
    ('lid_bulge', (0.086, 0.031, 1.685), (0.016, 0.019, 0.013), 0.0040),
    ('orbit', (0.078, 0.031, 1.685), (0.030, 0.038, 0.030), -0.0045),
    ('nose_bridge', (0.090, 0.0, 1.672), (0.014, 0.0075, 0.022), 0.0085),
    ('nose_tip', (0.104, 0.0, 1.652), (0.012, 0.010, 0.009), 0.0125),
    ('nose_ala', (0.094, 0.0145, 1.649), (0.009, 0.008, 0.008), 0.0055),
    ('nostril', (0.099, 0.0085, 1.643), (0.006, 0.005, 0.004), -0.0035),
    ('philtrum', (0.095, 0.0, 1.635), (0.008, 0.004, 0.007), -0.0018),
    ('lip_up', (0.096, 0.0, 1.6295), (0.010, 0.024, 0.0055), 0.0048),
    ('lip_low', (0.096, 0.0, 1.6165), (0.010, 0.022, 0.0060), 0.0052),
    ('mouth_corner', (0.084, 0.027, 1.6235), (0.006, 0.006, 0.006), -0.0022),
    ('chin', (0.086, 0.0, 1.5985), (0.012, 0.020, 0.013), 0.0075),
    ('mentolabial', (0.093, 0.0, 1.6075), (0.006, 0.018, 0.0045), -0.0030),
    ('cheekbone', (0.058, 0.052, 1.671), (0.020, 0.020, 0.014), 0.0050),
    ('cheek', (0.064, 0.046, 1.640), (0.026, 0.024, 0.020), 0.0035),
    ('nasolabial', (0.090, 0.022, 1.640), (0.008, 0.006, 0.016), -0.0022),
    ('forehead', (0.082, 0.0, 1.745), (0.020, 0.050, 0.040), 0.0040),
    ('temple', (0.030, 0.070, 1.705), (0.020, 0.015, 0.020), -0.0030),
    ('jawline', (-0.010, 0.062, 1.612), (0.030, 0.012, 0.012), 0.0030),
]

# the nose is added after the smoothing pass (16 Taubin iterations flatten a 1 cm feature on this 5 mm grid). It is a height field in X over the
# (y, z) plane, so it cannot fold: (name, centre (y, z), sigma (y, z) in metres, height in metres); mirrored across Y unless centre y == 0
NOSE_BUMPS = [
    ('nose_root', (0.0, 1.688), (0.0070, 0.0070), 0.0040),
    ('nose_dorsum', (0.0, 1.667), (0.0068, 0.0105), 0.0110),
    ('nose_tip', (0.0, 1.649), (0.0085, 0.0068), 0.0165),
    ('nose_ala', (0.0150, 1.645), (0.0062, 0.0062), 0.0065),
    ('nostril', (0.0085, 1.640), (0.0038, 0.0040), -0.0035),
]

# face plane profile: z -> front x (metres); the ellipsoid is flattened toward it
FACE_PLANE = [(1.560, 0.030), (1.585, 0.070), (1.603, 0.084), (1.625, 0.091), (1.655, 0.093), (1.685, 0.092), (1.715, 0.090),
              (1.750, 0.084), (1.775, 0.072), (1.792, 0.045), (1.800, 0.000)]
# half-width profile: z -> multiplier on y (the jaw stays full so the chin is round, the brow level is widest)
WIDTH_PROFILE = [(1.560, 0.88), (1.575, 0.95), (1.590, 0.985), (1.610, 0.99), (1.650, 1.00), (1.690, 1.04), (1.735, 1.04), (1.770, 1.02), (1.792, 0.93), (1.800, 0.80)]


def shape_head(P, faces, detail=1.0):
    P = P.copy()
    zs = P[:, 2]
    # flatten the front toward the face plane
    zz = np.clip(zs, CENTER[2] - RADII[2] * 0.999, CENTER[2] + RADII[2] * 0.999)
    ell_front = CENTER[0] + RADII[0] * np.sqrt(1 - ((zz - CENTER[2]) / RADII[2]) ** 2)
    fz = np.array([z for z, _ in FACE_PLANE])
    fx = np.array([x for _, x in FACE_PLANE])
    target = np.interp(zs, fz, fx)
    gain = (target - CENTER[0]) / np.maximum(ell_front - CENTER[0], 1e-4)
    w = G.smoothstep((P[:, 0] - CENTER[0]) / 0.045)
    P[:, 0] = CENTER[0] + (P[:, 0] - CENTER[0]) * (1 + (gain - 1) * w)
    wy = np.interp(zs, [z for z, _ in WIDTH_PROFILE], [m for _, m in WIDTH_PROFILE])
    P[:, 1] *= wy
    n = G.normals(P, faces)
    disp = np.zeros_like(P)
    for name, c, r, amt in BUMPS:
        for sy in ((1, -1) if abs(c[1]) > 1e-6 else (1,)):
            cc = (c[0], c[1] * sy, c[2])
            disp += G.gauss_bump(P, cc, r, 'normal', amt * detail, n)
    P = P + disp
    return P


# ----------------------------------------------------------------------------- topology: openings, pockets, neck

class Work:
    """Mutable head mesh: vertex list + face list with kill flags."""

    def __init__(self, P, F):
        self.P = [np.array(p, dtype=np.float64) for p in P]
        self.F = [tuple(f) for f in F]
        self.dead = set()

    def add_v(self, p):
        self.P.append(np.array(p, dtype=np.float64))
        return len(self.P) - 1

    def add_f(self, f):
        self.F.append(tuple(int(i) for i in f))
        return len(self.F) - 1

    def kill(self, idxs):
        self.dead.update(idxs)

    def arrays(self):
        faces = [f for i, f in enumerate(self.F) if i not in self.dead]
        return np.array(self.P), faces


def _order_loop_by_angle(P, loop, center):
    return loop


def smooth_region(w, center, radius, pinned, iters=4, lam=0.5):
    """Laplacian-smooth live vertices within radius of center (numpy mask), keeping pinned vertex ids fixed."""
    P = np.array(w.P)
    live = set()
    for i, f in enumerate(w.F):
        if i in w.dead:
            continue
        live.update(f)
    adj = {}
    for i, f in enumerate(w.F):
        if i in w.dead:
            continue
        k = len(f)
        for m in range(k):
            a, b = f[m], f[(m + 1) % k]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    sel = [i for i in live if np.linalg.norm(P[i] - center) < radius and i not in pinned and i in adj]
    for _ in range(iters):
        new = {}
        for i in sel:
            new[i] = P[i] + lam * (np.mean([P[j] for j in adj[i]], axis=0) - P[i])
        for i, p in new.items():
            P[i] = p
    for i in sel:
        w.P[i] = P[i]


def smooth_face_surface(w, info, iters=8, lam=0.45, mu=-0.47, bounds=((0.03, 0.12), (-0.078, 0.078), (1.585, 1.765))):
    """Taubin (lambda|mu) smoothing of the front of the face: removes the small ridges the bumps and the eye/mouth surgery leave behind
    (they show up as dark triangular patches under hard light) without shrinking the shape. Eyelid rims, pocket rings and the mouth
    rings stay exactly where they are."""
    P = np.array(w.P)
    live = set()
    adj = {}
    for i, f in enumerate(w.F):
        if i in w.dead:
            continue
        live.update(f)
        k = len(f)
        for m in range(k):
            a, b = f[m], f[(m + 1) % k]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    pinned = set()
    for nm in ('eye_l', 'eye_r'):
        rings = info[nm]
        pinned.update(rings[0])                      # lid rim
        for ring in rings[3:]:                       # pocket rings
            pinned.update(ring)
    for ru, rl in info['mouth']['rings']:
        pinned.update(ru)
        pinned.update(rl)
    (x0, x1), (y0, y1), (z0, z1) = bounds
    sel = [i for i in live if i not in pinned and i in adj and x0 < P[i, 0] < x1 and y0 < P[i, 1] < y1 and z0 < P[i, 2] < z1]
    # fade the effect towards the region border so the smoothed patch blends into the untouched surface
    wgt = {}
    for i in sel:
        d = min(P[i, 0] - x0, x1 - P[i, 0], P[i, 1] - y0, y1 - P[i, 1], P[i, 2] - z0, z1 - P[i, 2])
        wgt[i] = float(np.clip(d / 0.012, 0.0, 1.0))
    for _ in range(iters):
        for step in (lam, mu):
            new = {i: P[i] + step * wgt[i] * (np.mean([P[j] for j in adj[i]], axis=0) - P[i]) for i in sel}
            for i, p in new.items():
                P[i] = p
    for i in sel:
        w.P[i] = P[i]


def _quad_warp_deg(P, f):
    """Angle between the normals of the two triangles of a quad (0 for a planar quad)."""
    n1 = np.cross(P[f[1]] - P[f[0]], P[f[2]] - P[f[0]])
    n2 = np.cross(P[f[2]] - P[f[0]], P[f[3]] - P[f[0]])
    l1, l2 = np.linalg.norm(n1), np.linalg.norm(n2)
    if l1 < 1e-15 or l2 < 1e-15:
        return 180.0
    return float(np.degrees(np.arccos(np.clip(np.dot(n1, n2) / (l1 * l2), -1.0, 1.0))))


def relax_warped_quads(w, info, threshold=16.0, iters=60, lam=0.5, bounds=((0.03, 0.12), (-0.078, 0.078), (1.585, 1.765)), skip_nose=False):
    """Move the vertices of strongly warped quads towards the mean of their neighbours until the fold is gone. The junction where the radial
    grid around an eye meets the grid of the face leaves a few folded quads that show as scratches under a hard light. Eyelid rims, pocket
    rings and mouth rings stay where they are."""
    P = np.array(w.P)
    faces = [f for i, f in enumerate(w.F) if i not in w.dead]
    adj = {}
    for f in faces:
        k = len(f)
        for m in range(k):
            a, b = f[m], f[(m + 1) % k]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    pinned = set()
    for nm in ('eye_l', 'eye_r'):
        rings = info[nm]
        pinned.update(rings[0])
        for ring in rings[3:]:
            pinned.update(ring)
    for ru, rl in info['mouth']['rings']:
        pinned.update(ru)
        pinned.update(rl)
    (x0, x1), (y0, y1), (z0, z1) = bounds
    quads = [f for f in faces if len(f) == 4 and x0 < np.mean(P[list(f), 0]) < x1 and y0 < np.mean(P[list(f), 1]) < y1 and z0 < np.mean(P[list(f), 2]) < z1]
    if skip_nose:     # the nose itself is meant to be steep: only the flanks and the rest of the face are relaxed
        quads = [f for f in quads if not (abs(np.mean(P[list(f), 1])) < 0.012 and 1.636 < np.mean(P[list(f), 2]) < 1.695)]
    for _ in range(iters):
        bad = set()
        for f in quads:
            if _quad_warp_deg(P, f) > threshold:
                bad.update(f)
        bad -= pinned
        if not bad:
            break
        new = {i: P[i] + lam * (np.mean([P[j] for j in adj[i]], axis=0) - P[i]) for i in bad}
        for i, p in new.items():
            P[i] = p
    for i in range(len(P)):
        w.P[i] = P[i]


def add_nose(w, amount=1.0):
    """Raise the nose as a height field in +X over the live front of the head mesh (x above 5 cm)."""
    P = np.array(w.P)
    front = P[:, 0] > 0.05
    h = np.zeros(len(P))
    for name, (cy, cz), (sy_, sz_), amt in NOSE_BUMPS:
        for sg in ((1, -1) if abs(cy) > 1e-6 else (1,)):
            h += amt * amount * np.exp(-0.5 * (((P[:, 1] - cy * sg) / sy_) ** 2 + ((P[:, 2] - cz) / sz_) ** 2))
    for i in np.nonzero(front & (np.abs(h) > 1e-7))[0]:
        w.P[i] = w.P[i] + np.array([h[i], 0.0, 0.0])


def _slerp_dir(a, b, t):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    d = float(np.clip(a @ b, -1, 1))
    om = math.acos(d)
    if om < 1e-6:
        return a
    return (math.sin((1 - t) * om) * a + math.sin(t * om) * b) / math.sin(om)


def eye_openings(w, grid, side_names=('l', 'r'), R_ball=0.0122, gap=0.0024, a_w=0.0128, b_h=0.0060, p_exp=2.3):
    """Radial eye construction: delete a 10x6 patch around each eye, rebuild the region as an almond lid rim (on a sphere
    around the eyeball) plus two blended concentric rings out to the patch boundary, then a spherical pocket behind the rim.
    Returns rings dict: info['eye_l'] = [rim, ring1, ring2, pocket1..K] (vertex id lists, 32 each)."""
    out = {}
    j0, j1, k0, k1 = front_cells(grid, 0.0155, 0.0465, 1.6810, 1.6900)
    for name, sy in (('l', 1.0), ('r', -1.0)):
        jl, jh = (j0 - 2, j1 + 2)
        if sy < 0:
            jl, jh = grid.ny - (j1 + 2), grid.ny - (j0 - 2)
        cells = [grid.cell_face[('+x', j, k)] for j in range(jl, jh) for k in range(k0 - 2, k1 + 2)]
        removed = [w.F[c] for c in cells]
        w.kill(cells)
        loops = G.boundary_loops(len(w.P), removed)
        outer = max(loops, key=len)
        ec = np.array([EYE_C[0], sy * EYE_C[1], EYE_C[2]])
        # order by azimuth about the eye centre (y towards +, z up)
        alpha = np.array([math.atan2(w.P[i][2] - ec[2], w.P[i][1] - ec[1]) for i in outer])
        order = np.argsort(alpha)
        outer = [outer[k] for k in order]
        alpha = alpha[order]
        n = len(outer)
        R_lid = R_ball + gap
        rim = []
        for a_ in alpha:
            c, s_ = math.cos(a_), math.sin(a_)
            rho = (abs(c / a_w) ** p_exp + abs(s_ / b_h) ** p_exp) ** (-1.0 / p_exp)
            dy, dz = rho * c, rho * s_
            rad = max(R_lid ** 2 - dy * dy - dz * dz, 0.0)
            rim.append(w.add_v(np.array([ec[0] + math.sqrt(rad), ec[1] + dy, ec[2] + dz])))
        rings = [rim]
        d_r = [w.P[i] - ec for i in rim]
        d_o = [w.P[i] - ec for i in outer]
        for t_ in (0.36, 0.70):
            te = t_ * t_ * (3 - 2 * t_)
            ring = []
            for m in range(n):
                d = _slerp_dir(d_r[m], d_o[m], te)
                r = np.linalg.norm(d_r[m]) * (1 - te) + np.linalg.norm(d_o[m]) * te
                ring.append(w.add_v(ec + d * r))
            rings.append(ring)
        # faces rim -> ring1 -> ring2 -> outer
        chain = [rim] + rings[1:] + [outer]
        for a_r, b_r in zip(chain[:-1], chain[1:]):
            for m in range(n):
                w.add_f((a_r[m], a_r[(m + 1) % n], b_r[(m + 1) % n], b_r[m]))
        smooth_region(w, ec, 0.030, set(rim) | set(outer), iters=3, lam=0.4)
        # spherical pocket behind the rim
        K = 4
        theta0 = [math.acos(np.clip(d[0] / np.linalg.norm(d), -1, 1)) for d in d_r]
        az = [math.atan2(d[2], d[1]) for d in d_r]
        Rcup = R_ball + 0.0009
        pocket = []
        for kk in range(1, K + 1):
            ring = []
            for m in range(n):
                th = theta0[m] + (math.radians(128) - theta0[m]) * (kk / K)
                ring.append(w.add_v(ec + Rcup * np.array([math.cos(th), math.sin(th) * math.cos(az[m]), math.sin(th) * math.sin(az[m])])))
            pocket.append(ring)
        pole = w.add_v(ec + Rcup * np.array([-1.0, 0, 0]))
        prev = rim
        for ring in pocket:
            for m in range(n):
                w.add_f((prev[m], prev[(m + 1) % n], ring[(m + 1) % n], ring[m]))
            prev = ring
        for m in range(n):
            w.add_f((prev[m], prev[(m + 1) % n], pole))
        out['eye_' + name] = [rim, rings[1], rings[2]] + pocket
        out['eye_' + name + '_centre'] = ec
        out['eye_' + name + '_outer'] = outer
    return out


def mouth_slit(w, grid, y_half=0.0265, z_line=1.6235, depth_profile=None):
    """Open a zero-width slit along the mouth line between the corners, then extrude a closed cavity behind it.
    Returns dict with 'upper', 'lower' chains and cavity rings."""
    nx = grid.nx
    # locate the mouth-line row and corner columns on the front face
    j0, j1, k0, k1 = front_cells(grid, -y_half, y_half, z_line, z_line)
    kline = k0  # grid line index nearest to z_line
    verts_on_line = [grid.vid[(nx, j, kline)] for j in range(j0, j1 + 1)]
    corner_l, corner_r = verts_on_line[0], verts_on_line[-1]
    interior = verts_on_line[1:-1]
    dup = {}
    for vi in interior:
        dup[vi] = w.add_v(w.P[vi])
    # faces below the line use the duplicated vertices
    for j in range(j0, j1):
        fi = grid.cell_face[('+x', j, kline - 1)]
        f = w.F[fi]
        w.F[fi] = tuple(dup.get(i, i) for i in f)
    upper = verts_on_line                               # corner_l ... corner_r (original verts)
    lower = [corner_l] + [dup[v] for v in interior] + [corner_r]
    return {'upper': upper, 'lower': lower, 'kline': kline}


def mouth_cavity(w, slit, depth=(0.004, 0.009, 0.017, 0.031, 0.050), gap=(0.0035, 0.0075, 0.0125, 0.0175, 0.021), half_w_scale=(1.0, 1.02, 1.05, 1.08, 1.05)):
    up, lo = slit['upper'], slit['lower']
    pts_u = np.array([w.P[i] for i in up])
    y0, y1 = pts_u[0][1], pts_u[-1][1]
    ymid = (y0 + y1) / 2
    hw = abs(y1 - y0) / 2
    zline = pts_u[:, 2].mean()
    ring_u = list(up)
    ring_l = list(lo)
    rings = [(ring_u, ring_l)]
    for d, g, hs in zip(depth, gap, half_w_scale):
        ru, rl = [], []
        for k, i in enumerate(up):
            p = w.P[i]
            u = (p[1] - ymid) / hw
            prof = max(1 - u * u, 0.0) ** 0.55
            ru.append(i if False else w.add_v(np.array([p[0] - d, ymid + (p[1] - ymid) * hs, zline + g * prof])))
        for k, i in enumerate(lo):
            p = w.P[i]
            u = (p[1] - ymid) / hw
            prof = max(1 - u * u, 0.0) ** 0.55
            rl.append(w.add_v(np.array([p[0] - d, ymid + (p[1] - ymid) * hs, zline - g * prof])))
        # corners are shared between upper and lower chain: merge them
        rl[0], rl[-1] = ru[0], ru[-1]
        rings.append((ru, rl))
    # faces between rings (upper chain sheet and lower chain sheet)
    for (au, al), (bu, bl) in zip(rings[:-1], rings[1:]):
        for m in range(len(au) - 1):
            w.add_f((au[m], au[m + 1], bu[m + 1], bu[m]))
        for m in range(len(al) - 1):
            w.add_f((al[m + 1], al[m], bl[m], bl[m + 1]))
    # back cap: close the last ring (upper chain + reversed lower chain) with a fan
    au, al = rings[-1]
    loop = list(au) + list(reversed(al[1:-1]))
    c = np.mean([w.P[i] for i in loop], axis=0)
    cid = w.add_v(c + np.array([-0.006, 0, 0]))
    for m in range(len(loop)):
        w.add_f((loop[m], loop[(m + 1) % len(loop)], cid))
    return {'rings': rings}


def neck_peg(w, radius=0.047, z_bottom=1.520, z_top=1.628, n=24):
    """Separate closed neck tube: its lower part hides inside the body's neck stump and collar, its top inside the head."""
    zs = np.linspace(z_bottom, z_top, 9)
    rings = []
    for z in zs:
        t = (z - z_bottom) / (z_top - z_bottom)
        cx = 0.010 - 0.016 * t
        r = radius * (1.0 + 0.06 * math.sin(t * math.pi * 0.9)) * (1.0 if t < 0.8 else 1.0 - 0.6 * (t - 0.8) / 0.2 * 0.5)
        ring = []
        for m in range(n):
            a = 2 * math.pi * m / n
            ring.append(w.add_v(np.array([cx + r * 1.02 * math.cos(a), r * math.sin(a), z])))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for m in range(n):
            w.add_f((rings[k][m], rings[k][(m + 1) % n], rings[k + 1][(m + 1) % n], rings[k + 1][m]))
    for ring, zc in ((rings[0], z_bottom), (rings[-1], z_top)):
        c = w.add_v(np.array([np.mean([w.P[i][0] for i in ring]), 0.0, zc]))
        for m in range(n):
            w.add_f((ring[m], ring[(m + 1) % n], c) if zc == z_top else (ring[(m + 1) % n], ring[m], c))
    return {'rings': rings}


def compact_with_info(V, F, info):
    """Drop vertices no face uses (left behind by the eye and mouth surgery) and renumber the vertex ids stored in `info`."""
    used = sorted({int(i) for f in F for i in f})
    remap = {old: new for new, old in enumerate(used)}
    V2 = np.asarray(V)[used]
    F2 = [tuple(remap[int(i)] for i in f) for f in F]

    def rm(x, key=None):
        if isinstance(x, dict):
            return {k: (x[k] if k == 'kline' else rm(x[k], k)) for k in x}
        if isinstance(x, tuple):
            return tuple(rm(y) for y in x)
        if isinstance(x, list):
            if x and isinstance(x[0], (int, np.integer)):
                return [remap[int(i)] for i in x]
            return [rm(y) for y in x]
        return x
    return V2, F2, rm(info)


def build_head(detail=1.0, smooth_iters=16):
    g = HeadGrid()
    P, F = head_arrays(g)
    F = G.fix_winding(P, F)
    # fix_winding rebuilds faces via bmesh and may reorder; rebuild the cell map by matching vertex sets
    fmap = {frozenset(f): i for i, f in enumerate(F)}
    old = list(g.cell_face.items())
    g.cell_face = {}
    orig_faces = HeadGrid()  # same construction order -> original vertex tuples
    for key, idx in old:
        vs = frozenset(orig_faces.faces[idx])
        g.cell_face[key] = fmap[vs]
    P = shape_head(P, F, detail)
    w = Work(P, F)
    info = {}
    info.update(eye_openings(w, g))
    slit = mouth_slit(w, g)
    info['mouth'] = mouth_cavity(w, slit)
    info['mouth_slit'] = slit
    if smooth_iters:
        smooth_face_surface(w, info, iters=smooth_iters)
    relax_warped_quads(w, info)
    add_nose(w)
    relax_warped_quads(w, info, skip_nose=True)
    V, Fc = w.arrays()
    n0 = len(V)
    info['neck'] = neck_peg(w)
    V, Fc = w.arrays()
    Fc = G.fix_winding(V, Fc)
    V, Fc, info = compact_with_info(V, Fc, info)
    return V, Fc, info


# ----------------------------------------------------------------------------- small parts


def uv_sphere(center, radii, n_lon=24, n_lat=14, axis='x'):
    """Sphere with poles along +/-X (or Z). Returns verts, faces, and per-vertex polar angle (from +axis)."""
    verts, faces, polar = [], [], []
    for i in range(n_lat + 1):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            if axis == 'x':
                d = (math.cos(th), math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph))
            else:
                d = (math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))
            verts.append(tuple(np.array(center) + np.array(radii) * np.array(d)))
            polar.append(th)
    for i in range(n_lat):
        for j in range(n_lon):
            a = i * n_lon + j
            b = i * n_lon + (j + 1) % n_lon
            c = (i + 1) * n_lon + (j + 1) % n_lon
            d = (i + 1) * n_lon + j
            if i == 0:
                faces.append((a, c, d))
            elif i == n_lat - 1:
                faces.append((a, b, d))
            else:
                faces.append((a, b, c, d))
    return np.array(verts), faces, np.array(polar)


def eyeball(center, R=0.0122, cornea=0.0012):
    v, f, th = uv_sphere(center, (R, R, R), 28, 16, 'x')
    c = np.array(center)
    d = v - c
    dome = np.exp(-(th / 0.55) ** 4) * cornea
    n = d / np.linalg.norm(d, axis=1, keepdims=True)
    v = v + n * dome[:, None]
    return v, G.fix_winding(v, f), th


def ear_mesh(side_sign):
    c = np.array([-0.010, side_sign * 0.079, 1.678])
    v, f, _ = uv_sphere(c, (0.010, 0.0065, 0.030), 20, 12, 'z')
    v = np.array(v)
    # ear tapers at the lobe, flares outward at the back rim, concha dent on the outer face
    rel = v - c
    t = (rel[:, 2] / 0.030)
    v[:, 1] += side_sign * 0.004 * np.clip(-rel[:, 0] / 0.010, 0, 1) * (1 - np.abs(t) ** 2)
    dent = np.exp(-(((rel[:, 0] + 0.001) / 0.006) ** 2 + ((rel[:, 2] - 0.004) / 0.010) ** 2))
    v[:, 1] -= side_sign * 0.0038 * dent * (np.sign(rel[:, 1]) == side_sign)
    v[:, 0] += 0.002 * t * t
    return v, G.fix_winding(v, f)


def rounded_box(size, center=(0, 0, 0), seg=5, round_=0.35):
    """Superellipsoid-ish rounded box (quad sphere mapped)."""
    n = seg
    verts, faces = [], []
    idx = {}
    def V(i, j, k):
        key = (i, j, k)
        if key not in idx:
            idx[key] = len(verts)
            verts.append((2.0 * i / n - 1, 2.0 * j / n - 1, 2.0 * k / n - 1))
        return idx[key]
    for a in range(n):
        for b in range(n):
            faces += [(V(n, a, b), V(n, a + 1, b), V(n, a + 1, b + 1), V(n, a, b + 1)), (V(0, a, b), V(0, a, b + 1), V(0, a + 1, b + 1), V(0, a + 1, b)),
                      (V(a, n, b), V(a, n, b + 1), V(a + 1, n, b + 1), V(a + 1, n, b)), (V(a, 0, b), V(a + 1, 0, b), V(a + 1, 0, b + 1), V(a, 0, b + 1)),
                      (V(a, b, n), V(a + 1, b, n), V(a + 1, b + 1, n), V(a, b + 1, n)), (V(a, b, 0), V(a, b + 1, 0), V(a + 1, b + 1, 0), V(a + 1, b, 0))]
    q = np.array(verts)
    sph = q / np.linalg.norm(q, axis=1, keepdims=True)
    m = q * (1 - round_) + sph * np.abs(q).max(axis=1, keepdims=True) * round_
    v = m * (np.array(size) / 2.0) + np.array(center)
    return v, G.fix_winding(v, faces)


def teeth_meshes(z_line=1.6235):
    """Upper and lower tooth rows on an arch behind the lips. Returns (verts, faces) for each row merged."""
    out = {}
    for row, sgn in (('upper', 1), ('lower', -1)):
        parts = []
        for m in range(-6, 7):
            phi = math.radians(m * 11.0)
            arch_c = np.array([0.055, 0.0])
            rx, ry = 0.0275, 0.031
            x = arch_c[0] + rx * math.cos(phi)
            y = ry * math.sin(phi)
            w_ = 0.0078 if abs(m) <= 1 else (0.0068 if abs(m) == 2 else 0.0060)
            h_ = 0.0115 if abs(m) <= 1 else 0.0100
            zc = z_line + sgn * (h_ / 2 + 0.0004)
            v, f = rounded_box((0.0034, w_, h_), (x, y, zc), seg=3, round_=0.45)
            # rotate about Z to follow the arch tangent
            ang = phi
            R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
            c = np.array([x, y])
            xy = (v[:, :2] - c) @ R.T + c
            v = np.column_stack([xy, v[:, 2]])
            parts.append((v, f))
        V, F, _ = G.merge(parts)
        out[row] = (V, F)
    return out


def tongue_mesh(z=1.6075, n=12):
    rings = []
    verts, faces = [], []
    xs = np.linspace(0.006, 0.074, 9)
    for k, x in enumerate(xs):
        t = k / (len(xs) - 1)
        wd = 0.0175 * (1 - 0.35 * t ** 2) * (1 if t < 0.92 else 0.7)
        ht = 0.0075 * (1 - 0.30 * t)
        ring = []
        for m in range(n):
            a = 2 * math.pi * m / n
            ring.append(len(verts))
            verts.append((x, wd * math.cos(a), z + 0.002 + ht * math.sin(a) * (1.0 if math.sin(a) > 0 else 0.55)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for m in range(n):
            faces.append((rings[k][m], rings[k][(m + 1) % n], rings[k + 1][(m + 1) % n], rings[k + 1][m]))
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        c = len(verts)
        verts.append(tuple(np.mean([verts[i] for i in ring], axis=0)))
        for m in range(n):
            faces.append((ring[(m + 1) % n], ring[m], c) if flip else (ring[m], ring[(m + 1) % n], c))
    v = np.array(verts)
    return v, G.fix_winding(v, faces)


if __name__ == '__main__':
    g = HeadGrid()
    print('verts', len(g.verts), 'faces', len(g.faces))

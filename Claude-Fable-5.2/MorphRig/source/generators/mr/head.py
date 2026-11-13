"""Head, face, neck, eyes, mouth interior - built as structured grids fitted to an implicit sculpt.

Stage A (this part): the implicit head shape and the base quad grid (columns around the head, rows from
crown to neck) that is projected onto it.
"""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, gauss, Pchip, TAU
from . import sdf
from . import skel
from .skel import J

NU = 64                  # columns around the head (even)
HALF = NU // 2
# column azimuths (deg) of the left half, index 0 = face centre, HALF = back centre
_FRONT = [0.0, 3.5, 7.0, 11.7, 16.4, 21.1, 25.8, 30.5, 35.2, 40.0]
_rest = HALF - (len(_FRONT) - 1)
_w = np.linspace(1.0, 1.55, _rest)
_w = _w / _w.sum() * (180.0 - _FRONT[-1])
COL_DEG = _FRONT + list(_FRONT[-1] + np.cumsum(_w))
COL_DEG[-1] = 180.0
assert len(COL_DEG) == HALF + 1

EYE_C0, EYE_C1 = 2, 9          # eye hole columns (left side)
MOUTH_C = 5                    # mouth hole spans columns -5..+5

# landmark profiles (rho = horizontal distance from the head axis, z) at front / side / back
AXIS_Y_HEAD = -0.006
AXIS_Y_NECK = 0.014
LM = [
    # name,          front,            side,             back,          rows to next
    ('crown',       (0.014, 1.7868), (0.014, 1.7868), (0.014, 1.7868), 4),
    ('cranium',     (0.066, 1.768),  (0.058, 1.764),  (0.072, 1.762),  4),
    ('hairline',    (0.090, 1.738),  (0.072, 1.732),  (0.091, 1.722),  6),
    ('brow',        (0.096, 1.6895), (0.075, 1.690),  (0.094, 1.680),  6),
    ('infraorb',    (0.094, 1.6565), (0.075, 1.655),  (0.090, 1.645),  6),
    ('nosebase',    (0.098, 1.6195), (0.071, 1.625),  (0.080, 1.615),  6),
    ('chincrease',  (0.094, 1.5870), (0.064, 1.600),  (0.066, 1.590),  3),
    ('menton',      (0.082, 1.5585), (0.055, 1.584),  (0.058, 1.570),  4),
    ('throat',      (0.036, 1.5500), (0.048, 1.565),  (0.052, 1.550),  2),
    ('neckhi',      (0.037, 1.5300), (0.047, 1.535),  (0.050, 1.530),  4),
    ('necklo',      (0.046, 1.4920), (0.052, 1.492),  (0.054, 1.492),  0),
]
ROW_OF = {}
_r = 0
for _name, _f, _s, _b, _n in LM:
    ROW_OF[_name] = _r
    _r += _n
NV = _r - LM[-1][4]
NV = ROW_OF['necklo']
EYE_R0, EYE_R1 = ROW_OF['brow'], ROW_OF['infraorb']
MOUTH_R0, MOUTH_R1 = ROW_OF['nosebase'], ROW_OF['chincrease']

EYE = J['eye_l'].copy()
EYE_RAD = skel.EYE_R


def build_head_sdf(with_ears=False):
    s = sdf.Shape(sym=True)
    E = sdf.sd_ellipsoid
    S = sdf.sd_sphere
    C = sdf.sd_capsule
    s.add(lambda p: E(p, (0, -0.0020, 1.7000), (0.0760, 0.0930, 0.0870)))                 # cranium
    s.add(lambda p: E(p, (0, 0.0140, 1.6520), (0.0655, 0.0700, 0.0560)), 0.030)           # skull base / mastoid
    s.add(lambda p: S(p, (0, -0.0500, 1.7150), 0.0510), 0.030)                             # forehead
    s.add(lambda p: E(p, (0, -0.0380, 1.6500), (0.0625, 0.0600, 0.0450)), 0.030)          # mid face
    s.add(lambda p: E(p, (0, -0.0400, 1.6050), (0.0410, 0.0550, 0.0440)), 0.030)          # lower face
    s.add(lambda p: S(p, (0.0470, -0.0585, 1.6760), 0.0165), 0.022)                        # lateral orbital rim
    s.add(lambda p: C(p, (0.0320, 0.0060, 1.6220), (0.0070, -0.0715, 1.5790), 0.0155, 0.0150), 0.030)  # jaw line
    s.add(lambda p: E(p, (0.0330, -0.0420, 1.6300), (0.0225, 0.0330, 0.0270)), 0.030)          # cheek fill
    s.add(lambda p: S(p, (0, -0.0805, 1.5790), 0.0185), 0.020)                             # chin
    s.add(lambda p: S(p, (0.0440, -0.0620, 1.6470), 0.0215), 0.028)                        # cheek bone
    s.add(lambda p: S(p, (0.0320, -0.0770, 1.6390), 0.0200), 0.030)                        # cheek apple
    s.add(lambda p: C(p, (0.0120, -0.0945, 1.6925), (0.0460, -0.0835, 1.6950), 0.0075), 0.024)  # brow ridge
    s.add(lambda p: E(p, (0, -0.0850, 1.6050), (0.0290, 0.0215, 0.0175)), 0.022)          # muzzle
    s.add(lambda p: C(p, (0, -0.0885, 1.6830), (0, -0.1105, 1.6400), 0.0058, 0.0078), 0.011)   # nose dorsum
    s.add(lambda p: S(p, (0, -0.1125, 1.6355), 0.0098), 0.008)                             # nose tip
    s.add(lambda p: S(p, (0.0102, -0.1010, 1.6305), 0.0068), 0.006)                        # ala
    s.add(lambda p: C(p, (0, -0.1060, 1.6270), (0, -0.0985, 1.6240), 0.0054), 0.006)       # columella
    s.add(lambda p: C(p, (0, 0.0270, 1.4300), (0, 0.0080, 1.6050), 0.0540, 0.0455), 0.030)  # neck
    if with_ears:
        s.add(lambda p: E(p, (0.0750, 0.0140, 1.6550), (0.0060, 0.0170, 0.0290)), 0.006)
    s.sub(lambda p: S(p, (0.0320, -0.0985, 1.6745), 0.0150), 0.012)                        # eye socket
    s.sub(lambda p: S(p, (0.0990, -0.0560, 1.7000), 0.0230), 0.035)                        # temple
    s.sub(lambda p: C(p, (0, -0.1095, 1.6205), (0, -0.1100, 1.6150), 0.0026), 0.008)       # philtrum
    s.sub(lambda p: C(p, (-0.010, -0.1030, 1.5862), (0.010, -0.1030, 1.5862), 0.0048), 0.010)  # chin crease
    s.sub(lambda p: S(p, (0.0065, -0.1045, 1.6240), 0.0034), 0.004)                        # nostril
    return s


def ray_project(shape, origins, targets, tmax=0.26, samples=120):
    """Outermost surface hit along rays origin -> through target."""
    o = np.asarray(origins, dtype=np.float64)
    d = np.asarray(targets, dtype=np.float64) - o
    d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-12)
    ts = np.linspace(0.0, tmax, samples)
    n = len(o)
    inside = np.zeros((n, samples), dtype=bool)
    for k, t in enumerate(ts):
        inside[:, k] = shape(o + d * t) < 0.0
    # last inside sample
    idx = samples - 1 - np.argmax(inside[:, ::-1], axis=1)
    idx = np.clip(idx, 0, samples - 2)
    lo = ts[idx]
    hi = ts[idx + 1]
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        f = shape(o + d * mid[:, None])
        ins = f < 0.0
        lo = np.where(ins, mid, lo)
        hi = np.where(ins, hi, mid)
    return o + d * (0.5 * (lo + hi))[:, None]


def _profile_tables():
    t = np.array([ROW_OF[l[0]] for l in LM], dtype=np.float64)
    out = []
    for k in (1, 2, 3):
        out.append(Pchip(t, np.array([l[k] for l in LM])))
    return out


def initial_grid():
    """(NV+1, NU, 3) initial guess from interpolated landmark profiles."""
    pf, ps, pb = _profile_tables()
    P = np.zeros((NV + 1, NU, 3))
    for i in range(NV + 1):
        f, s, b = pf(float(i)), ps(float(i)), pb(float(i))
        # axis shifts back from the skull to the neck
        zc = (f[1] + s[1] + b[1]) / 3.0
        cy = lerp(AXIS_Y_NECK, AXIS_Y_HEAD, float(smoothstep(1.555, 1.60, zc)))
        for j in range(NU):
            jj = j if j <= HALF else NU - j
            th = math.radians(COL_DEG[jj])
            sgn = 1.0 if j <= HALF else -1.0
            c, sn = math.cos(th), math.sin(th)
            wf = max(c, 0.0) ** 1.6
            wb = max(-c, 0.0) ** 1.6
            ws = abs(sn) ** 1.6
            tot = wf + wb + ws
            rho = (wf * f[0] + ws * s[0] + wb * b[0]) / tot
            z = (wf * f[1] + ws * s[1] + wb * b[1]) / tot
            P[i, j] = (sgn * rho * sn, cy - rho * c, z)
    return P


def relax_grid(P, shape, iters=4, lam=0.45, pin=None, lock_rows=(0,)):
    """Tangential Laplacian relaxation of a (rows, NU) periodic grid followed by re-projection."""
    rows = P.shape[0]
    pin = np.zeros(P.shape[:2], dtype=bool) if pin is None else pin
    for _ in range(iters):
        up = np.vstack([P[:1], P[:-1]])
        dn = np.vstack([P[1:], P[-1:]])
        lf = np.roll(P, 1, axis=1)
        rt = np.roll(P, -1, axis=1)
        avg = (up + dn + lf + rt) * 0.25
        new = P + (avg - P) * lam
        new[pin] = P[pin]
        for r in lock_rows:
            new[r] = P[r]
        new[-1] = P[-1]
        flat = shape.project(new.reshape(-1, 3), iters=4)
        Q = flat.reshape(P.shape)
        Q[pin] = P[pin]
        for r in lock_rows:
            Q[r] = P[r]
        Q[-1, :, 2] = P[-1, :, 2]
        # exact symmetry
        Q[:, 0, 0] = 0.0
        Q[:, HALF, 0] = 0.0
        for j in range(1, HALF):
            m = Q[:, j].copy()
            Q[:, NU - j] = m * np.array([-1.0, 1.0, 1.0])
        P = Q
    return P


def base_grid(shape=None, relax=3):
    """Initial landmark grid -> ray cast (face / skull / neck) or closest point (throat fillet) -> relax."""
    shape = shape or build_head_sdf()
    P = initial_grid()
    r_men, r_nhi = ROW_OF['menton'], ROW_OF['neckhi']
    O = np.zeros_like(P)
    for i in range(NV + 1):
        zc = P[i, :, 2].mean()
        if i <= r_men:
            cy = AXIS_Y_HEAD
            oz = min(max(zc, 1.605), 1.700)
        else:
            cy = AXIS_Y_NECK
            oz = zc
        O[i, :, 0] = 0.0
        O[i, :, 1] = cy
        O[i, :, 2] = oz
    Q = P.copy()
    ray_rows = [i for i in range(NV + 1) if i <= r_men or i >= r_nhi]
    idx = np.array(ray_rows)
    Q[idx] = ray_project(shape, O[idx].reshape(-1, 3), P[idx].reshape(-1, 3)).reshape(len(idx), NU, 3)
    mid = np.array([i for i in range(NV + 1) if i not in ray_rows])
    if len(mid):
        Q[mid] = shape.project(P[mid].reshape(-1, 3), iters=16).reshape(len(mid), NU, 3)
    Q[:, 0, 0] = 0.0
    Q[:, HALF, 0] = 0.0
    Q = relax_grid(Q, shape, iters=relax)
    return Q, shape


# =====================================================================================================
# Stage B: eyes, lids, lips, mouth interior, weights
# =====================================================================================================
from .meshkit import MeshData
from .util import resample_closed, bump

NE = 2 * ((EYE_C1 - EYE_C0) + (EYE_R1 - EYE_R0))     # 26 vertices per eye ring
NM = 2 * (2 * MOUTH_C + (MOUTH_R1 - MOUTH_R0))       # 32 vertices per mouth ring
assert NE == 26 and NM == 32, (NE, NM)

SKIN = 'M_Skin'
WET = 'M_EyesMouth'
HAIRMAT = 'M_Hair'

# ---- eye opening (left eye; right is mirrored)
EYE_XC, EYE_HW = 0.03200, 0.01550
EYE_Z_IN, EYE_Z_OUT = EYE[2] - 0.0010, EYE[2] + 0.0017
LID_H_UP, LID_H_LO = 0.0063, 0.0060
ORBIT = dict(xo=0.0330, zo=1.6732, nasal=0.0210, temporal=0.0225, up=0.0172, down=0.0165, n=2.5)

# ---- mouth
MOUTH_W = 0.0238
MOUTH_Z = 1.6015
MOUTH_Y = -0.1058
ARCH_R = 0.0315
MOUTH_OVAL = dict(zc=1.6020, w=0.0335, up=0.0172, down=0.0148, n=2.6)


def _spow(c, n):
    return np.sign(c) * np.abs(c) ** (2.0 / n)


def eye_hole_loop(side='l'):
    """Grid (row, col) sequence of the eye hole boundary, index 0 = inner canthus, going over the upper lid."""
    R0, R1, C0, C1 = EYE_R0, EYE_R1, EYE_C0, EYE_C1
    mid = (R0 + R1) // 2
    seq = [(mid, C0)] + [(r, C0) for r in range(mid - 1, R0, -1)] + [(R0, C0)]
    seq += [(R0, c) for c in range(C0 + 1, C1)] + [(R0, C1)]
    seq += [(r, C1) for r in range(R0 + 1, R1)] + [(R1, C1)]
    seq += [(R1, c) for c in range(C1 - 1, C0, -1)] + [(R1, C0)]
    seq += [(r, C0) for r in range(R1 - 1, mid, -1)]
    assert len(seq) == NE, len(seq)
    if side == 'r':
        seq = [(r, (NU - c) % NU) for (r, c) in seq]
    return seq


def mouth_hole_loop():
    """Index 0 = left mouth corner (+X), going over the upper lip to the right corner (index NM/2)."""
    R0, R1, C = MOUTH_R0, MOUTH_R1, MOUTH_C
    mid = (R0 + R1) // 2
    seq = [(mid, C)] + [(r, C) for r in range(mid - 1, R0, -1)] + [(R0, C)]
    seq += [(R0, c) for c in range(C - 1, -C, -1)] + [(R0, -C)]
    seq += [(r, -C) for r in range(R0 + 1, R1)] + [(R1, -C)]
    seq += [(R1, c) for c in range(-C + 1, C)] + [(R1, C)]
    seq += [(r, C) for r in range(R1 - 1, mid, -1)]
    assert len(seq) == NM, len(seq)
    return [(r, c % NU) for (r, c) in seq]


def head_surface_y(shape, x, z):
    """Front skin depth (y) of the implicit head at front-plane positions."""
    x = np.atleast_1d(np.asarray(x, dtype=np.float64))
    z = np.atleast_1d(np.asarray(z, dtype=np.float64))
    o = np.stack([x, np.full_like(x, 0.03), z], axis=1)
    t = o + np.array([0.0, -1.0, 0.0])
    return ray_project(shape, o, t, tmax=0.20, samples=110)[:, 1]


def lid_surface_y(x, z, extra=0.0):
    """Depth of the eyelid shell: eyeball sphere (+extra) with a tangent continuation beyond the globe."""
    RL = EYE_RAD + extra
    d = np.sqrt((np.asarray(x) - EYE[0]) ** 2 + (np.asarray(z) - EYE[2]) ** 2)
    d0 = 0.78 * RL
    dep0 = math.sqrt(RL * RL - d0 * d0)
    slope = -d0 / dep0
    dep = np.where(d <= d0, np.sqrt(np.maximum(RL * RL - np.minimum(d, d0) ** 2, 1e-12)), dep0 + slope * 0.75 * (d - d0))
    return EYE[1] - dep


def eye_margin_xz(k):
    """Front-plane lid margin point for ring index k (left eye)."""
    h = NE // 2
    if k == 0:
        return EYE_XC - EYE_HW, EYE_Z_IN
    if k == h:
        return EYE_XC + EYE_HW, EYE_Z_OUT
    if k < h:
        u = -1.0 + 2.0 * k / h
        zl = lerp(EYE_Z_IN, EYE_Z_OUT, (u + 1) / 2)
        return EYE_XC + u * EYE_HW, zl + LID_H_UP * (1 - u * u) ** 0.72 * (1 - 0.22 * u)
    u = 1.0 - 2.0 * (k - h) / h
    zl = lerp(EYE_Z_IN, EYE_Z_OUT, (u + 1) / 2)
    return EYE_XC + u * EYE_HW, zl - LID_H_LO * (1 - u * u) ** 0.80 * (1 + 0.20 * u)


def eye_orbit_xz(k):
    a = TAU * k / NE
    ca, sa = math.cos(a), math.sin(a)
    o = ORBIT
    x = o['xo'] - float(_spow(ca, o['n'])) * (o['nasal'] if ca > 0 else o['temporal'])
    z = o['zo'] + float(_spow(sa, o['n'])) * (o['up'] if sa > 0 else o['down'])
    return x, z


def eye_rings(shape):
    """List of rings (outer -> inner) of (NE,3) arrays for the left eye, ring 0 being the orbit (hole boundary)."""
    h = NE // 2
    orb = np.array([eye_orbit_xz(k) for k in range(NE)])
    mar = np.array([eye_margin_xz(k) for k in range(NE)])
    rings = []
    # orbit ring on the head surface
    y0 = head_surface_y(shape, orb[:, 0], orb[:, 1])
    rings.append(np.stack([orb[:, 0], y0, orb[:, 1]], axis=1))
    for f, g, extra in ((0.40, 0.62, 0.0026), (0.74, 1.0, 0.0024)):
        xz = lerp(orb, mar, f)
        yh = head_surface_y(shape, xz[:, 0], xz[:, 1])
        yl = lid_surface_y(xz[:, 0], xz[:, 1], extra)
        y = lerp(yh, yl, g)
        if g < 1.0:
            # soft crease above the upper lid, slight tear trough below
            for k in range(NE):
                s = math.sin(math.pi * (k % h) / h) if k not in (0, h) else 0.0
                y[k] += (0.0013 if k < h else 0.0) * s
        rings.append(np.stack([xz[:, 0], y, xz[:, 1]], axis=1))
    # margin outer edge
    rings.append(np.stack([mar[:, 0], lid_surface_y(mar[:, 0], mar[:, 1], 0.0017), mar[:, 1]], axis=1))
    # inner edge and seal: shrink towards the opening axis
    for shift, extra in ((0.0007, 0.0004), (0.0026, -0.0014)):
        xz = mar.copy()
        for k in range(NE):
            if k in (0, h):
                dx = 1.0 if k == 0 else -1.0
                xz[k, 0] += dx * shift * 1.2
                continue
            u = (xz[k, 0] - EYE_XC) / EYE_HW
            zl = lerp(EYE_Z_IN, EYE_Z_OUT, (u + 1) / 2)
            tgt = np.array([EYE_XC + 0.6 * u * EYE_HW, zl])
            d = tgt - xz[k]
            n = np.linalg.norm(d)
            if n > 1e-9:
                xz[k] += d / n * min(shift, n * 0.8)
        rings.append(np.stack([xz[:, 0], lid_surface_y(xz[:, 0], xz[:, 1], extra), xz[:, 1]], axis=1))
    return rings


def lid_weight(k, ring_index):
    """(upper, lower) eyelid bone weights for ring index k; ring_index 0 = orbit ... 5 = seal."""
    h = NE // 2
    if k in (0, h):
        return 0.0, 0.0
    rf = [0.0, 0.30, 0.82, 1.0, 1.0, 1.0][ring_index]
    s = math.sin(math.pi * (k % h) / h) ** 0.75
    if k < h:
        return rf * s, 0.0
    return 0.0, rf * s


# ---------------------------------------------------------------------------------- mouth curves
def _lipw(a):
    return (1.0 - min(a, 1.0) ** 2.6) ** 0.9


def mouth_s(k):
    return math.cos(math.pi * k / (NM // 2))        # k=0 -> +1 (left corner), NM/2 -> -1


def arch(x):
    return ARCH_R - math.sqrt(max(ARCH_R ** 2 - x * x, 1e-12))


def lip_curves(s):
    a = abs(s)
    x = MOUTH_W * s
    z_st = MOUTH_Z + 0.0005 * (1 - math.exp(-(a / 0.30) ** 2)) - 0.0002
    bow = 1 - 0.13 * math.exp(-(a / 0.22) ** 2) + 0.05 * math.exp(-((a - 0.36) / 0.16) ** 2)
    z_uv = z_st + 0.0086 * _lipw(a) * bow
    z_lv = z_st - 0.0100 * (1 - a ** 2.2) ** 0.75
    return dict(x=x, a=a, z_st=z_st, z_uv=z_uv, z_lv=z_lv, w=_lipw(a))


def mouth_oval_xz(k):
    a = TAU * k / NM
    o = MOUTH_OVAL
    ca, sa = math.cos(a), math.sin(a)
    return o['w'] * float(_spow(ca, o['n'])), o['zc'] + float(_spow(sa, o['n'])) * (o['up'] if sa > 0 else o['down'])


def mouth_rings(shape):
    """Rings from the hole boundary inwards: [m6 skin, m5 skin mid, m4 border, m3 peak, m2 contact, m1 inner, m0 gum].
    Lip depths are offsets from the implicit skin surface that fade towards the mouth corners."""
    h = NM // 2
    oval = np.array([mouth_oval_xz(k) for k in range(NM)])
    y6 = head_surface_y(shape, oval[:, 0], oval[:, 1])
    m6 = np.stack([oval[:, 0], y6, oval[:, 1]], axis=1)
    m4 = np.zeros((NM, 3)); m3 = np.zeros((NM, 3)); m2 = np.zeros((NM, 3)); m1 = np.zeros((NM, 3)); m0 = np.zeros((NM, 3))
    cv = [lip_curves(mouth_s(k)) for k in range(NM)]
    xs = np.array([c['x'] for c in cv])
    ysk_st = head_surface_y(shape, xs, np.array([c['z_st'] for c in cv]))
    for k in range(NM):
        c = cv[k]
        w = c['w']
        upper = (0 < k < h)
        corner = k in (0, h)
        sg = 1.0 if mouth_s(k) >= 0 else -1.0
        yst = ysk_st[k] + 0.0026 * w + 0.0010 * (1 - w)          # contact line sits behind the lip bodies
        if corner:
            m2[k] = (c['x'], yst, c['z_st'])
            m3[k] = (c['x'] + sg * 0.0012, yst - 0.0006, c['z_st'])
            m4[k] = (c['x'] + sg * 0.0026, yst - 0.0010, c['z_st'])
            m1[k] = (c['x'] - sg * 0.0014, yst + 0.0032, c['z_st'])
            m0[k] = (c['x'] - sg * 0.0026, yst + 0.0078, c['z_st'])
            continue
        if upper:
            zb = c['z_uv']
            ypk = ysk_st[k] - 0.0034 * w
            zin, zg = c['z_st'] + 0.0030 * w, c['z_st'] + 0.0085 * w + 0.0010
        else:
            zb = c['z_lv']
            ypk = ysk_st[k] - 0.0026 * w
            zin, zg = c['z_st'] - 0.0030 * w, c['z_st'] - 0.0085 * w - 0.0010
        ysk = float(head_surface_y(shape, [c['x']], [zb])[0])
        yb = ysk - 0.0007 * w
        m4[k] = (c['x'], yb, zb)
        m3[k] = (c['x'], ypk, lerp(zb, c['z_st'], 0.52))
        m2[k] = (c['x'], yst, c['z_st'])
        m1[k] = (c['x'] * 0.97, yst + 0.0040, zin)
        m0[k] = (c['x'] * 0.95, yst + 0.0086, zg)
    xz5 = (m6[:, [0, 2]] + m4[:, [0, 2]]) * 0.5
    y5 = head_surface_y(shape, xz5[:, 0], xz5[:, 1])
    m5 = np.stack([xz5[:, 0], y5, xz5[:, 1]], axis=1)
    return [m6, m5, m4, m3, m2, m1, m0]


def lip_jaw_weight(k):
    h = NM // 2
    if k in (0, h):
        return 0.5
    d = min(k % h, h - (k % h))
    if k < h:
        return 0.5 * (1.0 - float(smoothstep(0.0, 3.5, d)))
    return 1.0 - 0.5 * (1.0 - float(smoothstep(0.0, 4.5, d)))


BAG = [  # (y, half width, half height up, half height down)
    (-0.0890, 0.0238, 0.0125, 0.0125), (-0.0730, 0.0262, 0.0162, 0.0170), (-0.0540, 0.0252, 0.0172, 0.0180),
    (-0.0380, 0.0185, 0.0125, 0.0130)]


def bag_ring(i):
    y, wx, zu, zd = BAG[i]
    out = np.zeros((NM, 3))
    for k in range(NM):
        a = TAU * k / NM
        ca, sa = math.cos(a), math.sin(a)
        out[k] = (wx * float(_spow(ca, 2.3)), y, MOUTH_Z - 0.001 + float(_spow(sa, 2.3)) * (zu if sa > 0 else zd))
    return out


# ---------------------------------------------------------------------------------- weights
def base_weights(p):
    """head / neck / spine distribution for skin points (no jaw, no lids)."""
    x, y, z = p
    t = (z - (1.572 + 0.42 * y)) / 0.034
    w_head = float(smoothstep(-1.0, 1.0, t))
    w_sp = 1.0 - float(smoothstep(1.482, 1.528, z))
    w = {'head': w_head, 'neck_01': (1 - w_head) * (1 - w_sp), 'spine_03': (1 - w_head) * w_sp}
    return {k: v for k, v in w.items() if v > 1e-5}


def jaw_mask(p):
    x, y, z = p
    z_line = MOUTH_Z + (y + 0.092) * 0.255
    a = float(smoothstep(-0.004, 0.013, z_line - z))
    b = 1.0 - float(smoothstep(-0.004, 0.022, y))
    c = 1.0
    if z < 1.566:
        c = 1.0 - float(smoothstep(-0.078, -0.034, y))
    return a * b * c


def with_jaw(w, wj):
    out = {k: v * (1 - wj) for k, v in w.items()}
    if wj > 1e-5:
        out['jaw'] = out.get('jaw', 0.0) + wj
    return out


def build_head(shape=None):
    """Returns dict of MeshData: skin (head+neck), eyes, mouth (bag/teeth/tongue), lashes; plus info."""
    shape = shape or build_head_sdf()
    P, shape = base_grid(shape, relax=2)
    # ---- retarget hole boundaries to smooth ovals, relax the neighbourhood
    pin = np.zeros(P.shape[:2], dtype=bool)
    e_rings = eye_rings(shape)
    m_rings = mouth_rings(shape)
    for k, (r, c) in enumerate(eye_hole_loop('l')):
        P[r, c] = e_rings[0][k]
        pin[r, c] = True
    for k, (r, c) in enumerate(eye_hole_loop('r')):
        P[r, c] = e_rings[0][k] * np.array([-1.0, 1.0, 1.0])
        pin[r, c] = True
    for k, (r, c) in enumerate(mouth_hole_loop()):
        P[r, c] = m_rings[0][k]
        pin[r, c] = True
    # hole interiors: park them on the boundary average so they do not disturb relaxation
    for (R0, R1, C0, C1) in ((EYE_R0, EYE_R1, EYE_C0, EYE_C1), (EYE_R0, EYE_R1, NU - EYE_C1, NU - EYE_C0)):
        for r in range(R0 + 1, R1):
            for c in range(C0 + 1, C1):
                pin[r, c] = True
    for r in range(MOUTH_R0 + 1, MOUTH_R1):
        for c in list(range(0, MOUTH_C)) + list(range(NU - MOUTH_C + 1, NU)):
            pin[r, c] = True
    P = relax_grid(P, shape, iters=7, lam=0.5, pin=pin)

    md = MeshData('Head')
    gid = -np.ones(P.shape[:2], dtype=np.int64)

    def in_hole_interior(r, c):
        if EYE_R0 < r < EYE_R1 and (EYE_C0 < c < EYE_C1 or NU - EYE_C1 < c < NU - EYE_C0):
            return True
        if MOUTH_R0 < r < MOUTH_R1 and (c < MOUTH_C or c > NU - MOUTH_C):
            return True
        return False

    for r in range(NV + 1):
        for c in range(NU):
            if in_hole_interior(r, c):
                continue
            p = P[r, c]
            gid[r, c] = md.vert(p, with_jaw(base_weights(p), jaw_mask(p)), tag='headgrid')

    def cell_in_hole(r, c):
        if EYE_R0 <= r < EYE_R1 and (EYE_C0 <= c < EYE_C1 or NU - EYE_C1 <= c < NU - EYE_C0):
            return True
        if MOUTH_R0 <= r < MOUTH_R1 and (c < MOUTH_C or c >= NU - MOUTH_C):
            return True
        return False

    for r in range(NV):
        for c in range(NU):
            if cell_in_hole(r, c):
                continue
            c2 = (c + 1) % NU
            tag = 'scalp' if r < ROW_OF['hairline'] else ('neck' if r >= ROW_OF['menton'] + 2 else 'face')
            md.face([gid[r, c], gid[r + 1, c], gid[r + 1, c2], gid[r, c2]], SKIN, tag)
    md.grid_cap([gid[0, c] for c in range(NU)], SKIN, 'scalp')

    info = dict(gid=gid, P=P, shape=shape)

    # ---- eyes
    lash = MeshData('Lashes')
    for side in ('l', 'r'):
        sx = 1.0 if side == 'l' else -1.0
        loop = [gid[r, c] for (r, c) in eye_hole_loop(side)]
        rings_idx = [loop]
        for ri in range(1, len(e_rings)):
            pts = e_rings[ri] * np.array([sx, 1.0, 1.0])
            ws = []
            for k in range(NE):
                up, lo = lid_weight(k, ri)
                w = {'head': 1.0 - up - lo}
                if up > 0:
                    w['lid_upper_' + side] = up
                if lo > 0:
                    w['lid_lower_' + side] = lo
                ws.append(w)
            rings_idx.append(md.ring(pts, ws, tag='eyering%d_%s' % (ri, side)))
        for a, b in zip(rings_idx[:-1], rings_idx[1:]):
            md.strip(a, b, SKIN, 'eyelid_' + side, closed=True, flip=(side == 'l'))
        info['eye_rings_' + side] = rings_idx
        # lashes: tapered strip along the upper outer margin (ring index 3)
        h = NE // 2
        base, tip, wl = [], [], []
        for k in range(1, h):
            p = e_rings[3][k].copy()
            u = -1.0 + 2.0 * k / h
            length = 0.0034 * (0.45 + 0.55 * math.sin(math.pi * k / h)) * (1.0 + 0.45 * max(u, 0.0))
            d = norm(V(0.28 * u + 0.10, -0.80, 0.52))
            q = p + d * length
            p2 = p + V(0, -0.0002, 0.0002)
            base.append(p2 * np.array([sx, 1, 1]))
            tip.append(q * np.array([sx, 1, 1]))
            up, lo = lid_weight(k, 3)
            wl.append({'head': 1.0 - up, 'lid_upper_' + side: up})
        ib = lash.ring(base, wl, tag='lash')
        it = lash.ring(tip, wl, tag='lash')
        lash.strip(ib, it, HAIRMAT, 'lash', closed=False, flip=(side == 'r'))
        # underside so the lash is visible from below without two-sided materials
        ib2 = lash.ring([p + np.array([0, 0.00025, -0.00035]) for p in base], wl, tag='lash')
        lash.strip(it, ib2, HAIRMAT, 'lash', closed=False, flip=(side == 'r'))

    # ---- mouth
    loop = [gid[r, c] for (r, c) in mouth_hole_loop()]
    h = NM // 2
    # hole boundary jaw weights follow the lips at the lower corners
    mrings = [loop]
    for ri in range(1, len(m_rings)):
        ws = []
        for k in range(NM):
            p = m_rings[ri][k]
            ws.append(with_jaw(base_weights(p), lip_jaw_weight(k)))
        mrings.append(md.ring(m_rings[ri], ws, tag='mouthring%d' % ri))
    for i, (a, b) in enumerate(zip(mrings[:-1], mrings[1:])):
        md.strip(a, b, SKIN, 'lips' if i >= 1 else 'lipskin', closed=True, flip=False)
    info['mouth_rings'] = mrings
    # blend the hole boundary weights towards the lip weights (lower boundary must open with the jaw)
    for k, vi in enumerate(loop):
        p = np.array(md.v[vi])
        wj_grid = jaw_mask(p)
        wj = max(wj_grid, lip_jaw_weight(k)) if k > h else min(max(wj_grid, 0.0), lip_jaw_weight(k) + 0.25)
        if k in (0, h):
            wj = 0.5
        md.w[vi] = with_jaw(base_weights(p), wj)

    mouth = MeshData('MouthInterior')
    # mouth bag (continues from the gum ring, separate material)
    prev = mrings[-1]
    bag_rings = []
    for i in range(len(BAG)):
        pts = bag_ring(i)
        ws = [with_jaw({'head': 1.0}, lip_jaw_weight(k)) for k in range(NM)]
        cur = md.ring(pts, ws, tag='bag')
        md.strip(prev, cur, WET, 'mouthbag', closed=True, flip=False)
        bag_rings.append(cur)
        prev = cur
    md.grid_cap(prev, WET, 'mouthbag', flip=True)
    info['bag_rings'] = bag_rings

    # ---- weights smoothing over the skin (keeps lids/lips crisp by locking ring tags)
    lock = tuple('eyering%d_%s' % (i, s) for i in range(1, 6) for s in ('l', 'r'))
    md.smooth_weights(iters=2, lam=0.45, lock_tags=lock)

    # ---- taper of the lower face: slimmer cheeks and jaw line (the mouth area and the back of the skull stay)
    for i, p in enumerate(md.v):
        ax = abs(p[0])
        k = 0.115 * float(smoothstep(1.650, 1.598, p[2])) * (1.0 - 0.55 * float(smoothstep(1.570, 1.535, p[2])))
        w = float(smoothstep(0.020, 0.048, ax)) * float(smoothstep(0.034, 0.004, p[1]))
        if k * w > 1e-5:
            p[0] *= 1.0 - k * w
            p[1] += 0.0035 * k * w / 0.115 * float(smoothstep(-0.02, -0.09, p[1]))      # cheeks a little flatter in front

    # ---- seams: back centre line, neck/scalp are part of the same island
    md.seam_path([gid[r, HALF] for r in range(0, NV + 1)])
    # ... continued over the crown towards the forehead (hidden under the hair) so the face is not squeezed
    P0 = np.array([md.v[gid[r, 0]] for r in range(0, NV + 1)])
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P0, axis=0), axis=1))])
    r_stop = int(np.searchsorted(arc, 0.080))
    md.seam_path([gid[r, 0] for r in range(0, max(r_stop, 1) + 1)])
    md.seam_path([gid[0, c] for c in range(NU)], closed=True)          # the small crown cap becomes its own island
    md.seam_path(mrings[-1], closed=True)

    parts = dict(skin=md, lashes=lash)
    parts['eyes'] = build_eyeballs()
    parts['teeth'] = build_teeth()
    parts['tongue'] = build_tongue()
    return parts, info


# ---------------------------------------------------------------------------------- interior parts
def build_eyeballs(seg=20, rings=12):
    md = MeshData('Eyes')
    for side in ('l', 'r'):
        sx = 1.0 if side == 'l' else -1.0
        c = EYE * np.array([sx, 1.0, 1.0])
        w = {'eye_' + side: 1.0}
        rr = []
        for i in range(1, rings):
            th = math.pi * i / rings          # 0 = front pole (-Y)
            # subtle corneal bulge on the front cap
            bulge = 1.0 + 0.035 * math.exp(-(th / 0.42) ** 2)
            pts = []
            for j in range(seg):
                ph = TAU * j / seg
                d = V(math.sin(th) * math.cos(ph), -math.cos(th), math.sin(th) * math.sin(ph))
                pts.append(c + d * EYE_RAD * bulge)
            rr.append(md.ring(pts, w, tag='eye_' + side))
        md.fan_cap(rr[0], c + V(0, -EYE_RAD * 1.035, 0), w, WET, 'eye_' + side, flip=False)
        md.loft(rr, WET, 'eye_' + side, closed=True, flip=True)
        md.fan_cap(rr[-1], c + V(0, EYE_RAD, 0), w, WET, 'eye_' + side, flip=True)
    return md


def _arch_pt(t, front_y, width, depth):
    """Dental arch (parabola) in the horizontal plane; t in [-1, 1]."""
    return width * t, front_y + depth * (abs(t) ** 2.0)


def build_teeth(n=22):
    md = MeshData('Teeth')
    specs = [  # name, bone, front y, half width, depth, z gum, z edge, thickness
        ('upper', 'head', -0.1008, 0.0215, 0.0300, MOUTH_Z + 0.0105, MOUTH_Z - 0.0013, 0.0052),
        ('lower', 'jaw', -0.0968, 0.0200, 0.0285, MOUTH_Z - 0.0098, MOUTH_Z + 0.0001, 0.0048),
    ]
    for name, bone, fy, wd, dp, zg, ze, th in specs:
        w = {bone: 1.0}
        secs = []
        for i in range(n + 1):
            t = -1.0 + 2.0 * i / n
            x, y = _arch_pt(t, fy, wd, dp)
            # arch tangent / normal
            dx, dy = wd, dp * 2.0 * t
            ln = math.hypot(dx, dy)
            nx, ny = -dy / ln, dx / ln           # inward normal (towards the mouth centre/back)
            if ny < 0:
                nx, ny = -nx, -ny
            thick = th * (1.0 + 0.9 * abs(t) ** 2)
            # tooth edge scallop
            sc = 0.0006 * abs(math.sin(math.pi * i * 0.5))
            zedge = ze + (sc if name == 'upper' else -sc)
            gum_out = 0.0012 if name == 'upper' else -0.0004      # the lower gum must stay behind the skin below the lip
            o = np.array([x, y, 0.0])
            nrm = np.array([nx, ny, 0.0])
            sec = [o - nrm * gum_out + V(0, 0, zg), o + V(0, 0, lerp(zg, zedge, 0.45)), o + V(0, 0, zedge),
                   o + nrm * thick + V(0, 0, zedge), o + nrm * thick + V(0, 0, lerp(zg, zedge, 0.45)),
                   o + nrm * (thick + gum_out) + V(0, 0, zg)]
            secs.append(md.ring(sec, w, tag='teeth_' + name))
        for a, b in zip(secs[:-1], secs[1:]):
            md.strip(a, b, WET, 'teeth_' + name, closed=True, flip=(name == 'upper'))
        md.grid_cap(secs[0], WET, 'teeth_' + name, flip=(name != 'upper'))
        md.grid_cap(secs[-1], WET, 'teeth_' + name, flip=(name == 'upper'))
    return md


def build_tongue(nr=9, ns=10):
    md = MeshData('Tongue')
    a, b, c = J['tongue_01'], J['tongue_02'], J['tongue_end']
    rings = []
    for i in range(nr):
        t = i / (nr - 1.0)
        cen = lerp(a, c, t) + V(0, 0, 0.0012 * math.sin(math.pi * t))
        cen = cen + V(0, 0.010 * (1 - t) ** 2, -0.004 * (1 - t) ** 2)   # root dives back/down
        hw = lerp(0.0165, 0.0105, t ** 1.2) * (1.0 - 0.55 * t ** 6)
        ht = lerp(0.0062, 0.0038, t) * (1.0 - 0.5 * t ** 6)
        w2 = float(smoothstep(0.30, 0.80, t))
        w = {'tongue_01': 1 - w2, 'tongue_02': w2}
        pts = []
        for j in range(ns):
            ang = TAU * j / ns
            groove = -0.0012 * math.exp(-(math.cos(ang) / 0.35) ** 2) * (1 if math.sin(ang) > 0 else 0) * (1 - t)
            pts.append(cen + V(hw * math.cos(ang), 0, ht * math.sin(ang) + groove))
        rings.append(md.ring(pts, w, tag='tongue'))
    md.loft(rings, WET, 'tongue', closed=True, flip=True)
    md.fan_cap(rings[0], md.pos(rings[0]).mean(axis=0) + V(0, 0.004, 0), {'tongue_01': 1.0}, WET, 'tongue', flip=True)
    md.fan_cap(rings[-1], c + V(0, -0.0035, 0), {'tongue_02': 1.0}, WET, 'tongue', flip=False)
    return md

"""Stylised slicked-back undercut built from sculpted, overlapping ribbons.

Design space: 'unwrapped' scalp coordinates (u, v) = azimuthal-equidistant map around the crown
(u towards the character's left, v towards the back, length = arc length from the crown in metres).
The long top is combed back from the front hairline in two staggered layers with a lifted front;
sides and back below the ribbons are an undercut painted into the skin texture. A thin under-cap hides
the scalp between ribbons.
"""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, TAU
from .meshkit import MeshData
from . import head as headmod

HAIRMAT = 'M_Hair'
CENTER = V(0, -0.004, 1.700)
R0 = 0.088


class Scalp:
    def __init__(self, shape):
        self.shape = shape

    def points(self, uv):
        uv = np.atleast_2d(np.asarray(uv, dtype=np.float64))
        r = np.linalg.norm(uv, axis=1)
        psi = r / R0
        az = np.arctan2(uv[:, 1], uv[:, 0])
        d = np.stack([np.sin(psi) * np.cos(az), np.sin(psi) * np.sin(az), np.cos(psi)], axis=1)
        o = np.tile(CENTER, (len(uv), 1))
        return headmod.ray_project(self.shape, o, o + d, tmax=0.16, samples=70)

    def normals(self, pts):
        return self.shape.normal(pts)


def pompadour(d, extra=0.0, front=1.0):
    """Common lift profile (metres above the scalp) versus distance d behind the root: lifted front, flat crown."""
    return (0.0035 + extra + front * 0.019 * math.exp(-((d - 0.030) / 0.030) ** 2)
            + 0.0065 * math.exp(-((d - 0.095) / 0.060) ** 2))


def ribbon(md, scalp, path_uv, width, thick, extra=0.0, front=1.0, nlen=13, tag='hair', tip_drop=1.0):
    """One flat, crested hair lock along a polyline given in unwrapped scalp coordinates."""
    path_uv = np.asarray(path_uv, dtype=np.float64)
    md._locks = getattr(md, '_locks', 0) + 1
    lock = (md._locks * 0.6180339887) % 1.0
    seg = np.linalg.norm(np.diff(path_uv, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    ss = np.linspace(0, total, nlen + 1)
    uv = np.stack([np.interp(ss, cum, path_uv[:, 0]), np.interp(ss, cum, path_uv[:, 1])], axis=1)
    for _ in range(2):
        uv[1:-1] = 0.25 * uv[:-2] + 0.5 * uv[1:-1] + 0.25 * uv[2:]
    base = scalp.points(uv)
    nrm = scalp.normals(base)
    w = {'head': 1.0}
    cen = []
    for i in range(nlen + 1):
        s = i / float(nlen)
        h = pompadour(ss[i], extra, front)
        h *= float(smoothstep(-0.02, 0.10, s))                       # roots emerge from the hairline
        h = lerp(h, 0.0030, float(smoothstep(0.62, 1.0, s)) * tip_drop)   # tips settle onto the head
        cen.append(base[i] + nrm[i] * h)
    cen = np.array(cen)
    prof = [(-1.0, 0.0), (-0.55, 0.62), (0.0, 1.0), (0.55, 0.62), (1.0, 0.0), (0.5, -0.22), (0.0, -0.30), (-0.5, -0.22)]
    rings = []
    for i in range(nlen + 1):
        s = i / float(nlen)
        a = cen[max(i - 1, 0)]
        b = cen[min(i + 1, nlen)]
        T = norm(b - a)
        N = nrm[i]
        L = norm(np.cross(N, T))
        Vv = np.cross(T, L)
        wd = width * (0.70 + 0.30 * float(smoothstep(0.0, 0.2, s))) * (1.0 - float(smoothstep(0.55, 1.0, s)) ** 1.6)
        th = thick * (0.6 + 0.4 * float(smoothstep(0.0, 0.2, s))) * (1.0 - float(smoothstep(0.60, 1.0, s)) ** 1.4)
        if i == nlen:
            vi = md.vert(cen[i], w, tag)
            _strand(md, vi, s, 0.0, 0.0, lock)
            rings.append([vi] * len(prof))
            continue
        ring = []
        for k, (cu, sv) in enumerate(prof):
            vi = md.vert(cen[i] + L * (cu * wd * 0.5) + Vv * (sv * th), w, tag)
            ang = TAU * k / len(prof)
            _strand(md, vi, s, math.cos(ang), math.sin(ang), lock)
            ring.append(vi)
        rings.append(ring)
    c0 = md.fan_cap(rings[0], cen[0] - nrm[0] * 0.004, w, HAIRMAT, tag, flip=False)
    _strand(md, c0, 0.0, 0.0, 0.0, lock)
    for a, b in zip(rings[:-1], rings[1:]):
        md.strip(a, b, HAIRMAT, tag, closed=True, flip=True)
    return rings


def _strand(md, vi, s, ca, sa, lock):
    """Per-vertex strand coordinates for the hair texture: s along the lock, (cos, sin) around it, lock id."""
    md.vcol.setdefault('strand_s', {})[vi] = float(s)
    md.vcol.setdefault('strand_c', {})[vi] = float(ca)
    md.vcol.setdefault('strand_n', {})[vi] = float(sa)
    md.vcol.setdefault('strand_id', {})[vi] = float(lock)


def hairline_v(u):
    """Front hairline (v, negative = forward) as a function of u: slightly rounded with soft temple recession."""
    a = abs(u)
    return -0.098 + 0.020 * (a / 0.075) ** 2.0 + 0.004 * math.exp(-(a / 0.012) ** 2)


def build_hair(shape):
    md = MeshData('Hair')
    scalp = Scalp(shape)
    w = {'head': 1.0}
    # ---------------- under-cap: thin shell from the crown to the undercut line
    nr, nu = 8, 48
    uv, meta = [], []
    for i in range(nr + 1):
        f = i / float(nr)
        for j in range(nu):
            a = TAU * j / nu
            ca, sa = math.cos(a), math.sin(a)
            # undercut line: front follows the hairline, sides ~8 cm from the crown, back a little lower
            r_front = 0.094
            r_side = 0.082
            r_back = 0.096
            rr = r_side + (r_front - r_side) * max(-sa, 0.0) ** 2 + (r_back - r_side) * max(sa, 0.0) ** 2
            r = 0.010 + (rr - 0.010) * f
            uv.append((r * ca, r * sa))
            meta.append(f)
    P = scalp.points(uv)
    N = scalp.normals(P)
    rows = []
    for i in range(nr + 1):
        sl = slice(i * nu, (i + 1) * nu)
        f = i / float(nr)
        off = 0.0045 * (1.0 - 0.80 * f ** 4)
        row = md.ring(P[sl] + N[sl] * off, w, tag='hair_cap')
        for j, vi in enumerate(row):
            _strand(md, vi, f, math.cos(TAU * j / nu), math.sin(TAU * j / nu), 0.0)
        rows.append(row)
    md.loft(rows, HAIRMAT, 'hair_cap', closed=True, flip=False)
    md.grid_cap(rows[0], HAIRMAT, 'hair_cap', flip=True)

    # ---------------- layer 1: wide locks from the hairline straight back, covering the whole top
    us = np.linspace(-0.070, 0.070, 11)
    for i, u in enumerate(us):
        v0 = hairline_v(u) + 0.003
        end_v = 0.096 - 0.036 * (abs(u) / 0.070) ** 2 + 0.006 * math.sin(i * 2.1)
        path = [(u, v0), (u * 0.97, v0 + 0.05), (u * 0.84, 0.0), (u * 0.64, end_v)]
        ribbon(md, scalp, path, width=0.0200, thick=0.0058, extra=0.0, front=1.0 - 0.55 * (abs(u) / 0.070) ** 2, tag='hair_l1')
    # ---------------- layer 2: staggered between layer-1 locks, a little higher and shorter, combed slightly right
    us2 = np.linspace(-0.063, 0.063, 10)
    for i, u in enumerate(us2):
        v0 = hairline_v(u) + 0.000
        sweep = -0.010
        end_v = 0.058 - 0.026 * (abs(u) / 0.063) ** 2 + 0.012 * math.cos(i * 1.7)
        path = [(u, v0), (u + sweep * 0.3, v0 + 0.045), (u * 0.86 + sweep, -0.005), (u * 0.72 + sweep * 1.2, end_v)]
        ribbon(md, scalp, path, width=0.0170, thick=0.0052, extra=0.0038, front=1.0 - 0.55 * (abs(u) / 0.063) ** 2, tag='hair_l2')
    # ---------------- layer 3: narrower accent locks with uneven lengths on the crest
    for (u, ln, sw) in [(-0.040, 0.085, -0.014), (-0.018, 0.118, -0.012), (0.006, 0.100, -0.016), (0.028, 0.124, -0.010),
                        (0.048, 0.080, -0.006)]:
        v0 = hairline_v(u) - 0.002
        path = [(u, v0), (u + sw * 0.4, v0 + ln * 0.35), (u + sw, v0 + ln * 0.7), (u + sw * 1.3, v0 + ln)]
        ribbon(md, scalp, path, width=0.0120, thick=0.0045, extra=0.0072, front=1.0 - 0.5 * (abs(u) / 0.06) ** 2, tag='hair_l3')
    info = dict(scalp=scalp)
    return md, info

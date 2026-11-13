"""Small numeric helpers shared by all generators (numpy only, no bpy)."""
import math
import numpy as np

TAU = 2.0 * math.pi


def V(*a):
    return np.array(a, dtype=np.float64)


def norm(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n < 1e-12, 1.0, n)


def length(v):
    return float(np.linalg.norm(v))


def lerp(a, b, t):
    return a + (b - a) * t


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def smoothstep(e0, e1, x):
    if e0 == e1:
        return (np.asarray(x) >= e0).astype(np.float64)
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def gauss(x, c, s):
    return np.exp(-0.5 * ((np.asarray(x, dtype=np.float64) - c) / s) ** 2)


def bump(x, c, half):
    """Compact smooth bump: 1 at c, 0 beyond c+-half."""
    t = np.clip(np.abs(np.asarray(x, dtype=np.float64) - c) / half, 0.0, 1.0)
    return (1.0 - t * t) ** 2


def ang_diff(a, b):
    """Signed smallest difference a-b for angles in radians."""
    d = (np.asarray(a) - b + math.pi) % TAU - math.pi
    return d


def ang_gauss(a, c, s):
    return np.exp(-0.5 * (ang_diff(a, c) / s) ** 2)


class Pchip:
    """Monotone cubic Hermite interpolation of vector valued tables (no overshoot)."""

    def __init__(self, x, y):
        self.x = np.asarray(x, dtype=np.float64)
        self.y = np.asarray(y, dtype=np.float64)
        if self.y.ndim == 1:
            self.y = self.y[:, None]
            self.scalar = True
        else:
            self.scalar = False
        n = len(self.x)
        h = np.diff(self.x)
        d = np.diff(self.y, axis=0) / h[:, None]
        m = np.zeros_like(self.y)
        if n == 2:
            m[0] = d[0]
            m[1] = d[0]
        else:
            for k in range(1, n - 1):
                w1 = 2 * h[k] + h[k - 1]
                w2 = h[k] + 2 * h[k - 1]
                dk0, dk1 = d[k - 1], d[k]
                same = (dk0 * dk1) > 0
                with np.errstate(divide='ignore', invalid='ignore'):
                    hm = (w1 + w2) / (w1 / np.where(dk0 == 0, 1, dk0) + w2 / np.where(dk1 == 0, 1, dk1))
                m[k] = np.where(same, hm, 0.0)
            m[0] = self._end(h[0], h[1], d[0], d[1])
            m[-1] = self._end(h[-1], h[-2], d[-1], d[-2])
        self.m = m
        self.h = h

    @staticmethod
    def _end(h0, h1, d0, d1):
        m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        m = np.where(np.sign(m) != np.sign(d0), 0.0, m)
        m = np.where((np.sign(d0) != np.sign(d1)) & (np.abs(m) > 3 * np.abs(d0)), 3 * d0, m)
        return m

    def __call__(self, xq):
        xq_arr = np.atleast_1d(np.asarray(xq, dtype=np.float64))
        xc = np.clip(xq_arr, self.x[0], self.x[-1])
        k = np.clip(np.searchsorted(self.x, xc, side='right') - 1, 0, len(self.x) - 2)
        h = self.h[k]
        t = ((xc - self.x[k]) / h)[:, None]
        h = h[:, None]
        h00 = 2 * t ** 3 - 3 * t ** 2 + 1
        h10 = t ** 3 - 2 * t ** 2 + t
        h01 = -2 * t ** 3 + 3 * t ** 2
        h11 = t ** 3 - t ** 2
        out = h00 * self.y[k] + h10 * h * self.m[k] + h01 * self.y[k + 1] + h11 * h * self.m[k + 1]
        if self.scalar:
            out = out[:, 0]
        if np.ndim(xq) == 0:
            return out[0]
        return out


def table(rows):
    """rows: list of (x, {name: value}) -> dict name -> Pchip over x. Missing names are not allowed."""
    xs = [r[0] for r in rows]
    names = list(rows[0][1].keys())
    return {n: Pchip(xs, [r[1][n] for r in rows]) for n in names}


def rot_axis(axis, ang):
    axis = norm(axis)
    x, y, z = axis
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def frame_from(y_axis, z_hint):
    """Right handed frame with Y along y_axis and Z as close as possible to z_hint. Columns = X,Y,Z."""
    y = norm(y_axis)
    z = np.asarray(z_hint, dtype=np.float64)
    z = z - y * np.dot(z, y)
    if np.linalg.norm(z) < 1e-9:
        z = np.array([0.0, 0.0, 1.0]) - y * y[2]
        if np.linalg.norm(z) < 1e-9:
            z = np.array([0.0, -1.0, 0.0])
    z = norm(z)
    x = np.cross(y, z)
    return np.stack([x, y, z], axis=1)


def superellipse_r(ang, a, b, n):
    """Polar radius of superellipse |x/a|^n + |y/b|^n = 1 at polar angle ang (x=cos, y=sin)."""
    c = np.abs(np.cos(ang))
    s = np.abs(np.sin(ang))
    return (np.maximum(c / a, 1e-12) ** n + np.maximum(s / b, 1e-12) ** n) ** (-1.0 / n)


def resample_closed(pts, n, anchor_idx=None):
    """Resample a dense closed polyline to n points at equal arc length, starting at pts[0]."""
    pts = np.asarray(pts)
    seg = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    tq = np.arange(n) * total / n
    k = np.clip(np.searchsorted(cum, tq, side='right') - 1, 0, len(pts) - 1)
    f = (tq - cum[k]) / np.where(seg[k] < 1e-12, 1, seg[k])
    nxt = (k + 1) % len(pts)
    return pts[k] * (1 - f)[:, None] + pts[nxt] * f[:, None]


def resample_open(pts, n):
    """Resample an open polyline to n points (including both ends) at equal arc length."""
    pts = np.asarray(pts)
    seg = np.linalg.norm(pts[1:] - pts[:-1], axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    tq = np.linspace(0, cum[-1], n)
    k = np.clip(np.searchsorted(cum, tq, side='right') - 1, 0, len(pts) - 2)
    f = (tq - cum[k]) / np.where(seg[k] < 1e-12, 1, seg[k])
    return pts[k] * (1 - f)[:, None] + pts[k + 1] * f[:, None]


def mirror_x(p):
    p = np.array(p, dtype=np.float64)
    p[..., 0] *= -1
    return p

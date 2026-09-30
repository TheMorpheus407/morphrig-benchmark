"""MorphRig signed-distance-field toolkit (numpy, no Blender dependency).

Authored for the MorphRig Operative.  Shapes of the organic surfaces (body suit,
head, hand, boots) are described as smooth unions of simple primitives; mesh
cages are then ray-cast / projected onto these fields.  All units are metres.
"""
import numpy as np


def _v(x):
    return np.asarray(x, dtype=np.float64)


def length(v):
    return np.sqrt(np.maximum((v * v).sum(-1), 0.0))


def normalize(v):
    v = _v(v)
    n = length(v)
    return v / np.maximum(n, 1e-12)[..., None] if v.ndim > 1 else v / max(n, 1e-12)


def rot_to_local(axis_y, axis_hint=(0.0, 0.0, 1.0)):
    """Return 3x3 matrix whose rows are the local X,Y,Z axes (local Y = axis_y)."""
    y = normalize(_v(axis_y))
    h = _v(axis_hint)
    if abs(np.dot(h, y)) > 0.95:
        h = _v((1.0, 0.0, 0.0))
    x = normalize(np.cross(y, h))
    z = np.cross(x, y)
    return np.stack([x, y, z])


class SDF:
    def __call__(self, p):
        raise NotImplementedError

    def grad(self, p, h=1e-4):
        p = _v(p)
        g = np.zeros_like(p)
        for i in range(3):
            d = np.zeros(3)
            d[i] = h
            g[:, i] = (self(p + d) - self(p - d)) / (2 * h)
        return g

    # composition helpers
    def __or__(self, other):
        return Union([self, other], 0.0)


class Sphere(SDF):
    def __init__(self, c, r):
        self.c, self.r = _v(c), float(r)

    def __call__(self, p):
        return length(p - self.c) - self.r


class Ellipsoid(SDF):
    """Approximate ellipsoid distance (Quilez bound). rot rows = local axes."""

    def __init__(self, c, r, axis=None, hint=(0.0, 0.0, 1.0), rot=None):
        self.c, self.r = _v(c), _v(r)
        if rot is not None:
            self.rot = _v(rot)
        elif axis is not None:
            self.rot = rot_to_local(axis, hint)
        else:
            self.rot = None

    def __call__(self, p):
        q = p - self.c
        if self.rot is not None:
            q = q @ self.rot.T
        k0 = length(q / self.r)
        k1 = length(q / (self.r * self.r))
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)


class Capsule(SDF):
    def __init__(self, a, b, r):
        self.a, self.b, self.r = _v(a), _v(b), float(r)

    def __call__(self, p):
        pa = p - self.a
        ba = self.b - self.a
        h = np.clip((pa @ ba) / (ba @ ba), 0.0, 1.0)
        return length(pa - h[:, None] * ba) - self.r


class RoundCone(SDF):
    """Exact round cone (Quilez): spheres r1 at a and r2 at b joined tangentially."""

    def __init__(self, a, b, r1, r2):
        self.a, self.b, self.r1, self.r2 = _v(a), _v(b), float(r1), float(r2)

    def __call__(self, p):
        a, b, r1, r2 = self.a, self.b, self.r1, self.r2
        ba = b - a
        l2 = ba @ ba
        rr = r1 - r2
        a2 = l2 - rr * rr
        il2 = 1.0 / l2
        pa = p - a
        y = pa @ ba
        z = y - l2
        x = pa * l2 - y[:, None] * ba
        x2 = (x * x).sum(-1)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
        d1 = np.sqrt(x2 + z2) * il2 - r2
        d2 = np.sqrt(x2 + y2) * il2 - r1
        return np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))


class EllipticCone(SDF):
    """Tapered capsule with elliptical cross-section (approximate).

    Axis from a to b; cross-section radii (rx, rz) interpolate from ra to rb.
    'hint' orients the local Z of the section.
    """

    def __init__(self, a, b, ra, rb, hint=(0.0, 0.0, 1.0)):
        self.a, self.b = _v(a), _v(b)
        self.ra, self.rb = _v(ra), _v(rb)
        self.rot = rot_to_local(self.b - self.a, hint)
        self.len = float(length(self.b - self.a))

    def __call__(self, p):
        q = (p - self.a) @ self.rot.T  # local: y along axis
        t = np.clip(q[:, 1] / self.len, 0.0, 1.0)
        r = self.ra[None, :] * (1 - t)[:, None] + self.rb[None, :] * t[:, None]
        # distance to elliptical section, scaled
        ex = q[:, 0] / r[:, 0]
        ez = q[:, 2] / r[:, 1]
        rad = np.sqrt(ex * ex + ez * ez)
        rmin = np.minimum(r[:, 0], r[:, 1])
        dsec = (rad - 1.0) * rmin
        yout = np.maximum(-q[:, 1], 0) + np.maximum(q[:, 1] - self.len, 0)
        # round the caps
        inside = np.maximum(dsec, 0)
        return np.where(yout > 0, np.sqrt(inside ** 2 + yout ** 2) + np.minimum(dsec, 0), dsec)


class RoundBox(SDF):
    def __init__(self, c, half, r, rot=None):
        self.c, self.half, self.r = _v(c), _v(half), float(r)
        self.rot = None if rot is None else _v(rot)

    def __call__(self, p):
        q = p - self.c
        if self.rot is not None:
            q = q @ self.rot.T
        d = np.abs(q) - (self.half - self.r)
        return length(np.maximum(d, 0.0)) + np.minimum(np.max(d, axis=-1), 0.0) - self.r


class Plane(SDF):
    """Half space: inside where dot(p-c, n) < 0."""

    def __init__(self, c, n):
        self.c, self.n = _v(c), normalize(_v(n))

    def __call__(self, p):
        return (p - self.c) @ self.n


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


class Union(SDF):
    def __init__(self, items, k=0.02):
        self.items = list(items)
        self.k = k

    def __call__(self, p):
        d = None
        for it in self.items:
            if isinstance(it, tuple):  # (sdf, k_override)
                s, k = it
            else:
                s, k = it, self.k
            v = s(p)
            d = v if d is None else smin(d, v, k)
        return d


class Subtract(SDF):
    def __init__(self, base, cutter, k=0.01):
        self.base, self.cutter, self.k = base, cutter, k

    def __call__(self, p):
        return smax(self.base(p), -self.cutter(p), self.k)


class Intersect(SDF):
    def __init__(self, a, b, k=0.0):
        self.a, self.b, self.k = a, b, k

    def __call__(self, p):
        return smax(self.a(p), self.b(p), self.k)


class Offset(SDF):
    def __init__(self, child, d):
        self.child, self.d = child, d

    def __call__(self, p):
        return self.child(p) - self.d


class Mirror(SDF):
    """Mirror across X=0 (left/right symmetric parts)."""

    def __init__(self, child):
        self.child = child

    def __call__(self, p):
        q = p.copy()
        q[:, 0] = np.abs(q[:, 0])
        return self.child(q)


class Displace(SDF):
    """Additive displacement field: f(p) - g(p) where g returns bump heights."""

    def __init__(self, child, fn):
        self.child, self.fn = child, fn

    def __call__(self, p):
        return self.child(p) - self.fn(p)


def gauss_bump(p, c, sig, amp):
    """Anisotropic gaussian bump; sig is per-axis sigma (world axes)."""
    q = (p - _v(c)) / _v(sig)
    return amp * np.exp(-0.5 * (q * q).sum(-1))


# ---------------------------------------------------------------------------
# Ray casting / projection
# ---------------------------------------------------------------------------

def ray_exit(sdf, origins, dirs, tmax=0.6, max_step=0.004, min_step=0.0003, iters=400):
    """Distance along each ray (starting inside, f<0) to the first exit crossing."""
    O = _v(origins)
    D = normalize(_v(dirs))
    n = len(O)
    t = np.zeros(n)
    f = sdf(O)
    hit = np.zeros(n, bool)
    lo = np.zeros(n)
    hi = np.full(n, np.nan)
    active = np.ones(n, bool)
    # origins outside: mark as zero distance
    outside = f > 0
    hi[outside] = 0.0
    lo[outside] = 0.0
    active[outside] = False
    for _ in range(iters):
        if not active.any():
            break
        idx = np.nonzero(active)[0]
        step = np.clip(-f[idx] * 0.8, min_step, max_step)
        tn = t[idx] + step
        fn = sdf(O[idx] + tn[:, None] * D[idx])
        crossed = fn > 0
        ci = idx[crossed]
        lo[ci] = t[ci]
        hi[ci] = tn[crossed]
        active[ci] = False
        hit[ci] = True
        t[idx] = tn
        f[idx] = fn
        over = t > tmax
        active &= ~over
    # bisection
    m = ~np.isnan(hi)
    a = lo[m].copy()
    b = hi[m].copy()
    Om, Dm = O[m], D[m]
    for _ in range(30):
        mid = 0.5 * (a + b)
        fm = sdf(Om + mid[:, None] * Dm)
        inside = fm < 0
        a = np.where(inside, mid, a)
        b = np.where(inside, b, mid)
    out = np.full(n, tmax)
    out[m] = 0.5 * (a + b)
    return out


def project(sdf, P, iters=6, maxmove=0.02):
    """Project points onto the zero set along the field gradient."""
    P = _v(P).copy()
    for _ in range(iters):
        f = sdf(P)
        g = sdf.grad(P)
        gg = np.maximum((g * g).sum(-1), 1e-12)
        mv = -(f / gg)[:, None] * g
        ln = length(mv)
        sc = np.minimum(1.0, maxmove / np.maximum(ln, 1e-12))
        P += mv * sc[:, None]
    return P


def surface_normals(sdf, P):
    return normalize(sdf.grad(P))


# ---------------------------------------------------------------------------
# Profile-driven solids (cross sections lofted along Z)
# ---------------------------------------------------------------------------

def pchip(xk, yk, x):
    """Monotone cubic (Fritsch-Carlson) interpolation, vectorised."""
    xk = np.asarray(xk, float)
    yk = np.asarray(yk, float)
    x = np.clip(np.asarray(x, float), xk[0], xk[-1])
    h = np.diff(xk)
    d = np.diff(yk) / h
    m = np.zeros_like(yk)
    for i in range(1, len(xk) - 1):
        if d[i - 1] * d[i] > 0:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = d[0]
    m[-1] = d[-1]
    idx = np.clip(np.searchsorted(xk, x) - 1, 0, len(xk) - 2)
    t = (x - xk[idx]) / h[idx]
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * yk[idx] + h10 * h[idx] * m[idx] + h01 * yk[idx + 1] + h11 * h[idx] * m[idx + 1]


class ProfileSolid(SDF):
    """Solid whose horizontal cross-sections are two superellipse halves.

    table rows: z, y_front, y_back, half_width, y_width, n_front, n_back
    (y_front < y_width < y_back).  Above the top row the solid is closed.
    """

    def __init__(self, table, dome_start=None, ztop=None):
        t = np.asarray(table, float)
        order = np.argsort(t[:, 0])
        self.t = t[order]
        self.zmin, self.zmax = self.t[0, 0], self.t[-1, 0]
        self.dome_start = dome_start
        self.ztop = ztop

    def props(self, z):
        cols = [pchip(self.t[:, 0], self.t[:, k], z) for k in range(1, 7)]
        return cols

    def __call__(self, p):
        z = p[:, 2]
        zq = z if self.dome_start is None else np.minimum(z, self.dome_start)
        yf, yb, w, yw, nf, nb = self.props(zq)
        if self.dome_start is not None:
            tt = np.clip((z - self.dome_start) / (self.ztop - self.dome_start), 0.0, 1.0)
            sc = np.sqrt(np.maximum(1.0 - tt * tt, 0.0))
            yf = yw + (yf - yw) * sc
            yb = yw + (yb - yw) * sc
            w = w * sc
        w = np.maximum(w, 1e-5)
        dx = p[:, 0]
        dy = p[:, 1] - yw
        rho = np.sqrt(dx * dx + dy * dy)
        rs = np.maximum(rho, 1e-9)
        cphi = -dy / rs
        sphi = np.abs(dx) / rs
        b = np.where(cphi > 0, yw - yf, yb - yw)
        b = np.maximum(b, 1e-5)
        n = np.where(cphi > 0, nf, nb)
        R = (np.abs(sphi / w) ** n + np.abs(cphi / b) ** n) ** (-1.0 / n)
        f = rho - R
        zt = self.zmax if self.ztop is None else self.ztop
        above = z > zt
        f = np.where(above, np.sqrt(rho ** 2 + (z - zt) ** 2) + 0.0, f)
        if self.dome_start is not None:
            # near the dome top the radial measure degenerates: use vertical distance too
            f = np.where(z > self.dome_start, np.maximum(f, (z - zt) * 0.9), f)
        below = z < self.zmin
        f = np.where(below, np.maximum(f, self.zmin - z), f)
        return f

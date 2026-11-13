"""Tiny signed-distance toolkit used to 'sculpt' organic forms with maths (numpy, vectorised)."""
import numpy as np


def sd_sphere(p, c, r):
    return np.linalg.norm(p - np.asarray(c), axis=1) - r


def sd_ellipsoid(p, c, rad, rot=None):
    q = p - np.asarray(c)
    if rot is not None:
        q = q @ np.asarray(rot)
    rad = np.asarray(rad, dtype=np.float64)
    k0 = np.linalg.norm(q / rad, axis=1)
    k1 = np.linalg.norm(q / (rad * rad), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_capsule(p, a, b, ra, rb=None):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    rb = ra if rb is None else rb
    pa = p - a
    ba = b - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0.0, 1.0)
    return np.linalg.norm(pa - h[:, None] * ba, axis=1) - (ra + (rb - ra) * h)


def sd_box(p, c, half, rot=None, r=0.0):
    q = p - np.asarray(c)
    if rot is not None:
        q = q @ np.asarray(rot)
    d = np.abs(q) - (np.asarray(half) - r)
    return np.linalg.norm(np.maximum(d, 0.0), axis=1) + np.minimum(d.max(axis=1), 0.0) - r


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


class Shape:
    """Ordered list of smooth unions / subtractions. Symmetric about x = 0 when sym=True."""

    def __init__(self, sym=True):
        self.ops = []
        self.sym = sym

    def add(self, fn, k=0.02):
        self.ops.append(('add', fn, k))
        return self

    def sub(self, fn, k=0.01):
        self.ops.append(('sub', fn, k))
        return self

    def __call__(self, p):
        p = np.asarray(p, dtype=np.float64)
        if self.sym:
            p = p.copy()
            p[:, 0] = np.abs(p[:, 0])
        d = None
        for kind, fn, k in self.ops:
            v = fn(p)
            if d is None:
                d = v
            elif kind == 'add':
                d = smin(d, v, k)
            else:
                d = smax(d, -v, k)
        return d

    def grad(self, p, eps=2e-4):
        p = np.asarray(p, dtype=np.float64)
        g = np.zeros_like(p)
        for i in range(3):
            e = np.zeros(3)
            e[i] = eps
            g[:, i] = (self(p + e) - self(p - e)) / (2 * eps)
        return g

    def project(self, p, iters=12, max_step=0.02):
        """Move points onto the zero level set along the gradient."""
        p = np.array(p, dtype=np.float64)
        for _ in range(iters):
            d = self(p)
            g = self.grad(p)
            n2 = np.maximum((g * g).sum(axis=1), 1e-12)
            step = np.clip(d, -max_step, max_step)[:, None] * g / n2[:, None]
            p -= step
        return p

    def normal(self, p):
        g = self.grad(p)
        return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)

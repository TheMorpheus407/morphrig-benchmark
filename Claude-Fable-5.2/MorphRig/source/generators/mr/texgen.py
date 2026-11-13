"""Procedural PBR textures for the Operative, painted in UV space from the rest mesh (numpy) + baked AO (Cycles).

Outputs per material slot (PNG, 8 bit):
  T_<Slot>_BaseColor  sRGB
  T_<Slot>_Normal     tangent space, OpenGL (+Y) convention
  T_<Slot>_ORM        linear: R ambient occlusion, G roughness, B metallic
  T_<Slot>_Mask       linear: R team accent paint, G team icon A (chevron) + solid trim, B team icon B (ring) + dashed trim,
                      A emissive accent weight                    (only for slots that use it)
Space: armature rest space, metres, +X = character's left, -Y = forward, +Z = up.
"""
import json
import math
import os
import time
import numpy as np
from .texraster import MeshArrays, Raster, write_png, linear_to_srgb, srgb_to_linear
from . import skel

J = skel.J
SIZES = {'M_Skin': 4096, 'M_EyesMouth': 1024, 'M_Hair': 2048, 'M_Suit': 2048, 'M_Armor': 2048, 'M_Cyber': 2048}
AUX_DIV = {'M_Skin': 2}                      # normal / ORM are written at size / AUX_DIV
SHADING = {'M_Skin': 'skin', 'M_EyesMouth': 'wet', 'M_Hair': 'hair', 'M_Suit': 'cloth', 'M_Armor': 'hard', 'M_Cyber': 'metal'}
HAS_MASK = ('M_EyesMouth', 'M_Suit', 'M_Armor', 'M_Cyber')


def S(r, g, b):
    """sRGB triple -> linear numpy colour."""
    return srgb_to_linear(np.array([r, g, b], dtype=np.float64))


# ------------------------------------------------------------------------------------------------ maths helpers
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-20), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    """colour / scalar mix with a per-texel weight."""
    t = np.asarray(t)
    if np.ndim(a) == 1 and len(a) == 3 and np.ndim(t) == 1:
        a = np.broadcast_to(a, (len(t), 3))
    if np.ndim(a) == 2 and np.ndim(t) == 1:
        t = t[:, None]
    return a + (b - a) * t


def _hash3(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761 & 0x7FFFFFFF)
    h = ((h ^ (h >> 13)) * 1274126177) & 0x7FFFFFFF
    h = (h ^ (h >> 16)) & 0x7FFFFFFF
    return h.astype(np.float64) / 2147483648.0


def vnoise(p, freq, seed=0):
    """Value noise in [0, 1] of 3D points (n, 3)."""
    q = p * freq
    i = np.floor(q).astype(np.int64)
    f = q - i
    u = f * f * (3.0 - 2.0 * f)
    out = 0.0
    for dz in (0, 1):
        wz = u[:, 2] if dz else 1.0 - u[:, 2]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1.0 - u[:, 1]
            for dx in (0, 1):
                wx = u[:, 0] if dx else 1.0 - u[:, 0]
                out = out + _hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed) * wx * wy * wz
    return out


def fbm(p, freq, octaves=4, seed=0, gain=0.5, lac=2.03):
    a, tot, out = 1.0, 0.0, 0.0
    for o in range(octaves):
        out = out + a * vnoise(p, freq, seed + 17 * o)
        tot += a
        a *= gain
        freq *= lac
    return out / tot


def noise1(x, seed=0):
    """1D value noise."""
    i = np.floor(x).astype(np.int64)
    f = x - i
    u = f * f * (3.0 - 2.0 * f)
    z = np.zeros_like(i)
    return _hash3(i, z, z, seed) * (1 - u) + _hash3(i + 1, z, z, seed) * u


def seg_dist(px, py, ax, ay, bx, by):
    """Distance from 2D points to the segment a-b."""
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy + 1e-20), 0.0, 1.0)
    return np.hypot(px - (ax + dx * t), py - (ay + dy * t))


def polyline_dist(px, py, pts):
    d = np.full(px.shape, 1e9)
    for (a, b) in zip(pts[:-1], pts[1:]):
        d = np.minimum(d, seg_dist(px, py, a[0], a[1], b[0], b[1]))
    return d


def line_mask(d, width, soft=0.00025):
    return 1.0 - smoothstep(width * 0.5 - soft, width * 0.5 + soft, d)


def triplanar_uv(P, N):
    """2D coordinates of each texel on the plane of its dominant normal axis."""
    a = np.abs(N)
    ax = np.argmax(a, axis=1)
    u = np.where(ax == 0, P[:, 1], P[:, 0])
    v = np.where(ax == 2, P[:, 1], P[:, 2])
    return u, v


def hex_edge(u, v, size):
    """Distance (in units of size) to the nearest hexagon cell edge, 0 at the edge .. 0.5 at the centre."""
    x, y = u / size, v / size
    sx, sy = 1.0, math.sqrt(3.0)
    ax = np.mod(x, sx) - sx / 2
    ay = np.mod(y, sy) - sy / 2
    bx = np.mod(x - sx / 2, sx) - sx / 2
    by = np.mod(y - sy / 2, sy) - sy / 2
    use_a = (ax * ax + ay * ay) < (bx * bx + by * by)
    gx = np.abs(np.where(use_a, ax, bx))
    gy = np.abs(np.where(use_a, ay, by))
    d = np.maximum(gx, gx * 0.5 + gy * (sy / 2))
    return 0.5 - d


# ------------------------------------------------------------------------------------------------ context
class Fields:
    """Per-vertex helper fields of the whole mesh."""

    def __init__(self, ma):
        self.ma = ma
        co, tv = ma.co, ma.tri_verts
        fn = np.cross(co[tv[:, 1]] - co[tv[:, 0]], co[tv[:, 2]] - co[tv[:, 0]])
        vn = np.zeros_like(co)
        for k in range(3):
            np.add.at(vn, tv[:, k], fn)
        self.vn = vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        e = np.concatenate([tv[:, [0, 1]], tv[:, [1, 2]], tv[:, [2, 0]]])
        e = np.concatenate([e, e[:, ::-1]])
        d = co[e[:, 1]] - co[e[:, 0]]
        k = ((self.vn[e[:, 1]] - self.vn[e[:, 0]]) * d).sum(axis=1) / np.maximum((d * d).sum(axis=1), 1e-12)
        cnt = np.maximum(np.bincount(e[:, 0], minlength=len(co)), 1)
        self.curv = np.bincount(e[:, 0], weights=k, minlength=len(co)) / cnt          # > 0 convex (1/m)
        # open boundary vertices
        es = np.sort(np.concatenate([tv[:, [0, 1]], tv[:, [1, 2]], tv[:, [2, 0]]]), axis=1)
        key = es[:, 0].astype(np.int64) * len(co) + es[:, 1]
        uniq, counts = np.unique(key, return_counts=True)
        b = uniq[counts == 1]
        self.boundary = np.zeros(len(co))
        self.boundary[(b // len(co)).astype(np.int64)] = 1.0
        self.boundary[(b % len(co)).astype(np.int64)] = 1.0

    def boundary_field(self, regions, iters=2, lam=0.5):
        """1 on open-boundary vertices of the given regions, smoothly decaying over a few rings."""
        m = self.ma.region_mask_vertices(regions) * self.boundary
        return self.ma.smooth_vertex_field(m, iters=iters, lam=lam)


class Ctx:
    def __init__(self, ma, fields, r, ao):
        self.ma, self.f, self.r = ma, fields, r
        self.n = r.n
        self.P = r.position()
        self.N = r.normal()
        self.reg = r.region()
        self.ao = ao if ao is not None else np.ones(r.n)
        self.size = r.size

    def m(self, *names):
        ids = [self.ma.region_id(x) for x in names]
        return np.isin(self.reg, ids)

    def v(self, values):
        return self.r.vertex_attr(values)

    def attr(self, name):
        a = self.ma.vattr.get(name)
        return self.r.vertex_attr(a) if a is not None else np.zeros(self.n)

    def blur(self, values, radius_px):
        """Soften a per-texel scalar in UV space (inside its island neighbourhood)."""
        rad = max(1, int(round(radius_px * self.size / 4096.0)))
        img = self.r.dilate(self.r.image(values.astype(np.float32)), iters=min(rad * 2, 24))
        for _ in range(3):
            for axis in (0, 1):
                c = np.cumsum(np.pad(img, [(rad + 1, rad) if a == axis else (0, 0) for a in (0, 1)], mode='edge'), axis=axis, dtype=np.float64)
                if axis == 0:
                    img = ((c[2 * rad + 1:, :] - c[:-(2 * rad + 1), :]) / (2 * rad + 1)).astype(np.float32)
                else:
                    img = ((c[:, 2 * rad + 1:] - c[:, :-(2 * rad + 1)]) / (2 * rad + 1)).astype(np.float32)
        return img[self.r.yx].astype(np.float64)


def new_result(n, base, rough, metal=0.0):
    return dict(base=np.broadcast_to(np.asarray(base, dtype=np.float64), (n, 3)).copy(), rough=np.full(n, float(rough)),
                metal=np.full(n, float(metal)), height=np.zeros(n), mask=np.zeros((n, 4)), ao=None)


def paint(res, m, base=None, rough=None, metal=None):
    """Blend a material over the result with weight m (n,)."""
    if base is not None:
        res['base'] = mix(res['base'], np.asarray(base, dtype=np.float64), m)
    if rough is not None:
        res['rough'] = res['rough'] + (rough - res['rough']) * m
    if metal is not None:
        res['metal'] = res['metal'] + (metal - res['metal']) * m


# ------------------------------------------------------------------------------------------------ skin
def shade_skin(c):
    P, N = c.P, c.N
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    res = new_result(c.n, S(0.83, 0.62, 0.52), 0.47)
    head = c.m('face', 'scalp', 'neck', 'lips', 'lipskin', 'eyelid_l', 'eyelid_r')
    # ---- broad tone variation
    n1 = fbm(P, 22.0, 3, seed=3)
    n2 = fbm(P, 160.0, 3, seed=9)
    tone = 1.0 + 0.07 * (n1 - 0.5) + 0.04 * (n2 - 0.5)
    res['base'] = res['base'] * tone[:, None]
    red = S(0.80, 0.42, 0.38)
    eye_l, eye_r = J['eye_l'], J['eye_r']
    # nose tip = most forward face point
    fsel = c.m('face')
    if fsel.any():
        k = np.argmin(np.where(fsel, y, 1e9))
        nose = P[k]
    else:
        nose = np.array([0.0, -0.12, 1.635])
    g3 = lambda cx, cy, cz, rr: np.exp(-(((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) / (rr * rr)))
    blush = np.zeros(c.n)
    for sx in (1.0, -1.0):
        blush += g3(sx * 0.047, nose[1] + 0.036, nose[2] + 0.004, 0.024) * 0.30
        blush += g3(sx * 0.031, eye_l[1] - 0.004, eye_l[2] - 0.016, 0.012) * 0.04            # under-eye warmth
    blush += g3(nose[0], nose[1], nose[2], 0.013) * 0.22
    blush += g3(0.0, nose[1] + 0.022, nose[2] - 0.062, 0.016) * 0.12                          # chin
    paint(res, np.clip(blush, 0, 1) * head, base=red)
    # forehead a touch lighter
    fore = g3(0.0, nose[1] + 0.028, nose[2] + 0.078, 0.040) * head
    res['base'] = res['base'] * (1.0 + 0.05 * fore)[:, None]
    res['rough'] = res['rough'] - 0.05 * fore - 0.06 * g3(nose[0], nose[1], nose[2], 0.014)
    # ---- shaved sides / back: stubble
    # (undercut: everything behind the sideburn line and above the nape line, plus the crown under the hair)
    phi = np.abs(np.degrees(np.arctan2(x, -(y - 0.010))))
    side_edge = 66.0 - 14.0 * smoothstep(1.66, 1.72, z)                    # sideburn line leans forward towards the temple
    nape = 1.640 - 0.070 * smoothstep(92.0, 138.0, phi)
    und = smoothstep(side_edge - 3.0, side_edge + 3.0, phi) * smoothstep(nape - 0.004, nape + 0.005, z) * head
    scalp = np.maximum(c.blur(c.m('scalp').astype(np.float64), 70), und)
    dots = vnoise(P, 3800.0, seed=5)
    stub = np.clip(scalp, 0, 1) * (0.62 + 0.30 * smoothstep(0.35, 0.75, dots))
    paint(res, stub, base=S(0.33, 0.29, 0.28), rough=0.62)
    res['height'] += stub * (dots - 0.5) * 0.00006
    # ---- brows (front projection)
    brow = np.zeros(c.n)
    frontish = smoothstep(0.05, 0.35, -N[:, 1])
    for sx in (1.0, -1.0):
        ax = x * sx
        t = np.clip((ax - 0.0095) / 0.049, 0.0, 1.0)
        zb = eye_l[2] + 0.0185 + 0.0048 * np.sin(np.pi * t ** 0.85) - 0.0050 * smoothstep(0.62, 1.0, t)
        th = 0.0064 * (1.0 - 0.70 * t ** 1.3)
        inside = smoothstep(0.0, 0.004, ax - 0.0085) * (1.0 - smoothstep(0.056, 0.060, ax))
        hairs = 0.72 + 0.28 * noise1((z - zb) * 900.0 + ax * 2600.0, seed=11) * noise1(ax * 5200.0 + z * 800.0, seed=12)
        brow = np.maximum(brow, (1.0 - smoothstep(th * 0.30, th * 0.62, np.abs(z - zb))) * inside * hairs)
    brow *= frontish * c.m('face', 'eyelid_l', 'eyelid_r')
    paint(res, np.clip(brow * 1.4, 0, 1) * 0.92, base=S(0.155, 0.125, 0.115), rough=0.6)
    res['height'] += brow * 0.00007
    # ---- lash line / liner along the lid margins
    lid = c.v(c.f.boundary_field(['eyelid_l', 'eyelid_r'], iters=1, lam=0.45)) * c.m('eyelid_l', 'eyelid_r')
    upper = smoothstep(-0.001, 0.002, z - eye_l[2])
    liner = smoothstep(0.30, 0.85, lid) * (0.45 + 0.55 * upper)
    paint(res, liner * 0.88, base=S(0.10, 0.075, 0.075), rough=0.5)
    shade = smoothstep(0.02, 0.5, lid) * 0.14                                                 # soft socket shading
    res['base'] = res['base'] * (1.0 - shade * (0.6 + 0.4 * upper))[:, None]
    # ---- lips
    lips = c.blur(c.m('lips').astype(np.float64), 10)
    lipcol = S(0.62, 0.30, 0.32)
    paint(res, np.clip(lips, 0, 1) * 0.90, base=lipcol, rough=0.30)
    seam = c.v(c.f.boundary_field(['lips'], iters=1, lam=0.4)) * c.m('lips')
    res['base'] = res['base'] * (1.0 - 0.45 * smoothstep(0.25, 0.9, seam))[:, None]
    crease = np.sin(x * 2 * np.pi / 0.0011 + 6.0 * noise1(x * 700.0, seed=4))
    res['height'] += lips * crease * 0.00004
    # ---- circuit inlay on the left temple / cheekbone (side projection), fed from the ear unit
    side = smoothstep(0.25, 0.55, N[:, 0]) * (x > 0.03) * head
    zc = 1.655
    lines = [[(-0.012, zc), (-0.046, zc), (-0.056, zc - 0.010), (-0.068, zc - 0.010)],
             [(-0.026, zc), (-0.034, zc + 0.008), (-0.058, zc + 0.008)],
             [(-0.018, zc), (-0.026, zc - 0.008), (-0.040, zc - 0.008)]]
    d = np.full(c.n, 1e9)
    nodes = np.full(c.n, 1e9)
    for ln in lines:
        d = np.minimum(d, polyline_dist(y, z, ln))
        nodes = np.minimum(nodes, np.hypot(y - ln[-1][0], z - ln[-1][1]))
    inlay = np.maximum(line_mask(d, 0.0009, 0.00015), 1.0 - smoothstep(0.0013, 0.0016, nodes)) * side
    paint(res, inlay, base=S(0.62, 0.80, 0.82), rough=0.28, metal=0.9)
    res['height'] -= inlay * 0.00008
    # ---- left arm: barcode tattoo on the outer upper arm
    a0, a1 = J['upperarm_l'], J['lowerarm_l']
    axis = (a1 - a0) / np.linalg.norm(a1 - a0)
    n_out = np.array([0.73, 0.0, 0.68])
    n_out = n_out - axis * np.dot(n_out, axis)
    n_out /= np.linalg.norm(n_out)
    tdir = np.cross(axis, n_out)
    cen = a0 + (a1 - a0) * 0.50
    rel = P - cen
    sa, ta = rel @ axis, rel @ tdir
    arm = c.m('skinarm_l')
    facing = smoothstep(0.45, 0.75, N @ n_out)
    bar_i = np.floor((sa + 0.021) / 0.0010)
    bars = (_hash3(bar_i.astype(np.int64), np.zeros(c.n, np.int64), np.zeros(c.n, np.int64), 77) > 0.46).astype(np.float64)
    guard = ((bar_i == 0) | (bar_i == 2) | (bar_i == 39) | (bar_i == 41)).astype(np.float64)
    inbar = (np.abs(sa) < 0.021) * (np.abs(ta) < np.where(guard > 0, 0.0115, 0.0095))
    digits = (np.abs(sa) < 0.017) * (ta > -0.0145) * (ta < -0.0112) * (_hash3((np.floor(sa / 0.0016)).astype(np.int64), np.zeros(c.n, np.int64),
                                                                              np.zeros(c.n, np.int64), 31) > 0.35)
    ink = np.clip(np.maximum(np.maximum(bars, guard) * inbar, digits), 0, 1) * facing * arm
    paint(res, ink * 0.80, base=S(0.10, 0.13, 0.17), rough=0.5)
    # ---- hand: knuckles, dark glossy nails
    hand = c.m('hand', 'thumb', 'finger_index', 'finger_middle', 'finger_ring', 'finger_pinky')
    dorsal = -skel.HAND_P
    kn = np.zeros(c.n)
    nail = np.zeros(c.n)
    for fn in ('thumb', 'index', 'middle', 'ring', 'pinky'):
        dn = dorsal if fn != 'thumb' else -skel.hand_dir(0.25, -0.75, 0.62)
        for jn in ('_02_l', '_03_l'):
            jp = J[fn + jn]
            kn += np.exp(-((P - (jp + dn * 0.006)) ** 2).sum(axis=1) / 0.006 ** 2) * 0.35
        j3, je = J[fn + '_03_l'], J[fn + '_end_l']
        ax = (je - j3) / np.linalg.norm(je - j3)
        lat = np.cross(ax, dn)
        cen = j3 + (je - j3) * 0.60
        rel = P - cen
        s_, l_ = rel @ ax, rel @ lat
        w = 0.0036 if fn != 'thumb' else 0.0046
        e = (s_ / 0.0058) ** 2 + (l_ / w) ** 2
        nail = np.maximum(nail, (1.0 - smoothstep(0.80, 1.05, e)) * smoothstep(0.25, 0.55, N @ dn))
    paint(res, np.clip(kn, 0, 0.5) * hand * smoothstep(0.1, 0.5, N @ dorsal), base=red)
    paint(res, nail * hand, base=S(0.05, 0.09, 0.12), rough=0.16)
    res['height'] += nail * hand * 0.00012
    # ---- pores
    res['height'] += (vnoise(P, 2600.0, seed=21) - 0.5) * 0.000035 * (1.0 - np.clip(stub + brow + nail, 0, 1))
    res['rough'] = res['rough'] + 0.05 * (n2 - 0.5)
    # ambient occlusion tints towards a warm shadow tone instead of grey
    aoc = np.clip(c.ao, 0, 1)
    res['base'] = res['base'] * mix(S(0.62, 0.36, 0.30), np.ones(3), smoothstep(0.25, 0.9, aoc))
    return res


# ------------------------------------------------------------------------------------------------ eyes, teeth, tongue, mouth
def shade_eyesmouth(c):
    P, N = c.P, c.N
    res = new_result(c.n, S(0.25, 0.08, 0.08), 0.35)
    res['ao'] = np.ones(c.n)
    for side in ('l', 'r'):
        m = c.m('eye_' + side)
        if not m.any():
            continue
        ce = J['eye_' + side]
        d = P - ce
        d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        th = np.arccos(np.clip(-d[:, 1], -1, 1))                      # angle from the visual axis (-Y)
        ph = np.arctan2(d[:, 2], d[:, 0])
        r = th / 0.505
        scl = mix(S(0.90, 0.88, 0.86), S(0.83, 0.60, 0.56), smoothstep(0.85, 1.45, th) * 0.45)
        vein = smoothstep(0.62, 0.80, fbm(np.stack([ph * 3.0, th * 1.4, np.zeros(c.n)], axis=1), 2.2, 3, seed=41)) * smoothstep(0.70, 1.2, th)
        scl = mix(scl, S(0.78, 0.38, 0.36), vein * 0.35)
        fib = noise1(ph * 22.0 / (2 * np.pi) * 6.0, seed=3) * 0.6 + noise1(ph * 70.0, seed=8) * 0.4
        iris = mix(S(0.05, 0.30, 0.38), S(0.16, 0.62, 0.66), np.clip(fib * (0.55 + 0.45 * r), 0, 1))
        iris = mix(iris, S(0.75, 0.62, 0.30), (1.0 - smoothstep(0.38, 0.56, r)) * 0.50)       # warm collarette near the pupil
        iris = iris * (1.0 - 0.75 * smoothstep(0.80, 1.0, r))[:, None]                          # limbal ring
        ring = line_mask(np.abs(r - 0.68), 0.045, 0.012)
        ticks = line_mask(np.abs(r - 0.80), 0.05, 0.012) * (np.mod(ph / (2 * np.pi) * 12.0, 1.0) < 0.22)
        aug = np.clip(ring + ticks, 0, 1)
        iris = mix(iris, S(0.70, 0.98, 0.96), aug * 0.85)
        col = mix(scl, iris, 1.0 - smoothstep(0.97, 1.03, r))
        col = mix(col, S(0.012, 0.012, 0.015), 1.0 - smoothstep(0.33, 0.37, r))
        res['base'][m] = col[m]
        res['rough'][m] = np.where(r < 1.05, 0.06, 0.16)[m]
        res['mask'][m, 3] = (aug * (r < 1.0) * 0.55)[m]
    for name, top in (('teeth_upper', True), ('teeth_lower', False)):
        m = c.m(name)
        if not m.any():
            continue
        z = P[:, 2]
        zmin, zmax = z[m].min(), z[m].max()
        g = (z - zmin) / max(zmax - zmin, 1e-6)
        gum = smoothstep(0.52, 0.66, g) if top else smoothstep(0.48, 0.34, g)
        # tooth gaps: constant arc-length steps along the dental arch (parabola x = w t, y = fy + d t^2), found by
        # projecting every texel onto the arch centre line
        fy, tw, dp = (-0.1008, 0.0215, 0.0300) if top else (-0.0968, 0.0200, 0.0285)
        t = np.clip(P[:, 0] / tw, -1.2, 1.2)
        for _ in range(6):
            ox, oy = tw * t, fy + dp * t * t
            dx, dy = tw, 2.0 * dp * t
            f = (ox - P[:, 0]) * dx + (oy - P[:, 1]) * dy
            df = dx * dx + dy * dy + (oy - P[:, 1]) * 2.0 * dp
            t = np.clip(t - f / np.maximum(df, 1e-9), -1.3, 1.3)
        a = 2.0 * dp / tw
        arc = np.sign(t) * 0.5 * tw * (np.abs(t) * np.sqrt(1.0 + (a * t) ** 2) + np.arcsinh(a * np.abs(t)) / a)
        tooth = 0.0074
        gap = line_mask(np.abs(np.mod(arc / tooth + 0.5, 1.0) - 0.5) * tooth, 0.0005, 0.00015) * (1.0 - gum)
        col = mix(S(0.86, 0.83, 0.74), S(0.70, 0.33, 0.34), gum)
        col = col * (1.0 - 0.55 * gap)[:, None]
        res['base'][m] = col[m]
        res['rough'][m] = mix(0.22, 0.36, gum)[m]
        res['height'][m] = (-gap * 0.00012)[m]
    m = c.m('tongue')
    if m.any():
        bump = vnoise(P, 1500.0, seed=6)
        res['base'][m] = (S(0.72, 0.34, 0.36) * (0.9 + 0.2 * bump)[:, None])[m]
        res['rough'][m] = 0.34
        res['height'][m] = ((bump - 0.5) * 0.00008)[m]
    m = c.m('mouthbag')
    if m.any():
        depth = smoothstep(-0.105, -0.075, P[:, 1])
        res['base'][m] = mix(S(0.42, 0.15, 0.16), S(0.12, 0.03, 0.04), depth)[m]
        res['rough'][m] = 0.40
        res['ao'][m] = mix(0.8, 0.35, depth)[m]
    return res


# ------------------------------------------------------------------------------------------------ hair
def shade_hair(c):
    P = c.P
    s = c.attr('strand_s')
    ca, sa = c.attr('strand_c'), c.attr('strand_n')
    lock = c.attr('strand_id')
    ang = np.arctan2(sa, ca)
    a = ang / (2 * np.pi) + 0.012 * np.sin(s * 9.0 + lock * 40.0)
    cap = c.m('hair_cap')
    k1 = np.where(cap, 260.0, 46.0)
    k2 = np.where(cap, 60.0, 11.0)
    v1 = noise1(a * k1 + lock * 97.0, seed=1)
    v2 = noise1(a * k2 + lock * 31.0, seed=2)
    v3 = noise1(a * k1 * 2.3 + lock * 13.0 + s * 3.0, seed=3)
    root, mid, tip = S(0.26, 0.23, 0.23), S(0.88, 0.88, 0.91), S(0.97, 0.97, 0.99)
    col = mix(root, mid, smoothstep(0.02, 0.26, s))
    col = mix(col, tip, smoothstep(0.55, 1.0, s) * 0.8)
    streak = 0.84 + 0.20 * v1 + 0.08 * (v3 - 0.5)
    col = col * streak[:, None]
    col = mix(col, col * S(0.66, 0.69, 0.74), smoothstep(0.50, 0.25, v2) * 0.45)               # darker strand groups
    col = mix(col, S(0.62, 0.90, 0.96), smoothstep(0.84, 0.93, v2) * 0.42 * smoothstep(0.15, 0.4, s))   # a few cool-tinted strands
    under = smoothstep(-0.7, 0.35, np.sin(ang))
    col = col * np.where(cap, 1.0, 0.80 + 0.20 * under)[:, None]
    capc = mix(root, mid, 0.42) * (0.70 + 0.45 * v1)[:, None]
    col = np.where(cap[:, None], capc, col)
    res = new_result(c.n, np.zeros(3), 0.40)
    res['base'] = col
    res['rough'] = 0.34 + 0.22 * (1.0 - v1) + np.where(cap, 0.1, 0.0)
    res['height'] = (v1 - 0.5) * 0.00032 + (v3 - 0.5) * 0.00016 + (v2 - 0.5) * 0.00020
    m = c.m('lash')
    res['base'][m] = S(0.035, 0.03, 0.03)
    res['rough'][m] = 0.5
    res['height'][m] = 0.0
    return res


# ------------------------------------------------------------------------------------------------ suit
def _limb_axis_coords(P, joints):
    """(distance along the joint chain, nearest axis point) for a polyline of joints."""
    best = np.full(len(P), 1e9)
    near = np.zeros_like(P)
    for a, b in zip(joints[:-1], joints[1:]):
        d = b - a
        t = np.clip(((P - a) @ d) / (d @ d), 0.0, 1.0)
        q = a + t[:, None] * d
        dist = np.linalg.norm(P - q, axis=1)
        upd = dist < best
        best = np.where(upd, dist, best)
        near[upd] = q[upd]
    return best, near


def shade_suit(c):
    P, N = c.P, c.N
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    fab_a = S(0.205, 0.240, 0.315)          # main technical fabric (dark navy)
    fab_b = S(0.118, 0.134, 0.172)          # rubberised flex panels
    res = new_result(c.n, fab_a, 0.66)
    tu, tv = triplanar_uv(P, N)
    hexd = hex_edge(tu, tv, 0.0052)
    weave = smoothstep(0.0, 0.10, hexd)
    grain = fbm(P, 900.0, 2, seed=5)
    res['base'] = res['base'] * (0.82 + 0.20 * weave + 0.10 * (grain - 0.5))[:, None]
    res['height'] = (weave - 1.0) * 0.00010
    torso = c.m('torso', 'collar')
    legs_l, legs_r = c.m('leg_l'), c.m('leg_r')
    arm_r = c.m('arm_r')
    panel = np.zeros(c.n)
    pipe = np.zeros(c.n)
    seam = np.zeros(c.n)
    # torso: side panels between the front and back fields, spine channel
    th = np.degrees(np.arctan2(x, -y))                     # 0 front, +-90 sides, 180 back
    rho = np.hypot(x, y)
    for sgn in (1.0, -1.0):
        t = th * sgn
        inz = smoothstep(0.985, 1.005, z) * (1.0 - smoothstep(1.335, 1.355, z))
        pn = smoothstep(56.0, 58.0, t) * (1.0 - smoothstep(120.0, 122.0, t)) * inz * torso
        panel = np.maximum(panel, pn)
        for edge in (57.0, 121.0):
            dm = np.abs(np.radians(t - edge)) * rho
            seam = np.maximum(seam, line_mask(dm, 0.0016) * inz * torso)
        dm = np.abs(np.radians(t - 51.5)) * rho
        pipe = np.maximum(pipe, line_mask(dm, 0.0042) * inz * torso)
    spine = (1.0 - smoothstep(0.024, 0.026, np.abs(x))) * smoothstep(0.3, 0.6, N[:, 1]) * torso * smoothstep(1.0, 1.02, z)
    panel = np.maximum(panel, spine)
    # zipper down the centre front
    zipm = (np.abs(x) < 0.0030) * smoothstep(0.2, 0.5, -N[:, 1]) * torso * (z > 0.99)
    teeth = (np.mod(z, 0.0030) < 0.0017).astype(np.float64)
    # legs: inner flex panel, outer double stripe, ribbed knee zone
    for sgn, mleg, jn in ((1.0, legs_l, '_l'), (-1.0, legs_r, '_r')):
        chain = [J['thigh' + jn], J['calf' + jn], J['foot' + jn]]
        dist, near = _limb_axis_coords(P, chain)
        rad = P - near
        rl = np.maximum(np.linalg.norm(rad[:, :2], axis=1), 1e-6)
        ang = np.degrees(np.arctan2(rad[:, 0] * sgn, -rad[:, 1]))             # 0 front, +90 outer side, -90 inner
        inner = smoothstep(-128.0, -124.0, ang) * (1.0 - smoothstep(-56.0, -52.0, ang)) * smoothstep(0.50, 0.52, z) * (1.0 - smoothstep(0.90, 0.93, z))
        panel = np.maximum(panel, inner * mleg)
        knee = smoothstep(0.43, 0.445, z) * (1.0 - smoothstep(0.585, 0.60, z))
        panel = np.maximum(panel, knee * mleg)
        for off in (-7.0, 7.0):
            dm = np.abs(np.radians(ang - (90.0 + off))) * rl
            st = line_mask(dm, 0.0034) * smoothstep(0.615, 0.63, z) * (1.0 - smoothstep(0.925, 0.94, z))
            pipe = np.maximum(pipe, st * mleg)
        for zc in (0.605, 0.425):
            seam = np.maximum(seam, line_mask(np.abs(z - zc), 0.0018) * mleg)
    # right sleeve: elbow flex zone and a biceps band
    a0, a1 = J['upperarm_r'], J['lowerarm_r']
    ax = (a1 - a0) / np.linalg.norm(a1 - a0)
    sarm = (P - a0) @ ax
    L = np.linalg.norm(a1 - a0)
    panel = np.maximum(panel, smoothstep(L - 0.060, L - 0.050, sarm) * arm_r)
    pipe = np.maximum(pipe, line_mask(np.abs(sarm - 0.115), 0.0048) * arm_r)
    pipe = np.maximum(pipe, line_mask(np.abs(sarm - 0.127), 0.0020) * arm_r)
    # collar: knitted rib with an accent rim
    col = c.m('collar')
    zc_top = z[col].max() if col.any() else 1.5
    pipe = np.maximum(pipe, smoothstep(zc_top - 0.0065, zc_top - 0.0050, z) * col)
    rib_v = np.sin(np.radians(th) * rho * 2 * np.pi / 0.0032)
    # apply flex panels
    ribs = np.sin(z * 2 * np.pi / 0.0042)
    paint(res, panel, base=fab_b * (0.92 + 0.16 * smoothstep(-0.2, 0.6, ribs))[:, None], rough=0.40)
    res['height'] = res['height'] * (1.0 - panel) + panel * ribs * 0.00016
    res['height'] += col * rib_v * 0.00014 * (1.0 - panel)
    res['height'] -= seam * 0.00030
    res['base'] = res['base'] * (1.0 - 0.55 * seam)[:, None]
    paint(res, zipm, base=S(0.05, 0.05, 0.06), rough=0.42, metal=0.0)
    paint(res, zipm * teeth * (np.abs(x) < 0.0019), base=S(0.42, 0.43, 0.45), rough=0.32, metal=1.0)
    res['height'] += zipm * (teeth * 0.00025 - 0.00010)
    # glove (fingerless, left hand)
    gl = c.m('glove', 'glove_hem')
    leather = fbm(P, 520.0, 3, seed=8)
    paint(res, gl, base=S(0.13, 0.12, 0.12) * (0.85 + 0.3 * leather)[:, None], rough=0.50)
    res['height'] = np.where(gl, (leather - 0.5) * 0.00012, res['height'])
    hem = c.m('glove_hem', 'hem_l')
    paint(res, hem, base=S(0.045, 0.045, 0.05), rough=0.58)
    pipe = np.maximum(pipe, c.m('hem_l') * 1.0)
    # webbing straps / arm band
    st = c.m('strap_l', 'strap_r', 'armband_l')
    web = np.sin((tu + tv) * 2 * np.pi / 0.0016) * np.sin((tu - tv) * 2 * np.pi / 0.0016)
    paint(res, st, base=S(0.11, 0.115, 0.125) * (0.9 + 0.16 * web)[:, None], rough=0.62)
    res['height'] = np.where(st, web * 0.00008, res['height'])
    pipe = np.where(st, 0.0, pipe)
    # team accent piping (mask R); underlying paint is a neutral light grey so the Blender preview reads too
    pipe = np.clip(pipe * (1.0 - zipm), 0, 1)
    paint(res, pipe, base=S(0.55, 0.57, 0.60), rough=0.45)
    res['height'] += pipe * 0.00012
    res['mask'][:, 0] = pipe
    # wear / dust in the crevices
    res['base'] = res['base'] * (0.55 + 0.45 * smoothstep(0.05, 0.75, c.ao))[:, None]
    res['rough'] = np.clip(res['rough'] + 0.08 * (grain - 0.5), 0.05, 1.0)
    return res


# ------------------------------------------------------------------------------------------------ armour
def _chevron(u, v, size):
    """Two stacked chevrons pointing up, coordinates in metres around the icon centre. Returns coverage 0..1."""
    out = np.zeros(u.shape)
    w = size * 0.115
    for k in (0.0, -0.34):
        d = np.abs((v - k * size) + np.abs(u) * 0.95 - size * 0.34)
        out = np.maximum(out, line_mask(d * 0.72, w * 2.0, size * 0.02) * (np.abs(u) < size * 0.46))
    return out


def _ring(u, v, size):
    r = np.hypot(u, v)
    return np.maximum(line_mask(np.abs(r - size * 0.36), size * 0.15, size * 0.02), 1.0 - smoothstep(size * 0.10, size * 0.13, r))


# plate decals: region -> list of (kind, u, v, size_m) with u, v in plate parameters
ICONS = {'chest_plate': [(0.27, 0.66, 0.030)], 'back_plate': [(0.50, 0.60, 0.058)], 'pauldron_r': [(0.50, 0.50, 0.040)],
         'tasset_l': [(0.50, 0.52, 0.026)], 'shin_l': [(0.50, 0.80, 0.020)], 'shin_r': [(0.50, 0.80, 0.020)]}
# accent paint bands (mask R): region -> list of (u0, u1, v0, v1)
BANDS = {'chest_plate': [(0.58, 0.86, 0.70, 0.76), (0.58, 0.78, 0.60, 0.645)], 'pauldron_r': [(0.0, 1.0, 0.10, 0.20)],
         'shin_l': [(0.0, 1.0, 0.56, 0.62)], 'shin_r': [(0.0, 1.0, 0.56, 0.62)], 'bracer_l': [(0.0, 1.0, 0.70, 0.80)],
         'knee_l': [(0.36, 0.64, 0.30, 0.40)], 'knee_r': [(0.36, 0.64, 0.30, 0.40)], 'back_plate': [(0.10, 0.34, 0.82, 0.87), (0.66, 0.90, 0.82, 0.87)],
         'ab_plate': [(0.40, 0.60, 0.42, 0.58)], 'armpad_l': [(0.2, 0.8, 0.40, 0.60)], 'gorget': [(0.0, 1.0, 0.44, 0.56)]}
# emissive strips (mask A)
GLOW = {'chest_plate': [(0.60, 0.84, 0.42, 0.455)], 'back_plate': [(0.47, 0.53, 0.12, 0.44)], 'bracer_l': [(0.30, 0.70, 0.30, 0.36)],
        'thighplate_r': [(0.30, 0.70, 0.84, 0.88)]}
DARK_PLATES = ('belt', 'gorget', 'pouch', 'cell_holder', 'armpad_l')


def shade_armor(c):
    P, N = c.P, c.N
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    pu, pv = c.attr('plate_u'), c.attr('plate_v')
    pw, ph = c.attr('plate_w'), c.attr('plate_h')
    rim = c.attr('plate_rim')
    closed = c.attr('plate_closed') > 0.5
    is_plate = pw > 1e-4
    light = S(0.74, 0.75, 0.77)
    dark = S(0.16, 0.17, 0.19)
    trimc = S(0.24, 0.25, 0.275)
    res = new_result(c.n, light, 0.36)
    darkm = c.m(*DARK_PLATES)
    paint(res, darkm.astype(np.float64), base=dark, rough=0.46)
    # distance to the plate border in metres (open plates: both parameters, closed bands: v only)
    du = np.where(closed, 1e3, np.minimum(pu, 1.0 - pu) * pw)
    dv = np.minimum(pv, 1.0 - pv) * ph
    de = np.minimum(du, dv)
    small = (np.minimum(pw, ph) < 0.045)
    inset = np.where(small, 0.0035, 0.0075)
    top = is_plate * (rim < 0.08)
    # two-tone: graphite trim along the border, groove between trim and field
    trim = (1.0 - smoothstep(inset - 0.0004, inset + 0.0004, de)) * top * (1.0 - darkm)
    paint(res, trim, base=trimc, rough=0.48)
    groove = line_mask(np.abs(de - inset), 0.0011, 0.0002) * top
    res['height'] -= groove * 0.00045
    res['base'] = res['base'] * (1.0 - 0.6 * groove)[:, None]
    # team outline: thin line just inside the groove - solid (variant A, mask G) / dashed (variant B, mask B)
    lo = line_mask(np.abs(de - (inset + 0.0032)), 0.0016, 0.0002) * top * (~small) * (1.0 - darkm)
    arc = np.where(du < dv, pv * ph, pu * pw)
    dash = (np.mod(arc, 0.0115) < 0.0068).astype(np.float64)
    res['mask'][:, 1] = lo
    res['mask'][:, 2] = lo * dash
    # panel cut lines across the larger plates
    for regs, cuts in ((('chest_plate',), [('v', 0.52), ('u', 0.5)]), (('back_plate',), [('v', 0.50)]), (('shin_l', 'shin_r'), [('v', 0.50)]),
                       (('pauldron_r',), [('v', 0.62)]), (('thighplate_r',), [('v', 0.70)])):
        mm = c.m(*regs) * top
        for axis, val in cuts:
            d = np.abs(pv - val) * ph if axis == 'v' else np.abs(pu - val) * pw
            cut = line_mask(d, 0.0010, 0.0002) * mm * (de > inset)
            res['height'] -= cut * 0.00040
            res['base'] = res['base'] * (1.0 - 0.55 * cut)[:, None]
    # accent bands, glow strips, icons
    acc = np.zeros(c.n)
    for reg, lst in BANDS.items():
        mm = c.m(reg) * top
        for (u0, u1, v0, v1) in lst:
            acc = np.maximum(acc, mm * (pu >= u0) * (pu <= u1) * (pv >= v0) * (pv <= v1) * (de > inset + 0.0005))
    # hazard chevrons on the thigh plate
    mm = c.m('thighplate_r') * top
    hz = (np.mod((pu * pw + pv * ph) / 0.011, 1.0) < 0.5) * (pv > 0.18) * (pv < 0.36) * (de > inset + 0.001)
    acc = np.maximum(acc, mm * hz)
    glow = np.zeros(c.n)
    for reg, lst in GLOW.items():
        mm = c.m(reg) * top
        for (u0, u1, v0, v1) in lst:
            glow = np.maximum(glow, mm * (pu >= u0) * (pu <= u1) * (pv >= v0) * (pv <= v1))
    ia = np.zeros(c.n)
    ib = np.zeros(c.n)
    for reg, lst in ICONS.items():
        mm = c.m(reg) * top
        sel = mm > 0
        flip = 1.0
        if sel.sum() > 16 and np.corrcoef(pv[sel], z[sel])[0, 1] < -0.2:
            flip = -1.0                                              # plate v runs downwards: keep the icon upright
        for (u0, v0, size) in lst:
            uu, vv = (pu - u0) * pw, (pv - v0) * ph * flip
            ia = np.maximum(ia, _chevron(uu, vv, size) * mm)
            ib = np.maximum(ib, _ring(uu, vv, size) * mm)
    res['mask'][:, 0] = acc
    res['mask'][:, 1] = np.maximum(res['mask'][:, 1], ia)
    res['mask'][:, 2] = np.maximum(res['mask'][:, 2], ib)
    res['mask'][:, 3] = glow
    paint(res, glow, base=S(0.03, 0.035, 0.04), rough=0.2)
    res['height'] -= glow * 0.00025
    # boots: rubber sole, dark shaft, light toe cap and heel counter, accent heel tab
    boot = c.m('boot_l', 'boot_r')
    if boot.any():
        sole = (1.0 - smoothstep(0.018, 0.024, z)) * boot
        toe = (1.0 - smoothstep(-0.150, -0.135, y)) * smoothstep(0.022, 0.028, z) * boot
        shaft = boot * (1.0 - sole) * (1.0 - toe)
        paint(res, shaft, base=dark * 1.25, rough=0.48)
        paint(res, sole, base=S(0.030, 0.030, 0.034), rough=0.72)
        tread = (np.mod(y, 0.012) < 0.004) * sole
        res['height'] -= tread * 0.0006
        cuff = smoothstep(0.0, 1.0, (z - 0.40) / 0.02) * boot
        paint(res, cuff * boot * (z > 0.40), base=trimc, rough=0.5)
        tab = boot * smoothstep(0.55, 0.8, N[:, 1]) * (z > 0.035) * (z < 0.105) * (1.0 - smoothstep(0.016, 0.019, np.abs(np.abs(x) - 0.102)))
        res['mask'][:, 0] = np.maximum(res['mask'][:, 0], tab)
        for zc in (0.115, 0.26):
            g = line_mask(np.abs(z - zc), 0.0016, 0.0003) * boot
            res['height'] -= g * 0.0004
            res['base'] = res['base'] * (1.0 - 0.5 * g)[:, None]
    # belt buckle
    belt = c.m('belt')
    buck = belt * top * (np.abs(x) < 0.020) * smoothstep(0.6, 0.85, -N[:, 1])
    paint(res, buck, base=S(0.50, 0.51, 0.53), rough=0.30, metal=1.0)
    res['mask'][:, 3] = np.maximum(res['mask'][:, 3], buck * (np.abs(x) < 0.0055) * (np.abs(pv - 0.5) < 0.16))
    # pouch: coated fabric
    pm = c.m('pouch')
    tu, tv = triplanar_uv(P, N)
    web = np.sin((tu + tv) * 2 * np.pi / 0.0018) * np.sin((tu - tv) * 2 * np.pi / 0.0018)
    paint(res, pm.astype(np.float64), base=S(0.085, 0.09, 0.095) * (0.9 + 0.14 * web)[:, None], rough=0.60)
    res['height'] += pm * web * 0.00007
    # ---- wear: chipped paint on the bevels and exposed edges, scuffs, grime in the occluded areas
    n_c = fbm(P, 240.0, 4, seed=2)
    n_s = fbm(P * np.array([1.0, 1.0, 0.25]), 420.0, 3, seed=6)
    curv = np.clip(c.v(c.f.curv) / 260.0, 0.0, 1.0)
    edge = np.clip(np.maximum(smoothstep(0.10, 0.50, rim) * (rim < 0.9), curv), 0, 1) * (1.0 - boot)
    chips = smoothstep(0.50, 0.62, n_c + 0.42 * edge - 0.20) * (edge > 0.05)
    paint(res, chips * 0.92, base=S(0.34, 0.34, 0.35), rough=0.30, metal=1.0)
    res['height'] -= chips * 0.00010
    scuff = smoothstep(0.66, 0.80, n_s) * 0.35
    res['rough'] = np.clip(res['rough'] + scuff * 0.25 + 0.06 * (n_c - 0.5), 0.05, 1.0)
    res['base'] = res['base'] * (1.0 - 0.10 * scuff)[:, None]
    grime = (1.0 - smoothstep(0.25, 0.85, c.ao)) * (0.55 + 0.45 * n_c)
    res['base'] = mix(res['base'], res['base'] * S(0.36, 0.33, 0.30), np.clip(grime, 0, 1) * 0.85)
    res['rough'] = np.clip(res['rough'] + grime * 0.2, 0.05, 1.0)
    # accent paint: neutral under-colour (the team colour replaces it in the material)
    a_all = np.clip(res['mask'][:, 0], 0, 1) * (1.0 - chips)
    res['mask'][:, 0] = a_all
    paint(res, a_all, base=S(0.58, 0.60, 0.63), rough=0.34, metal=0.0)
    icon_any = np.clip(np.maximum(res['mask'][:, 1], res['mask'][:, 2]), 0, 1)
    res['mask'][:, 1] *= (1.0 - 0.8 * chips)
    res['mask'][:, 2] *= (1.0 - 0.8 * chips)
    res['height'] += icon_any * 0.00004
    return res


# ------------------------------------------------------------------------------------------------ cybernetics
CYBER_MATS = {
    'gunmetal': (S(0.185, 0.20, 0.23), 0.9, 0.36),
    'titanium': (S(0.42, 0.43, 0.46), 1.0, 0.38),
    'rubber': (S(0.055, 0.055, 0.062), 0.0, 0.58),
    'steel': (S(0.60, 0.61, 0.62), 1.0, 0.24),
    'anodized': (S(0.21, 0.22, 0.245), 1.0, 0.32),
    'glass': (S(0.02, 0.05, 0.06), 0.0, 0.08),
    'ceramic': (S(0.70, 0.71, 0.73), 0.0, 0.34),
}
CYBER_REGIONS = {
    'gunmetal': ['fore_shell_a', 'cuff', 'emitter_housing', 'beacon_body', 'ear_unit', 'blade_housing',
                 'blade_guard', 'cell_collar', 'beacon_dock', 'emitter_fin', 'ear_fin'],
    'titanium': ['fore_shell_b', 'mech_backplate'],
    'rubber': ['fore_core', 'mech_palm', 'cable', 'cell_grip'],
    'steel': ['piston', 'emitter_barrel', 'blade_rail', 'mech_joint', 'wrist_ball', 'cable_port', 'cable_plug', 'beacon_foot', 'beacon_antenna',
              'ear_boom', 'mech_knuckle', 'mech_thumb_mount', 'cell_cap', 'blade'],
    'anodized': ['mech_index', 'mech_middle', 'mech_ring', 'mech_pinky', 'mech_thumb'],
    'glass': ['emitter_lens', 'ear_lens', 'beacon_lens'],
    'ceramic': ['cell_body'],
}


def shade_cyber(c):
    P, N = c.P, c.N
    res = new_result(c.n, CYBER_MATS['gunmetal'][0], CYBER_MATS['gunmetal'][2], CYBER_MATS['gunmetal'][1])
    known = np.zeros(c.n, dtype=bool)
    for mat, regs in CYBER_REGIONS.items():
        m = c.m(*regs)
        col, met, ro = CYBER_MATS[mat]
        res['base'][m] = col
        res['metal'][m] = met
        res['rough'][m] = ro
        known |= m
    n_c = fbm(P, 300.0, 4, seed=12)
    n_f = vnoise(P, 2400.0, seed=14)
    res['rough'] = np.clip(res['rough'] + 0.10 * (n_c - 0.5) + 0.05 * (n_f - 0.5), 0.04, 1.0)
    res['base'] = res['base'] * (0.92 + 0.16 * n_c)[:, None]
    # lenses glow
    lens = c.m('emitter_lens', 'ear_lens', 'beacon_lens')
    res['mask'][:, 3] = lens * 1.0
    # fore-arm: accent band on the cuff, stripe pair along shell A, status segments on the housing
    e, w = J['lowerarm_r'], J['hand_r']
    ax = (w - e) / np.linalg.norm(w - e)
    s = (P - e) @ ax
    L = np.linalg.norm(w - e)
    cuff = c.m('cuff')
    acc = cuff * line_mask(np.abs(s - (s[cuff].mean() if cuff.any() else 0.0)), 0.0070, 0.0004)
    sh = c.m('fore_shell_a')
    if sh.any():
        s0, s1 = s[sh].min(), s[sh].max()
        t = (s - s0) / max(s1 - s0, 1e-6)
        acc = np.maximum(acc, sh * (t > 0.10) * (t < 0.24) * 1.0)
        seg = sh * (t > 0.40) * (t < 0.86) * (np.mod(t, 0.115) < 0.070)
        rad = P - (e + np.outer(s, ax))
        up = np.array([-0.7313537, 0.0, 0.68199836])                 # dorsal direction of the right fore-arm (emitter side)
        lat = np.cross(ax, up)
        res['mask'][:, 3] = np.maximum(res['mask'][:, 3], seg * (np.abs(rad @ lat) < 0.0032) * ((rad @ up) > 0))
    hs = c.m('emitter_housing')
    if hs.any():
        s0, s1 = s[hs].min(), s[hs].max()
        t = (s - s0) / max(s1 - s0, 1e-6)
        acc = np.maximum(acc, hs * (t > 0.08) * (t < 0.20) * 1.0)
    # power cell: hazard band + charge window
    cb = c.m('cell_body')
    if cb.any():
        bn = skel.bone_matrix('prop_cell')
        loc = (P - bn[:3, 3]) @ bn[:3, :3]
        yb = loc[:, 1]
        y0, y1 = yb[cb].min(), yb[cb].max()
        t = (yb - y0) / max(y1 - y0, 1e-6)
        sp = skel.bone_matrix('prop_cell_spare')
        loc2 = (P - sp[:3, 3]) @ sp[:3, :3]
        t2 = (loc2[:, 1] - y0) / max(y1 - y0, 1e-6)
        near_spare = np.linalg.norm(P - sp[:3, 3], axis=1) < np.linalg.norm(P - bn[:3, 3], axis=1)
        tt = np.where(near_spare, t2, t)
        ll = np.where(near_spare[:, None], loc2, loc)
        hz = cb * (tt > 0.58) * (tt < 0.80) * (np.mod((ll[:, 0] + ll[:, 2] + ll[:, 1]) / 0.006, 1.0) < 0.5)
        paint(res, hz.astype(np.float64), base=S(0.07, 0.07, 0.08), rough=0.4)
        res['mask'][:, 3] = np.maximum(res['mask'][:, 3], cb * (tt > 0.30) * (tt < 0.42))
        acc = np.maximum(acc, cb * (tt > 0.86) * 1.0)
    # blade: energy channel along the flat faces
    bl = c.m('blade')
    if bl.any():
        bm = skel.bone_matrix('blade_l')
        loc = (P - bm[:3, 3]) @ bm[:3, :3]
        ext = [(loc[bl][:, k].max() - loc[bl][:, k].min()) for k in (0, 2)]
        lat_axis = 0 if ext[0] > ext[1] else 2
        lat = loc[:, lat_axis] - 0.5 * (loc[bl][:, lat_axis].max() + loc[bl][:, lat_axis].min())
        res['mask'][:, 3] = np.maximum(res['mask'][:, 3], bl * line_mask(np.abs(lat), 0.0030, 0.0005) * 0.9)
        res['rough'][bl] = 0.14
    # beacon: accent ring, ear units: accent ring
    for reg in ('beacon_body', 'ear_unit'):
        mm = c.m(reg)
        if mm.any():
            zz = P[:, 2]
            if reg == 'beacon_body':
                bm = skel.bone_matrix('prop_beacon')
                h = (P - bm[:3, 3]) @ bm[:3, 1]
                h0, h1 = h[mm].min(), h[mm].max()
                t = (h - h0) / max(h1 - h0, 1e-6)
                acc = np.maximum(acc, mm * (t > 0.50) * (t < 0.66) * 1.0)
            else:
                r = np.hypot(P[:, 1] - 0.012, zz - 1.655)
                acc = np.maximum(acc, mm * line_mask(np.abs(r - 0.0235), 0.0030, 0.0004) * smoothstep(0.5, 0.8, np.abs(N[:, 0])))
    # cable: ribbed rubber
    cab = c.m('cable')
    if cab.any():
        d = np.linalg.norm(P - J['cable_01'], axis=1)
        ribs = np.sin(d * 2 * np.pi / 0.0048)
        res['height'] += cab * ribs * 0.00030
        res['base'] = res['base'] * np.where(cab, 0.85 + 0.2 * ribs, 1.0)[:, None]
    # mechanical fingers: lighter tips, grip pads
    for fn in ('index', 'middle', 'ring', 'pinky', 'thumb'):
        mm = c.m('mech_' + fn)
        if mm.any():
            je = J[fn + '_end_r']
            tipd = np.linalg.norm(P - je, axis=1)
            paint(res, mm * (1.0 - smoothstep(0.008, 0.011, tipd)), base=CYBER_MATS['steel'][0], rough=0.3, metal=1.0)
    # wear: bright edges, dirt in recesses
    curv = np.clip(c.v(c.f.curv) / 300.0, 0.0, 1.0)
    wear = smoothstep(0.62, 0.80, n_c * 0.55 + curv * 0.55) * (1.0 - lens) * (1.0 - c.m('fore_core', 'mech_palm', 'cable', 'cell_grip'))
    paint(res, wear * 0.70, base=S(0.50, 0.51, 0.52), rough=0.24, metal=1.0)
    grime = (1.0 - smoothstep(0.2, 0.8, c.ao)) * (0.5 + 0.5 * n_c)
    res['base'] = res['base'] * (1.0 - 0.55 * np.clip(grime, 0, 1))[:, None]
    res['rough'] = np.clip(res['rough'] + grime * 0.25, 0.04, 1.0)
    acc = np.clip(acc, 0, 1) * (1.0 - wear)
    res['mask'][:, 0] = acc
    paint(res, acc, base=S(0.58, 0.60, 0.63), rough=0.34, metal=0.0)
    paint(res, np.clip(res['mask'][:, 3], 0, 1), base=S(0.02, 0.03, 0.035), rough=0.12, metal=0.0)
    res['height'] += (n_f - 0.5) * 0.00003
    return res


SHADERS = {'M_Skin': shade_skin, 'M_EyesMouth': shade_eyesmouth, 'M_Hair': shade_hair, 'M_Suit': shade_suit, 'M_Armor': shade_armor,
           'M_Cyber': shade_cyber}
AO_IN_ALBEDO = {'M_Skin': 0.0, 'M_EyesMouth': 0.0, 'M_Hair': 0.30, 'M_Suit': 0.0, 'M_Armor': 0.30, 'M_Cyber': 0.30}


# ------------------------------------------------------------------------------------------------ AO bake (Cycles)
def bake_ao(ob, sizes, samples=48, distance=0.30, log=print):
    """Ambient occlusion of the rest mesh per material slot -> {slot: (size, size) float array, row 0 = v 0}."""
    import bpy
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type == 'OPTIX')
        sc.cycles.device = 'GPU' if any(d.use for d in prefs.devices) else 'CPU'
    except Exception as e:                                           # CPU fallback
        log('AO bake on CPU (%s)' % e)
        sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    if sc.world is None:
        sc.world = bpy.data.worlds.new('World')
    sc.world.light_settings.distance = distance
    sc.render.bake.margin = 6
    sc.render.bake.use_selected_to_active = False
    sc.render.bake.use_clear = True
    made = []
    for slot in ob.material_slots:
        mat = slot.material
        mat.use_nodes = True
        nt = mat.node_tree
        size = sizes[mat.name]
        img = bpy.data.images.new('AO_' + mat.name, size, size, alpha=False, float_buffer=True)
        img.colorspace_settings.name = 'Non-Color'
        node = nt.nodes.new('ShaderNodeTexImage')
        node.image = img
        for n in nt.nodes:
            n.select = False
        node.select = True
        nt.nodes.active = node
        made.append((mat, node, img))
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    keys = ob.data.shape_keys
    show = ob.show_only_shape_key
    t0 = time.time()
    bpy.ops.object.bake(type='AO')
    out = {}
    for mat, node, img in made:
        size = img.size[0]
        px = np.empty(size * size * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        out[mat.name] = px.reshape(size, size, 4)[:, :, 0].astype(np.float64)
        mat.node_tree.nodes.remove(node)
        bpy.data.images.remove(img)
    sc.render.engine = prev_engine
    log('AO baked in %.1f s (%s)' % (time.time() - t0, sc.cycles.device))
    return out


# ------------------------------------------------------------------------------------------------ driver
def _down(img, div):
    if div == 1:
        return img
    h, w = img.shape[0] // div, img.shape[1] // div
    return img[:h * div, :w * div].reshape(h, div, w, div, -1).mean(axis=(1, 3))


def generate(ob, out_dirs, scale=1.0, only=None, ao=True, log=print):
    """Paint and write all texture sets. out_dirs: list of directories that receive identical copies.
    scale < 1 renders smaller maps (previews). Returns the texture manifest dict."""
    me = ob.data
    ma = MeshArrays(me)
    fields = Fields(ma)
    sizes = {k: max(64, int(v * scale)) for k, v in SIZES.items()}
    ao_maps = {}
    if ao:
        ao_sizes = {k: min(v, 2048) for k, v in sizes.items()}
        ao_maps = bake_ao(ob, ao_sizes, log=log)
    for d in out_dirs:
        os.makedirs(d, exist_ok=True)
    mats = []
    for mi, name in enumerate(ma.materials):
        if only and name not in only:
            continue
        t0 = time.time()
        size = sizes[name]
        r = Raster(ma, mi, size)
        aot = None
        if name in ao_maps:
            a = ao_maps[name]
            rep = size // a.shape[0]
            if rep > 1:
                a = np.repeat(np.repeat(a, rep, axis=0), rep, axis=1)
            aot = a[r.yx]
        c = Ctx(ma, fields, r, aot)
        res = SHADERS[name](c)
        ao_out = res['ao'] if res['ao'] is not None else np.clip(c.ao, 0.0, 1.0)
        base = np.clip(res['base'], 0.0, 1.0)
        k = AO_IN_ALBEDO.get(name, 0.0)
        if k > 0:
            base = base * (1.0 - k + k * np.clip(ao_out, 0, 1))[:, None]
        nrm = r.normal_from_height(res['height'])
        slot = name[2:]
        div = AUX_DIV.get(name, 1) if scale >= 1.0 else 1
        files = dict(base_color='T_%s_BaseColor.png' % slot, normal='T_%s_Normal.png' % slot, orm='T_%s_ORM.png' % slot, mask=None, emissive=None)
        img_base = r.dilate(r.image(linear_to_srgb(base), fill=0.5), 16)
        img_n = _down(r.dilate(r.image(nrm * 0.5 + 0.5, fill=0.5), 16), div)
        orm = np.stack([np.clip(ao_out, 0, 1), np.clip(res['rough'], 0.02, 1.0), np.clip(res['metal'], 0, 1)], axis=1)
        img_orm = _down(r.dilate(r.image(orm, fill=0.5), 16), div)
        img_mask = None
        if name in HAS_MASK:
            files['mask'] = 'T_%s_Mask.png' % slot
            img_mask = r.dilate(r.image(np.clip(res['mask'], 0, 1), fill=0.0), 8)
        for d in out_dirs:
            write_png(os.path.join(d, files['base_color']), img_base)
            write_png(os.path.join(d, files['normal']), img_n)
            write_png(os.path.join(d, files['orm']), img_orm)
            if img_mask is not None:
                write_png(os.path.join(d, files['mask']), img_mask)
        mats.append(dict(slot=name, shading=SHADING[name], size=size, aux_size=size // div, coverage=round(float(r.mask.mean()), 3),
                         texel_mm_median=round(float(np.median(r.texel_size())) * 1000, 3), **files))
        log('TEX %-12s %4d px  %5.1f s  coverage %.2f' % (name, size, time.time() - t0, r.mask.mean()))
    doc = dict(schema='morphrig.textures/1', max_dimension=max(sizes.values()), materials=mats,
               packing=dict(base_color='sRGB', normal='tangent space, OpenGL (+Y) convention; flip green in Unreal',
                            orm='linear: R = ambient occlusion, G = roughness, B = metallic',
                            mask='linear: R = team accent paint area, G = team icon A (chevron) + solid trim line, '
                                 'B = team icon B (ring) + dashed trim line, A = emissive accent weight'),
               team_variants=dict(A=dict(name='Team A / cyan chevron', color_linear=[0.0, 0.62, 1.0], icon_channel='G', outline_style='solid'),
                                  B=dict(name='Team B / amber ring', color_linear=[1.0, 0.36, 0.02], icon_channel='B', outline_style='dashed')),
               generator='source/generators/mr/texgen.py (procedural, painted in UV space from the rest mesh; AO baked with Cycles)')
    if not only:
        for d in out_dirs:
            with open(os.path.join(d, 'texture_manifest.json'), 'w') as f:
                json.dump(doc, f, indent=1)
    return doc

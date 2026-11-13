"""Facial morph targets generated as displacement fields over the head skin (rest space).

Each target is a smooth field of the rest position plus the lip membership of a vertex (upper / lower),
so coincident contact-line vertices of the two lips move apart or seal correctly.
"""
import math
import numpy as np
from . import head as H
from . import facedefs

MW = H.MOUTH_W
MZ = H.MOUTH_Z


def _g(d, s):
    return np.exp(-(d / s) ** 2)


def _dist(P, c):
    return np.linalg.norm(P - np.asarray(c), axis=1)


class FaceFields:
    def __init__(self, md, info):
        self.P = md.P()
        n = len(self.P)
        P = self.P
        self.n = n
        updown = np.sign(P[:, 2] - MZ)
        lidmask = np.zeros(n)
        h = H.NM // 2
        rings = list(info['mouth_rings']) + list(info['bag_rings'])
        for ring in rings:
            for k, vi in enumerate(ring):
                updown[vi] = 0.0 if k in (0, h) else (1.0 if k < h else -1.0)
        for s in ('l', 'r'):
            for lvl, ring in enumerate(info['eye_rings_' + s]):
                for vi in ring:
                    lidmask[vi] = [0.0, 0.0, 0.55, 1.0, 1.0, 1.0][lvl]
        self.updown = updown
        self.lidmask = lidmask
        self.front = 1.0 - np.clip((P[:, 1] + 0.055) / 0.035, 0.0, 1.0)      # 1 on the face, 0 behind the cheeks
        self.dz = P[:, 2] - MZ
        self.u = P[:, 0] / MW
        self.a = np.abs(self.u)
        self.wx = np.where(self.a < 1.0, (1.0 - np.minimum(self.a, 1.0) ** 2.5), 0.0)
        self.up = (updown > 0).astype(float)
        self.lo = (updown < 0).astype(float)
        yc = float(np.array(md.v[info['mouth_rings'][4][0]])[1])
        self.corner = np.array([MW, yc, MZ])
        # depth attenuation for the inner mouth so the cavity follows the lips without collapsing
        ylip = P[:, 1].copy()
        self.inner = np.ones(n)
        for i, ring in enumerate(info['bag_rings']):
            for vi in ring:
                self.inner[vi] = [0.55, 0.22, 0.08, 0.0][min(i, 3)]

    # ---- helpers
    def zero(self):
        return np.zeros((self.n, 3))

    def side_l(self):
        return np.clip(0.5 + self.P[:, 0] / 0.012, 0.0, 1.0)

    # ---- individual targets (left side versions where mirrored)
    def smile_l(self):
        P = self.P
        d = self.zero()
        gc = _g(_dist(P, self.corner), 0.020)
        d += gc[:, None] * np.array([0.0075, 0.0040, 0.0085])
        along = np.clip(self.u, 0, 1) ** 1.3 * _g(self.dz, 0.013)
        d[:, 0] += along * 0.0045
        d[:, 1] += along * 0.0030 * np.clip(self.u, 0, 1)
        d[:, 2] += along * 0.0050 * np.clip(self.u, 0, 1) ** 2
        gch = _g(_dist(P, (0.040, -0.075, 1.628)), 0.022)
        d += gch[:, None] * np.array([0.0020, -0.0015, 0.0045])
        return d * self.inner[:, None]

    def frown_l(self):
        P = self.P
        d = self.zero()
        gc = _g(_dist(P, self.corner), 0.019)
        d += gc[:, None] * np.array([0.0020, 0.0015, -0.0078])
        along = np.clip(self.u, 0, 1) ** 1.3 * _g(self.dz, 0.013)
        d[:, 2] += -along * 0.0045 * np.clip(self.u, 0, 1) ** 2
        d[:, 0] += along * 0.0010
        return d * self.inner[:, None]

    def mouth_wide_l(self):
        P = self.P
        d = self.zero()
        gc = _g(_dist(P, self.corner), 0.021)
        d += gc[:, None] * np.array([0.0088, 0.0060, 0.0004])
        along = np.clip(self.u, 0, 1) * _g(self.dz, 0.013)
        d[:, 0] += along * 0.0050
        d[:, 1] += along * 0.0030 * np.clip(self.u, 0, 1)
        d[:, 2] += -self.updown * along * 0.0009
        return d * self.inner[:, None]

    def upper_lip_up_l(self):
        d = self.zero()
        wxs = _g(self.u - 0.42, 0.42) * np.where(self.a < 1.15, 1.0, 0.0)
        k = self.up * _g(self.dz, 0.014) * wxs
        d[:, 2] += 0.0052 * k
        d[:, 1] += -0.0012 * k
        return d * self.inner[:, None]

    def lower_lip_down_l(self):
        d = self.zero()
        wxs = _g(self.u - 0.42, 0.42) * np.where(self.a < 1.15, 1.0, 0.0)
        k = self.lo * _g(self.dz, 0.014) * wxs
        d[:, 2] += -0.0056 * k
        d[:, 1] += -0.0015 * k
        return d * self.inner[:, None]

    def pucker(self):
        P = self.P
        d = self.zero()
        rm = np.sqrt((P[:, 0] / 0.030) ** 2 + (self.dz / 0.020) ** 2)
        G = np.exp(-rm ** 2) * self.front
        d[:, 0] += -P[:, 0] * 0.62 * G
        d[:, 1] += -0.0062 * G * (1 - 0.3 * np.minimum(self.a, 1.0))
        d[:, 2] += self.updown * 0.0018 * _g(np.abs(self.dz) - 0.008, 0.006) * (1 - np.minimum(self.a, 1.0) ** 2) * self.front
        return d * np.maximum(self.inner, 0.35)[:, None]

    def funnel(self):
        P = self.P
        d = self.zero()
        rm = np.sqrt((P[:, 0] / 0.030) ** 2 + (self.dz / 0.020) ** 2)
        G = np.exp(-rm ** 2) * self.front
        d[:, 0] += -P[:, 0] * 0.40 * G
        d[:, 1] += -0.0078 * G
        part = _g(self.dz, 0.011) * (1 - np.minimum(self.a, 1.0) ** 2) * self.front
        d[:, 2] += self.up * 0.0040 * part - self.lo * 0.0056 * part
        return d * np.maximum(self.inner, 0.35)[:, None]

    def lip_press(self):
        d = self.zero()
        k = _g(self.dz, 0.004) * self.wx
        d[:, 2] += (-self.up * 0.0013 + self.lo * 0.0013) * k
        thin = _g(self.dz, 0.012) * self.wx
        d[:, 2] += -self.updown * 0.35 * np.abs(self.dz) * thin
        d[:, 1] += 0.0012 * _g(self.dz, 0.010) * self.wx
        return d * self.inner[:, None]

    def mouth_close(self):
        d = self.zero()
        below = np.clip(-self.dz, 0, None)
        above = np.clip(self.dz, 0, None)
        d[:, 2] += self.lo * 0.0080 * _g(below, 0.014) * self.wx
        d[:, 1] += self.lo * -0.0020 * _g(below, 0.012) * self.wx
        d[:, 2] += -self.up * 0.0026 * _g(above, 0.010) * self.wx
        return d * np.maximum(self.inner, 0.5)[:, None]

    def lip_roll_upper(self):
        d = self.zero()
        d[:, 1] += self.up * 0.0042 * _g(self.dz, 0.008) * self.wx
        d[:, 2] += -self.up * 0.0022 * _g(self.dz - 0.006, 0.006) * self.wx
        return d * self.inner[:, None]

    def lip_roll_lower(self):
        d = self.zero()
        d[:, 1] += self.lo * 0.0042 * _g(self.dz, 0.008) * self.wx
        d[:, 2] += self.lo * 0.0022 * _g(-self.dz - 0.006, 0.006) * self.wx
        return d * self.inner[:, None]

    def labiodental(self):
        d = self.zero()
        d[:, 1] += self.lo * 0.0058 * _g(self.dz, 0.009) * self.wx ** 0.5
        d[:, 2] += self.lo * 0.0036 * _g(self.dz, 0.010) * self.wx
        d[:, 2] += self.up * 0.0015 * _g(self.dz, 0.008) * self.wx
        return d * self.inner[:, None]

    def chin_raise(self):
        P = self.P
        d = self.zero()
        g = _g(_dist(P, (0.0, -0.098, MZ - 0.0235)), 0.016)
        d[:, 2] += 0.0042 * g
        d[:, 1] += -0.0010 * g
        k = self.lo * _g(self.dz, 0.010) * self.wx
        d[:, 2] += 0.0026 * k
        d[:, 1] += -0.0015 * k
        return d * self.inner[:, None]

    def cheek_puff_l(self):
        P = self.P
        g = _g(_dist(P, (0.046, -0.058, 1.612)), 0.024)
        dirv = np.stack([P[:, 0], P[:, 1] + 0.03, np.zeros(self.n)], axis=1)
        dirv /= np.maximum(np.linalg.norm(dirv, axis=1, keepdims=True), 1e-9)
        return dirv * (0.0085 * g)[:, None]

    def cheek_raise_l(self):
        P = self.P
        d = self.zero()
        g = _g(_dist(P, (0.037, -0.080, 1.642)), 0.019)
        d += g[:, None] * np.array([0.0005, -0.0018, 0.0052])
        g2 = _g(_dist(P, (0.033, -0.088, 1.661)), 0.012) * (1 - self.lidmask)
        d[:, 2] += 0.0018 * g2
        return d

    def squint_l(self):
        P = self.P
        d = self.zero()
        g2 = _g(_dist(P, (0.033, -0.088, 1.661)), 0.012) * (1 - self.lidmask)
        d += g2[:, None] * np.array([0.0, -0.0005, 0.0022])
        g3 = _g(_dist(P, (0.050, -0.076, 1.672)), 0.010) * (1 - self.lidmask)
        d[:, 0] += -0.0012 * g3
        g4 = _g(_dist(P, (0.036, -0.090, 1.692)), 0.014) * (1 - self.lidmask)
        d[:, 2] += -0.0015 * g4
        return d

    def nose_sneer_l(self):
        P = self.P
        d = self.zero()
        g = _g(_dist(P, (0.0125, -0.101, 1.632)), 0.011)
        d += g[:, None] * np.array([0.0008, -0.0005, 0.0042])
        gn = _g(_dist(P, (0.022, -0.092, 1.624)), 0.012)
        d += gn[:, None] * np.array([0.0, -0.0010, 0.0030])
        k = self.up * _g(self.dz, 0.012) * _g(self.u - 0.5, 0.35)
        d[:, 2] += 0.0022 * k
        return d * self.inner[:, None]

    def _brow(self, cx, sx, cz, amount_z, dx=0.0, dy=0.0, inner_emph=None):
        P = self.P
        gx = _g(P[:, 0] - cx, sx)
        dzb = P[:, 2] - cz
        gz = np.where(dzb > 0, _g(dzb, 0.030), _g(dzb, 0.012))
        g = gx * gz * self.front * (1 - self.lidmask)
        d = self.zero()
        d[:, 2] += amount_z * g
        d[:, 1] += dy * g
        if dx:
            e = _g(P[:, 0] - inner_emph[0], inner_emph[1]) if inner_emph else 1.0
            d[:, 0] += dx * g * e
        return d

    def brow_inner_up_l(self):
        return self._brow(0.015, 0.013, 1.6965, 0.0065, dy=-0.0008)

    def brow_outer_up_l(self):
        return self._brow(0.041, 0.014, 1.6990, 0.0065, dy=-0.0006)

    def brow_down_l(self):
        return self._brow(0.026, 0.022, 1.6950, -0.0046, dx=-0.0032, dy=-0.0010, inner_emph=(0.014, 0.014))


def build_face_shapes(md, info):
    """Returns {morph name: (n,3) delta array} for the head skin MeshData."""
    ff = FaceFields(md, info)
    # mirrored evaluator for the right side
    md_m_P = ff.P * np.array([-1.0, 1.0, 1.0])

    class Mir(FaceFields):
        pass

    mir = FaceFields.__new__(FaceFields)
    mir.__dict__.update(ff.__dict__)
    mir.P = md_m_P
    mir.u = mir.P[:, 0] / MW
    mir.a = np.abs(mir.u)
    out = {}
    for name in facedefs.MORPHS:
        if name.endswith('_l') or name.endswith('_r'):
            base = name[:-2] + '_l'
            fn = getattr(ff, base)
            if name.endswith('_l'):
                d = fn() * ff.side_mask(base) if hasattr(ff, 'side_mask') else fn()
            else:
                d = getattr(mir, base)() * np.array([-1.0, 1.0, 1.0])
        else:
            d = getattr(ff, name)()
        d[np.abs(d) < 1e-6] = 0.0
        out[name] = d
    return out


def apply_shape_keys(ob, shapes):
    import bpy
    if ob.data.shape_keys is None:
        ob.shape_key_add(name='Basis')
    n = len(ob.data.vertices)
    base = np.empty(n * 3)
    ob.data.vertices.foreach_get('co', base)
    for name, d in shapes.items():
        kb = ob.shape_key_add(name=name)
        kb.data.foreach_set('co', (base + d.reshape(-1)).astype(np.float32))
        kb.slider_min = 0.0
        kb.slider_max = 1.0
        kb.value = 0.0                    # new keys default to 1.0 in current Blender versions
    ob.data.update()

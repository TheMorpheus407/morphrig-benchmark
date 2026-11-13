"""Body surface (fitted suit + exposed skin arm) built as one connected quad mesh.

Topology: torso grid (NT columns) with arm holes and a V shaped hip line, leg tubes (NL) continuing the
hip line plus a crotch strip, arm tubes (NA) continuing the arm-hole loops. All loops are edge loops
placed deliberately around hips, knees, shoulders, elbows and wrists.
"""
import math
import numpy as np
from .util import (V, norm, lerp, smoothstep, bump, gauss, ang_gauss, table, Pchip, superellipse_r,
                   resample_open, frame_from, TAU)
from . import skel
from .skel import J, mirror_name
from .meshkit import MeshData
from . import hand as handmod

NT = 40   # torso columns (multiple of 4)
NA = 20   # arm ring size (arm hole = 4 columns x 6 rows)
NL = 24   # leg ring size (NT/2 + 4 crotch edges)

SUIT = 'M_Suit'
SKIN = 'M_Skin'

# ---------------------------------------------------------------------------------- torso sections
TORSO = table([
    (0.860, dict(cy=0.006, a=0.180, df=0.090, db=0.112, n=2.25)),
    (0.900, dict(cy=0.006, a=0.187, df=0.097, db=0.121, n=2.25)),
    (0.940, dict(cy=0.006, a=0.190, df=0.100, db=0.126, n=2.25)),
    (0.985, dict(cy=0.006, a=0.178, df=0.099, db=0.117, n=2.25)),
    (1.040, dict(cy=0.006, a=0.160, df=0.094, db=0.099, n=2.20)),
    (1.100, dict(cy=0.008, a=0.133, df=0.087, db=0.084, n=2.15)),
    (1.160, dict(cy=0.010, a=0.136, df=0.090, db=0.085, n=2.15)),
    (1.220, dict(cy=0.012, a=0.150, df=0.100, db=0.092, n=2.20)),
    (1.280, dict(cy=0.014, a=0.160, df=0.111, db=0.099, n=2.25)),
    (1.335, dict(cy=0.016, a=0.167, df=0.119, db=0.104, n=2.30)),
    (1.385, dict(cy=0.018, a=0.167, df=0.113, db=0.107, n=2.30)),
    (1.430, dict(cy=0.018, a=0.172, df=0.097, db=0.105, n=2.35)),
    (1.474, dict(cy=0.018, a=0.183, df=0.080, db=0.098, n=2.45)),
])

# rows: (z at the side, z at front centre, z at back centre)
ROWS = [
    (0.980, 0.878, 0.872), (1.000, 0.917, 0.912), (1.020, 0.955, 0.951), (1.040, 0.991, 0.988),
    (1.062, 1.026, 1.024), (1.085, 1.061, 1.060), (1.110, 1.096, 1.096),
    (1.135, 1.135, 1.135), (1.165, 1.165, 1.165), (1.195, 1.195, 1.195), (1.225, 1.225, 1.225),
    (1.255, 1.255, 1.255), (1.285, 1.285, 1.285), (1.315, 1.315, 1.315), (1.345, 1.345, 1.345),
    (1.375, 1.375, 1.375),                                   # row 15 = B (arm pit)
    (1.392, 1.389, 1.391), (1.409, 1.402, 1.406), (1.426, 1.414, 1.421),
    (1.443, 1.425, 1.435), (1.459, 1.434, 1.447),
    (1.474, 1.442, 1.458),                                   # row 21 = T (shoulder top)
]
ROW_B, ROW_T = 15, 21
COL_SIDE = NT // 4          # 10
HOLE_C0, HOLE_C1 = COL_SIDE - 2, COL_SIDE + 2

NECK = dict(cy=0.014, rx=0.0615, rf=0.060, rb=0.062, zf=1.468, zs=1.516, zb=1.512)
YOKE_S = [0.30, 0.58, 0.82]
COLLAR = [  # (dz above neck ring, radius scale, y shift)
    (0.016, 0.960, -0.002), (0.032, 0.935, -0.004), (0.046, 0.925, -0.007)]


def _torso_feature(t, z):
    """Multiplicative radial shaping of a torso section. t = param angle (0 front, pi/2 left)."""
    f = np.ones_like(t)
    # bust (soft, athletic)
    f += 0.085 * (ang_gauss(t, 0.42, 0.26) + ang_gauss(t, -0.42, 0.26)) * gauss(z, 1.322, 0.040)
    # sternum channel
    f -= 0.012 * ang_gauss(t, 0.0, 0.10) * gauss(z, 1.33, 0.05)
    # glutes
    f += 0.070 * (ang_gauss(t, math.pi - 0.50, 0.30) + ang_gauss(t, math.pi + 0.50, 0.30)) * gauss(z, 0.935, 0.055)
    f -= 0.030 * ang_gauss(t, math.pi, 0.08) * gauss(z, 0.92, 0.06)
    # spine furrow and shoulder blades
    f -= 0.016 * ang_gauss(t, math.pi, 0.09) * smoothstep(1.02, 1.12, z) * (1 - smoothstep(1.38, 1.46, z))
    f += 0.022 * (ang_gauss(t, math.pi - 0.52, 0.24) + ang_gauss(t, math.pi + 0.52, 0.24)) * gauss(z, 1.375, 0.045)
    # lower belly / abdominal plane
    f += 0.010 * ang_gauss(t, 0.0, 0.5) * gauss(z, 1.03, 0.05)
    # obliques pinch at waist sides
    f -= 0.012 * (ang_gauss(t, math.pi / 2, 0.3) + ang_gauss(t, -math.pi / 2, 0.3)) * gauss(z, 1.12, 0.05)
    return f


def torso_point(t, z):
    """Surface point for param angle t (array) at heights z (array)."""
    t = np.asarray(t, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64) * np.ones_like(t)
    a = TORSO['a'](z)
    df = TORSO['df'](z)
    db = TORSO['db'](z)
    n = TORSO['n'](z)
    cy = TORSO['cy'](z)
    s, c = np.sin(t), np.cos(t)
    e = 2.0 / n
    x = a * np.sign(s) * np.abs(s) ** e
    d = np.where(c > 0, df, db)
    y = -d * np.sign(c) * np.abs(c) ** e
    f = _torso_feature(t, z)
    return np.stack([x * f, cy + y * f, z], axis=1)


def _row_z(t, zs, zf, zb):
    s = np.abs(np.sin(t)) ** 1.5
    return np.where(np.cos(t) > 0, zf + (zs - zf) * s, zb + (zs - zb) * s)


def torso_row(k):
    """NT points of row k, equal arc length per quadrant, column 0 = front centre, NT/4 = left side."""
    zs, zf, zb = ROWS[k]
    q = NT // 4
    out = []
    for quad in range(4):
        t = np.linspace(quad * math.pi / 2, (quad + 1) * math.pi / 2, 65)
        pts = torso_point(t, _row_z(t, zs, zf, zb))
        rs = resample_open(pts, q + 1)
        out.extend(rs[:-1])
    return np.array(out)


def neck_ring():
    q = NT // 4
    out = []
    for quad in range(4):
        t = np.linspace(quad * math.pi / 2, (quad + 1) * math.pi / 2, 33)
        s, c = np.sin(t), np.cos(t)
        d = np.where(c > 0, NECK['rf'], NECK['rb'])
        z = _row_z(t, NECK['zs'], NECK['zf'], NECK['zb'])
        pts = np.stack([NECK['rx'] * s, NECK['cy'] - d * c, z], axis=1)
        out.extend(resample_open(pts, q + 1)[:-1])
    return np.array(out)


# ---------------------------------------------------------------------------------- limb sections
ARM = table([
    # s: distance from shoulder joint along the arm.  lat/med = away from / toward the body, f/b = front/back
    (-0.020, dict(lat=0.047, med=0.040, f=0.049, b=0.050)),
    (0.040, dict(lat=0.049, med=0.041, f=0.050, b=0.051)),
    (0.100, dict(lat=0.046, med=0.040, f=0.047, b=0.048)),
    (0.180, dict(lat=0.039, med=0.037, f=0.042, b=0.041)),
    (0.250, dict(lat=0.035, med=0.034, f=0.037, b=0.038)),
    (0.283, dict(lat=0.035, med=0.035, f=0.034, b=0.040)),
    (0.330, dict(lat=0.038, med=0.036, f=0.042, b=0.037)),
    (0.420, dict(lat=0.031, med=0.029, f=0.033, b=0.030)),
    (0.490, dict(lat=0.023, med=0.022, f=0.028, b=0.027)),
    (0.535, dict(lat=0.0185, med=0.0185, f=0.0275, b=0.0265)),
])
L_UP, L_LO = skel.L_UPPER, skel.L_LOWER
S_WRIST = L_UP + L_LO

ARM_FAN = [(-0.004, 0.050), (0.022, 0.060), (0.048, 0.072), (0.072, 0.086)]
ARM_S = [0.100, 0.125, 0.150, 0.175, 0.200, 0.222, 0.242, 0.258, 0.271, 0.283, 0.295, 0.308, 0.324,
         0.345, 0.370, 0.395, 0.420, 0.445, 0.470, 0.492, 0.512, 0.527, S_WRIST]
HEM_RING = 3   # sleeveless hem of the left arm follows fan ring 3

LEG = table([
    # s: distance from hip joint along the leg.  a = lateral half width, f/b = front/back, cx/cy centre offsets
    (-0.030, dict(a=0.094, f=0.097, b=0.112, ox=0.004, oy=0.006)),
    (0.055, dict(a=0.092, f=0.096, b=0.108, ox=0.004, oy=0.004)),
    (0.155, dict(a=0.085, f=0.093, b=0.091, ox=0.003, oy=0.000)),
    (0.255, dict(a=0.074, f=0.084, b=0.078, ox=0.001, oy=-0.002)),
    (0.355, dict(a=0.060, f=0.067, b=0.064, ox=0.000, oy=0.000)),
    (0.410, dict(a=0.052, f=0.058, b=0.056, ox=0.000, oy=0.002)),
    (0.4376, dict(a=0.052, f=0.060, b=0.055, ox=0.000, oy=0.002)),
    (0.486, dict(a=0.050, f=0.050, b=0.059, ox=0.000, oy=0.004)),
    (0.556, dict(a=0.054, f=0.044, b=0.071, ox=0.001, oy=0.006)),
    (0.656, dict(a=0.045, f=0.040, b=0.057, ox=0.000, oy=0.004)),
    (0.757, dict(a=0.036, f=0.037, b=0.043, ox=0.000, oy=0.002)),
    (0.859, dict(a=0.034, f=0.038, b=0.040, ox=0.000, oy=0.000)),
])
L_TH = float(np.linalg.norm(J['calf_l'] - J['thigh_l']))
L_CA = float(np.linalg.norm(J['foot_l'] - J['calf_l']))
LEG_FAN = [None, (0.010, 0.108), (0.045, 0.125), (0.080, 0.143), (0.113, 0.160), (0.145, 0.178)]
LEG_S = [0.195, 0.225, 0.255, 0.285, 0.315, 0.345, 0.372, 0.395, 0.412, 0.425, L_TH, 0.450, 0.463, 0.480,
         0.502, 0.530, 0.560, 0.590, 0.620, 0.655, 0.690, 0.725]


class Limb:
    """Smooth two-segment axis with interpolated frames."""

    def __init__(self, p0, p1, p2, zhint, blend=0.03):
        self.p0, self.p1, self.p2 = [np.array(p, float) for p in (p0, p1, p2)]
        self.l1 = float(np.linalg.norm(self.p1 - self.p0))
        self.l2 = float(np.linalg.norm(self.p2 - self.p1))
        self.f1 = frame_from(self.p1 - self.p0, zhint)
        self.f2 = frame_from(self.p2 - self.p1, zhint)
        self.blend = blend

    def frame(self, s):
        w = float(smoothstep(self.l1 - self.blend, self.l1 + self.blend, s))
        f = self.f1 * (1 - w) + self.f2 * w
        y = norm(f[:, 1])
        z = f[:, 2] - y * np.dot(f[:, 2], y)
        z = norm(z)
        x = np.cross(y, z)
        return np.stack([x, y, z], axis=1)

    def point(self, s):
        if s <= self.l1:
            return self.p0 + self.f1[:, 1] * s
        return self.p1 + self.f2[:, 1] * (s - self.l1)


ARM_LIMB = Limb(J['upperarm_l'], J['lowerarm_l'], J['hand_l'], skel.FWD)
LEG_LIMB = Limb(J['thigh_l'], J['calf_l'], J['foot_l'], skel.FWD)


def arm_point(s, g, shrink=0.0):
    """Left arm surface. g: angle from lateral/top (0) towards front (pi/2), medial (pi), back."""
    fr = ARM_LIMB.frame(s)
    u0, f0 = -fr[:, 0], fr[:, 2]
    c, sn = math.cos(g), math.sin(g)
    rc = float(ARM['lat'](s)) if c > 0 else float(ARM['med'](s))
    rs = float(ARM['f'](s)) if sn > 0 else float(ARM['b'](s))
    r = 1.0 / math.sqrt((c / rc) ** 2 + (sn / rs) ** 2) - shrink
    return ARM_LIMB.point(s) + r * (c * u0 + sn * f0)


def leg_point(s, b, shrink=0.0):
    """Left leg surface. b: angle from front (0) towards lateral (pi/2), back (pi), medial (3pi/2)."""
    fr = LEG_LIMB.frame(s)
    e_out, e_front = -fr[:, 0], fr[:, 2]
    c, sn = math.cos(b), math.sin(b)
    a = float(LEG['a'](s))
    rs = a * (1.0 if sn > 0 else 0.97)
    rc = float(LEG['f'](s)) if c > 0 else float(LEG['b'](s))
    r = 1.0 / math.sqrt((c / rc) ** 2 + (sn / rs) ** 2) - shrink
    cen = LEG_LIMB.point(s) + float(LEG['ox'](s)) * e_out + float(LEG['oy'](s)) * (-e_front)
    return cen + r * (sn * e_out + c * e_front)


# ---------------------------------------------------------------------------------- weights
def _mix(*pairs):
    out = {}
    for b, w in pairs:
        if w > 1e-5:
            out[b] = out.get(b, 0.0) + float(w)
    return out


def _scale(w, k):
    return {b: v * k for b, v in w.items()}


def _add(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0.0) + v
    return out


def spine_weights(z):
    w01 = float(smoothstep(1.020, 1.105, z))
    w12 = float(smoothstep(1.128, 1.216, z))
    w23 = float(smoothstep(1.252, 1.344, z))
    return _mix(('pelvis', 1 - w01), ('spine_01', w01 * (1 - w12)), ('spine_02', w12 * (1 - w23)), ('spine_03', w23))


def torso_weights(p, row):
    x, y, z = p
    w = spine_weights(z)
    side = 'l' if x >= 0 else 'r'
    # clavicle influence over the shoulder yoke
    wc = float(smoothstep(0.045, 0.150, abs(x)) * smoothstep(1.395, 1.455, z)) * 0.75
    if wc > 0:
        w = _add(_scale(w, 1 - wc), {'clavicle_' + side: wc})
    return w


def arm_weights(s, g, ring_index, side='l'):
    """Analytic weights of the arm tube."""
    L = lambda n: n + '_' + side
    c = math.cos(g)
    top = 0.5 + 0.5 * c            # 1 on the deltoid side, 0 in the arm pit
    # --- arm vs torso
    fan_w = [0.22 + 0.10 * (1 - top), 0.52 + 0.08 * (1 - top), 0.80, 0.94]
    w_arm = fan_w[ring_index] if ring_index < len(fan_w) else 1.0
    torso = _mix((L('clavicle'), 0.25 + 0.60 * top), ('spine_03', 0.75 - 0.60 * top))
    # --- along the arm
    w_lo = float(smoothstep(L_UP - 0.026, L_UP + 0.026, s))
    w_hand = float(smoothstep(S_WRIST - 0.022, S_WRIST + 0.012, s))
    tw_up = float(np.clip(1.0 - s / 0.19, 0, 1)) ** 1.0
    tw_lo = float(smoothstep(L_UP + 0.03, S_WRIST - 0.03, s)) * 0.88
    helper_el = float(bump(s, L_UP, 0.034)) * 0.50
    helper_sh = [0.50, 0.46, 0.30, 0.12]
    hs = helper_sh[ring_index] if ring_index < len(helper_sh) else float(np.clip(0.06 - (s - 0.10) * 1.2, 0, 1))
    up = (1 - w_lo)
    lo = w_lo * (1 - w_hand)
    arm = _mix((L('upperarm'), up * (1 - tw_up) * (1 - hs)), (L('upperarm_twist'), up * tw_up * (1 - hs)),
               (L('shoulder_helper'), up * hs),
               (L('lowerarm'), lo * (1 - tw_lo)), (L('lowerarm_twist'), lo * tw_lo), (L('hand'), w_lo * w_hand))
    if helper_el > 0:
        arm = _add(_scale(arm, 1 - helper_el), {L('elbow_helper'): helper_el})
    return _add(_scale(arm, w_arm), _scale(torso, 1 - w_arm))


def leg_weights(s, b, ring_index, side='l'):
    L = lambda n: n + '_' + side
    outer = 0.5 + 0.5 * math.sin(b)     # 1 lateral, 0 medial
    back = 0.5 - 0.5 * math.cos(b)
    fan = [0.36, 0.60, 0.80, 0.92, 0.98]
    if ring_index < len(fan):
        w_leg = fan[ring_index] - 0.22 * outer * (1 - ring_index / len(fan)) + 0.05 * back
        w_leg = float(np.clip(w_leg, 0.05, 1))
    else:
        w_leg = 1.0
    w_ca = float(smoothstep(L_TH - 0.027, L_TH + 0.027, s))
    tw = float(np.clip(1.0 - max(s, 0) / 0.27, 0, 1))
    hk = float(bump(s, L_TH, 0.036)) * 0.50
    hh_t = [0.50, 0.46, 0.34, 0.20, 0.08]
    hh = hh_t[ring_index] if ring_index < len(hh_t) else 0.0
    th = 1 - w_ca
    leg = _mix((L('thigh'), th * (1 - tw) * (1 - hh)), (L('thigh_twist'), th * tw * (1 - hh)), (L('hip_helper'), th * hh),
               (L('calf'), w_ca))
    if hk > 0:
        leg = _add(_scale(leg, 1 - hk), {L('knee_helper'): hk})
    return _add(_scale(leg, w_leg), {'pelvis': 1 - w_leg})


# ---------------------------------------------------------------------------------- builder
def build_body():
    md = MeshData('Body')
    info = {}

    # ---------------- torso rows
    rows = []
    for k in range(len(ROWS)):
        pts = torso_row(k)
        rows.append(md.ring(pts, [torso_weights(p, k) for p in pts], tag='torso'))
    row_t_pts = md.pos(rows[ROW_T])
    nring = neck_ring()
    yoke = []
    for si, sfrac in enumerate(YOKE_S):
        pts = lerp(row_t_pts, nring, sfrac)
        # convex trapezius: lift the sides, keep the centre line
        lift = 0.012 * math.sin(math.pi * sfrac) * np.abs(np.sin(np.arange(NT) * TAU / NT)) ** 2
        pts[:, 2] += lift
        ws = []
        for p in pts:
            w = torso_weights(p, ROW_T + 1 + si)
            ws.append(w)
        yoke.append(md.ring(pts, ws, tag='torso'))
    wneck = [_mix(('spine_03', 0.88), ('neck_01', 0.12)) for _ in range(NT)]
    neck_idx = md.ring(nring, wneck, tag='collar')
    collar = []
    for ci, (dz, sc, dy) in enumerate(COLLAR):
        pts = nring.copy()
        pts[:, 0] *= sc
        pts[:, 1] = NECK['cy'] + (pts[:, 1] - NECK['cy']) * sc + dy
        pts[:, 2] = nring[:, 2] * (1 - 0.35 * (ci + 1) / len(COLLAR)) + (NECK['zs'] + 0.004) * (0.35 * (ci + 1) / len(COLLAR)) + dz
        wn = 0.12 + 0.16 * (ci + 1)
        collar.append(md.ring(pts, _mix(('spine_03', 1 - wn), ('neck_01', wn)), tag='collar'))
    # collar rim (thickness) turned inwards and down
    top = md.pos(collar[-1])
    cen = top.mean(axis=0)
    rim1 = top + (cen - top) * 0.13
    rim1[:, 2] = top[:, 2] + 0.001
    rim2 = top + (cen - top) * 0.15
    rim2[:, 2] = top[:, 2] - 0.018
    wtop = md.w[collar[-1][0]]
    rim = [md.ring(rim1, wtop, tag='collar'), md.ring(rim2, wtop, tag='collar')]

    all_rows = rows + yoke + [neck_idx] + collar + rim
    info['rows'] = all_rows
    hole = set()
    for k in range(ROW_B, ROW_T):
        for j in range(HOLE_C0, HOLE_C1):
            hole.add((k, j))
            hole.add((k, NT - 1 - j))   # mirrored columns: NT-j-1 segment
    for k in range(len(all_rows) - 1):
        skip = {j for j in range(NT) if (k, j) in hole}
        tag = 'torso' if k < len(rows) + len(yoke) else 'collar'
        md.strip(all_rows[k], all_rows[k + 1], SUIT, tag, closed=True, skip=skip)

    # ---------------- crotch strip
    r0 = rows[0]
    pf, pb = np.array(md.v[r0[0]]), np.array(md.v[r0[NT // 2]])
    crotch = []
    for i, f in enumerate([0.25, 0.5, 0.75]):
        p = lerp(pb, pf, f)
        p[2] = min(pf[2], pb[2]) - 0.012 - 0.004 * math.sin(math.pi * f)
        crotch.append(md.vert(p, {'pelvis': 1.0}, tag='crotch'))

    def leg_ring0(side):
        if side == 'l':
            return [r0[j] for j in range(0, NT // 2 + 1)] + crotch
        return [r0[(NT - j) % NT] for j in range(0, NT // 2 + 1)] + crotch

    betas = [math.radians(90.0 + (m - 10) * 360.0 / NL) for m in range(NL)]

    def build_leg(side):
        sx = 1.0 if side == 'l' else -1.0
        ring0 = leg_ring0(side)
        # hip-line weights for ring 0 (shared with the torso row 0)
        for m, vi in enumerate(ring0):
            if side == 'r' and (m == 0 or m >= NT // 2):
                # centre line vertices already weighted by the left pass: average both sides
                wl = md.w[vi]
                wr = leg_weights(0.0, betas[m], 0, 'r')
                md.w[vi] = _add(_scale(wl, 0.5), _scale(wr, 0.5))
            else:
                md.w[vi] = leg_weights(0.0, betas[m], 0, side)
        rings = [ring0]
        svals = []
        for k in range(1, len(LEG_FAN)):
            so, si_ = LEG_FAN[k]
            svals.append([so + (si_ - so) * (1 - math.sin(b)) / 2 for b in betas])
        for s in LEG_S:
            svals.append([s] * NL)
        for k, sv in enumerate(svals):
            pts, ws = [], []
            for m in range(NL):
                p = leg_point(sv[m], betas[m])
                # keep the inner thighs from interpenetrating across the centre line
                p[0] = max(p[0], 0.0035 + 0.006 * min(1.0, k / 3.0))
                p[0] *= sx
                pts.append(p)
                ws.append(leg_weights(sv[m], betas[m], k + 1, side))
            rings.append(md.ring(pts, ws, tag='leg_' + side))
        md.loft(rings, SUIT, 'leg_' + side, closed=True, flip=(side == 'l'))
        # end cap inside the boot
        last = md.pos(rings[-1])
        md.fan_cap(rings[-1], last.mean(axis=0) + V(0, 0, -0.01), md.w[rings[-1][0]], SUIT, 'leg_' + side, flip=(side == 'l'))
        info['leg_rings_' + side] = rings
        return rings

    leg_l = build_leg('l')
    leg_r = build_leg('r')

    # ---------------- arms
    gam = [m * TAU / NA for m in range(NA)]

    def hole_loop(side):
        T, B = ROW_T, ROW_B
        cs = COL_SIDE
        seq = [(T, cs), (T, cs - 1), (T, cs - 2)]
        seq += [(r, cs - 2) for r in range(T - 1, B, -1)]
        seq += [(B, c) for c in range(cs - 2, cs + 3)]
        seq += [(r, cs + 2) for r in range(B + 1, T)]
        seq += [(T, cs + 2), (T, cs + 1)]
        assert len(seq) == NA, len(seq)
        out = []
        for (r, c) in seq:
            col = c if side == 'l' else (NT - c) % NT
            out.append(all_rows[r][col])
        return out

    def build_arm(side, s_end=None, organic_from_hem=False):
        sx = 1.0 if side == 'l' else -1.0
        ring0 = hole_loop(side)
        so, si_ = ARM_FAN[0]
        for m, vi in enumerate(ring0):
            s = so + (si_ - so) * (1 - math.cos(gam[m])) / 2
            p = arm_point(s, gam[m])
            p[0] *= sx
            md.v[vi] = p.tolist()
            md.w[vi] = arm_weights(s, gam[m], 0, side)
            md.vtag[vi] = 'armhole_' + side
        rings = [ring0]
        ring_s = [None]
        svals = []
        for k in range(1, len(ARM_FAN)):
            so, si_ = ARM_FAN[k]
            svals.append([so + (si_ - so) * (1 - math.cos(g)) / 2 for g in gam])
        for s in ARM_S:
            if s_end is not None and s > s_end + 1e-6:
                break
            svals.append([s] * NA)
        mats = []
        hem_at = None
        for k, sv in enumerate(svals):
            ridx = k + 1
            shrink = 0.0
            if organic_from_hem and ridx > HEM_RING:
                shrink = 0.0032
            pts, ws = [], []
            for m in range(NA):
                p = arm_point(sv[m], gam[m], shrink)
                p[0] *= sx
                pts.append(p)
                ws.append(arm_weights(sv[m], gam[m], ridx, side))
            rings.append(md.ring(pts, ws, tag='arm_' + side))
            ring_s.append(sv)
            if organic_from_hem and ridx == HEM_RING:
                # hem step: duplicate ring slightly further along at skin level
                pts2, ws2 = [], []
                for m in range(NA):
                    p = arm_point(sv[m] + 0.0035, gam[m], 0.0032)
                    p[0] *= sx
                    pts2.append(p)
                    ws2.append(arm_weights(sv[m] + 0.0035, gam[m], ridx, side))
                rings.append(md.ring(pts2, ws2, tag='arm_' + side))
                ring_s.append([x + 0.0035 for x in sv])
                hem_at = len(rings) - 1
        for i in range(len(rings) - 1):
            mat = SUIT
            tag = 'arm_' + side
            if organic_from_hem and hem_at is not None and i >= hem_at:
                mat, tag = SKIN, 'skinarm_' + side
            elif organic_from_hem and hem_at is not None and i == hem_at - 1:
                mat, tag = SUIT, 'hem_' + side
            md.strip(rings[i], rings[i + 1], mat, tag, closed=True, flip=(side == 'r'))
        info['arm_rings_' + side] = rings
        info['arm_ring_s_' + side] = ring_s
        info['arm_hem_' + side] = hem_at
        return rings

    arm_l = build_arm('l', None, organic_from_hem=True)
    arm_r = build_arm('r', 0.326, organic_from_hem=False)
    # close the right stump (hidden inside the cybernetic cuff)
    last = md.pos(arm_r[-1])
    md.fan_cap(arm_r[-1], last.mean(axis=0), md.w[arm_r[-1][0]], SUIT, 'arm_r', flip=(True))

    # ---------------- junction relaxation
    nb = md.vert_neighbors()

    def grow(seed, steps):
        cur = set(seed)
        dist = {i: 0 for i in cur}
        for d in range(1, steps + 1):
            nxt = set()
            for i in cur:
                for j in nb[i]:
                    if j not in dist:
                        dist[j] = d
                        nxt.add(j)
            cur = nxt
        return dist

    for side, arm in (('l', arm_l), ('r', arm_r)):
        dist = grow(arm[0], 3)
        sw = {i: (1.0 if d <= 1 else (0.6 if d == 2 else 0.3)) for i, d in dist.items()}
        md.smooth(sw, iters=6, lam=0.45)
    for side in ('l', 'r'):
        dist = grow(leg_ring0(side), 3)
        sw = {i: (0.9 if d <= 1 else (0.55 if d == 2 else 0.25)) for i, d in dist.items()}
        md.smooth(sw, iters=5, lam=0.45)

    # symmetrise the centre line exactly
    for r in all_rows:
        for j in (0, NT // 2):
            md.v[r[j]][0] = 0.0
    for c in crotch:
        md.v[c][0] = 0.0

    # ---------------- weights smoothing (soft junctions)
    md.smooth_weights(iters=2, lam=0.5)

    # ---------------- seams
    for side in ('l', 'r'):
        md.seam_path(hole_loop(side), closed=True)
        md.seam_path(leg_ring0(side), closed=True)
        rl = info['leg_rings_' + side]
        md.seam_path([r[22] for r in rl])
        ra = info['arm_rings_' + side]
        md.seam_path([r[10] for r in ra])
        # torso side seams: column below arm pit down to the hip row and over the shoulder
        col = COL_SIDE if side == 'l' else NT - COL_SIDE
        md.seam_path([all_rows[k][col] for k in range(0, ROW_B + 1)])
        md.seam_path([all_rows[k][col] for k in range(ROW_T, len(all_rows))])
    # ---------------- organic left hand continues the wrist ring
    info['hand_l'] = handmod.build_hand(md, arm_l[-1], 'l')
    info['crotch'] = crotch
    info['arm_l_last'] = arm_l[-1]
    info['neck_row'] = neck_idx
    return md, info

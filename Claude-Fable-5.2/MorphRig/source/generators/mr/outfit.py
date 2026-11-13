"""Hard armour, belt and boots. Plates are generated from the analytic body surfaces so they conform exactly
and are skinned rigidly (one bone each) - armour stays rigid by design, the suit flexes underneath."""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, bump, gauss, TAU, mirror_x
from . import body, skel, prim
from .skel import J
from .meshkit import MeshData

ARMOR = 'M_Armor'
SUIT = 'M_Suit'


# ---------------------------------------------------------------------------------- analytic surfaces
def torso_surf(t, z):
    p = body.torso_point(np.array([t]), np.array([z]))[0]
    e = 1e-3
    pt = body.torso_point(np.array([t + e]), np.array([z]))[0] - body.torso_point(np.array([t - e]), np.array([z]))[0]
    pz = body.torso_point(np.array([t]), np.array([z + e]))[0] - body.torso_point(np.array([t]), np.array([z - e]))[0]
    n = norm(np.cross(pt, pz))
    return p, n


def limb_surf(fn, s, a, side='l'):
    e = 1e-3
    p = fn(s, a)
    ps = fn(s + e, a) - fn(s - e, a)
    pa = fn(s, a + e) - fn(s, a - e)
    n = norm(np.cross(pa, ps))
    # make sure the normal points away from the limb axis
    if side == 'r':
        return mirror_x(p), mirror_x(n) * np.array([1.0, 1.0, 1.0])
    return p, n


def _fix_normal(fn_axis_point):
    pass


def arm_surf(s, g, side='l'):
    p, n = limb_surf(body.arm_point, s, g, 'l')
    c = body.ARM_LIMB.point(s)
    if np.dot(n, p - c) < 0:
        n = -n
    if side == 'r':
        return mirror_x(p), mirror_x(n)
    return p, n


def leg_surf(s, b, side='l'):
    p, n = limb_surf(body.leg_point, s, b, 'l')
    c = body.LEG_LIMB.point(s)
    if np.dot(n, p - c) < 0:
        n = -n
    if side == 'r':
        return mirror_x(p), mirror_x(n)
    return p, n


# ---------------------------------------------------------------------------------- torso armour
def build_chest(md):
    def surf(u, v):
        a = abs(2 * u - 1)
        zb = 1.296 - 0.020 * (1 - a ** 1.6)            # V shaped lower edge
        zt = 1.418 + 0.020 * a ** 2.0                   # scooped neck line
        z = lerp(zb, zt, v)
        span = lerp(0.92, 0.80, v) + 0.10 * math.sin(math.pi * v)
        return torso_surf((2 * u - 1) * span, z)

    def relief(u, v):
        a = abs(2 * u - 1)
        r = 0.0035 * math.exp(-(a / 0.10) ** 2)                               # sternum keel
        r += 0.0030 * float(smoothstep(0.16, 0.24, a)) * float(1 - smoothstep(0.80, 0.92, a)) * float(smoothstep(0.10, 0.22, v)) * float(1 - smoothstep(0.84, 0.95, v))
        r -= 0.0020 * math.exp(-((v - 0.40) / 0.035) ** 2) * float(smoothstep(0.15, 0.3, a))   # lame split
        return r

    prim.plate(md, surf, 26, 14, {'spine_03': 1.0}, ARMOR, 'chest_plate', thickness=0.0075, gap=0.0030, bevel=0.0030, relief=relief)


def build_back(md):
    def surf(u, v):
        a = abs(2 * u - 1)
        zb = 1.300 - 0.012 * (1 - a ** 2)
        zt = 1.440 + 0.012 * a ** 2
        z = lerp(zb, zt, v)
        span = lerp(0.82, 0.74, v) + 0.08 * math.sin(math.pi * v)
        return torso_surf(math.pi + (2 * u - 1) * span, z)

    def relief(u, v):
        a = abs(2 * u - 1)
        r = 0.0115 * float(1 - smoothstep(0.13, 0.20, a)) * float(smoothstep(0.02, 0.10, v)) * float(1 - smoothstep(0.90, 0.98, v))   # spine unit
        r += 0.0025 * float(smoothstep(0.30, 0.38, a)) * float(1 - smoothstep(0.82, 0.92, a))
        r += 0.0030 * math.exp(-((v - 0.55) / 0.05) ** 2) * float(1 - smoothstep(0.13, 0.2, a))
        return r

    prim.plate(md, surf, 24, 14, {'spine_03': 1.0}, ARMOR, 'back_plate', thickness=0.0075, gap=0.0030, bevel=0.0030, relief=relief)


def build_belt(md):
    def surf(u, v):
        t = TAU * u
        zc = 1.030 + 0.010 * (1 - math.cos(t)) / 2
        z = zc + (v - 0.5) * 0.044
        return torso_surf(t, z)

    def relief(u, v):
        t = TAU * u
        d = abs(((t + math.pi) % TAU) - math.pi)
        r = 0.0055 * float(1 - smoothstep(0.10, 0.16, d))                       # front buckle
        r += 0.0012 * math.cos(v * math.pi * 2) * -1.0
        return r

    prim.plate(md, surf, 56, 4, {'pelvis': 1.0}, ARMOR, 'belt', thickness=0.0055, gap=0.0020, bevel=0.0020, relief=relief, closed_u=True)
    # pouches (rigid boxes on the belt): right front hip utility pouch, left hip cell holder, back-right beacon dock
    def belt_frame(t, z=1.030, out=0.010):
        p, n = torso_surf(t, z)
        up = V(0, 0, 1)
        m = np.eye(4)
        tang = norm(np.cross(up, n))
        m[:3, 0] = tang
        m[:3, 1] = up
        m[:3, 2] = n
        m[:3, 3] = p + n * out
        return m

    w = {'pelvis': 1.0}
    m = belt_frame(-0.95)
    prim.box(md, m, 0.030, 0.062, 0.016, w, ARMOR, 'pouch', chamfer=0.006, y0=-0.040)
    m = belt_frame(-2.05, out=0.009)
    prim.box(md, m, 0.024, 0.050, 0.013, w, ARMOR, 'pouch', chamfer=0.005, y0=-0.034)
    return belt_frame


# ---------------------------------------------------------------------------------- limb armour
def build_pauldron(md, side='r'):
    bone = 'shoulder_helper_' + side

    def surf(u, v):
        s = lerp(-0.046, 0.132, v)
        g = math.radians(lerp(-112.0, 112.0, u))
        return arm_surf(s, g, side)

    def relief(u, v):
        a = abs(2 * u - 1)
        r = 0.014 * (1 - a ** 2.2) * math.sin(math.pi * min(1.0, v * 1.05)) ** 0.7        # dome
        r += 0.0035 * float(smoothstep(0.80, 0.90, v)) * (1 - a ** 4)                       # lower lip
        r += 0.0030 * math.exp(-(a / 0.09) ** 2) * float(smoothstep(0.05, 0.3, v))          # crest
        return r

    prim.plate(md, surf, 18, 12, {bone: 1.0}, ARMOR, 'pauldron_' + side, thickness=0.0085, gap=0.0060, bevel=0.0035,
               relief=relief, flip=(side == 'r'))


def build_bracer(md, side='l'):
    bone = 'lowerarm_' + side

    def surf(u, v):
        s = lerp(0.326, 0.462, v)
        return arm_surf(s, TAU * u, side)

    def relief(u, v):
        t = TAU * u
        d = abs(((t + math.pi) % TAU) - math.pi)
        return 0.0020 * float(1 - smoothstep(0.75, 0.95, d)) + 0.0010 * math.exp(-((v - 0.5) / 0.3) ** 8)

    prim.plate(md, surf, 20, 6, {bone: 1.0}, ARMOR, 'bracer_' + side, thickness=0.0048, gap=0.0028, bevel=0.0018,
               relief=relief, closed_u=True, flip=(side == 'r'))


def build_knee(md, side):
    bone = 'knee_helper_' + side
    LT = body.L_TH

    def surf(u, v):
        s = lerp(LT - 0.058, LT + 0.052, v)
        b = math.radians(lerp(-64.0, 64.0, u))
        return leg_surf(s, b, side)

    def relief(u, v):
        a = abs(2 * u - 1)
        r = 0.010 * (1 - a ** 2.4) * math.sin(math.pi * v) ** 0.8
        r += 0.003 * math.exp(-(a / 0.12) ** 2) * math.sin(math.pi * v)
        return r

    prim.plate(md, surf, 12, 10, {bone: 1.0}, ARMOR, 'knee_' + side, thickness=0.0080, gap=0.0045, bevel=0.0030,
               relief=relief, flip=(side == 'r'))


def build_shin(md, side):
    bone = 'calf_' + side
    LT = body.L_TH

    def surf(u, v):
        s = lerp(LT + 0.066, 0.712, v)
        half = lerp(78.0, 62.0, v)
        b = math.radians(lerp(-half, half, u))
        return leg_surf(s, b, side)

    def relief(u, v):
        a = abs(2 * u - 1)
        r = 0.0045 * math.exp(-(a / 0.16) ** 2)
        r += 0.0025 * float(smoothstep(0.30, 0.40, a)) * float(1 - smoothstep(0.82, 0.92, a))
        return r

    prim.plate(md, surf, 12, 12, {bone: 1.0}, ARMOR, 'shin_' + side, thickness=0.0070, gap=0.0040, bevel=0.0028,
               relief=relief, flip=(side == 'r'))


def build_thigh_plate(md, side='r'):
    bone = 'thigh_' + side

    def surf(u, v):
        s = lerp(0.125, 0.325, v)
        b = math.radians(lerp(38.0, 142.0, u))
        return leg_surf(s, b, side)

    def relief(u, v):
        a = abs(2 * u - 1)
        return 0.0030 * float(1 - smoothstep(0.55, 0.75, a)) * float(smoothstep(0.08, 0.2, v)) * float(1 - smoothstep(0.8, 0.92, v))

    prim.plate(md, surf, 10, 10, {bone: 1.0}, ARMOR, 'thighplate_' + side, thickness=0.0065, gap=0.0035, bevel=0.0026,
               relief=relief, flip=(side == 'r'))
    # two straps around the thigh holding the plate (soft goods)
    for s0 in (0.150, 0.300):
        def ssurf(u, v, s0=s0):
            return leg_surf(s0 + (v - 0.5) * 0.022, TAU * u, side)
        prim.plate(md, ssurf, 24, 1, {bone: 1.0}, SUIT, 'strap_' + side, thickness=0.0022, gap=0.0006, bevel=0.0008,
                   closed_u=True, flip=(side == 'r'))


def build_left_thigh_strap(md):
    def ssurf(u, v):
        return leg_surf(0.190 + (v - 0.5) * 0.030, TAU * u, 'l')
    prim.plate(md, ssurf, 24, 1, {'thigh_l': 1.0}, SUIT, 'strap_l', thickness=0.0024, gap=0.0006, bevel=0.0008, closed_u=True)


# ---------------------------------------------------------------------------------- yoke / collar surface
_YOKE = {}


def _yoke_rings():
    if not _YOKE:
        rt = body.torso_row(body.ROW_T)
        nr = body.neck_ring()
        _YOKE['t'] = rt
        _YOKE['n'] = nr
    return _YOKE['t'], _YOKE['n']


def _ring_at(ring, u):
    n = len(ring)
    f = (u % 1.0) * n
    i = int(math.floor(f)) % n
    t = f - math.floor(f)
    return ring[i] * (1 - t) + ring[(i + 1) % n] * t


def yoke_point(u, s):
    """u in [0,1) around (0 = front centre, towards the left), s: 0 = shoulder row .. 1 = neck ring, >1 = up the collar."""
    rt, nr = _yoke_rings()
    if s <= 1.0:
        p = lerp(_ring_at(rt, u), _ring_at(nr, u), s)
        p = p + np.array([0, 0, 0.012 * math.sin(math.pi * s) * abs(math.sin(TAU * u)) ** 2])
        return p
    k = s - 1.0
    base = _ring_at(nr, u)
    cen = np.array([0.0, body.NECK['cy'], base[2]])
    q = cen + (base - cen) * (1.0 - 0.09 * min(k, 1.0))
    q[2] = base[2] + 0.050 * k
    q[1] -= 0.006 * k
    return q


def yoke_surf(u, s):
    e = 2e-3
    p = yoke_point(u, s)
    pu = yoke_point(u + e, s) - yoke_point(u - e, s)
    ps = yoke_point(u, s + e) - yoke_point(u, s - e)
    n = norm(np.cross(pu, ps))
    if n[2] < 0 and s <= 1.0:
        n = -n
    if s > 1.0:
        c = np.array([0.0, body.NECK['cy'], p[2]])
        if np.dot(n, p - c) < 0:
            n = -n
    return p, n


def build_gorget(md):
    def surf(u, v):
        a = abs(((u + 0.5) % 1.0) - 0.5) * 2.0            # 0 front centre .. 1 back centre
        s0 = 0.50 - 0.14 * (1 - a) ** 2                   # dips towards the sternum at the front
        return yoke_surf(u, lerp(s0, 1.34, v))

    def relief(u, v):
        return 0.0030 * float(smoothstep(0.55, 0.70, v)) + 0.0015 * math.sin(math.pi * v)

    prim.plate(md, surf, 40, 6, {'spine_03': 1.0}, ARMOR, 'gorget', thickness=0.0055, gap=0.0030, bevel=0.0022, relief=relief,
               closed_u=True)


def build_ab_plate(md):
    def surf(u, v):
        a = abs(2 * u - 1)
        zb = 1.196 - 0.016 * (1 - a ** 1.6)
        zt = 1.272 - 0.020 * (1 - a ** 1.6)
        span = lerp(0.50, 0.66, v)
        return torso_surf((2 * u - 1) * span, lerp(zb, zt, v))

    def relief(u, v):
        a = abs(2 * u - 1)
        return 0.0028 * math.exp(-(a / 0.12) ** 2) + 0.0018 * float(smoothstep(0.2, 0.3, a)) * float(1 - smoothstep(0.78, 0.9, a))

    prim.plate(md, surf, 16, 6, {'spine_02': 1.0}, ARMOR, 'ab_plate', thickness=0.0060, gap=0.0028, bevel=0.0025, relief=relief)


def build_arm_band(md):
    def ssurf(u, v):
        return arm_surf(0.150 + (v - 0.5) * 0.030, TAU * u, 'l')
    prim.plate(md, ssurf, 20, 1, {'upperarm_l': 1.0}, SUIT, 'armband_l', thickness=0.0024, gap=0.0006, bevel=0.0008, closed_u=True)

    def psurf(u, v):
        return arm_surf(0.132 + v * 0.040, math.radians(lerp(-38.0, 38.0, u)), 'l')
    prim.plate(md, psurf, 5, 4, {'upperarm_l': 1.0}, ARMOR, 'armpad_l', thickness=0.0050, gap=0.0030, bevel=0.0018)


def build_tasset(md, side='l'):
    bone = 'hip_helper_' + side

    def surf(u, v):
        s = lerp(-0.012, 0.165, v)
        half = lerp(54.0, 44.0, v)
        b = math.radians(90.0 + lerp(-half, half, u))
        return leg_surf(s, b, side)

    def relief(u, v):
        a = abs(2 * u - 1)
        return 0.0035 * math.exp(-(a / 0.18) ** 2) * float(smoothstep(0.05, 0.2, v)) + 0.0020 * float(smoothstep(0.82, 0.92, v))

    prim.plate(md, surf, 10, 9, {bone: 1.0}, ARMOR, 'tasset_' + side, thickness=0.0065, gap=0.0050, bevel=0.0026, relief=relief,
               flip=(side == 'r'))


# ---------------------------------------------------------------------------------- boots
BOOT_TOP = 0.338
NB = 20


def _boot_sections(side='l'):
    """Returns list of (points (NB,3), weights) from the cuff down to the toe for the left boot."""
    ank = J['foot_l']
    ball = J['ball_l']
    cx = 0.1015
    out = []

    def ring_h(z, a, f, b, cy, wts, xo=0.0):
        """horizontal section; index 0 = front (-Y), increasing towards lateral."""
        pts = []
        for k in range(NB):
            ang = TAU * k / NB
            c, s = math.cos(ang), math.sin(ang)
            r = 1.0 / math.sqrt((c / (f if c > 0 else b)) ** 2 + (s / a) ** 2)
            pts.append((cx + xo + r * s, cy - r * c, z))
        out.append((np.array(pts), wts))

    wc = {'calf_l': 1.0}
    ring_h(BOOT_TOP, 0.0530, 0.0500, 0.0660, 0.0130, wc)
    ring_h(0.300, 0.0515, 0.0490, 0.0640, 0.0135, wc)
    ring_h(0.245, 0.0470, 0.0465, 0.0560, 0.0150, wc)
    ring_h(0.195, 0.0435, 0.0450, 0.0500, 0.0170, wc)
    ring_h(0.155, 0.0415, 0.0450, 0.0480, 0.0190, {'calf_l': 0.8, 'foot_l': 0.2})
    ring_h(0.125, 0.0410, 0.0460, 0.0480, 0.0205, {'calf_l': 0.5, 'foot_l': 0.5})
    # heel fan: sections rotate about the instep pivot from horizontal to vertical
    piv = np.array([cx, -0.030, 0.118])
    for ai, deg in enumerate((22.0, 45.0, 68.0)):
        a = math.radians(deg)
        pts = []
        # far radius grows towards the heel then shrinks to the sole length
        reach_back = lerp(0.098, 0.104, math.sin(a))          # distance from pivot to the heel curve
        half_w = lerp(0.0410, 0.0450, deg / 90.0)
        for k in range(NB):
            ang = TAU * k / NB
            c, s = math.cos(ang), math.sin(ang)
            # local section coords: u (lateral), w (from pivot towards the far side, along the rotated plane)
            ww = (1 - c) * 0.5                                 # 0 at the front point (pivot side), 1 at the far side
            lat = half_w * s * (0.55 + 0.45 * math.sin(math.pi * ww) ** 0.5)
            dist = reach_back * ww ** 0.9
            dy = math.cos(a) * dist
            dz = -math.sin(a) * dist
            fwd_bulge = 0.012 * (1 - ww) ** 2
            pts.append((piv[0] + lat, piv[1] + dy - fwd_bulge * math.cos(a), piv[2] + dz + fwd_bulge * math.sin(a) * 0.3))
        wa = 0.75 + 0.08 * ai
        out.append((np.array(pts), {'calf_l': 1 - wa, 'foot_l': wa}))
    # foot: vertical sections marching forward (index 0 = top of the foot)
    foot = [  # (y, half width, top z, x offset, weights)
        (-0.030, 0.0450, 0.1010, 0.0000, 1.0, 0.0),
        (-0.058, 0.0465, 0.0860, 0.0010, 1.0, 0.0),
        (-0.086, 0.0485, 0.0730, 0.0020, 1.0, 0.0),
        (-0.108, 0.0495, 0.0650, 0.0030, 0.85, 0.15),
        (-0.122, 0.0500, 0.0610, 0.0035, 0.5, 0.5),
        (-0.136, 0.0495, 0.0580, 0.0040, 0.15, 0.85),
        (-0.160, 0.0470, 0.0540, 0.0045, 0.0, 1.0),
        (-0.186, 0.0410, 0.0490, 0.0050, 0.0, 1.0),
        (-0.205, 0.0300, 0.0410, 0.0050, 0.0, 1.0),
    ]
    for (y, hw, zt, xo, wf, wb) in foot:
        pts = []
        for k in range(NB):
            ang = TAU * k / NB
            c, s = math.cos(ang), math.sin(ang)
            # superellipse in XZ: flat sole, rounded top
            ex = 2.0 / 3.2
            lat = hw * np.sign(s) * abs(s) ** ex
            zz = zt * 0.5 + zt * 0.5 * np.sign(c) * abs(c) ** (2.0 / (2.2 if c > 0 else 5.0))
            # welt: sole edge slightly proud
            if zz < 0.022:
                lat *= 1.045
            pts.append((cx + xo + lat, y, max(zz, 0.0)))
        w = {}
        if wf > 0:
            w['foot_l'] = wf
        if wb > 0:
            w['ball_l'] = wb
        out.append((np.array(pts), w))
    return out


def build_boot(md, side):
    secs = _boot_sections()
    rings = []
    for pts, w in secs:
        if side == 'r':
            pts = pts * np.array([-1.0, 1.0, 1.0])
            w = {skel.mirror_name(k): v for k, v in w.items()}
        rings.append(md.ring(pts, w, tag='boot_' + side))
    for i, (a, b) in enumerate(zip(rings[:-1], rings[1:])):
        md.strip(a, b, ARMOR, 'boot_' + side, closed=True, flip=(side == 'l'))
    # toe cap
    last = md.pos(rings[-1])
    tip = last.mean(axis=0) + np.array([0, -0.012, -0.004])
    md.fan_cap(rings[-1], tip, md.w[rings[-1][0]], ARMOR, 'boot_' + side, flip=(side == 'l'))
    # cuff rim: turn the top edge inwards so the boot has visible thickness
    top = md.pos(rings[0])
    cen = top.mean(axis=0)
    rim1 = top + (cen - top) * 0.10 + np.array([0, 0, 0.0015])
    rim2 = top + (cen - top) * 0.13 + np.array([0, 0, -0.020])
    w0 = md.w[rings[0][0]]
    r1 = md.ring(rim1, w0, tag='boot_' + side)
    r2 = md.ring(rim2, w0, tag='boot_' + side)
    md.strip(r1, rings[0], ARMOR, 'boot_' + side, closed=True, flip=(side == 'l'))
    md.strip(r2, r1, ARMOR, 'boot_' + side, closed=True, flip=(side == 'l'))
    md.seam_path([r[NB // 2] for r in rings[:6]])
    return rings


def build_outfit():
    md = MeshData('Outfit')
    build_chest(md)
    build_back(md)
    belt_frame = build_belt(md)
    build_pauldron(md, 'r')
    build_bracer(md, 'l')
    for s in ('l', 'r'):
        build_knee(md, s)
        build_shin(md, s)
        build_boot(md, s)
    build_thigh_plate(md, 'r')
    build_left_thigh_strap(md)
    build_gorget(md)
    build_ab_plate(md)
    build_arm_band(md)
    build_tasset(md, 'l')
    return md, dict(belt_frame=belt_frame)

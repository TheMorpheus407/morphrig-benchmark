"""Cybernetic right fore-arm and hand (rigid mechanical segments), wrist emitter, power cells, fore-arm
blade, deployable beacon, ear comm units and the occipital data-cable tail."""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, TAU, mirror_x, frame_from
from . import skel, prim, body
from .skel import J, FINGERS, THUMB
from .meshkit import MeshData

CYBER = 'M_Cyber'
ARMOR = 'M_Armor'

CELL_HALF = (0.0105, 0.0150)      # lateral / along-arm half sizes of the power cell body
CELL_DEPTH = 0.026                # how far the cell reaches into its slot below the bone origin
CELL_TOP = 0.030                  # how far it stands proud above the bone origin


def cell_geometry(md, m, bone):
    """Power cell in its bone frame (local Y = eject direction)."""
    w = {bone: 1.0}
    hx, hz = CELL_HALF
    prim.box(md, m, hx, CELL_DEPTH + 0.012, hz, w, CYBER, 'cell_body', chamfer=0.003, y0=-CELL_DEPTH)
    prim.box(md, m, hx + 0.0022, 0.012, hz + 0.0022, w, CYBER, 'cell_cap', chamfer=0.0035, y0=0.010)
    # grip bar on top
    prim.box(md, m, hx * 0.42, CELL_TOP - 0.020, hz * 0.85, w, CYBER, 'cell_grip', chamfer=0.002, y0=0.020)


def build_forearm(md):
    e, d, dor, rad = skel._arm_frame('r')
    m = prim.frame(e, d, dor)
    w = {'lowerarm_r': 1.0}
    wt = {'lowerarm_twist_r': 1.0}
    wh = {'hand_r': 1.0}
    LL = skel.L_LOWER
    # elbow cuff (covers the sleeve end)
    prim.lathe(md, m, [(0.0400, 0.014), (0.0470, 0.020), (0.0475, 0.050), (0.0430, 0.060), (0.0380, 0.062)], 16, w, CYBER, 'cuff')

    def shell(y0, y1, s0, s1, tag):
        (hx0, hz0), (hx1, hz1) = s0, s1
        c0, c1 = min(hx0, hz0) * 0.42, min(hx1, hz1) * 0.42
        e_ = 0.004
        secs = [(y0, prim.chamfer_rect(hx0 - e_, hz0 - e_, c0)), (y0 + e_, prim.chamfer_rect(hx0, hz0, c0)),
                (y1 - e_, prim.chamfer_rect(hx1, hz1, c1)), (y1, prim.chamfer_rect(hx1 - e_, hz1 - e_, c1))]
        prim.loft_sections(md, m, secs, w, CYBER, tag)

    shell(0.052, 0.120, (0.0405, 0.0385), (0.0375, 0.0355), 'fore_shell_a')
    shell(0.128, 0.200, (0.0365, 0.0345), (0.0305, 0.0285), 'fore_shell_b')
    # inner core visible in the panel gap and at the wrist
    prim.lathe(md, m, [(0.0290, 0.110), (0.0290, 0.140)], 12, w, CYBER, 'fore_core')
    prim.lathe(md, m, [(0.0215, 0.190), (0.0215, 0.238)], 12, w, CYBER, 'fore_core')
    # twisting wrist collar (hexagonal) and wrist ball
    prim.lathe(md, m, [(0.0240, 0.206), (0.0285, 0.209), (0.0285, 0.232), (0.0240, 0.236)], 6, wt, CYBER, 'wrist_collar')
    prim.sphere(md, J['hand_r'], 0.0185, wh, CYBER, 'wrist_ball', seg=12, rings=8)
    # two actuator rods on the palmar side
    for sx in (-1.0, 1.0):
        mr_ = m.copy()
        mr_[:3, 3] = prim.xf(m, (sx * 0.0185, 0.0, -0.0205))
        prim.lathe(md, mr_, [(0.0036, 0.150), (0.0036, 0.246)], 6, w, CYBER, 'piston')
        prim.lathe(md, mr_, [(0.0056, 0.150), (0.0056, 0.196)], 6, w, CYBER, 'piston')
    # ---- emitter housing on the dorsal side, barrel and muzzle
    mh = m.copy()
    mh[:3, 3] = prim.xf(m, (0.0, 0.0, 0.0440))
    prim.box(md, mh, 0.0185, 0.150, 0.0160, w, CYBER, 'emitter_housing', chamfer=0.0055, y0=0.062)
    mb = m.copy()
    mb[:3, 3] = prim.xf(m, (0.0, 0.0, 0.0470))
    prim.lathe(md, mb, [(0.0100, 0.205), (0.0100, 0.246), (0.0132, 0.248), (0.0132, 0.262), (0.0085, 0.262), (0.0085, 0.252)],
               12, w, CYBER, 'emitter_barrel', cap_start=True, cap_end=True)
    # side cooling fins
    for sx in (-1.0, 1.0):
        mf = m.copy()
        mf[:3, 3] = prim.xf(m, (sx * 0.0205, 0.0, 0.0440))
        prim.box(md, mf, 0.0030, 0.060, 0.0100, w, CYBER, 'emitter_fin', chamfer=0.0012, y0=0.130)
    # rear sight block / status lens
    ms = m.copy()
    ms[:3, 3] = prim.xf(m, (0.0, 0.0, 0.0625))
    prim.box(md, ms, 0.0080, 0.024, 0.0040, w, CYBER, 'emitter_lens', chamfer=0.0018, y0=0.168)
    # ---- cell slot collar + the cell itself (prop bone)
    cell_pos = prim.xf(m, (0.0, 0.105, 0.0500))
    skel.place_bone('prop_cell', cell_pos, cell_pos + dor * 0.06, d)
    mc = prim.frame(cell_pos, dor, d)
    hx, hz = CELL_HALF
    prim.box(md, mc, hx + 0.0050, 0.008, hz + 0.0050, w, CYBER, 'cell_collar', chamfer=0.004, y0=0.002)
    cell_geometry(md, mc, 'prop_cell')
    return m


def build_mech_hand(md):
    side = 'r'
    Wp = J['hand_r']
    D = mirror_x(skel.HAND_D)
    T = mirror_x(skel.HAND_T)
    P = mirror_x(skel.HAND_P)
    dorsal = -P
    wh = {'hand_r': 1.0}
    mpalm = prim.frame(Wp, D, dorsal)
    # palm block, knuckle guard and thumb mount
    prim.box(md, mpalm, 0.0395, 0.072, 0.0125, wh, CYBER, 'mech_palm', chamfer=0.0055, y0=0.016, taper=1.04)
    mk = mpalm.copy()
    mk[:3, 3] = prim.xf(mpalm, (0.0, 0.0, 0.0075))
    prim.box(md, mk, 0.0400, 0.016, 0.0085, wh, CYBER, 'mech_knuckle', chamfer=0.0035, y0=0.080)
    mi = mpalm.copy()
    mi[:3, 3] = prim.xf(mpalm, (0.0, 0.0, 0.0105))
    prim.box(md, mi, 0.0260, 0.044, 0.0040, wh, CYBER, 'mech_backplate', chamfer=0.002, y0=0.026)

    def digit(name, lens, rb, rt, n=8):
        js = [J['%s_%02d_%s' % (name, i + 1, side)] for i in range(3)] + [J['%s_end_%s' % (name, side)]]
        for i in range(3):
            a, b = js[i], js[i + 1]
            bone = '%s_%02d_%s' % (name, i + 1, side)
            w = {bone: 1.0}
            ln = float(np.linalg.norm(b - a))
            r0 = lerp(rb, rt, i / 3.0) * 1.04
            r1 = lerp(rb, rt, (i + 1) / 3.0) * 1.04
            mseg = prim.frame(a, b - a, dorsal)
            gap = 0.0030
            ph = TAU / (2 * n)
            if i < 2:
                prof = [(r0 * 0.80, gap), (r0, gap + 0.0025), (r1, ln - gap - 0.0025), (r1 * 0.80, ln - gap)]
            else:
                prof = [(r0 * 0.80, gap), (r0, gap + 0.0025), (r1 * 0.98, ln * 0.62), (r1 * 0.72, ln * 0.90), (r1 * 0.36, ln)]
            prim.lathe(md, mseg, prof, n, w, CYBER, 'mech_' + name, rz_scale=0.90, phase=ph)
            # joint pin: short cylinder across the knuckle axis
            mj = prim.frame(a, np.cross(dorsal, b - a), b - a)
            jr = r0 * 0.86
            prim.lathe(md, mj, [(jr, -r0 * 1.02), (jr, r0 * 1.02)], 8, w, CYBER, 'mech_joint')

    for f in ('index', 'middle', 'ring', 'pinky'):
        digit(f, FINGERS[f][2], FINGERS[f][3], FINGERS[f][4])
    digit('thumb', THUMB[2], THUMB[3] * 1.12, THUMB[4])
    prim.sphere(md, J['thumb_01_r'], 0.0140, wh, CYBER, 'mech_thumb_mount', seg=10, rings=6)


def build_blade(md):
    """Left fore-arm blade housing (rigid to the fore-arm) and the sliding blade (blade_l bone)."""
    e, d, dor, rad = skel._arm_frame('l')
    m = prim.frame(e, d, dor)
    w = {'lowerarm_l': 1.0}
    z_h = 0.0500                                    # housing centre height above the fore-arm axis
    mh = m.copy()
    mh[:3, 3] = prim.xf(m, (0.0, 0.0, z_h))
    prim.box(md, mh, 0.0200, 0.150, 0.0090, w, ARMOR, 'blade_housing', chamfer=0.0045, y0=0.060)
    # guide rails and front guard
    for sx in (-1.0, 1.0):
        mr_ = m.copy()
        mr_[:3, 3] = prim.xf(m, (sx * 0.0215, 0.0, z_h - 0.001))
        prim.box(md, mr_, 0.0032, 0.120, 0.0062, w, CYBER, 'blade_rail', chamfer=0.0015, y0=0.075)
    mg = m.copy()
    mg[:3, 3] = prim.xf(m, (0.0, 0.0, z_h))
    prim.box(md, mg, 0.0235, 0.014, 0.0115, w, CYBER, 'blade_guard', chamfer=0.004, y0=0.203)
    # ---- blade (retracted rest pose): bone origin at the housing rear
    head = prim.xf(m, (0.0, 0.050, z_h))
    skel.place_bone('blade_l', head, head + d * 0.30, dor)
    skel.BLADE_TRAVEL = 0.170
    mb = prim.frame(head, d, dor)
    wb = {'blade_l': 1.0}
    L = 0.215
    hw = 0.0165
    th = 0.0024
    # flat diamond section tapering to a point; tang hidden in the housing
    def sec(hx, hz):
        return [(hx, 0.0), (hx * 0.45, hz), (-hx * 0.45, hz), (-hx, 0.0), (-hx * 0.45, -hz), (hx * 0.45, -hz)]
    secs = [(0.006, sec(hw * 0.75, th)), (0.016, sec(hw, th)), (L * 0.62, sec(hw, th)), (L * 0.86, sec(hw * 0.62, th * 0.9)),
            (L, sec(0.0006, 0.0003))]
    prim.loft_sections(md, mb, secs, wb, CYBER, 'blade')
    md_info = dict(blade_len=L, housing_front=0.217)
    skel.SOCKETS_EXTRA = getattr(skel, 'SOCKETS_EXTRA', {})
    skel.BLADE_GEOM = dict(length=L, base_offset=0.016)
    return md_info


def build_beacon_geo(md, m, bone, mat=CYBER):
    w = {bone: 1.0}
    prim.lathe(md, m, [(0.0270, 0.000), (0.0335, 0.004), (0.0335, 0.019), (0.0285, 0.025), (0.0180, 0.031), (0.0070, 0.0345)],
               14, w, mat, 'beacon_body')
    prim.lathe(md, m, [(0.0120, 0.0300), (0.0120, 0.0390), (0.0060, 0.0420)], 10, w, mat, 'beacon_lens')
    for k in range(3):
        a = TAU * k / 3 + 0.5
        mf = m.copy()
        ax = m[:3, 0] * math.cos(a) + m[:3, 2] * math.sin(a)
        mf2 = prim.frame(m[:3, 3] + ax * 0.024 + m[:3, 1] * 0.001, ax, m[:3, 1])
        prim.box(md, mf2, 0.0060, 0.020, 0.0030, w, mat, 'beacon_foot', chamfer=0.0012, y0=0.0)
    ma = m.copy()
    ma[:3, 3] = m[:3, 3] + m[:3, 0] * 0.020
    prim.lathe(md, ma, [(0.0022, 0.020), (0.0016, 0.060), (0.0030, 0.063)], 6, w, mat, 'beacon_antenna')


def build_belt_props(md, belt_frame):
    wp = {'pelvis': 1.0}
    # ---- spare cell in an open holder on the left hip
    mb = belt_frame(1.12, z=1.030, out=0.0)
    n = mb[:3, 2]
    up = V(0, 0, 1)
    pos = mb[:3, 3] + n * 0.0235 + up * 0.004
    skel.place_bone('prop_cell_spare', pos, pos + up * 0.06, n)
    mc = prim.frame(pos, up, n)
    hx, hz = CELL_HALF
    # holder: a U-shaped cradle = back plate + bottom cup
    mh = prim.frame(pos - up * (CELL_DEPTH + 0.004), up, n)
    prim.box(md, mh, hx + 0.0050, 0.020, hz + 0.0050, wp, ARMOR, 'cell_holder', chamfer=0.004, y0=0.0)
    mbk = prim.frame(pos - n * (hz + 0.0045) - up * CELL_DEPTH, up, n)
    prim.box(md, mbk, hx + 0.0050, 0.050, 0.0030, wp, ARMOR, 'cell_holder', chamfer=0.0012, y0=0.0)
    cell_geometry(md, mc, 'prop_cell_spare')
    # second, empty cradle further back on the belt: the spent cell is parked here during the reload
    t2 = 1.12
    for _ in range(60):
        t2 += 0.01
        m2 = belt_frame(t2, z=1.030, out=0.0)
        rear = m2[:3, 3] + m2[:3, 2] * 0.0235 + up * 0.004
        if np.linalg.norm(rear - pos) >= 0.040:
            break
    n2 = m2[:3, 2]
    skel.REAR_CRADLE.update(head=rear.copy(), tail=rear + up * 0.06, zhint=n2.copy())
    skel.rebuild_sockets()
    mh2 = prim.frame(rear - up * (CELL_DEPTH + 0.004), up, n2)
    prim.box(md, mh2, hx + 0.0050, 0.020, hz + 0.0050, wp, ARMOR, 'cell_holder', chamfer=0.004, y0=0.0)
    mbk2 = prim.frame(rear - n2 * (hz + 0.0045) - up * CELL_DEPTH, up, n2)
    prim.box(md, mbk2, hx + 0.0050, 0.050, 0.0030, wp, ARMOR, 'cell_holder', chamfer=0.0012, y0=0.0)
    # ---- beacon on a dock at the back-right of the belt
    mb = belt_frame(math.pi + 0.62, z=1.034, out=0.0)
    n = mb[:3, 2]
    pos = mb[:3, 3] + n * 0.0420 - up * 0.014
    skel.place_bone('prop_beacon', pos, pos + up * 0.06, n)
    mbe = prim.frame(pos, up, n)
    build_beacon_geo(md, mbe, 'prop_beacon')
    md_ = prim.frame(mb[:3, 3] + n * 0.004 - up * 0.016, n, up)
    prim.box(md, md_, 0.0200, 0.012, 0.0200, wp, ARMOR, 'beacon_dock', chamfer=0.004, y0=0.0)
    return dict()


def build_head_gear(md, shape):
    """Ear comm units (rigid to the head) and the occipital port with its cable tail."""
    from . import head as headmod
    wh = {'head': 1.0}
    for sx in (1.0, -1.0):
        o = np.array([[0.0, 0.012, 1.655]])
        hit = headmod.ray_project(shape, o, o + np.array([sx, 0.0, 0.0]), tmax=0.12, samples=60)[0]
        base = hit - np.array([sx * 0.003, 0, 0])
        m = prim.frame(base, V(sx, 0, 0), V(0, 0, 1))
        prim.lathe(md, m, [(0.0215, 0.000), (0.0262, 0.0030), (0.0262, 0.0095), (0.0195, 0.0135), (0.0105, 0.0150)], 14, wh, CYBER, 'ear_unit')
        prim.lathe(md, m, [(0.0085, 0.0140), (0.0085, 0.0175), (0.0050, 0.0190)], 10, wh, CYBER, 'ear_lens')
        # antenna fin sweeping up and back, small boom towards the cheek
        mf = prim.frame(base + V(sx * 0.008, 0.012, 0.014), norm(V(0, 0.55, 0.84)), V(sx, 0, 0))
        prim.box(md, mf, 0.0065, 0.050, 0.0022, wh, CYBER, 'ear_fin', chamfer=0.0010, y0=0.0, taper=0.45)
        mb = prim.frame(base + V(sx * 0.007, -0.016, -0.010), norm(V(0, -0.86, -0.50)), V(sx, 0, 0))
        prim.box(md, mb, 0.0045, 0.030, 0.0026, wh, CYBER, 'ear_boom', chamfer=0.0010, y0=0.0, taper=0.6)
    # occipital port
    c1 = J['cable_01']
    mp = prim.frame(c1 + V(0, -0.010, 0.004), V(0, 1, -0.25), V(0, 0, 1))
    prim.lathe(md, mp, [(0.0170, 0.000), (0.0195, 0.004), (0.0195, 0.010), (0.0125, 0.014)], 12, wh, CYBER, 'cable_port')
    # cable: ribbed tube along the cable bones
    js = [J['cable_01'], J['cable_02'], J['cable_03'], J['cable_04'], J['cable_end']]
    names = ['cable_01', 'cable_02', 'cable_03', 'cable_04']
    seg_per = 5
    rings = []
    n = 10
    total = seg_per * 4
    for k in range(total + 1):
        f = k / float(seg_per)
        i = min(int(f), 3)
        t = f - i
        cen = lerp(js[i], js[i + 1], t)
        tan = norm(js[i + 1] - js[i])
        if 0 < i and t < 0.5:
            tan = norm(lerp(norm(js[i] - js[i - 1]), tan, 0.5 + t))
        elif i < 3 and t > 0.5:
            tan = norm(lerp(tan, norm(js[i + 2] - js[i + 1]), t - 0.5))
        fr = frame_from(tan, V(0, 1, 0))
        r = 0.0072 * (1.0 + 0.16 * (1 if k % 2 == 0 else -1)) * (1.0 - 0.25 * (k / total) ** 2)
        wb = float(smoothstep(0.30, 0.70, t))
        w = {names[i]: 1 - wb}
        if i < 3:
            w[names[i + 1]] = wb
        else:
            w = {names[i]: 1.0}
        if i > 0 and t < 0.30:
            wa = float(smoothstep(0.0, 0.30, t)) * 0.5 + 0.5
            w = {names[i]: wa, names[i - 1]: 1 - wa}
        pts = [cen + (fr[:, 0] * math.cos(TAU * j / n) + fr[:, 2] * math.sin(TAU * j / n)) * r for j in range(n)]
        rings.append(md.ring(pts, w, tag='cable'))
    for a, b in zip(rings[:-1], rings[1:]):
        md.strip(a, b, CYBER, 'cable', closed=True, flip=True)
    md.fan_cap(rings[0], js[0], {'cable_01': 1.0}, CYBER, 'cable', flip=True)
    # end connector
    me = prim.frame(js[-1] - norm(js[-1] - js[-2]) * 0.004, js[-1] - js[-2], V(0, 1, 0))
    prim.lathe(md, me, [(0.0062, 0.0), (0.0092, 0.003), (0.0092, 0.016), (0.0050, 0.021)], 10, {'cable_04': 1.0}, CYBER, 'cable_plug')


def build_cyber(outfit_info, shape=None):
    md = MeshData('Cyber')
    build_forearm(md)
    build_mech_hand(md)
    blade = build_blade(md)
    build_belt_props(md, outfit_info['belt_frame'])
    if shape is not None:
        build_head_gear(md, shape)
    return {'cyber': md}, dict(blade=blade)

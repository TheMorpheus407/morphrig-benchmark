"""Procedural gait generator for the in-place locomotion loops (8-direction walk / run, sprint).

The body stays over the origin; a planted foot therefore travels opposite to the travel direction at the
nominal speed, exactly linearly, so there is no foot sliding by construction. Phase convention: left foot
contact at phase 0, right foot contact at phase 0.5 (shared by every loop for phase-synchronised blending).
"""
import math
import numpy as np
from . import clips as clipdefs
from .pose import Pose, solve_cog_height, leg_stretch

# direction specific cycle lengths (frames @30 fps). Lateral gaits use a quicker cadence (shorter reach).
CYCLE = {
    'walk': {'f': 32, 'fl': 30, 'fr': 30, 'l': 26, 'r': 26, 'bl': 28, 'br': 28, 'b': 30},
    'run': {'f': 22, 'fl': 22, 'fr': 22, 'l': 20, 'r': 20, 'bl': 20, 'br': 20, 'b': 22},
    'sprint': {'f': 16},
}

STYLE = {
    'walk': dict(beta=0.59, width=0.20, lift=0.060, drop=0.045, bob=0.016, sway=0.016, lean=3.0, hip_yaw=8.0, hip_roll=3.5,
                 arm=20.0, arm_bend=(16.0, 30.0), curl=0.28, kick=10.0, heel=0.55, toe=1.50, counter=0.9, reach=0.33),
    'run': dict(beta=0.29, width=0.12, lift=0.20, drop=0.060, bob=0.030, sway=0.008, lean=10.0, hip_yaw=11.0, hip_roll=4.5,
                arm=36.0, arm_bend=(82.0, 98.0), curl=0.62, kick=62.0, heel=0.10, toe=1.55, counter=1.0, reach=0.21),
    'sprint': dict(beta=0.245, width=0.09, lift=0.30, drop=0.060, bob=0.034, sway=0.004, lean=17.0, hip_yaw=14.0, hip_roll=5.0,
                   arm=56.0, arm_bend=(88.0, 108.0), curl=0.35, kick=85.0, heel=-0.30, toe=1.58, counter=1.0, reach=0.19),
}


def _sm(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _rot2(v, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)       # +deg rotates forward (y) towards -x? see usage


def pelvis_yaw_offset(theta):
    """Pelvis turn towards the travel direction (deg) for travel angle theta (deg, + = left)."""
    a = abs(theta)
    table = [(0, 0.0), (45, 26.0), (90, 40.0), (135, 14.0), (180, 0.0)]
    for (a0, v0), (a1, v1) in zip(table[:-1], table[1:]):
        if a0 <= a <= a1:
            v = v0 + (v1 - v0) * (a - a0) / (a1 - a0)
            return math.copysign(v, theta)
    return 0.0


def gait_poses(kind, theta_deg, speed_cm, frames):
    """Returns list of Pose for frames 0..frames (inclusive, last == first)."""
    st = STYLE[kind]
    N = frames
    T = N / float(clipdefs.FPS)
    v = speed_cm / 100.0
    S = v * T
    beta = st['beta']
    th = math.radians(theta_deg)
    d = np.array([-math.sin(th), math.cos(th)])          # travel dir in (x-left... careful) -> stored as (left, fwd)
    d = np.array([math.sin(th), math.cos(th)])           # (left, forward)
    psi = pelvis_yaw_offset(theta_deg)
    thp = math.radians(theta_deg - psi)                   # travel direction relative to the pelvis
    cf = math.cos(thp)
    sl = math.sin(thp)
    lateral = abs(math.sin(th))
    # quicker, flatter steps when the travel is not along the pelvis
    Ls = beta * S
    reach = st['reach'] * max(cf, 0.0) ** 2 + 0.40 * max(-cf, 0.0) ** 2 + 0.25 * sl * sl
    c_along = reach - Ls / 2.0
    w = st['width']
    psi_r = math.radians(psi)
    lat_axis = np.array([math.cos(psi_r), -math.sin(psi_r)])    # pelvis left axis in (left, fwd): yaw-left turns left axis backwards
    fwd_axis = np.array([math.sin(psi_r), math.cos(psi_r)])
    n_perp = np.array([d[1], -d[0]])                            # right-hand perpendicular of travel
    homes = {}
    for s, sg in (('l', 1.0), ('r', -1.0)):
        homes[s] = lat_axis * (0.092 + (w / 2 - 0.092) * 1.0) * sg + np.array([0.0, -0.02])
    # keep the two tracks apart across the travel direction (cross-over clearance)
    pl, pr = float(np.dot(homes['l'], n_perp)), float(np.dot(homes['r'], n_perp))
    sep_min = 0.135
    if abs(pl - pr) < sep_min:
        sgn = 1.0 if (pl - pr) >= 0 else -1.0
        if abs(pl - pr) < 1e-4:
            sgn = -1.0 if theta_deg >= 0 else 1.0
        add = (sep_min - abs(pl - pr)) / 2.0
        homes['l'] = homes['l'] + n_perp * add * sgn
        homes['r'] = homes['r'] - n_perp * add * sgn
    foot_yaw = psi * 0.85
    toe_out = 6.0
    poses = []
    lift_scale = 1.0 - 0.45 * lateral if kind != 'walk' else 1.0 - 0.15 * lateral
    back = max(-cf, 0.0)
    fwdc = max(cf, 0.0)
    guard = {'f': 0.0, 'fl': 0.45, 'fr': 0.45}.get(_dir_name(theta_deg), 1.0)
    if kind == 'sprint':
        guard = 0.0
    heel_off = 0.56 if kind == 'walk' else 0.38
    follow = 0.30 if kind == 'walk' else 0.16            # how much of the ground speed the foot keeps right after lift-off
    for f in range(N + 1):
        ph = (f % N) / float(N)
        p = Pose()
        # ---------------- feet
        for s, ph0, sg in (('l', 0.0, 1.0), ('r', 0.5, -1.0)):
            u = (ph - ph0) % 1.0
            ft = getattr(p, 'foot_' + s)
            if u < beta:
                sn = u / beta
                along = Ls / 2.0 - Ls * sn
                z = 0.0
                if fwdc >= back:
                    hs = st['heel'] * fwdc
                    if sn < 0.16:
                        roll = -hs * (1 - _sm(sn / 0.16))
                    elif sn < heel_off:
                        roll = 0.0
                    else:
                        roll = (st['toe'] * (0.35 + 0.65 * fwdc ** 0.5)) * _sm((sn - heel_off) / (1.0 - heel_off)) ** 1.2
                else:
                    if sn < 0.28:
                        roll = 0.85 * back * (1 - _sm(sn / 0.28))
                    elif sn < 0.66:
                        roll = 0.0
                    else:
                        roll = -0.55 * back * _sm((sn - 0.66) / 0.34)
                pitch = 0.0
            else:
                sn = (u - beta) / (1.0 - beta)
                m = -Ls * (1.0 - beta) / beta                 # ground speed per unit of swing parameter
                over = min(abs(m) * 0.12, 0.085)               # swing-leg retraction: small overshoot past the contact point
                se = 1.0 - over / max(abs(m), 1e-6)            # after se the foot already travels with the ground
                if sn < se:
                    q = sn / se
                    p0, p1 = -Ls / 2.0, Ls / 2.0 - m * (1.0 - se)
                    mt = m * se
                    h00 = 2 * q ** 3 - 3 * q ** 2 + 1
                    h10 = q ** 3 - 2 * q ** 2 + q
                    h01 = -2 * q ** 3 + 3 * q ** 2
                    h11 = q ** 3 - q ** 2
                    along = h00 * p0 + h10 * (mt * follow) + h01 * p1 + h11 * mt
                else:
                    along = Ls / 2.0 + m * (sn - 1.0)
                zs = min(1.0, sn / 0.97)
                z = st['lift'] * lift_scale * math.sin(math.pi * zs ** (0.62 if kind != 'walk' else 0.85)) ** 1.25
                if fwdc >= back:
                    toe_r = st['toe'] * (0.35 + 0.65 * fwdc ** 0.5)
                    hs = st['heel'] * fwdc
                    roll = toe_r * (1 - _sm(sn / 0.42)) - hs * _sm((sn - 0.70) / 0.30)
                    pitch = -st['kick'] * fwdc * math.sin(math.pi * min(1.0, sn / 0.62)) ** 1.5 * (1 if sn < 0.62 else 0)
                    # never let the toes dip through the ground while they point down
                    lim = math.degrees(math.asin(min(1.0, max(0.0, z - 0.01) / 0.234)))
                    pitch = max(pitch, -lim)
                else:
                    roll = -0.55 * back * (1 - _sm(sn / 0.35)) + 0.85 * back * _sm((sn - 0.62) / 0.38)
                    pitch = 6.0 * math.sin(math.pi * sn)
            xy = homes[s] + d * (c_along + along)
            ft['pos'] = (float(xy[0]), float(xy[1]), float(z))
            ft['yaw'] = foot_yaw + toe_out * sg
            ft['roll'] = float(roll)
            ft['pitch'] = float(pitch)
            kd = fwd_axis * 1.0 + lat_axis * 0.10 * sg
            ft['knee'] = (float(kd[0]), float(kd[1]), 0.0)
        # ---------------- pelvis / cog
        if kind == 'walk':
            bob = -st['bob'] * math.cos(4 * math.pi * ph)
        else:
            bob = -st['bob'] * math.cos(4 * math.pi * (ph - beta / 2.0))
        sway = st['sway'] * math.cos(2 * math.pi * (ph - beta / 2.0))
        sway_v = lat_axis * sway
        sway_v = sway_v - d * float(np.dot(sway_v, d))            # never surge along the travel direction
        lean = st['lean']
        p.cog = (float(sway_v[0]), float(sway_v[1]) + 0.010 * lean / 10.0 * math.cos(th), -st['drop'] - 0.020 * lateral + bob)
        p.cog_rot = (lean * math.cos(th) * (0.75 if back > 0.5 else 1.0), 0.45 * psi, lean * 0.55 * math.sin(th))
        osc = math.cos(2 * math.pi * ph)
        hy = -st['hip_yaw'] * osc * cf
        hr = -st['hip_roll'] * math.cos(2 * math.pi * (ph - beta / 2.0)) * (0.5 + 0.5 * abs(cf))
        p.hips = (2.0 + 1.5 * fwdc, 0.55 * psi + hy, hr)
        cn = st['counter']
        p.spine = (lean * 0.45 * math.cos(th), -0.45 * psi - hy * 0.85 * cn, -hr * 0.8 - lean * 0.25 * math.sin(th))
        p.head = (-lean * 0.75 * math.cos(th), hy * 0.2, -lean * 0.2 * math.sin(th) + hr * 0.25)
        # ---------------- arms (FK, chest space)
        A = st['arm'] * (0.35 + 0.65 * abs(math.cos(th)))
        sgn_dir = 1.0 if math.cos(th) >= -0.2 else -1.0
        for s, ph0 in (('l', 0.5), ('r', 0.0)):          # arm forward with the opposite leg
            sw = A * math.cos(2 * math.pi * (ph - ph0)) * sgn_dir
            a = getattr(p, 'arm_' + s)
            b0, b1 = st['arm_bend']
            fwd_amt = 0.5 + 0.5 * math.sin(math.radians(sw) * 90.0 / max(A, 1.0))
            bend = b0 + (b1 - b0) * (0.5 + 0.5 * sw / max(A, 1.0))
            out = 0.16 if kind == 'walk' else 0.24
            sr = math.radians(sw + (4.0 if kind == 'walk' else 10.0))
            relaxed = dict(upper=(out, math.sin(sr), -math.cos(sr)), bend=bend, hint=(-0.25 if kind != 'walk' else 0.0, 1.0, 0.25 if kind != 'walk' else 0.0),
                           hand=(0.0, 0.0, 0.0 if kind == 'walk' else 10.0))
            sg2 = math.radians(sw * 0.35 + 22.0)
            guardp = dict(upper=(0.26, math.sin(sg2), -math.cos(sg2)), bend=86.0 + 6.0 * math.cos(2 * math.pi * (ph - ph0)),
                          hint=(-0.35, 1.0, 0.55), hand=(0.0, 0.0, 12.0))
            for k in ('upper', 'hint', 'hand'):
                a[k] = tuple(relaxed[k][i] * (1 - guard) + guardp[k][i] * guard for i in range(3))
            a['bend'] = relaxed['bend'] * (1 - guard) + guardp['bend'] * guard
            a['ik'] = False
            cl = 2.0 * math.cos(2 * math.pi * (ph - ph0)) * (1.0 if kind != 'walk' else 0.5)
            setattr(p, 'clav_' + s, (1.0 + (2.0 if kind != 'walk' else 0.0), cl))
            fg = getattr(p, 'fing_' + s)
            fg['curl'] = st['curl'] * (1 - guard) + 0.5 * guard
            fg['thumb'] = fg['curl'] * 0.6
        p.breath = 0.35 * math.sin(2 * math.pi * ph) if kind != 'walk' else 0.2 * math.sin(2 * math.pi * ph)
        p.look = (0.0, 6.0, 1.66)
        if kind != 'walk':
            p.face = {'expr_focus': 0.6, 'jaw_open': 0.06 if kind == 'run' else 0.12}
        poses.append(p)
    poses[-1] = poses[0].copy()
    drop = solve_cog_height(poses[:-1], limit=0.982, smooth=3, loop=True)
    poses[-1] = poses[0].copy()
    return poses, dict(stance_len=Ls, stride=S, beta=beta, psi=psi, max_drop=float(drop.max()), contact_l=0, contact_r=int(round(N / 2)))


def _dir_name(theta):
    for k, v in clipdefs.DIRS.items():
        if abs(((theta - v + 180) % 360) - 180) < 1.0:
            return k
    return 'f'


def build_gait_clip(clip):
    meta = clip.meta
    kind = meta['gait']
    dname = clip.id.split('_')[1]
    N = CYCLE[kind][dname]
    clip.frames = N
    poses, info = gait_poses(kind, meta['travel_dir_deg'], meta['nominal_speed'], N)
    for f, p in enumerate(poses):
        p.apply(clip, f, dense=True)
    clip.events_replace([('foot_l_contact', 0), ('foot_r_contact', int(round(N / 2)))])
    clip.notes.update(info)
    return info

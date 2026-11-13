"""Organic left hand: palm tube continuing the fore-arm ring, four finger tubes branching from the knuckle
ring through shared web vertices, thumb branching from a palm-side hole. Fingerless glove hem included."""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, bump, TAU
from . import skel
from .skel import J, FINGERS, THUMB, HAND_D, HAND_T, HAND_P, hand_pt
from .meshkit import MeshData

SKIN = 'M_Skin'
SUIT = 'M_Suit'
GLOVE_T = 0.0022

PALM = [  # (d along hand, half width (t), half thickness (p), t centre shift)
    (0.018, 0.0300, 0.0172, 0.0010), (0.042, 0.0375, 0.0155, 0.0015), (0.066, 0.0412, 0.0140, -0.0010)]


def _sec(hw, hp, ang, n=3.2):
    """Palm section radius components for ring angle (0 = dorsal, 90 = radial/thumb side, 180 = palmar)."""
    c, s = math.cos(ang), math.sin(ang)
    e = 2.0 / n
    return (-(np.sign(c) * abs(c) ** e) * hp, (np.sign(s) * abs(s) ** e) * hw)     # (p component, t component)


def tube_from_loop(md, loop_idx, axis_pts, radii, weights, mat, tag, z_ref, flatten=1.0, settle=2, cap=True, flip=False,
                   mats=None):
    """Continue a tube from an existing vertex loop along axis points.
    radii: per axis point radius; weights: per axis point weight dict; z_ref: reference 'dorsal' direction."""
    n = len(loop_idx)
    P0 = md.pos(loop_idx)
    a0 = np.asarray(axis_pts[0], float)
    T0 = norm(np.asarray(axis_pts[1], float) - a0)
    e1 = norm(np.asarray(z_ref, float) - T0 * np.dot(z_ref, T0))
    e2 = np.cross(T0, e1)
    rel = P0 - P0.mean(axis=0)
    ang0 = np.arctan2(rel @ e2, rel @ e1)
    # unwrap so that the angles are monotonic around the loop
    ang0 = np.unwrap(ang0)
    direction = 1.0 if ang0[-1] > ang0[0] else -1.0
    uniform = ang0[0] + direction * TAU * np.arange(n) / n
    rings = [list(loop_idx)]
    for k in range(1, len(axis_pts)):
        c = np.asarray(axis_pts[k], float)
        prev = np.asarray(axis_pts[k - 1], float)
        nxt = np.asarray(axis_pts[min(k + 1, len(axis_pts) - 1)], float)
        T = norm(nxt - prev)
        f1 = norm(e1 - T * np.dot(e1, T))
        f2 = np.cross(T, f1)
        blend = min(1.0, k / float(settle))
        ang = ang0 * (1 - blend) + uniform * blend
        r = radii[k]
        pts = [c + (math.cos(a) * f1 * flatten + math.sin(a) * f2) * r for a in ang]
        rings.append(md.ring(pts, weights[k], tag=tag))
    for i, (a, b) in enumerate(zip(rings[:-1], rings[1:])):
        m = mats[i] if mats else mat
        md.strip(a, b, m, tag, closed=True, flip=flip)
    if cap:
        md.grid_cap(rings[-1], mats[-1] if mats else mat, tag, flip=not flip)
    return rings


def build_hand(md, wrist_ring, side='l'):
    """Append the organic hand to md starting from the arm's wrist ring (20 vertices). Returns info."""
    assert side == 'l'
    L = lambda n: n + '_' + side
    info = {}
    W = J['hand_l']
    wh = {L('hand'): 1.0}

    def pt(d, t, p):
        return W + d * HAND_D + t * HAND_T + p * HAND_P

    # ---------------- palm rings (glove thickness applied)
    rings = [list(wrist_ring)]
    for (d, hw, hp, ts) in PALM:
        pts = []
        for m in range(20):
            ang = TAU * m / 20
            pc, tc = _sec(hw + GLOVE_T, hp + GLOVE_T, ang)
            pts.append(pt(d, tc + ts, pc))
        rings.append(md.ring(pts, wh, tag='palm'))
    # ---------------- knuckle ring (skin level) built from the finger layout
    fnames = ['index', 'middle', 'ring', 'pinky']
    mcp = {f: np.array(FINGERS[f][0]) for f in fnames}          # (d, t, p)
    fdir = {f: norm(np.array(FINGERS[f][1])) for f in fnames}
    rad = {f: FINGERS[f][3] for f in fnames}
    L1 = {f: FINGERS[f][2][0] for f in fnames}

    def fpt(f, s, t_off, p_off):
        """point at distance s along finger f from its MCP with lateral (t) and palmar (p) offsets (hand frame)."""
        c = mcp[f] + fdir[f] * s
        return pt(c[0], c[1] + t_off, c[2] + p_off)

    kn = [None] * 20
    # dorsal: D0..D8 -> ring indices 4,3,2,1,0,19,18,17,16 ; palmar P0..P8 -> 6..14
    d_idx = [4, 3, 2, 1, 0, 19, 18, 17, 16]
    p_idx = [6, 7, 8, 9, 10, 11, 12, 13, 14]
    # lateral positions of the 9 dorsal columns: finger edges / centres / shared web columns
    cols = []
    for i, f in enumerate(fnames):
        r = rad[f] * 1.08
        if i == 0:
            cols.append((f, +r))
        cols.append((f, 0.0))
        if i < 3:
            nf = fnames[i + 1]
            cols.append((('web', f, nf), None))
        else:
            cols.append((f, -r))
    for k, (f, off) in enumerate(cols):
        if isinstance(f, tuple):
            _, fa, fb = f
            a = fpt(fa, 0.10 * L1[fa], -rad[fa] * 1.02, -rad[fa] * 0.80)
            b = fpt(fb, 0.10 * L1[fb], +rad[fb] * 1.02, -rad[fb] * 0.80)
            dpos = (a + b) * 0.5
            a = fpt(fa, 0.52 * L1[fa], -rad[fa] * 1.02, rad[fa] * 0.92)
            b = fpt(fb, 0.52 * L1[fb], +rad[fb] * 1.02, rad[fb] * 0.92)
            ppos = (a + b) * 0.5
            wd = {L('hand'): 0.5, L(fa + '_01'): 0.25, L(fb + '_01'): 0.25}
            wp = {L('hand'): 0.3, L(fa + '_01'): 0.35, L(fb + '_01'): 0.35}
        else:
            dpos = fpt(f, 0.10 * L1[f], off * 0.92, -rad[f] * (1.05 if off == 0 else 0.80))
            ppos = fpt(f, 0.52 * L1[f], off * 0.92, rad[f] * (1.0 if off == 0 else 0.80))
            wd = {L('hand'): 0.5, L(f + '_01'): 0.5}
            wp = {L('hand'): 0.25, L(f + '_01'): 0.75}
        kn[d_idx[k]] = md.vert(dpos, wd, 'knuckle')
        kn[p_idx[k]] = md.vert(ppos, wp, 'knuckle')
    # side mids: R (index radial), U (pinky ulnar)
    kn[5] = md.vert(fpt('index', 0.30 * L1['index'], rad['index'] * 1.02, 0.0), {L('hand'): 0.4, L('index_01'): 0.6}, 'knuckle')
    kn[15] = md.vert(fpt('pinky', 0.30 * L1['pinky'], -rad['pinky'] * 1.02, 0.0), {L('hand'): 0.4, L('pinky_01'): 0.6}, 'knuckle')
    # glove hem: duplicate of the last palm ring at skin level, then the knuckle ring
    last = rings[-1]
    d, hw, hp, ts = PALM[-1]
    hem = []
    for m in range(20):
        ang = TAU * m / 20
        pc, tc = _sec(hw, hp, ang)
        hem.append(pt(d + 0.0035, tc + ts, pc))
    hem_ring = md.ring(hem, wh, tag='palm')
    rings.append(hem_ring)
    rings.append(kn)
    # ---------------- palm faces with the thumb hole (rings index 1..3 = PALM rings B, C, D)
    hole = {(1, 4), (1, 5), (2, 4), (2, 5)}
    for i in range(len(rings) - 1):
        skip = {m for m in range(20) if (i, m) in hole}
        if i < 3:
            mat, tag = SUIT, 'glove'
        elif i == 3:
            mat, tag = SUIT, 'glove_hem'
        else:
            mat, tag = SKIN, 'hand'
        md.strip(rings[i], rings[i + 1], mat, tag, closed=True, flip=False, skip=skip)
    info['palm_rings'] = rings

    # ---------------- web vertices and finger tubes
    webs = []
    for i in range(3):
        fa, fb = fnames[i], fnames[i + 1]
        a = fpt(fa, 0.46 * L1[fa], -rad[fa] * 1.0, 0.0)
        b = fpt(fb, 0.46 * L1[fb], +rad[fb] * 1.0, 0.0)
        webs.append(md.vert((a + b) * 0.5, {L('hand'): 0.4, L(fa + '_01'): 0.3, L(fb + '_01'): 0.3}, 'web'))
    loops = {
        'index': [kn[4], kn[3], kn[2], webs[0], kn[8], kn[7], kn[6], kn[5]],
        'middle': [kn[2], kn[1], kn[0], webs[1], kn[10], kn[9], kn[8], webs[0]],
        'ring': [kn[0], kn[19], kn[18], webs[2], kn[12], kn[11], kn[10], webs[1]],
        'pinky': [kn[18], kn[17], kn[16], kn[15], kn[14], kn[13], kn[12], webs[2]],
    }
    dorsal = -HAND_P
    info['finger_rings'] = {}
    for f in fnames:
        j1, j2, j3, je = J[L(f + '_01')], J[L(f + '_02')], J[L(f + '_03')], J[f + '_end_' + side]
        l1, l2, l3 = FINGERS[f][2]
        rb, rt = FINGERS[f][3], FINGERS[f][4]
        ax = norm(je - j1)
        stations = [0.0, 0.66 * l1, l1 - 0.0055, l1, l1 + 0.0055, l1 + 0.5 * l2, l1 + l2 - 0.0045, l1 + l2,
                    l1 + l2 + 0.0045, l1 + l2 + 0.55 * l3, l1 + l2 + 0.86 * l3, l1 + l2 + l3 - 0.0012]
        tot = l1 + l2 + l3
        pts, rr, ww = [], [], []
        for s in stations:
            pts.append(j1 + ax * s)
            r = lerp(rb, rt, (s / tot) ** 1.2)
            r *= 1.0 + 0.07 * (float(bump(s, l1, 0.008)) + float(bump(s, l1 + l2, 0.007)))
            if s > l1 + l2 + 0.5 * l3:
                r *= math.sqrt(max(1.0 - ((s - (l1 + l2 + 0.5 * l3)) / (0.56 * l3)) ** 2, 0.05))
            rr.append(r)
            w12 = float(smoothstep(l1 - 0.006, l1 + 0.006, s))
            w23 = float(smoothstep(l1 + l2 - 0.005, l1 + l2 + 0.005, s))
            ww.append({L(f + '_01'): (1 - w12), L(f + '_02'): w12 * (1 - w23), L(f + '_03'): w12 * w23})
        rings_f = tube_from_loop(md, loops[f], pts, rr, ww, SKIN, 'finger_' + f, dorsal, flatten=0.90, settle=1, flip=True)
        info['finger_rings'][f] = rings_f

    # ---------------- thumb
    t1, t2, t3, te = J[L('thumb_01')], J[L('thumb_02')], J[L('thumb_03')], J['thumb_end_' + side]
    l1, l2, l3 = THUMB[2]
    rb, rt = THUMB[3], THUMB[4]
    loop = [rings[1][4], rings[1][5], rings[1][6], rings[2][6], rings[3][6], rings[3][5], rings[3][4], rings[2][4]]
    ax = norm(te - t1)
    stations = [0.0, 0.30 * l1, 0.62 * l1, l1 - 0.006, l1, l1 + 0.006, l1 + 0.5 * l2, l1 + l2 - 0.005, l1 + l2,
                l1 + l2 + 0.005, l1 + l2 + 0.55 * l3, l1 + l2 + 0.86 * l3, l1 + l2 + l3 - 0.0012]
    tot = l1 + l2 + l3
    pts, rr, ww, mats = [], [], [], []
    for i, s in enumerate(stations):
        pts.append(t1 + ax * s)
        r = lerp(rb * 1.28, rb, min(1.0, s / l1)) if s < l1 else lerp(rb, rt, ((s - l1) / (l2 + l3)) ** 1.1)
        r *= 1.0 + 0.06 * (float(bump(s, l1, 0.009)) + float(bump(s, l1 + l2, 0.008)))
        if i == 1:
            r += GLOVE_T
        if s > l1 + l2 + 0.5 * l3:
            r *= math.sqrt(max(1.0 - ((s - (l1 + l2 + 0.5 * l3)) / (0.56 * l3)) ** 2, 0.05))
        rr.append(r)
        wb = float(smoothstep(-0.004, 0.016, s))
        w12 = float(smoothstep(l1 - 0.007, l1 + 0.007, s))
        w23 = float(smoothstep(l1 + l2 - 0.006, l1 + l2 + 0.006, s))
        ww.append({L('hand'): (1 - wb), L('thumb_01'): wb * (1 - w12), L('thumb_02'): wb * w12 * (1 - w23), L('thumb_03'): wb * w12 * w23})
    mats = [SUIT, SUIT] + [SKIN] * (len(stations) - 2)
    zref = norm(-HAND_P * 0.6 + HAND_T * 0.8)
    rings_t = tube_from_loop(md, loop, pts, rr, ww, SKIN, 'thumb', zref, flatten=0.92, settle=2, flip=True, mats=mats)
    for vi in loop:
        w = dict(md.w[vi])
        md.w[vi] = {L('hand'): 0.72, L('thumb_01'): 0.28}
    info['thumb_rings'] = rings_t
    # seams: glove hem and a palm-side line so the hand unwraps into dorsal / palmar halves
    md.seam_path(rings[3], closed=True)
    md.seam_path([r[15] for r in rings])
    return info

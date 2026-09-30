"""Cybernetic left arm assembly (socket flange, muscle core, elbow joint, forearm shell, wrist emitter, blade sheath and
blade, power-cell slot, mechanical hand). Built from hs.py primitives; every Part is tied to a deformation bone."""
import math
import numpy as np
import skeleton_def as S
import hs
from hs import Part

A = np.array


def _n(v):
    v = A(v, float)
    return v / np.linalg.norm(v)


UA = _n(S.UPPERARM_DIR)
FA = _n(S.FOREARM_DIR)
HD = _n(S.HAND_DIR)
PN = _n(S.PALM_NORMAL)          # palm normal (toward the body)
DORSAL = -PN
SH, EL, WR = A(S.SHOULDER), A(S.ELBOW), A(S.WRIST)
FRONT = _n(A([1.0, 0, 0]) - FA * (FA[0]))     # forearm front side (+X, made perpendicular to the forearm axis)
OUT = _n(A([0, 1.0, 0]) - FA * FA[1])          # outward (away from the body)
SOCKET = SH + (EL - SH) * 0.62
BLADE_LEN = 0.26
BLADE_EXT = 0.22


def add(parts, name, vf, bone, mat='cyber', emit=0.0, accent=0.0):
    v, f = vf
    parts.append(Part(name, v, f, mat=mat, bone=bone, emit=emit, accent=accent))


def build_cyber_arm():
    parts = []
    # ------------------------------------------------------------------ shoulder socket flange and upper section
    ua_frame = hs.frame(UA, FRONT)
    add(parts, 'socket_flange', hs.cylinder(SOCKET - UA * 0.016, SOCKET + UA * 0.010, 0.0575, 0.0575, n=20, rings=2, z_hint=FRONT), 'upperarm_l', 'armor')
    add(parts, 'socket_ring', hs.cylinder(SOCKET + UA * 0.010, SOCKET + UA * 0.017, 0.0545, 0.0545, n=20, z_hint=FRONT), 'upperarm_l', 'cyber', emit=1.0, accent=1.0)
    # muscle core between the bands (flexible: hat-weighted along the upper arm)
    core = hs.cylinder(SOCKET + UA * 0.017, EL - UA * 0.030, 0.038, 0.034, n=14, rings=6, z_hint=FRONT)
    parts.append(Part('upper_core', core[0], core[1], mat='cyber', bone=None, flex='upperarm'))
    for k, (a, b) in enumerate(((0.030, 0.062), (0.078, 0.108))):
        add(parts, f'upper_band_{k}', hs.cylinder(SOCKET + UA * a, SOCKET + UA * b, 0.0485 - 0.002 * k, 0.0485 - 0.002 * k - 0.001, n=18, rings=2, z_hint=FRONT),
            'upperarm_twist_02_l', 'cyber')
    # ------------------------------------------------------------------ elbow joint
    hinge = _n(np.cross(UA, FA))
    add(parts, 'elbow_ball', hs.sphere(EL, (0.046, 0.046, 0.046), 18, 12), 'elbow_half_l', 'cyber')
    add(parts, 'elbow_pin', hs.cylinder(EL - hinge * 0.058, EL + hinge * 0.058, 0.0125, n=14, z_hint=FA), 'elbow_half_l', 'armor')
    add(parts, 'elbow_cap_a', hs.cylinder(EL + hinge * 0.052, EL + hinge * 0.062, 0.020, n=14, z_hint=FA), 'elbow_half_l', 'cyber', emit=1.0, accent=1.0)
    add(parts, 'elbow_cap_b', hs.cylinder(EL - hinge * 0.062, EL - hinge * 0.052, 0.020, n=14, z_hint=FA), 'elbow_half_l', 'cyber', emit=0.6)
    # ------------------------------------------------------------------ forearm shell (lofted superellipse rings)
    fr = hs.frame(FA, DORSAL)                  # local Z ~ dorsal, X across
    rings = []
    stations = [(0.030, 0.049, 0.047), (0.075, 0.050, 0.048), (0.130, 0.046, 0.045), (0.190, 0.040, 0.040), (0.240, 0.034, 0.034)]
    for s_, rz_, rx_ in stations:
        rings.append(hs.ring_points(EL + FA * s_, fr, rx_, rz_, n=20, exp=2.7))
    shell = hs.loft(rings, True, False)
    add(parts, 'forearm_shell', shell, 'lowerarm_l', 'cyber')
    # dorsal armour plate with emissive strip
    dplate = hs.rounded_box((0.052, 0.118, 0.010), fr, EL + FA * 0.125 + DORSAL * 0.049, seg=3, round_=0.35)
    add(parts, 'dorsal_plate', dplate, 'lowerarm_l', 'armor')
    add(parts, 'dorsal_strip', hs.rounded_box((0.010, 0.100, 0.004), fr, EL + FA * 0.125 + DORSAL * 0.0555, seg=2, round_=0.5), 'lowerarm_l', 'cyber', emit=1.0, accent=1.0)
    for k, s_ in enumerate((0.150, 0.170, 0.190)):
        add(parts, f'vent_{k}', hs.rounded_box((0.030, 0.008, 0.006), fr, EL + FA * s_ - fr[:, 0] * 0.0 + PN * 0.046, seg=2, round_=0.4), 'lowerarm_l', 'armor')
    # wrist roll ring (partial twist) and cable connector
    add(parts, 'wrist_ring', hs.cylinder(WR - FA * 0.028, WR - FA * 0.004, 0.0335, 0.0325, n=20, rings=2, z_hint=DORSAL), 'lowerarm_twist_02_l', 'armor')
    add(parts, 'wrist_ring_light', hs.cylinder(WR - FA * 0.004, WR + FA * 0.004, 0.0335, 0.0335, n=20, z_hint=DORSAL), 'lowerarm_twist_02_l', 'cyber', emit=1.0, accent=1.0)
    add(parts, 'cable_port', hs.rounded_box((0.024, 0.022, 0.016), fr, EL - FA * 0.020 - DORSAL * 0.030 + OUT * 0.0, seg=3, round_=0.3), 'elbow_half_l', 'armor')
    # ------------------------------------------------------------------ power-cell slot (front side of the forearm)
    slot_c = EL + FA * 0.150 + FRONT * 0.044
    sfr = hs.frame(FA, FRONT)
    for k, (off, size) in enumerate(((0.0, (0.052, 0.104, 0.008)), )):
        add(parts, 'cell_slot_floor', hs.rounded_box((0.052, 0.110, 0.008), sfr, slot_c + FRONT * 0.004, seg=3, round_=0.3), 'lowerarm_l', 'armor')
    for sgn in (-1, 1):
        add(parts, f'cell_slot_rail_{sgn}', hs.rounded_box((0.006, 0.110, 0.022), sfr, slot_c + sfr[:, 0] * sgn * 0.024 + FRONT * 0.014, seg=2, round_=0.3), 'lowerarm_l', 'armor')
    add(parts, 'cell_slot_end', hs.rounded_box((0.052, 0.006, 0.020), sfr, slot_c - FA * 0.052 + FRONT * 0.014, seg=2, round_=0.3), 'lowerarm_l', 'armor')
    # ------------------------------------------------------------------ blade sheath (hollow rectangular tube) and blade
    ofr = hs.frame(FA, OUT)
    sheath_c0 = EL + FA * 0.020 + OUT * 0.046
    L_sh = 0.235
    for name, off, size in (('sheath_top', OUT * 0.0135, (0.030, L_sh, 0.004)), ('sheath_bot', -OUT * 0.0135, (0.030, L_sh, 0.004))):
        add(parts, name, hs.rounded_box(size, ofr, sheath_c0 + FA * (L_sh / 2) + off, seg=2, round_=0.2), 'lowerarm_l', 'armor')
    for sgn in (-1, 1):
        add(parts, f'sheath_side_{sgn}', hs.rounded_box((0.004, L_sh, 0.027), ofr, sheath_c0 + FA * (L_sh / 2) + ofr[:, 0] * sgn * 0.0135, seg=2, round_=0.2), 'lowerarm_l', 'armor')
    add(parts, 'sheath_lip', hs.rounded_box((0.036, 0.008, 0.032), ofr, sheath_c0 + FA * (L_sh + 0.004), seg=2, round_=0.3), 'lowerarm_l', 'cyber', emit=0.8, accent=1.0)
    # blade: tapered slab, base at the blade bone head; retracted it sits inside the sheath
    br = []
    fr_b = hs.frame(FA, OUT)
    spec = [(0.0, 0.0105, 0.0022), (0.10, 0.0105, 0.0022), (0.19, 0.0100, 0.0018), (0.235, 0.0070, 0.0012), (0.258, 0.0025, 0.0006)]
    base = EL + FA * 0.024 + OUT * 0.046
    for t_, w_, th_ in spec:
        br.append(hs.ring_points(base + FA * t_, fr_b, w_, th_, n=12, exp=4.0))
    blade = hs.loft(br, True, True)
    add(parts, 'blade', blade, 'blade', 'cyber', emit=0.7, accent=1.0)
    # ------------------------------------------------------------------ wrist emitter (skinned to the hand)
    hfr = hs.frame(HD, DORSAL)
    e_c = WR + HD * 0.036 + DORSAL * 0.034
    add(parts, 'emitter_housing', hs.rounded_box((0.044, 0.064, 0.026), hfr, e_c, seg=3, round_=0.4), 'hand_l', 'armor')
    add(parts, 'emitter_barrel', hs.cylinder(e_c + HD * 0.020, e_c + HD * 0.092, 0.0105, 0.0100, n=16, rings=2, z_hint=DORSAL), 'hand_l', 'cyber')
    add(parts, 'emitter_lens', hs.cylinder(e_c + HD * 0.088, e_c + HD * 0.094, 0.0125, 0.0125, n=16, z_hint=DORSAL), 'hand_l', 'cyber', emit=1.0, accent=1.0)
    add(parts, 'emitter_strip', hs.rounded_box((0.006, 0.050, 0.004), hfr, e_c + DORSAL * 0.0135 + HD * 0.0, seg=2, round_=0.5), 'hand_l', 'cyber', emit=1.0, accent=1.0)
    # ------------------------------------------------------------------ mechanical hand
    palm_c = WR + HD * 0.050 + PN * 0.002
    add(parts, 'palm', hs.rounded_box((0.074, 0.094, 0.026), hfr, palm_c, seg=4, round_=0.35), 'hand_l', 'cyber')
    add(parts, 'palm_plate', hs.rounded_box((0.058, 0.066, 0.006), hfr, palm_c + DORSAL * 0.014, seg=3, round_=0.35), 'hand_l', 'armor')
    add(parts, 'palm_light', hs.rounded_box((0.020, 0.020, 0.003), hfr, palm_c + PN * 0.0145, seg=2, round_=0.5), 'hand_l', 'cyber', emit=1.0, accent=1.0)
    for fname in ('index', 'middle', 'ring', 'pinky'):
        b0 = S.BONE_BY_NAME[f'{fname}_metacarpal_l']
        b1 = S.BONE_BY_NAME[f'{fname}_01_l']
        p_mcp = A(b1.head)
        add(parts, f'{fname}_knuckle', hs.sphere(p_mcp, (0.0075, 0.0075, 0.0075), 10, 7), f'{fname}_metacarpal_l', 'armor')
        for i in (1, 2, 3):
            bn = S.BONE_BY_NAME[f'{fname}_{i:02d}_l']
            h, t = A(bn.head), A(bn.tail)
            d = t - h
            L = np.linalg.norm(d)
            fr_f = hs.frame(d, DORSAL)
            wd = (0.0128, 0.0118, 0.0104)[i - 1]
            th = (0.0118, 0.0108, 0.0096)[i - 1]
            c = (h + t) / 2
            add(parts, f'{fname}_seg{i}', hs.rounded_box((wd, L * 0.90, th), fr_f, c, seg=3, round_=0.45), bn.name, 'cyber' if i != 3 else 'armor')
            if i < 3:
                add(parts, f'{fname}_pin{i}', hs.cylinder(t - fr_f[:, 0] * wd * 0.55, t + fr_f[:, 0] * wd * 0.55, 0.0038, n=8, z_hint=d), bn.name, 'armor')
        tip = A(S.BONE_BY_NAME[f'{fname}_03_l'].tail)
        add(parts, f'{fname}_tip', hs.sphere(tip, (0.0055, 0.0055, 0.0055), 8, 6), f'{fname}_03_l', 'cyber', emit=0.8)
    for i in (1, 2, 3):
        bn = S.BONE_BY_NAME[f'thumb_{i:02d}_l']
        h, t = A(bn.head), A(bn.tail)
        d = t - h
        L = np.linalg.norm(d)
        fr_f = hs.frame(d, DORSAL)
        wd = (0.0150, 0.0135, 0.0118)[i - 1]
        th = (0.0135, 0.0122, 0.0108)[i - 1]
        add(parts, f'thumb_seg{i}', hs.rounded_box((wd, L * 0.90, th), fr_f, (h + t) / 2, seg=3, round_=0.45), bn.name, 'cyber' if i != 3 else 'armor')
        if i < 3:
            add(parts, f'thumb_pin{i}', hs.cylinder(t - fr_f[:, 0] * wd * 0.55, t + fr_f[:, 0] * wd * 0.55, 0.0040, n=8, z_hint=d), bn.name, 'armor')
    return parts


if __name__ == '__main__':
    ps = build_cyber_arm()
    v, f, pi, em, ac = hs.merge_parts(ps)
    print('parts', len(ps), 'verts', len(v), 'tris', sum(len(x) - 2 for x in f))

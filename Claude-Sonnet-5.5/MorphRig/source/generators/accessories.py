"""Operative accessories: boots, armor, collar, belt and pouches, straps, wrist bracer, braid, cable, props.
Everything returns lists of hs.Part (verts, faces, material tag, rigid bone or flexible rule)."""
import math
import numpy as np
import skeleton_def as S
import mr_geo as G
import hs
from hs import Part

A = np.array


def _n(v):
    v = A(v, float)
    return v / np.linalg.norm(v)


def mirror_part(p, suffix_from='_l', suffix_to='_r'):
    v = p.verts.copy()
    v[:, 1] *= -1
    f = [tuple(reversed(x)) for x in p.faces]
    bone = p.bone
    if bone and bone.endswith(suffix_from):
        bone = bone[: -len(suffix_from)] + suffix_to
    q = Part(p.name + '_r', v, f, p.mat, bone, p.emit, p.accent, p.flex)
    return q


def revolve(profile, center, axis, z_hint, n=32, sx=1.0, sz=1.0, close_start=False, close_end=False):
    """Revolve (radius, height-along-axis) profile points around an axis with optional elliptical scaling (sx, sz)."""
    R = hs.frame(axis, z_hint)
    rings = []
    for r, h in profile:
        pts = []
        for m in range(n):
            a = 2 * math.pi * m / n
            pts.append(A(center) + R @ A([r * sx * math.cos(a), h, r * sz * math.sin(a)]))
        rings.append(A(pts))
    return hs.loft(rings, close_start, close_end)


def arc_plate(center, R, rx, rz, a0, a1, y0, y1, thick=0.006, n=12, bevel=0.0):
    """Curved plate: elliptical arc (angles a0..a1 degrees in the local XZ plane of R, Y along the axis) between y0..y1."""
    outer, inner = [], []
    rows = 3
    for j in range(rows):
        y = y0 + (y1 - y0) * j / (rows - 1)
        # taper the edge rows for a bevelled look
        e = 1.0 - bevel * (1 - math.sin(math.pi * j / (rows - 1)))
        o, i_ = [], []
        for m in range(n):
            a = math.radians(a0 + (a1 - a0) * m / (n - 1))
            th = thick * (1.0 if 0 < m < n - 1 else 0.6)
            o.append(A(center) + R @ A([(rx + th * 0.5) * math.cos(a) * e, y, (rz + th * 0.5) * math.sin(a) * e]))
            i_.append(A(center) + R @ A([(rx - th * 0.5) * math.cos(a) * e, y, (rz - th * 0.5) * math.sin(a) * e]))
        outer.append(o)
        inner.append(i_)
    verts = np.array([p for row in outer for p in row] + [p for row in inner for p in row])
    nn = rows * n
    faces = []
    for j in range(rows - 1):
        for m in range(n - 1):
            a, b, c, d = j * n + m, j * n + m + 1, (j + 1) * n + m + 1, (j + 1) * n + m
            faces.append((a, b, c, d))
            faces.append((nn + d, nn + c, nn + b, nn + a))
    for m in range(n - 1):     # long edges
        faces.append((m, nn + m, nn + m + 1, m + 1))
        j = rows - 1
        faces.append(((j) * n + m + 1, nn + j * n + m + 1, nn + j * n + m, j * n + m))
    for j in range(rows - 1):  # end edges
        faces.append((j * n, (j + 1) * n, nn + (j + 1) * n, nn + j * n))
        faces.append((j * n + n - 1, nn + j * n + n - 1, nn + (j + 1) * n + n - 1, (j + 1) * n + n - 1))
    return verts, G.fix_winding(verts, faces)


# ----------------------------------------------------------------------------- boots

def boots():
    parts = []
    ank = A(S.ANKLE)
    cy = ank[1]
    # shaft
    stations = [(0.365, 0.064, 0.059, 0.014), (0.31, 0.061, 0.057, 0.010), (0.23, 0.055, 0.051, 0.004), (0.15, 0.057, 0.053, -0.001), (0.085, 0.064, 0.057, -0.006)]
    rings = []
    fr = hs.frame((0, 0, 1), (1, 0, 0))
    for z, rx, ry, cx in stations:
        rings.append(hs.ring_points(A([cx, cy, z]), fr, ry, rx, n=24, exp=2.5))
    v, f = hs.loft(rings, True, False)
    parts.append(Part('boot_shaft_l', v, f, 'armor', flex='boot'))
    # cuff ring (accent), covers the open top edge
    prof = [(0.0655, -0.012), (0.0685, -0.004), (0.0685, 0.010), (0.0640, 0.016), (0.0595, 0.012), (0.0590, -0.004)]
    v, f = revolve([(r, h + 0.365) for r, h in prof], A([0.014, cy, 0.0]), (0, 0, 1), (1, 0, 0), n=28, sx=1.0, sz=0.93)
    parts.append(Part('boot_cuff_l', v, f, 'cyber', flex='boot', emit=0.0, accent=1.0))
    # foot upper, rings along X
    xs = [-0.092, -0.062, -0.022, 0.030, 0.082, 0.130, 0.176, 0.216]
    hw = [0.040, 0.053, 0.054, 0.053, 0.056, 0.058, 0.052, 0.040]
    top = [0.072, 0.108, 0.118, 0.094, 0.072, 0.060, 0.052, 0.045]
    bot = [0.034, 0.030, 0.030, 0.030, 0.030, 0.034, 0.044, 0.056]
    fr = hs.frame((1, 0, 0), (0, 0, 1))
    rings = []
    for x, w, t, b in zip(xs, hw, top, bot):
        rings.append(hs.ring_points(A([x, cy, (t + b) / 2]), fr, w, (t - b) / 2, n=20, exp=3.0))
    v, f = hs.loft(rings, True, True)
    parts.append(Part('boot_foot_l', v, f, 'armor', flex='boot'))
    # sole slab
    fr = hs.frame((1, 0, 0), (0, 0, 1))
    sx = [-0.100, -0.075, 0.0, 0.08, 0.15, 0.205, 0.228]
    sw = [0.036, 0.050, 0.056, 0.058, 0.056, 0.048, 0.030]
    rings = [hs.ring_points(A([x, cy, 0.0165]), fr, w, 0.0165, n=16, exp=5.0) for x, w in zip(sx, sw)]
    for k in range(len(sx)):
        z_lift = 0.0 if sx[k] < 0.16 else 0.010 * ((sx[k] - 0.16) / 0.07) ** 2
        rings[k][:, 2] += z_lift
    v, f = hs.loft(rings, True, True)
    parts.append(Part('boot_sole_l', v, f, 'cyber', flex='boot', accent=0.6))
    # toe cap and heel block
    v, f = hs.rounded_box((0.060, 0.098, 0.040), None, A([0.190, cy, 0.062]), seg=3, round_=0.5)
    parts.append(Part('boot_toecap_l', v, f, 'armor', flex='boot'))
    v, f = hs.rounded_box((0.040, 0.086, 0.050), None, A([-0.078, cy, 0.062]), seg=3, round_=0.45)
    parts.append(Part('boot_heel_l', v, f, 'armor', flex='boot'))
    # emissive strip on the outer side of the boot
    v, f = hs.rounded_box((0.090, 0.003, 0.010), None, A([0.020, cy + 0.0575, 0.078]), seg=2, round_=0.5)
    parts.append(Part('boot_strip_l', v, f, 'cyber', flex='boot', emit=1.0, accent=1.0))
    parts += [mirror_part(p) for p in list(parts)]
    return parts


# ----------------------------------------------------------------------------- torso armour, collar, belt, straps

def torso_parts():
    parts = []
    fr_up = hs.frame((0, 0, 1), (1, 0, 0))     # local X = (0,-1,0)... use explicit ellipse radii in world XY: rx along X, ry along Y
    # note frame(): Y=(0,0,1), Z=(1,0,0) -> X = Y x Z = (0,1,0): local X is world +Y, local Z is world +X
    def band(zc0, zc1, rx, ry, a0, a1, thick=0.008, cx=0.0, n=14, bevel=0.35):
        return arc_plate(A([cx, 0, 0]), fr_up, ry, rx, a0, a1, zc0, zc1, thick, n, bevel)
    # chest plate (front, angles measured from +Y in the frame -> convert: local angle a: x=ry cos a, z=rx sin a)
    v, f = band(1.288, 1.398, 0.123, 0.166, 35, 145, 0.009, 0.006)
    parts.append(Part('chest_plate', v, f, 'armor', flex='torso'))
    v, f = band(1.222, 1.286, 0.114, 0.152, 40, 140, 0.008, 0.004, bevel=0.5)
    parts.append(Part('rib_plate_a', v, f, 'armor', flex='torso'))
    v, f = band(1.170, 1.220, 0.106, 0.146, 45, 135, 0.007, 0.002, bevel=0.5)
    parts.append(Part('rib_plate_b', v, f, 'armor', flex='torso'))
    v, f = hs.rounded_box((0.010, 0.030, 0.085), None, A([0.128, 0.0, 1.345]), seg=3, round_=0.5)
    parts.append(Part('sternum_ridge', v, f, 'cyber', flex='torso', emit=1.0, accent=1.0))
    # back plate
    v, f = band(1.285, 1.420, 0.121, 0.160, 215, 325, 0.009, -0.001)
    parts.append(Part('back_plate', v, f, 'armor', flex='torso'))
    v, f = hs.rounded_box((0.010, 0.070, 0.040), None, A([-0.128, 0.0, 1.355]), seg=3, round_=0.5)
    parts.append(Part('back_emitter_strip', v, f, 'cyber', flex='torso', emit=1.0, accent=1.0))
    # belt ring + buckle
    v, f = revolve([(1.0, 1.006), (1.03, 1.015), (1.03, 1.062), (1.0, 1.07), (0.985, 1.062), (0.985, 1.014)], A([-0.003, 0, 0]), (0, 0, 1), (1, 0, 0), n=40, sx=0.118, sz=0.164)
    # revolve with unit-radius profile scaled by sx (x depth) and sz (y width); heights = profile[1]
    v = np.array(v)
    v[:, 2] = v[:, 2]   # height already in metres
    parts.append(Part('belt', v, f, 'suit', flex='torso'))
    v, f = hs.rounded_box((0.014, 0.046, 0.046), None, A([0.125, 0.0, 1.040]), seg=3, round_=0.35)
    parts.append(Part('buckle', v, f, 'cyber', flex='torso', emit=0.5, accent=1.0))
    # pouches: right-front hip (cell pouch), left-back (beacon dock)
    v, f = hs.rounded_box((0.052, 0.078, 0.092), None, A([0.055, -0.150, 0.985]), seg=3, round_=0.3)
    parts.append(Part('pouch_cell', v, f, 'armor', flex='torso'))
    v, f = hs.rounded_box((0.020, 0.070, 0.070), None, A([0.092, -0.148, 1.000]), seg=3, round_=0.3)
    parts.append(Part('pouch_cell_flap', v, f, 'cyber', flex='torso', accent=1.0))
    v, f = hs.rounded_box((0.040, 0.030, 0.100), None, A([-0.120, -0.135, 0.985]), seg=3, round_=0.3)
    parts.append(Part('dock_arm', v, f, 'armor', flex='torso'))
    v, f = hs.cylinder(A([-0.100, -0.150, 0.925]), A([-0.100, -0.150, 1.030]), 0.033, 0.033, n=16, z_hint=(1, 0, 0))
    parts.append(Part('dock_cup', v, f, 'cyber', flex='torso', accent=0.5))
    # collar (revolve around the neck axis)
    prof = [(0.078, 1.474), (0.064, 1.500), (0.0595, 1.532), (0.0592, 1.566), (0.0570, 1.575), (0.0540, 1.570), (0.0538, 1.548), (0.0530, 1.504), (0.056, 1.474)]
    v, f = revolve([(r, h) for r, h in prof], A([0.010, 0, 0]), (0, 0, 1), (1, 0, 0), n=32)
    parts.append(Part('collar', v, f, 'suit', flex='torso'))
    v, f = revolve([(0.0602, 1.556), (0.0602, 1.5605), (0.0598, 1.5605), (0.0598, 1.556)], A([0.010, 0, 0]), (0, 0, 1), (1, 0, 0), n=32)
    parts.append(Part('collar_light', v, f, 'cyber', flex='torso', emit=1.0, accent=1.0))
    # chest strap ribbon from the right shoulder across the chest to the left hip
    pts = [A(p) for p in [(0.000, -0.150, 1.478), (0.085, -0.100, 1.420), (0.121, -0.040, 1.350), (0.120, 0.030, 1.255), (0.112, 0.090, 1.150), (0.094, 0.140, 1.070)]]
    pts2 = []
    for p in pts:  # push outward from the trunk axis a little
        d = A([p[0] / 0.115, p[1] / 0.16, 0.0])
        d /= np.linalg.norm(d) + 1e-9
        pts2.append(p + A([d[0] * 0.014, d[1] * 0.012, 0.0]))
    v, f = hs.tube_along(pts2, [(0.017, 0.0032)] * len(pts2), n=8, z_hint=(0, 0, 1), exp=4.0)
    parts.append(Part('chest_strap', v, f, 'suit', flex='torso', accent=0.4))
    return parts


def limb_armor():
    parts = []
    # right pauldron: plates stacked along the right upper-arm axis
    m = lambda p: A([p[0], -p[1], p[2]], float)
    sh = m(S.SHOULDER)
    ua = _n(A([S.UPPERARM_DIR[0], -S.UPPERARM_DIR[1], S.UPPERARM_DIR[2]]))
    R = hs.frame(ua, (1, 0, 0))
    for k, (s0, s1, rr, a0, a1) in enumerate(((-0.030, 0.020, 0.074, 100, 350), (0.006, 0.050, 0.078, 110, 340), (0.038, 0.082, 0.078, 120, 330))):
        v, f = arc_plate(sh + ua * 0.0, R, rr, rr * 0.96, a0, a1, s0, s1, 0.008, 14, bevel=0.3)
        parts.append(Part(f'pauldron_{k}', v, f, 'armor', bone='upperarm_r' if k > 0 else 'clavicle_r', accent=0.3 if k == 1 else 0.0))
    v, f = hs.sphere(sh + A([0.0, -0.004, 0.012]), (0.066, 0.064, 0.040), 18, 8, None)
    keep = v[:, 2] > sh[2] + 0.010
    # dome: clip lower half by flattening below the joint
    v = v.copy()
    v[~keep, 2] = sh[2] + 0.010 - 0.0
    parts.append(Part('pauldron_dome', v, f, 'armor', bone='clavicle_r'))
    v, f = hs.rounded_box((0.012, 0.050, 0.008), R, sh + ua * 0.040 + A([0, -0.078, 0.02]), seg=2, round_=0.5)
    parts.append(Part('pauldron_light', v, f, 'cyber', bone='upperarm_r', emit=1.0, accent=1.0))
    # knee guards and thigh straps, thigh holster (right)
    for sy, sfx in ((1.0, 'l'), (-1.0, 'r')):
        k = A([S.KNEE[0], sy * S.KNEE[1], S.KNEE[2]])
        hip = A([S.HIP[0], sy * S.HIP[1], S.HIP[2]])
        ank = A([S.ANKLE[0], sy * S.ANKLE[1], S.ANKLE[2]])
        ax = _n(ank - hip)
        Rk = hs.frame(ax, (1, 0, 0))
        v, f = arc_plate(k, Rk, 0.066, 0.068, 215, 325, -0.050, 0.055, 0.008, 12, bevel=0.35)
        parts.append(Part(f'knee_guard_{sfx}', v, f, 'armor', bone=f'calf_{sfx}' if False else f'knee_half_{sfx}'))
        v, f = hs.rounded_box((0.016, 0.050, 0.040), None, k + A([0.070, 0, 0.005]), seg=3, round_=0.5)
        parts.append(Part(f'knee_ridge_{sfx}', v, f, 'cyber', bone=f'knee_half_{sfx}', emit=0.9, accent=1.0))
        # thigh band
        th = hip + (k - hip) * 0.45
        v, f = revolve([(0.0, -0.016), (0.0, 0.016)], th, ax, (1, 0, 0), n=1) if False else hs.cylinder(th - ax * 0.016, th + ax * 0.016, 0.0925, 0.090, n=24, caps=False, z_hint=(1, 0, 0))
        parts.append(Part(f'thigh_band_{sfx}', v, f, 'suit', flex='thigh_' + sfx, accent=0.5))
    v, f = hs.rounded_box((0.038, 0.030, 0.130), None, A([0.004, -0.196, 0.760]), seg=3, round_=0.35)
    parts.append(Part('holster_plate', v, f, 'armor', bone='thigh_r'))
    v, f = hs.rounded_box((0.010, 0.010, 0.100), None, A([0.028, -0.198, 0.760]), seg=2, round_=0.5)
    parts.append(Part('holster_light', v, f, 'cyber', bone='thigh_r', emit=1.0, accent=1.0))
    # right wrist bracer covering the hand seam
    m2 = lambda p: A([p[0], -p[1], p[2]], float)
    wr = m2(S.WRIST)
    fa = _n(A([S.FOREARM_DIR[0], -S.FOREARM_DIR[1], S.FOREARM_DIR[2]]))
    prof = [(0.0355, -0.090), (0.0375, -0.084), (0.0365, -0.040), (0.0345, -0.010), (0.0355, 0.004), (0.0335, 0.010), (0.0315, 0.004), (0.0305, -0.030), (0.0325, -0.086)]
    v, f = revolve([(r, h) for r, h in prof], wr, fa, (1, 0, 0), n=24, sx=1.0, sz=0.88)
    parts.append(Part('wrist_bracer', v, f, 'armor', flex='bracer'))
    prof2 = [(0.0378, -0.058), (0.0378, -0.050), (0.0368, -0.050), (0.0368, -0.058)]
    v, f = revolve([(r, h) for r, h in prof2], wr, fa, (1, 0, 0), n=24, sx=1.0, sz=0.88)
    parts.append(Part('wrist_bracer_light', v, f, 'cyber', flex='bracer', emit=1.0, accent=1.0))
    return parts


# ----------------------------------------------------------------------------- braid, cable, props

def braid():
    """Short braid hanging from the back of the head, skinned along hair_01..05."""
    pts = [A(S.BONE_BY_NAME['hair_01'].head)] + [A(S.BONE_BY_NAME[f'hair_{i:02d}'].tail) for i in range(1, 6)]
    rings = []
    n = 14
    for i, p in enumerate(pts):
        d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        R = hs.frame(d, (1, 0, 0))
        t = i / (len(pts) - 1)
        r = 0.0165 * (1 - 0.42 * t) + 0.0
        ring = []
        for m in range(n):
            a = 2 * math.pi * m / n
            rr = r * (1 + 0.16 * math.sin(3 * a + i * 1.2))      # braid ridges
            ring.append(p + R @ A([rr * math.cos(a), 0, rr * math.sin(a)]))
        rings.append(A(ring))
    v, f = hs.loft(rings, True, True)
    parts = [Part('braid', v, f, 'hair', flex='braid')]
    tip = pts[-1] + A([-0.001, 0, -0.012])
    v, f = hs.sphere(tip, (0.0085, 0.0085, 0.0085), 12, 8)
    parts.append(Part('braid_bead', v, f, 'cyber', bone='hair_05', emit=0.9, accent=1.0))
    v, f = hs.cylinder(pts[0] + A([0.0, 0, 0.004]), pts[0] + A([0.0, 0, -0.012]), 0.0195, 0.0185, n=14, z_hint=(1, 0, 0))
    parts.append(Part('braid_tie', v, f, 'cyber', bone='hair_01', accent=1.0))
    return parts


def cable():
    pts = [A(S.BONE_BY_NAME['cable_01'].head)] + [A(S.BONE_BY_NAME[f'cable_{i:02d}'].tail) for i in range(1, 6)]
    v, f = hs.tube_along(pts, [0.0072, 0.0072, 0.0068, 0.0066, 0.0064, 0.0062], n=8, z_hint=(1, 0, 0))
    parts = [Part('cable', v, f, 'cyber', flex='cable')]
    tipv, tipf = hs.rounded_box((0.014, 0.014, 0.026), hs.frame(pts[-1] - pts[-2], (1, 0, 0)), pts[-1] + _n(pts[-1] - pts[-2]) * 0.010, seg=3, round_=0.45)
    parts.append(Part('cable_plug', tipv, tipf, 'armor', bone='cable_05'))
    parts.append(Part('cable_glow', *hs.cylinder(pts[-1] + _n(pts[-1] - pts[-2]) * 0.021, pts[-1] + _n(pts[-1] - pts[-2]) * 0.024, 0.0042, n=8), mat='cyber', bone='cable_05', emit=1.0, accent=1.0))
    return parts


def prop_power_cell():
    """Power cell centred at the origin, long axis = local +Z? -> long axis along +Y to match the prop bone (Y along the bone)."""
    parts = []
    body = hs.cylinder(A([0, -0.050, 0]), A([0, 0.050, 0]), 0.0165, 0.0165, n=20, rings=2)
    parts.append(Part('cell_body', body[0], body[1], 'armor'))
    for k, y in enumerate((-0.038, 0.038)):
        r = hs.cylinder(A([0, y - 0.005, 0]), A([0, y + 0.005, 0]), 0.0182, 0.0182, n=20)
        parts.append(Part(f'cell_ring_{k}', r[0], r[1], 'cyber', accent=1.0))
    core = hs.cylinder(A([0, -0.028, 0]), A([0, 0.028, 0]), 0.0128, 0.0128, n=16)
    v = core[0].copy()
    parts.append(Part('cell_core', v, core[1], 'cyber', emit=1.0, accent=1.0))
    cap = hs.cylinder(A([0, 0.050, 0]), A([0, 0.058, 0]), 0.0110, 0.0080, n=16)
    parts.append(Part('cell_tip', cap[0], cap[1], 'cyber'))
    for k in range(3):
        y = -0.012 + k * 0.012
        gr = hs.cylinder(A([0, y - 0.002, 0]), A([0, y + 0.002, 0]), 0.0172, 0.0172, n=20)
        parts.append(Part(f'cell_grip_{k}', gr[0], gr[1], 'armor'))
    return parts


def prop_beacon():
    """Small deployable beacon/drone: hex body, three fold-out legs, antenna, emissive eye ring. Origin at the base centre."""
    parts = []
    body = hs.cylinder(A([0, 0, 0.030]), A([0, 0, 0.100]), 0.036, 0.030, n=6, rings=2, z_hint=(1, 0, 0))
    parts.append(Part('beacon_body', body[0], body[1], 'armor'))
    dome = hs.sphere(A([0, 0, 0.100]), (0.030, 0.030, 0.022), 12, 6)
    parts.append(Part('beacon_dome', dome[0], dome[1], 'cyber', accent=0.7))
    eye = hs.cylinder(A([0, 0, 0.066]), A([0, 0, 0.076]), 0.0385, 0.0385, n=18, caps=False, z_hint=(1, 0, 0))
    parts.append(Part('beacon_eye_ring', eye[0], eye[1], 'cyber', emit=1.0, accent=1.0))
    core = hs.sphere(A([0, 0, 0.101]), (0.012, 0.012, 0.010), 10, 6)
    parts.append(Part('beacon_core', core[0], core[1], 'cyber', emit=1.0, accent=1.0))
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        d = A([math.cos(a), math.sin(a), 0])
        pts = [A([0, 0, 0.045]) + d * 0.030, A([0, 0, 0.030]) + d * 0.058, A([0, 0, 0.002]) + d * 0.078]
        v, f = hs.tube_along(pts, [0.0058, 0.0050, 0.0042], n=8, z_hint=(0, 0, 1))
        parts.append(Part(f'beacon_leg_{k}', v, f, 'armor'))
        foot = hs.sphere(pts[-1] + A([0, 0, 0.0015]), (0.0068, 0.0068, 0.0040), 8, 5)
        parts.append(Part(f'beacon_foot_{k}', foot[0], foot[1], 'cyber'))
    an = hs.cylinder(A([0, 0, 0.118]), A([0, 0, 0.190]), 0.0030, 0.0018, n=8, z_hint=(1, 0, 0))
    parts.append(Part('beacon_antenna', an[0], an[1], 'armor'))
    tip = hs.sphere(A([0, 0, 0.192]), (0.0055, 0.0055, 0.0055), 8, 6)
    parts.append(Part('beacon_antenna_tip', tip[0], tip[1], 'cyber', emit=1.0, accent=1.0))
    return parts

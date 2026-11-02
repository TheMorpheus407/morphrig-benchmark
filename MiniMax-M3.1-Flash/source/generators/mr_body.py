"""MorphRig body generator.

Builds the Operative's continuous body mesh:

  torso+neck   one swept tube, 48 columns
  head         96 columns (angular split of the neck ring) with face relief
  arms         22 columns, stitched into carved shoulder holes
  hands        22 columns (flat palm slab), stitched at the wrist
  fingers      6 columns, stitched into carved knuckle holes
  legs         24 columns, split from the pelvis ring (Y branch)
  boots        separate closed shapes overlapping the ankle

Column angles are front dense so the face gets the resolution it needs.

Every vertex carries a `part` tag; the skinning module uses those tags to
bind the mesh analytically (see mr_skin.py).
"""

import math
from mathutils import Vector

import mr_rig

import mr_core
from mr_core import (TAU, Tube, cleanup_faces, catmull_rom,
                     parallel_transport_frames, clamp, lerp)

D2R = math.pi / 180.0

TORSO_COLS = 96
HEAD_COLS = 192
ARM_COLS = 38
HAND_COLS = 38
LEG_COLS = 46
FOOT_COLS = 24
FINGER_COLS = 6

P = dict(
    ground=0.000, ankle=0.092, knee=0.505, hip=0.955, waist=1.075,
    chest=1.300, shoulder=1.405, neck_base=1.500, jaw=1.575,
    eye=1.665, crown=1.800,
)

# palm / finger direction in the neutral pose (forward and slightly down)
HAND_DIR = Vector((0.12, -0.78, -0.61)).normalized()


def g(v, c, s):
    """Gaussian falloff."""
    t = (v - c) / s
    return math.exp(-t * t)


# ---------------------------------------------------------------------------
# column distribution
# ---------------------------------------------------------------------------

def column_angles(n, front_deg=58.0, front_frac=0.42):
    """Front-dense column angles (radians).  Column 0 = front centre (-Y)."""
    pairs = (n - 2) // 2
    nfront = max(2, int(round(pairs * front_frac)))
    ds = []
    for k in range(1, pairs + 1):
        if k <= nfront:
            ds.append(front_deg * ((k / float(nfront)) ** 0.92))
        else:
            t = (k - nfront) / float(max(pairs - nfront, 1))
            ds.append(front_deg + (176.0 - front_deg) * t)
    ang = [270.0 * D2R]
    for k in range(pairs):
        ang.append((270.0 + ds[k]) * D2R)
    ang.append(450.0 * D2R)                       # back centre
    for k in range(pairs - 1, -1, -1):
        ang.append((450.0 + (180.0 - ds[k])) * D2R)
    return ang[:n]


def split_angles(ang):
    """Double an angle list, inserting angular midpoints."""
    out = []
    n = len(ang)
    for j in range(n):
        a = ang[j]
        b = ang[(j + 1) % n]
        if b < a:
            b += TAU
        out.append(a)
        out.append((a + b) * 0.5)
    return out


def ellipse_point(center, ang, w, d):
    return Vector((center[0] + w * math.cos(ang),
                   center[1] + d * math.sin(ang),
                   center[2]))


# ---------------------------------------------------------------------------
# torso
# ---------------------------------------------------------------------------

TORSO_PROFILE = [
    (0.855, 0.130, 0.100, 0.000),
    (0.832, 0.113, 0.090, 0.000),
    (0.808, 0.085, 0.070, 0.000),
    (0.782, 0.058, 0.052, 0.000),
    (0.880, 0.152, 0.110, 0.000),
    (0.915, 0.160, 0.115, 0.002),
    (0.955, 0.156, 0.113, 0.004),
    (1.000, 0.146, 0.106, 0.004),
    (1.040, 0.136, 0.099, 0.003),
    (1.075, 0.131, 0.096, 0.002),
    (1.110, 0.132, 0.098, 0.000),
    (1.150, 0.138, 0.102, -0.002),
    (1.190, 0.148, 0.109, -0.003),
    (1.225, 0.158, 0.115, -0.003),
    (1.260, 0.167, 0.119, -0.002),
    (1.295, 0.174, 0.120, 0.000),
    (1.325, 0.178, 0.118, 0.002),
    (1.355, 0.180, 0.114, 0.004),
    (1.385, 0.180, 0.110, 0.005),
    (1.412, 0.177, 0.106, 0.005),
    (1.438, 0.166, 0.102, 0.004),
    (1.458, 0.145, 0.096, 0.003),
    (1.475, 0.115, 0.087, 0.001),
    (1.490, 0.082, 0.074, 0.000),
    (1.505, 0.064, 0.061, 0.000),
    (1.530, 0.059, 0.057, 0.000),
    (1.560, 0.058, 0.056, -0.002),
]


def torso_profile(z):
    pr = TORSO_PROFILE
    if z <= pr[0][0]:
        return pr[0][1], pr[0][2], pr[0][3]
    if z >= pr[-1][0]:
        return pr[-1][1], pr[-1][2], pr[-1][3]
    for i in range(len(pr) - 1):
        z0, w0, d0, y0 = pr[i]
        z1, w1, d1, y1 = pr[i + 1]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            t = t * t * (3 - 2 * t)
            return (lerp(w0, w1, t), lerp(d0, d1, t), lerp(y0, y1, t))
    return pr[-1][1], pr[-1][2], pr[-1][3]


def ellipse_normal(a, w, d):
    """Outward (horizontal) normal of the ellipse at angle a."""
    return Vector((d * math.cos(a), w * math.sin(a), 0.0)).normalized()


def build_torso(mb):
    ang = column_angles(TORSO_COLS)
    t = Tube(mb, "torso")
    rows = sorted(set([p[0] for p in TORSO_PROFILE] +
                      [1.398, 1.425, 1.448]))
    for z in rows:
        w, d, yo = torso_profile(z)
        pts = []
        for a in ang:
            p = ellipse_point((0.0, yo, z), a, w, d)
            if z >= 1.470:
                # the chin and lower lip live on the neck rings of the torso
                disp = face_relief(p.x, p.y, p.z)
                if disp != 0.0:
                    p = p + ellipse_normal(a, w, d) * disp
            pts.append(p)
        v = (z - rows[0]) / max(rows[-1] - rows[0], 1e-6)
        # the neck is skin, it belongs to the head and not to the suit
        part = "neck" if z >= 1.505 else "torso"
        t.add_ring(pts, v=v, part=part)
    for i in range(len(rows) - 1):
        t.bridge(i, i + 1)
    # cap the crotch funnel at the bottom; the top continues into the head
    w, d, yo = torso_profile(rows[0])
    t.cap(0, center=(0.0, yo, rows[0]), flip=False, part="torso")
    return t, ang, rows


def row_index(rows, z):
    best = 0
    for i, r in enumerate(rows):
        if abs(r - z) < abs(rows[best] - z):
            best = i
    return best


# ---------------------------------------------------------------------------
# arms
# ---------------------------------------------------------------------------

ARM_PATH = [
    (0.176, 0.000, 1.405, 0.062),
    (0.198, -0.004, 1.305, 0.054),
    (0.220, -0.009, 1.200, 0.048),
    (0.236, -0.014, 1.120, 0.046),
    (0.252, -0.019, 1.030, 0.044),
    (0.264, -0.026, 0.950, 0.042),
    (0.272, -0.031, 0.890, 0.033),
]

ARM_HOLE = dict(right=(22, 33), left=(63, 74), dr=2, r0_z=1.362)


def arm_axis(side):
    pts = [Vector((side * x, y, z)) for (x, y, z, r) in ARM_PATH]
    rad = [r for (x, y, z, r) in ARM_PATH]
    centers = catmull_rom(pts, 20)
    n = len(centers)
    radii = []
    for i in range(n):
        f = i / float(n - 1) * (len(rad) - 1)
        i0 = min(int(f), len(rad) - 2)
        radii.append(lerp(rad[i0], rad[i0 + 1], f - i0))
    return centers, radii


def build_arm(mb, torso, torso_rows, side):
    j0, j1 = ARM_HOLE["right"] if side > 0 else ARM_HOLE["left"]
    r0 = row_index(torso_rows, ARM_HOLE["r0_z"])
    r1 = r0 + ARM_HOLE["dr"]
    loop = torso.carve(r0, r1, j0, j1)
    n = len(loop)
    part = "arm_r" if side > 0 else "arm_l"

    centers, radii = arm_axis(side)
    axis0 = Vector((side * 0.176, 0.0, 1.405))
    frames = parallel_transport_frames(centers)
    tang, right, up = frames[0]

    th = []
    for vi in loop:
        p = mb.verts[vi] - axis0
        th.append(math.atan2(p.dot(up), p.dot(right)))
    base = th[0]
    step = TAU / n

    t = Tube(mb, "arm")
    t.add_ring_indices(loop, v=0.0, part=part)
    nb = 4
    for k in range(nb):
        f = (k + 1) / float(nb)
        e = f * f * (3.0 - 2.0 * f)
        ci = min(1 + k, len(centers) - 1)
        c = axis0.lerp(centers[ci], 0.28 + 0.17 * k)
        r = radii[ci] * (1.16 - 0.10 * e)
        tg, rt, upv = frames[ci]
        pts = []
        for j in range(n):
            a = base + step * j
            tgt = c + rt * (r * math.cos(a)) + upv * (r * math.sin(a))
            pts.append(mb.verts[loop[j]].lerp(tgt, e))
        t.add_ring(pts, v=0.03 + 0.05 * k, part=part)
        t.bridge(k, k + 1)
    for i in range(nb + 1, len(centers)):
        tg, rt, upv = frames[i]
        r = radii[i]
        pts = [centers[i] + rt * (r * math.cos(base + step * j)) +
               upv * (r * math.sin(base + step * j)) for j in range(n)]
        t.add_ring(pts, v=0.09 + 0.60 * (i / float(len(centers) - 1)), part=part)
        t.bridge(i - 1, i)
    return t


# ---------------------------------------------------------------------------
# hand
# ---------------------------------------------------------------------------

HAND_STEPS = [
    (0.024, 0.027, 0.023),
    (0.044, 0.033, 0.021),
    (0.064, 0.036, 0.020),
    (0.080, 0.038, 0.019),
    (0.094, 0.039, 0.018),
    (0.104, 0.037, 0.016),
]

# rounded knuckle dome that closes the palm
HAND_DOME = [
    (0.111, 0.030, 0.013),
    (0.115, 0.019, 0.009),
    (0.117, 0.007, 0.004),
]

KNUCKLE_DIST = mr_core.KNUCKLE_DIST


def hand_cross(half_w, half_t, n=38, round_c=0.009):
    """n column palm cross-section (local across, up).

    (n-4)/2 dorsal verts, 2 left corners, (n-4)/2 palmar verts, 2 right
    corners.  Column 0 is the dorsal -X corner, column 8/9 is the left side
    (the thumb side for the right hand).
    """
    nd = (n - 4) // 2
    step = 2.0 * half_w / float(nd - 1)
    xs_d = [-half_w + step * i for i in range(nd)]
    xs_p = [-half_w + step * i for i in range(nd)]
    pts = [(x, half_t) for x in xs_d]
    pts.append((-half_w - round_c, half_t * 0.40))
    pts.append((-half_w - round_c, -half_t * 0.40))
    pts.extend((x, -half_t) for x in reversed(xs_p))
    pts.append((half_w + round_c, -half_t * 0.40))
    pts.append((half_w + round_c, half_t * 0.40))
    return pts


def build_hand(mb, arm, side):
    part = "hand_r" if side > 0 else "hand_l"
    last = arm.rings[-1]
    n = len(last)
    wrist_c = Vector((0, 0, 0))
    for vi in last:
        wrist_c += mb.verts[vi]
    wrist_c /= n
    fwd = Vector((side * HAND_DIR.x, HAND_DIR.y, HAND_DIR.z)).normalized()
    right = Vector((1.0, 0.0, 0.0))
    right = right - fwd * right.dot(fwd)
    if right.length < 1e-6:
        right = Vector((0.0, 1.0, 0.0))
    right.normalize()
    up = fwd.cross(right).normalized()
    if side < 0:
        right = -right

    palm = Tube(mb, "palm")
    palm.add_ring_indices(last, v=0.0, part=part)
    steps = HAND_STEPS + HAND_DOME
    for i, (t, hw, ht) in enumerate(steps):
        c = wrist_c + fwd * t
        ring = [c + right * u + up * v
                for (u, v) in hand_cross(hw, ht, HAND_COLS)]
        palm.add_ring(ring, v=0.02 + 0.60 * t / 0.150, part=part)
        palm.bridge(i, i + 1)
    palm.cap(len(palm.rings) - 1, part=part)
    return palm, wrist_c, fwd, right, up


FINGER_SPECS = [
    ("index", 0.068, 0.0093, 1),
    ("middle", 0.075, 0.0097, 5),
    ("ring", 0.070, 0.0089, 9),
    ("pinky", 0.057, 0.0079, 13),
]


def build_fingers(mb, palm, side, wrist_c, fwd, right, up):
    """Five digits that grow out of the closed palm."""
    sfx = "r" if side > 0 else "l"
    knuckle = wrist_c + fwd * KNUCKLE_DIST
    out = []
    for (nm, L, R, cell) in FINGER_SPECS:
        joints = mr_rig.finger_joints(knuckle, fwd, right, up, nm)
        t = _sweep_digit(mb, joints, R, right, up, nm, side=side)
        out.append((nm, t))
    joints = mr_rig.finger_joints(knuckle, fwd, right, up, "thumb")
    t = _sweep_digit(mb, joints, mr_rig.FINGER_TABLE["thumb"]["radius"],
                     right, up, "thumb", side=side)
    out.append(("thumb", t))
    return out


def _sweep_digit(mb, joints, radius, right_hint, up_hint, name, side=1,
                 cols=14):
    """Sweep one finger along its joint path.

    `joints` holds the root plus the three phalanx tips.  Every phalanx is
    tagged with its own part so it can be skinned to the matching bone.
    """
    sfx = "r" if side > 0 else "l"
    p0 = joints[0]

    # a frame per phalanx
    frames = []
    sv = right_hint.copy()
    for k in range(3):
        ax = (joints[k + 1] - joints[k]).normalized()
        sv = sv - ax * sv.dot(ax)
        if sv.length < 1e-6:
            sv = Vector((0.0, 0.0, 1.0)) - ax * ax.z
        sv.normalize()
        uv = ax.cross(sv).normalized()
        frames.append((sv, uv))

    radii = [radius * (1.0 - 0.09 * s) for s in (0.0, 0.44, 0.77, 1.0)]
    t = Tube(mb, "finger_" + name)

    def circle(center, frame, r):
        sv, uv = frame
        return [center + sv * (r * math.cos(TAU * j / cols)) +
                uv * (r * math.sin(TAU * j / cols)) for j in range(cols)]

    # ring 0 sits inside the palm so the digit appears to grow out of it
    t.add_ring(circle(p0, frames[0], radii[0]), v=0.03,
               part="finger_%s_01_%s" % (name, sfx))
    # ring 1 is the first knuckle and follows the second phalanx so the
    # joint is shared between the two bones
    t.add_ring(circle(joints[1], frames[0], radii[1]), v=0.03 + 0.32,
               part="finger_%s_02_%s" % (name, sfx))
    t.bridge(0, 1)
    t.add_ring(circle(joints[2], frames[1], radii[2]), v=0.03 + 0.62,
               part="finger_%s_02_%s" % (name, sfx))
    t.bridge(1, 2)
    t.add_ring(circle(joints[3], frames[2], radii[3]), v=0.03 + 0.95,
               part="finger_%s_03_%s" % (name, sfx))
    t.bridge(2, 3)
    tip = joints[3] + (joints[3] - joints[2]).normalized() * 0.004
    t.cap(3, center=tip, flip=True, part="finger_%s_03_%s" % (name, sfx))
    t.cap(0, center=p0, flip=True, part="finger_%s_01_%s" % (name, sfx))
    return t


# ---------------------------------------------------------------------------
# legs and boots
# ---------------------------------------------------------------------------

LEG_PATH = [
    (0.100, 0.000, 0.848, 0.094),
    (0.097, 0.002, 0.820, 0.089),
    (0.098, 0.004, 0.700, 0.083),
    (0.099, 0.005, 0.585, 0.073),
    (0.100, 0.005, 0.520, 0.065),
    (0.100, 0.004, 0.480, 0.060),
    (0.100, -0.004, 0.290, 0.070),
    (0.100, -0.010, 0.200, 0.062),
    (0.100, -0.008, 0.130, 0.048),
    (0.100, 0.000, 0.090, 0.036),
]


def leg_axis(side):
    pts = [Vector((side * x, y, z)) for (x, y, z, r) in LEG_PATH]
    rad = [r for (x, y, z, r) in LEG_PATH]
    centers = catmull_rom(pts, 22)
    n = len(centers)
    radii = []
    for i in range(n):
        f = i / float(n - 1) * (len(rad) - 1)
        i0 = min(int(f), len(rad) - 2)
        radii.append(lerp(rad[i0], rad[i0 + 1], f - i0))
    return centers, radii


def build_legs(mb, torso, torso_rows):
    """Attach both legs through carved holes in the pelvis funnel."""
    legs = []
    r0 = row_index(torso_rows, 0.855)
    for side, (j0, j1) in ((1, (18, 38)), (-1, (58, 78))):
        part = "leg_r" if side > 0 else "leg_l"
        loop = torso.carve(r0, r0, j0, j1)
        centers, radii = leg_axis(side)
        frames = parallel_transport_frames(centers)
        n = len(loop)
        leg_c = centers[0]
        ang = []
        for vi in loop:
            p = mb.verts[vi] - leg_c
            ang.append(math.atan2(p.y, p.x))
        turn = 0.0
        for k in range(1, n):
            d = ang[k] - ang[k - 1]
            while d > math.pi:
                d -= TAU
            while d < -math.pi:
                d += TAU
            turn += d
        if turn < 0:
            ang = list(reversed(ang))
        base = ang[0]
        step = TAU / n
        t = Tube(mb, "leg")
        t.add_ring_indices(loop, v=0.0, part=part)
        for k, frac in enumerate((0.5, 1.0)):
            ci = min(1 + k, len(centers) - 1)
            tg, rt, upv = frames[ci]
            rad = radii[ci]
            pts = []
            for j, vi in enumerate(loop):
                a = base + step * j
                tgt = centers[ci] + rt * (rad * math.cos(a)) + upv * (rad * math.sin(a))
                pts.append(mb.verts[vi].lerp(tgt, frac))
            t.add_ring(pts, v=0.02 + 0.05 * k, part=part)
            t.bridge(k, k + 1)
        for i in range(3, len(centers)):
            tg, rt, upv = frames[i]
            rad = radii[i]
            pts = [centers[i] + rt * (rad * math.cos(base + step * j)) +
                   upv * (rad * math.sin(base + step * j)) for j in range(n)]
            t.add_ring(pts, v=0.07 + 0.62 * (i / float(len(centers) - 1)), part=part)
            t.bridge(i - 1, i)
        # close the ankle (hidden inside the boot)
        t.cap(len(t.rings) - 1, center=centers[-1], flip=True, part=part)
        legs.append((side, t, list(loop)))
    return legs


# (y offset from the ankle, z centre, half width, half height)
BOOT_SECTIONS = [
    (0.020, 0.158, 0.050, 0.045),
    (0.008, 0.120, 0.055, 0.052),
    (-0.012, 0.082, 0.055, 0.055),
    (-0.042, 0.046, 0.052, 0.046),
    (-0.078, 0.033, 0.048, 0.033),
    (-0.112, 0.024, 0.043, 0.024),
    (-0.140, 0.017, 0.031, 0.017),
]


def build_boot(mb, side):
    """Closed boot shell overlapping the ankle; sole sits on z = 0.

    The cross sections are vertical ovals in the XZ plane so the shaft runs
    along Y (heel at +Y, toe at -Y).
    """
    part = "boot_r" if side > 0 else "boot_l"
    ax = 0.100 * side
    t = Tube(mb, "boot")
    ang = column_angles(FOOT_COLS)
    for i, (dy, zc, hw, hh) in enumerate(BOOT_SECTIONS):
        c = Vector((ax, dy, zc))
        pts = []
        for a in ang:
            pts.append(Vector((c.x + hw * math.cos(a),
                               c.y,
                               c.z + hh * math.sin(a))))
        t.add_ring(pts, v=0.62 + 0.38 * i / float(len(BOOT_SECTIONS) - 1),
                   part=part)
        if i:
            t.bridge(i - 1, i)
    # bottom of the sole
    t.cap(len(t.rings) - 1, center=Vector((ax, BOOT_SECTIONS[-1][0],
                                          BOOT_SECTIONS[-1][1])), flip=True,
          part=part)
    # top of the shaft (hidden inside the calf)
    t.cap(0, center=Vector((ax, BOOT_SECTIONS[0][0], BOOT_SECTIONS[0][1])),
          flip=False, part=part)
    return t


# ---------------------------------------------------------------------------
# head
# ---------------------------------------------------------------------------

HEAD_PROFILE = [
    (1.500, 0.064, 0.061, 0.000),
    (1.530, 0.061, 0.058, -0.001),
    (1.560, 0.058, 0.055, -0.002),
    (1.585, 0.061, 0.060, -0.004),
    (1.605, 0.068, 0.071, -0.006),
    (1.625, 0.073, 0.082, -0.008),
    (1.645, 0.075, 0.089, -0.009),
    (1.665, 0.076, 0.092, -0.008),
    (1.685, 0.075, 0.091, -0.006),
    (1.705, 0.072, 0.088, -0.004),
    (1.725, 0.068, 0.082, -0.001),
    (1.745, 0.066, 0.077, 0.003),
    (1.765, 0.057, 0.064, 0.008),
    (1.782, 0.044, 0.047, 0.013),
    (1.795, 0.027, 0.028, 0.016),
    (1.800, 0.010, 0.011, 0.017),
]


def head_profile(z):
    pr = HEAD_PROFILE
    if z <= pr[0][0]:
        return pr[0][1], pr[0][2], pr[0][3]
    if z >= pr[-1][0]:
        return pr[-1][1], pr[-1][2], pr[-1][3]
    for i in range(len(pr) - 1):
        z0, w0, d0, y0 = pr[i]
        z1, w1, d1, y1 = pr[i + 1]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            t = t * t * (3 - 2 * t)
            return (lerp(w0, w1, t), lerp(d0, d1, t), lerp(y0, y1, t))
    return pr[-1][1], pr[-1][2], pr[-1][3]


FACE_RELIEF_GAIN = 2.0


def face_relief(x, y, z):
    """Radial displacement for the facial features (metres).

    `y` is negative towards the front of the face.
    """
    front = clamp((-y - 0.010) / 0.050)
    if front <= 0.0:
        return 0.0
    ax = abs(x)
    d = 0.0
    # brow ridge
    d += 0.0046 * g(z, 1.690, 0.015) * g(ax, 0.038, 0.028)
    # eye sockets
    d -= 0.0040 * g(z, 1.664, 0.014) * g(ax, 0.032, 0.013)
    # eyelids bulge slightly
    d += 0.0016 * g(z, 1.660, 0.008) * g(ax, 0.031, 0.015)
    # nose bridge + tip
    nose = 0.0
    nose += 0.0032 * g(z, 1.700, 0.018)
    nose += 0.0090 * g(z, 1.658, 0.017)
    nose += 0.0115 * g(z, 1.634, 0.012)
    wnose = 0.011 + 0.011 * g(z, 1.638, 0.014)
    if ax < wnose:
        nose *= (1.0 - (ax / wnose) ** 2) ** 0.65
    else:
        nose = 0.0
    d += nose
    # cheekbones
    d += 0.0032 * g(z, 1.620, 0.014) * g(ax, 0.050, 0.017)
    # muzzle / mouth area recess
    d -= 0.0024 * g(z, 1.5840, 0.014) * g(ax, 0.024, 0.020)
    # upper lip
    d += 0.0046 * g(z, 1.6010, 0.0060) * g(ax, 0.0, 0.0135)
    # lower lip
    d += 0.0054 * g(z, 1.5900, 0.0068) * g(ax, 0.0, 0.0150)
    # philtrum groove
    d -= 0.0012 * g(z, 1.5985, 0.0055) * g(ax, 0.0, 0.0060)
    # mouth corner creases
    d -= 0.0018 * g(z, 1.5955, 0.0100) * g(ax, 0.0250, 0.0060)
    # chin
    d += 0.0036 * g(z, 1.5640, 0.0125) * g(ax, 0.008, 0.020)
    # jaw line
    d -= 0.0016 * g(z, 1.5720, 0.0110) * g(ax, 0.030, 0.014)
    # cheek hollow
    d -= 0.0020 * g(z, 1.588, 0.010) * g(ax, 0.038, 0.010)
    # eye lid crease
    d -= 0.0012 * g(z, 1.678, 0.006) * g(ax, 0.032, 0.016)
    return d * front * FACE_RELIEF_GAIN


def build_head(mb, torso, torso_ang, torso_rows):
    """Head tube: 192 columns, angular split of the neck ring."""
    ztop = torso_rows[-1]
    head_ang = split_angles(torso_ang)
    t = Tube(mb, "head")
    rows = sorted(set([p[0] for p in HEAD_PROFILE if p[0] > ztop] +
                      [1.5915, 1.5945, 1.5985, 1.6025, 1.6090, 1.6340]))
    zlo, zhi = rows[0], rows[-1]
    for i, z in enumerate(rows):
        w, d, yo = head_profile(z)
        pts = []
        for a in head_ang:
            p = ellipse_point((0.0, yo, z), a, w, d)
            disp = face_relief(p.x, p.y, p.z)
            if disp != 0.0:
                p = p + ellipse_normal(a, w, d) * disp
            pts.append(p)
        # The v coordinate grows with the height, not with the row index.
        # The rows are dense around the mouth, an index based mapping
        # would squash the lips into a hair line and stretch the skull.
        v = 0.06 + 0.80 * ((z - zlo) / max(zhi - zlo, 1e-6))
        t.add_ring(pts, v=v, part="head")
        if i:
            t.bridge(i - 1, i)
    # stitch the 96 column neck onto the 192 column head ring
    torso.split_bridge(len(torso.rings) - 1, t.rings[0], v_scale=0.86)
    w, d, yo = head_profile(rows[-1])
    t.cap(len(t.rings) - 1, center=(0.0, yo, rows[-1]), flip=True,
          part="head")
    # mouth opening: the slit between the lower and upper lip rings
    r_mouth = min(range(len(rows)), key=lambda i: abs(rows[i] - 1.5950))
    mouth = t.carve(r_mouth, r_mouth, 178, 12)
    return t, head_ang, rows, mouth


def socket_frame(mb, head_tube, side):
    """Return (surface point, outward normal, eye centre) for one orbit."""
    best = None
    bestd = 1e9
    for r in head_tube.rings:
        for vi in r:
            p = mb.verts[vi]
            if p.y > -0.040:
                continue
            if side > 0 and p.x < 0.008:
                continue
            if side < 0 and p.x > -0.008:
                continue
            d = (p.x - side * 0.0335) ** 2 + ((p.z - 1.6640) * 2.2) ** 2
            if d < bestd:
                bestd = d
                best = p.copy()
    if best is None:
        best = Vector((side * 0.0335, -0.0940, 1.664))
    core = Vector((0.0, -0.008, 1.672))
    n = (best - core).normalized()
    # the eyeball sits deep in the orbital bowl, only a disc of it shows
    # through the socket
    center = best - n * 0.0078
    return best, n, center


def head_uv_at(mb, head_tube, point):
    """UV coordinate of the head surface point nearest to `point`."""
    best = None
    bestd = 1e9
    for r, ring in enumerate(head_tube.rings):
        for c, vi in enumerate(ring):
            d = (mb.verts[vi] - point).length_squared
            if d < bestd:
                bestd = d
                best = (r, c)
    r, c = best
    us = head_tube._u_with_seams(r)
    return (us[c], head_tube.ring_v[r])


def brow_samples(mb, head_tube, side, count=13):
    """Sample the brow ridge of the head so the brow strip hugs the face.

    Only the front of the head is searched.  The nearest vertex in (x, z)
    alone would happily pick a vertex on the side of the skull, and the
    strip would then cut straight across the cheek instead of following the
    brow ridge.

    Every sample also carries the uv of the head under it, scaled into the
    skin band of the face atlas.
    """
    import mr_face
    verts = []
    for r in head_tube.rings:
        for vi in r:
            verts.append(vi)
    core = Vector((0.0, -0.008, 1.672))
    out = []
    for i in range(count):
        t = i / (count - 1.0)
        x = side * (0.0160 + 0.0335 * t)
        z = 1.6895 + 0.0060 * math.sin(math.pi * t * 0.85) - 0.0055 * t
        best = None
        bestd = 1e9
        for vi in verts:
            p = mb.verts[vi]
            if p.y > -0.048:
                continue
            d = ((p.x - x) ** 2 + ((p.z - z) * 2.5) ** 2 +
                 ((p.y + 0.098) * 0.45) ** 2)
            if d < bestd:
                bestd = d
                best = p.copy()
        if best is None:
            best = Vector((x, -0.090, z))
        n = (best - core).normalized()
        u, v = head_uv_at(mb, head_tube, best)
        out.append((best, n, (u * mr_face.SKIN_U_SCALE, v)))
    return out


# ---------------------------------------------------------------------------
# facial features that are separate geometry
# ---------------------------------------------------------------------------

def build_face_details(mb, head_tube, mouth_loop, mats):
    """Eyes, eyelids, mouth interior, teeth, tongue and brows.

    `mats` is (sclera, iris, cavity, teeth, brow).  The sclera and the teeth
    share the face texture (different UV rectangles) while the iris and the
    pupil share the dark optic material and are told apart by their own
    rectangle inside the optic texture.
    """
    import mr_face
    sclera_m, iris_m, dark, teeth_m, brow_m = mats
    atlas = mr_face.FACE_ATLAS
    optic = mr_face.OPTIC_ATLAS
    eye_r = eye_l = None
    for side in (1, -1):
        sfx = "r" if side > 0 else "l"
        surf, nrm, c = socket_frame(mb, head_tube, side)
        r_eye = 0.0112
        print("  EYE%s surf=(%.4f %.4f %.4f) n=(%.3f %.3f %.3f) c=(%.4f %.4f %.4f)"
              % (sfx, surf.x, surf.y, surf.z, nrm.x, nrm.y, nrm.z,
                 c.x, c.y, c.z))
        mr_face.add_eyeball(mb, side, c, r_eye, sclera_m, iris_m,
                            part="eye_%s" % sfx, iris_part="iris_%s" % sfx,
                            pupil_part="pupil_%s" % sfx,
                            sclera_uv=atlas["sclera"],
                            iris_uv=optic["iris"], pupil_uv=optic["pupil"])
        mr_face.add_eyelids(mb, side, c, r_eye + 0.0009, sclera_m,
                            upper=True, part="lid_up_%s" % sfx,
                            uv_rect=atlas["lid"])
        mr_face.add_eyelids(mb, side, c, r_eye + 0.0009, sclera_m,
                            upper=False, part="lid_lo_%s" % sfx,
                            uv_rect=atlas["lid"])
        # The brow is painted into the face atlas.  A separate strip of
        # geometry cannot follow the curve of the skull, it would read as a
        # band of tape stuck onto the face.
        if side > 0:
            eye_r = c
        else:
            eye_l = c
    mr_face.add_mouth_cavity(mb, None, mouth_loop, 0.032, dark,
                              part="mouth_cav")
    mr_face.add_teeth(mb, (0.0, -0.056, 1.5975), 0.028, 0.010, teeth_m, True,
                      part="teeth_up", uv_rect=atlas["teeth"])
    mr_face.add_teeth(mb, (0.0, -0.054, 1.5925), 0.026, 0.009, teeth_m, False,
                      part="teeth_lo", uv_rect=atlas["teeth"])
    mr_face.add_tongue(mb, (0.0, -0.056, 1.5860), dark, part="tongue")
    return eye_l, eye_r

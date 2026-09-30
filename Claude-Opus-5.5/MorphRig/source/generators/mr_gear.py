"""MorphRig Operative hard-surface gear, boots, cybernetic arm/hand and props.

Every piece is a Mesh carrying a 'bind' description used by the rigging stage:
  rigid:<bone>        all vertices weighted 1.0 to that bone
  transfer            weights copied from the nearest body-suit surface
  segments            per-vertex bone names stored in attrs['bone_id'] + BONE_TABLE
"""
import numpy as np
from mr_sdf import (Ellipsoid, Sphere, Capsule, RoundCone, RoundBox, EllipticCone, Union, Subtract,
                    Intersect, Plane, Mirror, ray_exit, project, normalize, length, rot_to_local)
from mr_meshkit import Mesh, ring_quads, relax_on_sdf, catmull_clark, make_consistent
from mr_params import J, FOOT_DIR_L, nrm, v, mirror

# ----------------------------------------------------------------- primitives

def cube_sphere_dirs(n):
    """Unit directions + quad faces of a cube-sphere with n x n quads per side."""
    verts = {}
    pts = []
    faces = []

    def vid(p):
        key = tuple(np.round(p, 6))
        if key not in verts:
            verts[key] = len(pts)
            pts.append(p)
        return verts[key]

    g = np.linspace(-1, 1, n + 1)
    for axis in range(3):
        for sign in (-1, 1):
            grid = [[None] * (n + 1) for _ in range(n + 1)]
            for i, a in enumerate(g):
                for j, b in enumerate(g):
                    p = np.zeros(3)
                    p[axis] = sign
                    p[(axis + 1) % 3] = a
                    p[(axis + 2) % 3] = b
                    grid[i][j] = vid(p)
            for i in range(n):
                for j in range(n):
                    f = (grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1])
                    faces.append(f if sign > 0 else f[::-1])
    P = np.array(pts)
    # equal-angle warp for nicer distribution
    P = np.tan(P * np.pi / 4)
    return normalize(P), faces


def sdf_blob(sdf, center, n=8, stretch=(1, 1, 1), relax=4, rot=None):
    """Star-shaped closed mesh: cube-sphere directions ray-cast from centre."""
    D, faces = cube_sphere_dirs(n)
    D = normalize(D * np.asarray(stretch))
    if rot is not None:
        D = D @ np.asarray(rot).T
    O = np.tile(np.asarray(center, float), (len(D), 1))
    t = ray_exit(sdf, O, D, tmax=1.0, max_step=0.002)
    m = Mesh(O + t[:, None] * D, faces)
    fn = m.face_normals()
    cents = np.array([m.v[list(f)].mean(0) for f in m.f])
    if np.mean(((cents - center) * fn).sum(-1)) < 0:
        m.f = [f[::-1] for f in m.f]
    if relax:
        relax_on_sdf(m, sdf, iters=relax, lam=0.35)
    return m


def tube(path_pts, radii, n=12, closed_ends=(True, True), ref=(0, 0, 1)):
    """Simple tube along a polyline with per-point radius (or (rx,ry) ellipse)."""
    from mr_body import _rmf_frames
    P = np.asarray(path_pts, float)
    T, R, B = _rmf_frames(P, ref)
    m = Mesh()
    rings = []
    ang = 2 * np.pi * np.arange(n) / n
    for k in range(len(P)):
        r = radii[k]
        rx, ry = (r, r) if np.isscalar(r) else r
        pts = P[k] + np.cos(ang)[:, None] * R[k] * rx + np.sin(ang)[:, None] * B[k] * ry
        rings.append(m.add_verts(pts))
    for k in range(len(rings) - 1):
        for f in ring_quads(rings[k], rings[k + 1]):
            m.add_face(f)
    if closed_ends[0]:
        c = m.add_verts(P[:1])[0]
        for i in range(n):
            m.add_face((rings[0][(i + 1) % n], rings[0][i], c))
    if closed_ends[1]:
        c = m.add_verts(P[-1:])[0]
        for i in range(n):
            m.add_face((rings[-1][i], rings[-1][(i + 1) % n], c))
    make_consistent(m, outward_point=P.mean(0))
    m.rings = rings
    return m


def box_mesh(center, half, rot=None, bevel=0.0, n=2):
    """Rounded box via a subdivided cube projected on a RoundBox sdf."""
    sdf = RoundBox(v(0, 0, 0), np.asarray(half), max(bevel, 1e-5))
    D, faces = cube_sphere_dirs(n)
    m = Mesh(D * 0.0, faces)
    # place cube-sphere verts on the cube then project onto the rounded box
    Q = D / np.max(np.abs(D), axis=1, keepdims=True) * np.asarray(half)
    m.v = Q
    if bevel > 0:
        m.v = project(sdf, m.v, iters=6)
    if rot is not None:
        m.v = m.v @ np.asarray(rot).T
    m.v = m.v + np.asarray(center)
    return m


def cylinder(p0, p1, r, n=16, caps=True, r1=None):
    return tube([p0, p1], [r, r if r1 is None else r1], n=n, closed_ends=(caps, caps))


def set_bind(m, bind, part):
    m.bind = bind
    m.part = part
    return m


def merge(meshes):
    out = Mesh()
    for mm in meshes:
        out.append(mm)
    return out


# ----------------------------------------------------------------- boots

BOOT_TOP = 0.305


def boot_sdf(side):
    A = J["foot_" + side]
    fd = FOOT_DIR_L.copy()
    if side == "r":
        fd[0] *= -1
    lat = nrm(np.cross(fd, v(0, 0, 1)))
    if side == "r":
        lat = -lat
    axz = v(A[0], A[1], 0)
    items = [
        RoundCone(v(A[0], A[1] + 0.006, BOOT_TOP), v(A[0], A[1] + 0.002, 0.120), 0.0505, 0.0450),  # shaft
        Ellipsoid(axz + v(0, 0, 0.088), v(0.043, 0.048, 0.040)),                     # ankle block
        Ellipsoid(axz - 0.052 * fd + v(0, 0, 0.052), v(0.041, 0.043, 0.050)),        # heel counter
        Ellipsoid(axz + 0.060 * fd + v(0, 0, 0.052), v(0.046, 0.075, 0.040), axis=fd, hint=v(0, 0, 1)),  # midfoot
        Ellipsoid(axz + 0.152 * fd + v(0, 0, 0.036), v(0.047, 0.066, 0.029), axis=fd, hint=v(0, 0, 1)),  # toe box
    ]
    upper = Union(items, k=0.02)
    # lugged sole: thicker than the upper's base and slightly wider (a visible ledge)
    sole = RoundBox(axz + 0.050 * fd + v(0, 0, 0.016), v(0.056, 0.153, 0.016), 0.007,
                    rot=np.stack([lat, fd, v(0, 0, 1)]))
    solid = Union([upper, sole], k=0.006)
    return Intersect(solid, Plane(v(0, 0, 0.0), v(0, 0, -1)), k=0.0)


def build_boot(side="l"):
    from mr_body import build_limb, _rmf_frames, _polyline_eval
    A = J["foot_" + side]
    fd = FOOT_DIR_L.copy()
    if side == "r":
        fd[0] *= -1
    axz = v(A[0], A[1], 0)
    ctrl = [v(A[0], A[1] + 0.006, BOOT_TOP), v(A[0], A[1] + 0.004, 0.200), v(A[0], A[1] + 0.004, 0.120),
            axz + v(0, 0, 0.072) - 0.004 * fd, axz + 0.050 * fd + v(0, 0, 0.050),
            axz + 0.120 * fd + v(0, 0, 0.042), axz + 0.192 * fd + v(0, 0, 0.036)]
    sdf = boot_sdf(side)
    total = _polyline_eval(ctrl, np.array([0.0]))[1]
    s_dense = np.linspace(0, total, 900)
    P, _ = _polyline_eval(ctrl, s_dense)
    T, R, B = _rmf_frames(P, v(0, 1, 0))
    n = 20
    ang = 2 * np.pi * np.arange(n) / n
    m = Mesh()
    rings = []
    s_vals = list(np.linspace(0.0, total - 0.012, 30))
    for s in s_vals:
        i = int(np.clip(np.searchsorted(s_dense, s), 0, len(s_dense) - 1))
        D = np.cos(ang)[:, None] * R[i] + np.sin(ang)[:, None] * B[i]
        O = np.tile(P[i], (n, 1))
        t = ray_exit(sdf, O, D, tmax=0.3, max_step=0.002)
        rings.append(m.add_verts(O + t[:, None] * D))
    for k in range(len(rings) - 1):
        for f in ring_quads(rings[k], rings[k + 1]):
            m.add_face(f)
    from mr_head import quad_cap
    for f in quad_cap(m, rings[-1], n // 4):
        m.add_face(f)
    make_consistent(m, outward_point=P.mean(0))
    fn = m.face_normals()
    cents = np.array([m.v[list(f)].mean(0) for f in m.f])
    if np.mean((fn * sdf.grad(cents)).sum(-1)) < 0:
        m.f = [f[::-1] for f in m.f]
    relax_on_sdf(m, sdf, iters=10, lam=0.35)
    m.group("boot_top", rings[0])
    m.rings = rings
    return set_bind(m, "transfer_boot", "boot_" + side)


# ----------------------------------------------------------------- cybernetic forearm & hand (right)

def forearm_frame(side="r"):
    E, W = J["lowerarm_" + side], J["hand_" + side]
    ax = nrm(W - E)
    # 'top' = dorsal side of the forearm (hand back) in the rest pose
    from mr_hand import hand_frame
    Rl, _ = hand_frame("l")
    back_l = -Rl[:, 2]           # back of the left hand
    top = back_l.copy()
    if side == "r":
        top[0] *= -1
    top = nrm(top - np.dot(top, ax) * ax)
    lat = np.cross(ax, top)
    if side == "r":
        lat = -lat
    # lat points to the thumb side for left; for right mirrored
    return E, W, ax, top, lat


def build_cyber_arm():
    """Right cybernetic forearm: shells, joints, emitter barrel, blade housing, cell cradle."""
    E, W, ax, top, lat = forearm_frame("r")
    L = np.linalg.norm(W - E)
    rot = np.stack([lat, ax, top])  # rows = local axes (x=lat, y=axis, z=top)
    pieces = []

    def P(u, a, t):  # local (lateral, axial, top) -> world
        return E + u * lat + a * ax + t * top

    # elbow joint housing (hinge) — rigid to lowerarm_r
    pieces.append(set_bind(cylinder(P(-0.034, 0.0, 0.0), P(0.034, 0.0, 0.0), 0.030, n=20), "rigid:lowerarm_r", "cyber_elbow"))
    # upper arm socket cap (rigid to upperarm_r): a cup around the end of the sleeve
    Sr = J["upperarm_r"]
    du = nrm(E - Sr)
    cup = tube([E - du * 0.085, E - du * 0.045, E - du * 0.012], [0.041, 0.043, 0.038], n=24,
               closed_ends=(False, True))
    pieces.append(set_bind(cup, "rigid:upperarm_r", "cyber_socket"))
    # forearm core (dark mechanical) — rigid lowerarm_r
    core = tube([P(0, 0.02, 0), P(0, L * 0.5, 0), P(0, L - 0.015, 0)], [(0.024, 0.021), (0.022, 0.019), (0.019, 0.015)],
                n=16, closed_ends=(True, True), ref=top)
    pieces.append(set_bind(core, "rigid:lowerarm_r", "cyber_core"))
    # dorsal armour plate (shell) — rigid lowerarm_r
    sdf_plate = Union([RoundCone(P(0, 0.035, 0.004), P(0, L - 0.030, 0.002), 0.036, 0.029)], k=0.0)
    dorsal = Intersect(sdf_plate, Plane(P(0, 0, -0.002), -top), k=0.004)
    rl = np.stack([lat, ax, top], 1)
    shell_outer = sdf_blob(dorsal, P(0, L * 0.5, 0.008), n=10, stretch=(0.6, 2.4, 0.6), rot=rl, relax=3)
    pieces.append(set_bind(shell_outer, "rigid:lowerarm_r", "cyber_plate_dorsal"))
    ventral = Intersect(Union([RoundCone(P(0, 0.045, -0.004), P(0, L - 0.040, -0.002), 0.033, 0.026)], k=0.0),
                        Plane(P(0, 0, -0.006), top), k=0.004)
    pieces.append(set_bind(sdf_blob(ventral, P(0, L * 0.5, -0.012), n=10, stretch=(0.6, 2.4, 0.6), rot=rl, relax=3),
                           "rigid:lowerarm_r", "cyber_plate_ventral"))
    # wrist ring (rigid lowerarm_twist_r -> follows hand roll)
    pieces.append(set_bind(tube([P(0, L - 0.026, 0), P(0, L - 0.004, 0)], [(0.030, 0.024), (0.028, 0.022)], n=20,
                                ref=top), "rigid:lowerarm_twist_01_r", "cyber_wrist"))
    # emitter barrel on the dorsal side near the wrist
    b0 = P(0.0, L - 0.105, 0.046)
    b1 = P(0.0, L - 0.012, 0.046)
    pieces.append(set_bind(tube([b0, b0 + ax * 0.02, b1 - ax * 0.012, b1], [0.012, 0.014, 0.014, 0.0115], n=16,
                                closed_ends=(True, False), ref=top), "rigid:lowerarm_r", "emitter"))
    muzzle = tube([b1 - ax * 0.004, b1 + ax * 0.008], [0.0135, 0.0105], n=16, closed_ends=(False, False), ref=top)
    pieces.append(set_bind(muzzle, "rigid:lowerarm_r", "emitter_muzzle"))
    # emitter mount between plate and barrel
    pieces.append(set_bind(box_mesh(P(0, L - 0.06, 0.034), v(0.010, 0.040, 0.008), rot=np.stack([lat, ax, top]).T,
                                    bevel=0.003, n=3), "rigid:lowerarm_r", "emitter_mount"))
    # power-cell cradle on the dorsal side, behind the emitter (toward the elbow)
    c0 = P(0.0, 0.070, 0.040)
    cradle = box_mesh(P(0.0, 0.105, 0.030), v(0.017, 0.048, 0.007), rot=np.stack([lat, ax, top]).T, bevel=0.004, n=3)
    pieces.append(set_bind(cradle, "rigid:lowerarm_r", "cell_cradle"))
    # blade housing along the ulnar (outer) side
    hous = box_mesh(P(-0.036, L * 0.52, 0.004), v(0.007, 0.100, 0.013), rot=np.stack([lat, ax, top]).T,
                    bevel=0.004, n=3)
    pieces.append(set_bind(hous, "rigid:lowerarm_r", "blade_housing"))
    return pieces


def cyber_anchor_points():
    """World-space sockets on the right forearm (rest pose)."""
    E, W, ax, top, lat = forearm_frame("r")
    L = np.linalg.norm(W - E)

    def P(u, a, t):
        return E + u * lat + a * ax + t * top
    return {
        "muzzle": P(0.0, L + 0.002, 0.046), "muzzle_dir": ax,
        "cell_slot": P(0.0, 0.105, 0.046), "cell_axis": ax, "cell_up": top,
        "blade_pivot": P(-0.044, L - 0.010, 0.004), "blade_axis_fold": -ax, "blade_side": -lat,
        "top": top, "lat": lat, "ax": ax,
    }


def build_blade():
    """Folding forearm blade in its FOLDED rest pose (tip toward the elbow)."""
    a = cyber_anchor_points()
    piv = a["blade_pivot"]
    d = a["blade_axis_fold"]   # along forearm toward elbow
    side = a["blade_side"]     # outward
    top = a["top"]
    Lb = 0.285
    # blade cross-section: diamond, thin; profile tapers to the tip
    prof = []
    n = 14
    for k in range(n + 1):
        t = k / n
        s = t * Lb
        w = 0.024 * (1 - t ** 1.6) + 0.002          # width (in 'top' direction)
        th = 0.0035 * (1 - 0.7 * t) + 0.0006        # thickness (in 'side' direction)
        c = piv + d * (s + 0.012) + side * 0.004 + top * (0.004 + 0.006 * t)
        prof.append((c, w, th))
    m = Mesh()
    rings = []
    for c, w, th in prof:
        pts = [c + top * w, c + side * th, c - top * w * 0.35, c - side * th]
        rings.append(m.add_verts(np.array(pts)))
    for k in range(len(rings) - 1):
        for f in ring_quads(rings[k], rings[k + 1]):
            m.add_face(f)
    tip = m.add_verts((prof[-1][0] + d * 0.018)[None])[0]
    for i in range(4):
        m.add_face((rings[-1][i], rings[-1][(i + 1) % 4], tip))
    m.add_face(tuple(rings[0][::-1]))
    make_consistent(m, outward_point=np.mean([p[0] for p in prof], 0) + top * 0.002)
    # sharp edges for a crisp blade
    for k in range(len(rings) - 1):
        for i in range(4):
            a_, b_ = rings[k][i], rings[k + 1][i]
            m.sharp.add((min(a_, b_), max(a_, b_)))
    # pivot hub
    hub = cylinder(piv - side * 0.006, piv + side * 0.010, 0.010, n=14)
    out = merge([m, hub])
    return set_bind(out, "rigid:blade_r", "blade")


def build_cyber_hand():
    """Right cybernetic hand: rigid segments per bone, using mirrored hand joints."""
    from mr_hand import hand_joints_world, FINGERS, RADIUS, THUMB_RAD, to_world
    pieces = []
    jw = hand_joints_world("r")
    # palm plate
    from mr_hand import hand_frame
    Rl, o = hand_frame("l")
    X, Y, Z = Rl[:, 0].copy(), Rl[:, 1].copy(), Rl[:, 2].copy()
    for a_ in (X, Y, Z):
        a_[0] *= -1
    rotm = np.stack([X, Y, Z], 1)   # mirrored axes (handedness flips)
    pc = to_world(v(0.048, -0.001, 0.0015), "r")
    palm = box_mesh(v(0, 0, 0), v(0.046, 0.037, 0.0125), bevel=0.008, n=4)
    palm.v = palm.v @ rotm.T + pc
    make_consistent(palm, outward_point=pc)
    pieces.append(set_bind(palm, "rigid:hand_r", "cyber_palm"))
    # knuckle bar
    k0 = to_world(v(0.088, 0.036, -0.004), "r")
    k1 = to_world(v(0.080, -0.037, -0.002), "r")
    pieces.append(set_bind(cylinder(k0, k1, 0.0075, n=12), "rigid:hand_r", "cyber_knuckles"))
    for f in FINGERS + ["thumb"]:
        rad = THUMB_RAD if f == "thumb" else RADIUS[f]
        for k in range(3):
            h, t = jw[f"{f}_0{k + 1}"]
            dirv = nrm(t - h)
            r = rad[k] * 0.95
            seg = tube([h + dirv * 0.0035, h + dirv * 0.35 * np.linalg.norm(t - h), t - dirv * 0.004],
                       [(r * 0.95, r * 0.8), (r, r * 0.85), (r * 0.9, r * 0.75)], n=10, ref=nrm(np.cross(dirv, Y)))
            pieces.append(set_bind(seg, f"rigid:{f}_0{k + 1}_r", f"cyber_{f}_{k + 1}"))
            # joint pin at the base of each segment
            side_ax = nrm(np.cross(dirv, Z))
            pin = cylinder(h - side_ax * r * 0.85, h + side_ax * r * 0.85, r * 0.55, n=10)
            parent = "hand_r" if k == 0 else f"{f}_0{k}_r"
            pieces.append(set_bind(pin, f"rigid:{parent}", f"cyber_{f}_pin{k + 1}"))
    return pieces


# ----------------------------------------------------------------- props

def build_power_cell(center, axis, up):
    ax = nrm(axis)
    upv = nrm(up - np.dot(up, ax) * ax)
    Lc = 0.070
    r = 0.0115
    p0 = center - ax * Lc / 2
    p1 = center + ax * Lc / 2
    path = [p0, p0 + ax * 0.004, p0 + ax * 0.010, p1 - ax * 0.010, p1 - ax * 0.004, p1]
    rad = [r * 0.72, r * 0.98, r, r, r * 0.98, r * 0.72]
    body = tube(path, rad, n=16, ref=upv)
    band = tube([center - ax * 0.012, center + ax * 0.012], [r * 1.06, r * 1.06], n=16, closed_ends=(False, False),
                ref=upv)
    grip = box_mesh(p1 + ax * 0.004, v(0.006, 0.004, 0.006), rot=np.stack([np.cross(ax, upv), ax, upv]).T,
                    bevel=0.002, n=2)
    m = merge([body, band, grip])
    return set_bind(m, "rigid:prop_cell", "power_cell")


def build_beacon(center, up, fwd):
    upv = nrm(up)
    f = nrm(fwd - np.dot(fwd, upv) * upv)
    lat = np.cross(f, upv)
    rotm = np.stack([lat, f, upv], 1)
    # build in local then rotate
    loc = Union([Ellipsoid(v(0, 0, 0), v(0.050, 0.050, 0.014)),
                 Ellipsoid(v(0, 0, 0.010), v(0.028, 0.028, 0.018)),
                 Capsule(v(0, 0, 0.02), v(0, 0, 0.042), 0.0025)], k=0.004)
    body = sdf_blob(loc, v(0, 0, 0.004), n=10, stretch=(1, 1, 0.5), relax=3)
    ring = tube([v(0, 0, -0.004), v(0, 0, 0.004)], [0.0525, 0.0525], n=32, closed_ends=(False, False), ref=v(1, 0, 0))
    legs = []
    for k in range(3):
        a = 2 * np.pi * k / 3 + 0.4
        dirv = v(np.cos(a), np.sin(a), 0)
        legs.append(box_mesh(dirv * 0.050 + v(0, 0, -0.010), v(0.010, 0.004, 0.009),
                             rot=np.stack([np.cross(v(0, 0, 1), dirv), dirv, v(0, 0, 1)]).T, bevel=0.002, n=2))
    m = merge([body, ring] + legs)
    m.v = m.v @ rotm.T + center
    return set_bind(m, "rigid:prop_beacon", "beacon")

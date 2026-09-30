"""MorphRig Operative body-suit surface: SDF anatomy + ring-cage topology.

The suit is one continuous quad mesh: torso (40 around), two arms (20 around,
the right arm ends inside the cybernetic elbow socket), two legs (24 around,
ending inside the boots).  Deformation loops are placed at shoulders, elbows,
wrist, hips, knees.  Openings (neck, wrist, elbow socket, boot tops) are hidden
under the collar, glove cuff, cyber socket and boots.
"""
import numpy as np
from mr_sdf import (Ellipsoid, Sphere, Capsule, RoundCone, EllipticCone, Union, Mirror,
                    ray_exit, project, normalize, length, gauss_bump, Displace)
from mr_meshkit import Mesh, relax_on_sdf, ring_quads, mirror_pairs, enforce_symmetry
from mr_params import J, ARM_DIR_UP, ARM_DIR_FO, nrm, v

N_TORSO = 40
N_ARM = 24
N_LEG = 24


# ----------------------------------------------------------------- anatomy
def torso_sdf():
    return Union([
        Ellipsoid((0, 0.020, 0.928), (0.146, 0.100, 0.115)),               # pelvis
        Mirror(Ellipsoid((0.058, 0.060, 0.890), (0.068, 0.058, 0.090))),   # gluteus
        Ellipsoid((0, 0.022, 1.060), (0.132, 0.088, 0.140)),               # waist / abdomen
        Ellipsoid((0, 0.032, 1.240), (0.138, 0.104, 0.170)),               # rib cage
        Ellipsoid((0, 0.030, 1.340), (0.165, 0.100, 0.108)),               # upper chest
        Mirror(Ellipsoid((0.070, -0.040, 1.338), (0.084, 0.034, 0.060))),  # pectoralis
        Mirror(Ellipsoid((0.104, 0.052, 1.290), (0.056, 0.056, 0.115))),   # latissimus
        Mirror(Ellipsoid((0.112, 0.012, 1.150), (0.040, 0.070, 0.090))),   # obliques
        Mirror(Capsule((0.030, 0.052, 1.462), (0.150, 0.044, 1.440), 0.040)),  # trapezius
        Capsule((0, 0.030, 1.400), (0, 0.020, 1.585), 0.055),              # neck
        Mirror(Sphere((0.166, 0.030, 1.408), 0.050)),                      # shoulder mass
    ], k=0.035)


def arm_sdf(side):
    s = 1.0 if side == "l" else -1.0
    S, E, W = J["upperarm_" + side], J["lowerarm_" + side], J["hand_" + side]
    du = nrm(E - S)
    df = nrm(W - E)
    back = v(0, 1, 0)
    up_perp = nrm(np.cross(du, v(0, 1, 0)) * s)  # roughly perpendicular "top" of arm
    if up_perp[2] < 0:
        up_perp = -up_perp
    items = [
        Ellipsoid(S + 0.045 * du + 0.012 * up_perp, (0.050, 0.090, 0.049), axis=du, hint=(0, 1, 0)),  # deltoid
        RoundCone(S, E, 0.045, 0.035),                                         # humerus mass
        Ellipsoid(S + 0.55 * (E - S) - 0.012 * back, (0.027, 0.080, 0.027), axis=du),  # biceps
        Ellipsoid(S + 0.42 * (E - S) + 0.013 * back + 0.004 * up_perp, (0.029, 0.095, 0.028), axis=du),  # triceps
        Sphere(E, 0.033),                                                      # elbow
        RoundCone(E, W, 0.037, 0.025),                                         # forearm
        Ellipsoid(E + 0.26 * (W - E), (0.036, 0.075, 0.032), axis=df),         # forearm muscles
        EllipticCone(E + 0.55 * (W - E), W, (0.030, 0.022), (0.027, 0.019), hint=up_perp),  # flattened wrist
    ]
    return Union(items, k=0.03)


def leg_sdf(side):
    H, K, A = J["thigh_" + side], J["calf_" + side], J["foot_" + side]
    s = 1.0 if side == "l" else -1.0
    dt = nrm(K - H)
    ds = nrm(A - K)
    items = [
        RoundCone(H + v(0, 0, 0.02), K, 0.084, 0.049),                               # femur mass
        Ellipsoid(H + 0.42 * (K - H) + v(0.010 * s, -0.030, 0), (0.049, 0.17, 0.043), axis=dt),   # quadriceps
        Ellipsoid(H + 0.40 * (K - H) + v(0, 0.034, 0), (0.049, 0.16, 0.040), axis=dt),            # hamstrings
        Ellipsoid(H + 0.25 * (K - H) + v(-0.034 * s, 0.0, 0), (0.040, 0.12, 0.044), axis=dt),    # adductors
        Sphere(K + v(0, -0.004, 0), 0.047),                                           # knee
        Ellipsoid(K + v(0, -0.036, 0.012), (0.021, 0.013, 0.027)),                  # patella
        RoundCone(K, A, 0.048, 0.029),                                                # tibia
        Ellipsoid(K + 0.27 * (A - K) + v(0, 0.031, 0), (0.044, 0.11, 0.039), axis=ds),            # gastrocnemius
        Sphere(A, 0.032),
    ]
    return Union(items, k=0.03)


def body_sdf():
    return Union([torso_sdf(), arm_sdf("l"), arm_sdf("r"), leg_sdf("l"), leg_sdf("r")], k=0.028)


# ----------------------------------------------------------------- helpers
def _ring_dirs(n, phase=0.0):
    phi = 2 * np.pi * (np.arange(n) + phase) / n
    return phi


def _rmf_frames(points, first_ref):
    """Rotation minimizing frames along a polyline. Returns tangents, refs, binormals."""
    P = np.asarray(points)
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]
    T[0] = P[1] - P[0]
    T[-1] = P[-1] - P[-2]
    T = normalize(T)
    R = np.zeros_like(P)
    r = np.asarray(first_ref, float)
    r = normalize(r - np.dot(r, T[0]) * T[0])
    R[0] = r
    for i in range(1, len(P)):
        r = R[i - 1] - np.dot(R[i - 1], T[i]) * T[i]
        R[i] = normalize(r)
    B = np.cross(T, R)
    return T, R, B


def _polyline_eval(ctrl, s):
    """Evaluate a polyline (with smoothed corners via Catmull-Rom) at arc params s (metres)."""
    ctrl = np.asarray(ctrl, float)
    # dense Catmull-Rom sampling
    pts = []
    n = len(ctrl)
    for i in range(n - 1):
        p0 = ctrl[max(i - 1, 0)]
        p1 = ctrl[i]
        p2 = ctrl[i + 1]
        p3 = ctrl[min(i + 2, n - 1)]
        for t in np.linspace(0, 1, 60, endpoint=False):
            t2, t3 = t * t, t * t * t
            pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    pts.append(ctrl[-1])
    pts = np.array(pts)
    seg = length(pts[1:] - pts[:-1])
    cum = np.concatenate([[0], np.cumsum(seg)])
    out = np.stack([np.interp(s, cum, pts[:, k]) for k in range(3)], -1)
    return out, cum[-1]


# ----------------------------------------------------------------- torso
def build_torso(m, tsdf):
    """Rings of N_TORSO verts; returns list of ring index arrays (bottom->top)."""
    phi = _ring_dirs(N_TORSO)
    dirs_h = np.stack([np.sin(phi), -np.cos(phi), np.zeros_like(phi)], -1)
    rings = []
    zs = np.linspace(0.846, 1.335, 23)
    for i, z in enumerate(zs):
        yc = np.interp(z, [0.85, 1.0, 1.2, 1.34], [0.018, 0.012, 0.028, 0.026])
        amp = 0.068 * max(0.0, 1.0 - i / 6.0) ** 1.5
        zz = z + amp * np.sin(phi) ** 2 - 0.006 * max(0.0, 1.0 - i / 4.0) * (np.cos(phi) > 0)
        O = np.stack([np.zeros(N_TORSO), np.full(N_TORSO, yc), zz], -1)
        t = ray_exit(tsdf, O, dirs_h)
        pts = O + t[:, None] * dirs_h
        rings.append(m.add_verts(pts))
    # shoulder cap: elevated rays from upper chest centre
    ctop = v(0, 0.026, 1.335)
    elev = np.radians(np.array([8, 16, 24, 32, 40, 48, 56, 64, 71]))
    for e in elev:
        d = np.stack([np.sin(phi) * np.cos(e), -np.cos(phi) * np.cos(e), np.full_like(phi, np.sin(e))], -1)
        O = np.tile(ctop, (N_TORSO, 1))
        t = ray_exit(tsdf, O, d)
        rings.append(m.add_verts(O + t[:, None] * d))
    return rings


def _hole_boundary_faces(rings, hole, n):
    """Ordered boundary loop of a set of (row, col) torso face cells."""
    def cell_verts(i, j):
        return (rings[i][j % n], rings[i][(j + 1) % n], rings[i + 1][(j + 1) % n], rings[i + 1][j % n])
    count = {}
    for (i, j) in hole:
        f = cell_verts(i, j)
        for k in range(4):
            a, b = f[k], f[(k + 1) % 4]
            key = (min(a, b), max(a, b))
            count[key] = count.get(key, 0) + 1
    bedges = [k for k, c in count.items() if c == 1]
    adj = {}
    for a, b in bedges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = bedges[0][0]
    loop = [start]
    prev = None
    cur = start
    while True:
        nxt = [x for x in adj[cur] if x != prev]
        nx = nxt[0]
        if nx == start:
            break
        loop.append(nx)
        prev, cur = cur, nx
        if len(loop) > 1000:
            raise RuntimeError("hole loop failed")
    return loop


def build_limb(m, ring0, axis_ctrl, s_list, part_sdf, full_sdf, n_ring, n_blend, ref_dir):
    """Create rings along a limb starting from an existing loop ring0 (vertex ids).

    The first n_blend rings are lofted (position interpolation) from ring0 to the
    first ray-cast ring, then projected onto the full anatomy; later rings are
    ray-cast perpendicular to the limb axis on the part sdf.  Angular
    correspondence uses a shared world reference direction so the loft cannot
    twist.
    """
    total_len = _polyline_eval(axis_ctrl, np.array([0.0]))[1]
    s_dense = np.linspace(0, total_len, 900)
    P, _ = _polyline_eval(axis_ctrl, s_dense)
    T, R, B = _rmf_frames(P, ref_dir)

    def frame_at(s):
        i = int(np.clip(np.searchsorted(s_dense, s), 0, len(s_dense) - 1))
        return P[i], T[i], R[i], B[i]

    ref = normalize(np.asarray(ref_dir, float))
    ring0 = np.asarray(ring0)
    s_first = s_list[n_blend]
    c1, T1, R1, B1 = frame_at(s_first)
    # loop plane
    p0 = m.v[ring0]
    cen = p0.mean(0)
    w = p0 - cen
    _, _, vt = np.linalg.svd(w)
    n0 = vt[2]
    if np.dot(n0, T1) < 0:
        n0 = -n0
    r0 = normalize(ref - np.dot(ref, n0) * n0)
    b0 = np.cross(n0, r0)
    ang = np.unwrap(np.arctan2(w @ b0, w @ r0))
    if ang[-1] < ang[0]:
        ring0 = ring0[::-1].copy()
        p0 = m.v[ring0]
        w = p0 - cen
        ang = np.unwrap(np.arctan2(w @ b0, w @ r0))
    if not np.all(np.diff(ang) > 0):
        print("WARN non-monotonic ring0 angles", np.round(np.degrees(np.diff(ang)), 1))
    # target angles: uniform, starting at the angle of vertex 0
    tgt = ang[0] + 2 * np.pi * np.arange(n_ring) / n_ring
    rt = normalize(ref - np.dot(ref, T1) * T1)
    bt = np.cross(T1, rt)
    dirs = np.cos(tgt)[:, None] * rt[None] + np.sin(tgt)[:, None] * bt[None]
    rmf_ang = np.arctan2(dirs @ B1, dirs @ R1)

    def cast_ring(s):
        c, tt, rr, bb = frame_at(s)
        D = np.cos(rmf_ang)[:, None] * rr[None, :] + np.sin(rmf_ang)[:, None] * bb[None, :]
        O = np.tile(c, (len(rmf_ang), 1))
        tr = ray_exit(part_sdf, O, D)
        return O + tr[:, None] * D

    target = cast_ring(s_first)
    rings = [ring0]
    cen0 = p0.mean(0)
    # make sure the loft origin is inside the anatomy
    for _ in range(20):
        f0 = full_sdf(cen0[None])[0]
        if f0 < -0.008:
            break
        g0 = normalize(full_sdf.grad(cen0[None])[0])
        cen0 = cen0 - g0 * 0.004
    for k in range(n_blend):
        wgt = (k + 1) / float(n_blend + 1)
        wgt = wgt * wgt * (3 - 2 * wgt)
        lin = (1 - wgt) * p0 + wgt * target
        ck = (1 - wgt) * cen0 + wgt * c1
        D = normalize(lin - ck)
        O = np.tile(ck, (len(D), 1))
        tr = ray_exit(full_sdf, O, D)
        rings.append(m.add_verts(O + tr[:, None] * D))
    for s in s_list[n_blend:]:
        rings.append(m.add_verts(cast_ring(s)))
    return rings


def build_suit():
    m = Mesh()
    tsdf = torso_sdf()
    full = body_sdf()
    rings = build_torso(m, tsdf)
    nr = len(rings)
    n = N_TORSO

    # ---- decide arm-hole rows: rings whose side point (phi=90) lies in shoulder band
    side_z = np.array([m.v[r[10]][2] for r in rings])
    hole_rows = {}
    hole_cells = {}
    faces_skip = set()
    for side, jc in (("l", 10), ("r", 30)):
        i0 = int(np.argmin(np.abs(side_z - 1.262)))
        i1 = i0 + 8
        j0, j1 = jc - 2, jc + 2
        hole_rows[side] = (i0, i1, j0, j1)
        corners = {(i0, j0), (i0, j1 - 1), (i1 - 1, j0), (i1 - 1, j1 - 1)}
        cells = set()
        for i in range(i0, i1):
            for j in range(j0, j1):
                if (i, j) in corners:
                    continue
                cells.add((i, j % n))
        hole_cells[side] = cells
        faces_skip |= cells
    # torso faces
    for i in range(nr - 1):
        for j in range(n):
            if (i, j) in faces_skip:
                continue
            a, b = rings[i][j], rings[i][(j + 1) % n]
            c, d = rings[i + 1][(j + 1) % n], rings[i + 1][j]
            m.add_face((a, b, c, d), part=0)
    m.group("neck_opening", rings[-1])
    m.group("torso")
    m.groups["torso"][:] = True

    # ---- arms
    arm_rings = {}
    for side in ("l", "r"):
        i0, i1, j0, j1 = hole_rows[side]
        loop = _hole_boundary_faces(rings, hole_cells[side], n)
        S, E, W = J["upperarm_" + side], J["lowerarm_" + side], J["hand_" + side]
        du = nrm(E - S)
        ctrl = [S - 0.06 * du, S, E, W + 0.01 * nrm(W - E)]
        # reference "top" direction for the ring angle origin
        ref = v(0, 0, 1)
        # orientation check: loop must be CCW around the axis (right-hand about du)
        up_len = np.linalg.norm(E - S) + 0.06
        fo_len = np.linalg.norm(W - E)
        if side == "l":
            s_list = list(np.arange(0.155, up_len + fo_len + 0.005, 0.02))
        else:
            s_list = list(np.arange(0.155, up_len - 0.006, 0.02))
        # denser rings around the elbow
        s_list = _densify(s_list, up_len, 0.035, 0.013)
        arm = arm_sdf(side)
        ar = build_limb(m, loop, ctrl, s_list, arm, full, N_ARM, n_blend=5, ref_dir=ref)
        for k in range(len(ar) - 1):
            for f in ring_quads(ar[k], ar[k + 1], closed=True, flip=False):
                m.add_face(f, part=1 if side == "l" else 2)
        arm_rings[side] = ar
        m.group("arm_" + side, np.concatenate(ar))
        m.group("arm_end_" + side, ar[-1])
        m.group("arm_root_" + side, ar[0])

    # ---- legs: inguinal loops share the torso bottom ring and a crotch path
    bottom = rings[0]
    yb_front = m.v[bottom[0]][1]
    yb_back = m.v[bottom[20]][1]
    cy = [yb_front + (yb_back - yb_front) * f for f in (0.25, 0.5, 0.75)]
    O = np.array([v(0, y, 0.90) for y in cy])
    D = np.tile(v(0, 0, -1), (3, 1))
    tt = ray_exit(full, O, D)
    crotch = m.add_verts(O + tt[:, None] * D)
    loop_l = [bottom[j] for j in range(0, 21)] + [crotch[2], crotch[1], crotch[0]]
    loop_r = [bottom[j % n] for j in range(20, 41)] + [crotch[0], crotch[1], crotch[2]]
    leg_rings = {}
    for side, loop in (("l", loop_l), ("r", loop_r)):
        H, K, A = J["thigh_" + side], J["calf_" + side], J["foot_" + side]
        ctrl = [H + v(0, 0, 0.08), H, K, A]
        dt = nrm(K - H)
        thigh_len = np.linalg.norm(K - H) + 0.08
        s_end = thigh_len + np.linalg.norm(A - K) - 0.17
        s_list = list(np.arange(0.232, s_end, 0.022))
        s_list = _densify(s_list, thigh_len, 0.04, 0.015)
        leg = leg_sdf(side)
        lr = build_limb(m, loop, ctrl, s_list, leg, full, N_LEG, n_blend=3, ref_dir=v(0, -1, 0))
        for k in range(len(lr) - 1):
            for f in ring_quads(lr[k], lr[k + 1], closed=True, flip=False):
                m.add_face(f, part=3 if side == "l" else 4)
        leg_rings[side] = lr
        m.group("leg_" + side, np.concatenate(lr))
        m.group("leg_end_" + side, lr[-1])

    # fix orientation: ensure outward normals using the full sdf gradient
    _orient_outward(m, full)
    # relax on the full anatomy
    pinned = np.zeros(m.nv, bool)
    pairs = mirror_pairs(m, tol=3e-3)
    m.sym_pairs = pairs
    relax_on_sdf(m, full, iters=12, lam=0.45, pinned=pinned, sym_pairs=pairs)
    m.v = project(full, m.v, iters=4)
    enforce_symmetry(m, pairs)

    # UV seams: back centre of torso, arm undersides, leg inner lines, junction loops
    m.mark_seam_path([r[20] for r in rings])
    for side in ("l", "r"):
        ar = arm_rings[side]
        m.mark_seam_loop(list(ar[0]))
        # underside: vertex index whose direction is most downward at first full ring
        k = len(ar) // 2
        cen = m.v[ar[k]].mean(0)
        j = int(np.argmin(m.v[ar[k]][:, 2] - cen[2] + 0 * cen[0]))
        m.mark_seam_path([ar[kk][j] for kk in range(1, len(ar))])
        lr = leg_rings[side]
        m.mark_seam_loop(list(lr[0]))
        k = len(lr) // 2
        cen = m.v[lr[k]].mean(0)
        sgn = 1.0 if side == "l" else -1.0
        j = int(np.argmin(sgn * (m.v[lr[k]][:, 0] - cen[0])))  # medial side
        m.mark_seam_path([lr[kk][j] for kk in range(1, len(lr))])
    m.compact()          # drop vertices left inside the arm openings (no faces reference them)
    return m, full


def _densify(s_list, center, halfwidth, step):
    s = [x for x in s_list if abs(x - center) > halfwidth]
    extra = list(np.arange(center - halfwidth, center + halfwidth + 1e-6, step))
    out = sorted(s + extra)
    # remove near duplicates
    res = []
    for x in out:
        if not res or x - res[-1] > 0.008:
            res.append(x)
    return res


def _orient_outward(m, sdf):
    fn = m.face_normals()
    cents = np.array([m.v[list(f)].mean(0) for f in m.f])
    g = normalize(sdf.grad(cents))
    dots = (fn * g).sum(-1)
    flips = 0
    for i, d in enumerate(dots):
        if d < 0:
            m.f[i] = tuple(reversed(m.f[i]))
            flips += 1
    return flips

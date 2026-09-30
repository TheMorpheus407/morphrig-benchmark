"""MorphRig Operative hands.

The organic hand is built for the LEFT side in a hand-local frame
(X toward the fingertips, Y toward the thumb, Z out of the palm) and placed
at the left wrist.  The cybernetic hand is built with the same joint layout
and mirrored to the right side, so both hands share one bone topology.

Topology: palm tube of 20 vertices; distal knuckle cap 8x2 quads; each finger
is an 8-vertex tube with three loops per joint; the thumb attaches to a 2x2
opening on the radial side of the palm.
"""
import numpy as np
from mr_sdf import (Ellipsoid, Sphere, Capsule, RoundCone, RoundBox, EllipticCone, Union,
                    ray_exit, project, normalize, length)
from mr_meshkit import Mesh, ring_quads, relax_on_sdf
from mr_params import J, ARM_DIR_FO, PALM_NORMAL_L, HAND_THUMB_DIR_L, nrm, v

FINGERS = ["index", "middle", "ring", "pinky"]

# joint layout (hand-local, metres)
MCP = {"index": v(0.0930, 0.0280, 0.0010), "middle": v(0.0970, 0.0085, 0.0000),
       "ring": v(0.0930, -0.0110, 0.0005), "pinky": v(0.0840, -0.0290, 0.0025)}
SEG_LEN = {"index": (0.0410, 0.0240, 0.0215), "middle": (0.0450, 0.0280, 0.0225),
           "ring": (0.0420, 0.0265, 0.0215), "pinky": (0.0330, 0.0200, 0.0195)}
SPLAY_DEG = {"index": 5.0, "middle": 0.5, "ring": -4.0, "pinky": -9.0}
RADIUS = {"index": (0.0093, 0.0086, 0.0078, 0.0068), "middle": (0.0096, 0.0089, 0.0080, 0.0070),
          "ring": (0.0090, 0.0084, 0.0076, 0.0066), "pinky": (0.0080, 0.0074, 0.0068, 0.0060)}
REST_CURL_DEG = (6.0, 9.0, 6.0)   # MCP, PIP, DIP flexion in the rest pose
CARPAL = {"index": v(0.012, 0.016, 0.0), "middle": v(0.012, 0.005, 0.0),
          "ring": v(0.012, -0.007, 0.0), "pinky": v(0.012, -0.018, 0.001)}  # metacarpal bases

THUMB_CMC = v(0.016, 0.019, 0.010)
THUMB_DIRS = [nrm(v(0.66, 0.62, 0.42)), nrm(v(0.80, 0.52, 0.30)), nrm(v(0.90, 0.36, 0.24))]
THUMB_LEN = (0.046, 0.033, 0.029)
THUMB_RAD = (0.0125, 0.0105, 0.0094, 0.0080)


def _rot(axis, deg):
    axis = nrm(axis)
    a = np.radians(deg)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def finger_joints(name):
    """Hand-local joint positions: MCP, PIP, DIP, TIP (with rest curl and splay)."""
    d = _rot(v(0, 0, 1), SPLAY_DEG[name]) @ v(1, 0, 0)
    side = nrm(np.cross(v(0, 0, 1), d))  # flexion axis (curling toward +Z = palm)
    pts = [MCP[name]]
    cur = d.copy()
    for k, L in enumerate(SEG_LEN[name]):
        cur = _rot(-side, REST_CURL_DEG[k]) @ cur  # flex toward the palm
        pts.append(pts[-1] + L * cur)
    return pts


def thumb_joints():
    pts = [THUMB_CMC]
    for d, L in zip(THUMB_DIRS, THUMB_LEN):
        pts.append(pts[-1] + L * d)
    return pts


def hand_frame(side="l"):
    """World matrix (3x3 rotation, origin) of the LEFT hand-local frame."""
    X = nrm(ARM_DIR_FO)
    Y = nrm(HAND_THUMB_DIR_L)
    Z = np.cross(X, Y)            # points out of the palm (see mr_params)
    R = np.stack([X, Y, Z], 1)    # columns = local axes in world
    return R, J["hand_l"].copy()


def to_world(p_local, side="l"):
    R, o = hand_frame("l")
    w = (np.asarray(p_local) @ R.T) + o
    if side == "r":
        w = w * np.array([-1.0, 1.0, 1.0])
    return w


def hand_joints_world(side="l"):
    """Bone head/tail positions for the hand skeleton in world space."""
    out = {}
    for f in FINGERS:
        pts = finger_joints(f)
        out[f + "_metacarpal"] = (to_world(CARPAL[f], side), to_world(pts[0], side))
        for k in range(3):
            out[f"{f}_0{k + 1}"] = (to_world(pts[k], side), to_world(pts[k + 1], side))
    tp = thumb_joints()
    for k in range(3):
        out[f"thumb_0{k + 1}"] = (to_world(tp[k], side), to_world(tp[k + 1], side))
    return out


# ------------------------------------------------------------------ organic hand
def hand_sdf():
    items = [
        RoundBox(v(0.046, -0.001, 0.0015), v(0.050, 0.0385, 0.0138), 0.0115),     # palm slab
        Ellipsoid(v(0.032, 0.022, 0.0105), v(0.030, 0.0165, 0.0125), axis=v(0.8, 0.45, 0.3)),  # thenar
        Ellipsoid(v(0.047, -0.029, 0.0095), v(0.040, 0.0120, 0.0095), axis=v(1, 0, 0)),         # hypothenar
        EllipticCone(v(-0.035, 0, 0.0005), v(0.012, 0, 0.0015), (0.0265, 0.0185), (0.030, 0.0165),
                     hint=v(0, 0, 1)),                                                 # wrist
    ]
    for f in FINGERS:
        pts = finger_joints(f)
        r = RADIUS[f]
        items.append(Sphere(pts[0] + v(-0.004, 0.0, -0.0030), r[0] * 0.80))           # knuckle
        for k in range(3):
            items.append(RoundCone(pts[k], pts[k + 1] - (pts[k + 1] - pts[k]) * (0.12 if k == 2 else 0.0),
                                   r[k], r[k + 1]))
    tp = thumb_joints()
    for k in range(3):
        items.append(RoundCone(tp[k], tp[k + 1] - (tp[k + 1] - tp[k]) * (0.12 if k == 2 else 0.0),
                               THUMB_RAD[k], THUMB_RAD[k + 1]))
    return Union(items, k=0.0065)


def finger_sdf(f):
    pts = finger_joints(f)
    r = RADIUS[f]
    items = [RoundCone(pts[k], pts[k + 1] - (pts[k + 1] - pts[k]) * (0.12 if k == 2 else 0.0), r[k], r[k + 1])
             for k in range(3)]
    return Union(items, k=0.004)


def thumb_sdf():
    tp = thumb_joints()
    items = [RoundCone(tp[k], tp[k + 1] - (tp[k + 1] - tp[k]) * (0.12 if k == 2 else 0.0),
                       THUMB_RAD[k], THUMB_RAD[k + 1]) for k in range(3)]
    return Union(items, k=0.004)


def _palm_ring_pts(x, sdf):
    """20 points around the palm cross-section at hand-local x (cast from centre)."""
    # parametrise: 9 palmar (+Z) from pinky->index, side (index), 9 dorsal index->pinky, side (pinky)
    ys = np.linspace(-0.031, 0.031, 9)
    O = []
    D = []
    c = v(x, -0.001, 0.0015)
    for y in ys:                         # palmar row (pinky -> index)
        O.append(v(x, y * 0.72, 0.0015))
        D.append(nrm(v(0, y * 0.35, 1.0)))
    O.append(c.copy())
    D.append(v(0, 1, 0))                 # index side
    for y in ys[::-1]:                   # dorsal row (index -> pinky)
        O.append(v(x, y * 0.72, 0.0015))
        D.append(nrm(v(0, y * 0.35, -1.0)))
    O.append(c.copy())
    D.append(v(0, -1, 0))                # pinky side
    O = np.array(O)
    D = np.array(D)
    t = ray_exit(sdf, O, D, tmax=0.1)
    return O + t[:, None] * D


def build_organic_hand():
    """Left organic hand in hand-local coordinates. Returns Mesh with groups."""
    m = Mesh()
    sdf = hand_sdf()
    xs = [-0.030, -0.018, -0.006, 0.006, 0.020, 0.036, 0.052, 0.068, 0.082]
    rings = [m.add_verts(_palm_ring_pts(x, sdf)) for x in xs]
    # ring layout: 0..8 palmar (pinky->index), 9 index side, 10..18 dorsal (index->pinky), 19 pinky side
    # thumb opening: faces between rings 2..4 spanning palmar[7]->palmar[8]->side9->dorsal10
    thumb_cells = {(2, 7), (2, 8), (3, 7), (3, 8)}
    for i in range(len(rings) - 1):
        for j in range(20):
            if (i, j) in thumb_cells:
                continue
            m.add_face((rings[i][j], rings[i][(j + 1) % 20], rings[i + 1][(j + 1) % 20], rings[i + 1][j]))
    # distal cap grid: rows = palmar row, middle row, dorsal row; cols 0..8 (pinky -> index)
    last = rings[-1]
    palmar = [last[j] for j in range(9)]
    dorsal = [last[18 - j] for j in range(9)]       # dorsal row reordered pinky->index
    xcap = xs[-1] + 0.006
    mid_pts = []
    for j in range(1, 8):
        pm = 0.5 * (m.v[palmar[j]] + m.v[dorsal[j]])
        mid_pts.append(pm + v(0.006, 0, 0))
    mid = [last[19]] + list(m.add_verts(np.array(mid_pts))) + [last[9]]
    grid = [palmar, mid, dorsal]
    finger_cols = {"pinky": 0, "ring": 2, "middle": 4, "index": 6}
    skip = set()
    for f, c0 in finger_cols.items():
        for r in range(2):
            for c in range(c0, c0 + 2):
                skip.add((r, c))
    for r in range(2):
        for c in range(8):
            if (r, c) in skip:
                continue
            m.add_face((grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]))
    m.group("wrist_open", rings[0])
    # fingers
    from mr_body import build_limb
    finger_rings = {}
    for f, c0 in finger_cols.items():
        loop = [grid[0][c0], grid[0][c0 + 1], grid[0][c0 + 2], grid[1][c0 + 2],
                grid[2][c0 + 2], grid[2][c0 + 1], grid[2][c0], grid[1][c0]]
        pts = finger_joints(f)
        ctrl = [pts[0] - (pts[1] - pts[0]) * 0.35] + pts
        L0 = np.linalg.norm(pts[1] - pts[0]) * 0.35
        lens = SEG_LEN[f]
        j1 = L0 + lens[0]
        j2 = j1 + lens[1]
        tip = j2 + lens[2]
        s_list = [L0 + 0.30 * lens[0], L0 + 0.62 * lens[0],
                  j1 - 0.004, j1 + 0.0005, j1 + 0.005,
                  j1 + 0.55 * lens[1],
                  j2 - 0.0035, j2 + 0.0005, j2 + 0.0045,
                  j2 + 0.55 * lens[2], tip - 0.0045]
        fr = build_limb(m, loop, ctrl, s_list, finger_sdf(f), sdf, 8, n_blend=1, ref_dir=v(0, 0, -1))
        for k in range(len(fr) - 1):
            for fc in ring_quads(fr[k], fr[k + 1], closed=True):
                m.add_face(fc)
        # tip cap
        from mr_head import quad_cap
        for fc in quad_cap(m, fr[-1], 2):
            m.add_face(fc)
        finger_rings[f] = fr
        m.group("finger_" + f, np.concatenate(fr))
    # thumb
    tl = [rings[2][7], rings[2][8], rings[2][9], rings[3][9], rings[4][9], rings[4][8], rings[4][7], rings[3][7]]
    tp = thumb_joints()
    ctrl = [tp[0] - (tp[1] - tp[0]) * 0.2] + tp
    base = np.linalg.norm(tp[1] - tp[0]) * 0.2
    L = THUMB_LEN
    j1 = base + L[0]
    j2 = j1 + L[1]
    tip = j2 + L[2]
    s_list = [base + 0.55 * L[0], base + 0.8 * L[0], j1 - 0.004, j1 + 0.001, j1 + 0.006,
              j1 + 0.55 * L[1], j2 - 0.0035, j2 + 0.001, j2 + 0.005, j2 + 0.55 * L[2], tip - 0.005]
    tr = build_limb(m, tl, ctrl, s_list, thumb_sdf(), sdf, 8, n_blend=2, ref_dir=v(0, -1, 1))
    for k in range(len(tr) - 1):
        for fc in ring_quads(tr[k], tr[k + 1], closed=True):
            m.add_face(fc)
    from mr_head import quad_cap
    for fc in quad_cap(m, tr[-1], 2):
        m.add_face(fc)
    m.group("finger_thumb", np.concatenate(tr))
    # orientation + relax
    from mr_meshkit import make_consistent
    make_consistent(m, outward_point=v(0.05, 0.0, 0.0015))
    fn = m.face_normals()
    cents = np.array([m.v[list(fc)].mean(0) for fc in m.f])
    g = sdf.grad(cents)
    if np.mean((fn * g).sum(-1)) < 0:
        m.f = [tuple(reversed(fc)) for fc in m.f]
    relax_on_sdf(m, sdf, iters=6, lam=0.3)
    m.compact()          # remove the vertices left inside the finger/thumb openings
    m.finger_rings = finger_rings
    m.thumb_rings = tr
    m.palm_rings = rings
    return m, sdf


def place(m, side="l"):
    """Transform a hand-local mesh to world; mirror for the right side."""
    out = Mesh(to_world(m.v, "l"), m.f)
    out.groups = {k: g.copy() for k, g in m.groups.items()}
    out.attrs = {k: a.copy() for k, a in m.attrs.items()}
    out.face_attrs = {k: list(a) for k, a in m.face_attrs.items()}
    out.seams = set(m.seams)
    out.sharp = set(m.sharp)
    if side == "r":
        out.v[:, 0] *= -1
        out.f = [tuple(reversed(f)) for f in out.f]
    return out

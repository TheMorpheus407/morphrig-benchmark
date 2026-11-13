"""Secondary motion: the occipital data cable (controls cable_01..04) trails the head as a damped chain.

The result is keyed onto the FK cable controls of the source action (one key per frame), so it stays editable:
delete the cable keys to animate the cable by hand, or run the bake again after changing the body animation
(rig UI: "Bake cable").
"""
import bpy
import numpy as np
from . import animio
from .animkit import m_to_q

CABLE = ['cable_01', 'cable_02', 'cable_03', 'cable_04']
STIFF = [1.0, 0.40, 0.19, 0.10, 0.065]       # pull towards the rest shape (in head space) per sub-step, root -> tip
DAMP = 0.87
GRAVITY = 9.81 * 0.40
SUBSTEPS = 3
# colliders: (bone, rest-space centre, radius)
COLLIDERS = [('head', (0.0, 0.012, 1.700), 0.086), ('neck_01', (0.0, 0.016, 1.515), 0.052), ('spine_03', (0.0, 0.026, 1.385), 0.100),
             ('spine_03', (0.0, 0.022, 1.300), 0.108), ('spine_02', (0.0, 0.016, 1.180), 0.105)]


def _strip_cable_curves(action, slot):
    cb = animio.channelbag(action, slot)
    if cb is None:
        return None
    for fc in list(cb.fcurves):
        if any(('pose.bones["%s"]' % b) in fc.data_path for b in CABLE):
            cb.fcurves.remove(fc)
    return cb


def _shortest_arc(a, b):
    """Rotation matrix turning unit vector a into unit vector b."""
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))
    if s < 1e-9:
        return np.eye(3)
    k = v / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * K + (1 - c) * (K @ K)


def bake_cable(rig, action, slot, n_frames, loop=False, is_pose=False, fps=30.0):
    """Simulate the cable for the action and key the four cable controls. Returns the simulated joint positions."""
    from . import rig as rigmod
    sc = bpy.context.scene
    cb = _strip_cable_curves(action, slot)
    rigmod.reset_pose(rig)
    animio.assign(rig, action, slot)
    bones = rig.data.bones
    rest = {b: np.array(bones[b].matrix_local) for b in CABLE + ['head', 'neck_01', 'spine_03', 'spine_02']}
    rest_pts = [rest[b][:3, 3] for b in CABLE] + [np.array(bones[CABLE[-1]].tail_local)]
    seg = [float(np.linalg.norm(rest_pts[i + 1] - rest_pts[i])) for i in range(4)]
    head_inv = np.linalg.inv(rest['head'])
    loc = [head_inv @ np.append(p, 1.0) for p in rest_pts]
    col_local = [(b, np.linalg.inv(rest[b]) @ np.append(np.array(c, float), 1.0), r) for (b, c, r) in COLLIDERS]
    frames = [0] if is_pose else list(range(0, n_frames + 1))
    sample = {}
    need = ['head', 'neck_01', 'spine_03', 'spine_02', 'cable_01']
    for f in frames:
        sc.frame_set(f)
        sample[f] = {b: np.array(rig.pose.bones[b].matrix) for b in need}

    def targets(f):
        return [(sample[f]['head'] @ l)[:3] for l in loc]

    def step(p, prev, f):
        tg = targets(f)
        cols = [((sample[f][b] @ c)[:3], r) for (b, c, r) in col_local]
        dt = 1.0 / (fps * SUBSTEPS)
        for _ in range(SUBSTEPS):
            p[0] = tg[0]
            for i in range(1, 5):
                v = (p[i] - prev[i]) * DAMP
                prev[i] = p[i].copy()
                p[i] = p[i] + v + np.array([0.0, 0.0, -GRAVITY * dt * dt])
                p[i] = p[i] + (tg[i] - p[i]) * STIFF[i]
            for _ in range(4):
                for i in range(1, 5):
                    d = p[i] - p[i - 1]
                    ln = np.linalg.norm(d)
                    if ln > 1e-9:
                        p[i] = p[i - 1] + d * (seg[i - 1] / ln)
                    for (cc, r) in cols:
                        dc = p[i] - cc
                        l2 = np.linalg.norm(dc)
                        if l2 < r + 0.008 and l2 > 1e-9:
                            p[i] = cc + dc * ((r + 0.008) / l2)
                    if p[i][2] < 0.012:
                        p[i][2] = 0.012
        return p, prev

    p = [t.copy() for t in targets(frames[0])]
    prev = [t.copy() for t in p]
    for _ in range(24):                                   # settle on the first pose
        prev = [q.copy() for q in p]
        p, prev = step(p, prev, frames[0])
    out = {}
    if is_pose:
        out[0] = [q.copy() for q in p]
    elif loop:
        for cyc in range(3):                              # run the cycle until the motion is periodic
            for f in frames[:-1]:
                p, prev = step(p, prev, f)
                if cyc == 2:
                    out[f] = [q.copy() for q in p]
        out[frames[-1]] = [q.copy() for q in out[frames[0]]]
    else:
        out[frames[0]] = [q.copy() for q in p]
        for f in frames[1:]:
            p, prev = step(p, prev, f)
            out[f] = [q.copy() for q in p]
    # ---- joint positions -> control rotations
    quats = {b: np.zeros((len(frames), 4)) for b in CABLE}
    for fi, f in enumerate(frames):
        P = out[f]
        M0 = sample[f]['cable_01'].copy()                 # cable_01 with an identity basis (its curves were removed)
        Mprev_new = None
        for i, b in enumerate(CABLE):
            if i > 0:
                M0 = Mprev_new @ np.linalg.inv(rest[CABLE[i - 1]]) @ rest[b]
            R0 = M0[:3, :3]
            R0 = R0 / np.linalg.norm(R0, axis=0, keepdims=True)
            d = P[i + 1] - P[i]
            d = d / max(np.linalg.norm(d), 1e-9)
            Rq = _shortest_arc(R0[:, 1], d)
            basis = R0.T @ Rq @ R0
            quats[b][fi] = m_to_q(basis)
            Mn = np.eye(4)
            Mn[:3, :3] = Rq @ R0
            Mn[:3, 3] = M0[:3, 3]
            Mprev_new = Mn
    kf = [0, 1] if is_pose else frames
    for b in CABLE:
        q = quats[b]
        if is_pose:
            q = np.vstack([q[0], q[0]])
        for i in range(1, len(q)):
            if np.dot(q[i], q[i - 1]) < 0:
                q[i] = -q[i]
        if loop and not is_pose:
            q[-1] = q[0]
        kfa = np.asarray(kf, dtype=np.float64)
        idx = animio.reduce_keys(kfa, q, 4.0e-4)
        for k in range(4):
            animio.set_curve(cb, animio.bone_path(b, 'rotation_quaternion'), k, kfa[idx], q[idx, k], b, interp='LINEAR', compress=False)
    rigmod.reset_pose(rig)
    return out


def copy_cable_end(rig, src_action, src_slot, src_frame, dst_action, dst_slot):
    """Key the cable controls of a pose action with the values the source action has at src_frame (held poses that
    must connect exactly to the end of a clip, e.g. dead_front after death_front)."""
    cb_src = animio.channelbag(src_action, src_slot)
    cb_dst = _strip_cable_curves(dst_action, dst_slot)
    for b in CABLE:
        path = animio.bone_path(b, 'rotation_quaternion')
        for k in range(4):
            fc = cb_src.fcurves.find(path, index=k)
            v = fc.evaluate(src_frame) if fc is not None else (1.0 if k == 0 else 0.0)
            animio.set_curve(cb_dst, path, k, [0.0, 1.0], [v, v], b, interp='LINEAR', compress=False)

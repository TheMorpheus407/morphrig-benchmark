"""Deterministic secondary motion for the hair tail (hair_tail_01..04), baked into each clip.

Verlet chain in world space, driven by the evaluated head bone of the control rig:
  * root particle rigidly attached to the head, 4 free particles (bone tails)
  * pull toward the head-relative rest shape (stiffness falls off along the chain), gravity,
    velocity damping, fixed segment lengths
  * collisions: floor plane and capsules for head, neck and upper back (so the tail rests on
    the collar/back and on the floor when lying down)
Loops are simulated for two warm-up cycles and the recorded cycle is cross-faded into its start
so the result stays seamless.  Output: per-frame local Euler XYZ rotations of the 4 rig bones,
applied as a procedural layer (they remain ordinary keys of the rig action and can be edited or
re-simulated by rebuilding the clip).
"""
import numpy as np
import bpy
from mathutils import Matrix, Vector

BONES = ["hair_tail_01", "hair_tail_02", "hair_tail_03", "hair_tail_04"]
STIFF = [0.55, 0.30, 0.18, 0.11]         # pull toward the rest shape per particle (per substep)
DAMP = 0.10
GRAV = 9.81
RADIUS = [0.016, 0.013, 0.010, 0.007]
SUB = 4


def _capsules(pbs):
    """(a, b, r) world capsules approximating head, neck and upper back/collar."""
    def head(n):
        return np.array(pbs[n].head)

    def tail(n):
        return np.array(pbs[n].tail)
    H0, H1 = head("head"), tail("head")
    caps = [(H0 + (H1 - H0) * 0.25, H0 + (H1 - H0) * 0.55, 0.088),     # skull
            (head("neck_01"), head("head"), 0.066),                   # neck + collar
            (head("spine_03") + (tail("spine_03") - head("spine_03")) * 0.2, tail("spine_03"), 0.125)]
    return caps


def _push_out(p, r, caps):
    for a, b, cr in caps:
        ab = b - a
        t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0.0, 1.0)
        q = a + ab * t
        d = p - q
        dist = np.linalg.norm(d)
        lim = cr + r
        if dist < lim:
            n = d / dist if dist > 1e-9 else np.array([0, 1.0, 0])
            p = q + n * lim
    if p[2] < RADIUS[-1]:
        p = p.copy()
        p[2] = RADIUS[-1]
    return p


def simulate_tail(rig, nframes, loop=False):
    sc = bpy.context.scene
    pbs = rig.pose.bones
    rest = {b.name: np.array(b.matrix_local) for b in rig.data.bones}
    chain_rest = [rest[b][:3, 3] for b in BONES] + [np.array(rig.data.bones[BONES[-1]].tail_local)]
    head_rest = rest["head"]
    local_pts = [np.linalg.inv(head_rest) @ np.append(p, 1.0) for p in chain_rest]
    seg = [np.linalg.norm(chain_rest[k + 1] - chain_rest[k]) for k in range(4)]
    # sample the driving head matrices and collision capsules once per frame
    Hs, Cs = [], []
    for f in range(nframes + 1):
        sc.frame_set(f)
        Hs.append(np.array(pbs["head"].matrix))
        Cs.append(_capsules(pbs))
    n_cycles = max(3, int(np.ceil(90.0 / max(nframes, 1)))) if loop else 1
    period = nframes if loop else nframes + 1
    dt = 1.0 / (30.0 * SUB)
    x = [(Hs[0] @ lp)[:3] for lp in local_pts]
    xp = [p.copy() for p in x]
    rec = []
    for cyc in range(n_cycles):
        for f in range(period):
            if cyc == n_cycles - 1:
                rec.append([p.copy() for p in x])          # state at frame f
            f1 = f + 1 if loop else min(f + 1, nframes)
            for s in range(SUB):
                a = (s + 1) / SUB
                Hm = Hs[f] * (1 - a) + Hs[f1] * a
                tgt = [(Hm @ lp)[:3] for lp in local_pts]
                caps = Cs[f] if a < 0.5 else Cs[f1]
                nx = [tgt[0]]
                for k in range(1, 5):
                    vel = (x[k] - xp[k]) * (1.0 - DAMP)
                    p = x[k] + vel + np.array([0, 0, -GRAV]) * dt * dt
                    p = p + (tgt[k] - p) * STIFF[k - 1]
                    nx.append(p)
                for _ in range(3):
                    for k in range(1, 5):
                        d = nx[k] - nx[k - 1]
                        L = np.linalg.norm(d)
                        if L > 1e-9:
                            nx[k] = nx[k - 1] + d / L * seg[k - 1]
                        nx[k] = _push_out(nx[k], RADIUS[k - 1], caps)
                xp = x
                x = nx
    if loop:
        rec.append([p.copy() for p in rec[0]])
        nb = min(8, nframes // 3)
        for i in range(nb):
            w = (i + 1) / (nb + 1)
            j = nframes - nb + i
            rec[j] = [pa * (1 - w) + pb * w for pa, pb in zip(rec[j], rec[0])]
    return _to_local(rig, rest, Hs, rec)


def _rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.9999:
        ax = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(ax) < 1e-6:
            ax = np.cross(a, [0, 1.0, 0])
        ax /= np.linalg.norm(ax)
        return np.array(Matrix.Rotation(np.pi, 3, Vector(ax)))
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1.0 / (1.0 + c))


def _to_local(rig, rest, Hs, rec):
    """World particle positions -> local Euler rotations of the 4 chain bones per frame."""
    parent = {b.name: (b.parent.name if b.parent else None) for b in rig.data.bones}
    out = {b: np.zeros((len(rec), 3)) for b in BONES}
    for f, pts in enumerate(rec):
        Hm = Hs[min(f, len(Hs) - 1)]
        par_world = Hm.copy()
        for k, bn in enumerate(BONES):
            pr = parent[bn]
            rest_local = np.linalg.inv(rest[pr]) @ rest[bn]
            W0 = par_world @ rest_local                    # bone world matrix with identity basis
            d_rest = W0[:3, 1]
            d_sim = pts[k + 1] - pts[k]
            Rw = _rot_between(d_rest, d_sim)
            W = W0.copy()
            W[:3, :3] = Rw @ W0[:3, :3]
            basis = np.linalg.inv(W0) @ W
            eul = Matrix([list(basis[0][:3]), list(basis[1][:3]), list(basis[2][:3])]).to_euler('XYZ')
            out[bn][f] = (eul.x, eul.y, eul.z)
            par_world = W
    return out


def tail_layer(sim):
    def layer(frames, S):
        n = len(frames)
        for bn, vals in sim.items():
            S[f"{bn}.rot"][:, :] = vals[:n]
    return layer

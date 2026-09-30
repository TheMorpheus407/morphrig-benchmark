"""Procedural skinning for the Operative (numpy). Weights come from chain 'hat functions' (twist and half-angle bones
included), spatial mask fields smoothed over the mesh (shoulder/hip blending) and nearest-vertex transfer for accessories.
W matrices are dense (n_verts x n_bones) in skeleton_def.BONES order; finalize() prunes to max influences and normalises."""
import numpy as np
import skeleton_def as S
import mr_geo as G

A = np.array
BONE_INDEX = {b.name: i for i, b in enumerate(S.BONES)}
NB = len(S.BONES)


def sm(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def project_polyline(P, poly):
    """Arc-length parameter s and distance of each point to the polyline (list of 3D points)."""
    poly = [A(p, float) for p in poly]
    seg_len = [np.linalg.norm(poly[i + 1] - poly[i]) for i in range(len(poly) - 1)]
    cum = np.concatenate([[0], np.cumsum(seg_len)])
    best_d = np.full(len(P), 1e9)
    best_s = np.zeros(len(P))
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)
        m = d < best_d
        best_d[m] = d[m]
        best_s[m] = cum[i] + t[m] * seg_len[i]
    # allow extension beyond the ends (signed) so anchors before 0 work
    a, b = poly[0], poly[1]
    ab = (b - a) / np.linalg.norm(b - a)
    t0 = (P - a) @ ab
    m = t0 < 0
    best_s[m & (best_d < 1e8)] = np.where(t0 < 0, t0, best_s)[m & (best_d < 1e8)]
    return best_s, best_d


def hat(s, anchors):
    """anchors: list of (bone_name, s_pos) ascending in s_pos. Returns (n, NB) weights with smoothstep blending."""
    W = np.zeros((len(s), NB))
    pos = A([p for _, p in anchors])
    idx = [BONE_INDEX[b] for b, _ in anchors]
    sc = np.clip(s, pos[0], pos[-1])
    k = np.clip(np.searchsorted(pos, sc, side='right') - 1, 0, len(pos) - 2)
    t = sm((sc - pos[k]) / np.maximum(pos[k + 1] - pos[k], 1e-9))
    rows = np.arange(len(s))
    np.add.at(W, (rows, [idx[i] for i in k]), 1 - t)
    np.add.at(W, (rows, [idx[i + 1] for i in k]), t)
    return W


def normalize(W):
    s = W.sum(axis=1, keepdims=True)
    s[s < 1e-9] = 1.0
    return W / s


def smooth_weights(W, adj, iters=3, lam=0.5, pinned=None):
    W = W.copy()
    for _ in range(iters):
        N = W.copy()
        for i, nb in enumerate(adj):
            if nb and (pinned is None or not pinned[i]):
                N[i] = (1 - lam) * W[i] + lam * W[nb].mean(axis=0)
        W = N
    return W


def prune(W, max_inf=6, min_w=0.008):
    W = W.copy()
    order = np.argsort(-W, axis=1)
    keep = np.zeros_like(W, dtype=bool)
    rows = np.arange(len(W))[:, None]
    keep[rows, order[:, :max_inf]] = True
    W[~keep] = 0
    W[W < min_w] = 0
    return normalize(W)


def rigid(n, bone):
    W = np.zeros((n, NB))
    W[:, BONE_INDEX[bone]] = 1.0
    return W


def transfer(P, src_P, src_W, k=4):
    """Weights for P from the k nearest source vertices (inverse distance)."""
    out = np.zeros((len(P), src_W.shape[1]))
    for i0 in range(0, len(P), 2048):
        chunk = P[i0:i0 + 2048]
        d = np.linalg.norm(chunk[:, None, :] - src_P[None, :, :], axis=2)
        nn = np.argsort(d, axis=1)[:, :k]
        dd = np.take_along_axis(d, nn, axis=1)
        w = 1.0 / (dd + 1e-4)
        w /= w.sum(axis=1, keepdims=True)
        for j in range(k):
            out[i0:i0 + 2048] += w[:, j:j + 1] * src_W[nn[:, j]]
    return out


# ----------------------------------------------------------------------------- chains

def _m(p, sy):
    return (p[0], sy * p[1], p[2])


def arm_anchors(sfx):
    return [('spine_03', -0.19), (f'clavicle_{sfx}', -0.085), (f'shoulder_half_{sfx}', -0.005), (f'upperarm_{sfx}', 0.055),
            (f'upperarm_twist_01_{sfx}', 0.125), (f'upperarm_twist_02_{sfx}', 0.235), (f'elbow_half_{sfx}', 0.330),
            (f'lowerarm_{sfx}', 0.385), (f'lowerarm_twist_01_{sfx}', 0.440), (f'lowerarm_twist_02_{sfx}', 0.520),
            (f'wrist_half_{sfx}', 0.595), (f'hand_{sfx}', 0.660)]


def leg_anchors(sfx):
    return [('pelvis', -0.14), (f'hip_half_{sfx}', 0.0), (f'thigh_{sfx}', 0.075), (f'thigh_twist_01_{sfx}', 0.145),
            (f'thigh_twist_02_{sfx}', 0.290), (f'knee_half_{sfx}', 0.430), (f'calf_{sfx}', 0.490),
            (f'calf_twist_01_{sfx}', 0.560), (f'calf_twist_02_{sfx}', 0.700), (f'foot_{sfx}', 0.860)]


TRUNK_ANCHORS = [('pelvis', 0.90), ('pelvis', 0.985), ('spine_01', 1.060), ('spine_02', 1.185), ('spine_03', 1.320),
                 ('spine_03', 1.430), ('neck_01', 1.500), ('neck_02', 1.555), ('head', 1.610)]


def arm_poly(sy):
    return [_m(S.SHOULDER, sy), _m(S.ELBOW, sy), _m(S.WRIST, sy), _m(S.add(S.WRIST, S.mul(S.HAND_DIR, 0.09)), sy)]


def leg_poly(sy):
    return [_m(S.HIP, sy), _m(S.KNEE, sy), _m(S.ANKLE, sy), _m(S.BALL, sy)]


def body_weights(P, faces, labels, kinds):
    """Weights for the Skin-modifier body base. labels/kinds from body_base.part_labels."""
    adj = G.adjacency(len(P), faces)
    lab = {k: (labels == i).astype(float) for i, k in enumerate(kinds)}
    # soft masks: smooth the hard labels over the mesh
    masks = {}
    for k in ('trunk', 'neck', 'arm_l', 'arm_r', 'leg_l', 'leg_r'):
        m = lab.get(k, np.zeros(len(P)))
        for _ in range(7):
            nm = m.copy()
            for i, nb in enumerate(adj):
                nm[i] = 0.4 * m[i] + 0.6 * np.mean(m[nb])
            m = nm
        masks[k] = m
    masks['trunk'] = masks['trunk'] + masks['neck']
    tot = sum(masks.values())
    tot[tot < 1e-9] = 1
    W_trunk = hat(P[:, 2], TRUNK_ANCHORS)
    W = np.zeros((len(P), NB))
    W += masks['trunk'][:, None] / tot[:, None] * W_trunk
    for sfx, sy in (('l', 1.0), ('r', -1.0)):
        s, d = project_polyline(P, arm_poly(sy))
        Wa = hat(s, arm_anchors(sfx))
        W += masks[f'arm_{sfx}'][:, None] / tot[:, None] * Wa
        s, d = project_polyline(P, leg_poly(sy))
        Wl = hat(s, leg_anchors(sfx))
        # the region above the hip is pelvis; keep the crotch centre on the pelvis
        W += masks[f'leg_{sfx}'][:, None] / tot[:, None] * Wl
    W = normalize(W)
    W = smooth_weights(W, adj, iters=4, lam=0.5)
    return W


def hand_weights(P, faces, sfx, sy):
    """Organic hand: per-finger chains blended with the palm."""
    adj = G.adjacency(len(P), faces)
    hand_head = A(_m(S.BONE_BY_NAME['hand_l'].head, sy))
    palm_c = A(_m(S.add(S.WRIST, S.mul(S.HAND_DIR, 0.055)), sy))
    W = np.zeros((len(P), NB))
    W[:, BONE_INDEX[f'hand_{sfx}']] = 1.0
    best = np.full(len(P), 1e9)
    chains = []
    for fname in ('index', 'middle', 'ring', 'pinky'):
        chains.append((fname, [f'{fname}_metacarpal_{sfx}', f'{fname}_01_{sfx}', f'{fname}_02_{sfx}', f'{fname}_03_{sfx}']))
    chains.append(('thumb', [f'thumb_01_{sfx}', f'thumb_02_{sfx}', f'thumb_03_{sfx}']))
    Wf = np.zeros_like(W)
    dmin = np.full(len(P), 1e9)
    for fname, bones in chains:
        pts = [A(_m(S.BONE_BY_NAME[bones[0].replace(f'_{sfx}', '_l')].head, sy))]
        for b in bones:
            pts.append(A(_m(S.BONE_BY_NAME[b.replace(f'_{sfx}', '_l')].tail, sy)))
        s, d = project_polyline(P, pts)
        joints = [0.0]
        for i in range(1, len(pts)):
            joints.append(joints[-1] + np.linalg.norm(pts[i] - pts[i - 1]))
        anchors = []
        for i, b in enumerate(bones):
            mid = (joints[i] + joints[i + 1]) / 2
            anchors.append((b, mid))
        Wc = hat(s, anchors)
        m = d < dmin
        Wf[m] = Wc[m]
        dmin[m] = d[m]
    # finger influence grows with distance from the palm centre along the finger
    dpalm = np.linalg.norm(P - palm_c, axis=1)
    g = sm((dpalm - 0.035) / 0.03)
    # thumb region: the thumb metacarpal also pulls the palm edge
    W = W * (1 - g[:, None]) + Wf * g[:, None]
    W = normalize(W)
    return smooth_weights(W, adj, iters=2, lam=0.4)


def head_weights(P, faces, info=None):
    """Head mesh: head bone, jaw for the lower face, eyelid bones around the eye rims, neck peg down the neck."""
    adj = G.adjacency(len(P), faces)
    W = np.zeros((len(P), NB))
    ib = BONE_INDEX
    z = P[:, 2]
    # neck peg vs head: by height along the neck
    Wn = hat(z, [('neck_01', 1.500), ('neck_02', 1.555), ('head', 1.610)])
    W += Wn
    # jaw: lower face in front of the jaw pivot, below the mouth line (soft), plus chin
    jaw_pivot = A([-0.020, 0.0, 1.635])
    front = sm((P[:, 0] - (-0.015)) / 0.05)
    below = sm((1.6235 - z) / 0.012) * sm((z - 1.548) / 0.012)      # only the lower face, not the neck peg
    # gradient: below the line vertices move fully with the jaw; near the slit gate by the chain (upper/lower lip)
    wj = below * front * sm((0.095 - np.abs(P[:, 1])) / 0.02 + 0.5)
    # cheeks follow the jaw a little
    wj = np.maximum(wj, 0.0)
    W[:, ib['jaw']] = wj
    W[:, ib['head']] = np.maximum(W[:, ib['head']] - wj, 0.0) + (1 - W.sum(axis=1)).clip(0, 1) * 0
    W = normalize(W)
    W = smooth_weights(W, adj, iters=2, lam=0.5)
    if info is not None:
        # eyelids: rim, ring1, ring2 follow the lid bones (upper/lower by height, corners half/half), fading outward
        for nm, sfx in (('eye_l', 'l'), ('eye_r', 'r')):
            ec = info[nm + '_centre']
            rings = info[nm]
            fades = (1.0, 0.70, 0.30, 0.10)
            for k, ring in enumerate(rings[:4]):
                fade = fades[k]
                for vi in ring:
                    dz = P[vi][2] - ec[2]
                    up = sm((dz + 0.0016) / 0.0032)
                    W[vi, :] = W[vi, :] * (1 - fade)
                    W[vi, ib[f'lid_up_{sfx}']] += fade * up
                    W[vi, ib[f'lid_lo_{sfx}']] += fade * (1 - up)
        # mouth: upper lip/upper cavity -> head, lower lip/lower cavity -> jaw, corners half
        mouth = info.get('mouth')
        slit = info.get('mouth_slit')
        if mouth is not None:
            for ru, rl in mouth['rings']:
                for vi in rl:
                    W[vi, :] = 0
                    W[vi, ib['jaw']] = 1.0
                for vi in ru:
                    W[vi, :] = 0
                    W[vi, ib['head']] = 1.0
            # corners share both
            ru0, rl0 = mouth['rings'][0]
            for vi in (ru0[0], ru0[-1]):
                W[vi, :] = 0
                W[vi, ib['head']] = 0.5
                W[vi, ib['jaw']] = 0.5
            for ru, rl in mouth['rings'][1:]:
                for vi in (ru[0], ru[-1]):
                    W[vi, :] = 0
                    W[vi, ib['head']] = 0.5
                    W[vi, ib['jaw']] = 0.5
    return normalize(W)


def boot_weights(P, sfx):
    """Boot: calf above the ankle, foot below, toe bone bending at the ball. z above 0.16 -> calf."""
    sy = 1.0 if sfx == 'l' else -1.0
    W = np.zeros((len(P), NB))
    z = P[:, 2]
    x = P[:, 0]
    a_calf = sm((z - 0.105) / 0.085)
    ball = sm((x - 0.128) / 0.050) * (1 - sm((z - 0.09) / 0.03))
    W[:, BONE_INDEX[f'calf_{sfx}']] = a_calf * (1 - ball)
    W[:, BONE_INDEX[f'foot_{sfx}']] = (1 - a_calf) * (1 - ball)
    W[:, BONE_INDEX[f'ball_{sfx}']] = ball * (1 - a_calf)
    # residual for a_calf*ball overlap goes to calf
    W[:, BONE_INDEX[f'calf_{sfx}']] += a_calf * ball
    return normalize(W)


def chain_hat_weights(P, anchors_bones, polyline):
    s, d = project_polyline(P, polyline)
    joints = [0.0]
    for i in range(1, len(polyline)):
        joints.append(joints[-1] + np.linalg.norm(A(polyline[i]) - A(polyline[i - 1])))
    anchors = []
    for i, b in enumerate(anchors_bones):
        anchors.append((b, joints[i]))
    return hat(s, anchors)

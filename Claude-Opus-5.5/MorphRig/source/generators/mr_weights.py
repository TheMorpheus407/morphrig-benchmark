"""MorphRig procedural skin weights.

Limbs use chain weights (position along the bone chain with smooth blends of a
given half-width around each joint), junctions are smoothed on the mesh graph,
twist bones take a growing share toward the distal joint, the face uses
anatomical fields (jaw, lids) and gear is rigid or transferred from the suit.
Result: dict bone -> float array (len nv), max 4 influences per vertex.
"""
import numpy as np
from mr_sdf import normalize, length


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def closest_on_segment(P, a, b):
    ab = b - a
    L2 = max(float(ab @ ab), 1e-12)
    t = ((P - a) @ ab) / L2
    tc = np.clip(t, 0, 1)
    q = a + tc[:, None] * ab
    return t, tc, length(P - q)


def chain_weights(P, chain, blends, bias=None):
    """chain: list of (name, head, tail); blends: half widths at internal joints (len-1).

    Returns dict name -> weights. Points are assigned by their nearest segment and a
    1-D chain coordinate s; joint j between bone j and j+1 blends over [S_j-b, S_j+b].
    """
    n = len(P)
    lens = [np.linalg.norm(t - h) for _, h, t in chain]
    S = np.concatenate([[0], np.cumsum(lens)])
    dists = []
    params = []
    for (nm, h, t) in chain:
        tr, tc, d = closest_on_segment(P, h, t)
        dists.append(d)
        params.append(tr)
    dists = np.array(dists)
    if bias is not None:
        dists = dists + np.asarray(bias)[:, None]
    k = np.argmin(dists, axis=0)
    tr = np.array(params)[k, np.arange(n)]
    tr_c = np.clip(tr, 0 if True else None, 1)
    s = S[k] + np.clip(tr, 0.0, 1.0) * np.array(lens)[k]
    # first/last bone extrapolate
    s = np.where((k == 0) & (tr < 0), 0.0, s)
    W = np.zeros((len(chain), n))
    # piecewise: start fully in bone assignment by s
    for j in range(len(chain)):
        lo = S[j]
        hi = S[j + 1]
        W[j] = ((s >= lo) & (s < hi)).astype(float)
    W[-1] += (s >= S[-1]).astype(float)
    # joint blends
    for j in range(len(chain) - 1):
        b = blends[j]
        if b <= 0:
            continue
        Sj = S[j + 1]
        near = np.abs(s - Sj) < b
        f = smoothstep((s - (Sj - b)) / (2 * b))
        W[j] = np.where(near, 1 - f, W[j])
        W[j + 1] = np.where(near, f, W[j + 1])
        for i in range(len(chain)):
            if i not in (j, j + 1):
                W[i] = np.where(near, 0.0, W[i])
    out = {}
    for j, (nm, h, t) in enumerate(chain):
        out[nm] = out.get(nm, 0) + W[j]
    return out, s, S


def add_into(total, part, mask=None, scale=1.0):
    for nm, w in part.items():
        if mask is not None:
            w = np.where(mask, w, 0.0)
        total[nm] = total.get(nm, 0) + w * scale
    return total


def normalize_weights(W, n, max_inf=4, prune=0.01):
    names = list(W.keys())
    M = np.stack([np.asarray(W[k], float) * np.ones(n) for k in names])  # (b, n)
    M[M < 0] = 0
    # keep top max_inf
    if len(names) > max_inf:
        idx = np.argsort(-M, axis=0)
        keep = np.zeros_like(M, bool)
        for r in range(max_inf):
            keep[idx[r], np.arange(n)] = True
        M = np.where(keep, M, 0.0)
    M[M < prune] = 0.0
    s = M.sum(0)
    s[s == 0] = 1
    M = M / s
    return {nm: M[i] for i, nm in enumerate(names) if M[i].max() > 0}


def smooth_weights(W, edges, n, iters=10, lam=0.5, mask=None, locked=None):
    """Laplacian smoothing of weight vectors along mesh edges (optionally masked)."""
    names = list(W.keys())
    M = np.stack([np.asarray(W[k], float) * np.ones(n) for k in names])
    cnt = np.zeros(n)
    np.add.at(cnt, edges[:, 0], 1)
    np.add.at(cnt, edges[:, 1], 1)
    cnt = np.maximum(cnt, 1)
    free = np.ones(n, bool) if mask is None else mask.copy()
    if locked is not None:
        free &= ~locked
    for _ in range(iters):
        acc = np.zeros_like(M)
        np.add.at(acc.T, edges[:, 0], M[:, edges[:, 1]].T)
        np.add.at(acc.T, edges[:, 1], M[:, edges[:, 0]].T)
        avg = acc / cnt
        M[:, free] = (1 - lam) * M[:, free] + lam * avg[:, free]
    return {nm: M[i] for i, nm in enumerate(names)}


def split_twist(W, parent, twist, P, head, tail, t0=0.15, t1=0.95, share=0.85, reverse=False):
    """Move a share of the parent's weight to its twist bone along the bone."""
    if parent not in W:
        return W
    t, tc, d = closest_on_segment(P, head, tail)
    f = smoothstep((tc - t0) / (t1 - t0)) * share
    if reverse:
        f = smoothstep((t1 - tc) / (t1 - t0)) * share
    moved = W[parent] * f
    W[parent] = W[parent] - moved
    W[twist] = W.get(twist, 0) + moved
    return W


def transfer_weights(P_dst, P_src, W_src, k=4):
    """Inverse-distance interpolation of weights from the k nearest source vertices."""
    names = list(W_src.keys())
    M = np.stack([W_src[nm] for nm in names], 1)  # (ns, b)
    out = np.zeros((len(P_dst), len(names)))
    chunk = 1024
    for s in range(0, len(P_dst), chunk):
        d = ((P_dst[s:s + chunk, None, :] - P_src[None, :, :]) ** 2).sum(-1)
        idx = np.argpartition(d, k, axis=1)[:, :k]
        dd = np.take_along_axis(d, idx, 1)
        w = 1.0 / (np.sqrt(dd) + 1e-4) ** 2
        w /= w.sum(1, keepdims=True)
        out[s:s + chunk] = np.einsum("nk,nkb->nb", w, M[idx])
    return {nm: out[:, i] for i, nm in enumerate(names)}

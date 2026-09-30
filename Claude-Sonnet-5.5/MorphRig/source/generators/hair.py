"""Close-cropped hair cap grown from the head surface: the faces above a hairline are offset along the vertex normals into a shell,
the rim is closed with a skirt so the shell has thickness. Rigid to the head bone. Returns (verts, faces, info)."""
import numpy as np
import mr_geo as G


def hairline_z(x, y):
    """Height of the hairline (m) for a surface point of the head: high on the forehead, dropping over the temples and to the nape."""
    front = 1.741
    nape = 1.612
    t = np.clip((0.045 - x) / 0.140, 0.0, 1.0)            # 0 at the forehead .. 1 at the back of the head
    z = front + (nape - front) * (t ** 1.35)
    side = np.clip((np.abs(y) - 0.052) / 0.030, 0.0, 1.0)     # temples: hair comes down in front of the ears
    z = z - 0.048 * side * np.clip((x + 0.03) / 0.09, 0.0, 1.0)
    z = z - 0.020 * side * (1.0 - np.clip((x + 0.03) / 0.09, 0.0, 1.0))
    return z


def hair_cap(V, F, thickness=0.0075, rim_thickness=0.0028, rim_smooth=14):
    V = np.asarray(V, dtype=np.float64)
    n = G.normals(V, F)
    cent = np.array([V[list(f)].mean(axis=0) for f in F])
    sel = np.nonzero(cent[:, 2] > hairline_z(cent[:, 0], cent[:, 1]))[0]
    used = np.unique(np.array([v for fi in sel for v in F[fi]]))
    remap = {int(v): i for i, v in enumerate(used)}
    base = V[used]
    # thickness tapers to the rim: height above the hairline decides how far the shell stands off
    h = np.clip((base[:, 2] - hairline_z(base[:, 0], base[:, 1])) / 0.030, 0.0, 1.0)
    off = rim_thickness + (thickness - rim_thickness) * (h * h * (3 - 2 * h))
    top = base + n[used] * off[:, None]
    faces = [tuple(remap[int(v)] for v in F[fi]) for fi in sel]
    # rim of the selected patch (boundary edges); smooth the staircase left by the grid cells along the loop
    edge_count = {}
    directed = {}
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
            directed[key] = (a, b)
    nb = len(used)
    nbr = {}
    for key, c in edge_count.items():
        if c == 1:
            nbr.setdefault(key[0], []).append(key[1])
            nbr.setdefault(key[1], []).append(key[0])
    rim = [v for v, l in nbr.items() if len(l) == 2]
    for _ in range(rim_smooth):
        new = {}
        for v in rim:
            a, b = nbr[v]
            new[v] = 0.5 * base[v] + 0.25 * (base[a] + base[b])
        for v, p in new.items():
            base[v] = p
    h = np.clip((base[:, 2] - hairline_z(base[:, 0], base[:, 1])) / 0.030, 0.0, 1.0)
    off = rim_thickness + (thickness - rim_thickness) * (h * h * (3 - 2 * h))
    top = base + n[used] * off[:, None]
    verts = np.concatenate([top, base])
    out = list(faces)
    for key, c in edge_count.items():
        if c == 1:
            u, v = directed[key]
            out.append((v, u, u + nb, v + nb))
    # keep only the vertices a face uses (the inner copies away from the rim would be loose vertices)
    used = sorted({int(i) for f in out for i in f})
    remap = {old: new for new, old in enumerate(used)}
    verts = verts[used]
    out = [tuple(remap[int(i)] for i in f) for f in out]
    return verts, out, {'n_scalp_faces': int(len(sel)), 'n_verts': int(len(verts))}

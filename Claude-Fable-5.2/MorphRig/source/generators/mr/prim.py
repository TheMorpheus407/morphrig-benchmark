"""Hard-surface building blocks on top of MeshData (prisms, lathes, spheres, conforming armour plates)."""
import math
import numpy as np
from .util import V, norm, lerp, smoothstep, TAU, frame_from
from .meshkit import MeshData


def frame(origin, y_axis, z_hint=(0, 0, 1)):
    """4x4 frame with Y along y_axis."""
    m = np.eye(4)
    m[:3, :3] = frame_from(np.asarray(y_axis, float), np.asarray(z_hint, float))
    m[:3, 3] = origin
    return m


def xf(m, p):
    p = np.asarray(p, dtype=np.float64)
    return p @ m[:3, :3].T + m[:3, 3]


def chamfer_rect(hx, hz, c):
    """8-point chamfered rectangle in the local XZ plane (counter-clockwise seen from +Y)."""
    c = min(c, hx * 0.95, hz * 0.95)
    return [(hx, -hz + c), (hx, hz - c), (hx - c, hz), (-hx + c, hz), (-hx, hz - c), (-hx, -hz + c), (-hx + c, -hz), (hx - c, -hz)]


def ngon(r, n, rz=None, phase=0.0):
    rz = r if rz is None else rz
    return [(r * math.cos(phase + TAU * k / n), rz * math.sin(phase + TAU * k / n)) for k in range(n)]


def loft_sections(md, m, sections, w, mat, tag, cap_start=True, cap_end=True, flip=False, sharp_rings=False):
    """sections: list of (y, [(x, z), ...]) in the local frame m. All sections need the same point count."""
    rings = []
    for (y, sec) in sections:
        pts = xf(m, [(x, y, z) for (x, z) in sec])
        rings.append(md.ring(pts, w, tag=tag))
    for a, b in zip(rings[:-1], rings[1:]):
        md.strip(a, b, mat, tag, closed=True, flip=not flip)
    if cap_start:
        _cap(md, rings[0], w, mat, tag, flip=flip)
    if cap_end:
        _cap(md, rings[-1], w, mat, tag, flip=not flip)
    if sharp_rings:
        for r in (rings[0], rings[-1]):
            md.sharp.update(frozenset((r[i], r[(i + 1) % len(r)])) for i in range(len(r)))
    return rings


def _cap(md, ring, w, mat, tag, flip=False):
    n = len(ring)
    if n % 2 == 0 and n <= 12:
        md.grid_cap(ring, mat, tag, flip=flip)
    else:
        c = md.pos(ring).mean(axis=0)
        md.fan_cap(ring, c, w, mat, tag, flip=flip)


def box(md, m, hx, length, hz, w, mat, tag, chamfer=0.003, y0=0.0, taper=1.0, end_chamfer=None):
    """Chamfered box along local Y from y0 to y0+length; taper scales the far end section."""
    ec = chamfer if end_chamfer is None else end_chamfer
    ec = min(ec, 0.42 * length)                        # always leave a flat band between the two end chamfers
    e0 = min(ec, 0.6 * min(hx, hz))                    # the end caps must keep a positive size on both axes
    e1 = min(ec, 0.6 * min(hx, hz) * taper)
    s0 = chamfer_rect(hx - e0, hz - e0, chamfer)
    s1 = chamfer_rect(hx, hz, chamfer)
    s2 = chamfer_rect(hx * taper, hz * taper, chamfer * taper)
    s3 = chamfer_rect(hx * taper - e1, hz * taper - e1, chamfer * taper)
    secs = [(y0, s0), (y0 + e0, s1), (y0 + length - e1, s2), (y0 + length, s3)]
    return loft_sections(md, m, secs, w, mat, tag)


def lathe(md, m, profile, n, w, mat, tag, cap_start=True, cap_end=True, rz_scale=1.0, phase=0.0):
    """Surface of revolution around local Y. profile: [(radius, y), ...]."""
    secs = [(y, ngon(r, n, r * rz_scale, phase)) for (r, y) in profile]
    return loft_sections(md, m, secs, w, mat, tag, cap_start, cap_end)


def sphere(md, c, r, w, mat, tag, seg=12, rings=8, scale=(1, 1, 1)):
    rr = []
    c = np.asarray(c, float)
    for i in range(1, rings):
        th = math.pi * i / rings
        pts = [c + np.array([math.sin(th) * math.cos(TAU * j / seg) * scale[0], math.sin(th) * math.sin(TAU * j / seg) * scale[1],
                             math.cos(th) * scale[2]]) * r for j in range(seg)]
        rr.append(md.ring(pts, w, tag=tag))
    md.fan_cap(rr[0], c + np.array([0, 0, r * scale[2]]), w, mat, tag, flip=False)
    for a, b in zip(rr[:-1], rr[1:]):
        md.strip(a, b, mat, tag, closed=True, flip=True)
    md.fan_cap(rr[-1], c - np.array([0, 0, r * scale[2]]), w, mat, tag, flip=True)
    return rr


def plate(md, surf, nu, nv, w, mat, tag, thickness=0.006, gap=0.002, bevel=0.0025, sink=0.002, relief=None, flip=False,
          closed_u=False, weights_fn=None):
    """Armour plate conforming to a surface.

    surf(u, v) -> (point, normal) for u, v in [0, 1]; relief(u, v) adds extra offset (ridges, panels).
    Builds the outer skin, a bevelled rim and side walls that sink slightly into the underlying surface.
    """
    outer = np.zeros((nv + 1, nu + (0 if closed_u else 1), 3))
    base = np.zeros_like(outer)
    nrm = np.zeros_like(outer)
    ncol = outer.shape[1]
    for j in range(nv + 1):
        for i in range(ncol):
            u, v = i / float(nu), j / float(nv)
            p, n = surf(u, v)
            off = gap + thickness + (relief(u, v) if relief else 0.0)
            base[j, i] = p
            nrm[j, i] = n
            outer[j, i] = p + n * off

    def wt(p):
        return weights_fn(p) if weights_fn else w

    grid = [[md.vert(outer[j, i], wt(outer[j, i]), tag) for i in range(ncol)] for j in range(nv + 1)]
    for j in range(nv):
        md.strip(grid[j], grid[j + 1], mat, tag, closed=closed_u, flip=flip)
    # plate parameters as vertex attributes (texture generator: borders, panel lines, decals in plate space)
    rows_u = [outer[j] for j in (0, nv // 2, nv)]
    pw = float(np.mean([np.linalg.norm(np.diff(np.vstack([r, r[:1]]) if closed_u else r, axis=0), axis=1).sum() for r in rows_u]))
    ph = float(np.mean([np.linalg.norm(np.diff(outer[:, i], axis=0), axis=1).sum() for i in (0, ncol // 2, ncol - 1)]))
    md._plates = getattr(md, '_plates', 0) + 1
    pid = (md._plates * 0.7548776662) % 1.0

    def mark(vi, u, v, rim):
        for name, val in (('plate_u', u), ('plate_v', v), ('plate_w', pw), ('plate_h', ph), ('plate_rim', rim), ('plate_id', pid),
                          ('plate_closed', 1.0 if closed_u else 0.0)):
            md.vcol.setdefault(name, {})[vi] = float(val)
    for j in range(nv + 1):
        for i in range(ncol):
            mark(grid[j][i], i / float(nu), j / float(nv), 0.0)
    # boundary loops (ordered) -> bevel ring + wall ring
    loops = []
    if closed_u:
        loops.append(([(0, i) for i in range(ncol)], True, False))
        loops.append(([(nv, i) for i in range(ncol)], True, True))
    else:
        b = [(0, i) for i in range(ncol)] + [(j, ncol - 1) for j in range(1, nv + 1)] + \
            [(nv, i) for i in range(ncol - 2, -1, -1)] + [(j, 0) for j in range(nv - 1, 0, -1)]
        loops.append((b, True, False))
    for (lp, closed, rev) in loops:
        P = np.array([outer[j, i] for (j, i) in lp])
        B = np.array([base[j, i] for (j, i) in lp])
        N = np.array([nrm[j, i] for (j, i) in lp])
        # outward direction in the surface: away from the plate interior
        cen = P.mean(axis=0) if not closed_u else None
        nxt = np.roll(P, -1, axis=0)
        prv = np.roll(P, 1, axis=0)
        tang = nxt - prv
        out = np.cross(tang, N)
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
        if not closed_u:
            sign = np.sign(((P - cen) * out).sum(axis=1).mean())
            out *= (sign if sign != 0 else 1.0)
        else:
            # for closed bands decide by comparing with the direction towards the other edge
            other = np.array([outer[nv - j, i] for (j, i) in lp])
            sign = np.sign(((P - other) * out).sum(axis=1).mean())
            out *= (sign if sign != 0 else 1.0)
        ring0 = [grid[j][i] for (j, i) in lp]
        bev = md.ring(P + out * bevel - N * bevel, [md.w[k] for k in ring0], tag=tag)
        wall = md.ring(B + out * bevel - N * sink, [md.w[k] for k in ring0], tag=tag)
        # winding: figure out from the first quad so that walls face outwards
        a0, a1 = np.array(md.v[ring0[0]]), np.array(md.v[ring0[1]])
        b0 = np.array(md.v[bev[0]])
        fn = np.cross(a1 - a0, b0 - a0)
        fl = bool(np.dot(fn, out[0] + N[0]) < 0)
        md.strip(ring0, bev, mat, tag, closed=True, flip=fl)
        md.strip(bev, wall, mat, tag, closed=True, flip=fl)
        for k, (j, i) in enumerate(lp):
            mark(bev[k], i / float(nu), j / float(nv), 0.6)
            mark(wall[k], i / float(nu), j / float(nv), 1.0)
    return grid

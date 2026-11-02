"""MorphRig facial features.

Adds to the head tube:
  * eyeballs with a domed iris / pupil, embedded in the orbital bowl
  * upper and lower eyelid shells that rotate on eyelid bones
    (the shells are concentric with the eyeball, so lids follow the gaze)
  * a carved mouth opening with an interior cavity (no holes through the head)
  * upper and lower teeth arcs
  * a tongue
  * brow strips
"""

import math
from mathutils import Vector

from mr_core import TAU, Tube, MeshBuilder

# UV atlas layout shared by every face element.  Each entry is
# (u0, v0, u1, v1) inside the single face texture.
#
# The head skin uses the whole u range and the v band up to SKIN_V_MAX.
# The band above it belongs to the sclera and the teeth, which are sampled
# by the eyeballs and the teeth arcs only.  Every other piece of face
# geometry has to stay below SKIN_V_MAX, otherwise it picks up the white
# of the sclera and shows as a pale streak across the face.
SKIN_V_MAX = 0.86

# The painted features (lips, brows, eye sockets) live in the skin band.
# The u of the head is scaled into it so the patches sit inside the atlas
# instead of straddling the wrap of the head.
SKIN_U_SCALE = 0.48

FACE_ATLAS = {
    "skin":   (0.00, 0.00, 0.48, 1.00),
    "sclera": (0.52, 0.88, 0.74, 1.00),
    "teeth":  (0.76, 0.88, 0.98, 1.00),
    # A plain patch of skin for the eyelid shells.  The shells are small
    # and they must not sample the whole skin band, they would drag the
    # painted lips and brows onto the eye.
    "lid":    (0.03, 0.87, 0.16, 1.00),
}

# The iris and the pupil live in the optic texture, they are the only two
# places that need a dark round shape on a bright field.
OPTIC_ATLAS = {
    "iris":  (0.03, 0.52, 0.25, 0.74),
    "pupil": (0.32, 0.52, 0.44, 0.64),
}


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

def sphere(center, radius, seg=20, rings=12, squash=1.0):
    """UV sphere as (verts, faces)."""
    verts = []
    faces = []
    verts.append(Vector((center[0], center[1], center[2] + radius * squash)))
    for i in range(1, rings):
        phi = math.pi * i / rings
        z = math.cos(phi) * radius * squash
        r = math.sin(phi) * radius
        for j in range(seg):
            th = TAU * j / seg
            verts.append(Vector((center[0] + r * math.cos(th),
                                 center[1] + r * math.sin(th),
                                 center[2] + z)))
    verts.append(Vector((center[0], center[1], center[2] - radius * squash)))
    bot = len(verts) - 1
    for j in range(seg):
        faces.append((0, 1 + (j + 1) % seg, 1 + j))
    for i in range(rings - 2):
        a = 1 + i * seg
        b = a + seg
        for j in range(seg):
            j1 = (j + 1) % seg
            faces.append((a + j, a + j1, b + j1, b + j))
    last = 1 + (rings - 2) * seg
    for j in range(seg):
        faces.append((bot, last + j, last + (j + 1) % seg))
    return verts, faces


def add_sphere(mb, center, radius, seg=20, rings=12, squash=1.0, mat=0,
               uv_scale=1.0, part=None, uv_rect=None):
    v, f = sphere(center, radius, seg, rings, squash)
    base = mb.add_verts(v, part)[0]
    for face in f:
        uvs = []
        for vi in face:
            p = mb.verts[base + vi]
            u = 0.5 + 0.5 * math.atan2(p.y - center[1], p.x - center[0]) / math.pi
            vv = 0.5 + 0.5 * math.asin(max(-1.0, min(1.0,
                            (p.z - center[2]) / (radius * squash)))) / (math.pi / 2)
            uvs.append((u * uv_scale, vv * uv_scale))
        if uv_rect is not None:
            u0, v0, u1, v1 = uv_rect
            uvs = [(u0 + u * (u1 - u0), v0 + vv * (v1 - v0)) for (u, vv) in uvs]
        mb.add_face([base + i for i in face], uvs, True, mat)
    return base


def _grid_surface(mb, grid, ref_point, mat, smooth=True, uv_rect=None):
    """Emit quads for a parametric grid, flipping winding to face `ref_point`."""
    rows = len(grid)
    cols = len(grid[0])
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = grid[r][c]
            b = grid[r][c + 1]
            d = grid[r + 1][c + 1]
            e = grid[r + 1][c]
            idx = [a, b, d, e]
            p0 = mb.verts[a]
            p1 = mb.verts[b]
            p2 = mb.verts[d]
            nrm = (p1 - p0).cross(p2 - p1)
            ref = (p0 - ref_point)
            if ref.length > 1e-9:
                ref.normalize()
            if nrm.dot(ref) < 0.0:
                idx = idx[::-1]
            u0 = c / float(cols - 1)
            u1 = (c + 1) / float(cols - 1)
            v0 = r / float(rows - 1)
            v1 = (r + 1) / float(rows - 1)
            uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            if uv_rect is not None:
                uv = [(uv_rect[0] + u * (uv_rect[2] - uv_rect[0]),
                       uv_rect[1] + v * (uv_rect[3] - uv_rect[1])) for (u, v) in uv]
            mb.add_quad(idx[0], idx[1], idx[2], idx[3], uv, smooth, mat)


def _stitch_border(mb, outer, inner, border, mat, smooth=True):
    for k in range(len(border)):
        r1, c1 = border[k]
        r2, c2 = border[(k + 1) % len(border)]
        a = outer[r1][c1]
        b = outer[r2][c2]
        c = inner[r2][c2]
        d = inner[r1][c1]
        mb.add_quad(a, b, c, d,
                    [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], smooth, mat)


def _border_loop(rows, cols):
    loop = []
    for c in range(cols):
        loop.append((0, c))
    for r in range(1, rows):
        loop.append((r, cols - 1))
    for c in range(cols - 2, -1, -1):
        loop.append((rows - 1, c))
    for r in range(rows - 2, 0, -1):
        loop.append((r, 0))
    return loop


# ---------------------------------------------------------------------------
# eyes
# ---------------------------------------------------------------------------

def add_eyeball(mb, side, center, radius=0.0125, mat_sclera=0, mat_iris=1,
                part=None, iris_part=None, pupil_part=None,
                sclera_uv=(0.52, 0.88, 0.74, 1.00),
                iris_uv=(0.03, 0.52, 0.25, 0.74),
                pupil_uv=(0.32, 0.52, 0.44, 0.64),
                iris_r=0.0042, pupil_r=0.0017):
    """Eyeball sphere plus a domed iris / pupil disc on its front.

    The sclera, the iris and the pupil carry three different UV rectangles,
    so all three can live in their own texture without bleeding into each
    other.  The iris and the pupil share the dark optic material and are
    told apart by their rectangle.
    """
    add_sphere(mb, center, radius, 24, 14, 1.0, mat_sclera, part=part,
               uv_rect=sclera_uv)
    c = Vector(center)
    fwd = Vector((0.0, -1.0, 0.0))
    seg = 20
    rings = 5
    iu0, iv0, iu1, iv1 = iris_uv
    pu0, pv0, pu1, pv1 = pupil_uv

    def iuv(u, v):
        return (iu0 + u * (iu1 - iu0), iv0 + v * (iv1 - iv0))

    def puv(u, v):
        return (pu0 + u * (pu1 - pu0), pv0 + v * (pv1 - pv0))

    # domed iris: concentric rings shrinking towards a raised pupil
    idx_c = mb.add_verts([c + fwd * (radius * 1.035)], iris_part)[0]
    ring_idx = []
    for k in range(rings, 0, -1):
        t = k / float(rings)
        rad = iris_r * t
        h = radius * (1.035 + 0.035 * (1.0 - t * t))
        row = []
        for j in range(seg):
            th = TAU * j / seg
            p = c + fwd * h + Vector((rad * math.cos(th), 0.0, rad * math.sin(th)))
            row.append(mb.add_verts([p], iris_part)[0])
        ring_idx.append(row)
    for j in range(seg):
        j1 = (j + 1) % seg
        mb.add_tri(idx_c, ring_idx[0][j], ring_idx[0][j1],
                   [iuv(0.5, 0.5),
                    iuv(0.5 + 0.45 * math.cos(TAU * j / seg),
                        0.5 + 0.45 * math.sin(TAU * j / seg)),
                    iuv(0.5 + 0.45 * math.cos(TAU * j1 / seg),
                        0.5 + 0.45 * math.sin(TAU * j1 / seg))], True, mat_iris)
    for k in range(rings - 1):
        a = ring_idx[k]
        b = ring_idx[k + 1]
        for j in range(seg):
            j1 = (j + 1) % seg
            mb.add_quad(a[j], a[j1], b[j1], b[j],
                        [iuv(j / float(seg), k / float(rings)),
                         iuv((j + 1) / float(seg), k / float(rings)),
                         iuv((j + 1) / float(seg), (k + 1) / float(rings)),
                         iuv(j / float(seg), (k + 1) / float(rings))], True, mat_iris)
    # pupil: separate geometry so it can use the black patch of the atlas
    ppart = pupil_part or iris_part
    pidx = mb.add_verts([c + fwd * (radius * 1.055)], ppart)[0]
    prow = []
    for j in range(seg):
        th = TAU * j / seg
        p = c + fwd * (radius * 1.052) + Vector((pupil_r * math.cos(th), 0.0,
                                                pupil_r * math.sin(th)))
        prow.append(mb.add_verts([p], ppart)[0])
    for j in range(seg):
        j1 = (j + 1) % seg
        mb.add_tri(pidx, prow[j], prow[j1],
                   [puv(0.5, 0.5),
                    puv(0.5 + 0.45 * math.cos(TAU * j / seg),
                        0.5 + 0.45 * math.sin(TAU * j / seg)),
                    puv(0.5 + 0.45 * math.cos(TAU * j1 / seg),
                        0.5 + 0.45 * math.sin(TAU * j1 / seg))], True, mat_iris)
    return center


def add_eyelids(mb, side, center, r_shell, mat=0, thickness=0.0008,
                upper=True, part=None, uv_rect=None):
    """Build an eyelid shell concentric with the eyeball.

    The shell is a spherical patch; rotating it about the eye centre sweeps
    the lid margin across the cornea, and because it is concentric it also
    follows the eye when the gaze moves.
    """
    c = Vector(center)
    fwd = Vector((0.0, -1.0, 0.0))
    up = Vector((0.0, 0.0, 1.0))
    sax = Vector((float(side), 0.0, 0.0))

    a_half = math.radians(102.0)
    if upper:
        e_top, e_bot = math.radians(86.0), math.radians(22.0)
    else:
        e_top, e_bot = math.radians(-18.0), math.radians(-78.0)

    na, ne = 17, 7
    dirs = []
    for i in range(ne):
        t = i / float(ne - 1)
        e = e_top + (e_bot - e_top) * t
        row = []
        for j in range(na):
            u = j / float(na - 1)
            a = -a_half + 2.0 * a_half * u
            d = (fwd * (math.cos(e) * math.cos(a)) +
                 sax * (math.cos(e) * math.sin(a)) +
                 up * math.sin(e))
            row.append(d.normalized())
        dirs.append(row)

    r_in = r_shell - thickness
    outer, inner = [], []
    for i in range(ne):
        ro, ri = [], []
        for j in range(na):
            ro.append(mb.add_verts([c + dirs[i][j] * r_shell], part)[0])
            ri.append(mb.add_verts([c + dirs[i][j] * r_in], part)[0])
        outer.append(ro)
        inner.append(ri)
    # outer faces point away from the eye centre, inner faces towards it
    _grid_surface(mb, outer, c, mat, uv_rect=uv_rect)
    _grid_surface(mb, inner, c, mat, uv_rect=uv_rect)
    _stitch_border(mb, outer, inner, _border_loop(ne, na), mat)
    return outer


# ---------------------------------------------------------------------------
# mouth
# ---------------------------------------------------------------------------

def add_mouth_cavity(mb, head, loop, depth=0.030, mat=2, part=None):
    """Interior shell behind the mouth opening so nothing shows through."""
    n = len(loop)
    c = Vector((0, 0, 0))
    for vi in loop:
        c += mb.verts[vi]
    c /= n
    back = c + Vector((0.0, depth, -0.005))
    t = Tube(mb, "mouth_cavity")
    t.add_ring_indices(loop, v=0.0, part=part)
    mid = []
    for vi in loop:
        p = mb.verts[vi]
        mid.append(p.lerp(back, 0.5))
    t.add_ring(mid, v=0.3, part=part)
    t.add_ring([back + (mb.verts[vi] - c) * 0.25 for vi in loop], v=0.6, part=part)
    t.bridge(0, 1, mat=mat)
    t.bridge(1, 2, mat=mat)
    t.cap(2, center=back, flip=True, mat=mat)
    return t


def add_teeth(mb, center, width=0.026, depth=0.020, mat=3, upper=True,
              part=None, uv_rect=None):
    """A simple arc of individual tooth boxes."""
    c = Vector(center)
    n = 8
    u0, v0, u1, v1 = uv_rect or (0.0, 0.0, 1.0, 1.0)
    for i in range(n):
        u = (i / (n - 1.0)) * 2.0 - 1.0
        x = c.x + u * width * 0.5
        sag = (1.0 - u * u) * 0.008
        y = c.y + sag
        w = width / n * 0.42
        h = depth * (0.55 + 0.45 * (1.0 - abs(u)))
        z0 = c.z
        z1 = c.z + (-h if upper else h)
        vs = []
        for (dx, dy, dz) in ((-w, -0.004, 0), (w, -0.004, 0), (w, 0.004, 0),
                              (-w, 0.004, 0), (-w, -0.004, -h if upper else h),
                              (w, -0.004, -h if upper else h),
                              (w, 0.004, -h if upper else h), (-w, 0.004, -h if upper else h)):
            vs.append(Vector((x + dx, y + dy, z0 + dz)))
        base = mb.add_verts(vs, part)[0]
        quads = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                 (2, 3, 7, 6), (3, 0, 4, 7)]
        for q in quads:
            mb.add_quad(base + q[0], base + q[1], base + q[2], base + q[3],
                        [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], False, mat)


def add_tongue(mb, center, mat=2, part=None):
    c = Vector(center)
    seg, rings = 12, 8
    verts = []
    for i in range(rings):
        t = i / (rings - 1.0)
        w = 0.016 * (1.0 - 0.45 * t)
        h = 0.006 * (1.0 - 0.55 * t)
        y = c.y + 0.022 * t
        z = c.z - 0.004 * t
        for j in range(seg):
            th = TAU * j / seg
            verts.append(Vector((c.x + w * math.cos(th), y,
                                 z + h * math.sin(th))))
    faces = []
    for i in range(rings - 1):
        a = i * seg
        b = a + seg
        for j in range(seg):
            j1 = (j + 1) % seg
            faces.append((a + j, a + j1, b + j1, b + j))
    base = mb.add_verts(verts, part)[0]
    for f in faces:
        mb.add_face([base + i for i in f],
                    [(0.5, 0.5)] * len(f), True, mat)


def add_brow_strip(mb, samples, mat=4, part=None, half=0.0050, out=0.0012):
    """A brow ridge strip that follows the sampled head surface.

    `samples` is a list of (surface point, outward normal, uv) triples.  The
    strip is vertical, it spans `half` up and down from the ridge and it
    stands `out` proud of the face.  A strip that follows the normal
    instead would be seen edge on and would collapse to a thin line.

    The uv is the one of the head under the strip, scaled into the skin band
    of the atlas, so the strip lands on the painted brow and never reaches
    the sclera region.
    """
    verts = []
    uvs = []
    up = Vector((0.0, 0.0, 1.0))
    for p, n, uv in samples:
        p = Vector(p)
        verts.append(p + up * half + n * out)
        verts.append(p - up * half + n * out)
        uvs.append(uv)
    base = mb.add_verts(verts, part)[0]
    n = len(samples)
    # the strip is thin, its two edges sit a little apart in the atlas
    dv = 0.014
    for i in range(n - 1):
        a = base + i * 2
        b = base + (i + 1) * 2
        u0, v0 = uvs[i]
        u1, v1 = uvs[i + 1]
        mb.add_quad(a, b, b + 1, a + 1,
                    [(u0, v0 - dv), (u1, v1 - dv), (u1, v1 + dv), (u0, v0 + dv)],
                    True, mat)


def add_brow(mb, center, width=0.040, thickness=0.005, arch=0.006, mat=4,
             side=1, part=None):
    """A thin curved strip used as an eyebrow."""
    c = Vector(center)
    seg = 9
    verts = []
    for i in range(seg):
        t = i / (seg - 1.0)
        x = c.x + side * (t - 0.5) * width
        y = c.y + arch * math.sin(math.pi * t) - 0.002 * t
        z = c.z + 0.004 * math.sin(math.pi * t * 0.9)
        verts.append(Vector((x, y, z + thickness * 0.5)))
        verts.append(Vector((x, y, z - thickness * 0.5)))
    base = mb.add_verts(verts, part)[0]
    for i in range(seg - 1):
        a = base + i * 2
        b = base + (i + 1) * 2
        mb.add_quad(a, b, b + 1, a + 1,
                    [(i / (seg - 1.0), 0), ((i + 1) / (seg - 1.0), 0),
                     ((i + 1) / (seg - 1.0), 1), (i / (seg - 1.0), 1)],
                    True, mat)

"""MorphRig core mesh library.

Procedural construction helpers used by every MorphRig generator:
  * MeshBuilder  - accumulates verts / faces / per-loop UVs / per-face flags
  * Tube         - a swept quad grid (rings x columns) with cell bookkeeping
  * carving      - removes a block of grid cells and returns the boundary loop
                   so a new limb branch can be stitched into the parent surface
  * frame maths  - parallel-transport frames along a centreline, ring profiles

All units are metres, Blender conventions (forward = -Y, up = +Z, right = +X).
"""

import math
from mathutils import Vector, Matrix, Quaternion

TAU = math.pi * 2.0

# distance from the wrist to the knuckles, shared by the mesh and the rig
KNUCKLE_DIST = 0.108


# ----------------------------------------------------------------------------
# small maths helpers
# ----------------------------------------------------------------------------

def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(t):
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(t):
    t = clamp(t)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def catmull_rom(points, samples):
    """Sample a Catmull-Rom spline through `points` (list of Vector)."""
    if len(points) < 2:
        return [Vector(p) for p in points]
    pts = [points[0] - (points[1] - points[0])] + list(points)
    pts.append(points[-1] + (points[-1] - points[-2]))
    out = []
    segs = len(points) - 1
    for s in range(samples):
        u = s / float(samples) * segs
        i = min(int(u), segs - 1)
        t = u - i
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        t2, t3 = t * t, t * t * t
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                          + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(Vector(points[-1]))
    return out


def parallel_transport_frames(centers, up_hint=Vector((0, 0, 1))):
    """Rotation-minimising frames along a polyline.

    Returns a list of (tangent, right, up) triples, right-handed with
    right x up == tangent.
    """
    n = len(centers)
    tangents = []
    for i in range(n):
        if i == 0:
            t = centers[1] - centers[0]
        elif i == n - 1:
            t = centers[-1] - centers[-2]
        else:
            t = centers[i + 1] - centers[i - 1]
        if t.length < 1e-9:
            t = Vector((0, 0, 1))
        tangents.append(t.normalized())

    ref = Vector(up_hint)
    if abs(ref.dot(tangents[0])) > 0.98:
        ref = Vector((0, 1, 0))
    right = ref.cross(tangents[0])
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()

    frames = []
    for i in range(n):
        t = tangents[i]
        if i > 0:
            axis = tangents[i - 1].cross(t)
            if axis.length > 1e-9:
                ang = math.atan2(axis.length, tangents[i - 1].dot(t))
                q = Quaternion(axis.normalized(), ang)
                right = q @ right
        right = (right - t * right.dot(t))
        if right.length < 1e-9:
            right = Vector((1, 0, 0))
        right.normalize()
        up = t.cross(right).normalized()
        frames.append((t, right, up))
    return frames


def resample_closed(points, count):
    """Resample a closed polygon to `count` points by arc length."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    seg = [(pts[(i + 1) % n] - pts[i]).length for i in range(n)]
    total = sum(seg)
    if total < 1e-12:
        return [Vector(p) for p in pts[:count]]
    out = []
    acc = 0.0
    for k in range(count):
        target = total * k / float(count)
        while acc + seg[k % n] < target and k < n * 4:
            acc += seg[k % n]
            k += 1
        local = (target - acc) / max(seg[k % n], 1e-12)
        a = pts[k % n]
        b = pts[(k + 1) % n]
        out.append(a.lerp(b, clamp(local)))
    return out


def split_ring_columns(points, extra, anchors=None):
    """Return a new closed ring with `extra` extra vertices inserted.

    Vertices are inserted on the longest edges (or on the edges listed in
    `anchors`, a list of column indices) so that the original corners are
    preserved exactly.
    """
    pts = [Vector(p) for p in points]
    n = len(pts)
    if extra <= 0:
        return pts
    if anchors:
        edge_count = {}
        for a in anchors:
            edge_count[a % n] = edge_count.get(a % n, 0) + 1
        chosen = []
        for e, c in edge_count.items():
            for _ in range(c):
                chosen.append(e)
        while len(chosen) < extra:
            # longest remaining edge
            best, blen = None, -1.0
            for i in range(n):
                if i in edge_count and edge_count[i] > 0:
                    continue
                L = (pts[(i + 1) % n] - pts[i]).length
                if L > blen:
                    blen, best = L, i
            if best is None:
                break
            edge_count[best] = 1
            chosen.append(best)
        chosen = chosen[:extra]
    else:
        order = sorted(range(n), key=lambda i: -(pts[(i + 1) % n] - pts[i]).length)
        chosen = order[:extra]
    counts = {}
    for e in chosen:
        counts[e] = counts.get(e, 0) + 1
    out = []
    for i in range(n):
        out.append(pts[i])
        k = counts.get(i, 0)
        if k:
            a, b = pts[i], pts[(i + 1) % n]
            for j in range(1, k + 1):
                out.append(a.lerp(b, j / float(k + 1)))
    return out


# ----------------------------------------------------------------------------
# mesh builder
# ----------------------------------------------------------------------------

class MeshBuilder:
    """Accumulates geometry with per-loop UVs and per-face attributes."""

    def __init__(self):
        self.verts = []
        self.faces = []
        self.loop_uvs = []
        self.face_smooth = []
        self.face_mat = []
        self.dead = set()      # indices into self.faces that were carved away
        self.part = []         # per-vertex ownership tag (skin binding)
        self.uv_rect = {}      # part -> (u0, v0, u1, v1) atlas placement

    def add_verts(self, pts, part="body"):
        base = len(self.verts)
        self.verts.extend(Vector(p) for p in pts)
        self.part.extend([part or "body"] * (len(self.verts) - base))
        return list(range(base, len(self.verts)))

    def mark(self, part, idxs):
        """Tag existing vertices as belonging to `part`."""
        for i in idxs:
            self.part[i] = part
        return idxs

    def part_indices(self, part):
        return [i for i, p in enumerate(self.part) if p == part]

    def add_face(self, idx, uv=None, smooth=True, mat=0):
        idx = list(idx)
        self.faces.append(tuple(idx))
        if uv is None:
            uv = [(0.0, 0.0)] * len(idx)
        self.loop_uvs.extend(tuple(x) for x in uv)
        self.face_smooth.append(bool(smooth))
        self.face_mat.append(mat)

    def add_quad(self, a, b, c, d, uv=None, smooth=True, mat=0):
        self.add_face([a, b, c, d], uv, smooth, mat)

    def add_tri(self, a, b, c, uv=None, smooth=True, mat=0):
        self.add_face([a, b, c], uv, smooth, mat)

    def merge(self, other, offset=Vector((0, 0, 0))):
        base = len(self.verts)
        self.verts.extend(Vector(v) + offset for v in other.verts)
        self.part.extend(other.part)
        for f, uvs, sm, mt in zip(other.faces, other.loop_uvs, other.face_smooth, other.face_mat):
            self.faces.append(tuple(i + base for i in f))
            self.loop_uvs.extend(uvs)
            self.face_smooth.append(sm)
            self.face_mat.append(mt)

    def to_object(self, name, collection=None):
        import bpy
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.verts], [], [list(f) for f in self.faces])
        me.update()
        uvl = me.uv_layers.new(name="UVMap")
        li = 0
        for pi, poly in enumerate(me.polygons):
            poly.use_smooth = self.face_smooth[pi]
            poly.material_index = self.face_mat[pi]
            rect = self.uv_rect.get(self.part[self.faces[pi][0]])
            for k in range(poly.loop_total):
                u, v = self.loop_uvs[li + k]
                if rect is not None:
                    u = rect[0] + u * (rect[2] - rect[0])
                    v = rect[1] + v * (rect[3] - rect[1])
                uvl.data[poly.loop_start + k].uv = (u, v)
            li += poly.loop_total
        obj = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(obj)
        return obj


# ----------------------------------------------------------------------------
# tube: swept quad grid
# ----------------------------------------------------------------------------

class Tube:
    """A grid of rings. Columns wrap (closed) unless `closed=False`.

    Each ring is a list of vertex indices; cells are addressed as (r, j)
    meaning the quad between ring r and r+1, column j and j+1.
    """

    def __init__(self, mb, name="tube", closed=True):
        self.mb = mb
        self.name = name
        self.closed = closed
        self.rings = []          # list[list[int]]
        self.ring_pts = []       # list[list[Vector]]
        self.ring_v = []         # v coordinate per ring
        self.cells = {}          # (r, j) -> face index
        self.u_seams = set()     # column indices where the u wrap happens

    # -- construction ------------------------------------------------------
    def add_ring(self, pts, v=0.0, part=None):
        idx = self.mb.add_verts(pts, part or "body")
        self.rings.append(idx)
        self.ring_pts.append([Vector(p) for p in pts])
        self.ring_v.append(v)
        return idx

    def add_ring_indices(self, idxs, v=0.0, part=None):
        """Adopt an existing vertex loop as a ring (keeps the mesh welded)."""
        idxs = list(idxs)
        if part:
            self.mb.mark(part, idxs)
        self.rings.append(idxs)
        self.ring_pts.append([Vector(self.mb.verts[i]) for i in idxs])
        self.ring_v.append(v)
        return idxs

    def split_bridge(self, r_a, b_idx, closed=True, mat=0, smooth=True, v_scale=1.0):
        """Bridge a ring of N columns onto a ring of 2N columns.

        Used where the column count doubles (neck 48 -> head 96).  Each
        source quad is split into a quad and a triangle so the surface stays
        watertight and free of T-junctions.  `v_scale` pulls the band down
        into the part of the atlas the material uses.
        """
        a = self.rings[r_a]
        n = len(a)
        assert len(b_idx) == 2 * n
        ua = self._u_with_seams(r_a)
        va = self.ring_v[r_a] * v_scale
        jmax = n if closed else n - 1
        for j in range(jmax):
            j1 = (j + 1) % n
            t0, t1 = a[j], a[j1]
            h0, hm, h2 = b_idx[2 * j], b_idx[2 * j + 1], b_idx[(2 * j + 2) % (2 * n)]
            u0 = ua[j]
            u1 = ua[j1] if j1 != 0 else 1.0
            um = 0.5 * (u0 + u1)
            # quad half
            self.mb.add_quad(t0, t1, h2, hm,
                             [(u0, va), (u1, va), (u1, va), (um, va)], smooth, mat)
            # triangle half
            self.mb.add_tri(t0, hm, h0,
                            [(u0, va), (um, va), (u0, va)], smooth, mat)

    @property
    def ncols(self):
        return len(self.rings[0]) if self.rings else 0

    def nrows(self):
        return len(self.rings)

    # -- uv ----------------------------------------------------------------
    def _u_values_raw(self, r):
        """Per-column u coordinates (0..1) measured by arc length."""
        pts = self.ring_pts[r]
        n = len(pts)
        seg = [(pts[(i + 1) % n] - pts[i]).length for i in range(n)]
        total = sum(seg)
        if total < 1e-12:
            return [0.0] * n
        acc = 0.0
        us = []
        for i in range(n):
            us.append(acc / total)
            acc += seg[i]
        return us

    def _u_with_seams(self, r):
        """u coordinates with island splits applied at the seam columns."""
        us = self._u_values_raw(r)
        n = len(us)
        if not self.u_seams:
            return us
        pts = self.ring_pts[r]
        seg = [(pts[(i + 1) % n] - pts[i]).length for i in range(n)]
        total = sum(seg)
        cum = [0.0]
        for s in seg:
            cum.append(cum[-1] + s)
        out = list(us)
        for j in sorted(self.u_seams):
            if j <= 0:
                continue
            denom = max(total - cum[j], 1e-12)
            for k in range(j, n):
                out[k] = (cum[k] - cum[j]) / denom
        return out

    # -- bridging ----------------------------------------------------------
    def bridge(self, r_a, r_b, flip=False, mat=0, smooth=True, u_scale=1.0, v_scale=1.0):
        """Create quads between ring r_a and ring r_b."""
        a = self.rings[r_a]
        b = self.rings[r_b]
        n = len(a)
        ua = self._u_with_seams(r_a)
        ub = self._u_with_seams(r_b)
        va = self.ring_v[r_a] * v_scale
        vb = self.ring_v[r_b] * v_scale
        jmax = n if self.closed else n - 1
        for j in range(jmax):
            j1 = (j + 1) % n
            idx = [a[j], a[j1], b[j1], b[j]]
            if flip:
                idx = idx[::-1]
            u0, u1 = ua[j] * u_scale, ua[j1] * u_scale
            if self.u_seams and j1 == 0:
                u1 = 1.0 * u_scale
            if self.u_seams and j in self.u_seams:
                u0 = 0.0
            uv = [(u0, va), (u1, va), (u1, vb), (u0, vb)]
            if flip:
                uv = uv[::-1]
            self.mb.add_quad(idx[0], idx[1], idx[2], idx[3], uv, smooth, mat)
            self.cells[(r_a, j)] = len(self.mb.faces) - 1

    def cap(self, r, center=None, flip=False, mat=0, smooth=True, u_center=(0.5, 0.5),
            part=None):
        """Close a ring with a triangle fan."""
        idxs = self.rings[r]
        n = len(idxs)
        if center is None:
            c = Vector((0, 0, 0))
            for i in idxs:
                c += self.mb.verts[i]
            c /= n
        else:
            c = Vector(center)
        if part is None:
            # The cap centre belongs to the same part as the ring it closes.
            # Without this it would fall back to the generic "body" tag and
            # the auto skinner would bind it to a different bone, which
            # stretches the cap into a spike.
            part = self.mb.part[idxs[0]] if idxs else None
        ci = self.mb.add_verts([c], part)[0]
        ua = self._u_with_seams(r)
        v = self.ring_v[r]
        for j in range(n):
            j1 = (j + 1) % n
            u0 = ua[j]
            u1 = ua[j1] if j1 != 0 else 1.0
            tri = [idxs[j], idxs[j1], ci]
            uv = [(u0, v), (u1, v), u_center]
            if flip:
                tri = tri[::-1]
                uv = uv[::-1]
            self.mb.add_tri(tri[0], tri[1], tri[2], uv, smooth, mat)

    # -- carving -----------------------------------------------------------
    def carve(self, r0, r1, j0, j1):
        """Delete the cells (r0..r1, j0..j1) and return the boundary loop.

        Column ranges may wrap around the ring (j1 < j0).  The loop is
        ordered so that the resulting branch surface faces outwards.
        """
        n = self.ncols
        cols = []
        j = j0 % n
        while True:
            cols.append(j)
            if j == (j1 % n):
                break
            j = (j + 1) % n
        for r in range(r0, r1 + 1):
            for jj in cols:
                key = (r, jj)
                if key in self.cells:
                    fi = self.cells.pop(key)
                    self.mb.dead.add(fi)
        return self.boundary_loop(r0, r1, cols)

    def boundary_loop(self, r0, r1, cols):
        n = self.ncols
        j0 = cols[0]
        j1 = cols[-1]
        loop = []
        for j in cols:
            loop.append(self.rings[r1 + 1][j % n])
        loop.append(self.rings[r1 + 1][(j1 + 1) % n])
        for r in range(r1, r0, -1):
            loop.append(self.rings[r][(j1 + 1) % n])
        loop.append(self.rings[r0][(j1 + 1) % n])
        for j in reversed(cols):
            loop.append(self.rings[r0][j % n])
        for r in range(r0 + 1, r1 + 1):
            loop.append(self.rings[r][j0 % n])
        out = []
        for v in loop:
            if not out or out[-1] != v:
                out.append(v)
        if len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out


def cleanup_faces(mb):
    """Remove faces that were carved away."""
    keep_f, keep_uv, keep_sm, keep_mat = [], [], [], []
    li = 0
    for i, f in enumerate(mb.faces):
        n = len(f)
        if i in mb.dead:
            li += n
            continue
        keep_f.append(f)
        keep_uv.extend(mb.loop_uvs[li:li + n])
        keep_sm.append(mb.face_smooth[i])
        keep_mat.append(mb.face_mat[i])
        li += n
    mb.faces = keep_f
    mb.loop_uvs = keep_uv
    mb.face_smooth = keep_sm
    mb.face_mat = keep_mat
    mb.dead = set()

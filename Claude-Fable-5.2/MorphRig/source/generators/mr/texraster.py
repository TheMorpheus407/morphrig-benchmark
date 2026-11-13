"""UV-space rasteriser (numpy): per-texel triangle id + barycentrics, attribute interpolation, dilation, PNG output."""
import struct
import zlib
import numpy as np


class MeshArrays:
    """Triangle soup of a Blender mesh in rest pose with everything the texture shaders need."""

    def __init__(self, me):
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        self.tri_loops = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get('loops', self.tri_loops)
        self.tri_loops = self.tri_loops.reshape(-1, 3)
        self.tri_verts = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get('vertices', self.tri_verts)
        self.tri_verts = self.tri_verts.reshape(-1, 3)
        self.tri_poly = np.empty(nt, dtype=np.int32)
        me.loop_triangles.foreach_get('polygon_index', self.tri_poly)
        self.tri_mat = np.empty(nt, dtype=np.int32)
        me.loop_triangles.foreach_get('material_index', self.tri_mat)
        self.co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get('co', self.co)
        self.co = self.co.reshape(-1, 3)
        uv = np.empty(len(me.loops) * 2, dtype=np.float64)
        me.uv_layers.active.data.foreach_get('uv', uv)
        self.uv = uv.reshape(-1, 2)
        cn = np.empty(len(me.loops) * 3, dtype=np.float64)
        me.corner_normals.foreach_get('vector', cn)
        self.corner_normal = cn.reshape(-1, 3)
        self.region = np.empty(len(me.polygons), dtype=np.int32)
        me.attributes['region'].data.foreach_get('value', self.region)
        self.region_names = list(me['region_names'])
        self.vattr = {}
        for a in me.attributes:
            if a.domain == 'POINT' and a.data_type == 'FLOAT':
                v = np.empty(len(me.vertices), dtype=np.float64)
                a.data.foreach_get('value', v)
                self.vattr[a.name] = v
        self.materials = [m.name if m else '' for m in me.materials]

    def region_id(self, name):
        return self.region_names.index(name) if name in self.region_names else -1

    def region_mask_vertices(self, names):
        """1.0 on vertices that belong to faces of the given regions."""
        ids = [self.region_id(n) for n in names]
        sel = np.isin(self.region[self.tri_poly], ids)
        m = np.zeros(len(self.co))
        m[self.tri_verts[sel].reshape(-1)] = 1.0
        return m

    def smooth_vertex_field(self, f, iters=4, lam=0.6):
        """Laplacian smoothing of a per-vertex scalar over the triangle graph."""
        a = np.concatenate([self.tri_verts[:, [0, 1]], self.tri_verts[:, [1, 2]], self.tri_verts[:, [2, 0]]])
        a = np.concatenate([a, a[:, ::-1]])
        f = f.astype(np.float64).copy()
        deg = np.bincount(a[:, 0], minlength=len(f)).astype(np.float64)
        deg[deg == 0] = 1.0
        for _ in range(iters):
            s = np.bincount(a[:, 0], weights=f[a[:, 1]], minlength=len(f))
            f = (1 - lam) * f + lam * s / deg
        return f


class Raster:
    """Rasterised texture space of one material."""

    def __init__(self, ma, mat_index, size):
        self.ma = ma
        self.size = size
        sel = np.nonzero(ma.tri_mat == mat_index)[0]
        self.tris = sel
        H = W = size
        tri_id = np.full((H, W), -1, dtype=np.int32)
        bary = np.zeros((H, W, 3), dtype=np.float32)
        px = ma.uv[ma.tri_loops[sel]] * size                    # (T, 3, 2) in pixel units (y up)
        for k in range(len(sel)):
            (ax, ay), (bx, by), (cx, cy) = px[k]
            x0 = max(int(np.floor(min(ax, bx, cx) - 1.0)), 0)
            x1 = min(int(np.ceil(max(ax, bx, cx) + 1.0)), W - 1)
            y0 = max(int(np.floor(min(ay, by, cy) - 1.0)), 0)
            y1 = min(int(np.ceil(max(ay, by, cy) + 1.0)), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-10:
                continue
            X = np.arange(x0, x1 + 1, dtype=np.float64) + 0.5
            Y = (np.arange(y0, y1 + 1, dtype=np.float64) + 0.5)[:, None]
            w0 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
            w1 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
            w2 = 1.0 - w0 - w1
            # conservative: accept pixel centres within ~0.6 px of the triangle
            e0 = 0.6 * np.hypot(bx - cx, by - cy) / abs(den)
            e1 = 0.6 * np.hypot(cx - ax, cy - ay) / abs(den)
            e2 = 0.6 * np.hypot(ax - bx, ay - by) / abs(den)
            inside = (w0 >= -e0) & (w1 >= -e1) & (w2 >= -e2)
            if not inside.any():
                continue
            # prefer true interior hits over conservative ones that were written before
            strict = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            sub_id = tri_id[y0:y1 + 1, x0:x1 + 1]
            sub_b = bary[y0:y1 + 1, x0:x1 + 1]
            write = inside & ((sub_id < 0) | strict)
            sub_id[write] = k
            sub_b[write, 0] = w0[write]
            sub_b[write, 1] = w1[write]
            sub_b[write, 2] = w2[write]
        self.tri_id = tri_id
        self.bary = bary
        self.mask = tri_id >= 0
        self.yx = np.nonzero(self.mask)
        self.n = len(self.yx[0])
        self.t = sel[tri_id[self.yx]]                           # global triangle index per covered texel
        self.b = bary[self.yx].astype(np.float64)
        bs = np.clip(self.b, 0.0, 1.0)
        self.bn = bs / bs.sum(axis=1, keepdims=True)            # clamped barycentrics (conservative border texels)

    # ---- interpolation onto the covered texels
    def vertex_attr(self, values):
        v = values[self.ma.tri_verts[self.t]]                   # (n, 3) or (n, 3, k)
        if v.ndim == 2:
            return (v * self.bn).sum(axis=1)
        return (v * self.bn[:, :, None]).sum(axis=1)

    def corner_attr(self, values):
        v = values[self.ma.tri_loops[self.t]]
        if v.ndim == 2:
            return (v * self.bn).sum(axis=1)
        return (v * self.bn[:, :, None]).sum(axis=1)

    def position(self):
        return self.vertex_attr(self.ma.co)

    def normal(self):
        n = self.corner_attr(self.ma.corner_normal)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    def region(self):
        return self.ma.region[self.ma.tri_poly[self.t]]

    def texel_size(self):
        """Metres per texel for every covered texel (from the 3D / UV area ratio of its triangle)."""
        ma = self.ma
        p = ma.co[ma.tri_verts[self.tris]]
        a3 = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
        u = ma.uv[ma.tri_loops[self.tris]] * self.size
        a2 = 0.5 * np.abs((u[:, 1, 0] - u[:, 0, 0]) * (u[:, 2, 1] - u[:, 0, 1]) - (u[:, 2, 0] - u[:, 0, 0]) * (u[:, 1, 1] - u[:, 0, 1]))
        s = np.sqrt(a3 / np.maximum(a2, 1e-12))
        return s[self.tri_id[self.yx]]

    # ---- images
    def image(self, values, channels=None, fill=0.0):
        """Scatter per-texel values (n,) or (n, k) into an (H, W[, k]) float image."""
        values = np.asarray(values, dtype=np.float32)
        if values.ndim == 1:
            img = np.full((self.size, self.size), fill, dtype=np.float32)
        else:
            img = np.full((self.size, self.size, values.shape[1]), fill, dtype=np.float32)
        img[self.yx] = values
        return img

    def dilate(self, img, iters=12):
        """Bleed covered texels outwards (edge padding against mip / filtering seams). Only the frontier texels of
        every pass are touched, so the cost follows the island perimeter and not the image area."""
        img = img.copy()
        mask = self.mask.copy()
        H, W = mask.shape
        nbrs = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
        for _ in range(iters):
            nb = np.zeros_like(mask)
            nb[1:, :] |= mask[:-1, :]
            nb[:-1, :] |= mask[1:, :]
            nb[:, 1:] |= mask[:, :-1]
            nb[:, :-1] |= mask[:, 1:]
            nb[1:, 1:] |= mask[:-1, :-1]
            nb[1:, :-1] |= mask[:-1, 1:]
            nb[:-1, 1:] |= mask[1:, :-1]
            nb[:-1, :-1] |= mask[1:, 1:]
            ys, xs = np.nonzero(nb & ~mask)
            if len(ys) == 0:
                break
            acc = np.zeros((len(ys),) + img.shape[2:], dtype=np.float64)
            cnt = np.zeros(len(ys), dtype=np.float64)
            for dy, dx in nbrs:
                yy, xx = ys + dy, xs + dx
                ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
                ok[ok] = mask[yy[ok], xx[ok]]
                if img.ndim == 3:
                    acc[ok] += img[yy[ok], xx[ok]]
                else:
                    acc[ok] += img[yy[ok], xx[ok]]
                cnt[ok] += 1.0
            if img.ndim == 3:
                img[ys, xs] = (acc / cnt[:, None]).astype(img.dtype)
            else:
                img[ys, xs] = (acc / cnt).astype(img.dtype)
            mask[ys, xs] = True
        return img

    def normal_from_height(self, height, strength=1.0):
        """Tangent-space normal map (OpenGL convention, +Y = +V) from a per-texel height in metres."""
        h = self.dilate(self.image(height), iters=3)
        s = self.dilate(self.image(self.texel_size(), fill=0.0), iters=3)
        s = np.where(s > 0, s, 1.0)
        dx = np.zeros_like(h)
        dy = np.zeros_like(h)
        dx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) * 0.5
        dy[1:-1, :] = (h[2:, :] - h[:-2, :]) * 0.5              # row index grows with v (y up)
        nx = -dx / s * strength
        ny = -dy / s * strength
        nz = np.ones_like(h)
        ln = np.sqrt(nx * nx + ny * ny + nz * nz)
        n = np.stack([nx / ln, ny / ln, nz / ln], axis=2)
        return n[self.yx]


def write_png(path, img, srgb_in=False):
    """img: float (H, W, 3|4) in 0..1 with row 0 = v 0 (bottom); written top-down as 8 bit PNG."""
    a = np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0)
    a = (a * 255.0 + 0.5).astype(np.uint8)[::-1]
    h, w, c = a.shape
    raw = np.concatenate([np.zeros((h, 1), dtype=np.uint8), a.reshape(h, w * c)], axis=1).tobytes()

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))

"""MorphRig procedural texture authoring (numpy).

Inputs per texture set are geometry maps baked in UV space by build_textures.py:
  P   (S, S, 3) rest-pose world position of every texel (metres)
  N   (S, S, 3) world normal
  AO  (S, S)    ambient occlusion
  PID (S, S)    part id (see mr_parts / scene['mr_part_names'])
  SH  (S, S)    shell id (1 outer, 2 inner, 3 rim, 0 = n/a)
  COV (S, S)    bool, texel covered by an island
Outputs (all float arrays in [0, 1]):
  BC  base colour, linear RGB  -> stored sRGB
  ORM R = ambient occlusion, G = roughness, B = metallic
  H   height in metres (converted to a tangent-space normal map)
  M   masks: R = team accent (tints base colour), G = emissive strength,
      B = team-A emblem (chevron), A = team-B emblem (ring)
"""
import zlib
import struct
import numpy as np

# ----------------------------------------------------------------- colour helpers
def srgb(hexstr):
    h = hexstr.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255.0
    return to_linear(c)


def to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def band(x, a, b, soft):
    """1 inside [a, b] with soft edges."""
    return smooth((x - a) / soft + 0.5) * smooth((b - x) / soft + 0.5)


# ----------------------------------------------------------------- noise (deterministic, vectorised)
def _hash3(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def vnoise(p, scale, seed=0):
    """Value noise in [0, 1]; p (n, 3) metres, scale = features per metre (per axis ok)."""
    q = p * np.asarray(scale, float)
    i = np.floor(q).astype(np.int64)
    f = q - i
    u = f * f * (3 - 2 * f)
    out = np.zeros(len(p), np.float32)
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                out += (wx * wy * wz).astype(np.float32) * _hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def fbm(p, scale, octaves=4, seed=0, gain=0.5):
    tot = np.zeros(len(p), np.float32)
    amp, norm = 1.0, 0.0
    s = np.asarray(scale, float)
    for o in range(octaves):
        tot += amp * vnoise(p, s, seed + o * 17)
        norm += amp
        amp *= gain
        s = s * 2.03
    return tot / norm


def cells(p, scale, seed=0):
    """Cheap cellular-ish pattern: distance to hashed feature point in the unit cell (0 = centre)."""
    q = p * scale
    i = np.floor(q).astype(np.int64)
    best = np.full(len(p), 9.0, np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = i + np.array([dx, dy, dz])
                fp = np.stack([_hash3(c[:, 0], c[:, 1], c[:, 2], seed + k) for k in range(3)], 1)
                d = np.linalg.norm(q - (c + fp), axis=1)
                best = np.minimum(best, d)
    return best


# ----------------------------------------------------------------- image utilities
def dilate(img, cov, iters=12):
    """Grow island colours into uncovered texels (keeps mip filtering from bleeding background)."""
    out = img.copy()
    m = cov.copy()
    for _ in range(iters):
        acc = np.zeros_like(out)
        cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(m, dy, 0), dx, 1)
            vals = np.roll(np.roll(out, dy, 0), dx, 1)
            add = sh & ~m
            if out.ndim == 3:
                acc[add] += vals[add]
            else:
                acc[add] += vals[add]
            cnt[add] += 1
        new = cnt > 0
        if not new.any():
            break
        if out.ndim == 3:
            out[new] = acc[new] / cnt[new][:, None]
        else:
            out[new] = acc[new] / cnt[new]
        m = m | new
    return out


def height_to_normal(H, cov, texel_m, strength=1.0):
    """Tangent-space normal (OpenGL convention: +Y = +V) from a height map in metres."""
    Hd = dilate(H.astype(np.float32), cov, 4)
    gy, gx = np.gradient(Hd)            # rows = v (image rows go +v because we store bottom-up)
    gx = gx / texel_m * strength
    gy = gy / texel_m * strength
    n = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def write_png(path, arr, srgb_encode=False):
    """arr (H, W, C) float in [0, 1], row 0 = bottom (Blender/UV convention). 8-bit PNG."""
    a = np.asarray(arr, np.float32)
    if a.ndim == 2:
        a = a[..., None]
    if srgb_encode:
        a = a.copy()
        a[..., :3] = to_srgb(a[..., :3])
    a = np.clip(np.round(a[::-1] * 255.0), 0, 255).astype(np.uint8)
    h, w, c = a.shape
    ctype = {1: 0, 3: 2, 4: 6}[c]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


# ----------------------------------------------------------------- texture context
class Ctx:
    """Holds the covered texels of one set as flat arrays; results are scattered back to images."""

    def __init__(self, maps, part_names):
        self.S = maps["P"].shape[0]
        self.cov = maps["COV"]
        idx = np.nonzero(self.cov.ravel())[0]
        self.idx = idx
        self.p = maps["P"].reshape(-1, 3)[idx].astype(np.float64)
        n = maps["N"].reshape(-1, 3)[idx].astype(np.float64)
        self.n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
        self.ao = maps["AO"].ravel()[idx]
        self.pid = np.round(maps["PID"].ravel()[idx]).astype(int)
        self.sh = np.round(maps["SH"].ravel()[idx]).astype(int)
        self.names = part_names
        k = len(idx)
        self.bc = np.zeros((k, 3))
        self.rough = np.full(k, 0.5)
        self.metal = np.zeros(k)
        self.h = np.zeros(k)
        self.m = np.zeros((k, 4))

    def part(self, *names):
        ids = [self.names.index(nm) for nm in names if nm in self.names]
        return np.isin(self.pid, ids)

    def part_prefix(self, prefix):
        ids = [i for i, nm in enumerate(self.names) if nm.startswith(prefix)]
        return np.isin(self.pid, ids)

    def paint(self, sel, color=None, rough=None, metal=None, w=None):
        """Blend material values into selected texels with weight w (defaults to 1)."""
        if w is None:
            w = np.ones(int(sel.sum())) if sel.dtype == bool else sel
        if sel.dtype == bool:
            idx = sel
            ww = w if np.ndim(w) else np.full(int(sel.sum()), w)
        else:
            idx = slice(None)
            ww = sel
        if color is not None:
            c = np.asarray(color, float)
            if c.ndim == 1:
                self.bc[idx] = self.bc[idx] * (1 - ww[:, None]) + c[None, :] * ww[:, None]
            else:
                self.bc[idx] = self.bc[idx] * (1 - ww[:, None]) + c * ww[:, None]
        if rough is not None:
            self.rough[idx] = self.rough[idx] * (1 - ww) + rough * ww
        if metal is not None:
            self.metal[idx] = self.metal[idx] * (1 - ww) + metal * ww

    def images(self):
        S = self.S
        out = {}

        def scatter(vals, ch):
            img = np.zeros((S * S, ch), np.float32)
            img[self.idx] = vals.reshape(len(self.idx), ch)
            return img.reshape(S, S, ch)
        out["BC"] = scatter(np.clip(self.bc, 0, 1), 3)
        orm = np.stack([np.clip(self.ao, 0, 1), np.clip(self.rough, 0.02, 1), np.clip(self.metal, 0, 1)], 1)
        out["ORM"] = scatter(orm, 3)
        out["H"] = scatter(self.h, 1)[..., 0]
        out["M"] = scatter(np.clip(self.m, 0, 1), 4)
        return out

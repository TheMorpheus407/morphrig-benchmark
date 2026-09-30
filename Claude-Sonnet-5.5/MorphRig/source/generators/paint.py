"""Procedural painters for the Operative textures (numpy). Every painter receives the rasterised attribute maps of one material atlas
(position, normal, vertex masks, object id per texel) and returns the channels of the game-ready texture set:
    bc (sRGB base colour), rough, metal, ao, height (metres, converted to a DirectX normal map later), emit (grey intensity), tm (RGBA team mask)
Team mask channels: R accent paint, G icon A (circle), B icon B (diamond), A reserved (1).
All patterns are functions of the 3D rest-pose position, so they stay continuous across UV seams."""
import numpy as np

# ----------------------------------------------------------------------------- noise


def _hash(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) ^ (np.int64(seed) * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / 16777216.0


def vnoise(p, freq, seed=0):
    """Trilinear value noise in [0,1]; p is (...,3) in metres, freq per metre (a scalar or a 3-vector for anisotropy)."""
    q = p * np.asarray(freq, dtype=np.float32)
    i = np.floor(q)
    f = (q - i).astype(np.float32)
    u = f * f * (3 - 2 * f)
    ix, iy, iz = i[..., 0], i[..., 1], i[..., 2]
    out = 0.0
    for dz in (0, 1):
        wz = u[..., 2] if dz else 1 - u[..., 2]
        for dy in (0, 1):
            wy = u[..., 1] if dy else 1 - u[..., 1]
            for dx in (0, 1):
                wx = u[..., 0] if dx else 1 - u[..., 0]
                out = out + _hash(ix + dx, iy + dy, iz + dz, seed) * wx * wy * wz
    return out


def fbm(p, freq, octaves=4, seed=0, gain=0.5, lac=2.03):
    amp, tot, out = 1.0, 0.0, 0.0
    fr = np.asarray(freq, dtype=np.float32)
    for o in range(octaves):
        out = out + amp * vnoise(p, fr, seed + 17 * o)
        tot += amp
        amp *= gain
        fr = fr * lac
    return out / tot


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def soft(dist, width):
    """Anti-aliased mask: 1 where dist > width / 2, 0 where dist < -width / 2 (dist positive inside the shape)."""
    return np.clip(dist / width + 0.5, 0.0, 1.0).astype(np.float32)


def lerp(a, b, t):
    return a + (b - a) * t


def mix3(a, b, t):
    t = np.asarray(t)[..., None]
    return a + (np.asarray(b) - a) * t


def col(r, g, b):
    return np.array([r, g, b], dtype=np.float32)


def new_channels(shape):
    H, W = shape
    return dict(bc=np.zeros((H, W, 3), np.float32), rough=np.full((H, W), 0.6, np.float32), metal=np.zeros((H, W), np.float32), ao=np.ones((H, W), np.float32),
                height=np.zeros((H, W), np.float32), emit=np.zeros((H, W), np.float32), tm=np.concatenate([np.zeros((H, W, 3), np.float32), np.ones((H, W, 1), np.float32)], axis=2))


def curvature(M, texel):
    """Convexity/concavity from the normal map: >0 convex edges, <0 concave creases (approximate, per metre)."""
    N = M['nrm']
    cov = M['cov']
    gx = np.zeros_like(N)
    gy = np.zeros_like(N)
    gx[:, 1:-1] = (N[:, 2:] - N[:, :-2]) * 0.5
    gy[1:-1] = (N[2:] - N[:-2]) * 0.5
    ok = cov.copy()
    ok[:, 1:-1] &= cov[:, 2:] & cov[:, :-2]
    ok[1:-1] &= cov[2:] & cov[:-2]
    # divergence of the tangent-plane normal variation ~ mean curvature
    div = gx[..., 0] * M['tx'][..., 0] + gx[..., 1] * M['tx'][..., 1] + gx[..., 2] * M['tx'][..., 2] + gy[..., 0] * M['ty'][..., 0] + gy[..., 1] * M['ty'][..., 1] + gy[..., 2] * M['ty'][..., 2]
    c = div / np.maximum(texel, 2e-5)
    c[~ok] = 0.0
    return c


# ----------------------------------------------------------------------------- shared helpers
def team_icons(M, ch, obj_ids, specs):
    """Paint the two team icons (circle in G, diamond in B) on armour surfaces found from geometry.
    specs: list of dict(select=boolean mask over the atlas, axes=(i, j) world axes of the icon plane, radius=metres). The icon is centred on
    the centroid of the selected texels, so it always lands on real armour."""
    pos = M['pos']
    for sp in specs:
        m = sp['select'] & np.isin(M['oid'], obj_ids) & M['cov']
        if m.sum() < 200:
            continue
        ia, ib = sp['axes']
        w = m.astype(np.float32)
        ac = float((pos[..., ia] * w).sum() / w.sum())
        bc = float((pos[..., ib] * w).sum() / w.sum())
        da = pos[..., ia] - ac
        db = pos[..., ib] - bc
        r = sp['radius']
        circle = np.clip((r - np.sqrt(da * da + db * db)) / 0.0012, 0.0, 1.0) * m
        diamond = np.clip((r * 1.18 - (np.abs(da) + np.abs(db))) / 0.0012, 0.0, 1.0) * m
        ch['tm'][..., 1] = np.maximum(ch['tm'][..., 1], circle)
        ch['tm'][..., 2] = np.maximum(ch['tm'][..., 2], diamond)


# ----------------------------------------------------------------------------- landmarks (character space, metres)
EYE_C = {1: np.array([0.0715, 0.031, 1.6855], np.float32), -1: np.array([0.0715, -0.031, 1.6855], np.float32)}
EYE_A, EYE_B, EYE_P = 0.0128, 0.0060, 2.3          # opening half width / height, superellipse exponent (head.eye_openings)
MOUTH_Z, MOUTH_HALF = 1.6235, 0.0265
BROW_PTS = np.array([[0.016, 1.7075], [0.027, 1.7130], [0.040, 1.7165], [0.052, 1.7150], [0.063, 1.7100]], np.float32)     # (|y|, z)
BROW_W = np.array([0.0034, 0.0033, 0.0029, 0.0022, 0.0011], np.float32)


def poly_dist(y, z, pts, widths=None):
    """Distance from (y,z) samples to a polyline; also the interpolated half width at the closest point."""
    best = np.full(y.shape, 9.0, np.float32)
    wbest = np.zeros(y.shape, np.float32)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = b - a
        L2 = float(d @ d)
        t = np.clip(((y - a[0]) * d[0] + (z - a[1]) * d[1]) / L2, 0.0, 1.0)
        dy = y - (a[0] + t * d[0])
        dz = z - (a[1] + t * d[1])
        dist = np.sqrt(dy * dy + dz * dz)
        upd = dist < best
        best = np.where(upd, dist, best)
        if widths is not None:
            wbest = np.where(upd, widths[i] + (widths[i + 1] - widths[i]) * t, wbest)
    return best, wbest


def names_mask(M, *names):
    ids = [i for i, n in enumerate(M['names']) if n in names]
    return np.isin(M['oid'], ids) & M['cov']


# ----------------------------------------------------------------------------- skin
def paint_skin(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    extra = M['mask'][..., 2]
    head = names_mask(M, 'Operative_Head')
    body = names_mask(M, 'Operative_Body')
    hand = names_mask(M, 'Operative_Hand_R')
    # base tone with slow variation, redder over cheeks/nose/ears, a cooler cast in shadowed hollows
    n_lo = fbm(pos, 9.0, 4, 3)
    n_mid = fbm(pos, 60.0, 3, 7)
    base = col(0.575, 0.395, 0.315)
    tone = base[None, None, :] * (0.94 + 0.12 * n_lo)[..., None]
    tone = tone + (n_mid[..., None] - 0.5) * col(0.030, 0.018, 0.014)
    blush = np.exp(-(((np.abs(y) - 0.047) / 0.020) ** 2 + ((x - 0.072) / 0.030) ** 2 + ((z - 1.645) / 0.020) ** 2))
    tone = tone + blush[..., None] * col(0.070, -0.010, -0.010) * head[..., None]
    nose = np.exp(-(((y) / 0.014) ** 2 + ((z - 1.650) / 0.016) ** 2 + ((x - 0.108) / 0.014) ** 2))
    tone = tone + nose[..., None] * col(0.05, -0.012, -0.012) * head[..., None]
    ear = (np.abs(extra - 0.25) < 0.02) & (np.abs(y) > 0.068) & head
    tone = np.where(ear[..., None], tone * col(1.10, 0.88, 0.86), tone)
    # knuckles / joints of the hand slightly darker, forearm hair-line freckles
    freck = smoothstep(0.80, 0.86, fbm(pos, 240.0, 2, 11))
    tone = tone * (1.0 - 0.10 * freck[..., None] * (body | hand)[..., None])
    # eye sockets: darker, cooler skin, and the upper-lid crease
    for s in (1, -1):
        dy, dz = y - EYE_C[s][1], z - EYE_C[s][2]
        r = (np.abs(dy) / EYE_A) ** EYE_P + (np.abs(dz) / EYE_B) ** EYE_P
        near = head & (x > 0.03) & (r < 12.0)
        sock = np.exp(-r / 5.0) * near
        tone = tone * (1.0 - 0.09 * sock[..., None]) + sock[..., None] * col(-0.006, -0.003, 0.008)
        crease = near * (dz > 0) * np.clip(1.0 - np.abs(r - 3.2) / 0.55, 0.0, 1.0)
        tone = tone * (1.0 - 0.18 * crease[..., None])
        # lash line and liner: dark band hugging the upper lid, longer at the outer corner
        outer = np.clip(dy * s / EYE_A, 0.0, 1.4)          # towards the outer corner
        lash = near * soft(dz + 0.0012, 0.0004) * soft(r - 0.88, 0.05) * soft(1.22 + 0.6 * np.clip(outer - 0.35, 0, 1) - r, 0.05) * soft(x - 0.06, 0.004)
        tone = tone * (1.0 - 0.92 * lash[..., None]) + 0.92 * lash[..., None] * col(0.040, 0.027, 0.024)[None, None, :]
        low = near * soft(-0.0012 - dz, 0.0004) * soft(r - 0.95, 0.05) * soft(1.20 - r, 0.05) * soft(x - 0.06, 0.004)
        tone = tone * (1.0 - 0.45 * low[..., None])
        # brows
        dist, hw = poly_dist(np.abs(y), z, BROW_PTS, BROW_W)
        brow = head & (np.sign(y) == s) & (nrm[..., 0] > 0.15) & (x > 0.05)
        stroke = 0.55 + 0.9 * vnoise(pos, np.array([700.0, 900.0, 1400.0], np.float32), 21)
        bm = np.clip((hw - dist) / 0.0016, 0.0, 1.0) * brow * np.clip(stroke, 0.0, 1.0)
        tone = tone * (1.0 - 0.92 * bm[..., None]) + 0.92 * bm[..., None] * col(0.105, 0.066, 0.048)
        ch['height'] += bm * 1.2e-4
    # lips and mouth interior
    dz = z - MOUTH_Z
    prof = np.clip(1.0 - (y / (MOUTH_HALF + 0.0045)) ** 2, 0.0, 1.0) ** 0.7
    # one band from the lower to the upper lip edge, with 0.5 mm soft borders
    band = np.minimum(dz + 0.0112 * prof + 0.0004, 0.0088 * prof + 0.0004 - dz)
    lips = head * soft(band, 0.0005) * soft(x - 0.06, 0.004) * soft(nrm[..., 0] - 0.10, 0.10) * soft(MOUTH_HALF + 0.005 - np.abs(y), 0.0005)
    lipc = col(0.515, 0.255, 0.255)
    edge = np.clip(1.0 - np.abs(np.abs(dz) - 0.0006) / 0.0010, 0.0, 1.0)
    lipm = np.clip(lips.astype(np.float32), 0, 1)
    tone = tone * (1.0 - lipm[..., None]) + lipm[..., None] * (lipc * (0.94 + 0.10 * vnoise(pos, np.array([1500, 300, 300], np.float32), 4))[..., None])
    tone = tone * (1.0 - 0.35 * (edge * lipm)[..., None])
    pocket = smoothstep(0.30, 0.45, extra) * (1.0 - smoothstep(0.55, 0.70, extra)) * head
    tone = tone * (1.0 - 0.6 * pocket[..., None]) + 0.6 * pocket[..., None] * col(0.50, 0.22, 0.22)
    inside = smoothstep(0.55, 0.95, extra) * head
    tone = tone * (1.0 - inside[..., None]) + inside[..., None] * (col(0.230, 0.058, 0.062) * (0.55 + 0.45 * smoothstep(0.02, 0.10, x)[..., None]))
    ch['bc'] = np.clip(tone, 0, 1)
    # roughness: skin ~0.52, lips glossier, mouth interior wet
    rough = 0.52 + 0.10 * n_mid - 0.14 * lipm
    rough = np.where(inside > 0.5, 0.22, rough)
    ch['rough'] = np.clip(rough, 0.08, 1.0).astype(np.float32)
    ch['ao'] = np.clip(1.0 - 0.55 * inside, 0, 1).astype(np.float32)
    # pores and fine skin relief
    pores = fbm(pos, 420.0, 3, 31) - 0.5
    ch['height'] += (pores * 3.5e-5 + (fbm(pos, 55.0, 2, 33) - 0.5) * 4.0e-5).astype(np.float32)
    ch['height'] += (vnoise(pos, np.array([1600.0, 250.0, 250.0], np.float32), 35) - 0.5).astype(np.float32) * 2.5e-5 * lipm
    return ch


# ----------------------------------------------------------------------------- suit
def paint_suit(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    fab = fbm(pos, 900.0, 2, 41)
    blot = fbm(pos, 14.0, 3, 43)
    base = col(0.058, 0.066, 0.086)
    bc = base[None, None, :] * (0.86 + 0.28 * blot)[..., None] * (0.92 + 0.16 * fab)[..., None]
    # reinforced panels: thighs (front), shins, shoulders and the abdomen are a lighter, slightly glossier weave
    panel = np.zeros((H, W), np.float32)
    panel += smoothstep(0.50, 0.56, z) * (1 - smoothstep(0.88, 0.94, z)) * (nrm[..., 0] > 0.15)      # front thigh
    panel += (1 - smoothstep(0.34, 0.40, z)) * smoothstep(0.10, 0.16, z) * (nrm[..., 0] > 0.30)          # shin
    panel += smoothstep(1.02, 1.06, z) * (1 - smoothstep(1.16, 1.20, z)) * (np.abs(y) < 0.10) * (nrm[..., 0] > 0.2)
    panel = np.clip(panel, 0, 1)
    bc = bc * (1.0 + 0.55 * panel[..., None])
    # seams: horizontal lines at the hip, knee and mid torso, vertical side seams (team accent piping)
    seam = np.zeros((H, W), np.float32)
    for z0, w in ((0.535, 0.0011), (0.945, 0.0013), (1.105, 0.0011), (0.185, 0.0010)):
        seam = np.maximum(seam, np.clip(1.0 - np.abs(z - z0) / w, 0.0, 1.0))
    bc = bc * (1.0 - 0.55 * seam[..., None])
    side = smoothstep(0.978, 0.992, np.abs(nrm[..., 1])) * (z > 0.06) * (1.0 - smoothstep(0.90, 0.96, z)) * (np.abs(y) > 0.06)   # leg stripes only: on the torso the mask breaks into blobs
    tm = np.clip(side, 0, 1)
    bc = np.where(tm[..., None] > 0.02, mix3(bc, col(0.34, 0.34, 0.36), tm), bc)
    ch['bc'] = np.clip(bc, 0, 1)
    ch['tm'][..., 0] = tm
    ch['rough'] = np.clip(0.66 - 0.16 * panel + 0.12 * (fab - 0.5) - 0.20 * tm, 0.2, 1.0).astype(np.float32)
    ch['metal'] = (0.04 * panel).astype(np.float32)
    weave = np.sin(pos[..., 1] * 2 * np.pi * 900.0) * np.sin(pos[..., 2] * 2 * np.pi * 900.0)
    ch['height'] = ((fab - 0.5) * 6e-5 + weave * 1.6e-5 * (0.6 + 0.8 * panel) - seam * 1.4e-4 + tm * 6e-5).astype(np.float32)
    ch['ao'] = np.clip(1.0 - 0.35 * seam, 0, 1).astype(np.float32)
    return ch


# ----------------------------------------------------------------------------- armour
def paint_armor(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    acc = M['mask'][..., 1]
    curv = curvature(M, M['texel'])
    edge = smoothstep(14.0, 60.0, curv)                                    # convex edges
    cavity = smoothstep(14.0, 70.0, -curv)
    grain = fbm(pos, 700.0, 3, 51)
    blot = fbm(pos, 22.0, 4, 53)
    scratch = smoothstep(0.66, 0.72, np.abs(vnoise(pos, np.array([1800.0, 60.0, 60.0], np.float32), 55) - 0.5) * 0 + fbm(pos, np.array([1400.0, 90.0, 90.0], np.float32), 2, 57)) * 0.55
    scratch = np.maximum(scratch, smoothstep(0.70, 0.75, fbm(pos, np.array([60.0, 1300.0, 60.0], np.float32), 2, 59)) * 0.45)
    wear = np.clip(edge * (0.5 + 0.9 * blot) + scratch * 0.35, 0, 1)
    paint = col(0.155, 0.165, 0.185)
    bc = paint[None, None, :] * (0.80 + 0.40 * blot)[..., None] * (0.94 + 0.12 * grain)[..., None]
    metal_col = col(0.560, 0.575, 0.600)
    bc = mix3(bc, metal_col, wear * 0.8)
    bc = bc * (1.0 - 0.45 * cavity[..., None])
    # team-accent painted panels (accent > 0.5): neutral mid grey that the material tints with the team colour
    acc_m = smoothstep(0.35, 0.65, acc)
    bc = mix3(bc, col(0.40, 0.40, 0.42) * (0.85 + 0.30 * grain)[..., None], acc_m)
    ch['bc'] = np.clip(bc, 0, 1)
    ch['tm'][..., 0] = acc_m
    ch['metal'] = np.clip(0.10 + 0.85 * wear, 0, 1).astype(np.float32)
    ch['rough'] = np.clip(0.50 - 0.16 * wear + 0.14 * (grain - 0.5) + 0.10 * cavity, 0.15, 1.0).astype(np.float32)
    ch['ao'] = np.clip(1.0 - 0.55 * cavity, 0, 1).astype(np.float32)
    ch['height'] = ((grain - 0.5) * 3.0e-5 - cavity * 2.5e-4 + scratch * -1.0e-4 + edge * 2.0e-5).astype(np.float32)
    gear = [i for i, n in enumerate(M['names']) if n == 'Operative_Gear']
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    torso = (z > 1.15) & (z < 1.42) & (np.abs(y) < 0.14)
    specs = [
        dict(select=torso & (x > 0.06) & (z > 1.295) & (nrm[..., 0] > 0.40) & (y > 0.035), axes=(1, 2), radius=0.020),      # outer face of the chest plate, left of the sternum strip
        dict(select=torso & (x < -0.03) & (nrm[..., 0] < -0.30) & (y > 0.035), axes=(1, 2), radius=0.024),    # outer face of the back plate, beside the emitter strip
        dict(select=(nrm[..., 2] > 0.5) & (z > 1.40) & (y < -0.12), axes=(0, 1), radius=0.020),                # top of the right shoulder guard (seen from above)
    ]
    team_icons(M, ch, gear, specs)
    # icon relief (raised) and a slightly brighter print
    ic = np.maximum(ch['tm'][..., 1], ch['tm'][..., 2])
    ch['height'] += ic * 1.2e-4
    ch['bc'] = np.where(ic[..., None] > 0.05, mix3(ch['bc'], col(0.46, 0.46, 0.48), ic), ch['bc'])
    return ch


# ----------------------------------------------------------------------------- cybernetics
def paint_cyber(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    emit = M['mask'][..., 0]
    acc = M['mask'][..., 1]
    curv = curvature(M, M['texel'])
    edge = smoothstep(14.0, 60.0, curv)
    cavity = smoothstep(14.0, 70.0, -curv)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    brushed = vnoise(np.stack([xx * 0.03, yy * 2.2, np.zeros_like(xx)], axis=-1), 1.0, 61)
    blot = fbm(pos, 30.0, 3, 63)
    metal = col(0.340, 0.355, 0.385)
    bc = metal[None, None, :] * (0.85 + 0.30 * blot)[..., None] * (0.90 + 0.20 * brushed)[..., None]
    bc = mix3(bc, col(0.62, 0.63, 0.66), edge * 0.6)
    bc = bc * (1.0 - 0.5 * cavity[..., None])
    em = smoothstep(0.08, 0.55, emit)
    bc = mix3(bc, col(0.030, 0.032, 0.036), em)                        # lenses / light strips: dark glass under the emission
    acc_m = smoothstep(0.30, 0.70, acc) * (1.0 - em)
    bc = mix3(bc, col(0.42, 0.42, 0.44) * (0.88 + 0.24 * brushed)[..., None], acc_m)
    ch['bc'] = np.clip(bc, 0, 1)
    ch['metal'] = np.clip(0.92 - 0.90 * em - 0.35 * acc_m, 0, 1).astype(np.float32)
    ch['rough'] = np.clip(0.30 + 0.18 * (brushed - 0.5) + 0.10 * blot + 0.30 * cavity - 0.20 * em, 0.1, 1.0).astype(np.float32)
    ch['ao'] = np.clip(1.0 - 0.6 * cavity, 0, 1).astype(np.float32)
    ch['height'] = ((brushed - 0.5) * 2.2e-5 - cavity * 2.0e-4 + edge * 1.5e-5).astype(np.float32)
    ch['emit'] = (em * np.clip(emit, 0, 1)).astype(np.float32)
    ch['tm'][..., 0] = acc_m
    return ch


# ----------------------------------------------------------------------------- hair
def paint_hair(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    braid = names_mask(M, 'Operative_Braid')
    cap = names_mask(M, 'Operative_Hair')
    # strands run front-to-back over the cap and along z in the braid
    f_cap = np.array([70.0, 1500.0, 1300.0], np.float32)
    f_braid = np.array([1500.0, 1500.0, 90.0], np.float32)
    strands = np.where(braid, fbm(pos, f_braid, 3, 71), fbm(pos, f_cap, 3, 73))
    coarse = fbm(pos, 40.0, 3, 75)
    base = col(0.034, 0.036, 0.052)
    bc = base[None, None, :] * (0.55 + 0.9 * strands)[..., None] * (0.9 + 0.3 * coarse)[..., None]
    sheen = smoothstep(0.6, 0.95, strands) * 0.10
    bc = bc + sheen[..., None] * col(0.35, 0.40, 0.55)
    # braid ties (MI_cyber) are separate faces, this atlas only carries hair
    ch['bc'] = np.clip(bc, 0, 1)
    ch['rough'] = np.clip(0.38 + 0.22 * (1 - strands), 0.15, 1.0).astype(np.float32)
    ch['ao'] = np.clip(0.75 + 0.25 * strands, 0, 1).astype(np.float32)
    ch['height'] = ((strands - 0.5) * 1.0e-4).astype(np.float32)
    return ch


# ----------------------------------------------------------------------------- mouth
def paint_mouth(M):
    pos, nrm, cov = M['pos'], M['nrm'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    part = M['mask'][..., 2]
    tongue = np.abs(part - 1.0) < 0.12
    n1 = fbm(pos, 500.0, 3, 81)
    n2 = fbm(pos, 80.0, 3, 83)
    teeth = col(0.845, 0.805, 0.715)
    bc = teeth[None, None, :] * (0.90 + 0.14 * n2)[..., None] * (0.96 + 0.08 * n1)[..., None]
    # teeth: darker gum-side and contact lines between neighbours
    gum = smoothstep(0.0, 1.0, 1.0 - np.clip((z - 1.6235) / 0.012, 0, 1)) * 0.0
    tongue_col = col(0.640, 0.245, 0.270)
    groove = np.exp(-((y / 0.0022) ** 2))
    tc = tongue_col[None, None, :] * (0.86 + 0.28 * n2)[..., None] * (1.0 - 0.32 * groove)[..., None]
    tc = tc + (smoothstep(0.55, 0.9, n1) * 0.06)[..., None] * col(1.0, 0.9, 0.9)
    bc = np.where(tongue[..., None], tc, bc)
    ch['bc'] = np.clip(bc, 0, 1)
    ch['rough'] = np.where(tongue, 0.30 + 0.2 * n1, 0.24 + 0.1 * n2).astype(np.float32)
    ch['ao'] = np.where(tongue, 0.85, 0.75).astype(np.float32)
    ch['height'] = np.where(tongue, (n1 - 0.5) * 2.2e-4 - groove * 1.0e-4, (n1 - 0.5) * 1.0e-5).astype(np.float32)
    return ch


# ----------------------------------------------------------------------------- eyes
def paint_eye(M):
    """Analytic: colour from the direction of the texel from its eye centre, forward = +X."""
    pos, cov = M['pos'], M['cov']
    H, W = cov.shape
    ch = new_channels((H, W))
    s = np.where(pos[..., 1] >= 0, 1, -1)
    cen = np.where((s > 0)[..., None], EYE_C[1][None, None, :], EYE_C[-1][None, None, :])
    d = pos - cen
    r = np.maximum(np.linalg.norm(d, axis=-1, keepdims=True), 1e-6)
    d = d / r
    theta = np.arccos(np.clip(d[..., 0], -1, 1))                      # angle from the gaze axis
    phi = np.arctan2(d[..., 2], d[..., 1])
    iris_r, pupil_r = 0.47, 0.19
    fibres = vnoise(np.stack([np.cos(phi) * 6.0, np.sin(phi) * 6.0, theta * 2.0], axis=-1), 3.0, 91)
    fibres2 = vnoise(np.stack([np.cos(phi) * 14.0, np.sin(phi) * 14.0, theta * 3.0], axis=-1), 3.0, 93)
    iris_in = col(0.60, 0.36, 0.10)
    iris_out = col(0.24, 0.30, 0.12)
    t = np.clip((theta - pupil_r) / (iris_r - pupil_r), 0, 1)
    iris = mix3(iris_in, iris_out, t) * (0.65 + 0.7 * fibres)[..., None] * (0.85 + 0.3 * fibres2)[..., None]
    limbal = smoothstep(iris_r - 0.09, iris_r, theta)
    iris = iris * (1.0 - 0.75 * limbal[..., None])
    sclera = col(0.860, 0.835, 0.815) * (0.93 + 0.10 * fbm(pos, 500.0, 2, 95))[..., None]
    veins = smoothstep(0.72, 0.86, fbm(np.stack([d[..., 0] * 9, d[..., 1] * 9, d[..., 2] * 9], axis=-1), 6.0, 3, 97)) * smoothstep(0.75, 1.2, theta) * 0.35
    sclera = mix3(sclera, col(0.72, 0.36, 0.34), veins)
    sclera = sclera * (1.0 - 0.25 * smoothstep(1.35, 2.0, theta)[..., None])
    bc = np.where((theta < iris_r)[..., None], iris, sclera)
    pupil = 1.0 - smoothstep(pupil_r - 0.02, pupil_r + 0.005, theta)
    bc = bc * (1.0 - pupil[..., None]) + pupil[..., None] * col(0.010, 0.010, 0.012)
    ch['bc'] = np.clip(bc, 0, 1)
    ch['rough'] = np.where(theta < iris_r + 0.05, 0.10, 0.28).astype(np.float32)
    ch['ao'] = np.ones((H, W), np.float32)
    ch['height'] = (-1.5e-5 * smoothstep(pupil_r, iris_r, theta) * (theta < iris_r)).astype(np.float32)      # iris sits slightly behind the cornea
    return ch


PAINTERS = {'skin': paint_skin, 'suit': paint_suit, 'armor': paint_armor, 'cyber': paint_cyber, 'hair': paint_hair, 'mouth': paint_mouth, 'eye': paint_eye}

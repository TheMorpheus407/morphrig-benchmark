"""MorphRig texture designs per texture set (see mr_textures for the data model).

Palette: charcoal techwear suit, olive-charcoal vest, bone-white hard plates with gunmetal rims,
gunmetal/carbon cyber limb.  Team accent areas are stored as a light neutral in the base colour
and flagged in mask R; the material multiplies them by the team colour (A cyan / B orange).
Mask G drives emission, mask B/A hold the team-A chevron and team-B ring emblems.
"""
import numpy as np
from mr_textures import srgb, smooth, band, vnoise, fbm, cells
from mr_params import J, H, EYE_R, ARM_DIR_UP, ARM_DIR_FO, PALM_NORMAL_L, FOOT_DIR_L, nrm

ACCENT_BASE = np.array([0.78, 0.78, 0.78])      # neutral that the team colour multiplies


def _accent(c, sel, glow=0.0, w=None):
    """Mark texels as team accent (+ optional emission)."""
    if w is None:
        w = np.ones(int(sel.sum()))
    c.paint(sel, ACCENT_BASE, rough=0.35, w=w)
    c.m[sel, 0] = np.maximum(c.m[sel, 0], w)
    if glow:
        c.m[sel, 1] = np.maximum(c.m[sel, 1], w * glow)


def _perp(d, axis):
    d = np.asarray(d, float)
    return nrm(d - np.dot(d, axis) * axis)


def _emblem(c, sel, centre, e1, e2, size):
    """Chevron (team A, mask B) and ring (team B, mask A) emblems in the plane (e1, e2)."""
    q = c.p[sel] - centre
    u = q @ e1 / size
    v = q @ e2 / size
    # chevron: two thick strokes meeting at the top, plus a bar
    s1 = np.abs((v - 0.35) - (-1.4 * np.abs(u))) < 0.22
    chevron = s1 & (np.abs(u) < 0.62) & (v > -0.62)
    chev2 = (np.abs((v + 0.2) - (-1.4 * np.abs(u))) < 0.14) & (np.abs(u) < 0.45) & (v > -0.9)
    ring = np.abs(np.hypot(u, v) - 0.55) < 0.14
    dot = np.hypot(u, v) < 0.16
    a = (chevron | chev2).astype(float)
    b = (ring | dot).astype(float)
    idx = np.nonzero(sel)[0]
    c.m[idx, 2] = np.maximum(c.m[idx, 2], a)
    c.m[idx, 3] = np.maximum(c.m[idx, 3], b)
    # emblem plate: slightly darker disc behind both emblems
    plate = np.hypot(u, v) < 0.95
    sub = idx[plate]
    c.bc[sub] = c.bc[sub] * 0.55
    c.h[sub] += 0.0002


def _limb_line(p, pts, ref_dir, halfw):
    """Mask of a line along a limb: angle around the limb polyline (pts) measured from ref_dir
    (per-segment, made perpendicular to the segment); halfw in metres."""
    pts = [np.asarray(q, float) for q in pts]
    best_d = np.full(len(p), 1e9)
    out = np.zeros(len(p), bool)
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        L2 = float(ab @ ab)
        t = np.clip((p - a) @ ab / L2, 0.0, 1.0)
        q = a + t[:, None] * ab
        r = p - q
        d = np.linalg.norm(r, axis=1)
        axis = ab / np.sqrt(L2)
        ref = _perp(ref_dir, axis)
        rr = r - (r @ axis)[:, None] * axis
        rn = np.linalg.norm(rr, axis=1) + 1e-9
        ang = np.arccos(np.clip((rr @ ref) / rn, -1, 1))
        on = (ang * rn) < halfw
        use = d < best_d
        out = np.where(use, on, out)
        best_d = np.minimum(best_d, d)
    return out


# ================================================================= suit (+ cloth gear)
def suit(c):
    p, n = c.p, c.n
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    allm = np.ones(len(p), bool)
    c.paint(allm, srgb("#3B3F46"), rough=0.78, metal=0.0)
    g = fbm(p, 55.0, 3, seed=1)
    c.bc *= (0.90 + 0.18 * g)[:, None]
    c.h += (vnoise(p, 1100.0, 3) - 0.5) * 0.00006
    torso = c.part("suit_torso")
    # ribbed side panels and their seams
    side = torso & (np.abs(x) > 0.105) & (z > 1.02) & (z < 1.40)
    c.paint(side, srgb("#30343A"), rough=0.83)
    c.h[side] += 0.00010 * np.sin(2 * np.pi * z[side] / 0.004)
    seam = torso & (np.abs(np.abs(x) - 0.105) < 0.0014) & (z > 1.02) & (z < 1.42)
    c.h[seam] -= 0.00035
    c.paint(seam, srgb("#191B1E"))
    # arms: dorsal accent piping (left full arm, right upper arm down to the cyber socket)
    for s, sg in (("l", 1.0), ("r", -1.0)):
        arm = c.part("suit_arm_" + s)
        up_ax = ARM_DIR_UP * np.array([sg, 1, 1])
        fo_ax = ARM_DIR_FO * np.array([sg, 1, 1])
        sh = J["upperarm_" + s]
        el = J["lowerarm_" + s]
        t = (p - sh) @ up_ax
        on_fore = t > np.linalg.norm(el - sh)
        ax = np.where(on_fore[:, None], fo_ax[None, :], up_ax[None, :])
        top = np.array([0, 0, 1.0])
        dors = top[None, :] - (ax @ top)[:, None] * ax
        dors /= np.linalg.norm(dors, axis=1, keepdims=True)
        pts = [sh, el, J["hand_" + s]] if s == "l" else [sh, el]
        pipe = arm & _limb_line(p, pts, top, 0.0028)
        _accent(c, pipe, glow=0.45)
        c.h[pipe] += 0.0003
        # quilted elbow patch on the organic arm
        if s == "l":
            de = np.linalg.norm(p - el, axis=1)
            patch = arm & (de < 0.055) & ((n * dors).sum(1) < 0.2)
            q1 = p @ nrm(np.array([0.3, 0.7, 0.6]))
            q2 = p @ nrm(np.array([-0.5, 0.2, 0.8]))
            quilt = (np.abs(np.sin(2 * np.pi * q1 / 0.012)) < 0.12) | (np.abs(np.sin(2 * np.pi * q2 / 0.012)) < 0.12)
            c.paint(patch, srgb("#1F2124"), rough=0.86)
            c.h[patch & quilt] -= 0.00035
    # legs: lateral piping + a cargo pocket on the right thigh
    for s, sg in (("l", 1.0), ("r", -1.0)):
        leg = c.part("suit_leg_" + s)
        pts = [J["thigh_" + s], J["calf_" + s], J["foot_" + s]]
        pipe = leg & _limb_line(p, pts, np.array([sg, 0.0, 0.0]), 0.0028) & (z > 0.30) & (z < 0.90)
        _accent(c, pipe, glow=0.45)
        c.h[pipe] += 0.0003
    pocket = c.part("suit_leg_r") & (x < -0.115) & (z > 0.60) & (z < 0.78) & (y > -0.045) & (y < 0.055)
    c.paint(pocket, srgb("#26292D"), rough=0.84)
    edge = pocket & ((z < 0.605) | (z > 0.775) | (y < -0.04) | (y > 0.05) | (np.abs(z - 0.74) < 0.0015))
    c.h[edge] -= 0.0004
    c.h[pocket] += 0.0006
    # ------------------------------------------------------------- vest
    vest = c.part("vest")
    c.paint(vest, srgb("#4D504B"), rough=0.86)
    c.bc[vest] *= (0.88 + 0.24 * fbm(p[vest], 40.0, 3, seed=5))[:, None]
    c.h[vest] += (vnoise(p[vest], 1400.0, 7) - 0.5) * 0.0001
    front = vest & (y < 0.0)
    back = vest & (y > 0.04)
    for zone, xlim in ((front, 0.135), (back, 0.15)):
        zz = (z - 1.075) % 0.038
        row = zone & (zz < 0.025) & (np.abs(x) < xlim) & (z > 1.07) & (z < 1.25)
        tack = row & (np.abs(((x + 0.019) % 0.038) - 0.019) < 0.0022)
        c.paint(row, srgb("#383A36"), rough=0.8)
        c.h[row] += 0.0008
        c.h[tack] -= 0.0005
    zipper = front & (np.abs(x) < 0.0045) & (z < 1.39)
    c.paint(zipper, srgb("#3A3A3D"), rough=0.35, metal=0.7)
    c.h[zipper] += 0.0005 * (np.sin(2 * np.pi * z[zipper] / 0.003) > 0)
    stripe = front & (np.abs(z - 1.305) < 0.003) & (np.abs(x) > 0.02) & (np.abs(x) < 0.125)
    _accent(c, stripe, glow=0.8)
    _emblem(c, back & (z > 1.24), np.array([0.0, 0.14, 1.315]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), 0.055)
    rim = vest & (c.sh == 3)
    inner = vest & (c.sh == 2)
    c.paint(rim, srgb("#1E1F1F"), rough=0.7)
    c.paint(inner, srgb("#18191A"), rough=0.9)
    # ------------------------------------------------------------- straps, collar, belt, bracer
    straps = c.part("strap_l", "strap_r")
    c.paint(straps, srgb("#2A2B2E"), rough=0.8)
    c.h[straps] += 0.00015 * np.sin(2 * np.pi * x[straps] / 0.003)
    collar = c.part("collar")
    c.paint(collar, srgb("#34373C"), rough=0.7)
    phi = np.arctan2(x, -(y - 0.018))
    ztop = 1.488 + 0.040 * 0.5 * (1 - np.cos(phi))
    ctop = collar & (z > ztop - 0.007) & (c.sh != 2)
    _accent(c, ctop, glow=0.9)
    belt = c.part("belt")
    c.paint(belt, srgb("#222326"), rough=0.75)
    c.h[belt] += 0.00012 * np.sin(2 * np.pi * z[belt] / 0.0025)
    bracer = c.part("bracer")
    c.paint(bracer, srgb("#393B40"), rough=0.55)
    a = ARM_DIR_FO
    dors = _perp(-PALM_NORMAL_L, a)
    s = (p - J["lowerarm_l"]) @ a
    br_strip = bracer & ((n @ dors) > 0.93) & (c.sh == 1)
    _accent(c, br_strip, glow=1.0)
    grooves = bracer & (np.abs(((s + 0.0125) % 0.025) - 0.0125) < 0.0012)
    c.h[grooves] -= 0.0004
    c.paint(bracer & (c.sh == 2), srgb("#141516"), rough=0.9)
    # cavity darkening
    c.bc *= (0.80 + 0.20 * c.ao)[:, None]


# ================================================================= armor (plates, boots, hardware)
def armor(c):
    p, n = c.p, c.n
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    allm = np.ones(len(p), bool)
    c.paint(allm, srgb("#45484E"), rough=0.35, metal=0.8)
    plates = c.part("pauldron_0", "pauldron_1", "kneepad_l", "kneepad_r")
    outer = plates & (c.sh == 1)
    c.paint(outer, srgb("#D2CEC5"), rough=0.42, metal=0.0)
    wear = fbm(p[outer], 30.0, 4, seed=11)
    c.bc[outer] *= (0.90 + 0.14 * wear)[:, None]
    c.rough[outer] += 0.08 * (wear - 0.5)
    c.paint(plates & (c.sh == 3), srgb("#3A3D42"), rough=0.32, metal=0.7)
    c.paint(plates & (c.sh == 2), srgb("#202226"), rough=0.6, metal=0.2)
    # pauldron: accent stripe + emblem on the top plate
    S = J["upperarm_r"]
    ax = nrm(J["lowerarm_r"] - S)
    up = _perp(np.array([0, 0, 1.0]), ax)
    fwd = nrm(np.cross(ax, up))
    if fwd[1] > 0:
        fwd = -fwd
    ctr = S + ax * 0.02
    sa = (p - ctr) @ ax
    p0 = c.part("pauldron_0") & (c.sh == 1)
    p1 = c.part("pauldron_1") & (c.sh == 1)
    _accent(c, p1 & (np.abs(sa - 0.075) < 0.006), glow=0.6)
    ang = np.radians(9.0)
    d0 = up * np.cos(ang) + ax * np.sin(ang)
    em_c = ctr + d0 * 0.075
    _emblem(c, p0, em_c, fwd, _perp(ax, d0), 0.028)
    # knee pads: accent stripe near the lower edge
    for s in "lr":
        K = J["calf_" + s]
        kp = c.part("kneepad_" + s) & (c.sh == 1)
        _accent(c, kp & (np.abs(z - (K[2] - 0.045)) < 0.005), glow=0.5)
        hexp = cells(p[kp], 160.0, seed=3)
        c.h[kp] -= 0.00025 * (hexp > 0.42)
    # boots
    for s, sg in (("l", 1.0), ("r", -1.0)):
        A = J["foot_" + s]
        fd = FOOT_DIR_L * np.array([sg, 1, 1])
        lat = nrm(np.cross(fd, np.array([0, 0, 1.0]))) * sg
        boot = c.part("boot") & (np.sign(x) == sg)
        rel = p - np.array([A[0], A[1], 0.0])
        sf = rel @ fd
        sl = rel @ lat
        c.paint(boot, srgb("#3A3C41"), rough=0.7, metal=0.0)
        c.bc[boot] *= (0.9 + 0.15 * fbm(p[boot], 50.0, 3, seed=21))[:, None]
        toe = boot & (sf > 0.105) & (z < 0.075)
        heel = boot & (sf < -0.03) & (z < 0.095)
        c.paint(toe | heel, srgb("#4A4D53"), rough=0.55)
        sole = boot & (z < 0.031)
        c.paint(sole, srgb("#111214"), rough=0.92)
        lugs = sole & (n[:, 2] < -0.7)
        c.h[lugs] -= 0.0012 * ((np.abs(np.sin(2 * np.pi * sf[lugs] / 0.016)) > 0.55)
                               | (np.abs(np.sin(2 * np.pi * sl[lugs] / 0.02)) > 0.8))
        welt = boot & (np.abs(z - 0.0335) < 0.0022)
        _accent(c, welt, glow=0.9)
        laces = boot & (sf > -0.005) & (sf < 0.095) & (z > 0.07) & (z < 0.21) & (np.abs(sl) < 0.019) & \
            ((n @ fd) > 0.25)
        cross = (np.abs(np.sin(2 * np.pi * (sf + z * 0.6 + sl) / 0.022)) < 0.28) | \
                (np.abs(np.sin(2 * np.pi * (sf + z * 0.6 - sl) / 0.022)) < 0.28)
        cord = laces & cross
        c.paint(laces, srgb("#1A1B1D"), rough=0.8)
        c.paint(cord, srgb("#0E0E0F"), rough=0.85)
        c.h[cord] += 0.0009
        tab = boot & (z > 0.245) & (sf < -0.02) & (np.abs(sl) < 0.013)
        _accent(c, tab, glow=0.3)
    # belt hardware
    c.paint(c.part("buckle"), srgb("#5B5F66"), rough=0.28, metal=0.85)
    bk = c.part("buckle") & (np.hypot(x, z - 0.977) < 0.006) & (y < -0.085)
    _accent(c, bk, glow=1.0)
    pouch = c.part("pouch")
    c.paint(pouch, srgb("#2F312F"), rough=0.86, metal=0.0)
    c.h[pouch] += (vnoise(p[pouch], 1400.0, 9) - 0.5) * 0.0001
    flap = pouch & (z > 0.985)
    c.paint(flap, srgb("#282A28"))
    c.h[pouch & (np.abs(z - 0.985) < 0.0015)] -= 0.0004
    ch = c.part("charger")
    c.paint(ch, srgb("#3A3D42"), rough=0.4, metal=0.6)
    chc = np.array([0.175, -0.035, 0.955]) - nrm(np.array([0.98, -0.20, 0.0])) * 0.004
    ring = ch & (np.abs(np.linalg.norm(p - chc, axis=1) - 0.018) < 0.003)
    _accent(c, ring, glow=1.0)
    c.paint(c.part("beacon_clip"), srgb("#45484E"), rough=0.35, metal=0.8)
    band_ = c.part("hair_band")
    c.paint(band_, srgb("#45484E"), rough=0.3, metal=0.85)
    mid = band_ & (np.abs(p[:, 2] - 1.718) < 0.0025)
    _accent(c, mid, glow=0.8)
    c.bc *= (0.78 + 0.22 * c.ao)[:, None]


# ================================================================= cyber limb and props
def cyber(c):
    p, n = c.p, c.n
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    allm = np.ones(len(p), bool)
    c.paint(allm, srgb("#6A707B"), rough=0.33, metal=0.85)
    E = J["lowerarm_r"]
    ax = nrm(J["hand_r"] - E)
    s = (p - E) @ ax
    plates = c.part("cyber_plate_dorsal", "cyber_plate_ventral")
    brushed = vnoise(p[plates] - np.outer(p[plates] @ ax, ax), 900.0, 13)
    c.rough[plates] = 0.26 + 0.12 * brushed
    grooves = plates & (np.abs(((s + 0.02) % 0.04) - 0.02) < 0.0011)
    c.h[grooves] -= 0.0005
    c.paint(grooves, srgb("#2A2D32"))
    core = c.part("cyber_core")
    c.paint(core, srgb("#2A2C31"), rough=0.45, metal=0.2)
    rel = p[core] - E
    ang = np.arctan2(rel @ nrm(np.cross(ax, [0, 0, 1.0])), rel @ np.array([0, 0, 1.0]))
    u = s[core] / 0.004
    v = ang * 0.025 / 0.004
    weave = ((np.floor(u + v) + np.floor(u - v)) % 2).astype(float)
    c.bc[core] *= (0.8 + 0.4 * weave)[:, None]
    c.rough[core] = 0.35 + 0.2 * weave
    dark = c.part("cyber_elbow", "cyber_socket", "cyber_wrist", "cyber_knuckles", "emitter_mount") | \
        c.part_prefix("cyber_") & np.isin(c.pid, [i for i, nm in enumerate(c.names) if "_pin" in nm])
    c.paint(dark, srgb("#40434A"), rough=0.4, metal=0.85)
    c.paint(c.part("emitter"), srgb("#3A3D44"), rough=0.3, metal=0.9)
    muz = c.part("emitter_muzzle")
    c.paint(muz, srgb("#2A2C31"), rough=0.3, metal=0.9)
    mz_front = muz & ((n @ ax) > 0.6)
    _accent(c, mz_front, glow=1.0)
    crad = c.part("cell_cradle")
    c.paint(crad, srgb("#2A2C31"), rough=0.35, metal=0.85)
    _accent(c, crad & (c.ao > 0.8) & (np.abs(((s + 0.01) % 0.02) - 0.01) < 0.0015), glow=0.8)
    c.paint(c.part("blade_housing"), srgb("#33363C"), rough=0.3, metal=0.9)
    blade = c.part("blade")
    c.paint(blade, srgb("#B9BFC7"), rough=0.16, metal=1.0)
    c.rough[blade] += 0.06 * vnoise(p[blade], 600.0, 17)
    palm = c.part("cyber_palm")
    c.paint(palm, srgb("#555A63"), rough=0.35, metal=0.85)
    tips = c.part("cyber_index_3", "cyber_middle_3", "cyber_ring_3", "cyber_pinky_3", "cyber_thumb_3")
    pads = tips & ((n @ np.array([0.0, 0.0, -1.0])) > -2)      # whole tip, rubberised
    c.paint(pads, srgb("#202124"), rough=0.7, metal=0.1)
    # power cell: glowing core window
    cell = c.part("power_cell")
    c.paint(cell, srgb("#3E4148"), rough=0.3, metal=0.8)
    if cell.any():
        pc = p[cell]
        cen = pc.mean(0)
        u_, s_, vt = np.linalg.svd(pc - cen, full_matrices=False)
        cax = vt[0]
        t = (pc - cen) @ cax
        win = np.abs(t) < 0.012
        idx = np.nonzero(cell)[0][win]
        sel = np.zeros(len(p), bool)
        sel[idx] = True
        _accent(c, sel, glow=1.0)
    # beacon: armour-white shell with a glowing equator
    bea = c.part("beacon")
    if bea.any():
        pb = p[bea]
        cen = pb.mean(0)
        c.paint(bea, srgb("#D2CEC5"), rough=0.4, metal=0.0)
        low = bea & (z < cen[2] - 0.012)
        c.paint(low, srgb("#2B2D31"), rough=0.4, metal=0.7)
        eq = bea & (np.abs(z - cen[2]) < 0.004)
        _accent(c, eq, glow=1.0)
    c.paint(c.part("comm_disc"), srgb("#3E4148"), rough=0.3, metal=0.85)
    _accent(c, c.part("comm_rim"), glow=1.0)
    c.paint(c.part("comm_fin"), srgb("#2A2C31"), rough=0.4, metal=0.8)
    c.bc *= (0.75 + 0.25 * c.ao)[:, None]


# ================================================================= skin (head + left hand)
HAIR_C = np.array([0.0, 0.012, 1.655])


def _hairline_el(a):
    front = np.clip(np.cos(a), 0, 1)
    side = np.abs(np.sin(a))
    back = np.clip(-np.cos(a), 0, 1)
    return np.maximum(33.0 * front ** 1.3 + 10.0 * side * (1 - back) - 34.0 * back ** 1.5, -34.0)


def skin(c):
    import mr_hand
    p, n = c.p, c.n
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    allm = np.ones(len(p), bool)
    base = srgb("#B98468")
    c.paint(allm, base, rough=0.48, metal=0.0)
    lo = fbm(p, 25.0, 3, seed=31)
    c.bc *= (0.93 + 0.12 * lo)[:, None]
    blot = fbm(p, 140.0, 3, seed=37)
    c.bc += (np.array([0.020, -0.004, -0.006]) * (blot - 0.5)[:, None])
    # pores / micro relief
    c.h += (vnoise(p, 2600.0, 41) - 0.5) * 0.00005 + (vnoise(p, 700.0, 43) - 0.5) * 0.00006
    head = c.part("head")
    hand = c.part("hand_l")
    red = srgb("#B5645A")
    for sgx in (1.0, -1.0):
        cheek = np.array([0.045 * sgx, -0.080, 1.635])
        w = np.exp(-(np.linalg.norm(p - cheek, axis=1) / 0.018) ** 2) * head
        c.paint(allm, red, w=0.22 * w)
        ear = np.array([0.075 * sgx, 0.005, 1.645])
        w = np.exp(-(np.linalg.norm(p - ear, axis=1) / 0.025) ** 2) * head
        c.paint(allm, red, w=0.25 * w)
    nose = np.exp(-(np.linalg.norm(p - H["nose_tip"], axis=1) / 0.012) ** 2) * head
    c.paint(allm, red, w=0.25 * nose)
    c.rough -= 0.08 * nose + 0.06 * np.exp(-(np.linalg.norm(p - np.array([0, -0.10, 1.72]), axis=1) / 0.03) ** 2) * head
    # lips
    M = H["mouth"]
    hw = H["mouth_half_width"] if "mouth_half_width" in H else 0.0252
    dz = z - M[2]
    lips = c.part("lips")
    lipb = c.part("lip_border")
    lipw = lips | lipb
    corner = 1.0 - smooth((np.abs(x) - hw * 0.78) / (hw * 0.3))
    wl = np.where(lips, 0.78, 0.0) + np.where(lipb, 0.30, 0.0)
    c.paint(allm, srgb("#9A5850"), rough=0.36, w=wl * corner)
    c.h[lips] += (vnoise(p[lips] * np.array([1.0, 1.0, 0.1]), 2200.0, 47) - 0.5) * 0.00008
    inner = c.part("mouth_inner")
    depth = smooth((y - (M[1] + 0.004)) / 0.008)
    c.paint(allm, srgb("#4A2222"), rough=0.4, w=inner * (0.5 + 0.5 * depth))
    # eyebrows: arcs above each eye, strand texture
    brow_col = srgb("#2C1F18")
    for sgx in (1.0, -1.0):
        E = H["eye_l"] * np.array([sgx, 1, 1])
        t = (x * sgx - 0.010) / 0.042
        arc_z = 1.6975 + 0.0060 * np.sin(np.clip(t, 0, 1) * np.pi * 0.85) - 0.002 * t
        thick = 0.0055 * (1.2 - 0.55 * np.clip(t, 0, 1))
        wb = head & (t > -0.05) & (t < 1.05) & (y < E[1] + 0.02) & (np.abs(z - arc_z) < thick)
        strands = vnoise(p * np.array([1.0, 1.0, 0.25]), np.array([1800.0, 1800.0, 1800.0]), 51)
        dens = smooth((thick - np.abs(z - arc_z)) / 0.0015) * smooth((t + 0.05) / 0.12) * smooth((1.05 - t) / 0.15)
        wbw = wb * dens * (0.55 + 0.45 * strands)
        c.paint(allm, brow_col, rough=0.62, w=np.clip(1.25 * wbw, 0, 0.97))
        c.h += 0.00012 * wbw
        # lash lines along the lid margins (upper stronger)
        side = (x * sgx) > 0
        upper = z > E[2] - 0.0005
        lid = c.part("lid_margin") & side
        c.paint(lid, srgb("#1A1210"), rough=0.5, w=np.where(upper[lid], 0.92, 0.45))
    # undercut: shaved scalp below / beside the modelled top hair
    rel = p - HAIR_C
    r = np.linalg.norm(rel, axis=1)
    el = np.degrees(np.arcsin(np.clip(rel[:, 2] / np.maximum(r, 1e-6), -1, 1)))
    a = np.arctan2(rel[:, 0], -rel[:, 1])
    hl = _hairline_el(a)
    scalp = head & (el > hl - 2.0) & (r > 0.06)
    ws = scalp * smooth((el - (hl - 2.0)) / 3.0)
    dots = vnoise(p, 4200.0, 61)
    stub = srgb("#3A2E27")
    c.paint(allm, stub, rough=0.62, w=(0.55 + 0.35 * (dots > 0.55)) * ws)
    # beard shadow (jaw, chin, upper lip)
    face_front = head & ~lipw & ~inner
    wj = face_front * smooth((1.622 - z) / 0.022) * smooth((z - 1.545) / 0.012) \
        * smooth((0.035 - y) / 0.03) * (1 - smooth((np.abs(x) - 0.066) / 0.012))
    wul = face_front * (1 - smooth((np.abs(x) - 0.018) / 0.006)) * smooth((dz - 0.004) / 0.003) \
        * (1 - smooth((dz - 0.016) / 0.004)) * smooth((M[1] + 0.012 - y) / 0.01)
    wj = np.maximum(wj, 0.8 * wul)
    c.paint(allm, srgb("#6A5A52"), rough=0.55, w=0.30 * wj * (0.6 + 0.4 * (dots > 0.5)))
    # hand: knuckle redness, nails
    if hand.any():
        hj = mr_hand.hand_joints_world("l")
        R, _ = mr_hand.hand_frame("l")
        back = -R[:, 2]
        for f in mr_hand.FINGERS + ["thumb"]:
            key = f + ("_03" if True else "")
            h0, t0 = hj[f + "_03"]
            tipdir = nrm(t0 - h0)
            nail_c = h0 + (t0 - h0) * 0.62
            dn = np.linalg.norm(p - nail_c, axis=1)
            dorsal = (n @ back) > 0.35 if f != "thumb" else (n @ nrm(back + R[:, 1])) > 0.2
            nail = hand & dorsal & (dn < 0.0065)
            c.paint(nail, srgb("#D6A594"), rough=0.28)
            c.h[nail] += 0.00015
            if f != "thumb":
                kn = hj[f + "_01"][0]
                wk = np.exp(-(np.linalg.norm(p - kn, axis=1) / 0.010) ** 2) * hand
                c.paint(allm, red, w=0.25 * wk)
    c.bc *= (0.86 + 0.14 * c.ao)[:, None]


# ================================================================= hair
def hair(c):
    p, n = c.p, c.n
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    allm = np.ones(len(p), bool)
    c.paint(allm, srgb("#2A211C"), rough=0.5, metal=0.0)
    top = c.part("hair")
    tail = c.part("hair_tail")
    s_top = vnoise(p[top] * np.array([1.0, 0.05, 0.05]), 2600.0, 71)
    s_top2 = vnoise(p[top] * np.array([1.0, 0.08, 0.08]), 700.0, 73)
    c.bc[top] *= (0.72 + 0.45 * s_top * (0.6 + 0.4 * s_top2))[:, None]
    c.h[top] += 0.00035 * (s_top - 0.5)
    rel = p[tail] - np.array([0.0, 0.13, 1.66])
    ang = np.arctan2(rel[:, 0], rel[:, 1] - 0.0)
    s_t = vnoise(np.stack([ang * 0.02, np.zeros_like(ang), z[tail] * 0.05], 1), 2600.0, 75)
    c.bc[tail] *= (0.72 + 0.45 * s_t)[:, None]
    c.h[tail] += 0.0003 * (s_t - 0.5)
    c.rough += 0.1 * (vnoise(p, 900.0, 77) - 0.5)
    # dyed streak (team accent) on the left of the top section
    streak = top & (x > 0.021) & (x < 0.027) & (c.sh == 1)
    w = smooth((x[streak] - 0.021) / 0.0015) * smooth((0.027 - x[streak]) / 0.0015)
    _accent(c, streak, glow=0.0, w=w * 0.85)
    c.paint(c.sh == 3, srgb("#1E1714"))
    c.bc *= (0.75 + 0.25 * c.ao)[:, None]


# ================================================================= eye (uv-radial)
def eye(c, uv):
    """uv (k, 2) texture coordinates of the covered texels."""
    r = np.hypot(uv[:, 0] - 0.5, uv[:, 1] - 0.5)
    ang = np.arctan2(uv[:, 1] - 0.5, uv[:, 0] - 0.5)
    theta = np.degrees(2 * r * np.pi / 0.98)
    allm = np.ones(len(r), bool)
    c.paint(allm, srgb("#E6E1D8"), rough=0.04, metal=0.0)
    vein = vnoise(np.stack([np.cos(ang) * 3, np.sin(ang) * 3, r * 40], 1), 7.0, 81)
    periph = smooth((theta - 45) / 40)
    c.paint(allm, srgb("#D9A89E"), w=0.35 * periph * (vein > 0.62))
    iris = theta < 28.0
    fib = vnoise(np.stack([np.cos(ang) * 40, np.sin(ang) * 40, r * 120], 1), 1.0, 83)
    t = theta[iris] / 28.0
    col = srgb("#5E6B3B") * (0.75 + 0.5 * fib[iris])[:, None]
    col = col * (1 - smooth((t - 0.8) / 0.2) * 0.65)[:, None]            # limbal ring
    col = col + srgb("#8C7A44") * (0.6 * (1 - smooth((t - 0.30) / 0.15)))[:, None]   # collarette
    c.bc[iris] = col
    pupil = theta < 9.5
    c.paint(pupil, srgb("#040404"))
    c.h[iris] -= 0.0001 * (1 - t)
    c.rough[:] = 0.03


# ================================================================= mouth
def mouth(c):
    p = c.p
    teeth = c.part("teeth_upper", "teeth_lower")
    gums = c.part("gum_upper", "gum_lower")
    tongue = c.part("tongue")
    c.paint(teeth, srgb("#E3DCCB"), rough=0.25)
    c.paint(gums, srgb("#B5605C"), rough=0.4)
    c.paint(tongue, srgb("#B95E5A"), rough=0.55)
    c.h[tongue] += (vnoise(p[tongue], 3000.0, 91) - 0.5) * 0.00008
    c.bc *= (0.55 + 0.45 * c.ao)[:, None]


DESIGNS = {"suit": suit, "armor": armor, "cyber": cyber, "skin": skin, "hair": hair, "mouth": mouth}

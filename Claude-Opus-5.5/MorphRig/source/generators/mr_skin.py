"""MorphRig per-part skin weight assignment (uses mr_weights primitives)."""
import numpy as np
from mr_weights import (chain_weights, add_into, normalize_weights, smooth_weights, split_twist,
                        transfer_weights, smoothstep, closest_on_segment)
from mr_params import J, H, EYE_R, nrm, v
from mr_sdf import length


def _chain(bones, names):
    return [(n, bones[n][0], bones[n][1]) for n in names]


def suit_weights(m, bones):
    P = m.v
    n = m.nv
    E = m.edges()[0]
    W = {}
    arm_l, arm_r = m.groups["arm_l"], m.groups["arm_r"]
    leg_l, leg_r = m.groups["leg_l"], m.groups["leg_r"]
    torso_only = m.groups["torso"] & ~arm_l & ~arm_r & ~leg_l & ~leg_r
    # torso spine chain
    tw, s, S = chain_weights(P, _chain(bones, ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "neck_02"]),
                             [0.05, 0.06, 0.07, 0.035, 0.025])
    # clavicle influence on upper lateral torso
    ax = np.abs(P[:, 0])
    wcl = smoothstep((ax - 0.055) / 0.08) * smoothstep((P[:, 2] - 1.34) / 0.07) * 0.75
    for nm in list(tw):
        tw[nm] = tw[nm] * (1 - wcl)
    tw["clavicle_l"] = wcl * (P[:, 0] > 0)
    tw["clavicle_r"] = wcl * (P[:, 0] <= 0)
    add_into(W, tw, mask=m.groups["torso"])
    # arms
    for sd, mask in (("l", arm_l), ("r", arm_r)):
        names = [f"clavicle_{sd}", f"upperarm_{sd}", f"lowerarm_{sd}", f"hand_{sd}"]
        aw, s_, S_ = chain_weights(P, _chain(bones, names), [0.05, 0.034, 0.02])
        # ring0 (junction) handled by torso weights; blend arm root toward torso values
        add_into(W, aw, mask=mask & ~m.groups["torso"])
        # twist splits
        W = split_twist(W, f"upperarm_{sd}", f"upperarm_twist_01_{sd}", P, J[f"upperarm_{sd}"], J[f"lowerarm_{sd}"],
                        t0=0.05, t1=0.75, share=0.8, reverse=True)
        if sd == "l":
            W = split_twist(W, f"lowerarm_{sd}", f"lowerarm_twist_01_{sd}", P, J[f"lowerarm_{sd}"], J[f"hand_{sd}"],
                            t0=0.25, t1=1.0, share=0.9)
    # legs
    for sd, mask in (("l", leg_l), ("r", leg_r)):
        names = ["pelvis", f"thigh_{sd}", f"calf_{sd}", f"foot_{sd}"]
        ch = _chain(bones, names)
        ch[0] = ("pelvis", J["pelvis"] + v(0, 0, 0.0), J[f"thigh_{sd}"])
        lw, s_, S_ = chain_weights(P, ch, [0.07, 0.042, 0.03])
        add_into(W, lw, mask=mask & ~m.groups["torso"])
        W = split_twist(W, f"thigh_{sd}", f"thigh_twist_01_{sd}", P, J[f"thigh_{sd}"], J[f"calf_{sd}"],
                        t0=0.05, t1=0.7, share=0.7, reverse=True)
    # smoothing near junctions
    junction = np.zeros(n, bool)
    for sd in ("l", "r"):
        junction |= length(P - J[f"upperarm_{sd}"]) < 0.11
        junction |= length(P - J[f"thigh_{sd}"]) < 0.13
    junction |= P[:, 2] > 1.42
    W = smooth_weights(W, E, n, iters=14, lam=0.5, mask=junction)
    W = smooth_weights(W, E, n, iters=2, lam=0.3)
    return normalize_weights(W, n)


def head_weights(m, bones):
    P = m.v
    n = m.nv
    E = m.edges()[0]
    W = {}
    nw, s, S = chain_weights(P, _chain(bones, ["neck_01", "neck_02", "head"]), [0.025, 0.03])
    add_into(W, nw)
    # jaw field: below the plane through the TMJ axis and the mouth corners
    tmj_l, tmj_r = H["jaw_pivot_l"], H["jaw_pivot_r"]
    mc = H["mouth"] + v(0.0252, 0.019, -0.001)   # left mouth corner (approx)
    # plane normal: perpendicular to TMJ axis, containing the TMJ-mouth corner direction
    axis = nrm(tmj_l - tmj_r)
    d_front = nrm((mc - tmj_l) - np.dot(mc - tmj_l, axis) * axis)
    nplane = nrm(np.cross(axis, d_front))
    if nplane[2] < 0:
        nplane = -nplane
    sd = (P - tmj_l) @ nplane               # >0 above the plane
    front = (P[:, 1] < 0.030)
    wj = smoothstep((0.006 - sd) / 0.016) * front
    # fade the jaw toward the neck under the chin and behind the ramus
    wj *= smoothstep((P[:, 2] - 1.505) / 0.05)
    wj *= smoothstep((0.030 - P[:, 1]) / 0.03)
    # explicit lip / mouth rings
    for g, val in m.groups.items():
        if g.startswith(("lip_L", "mouth_in")) and g.endswith("_lo"):
            wj = np.where(val, 1.0, wj)
        if g.startswith(("lip_L", "mouth_in")) and g.endswith("_up"):
            wj = np.where(val, 0.0, wj)
    if "mouth_corner" in m.groups:
        wj = np.where(m.groups["mouth_corner"], 0.5, wj)
    bag = m.groups.get("mouth_bag", np.zeros(n, bool))
    # bag cap / back: floor half follows the jaw
    rel_z = P[:, 2] - H["mouth"][2]
    wj = np.where(bag & ~np.any([m.groups.get(f"mouth_in{k}_up", np.zeros(n, bool)) for k in range(1, 6)], axis=0)
                  & ~np.any([m.groups.get(f"mouth_in{k}_lo", np.zeros(n, bool)) for k in range(1, 6)], axis=0),
                  smoothstep((0.004 - rel_z) / 0.012), wj)
    for nm in list(W):
        W[nm] = W[nm] * (1 - wj)
    W["jaw"] = wj
    # smooth outside the explicit lip rings
    locked = np.zeros(n, bool)
    for g, val in m.groups.items():
        if g.startswith(("lip_L", "mouth_in", "lid_", "mouth_bag", "canthus")):
            locked |= val
    face_region = (P[:, 1] < 0.03) & (P[:, 2] < 1.66)
    W = smooth_weights(W, E, n, iters=6, lam=0.5, mask=face_region, locked=locked)
    # eyelids
    for sdn in ("l", "r"):
        for part, bone in (("up", "lid_upper_"), ("lo", "lid_lower_")):
            vals = {"A": 1.0, "B": 1.0, "C": 0.92, "D": 0.62, "E": 0.25, "F": 0.06}
            for ring, wv in vals.items():
                g = m.groups.get(f"lid_{ring}_{part}_{sdn}")
                if g is None:
                    continue
                idx = np.nonzero(g)[0]
                # falloff toward the canthi using the lateral position along the lid
                c = H["eye_" + sdn]
                rel = P[idx] - c
                ang = np.arctan2(np.abs(rel[:, 0]) * np.sign(rel[:, 0]) * (1 if sdn == "l" else -1), -rel[:, 1])
                a_mid = np.radians(-6.0)
                span = np.radians(70.0)
                q = np.clip((ang - a_mid) / span, -1, 1)
                fall = (1 - np.abs(q) ** 2.2)
                wl = np.clip(wv * fall, 0, 1)
                for nm in list(W):
                    W[nm][idx] = W[nm][idx] * (1 - wl)
                W[bone + sdn] = W.get(bone + sdn, np.zeros(n))
                W[bone + sdn][idx] += wl
    return normalize_weights(W, n)


def hand_weights(m, bones, side, fingers_groups=True):
    """Organic (left) hand weights: finger chains, palm metacarpals, wrist twist."""
    import mr_hand
    P = m.v
    n = m.nv
    E = m.edges()[0]
    W = {}
    sd = side
    hand_head, hand_tail = bones[f"hand_{sd}"]
    # palm & wrist: blend twist -> hand
    ch = [(f"lowerarm_twist_01_{sd}", bones[f"lowerarm_twist_01_{sd}"][0], bones[f"lowerarm_twist_01_{sd}"][1]),
          (f"hand_{sd}", hand_head, hand_tail)]
    pw, s, S = chain_weights(P, ch, [0.018])
    base_mask = np.ones(n, bool)
    for f in mr_hand.FINGERS + ["thumb"]:
        base_mask &= ~m.groups.get("finger_" + f, np.zeros(n, bool))
    add_into(W, pw, mask=base_mask)
    # metacarpal share on the distal palm (cupping)
    R, o = mr_hand.hand_frame("l")
    local = (P - (J["hand_l"] if sd == "l" else J["hand_r"])) @ R if sd == "l" else None
    if sd == "l":
        x, y = local[:, 0], local[:, 1]
        centers = {f: mr_hand.CARPAL[f][1] * 0.35 + mr_hand.MCP[f][1] * 0.65 for f in mr_hand.FINGERS}
        share = smoothstep((x - 0.030) / 0.055) * base_mask
        dens = []
        for f in mr_hand.FINGERS:
            dens.append(np.exp(-0.5 * ((y - centers[f]) / 0.010) ** 2))
        dens = np.array(dens)
        dens /= np.maximum(dens.sum(0), 1e-6)
        h = np.asarray(W[f"hand_{sd}"], float).copy()
        taken = np.zeros(n)
        for k, f in enumerate(mr_hand.FINGERS):
            wmc = share * dens[k] * 0.85 * h
            taken += wmc
            W[f"{f}_metacarpal_{sd}"] = W.get(f"{f}_metacarpal_{sd}", 0) + wmc
        W[f"hand_{sd}"] = h - taken
    # fingers
    for f in mr_hand.FINGERS:
        g = m.groups.get("finger_" + f)
        names = [f"{f}_metacarpal_{sd}", f"{f}_01_{sd}", f"{f}_02_{sd}", f"{f}_03_{sd}"]
        fw, s, S = chain_weights(P, _chain(bones, names), [0.0085, 0.0055, 0.0045])
        add_into(W, fw, mask=g)
    g = m.groups.get("finger_thumb")
    names = [f"hand_{sd}", f"thumb_01_{sd}", f"thumb_02_{sd}", f"thumb_03_{sd}"]
    ch = _chain(bones, names)
    fw, s, S = chain_weights(P, ch, [0.012, 0.0075, 0.0055])
    add_into(W, fw, mask=g)
    # thumb base region on the palm: blend toward thumb_01
    tb = bones[f"thumb_01_{sd}"]
    t, tc, d = closest_on_segment(P, tb[0], tb[1])
    wth = np.exp(-0.5 * (d / 0.011) ** 2) * smoothstep((0.6 - t) / 0.6) * base_mask * 0.6
    for nm in list(W):
        W[nm] = W[nm] * (1 - wth)
    W[f"thumb_01_{sd}"] = W.get(f"thumb_01_{sd}", 0) + wth
    W = smooth_weights(W, E, n, iters=3, lam=0.4, mask=base_mask)
    return normalize_weights(W, n)


def boot_weights(m, bones, side):
    P = m.v
    n = m.nv
    names = [f"calf_{side}", f"foot_{side}", f"ball_{side}"]
    ch = _chain(bones, names)
    fw, s, S = chain_weights(P, ch, [0.035, 0.022])
    W = dict(fw)
    # heel and sole behind the ankle: foot
    A = J[f"foot_{side}"]
    heel = (P[:, 2] < 0.105) & (P[:, 1] > A[1] - 0.02)
    wf = smoothstep((0.125 - P[:, 2]) / 0.05)
    for nm in list(W):
        W[nm] = np.where(heel, W[nm] * (1 - wf), W[nm])
    W[f"foot_{side}"] = np.where(heel, W[f"foot_{side}"] + wf, W[f"foot_{side}"])
    E = m.edges()[0]
    W = smooth_weights(W, E, n, iters=4, lam=0.4)
    return normalize_weights(W, n)


def rigid_weights(m, bone):
    return {bone: np.ones(m.nv)}

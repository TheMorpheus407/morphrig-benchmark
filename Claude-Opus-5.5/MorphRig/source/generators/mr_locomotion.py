"""MorphRig direction-aware gait generator (walk / run / sprint cycles, in place).

Travel direction psi is relative to body facing (0 = forward, 90 = left strafe,
180 = backward, -90 = right strafe).  The legs step along the travel direction,
the pelvis yaws partially toward it (forward-leg mode) or away from it (backward
mode), and the spine counter-rotates so the chest keeps facing forward.

During stance a foot slides backward in root space at exactly the travel speed,
so it is stationary in world space when the controller moves the capsule at the
nominal speed.  Heel/toe roll uses the rig's foot-roll property.
"""
import math
import numpy as np
from mr_anim import DEG, rot_z
from mr_clip import Clip
from mr_poses import ANKLE, ankle
from mr_params import J, FOOT_DIR_L

GAITS = {
    # speed m/s, cycle frames, stance fraction, stance width, lift, bob, drop, sway, hip yaw, lean,
    # arm swing, elbow, hand, cadence notes
    "walk": dict(v=1.5, N=31, d=0.60, w=0.185, lift=0.075, bob=0.024, drop=0.018, sway=0.018, hyaw=6.0,
                 lean=3.0, swing=17.0, elbow=(8.0, 24.0), hand="relaxed", heel=0.55, toe=0.62, kick=0.0, swing_pitch=8.0,
                 flex0=-8.0, abd=-28.0, abd_side=6.0),
    "run": dict(v=4.0, N=21, d=0.35, w=0.13, lift=0.19, bob=0.045, drop=0.055, sway=0.010, hyaw=10.0,
                lean=10.0, swing=34.0, elbow=(82.0, 95.0), hand="loose_fist", heel=0.35, toe=0.9, kick=0.18, swing_pitch=30.0,
                flex0=6.0, abd=-36.0, abd_side=4.0),
    "sprint": dict(v=6.5, N=19, d=0.29, w=0.11, lift=0.27, bob=0.050, drop=0.070, sway=0.006, hyaw=12.0,
                   lean=19.0, swing=55.0, elbow=(78.0, 100.0), hand="knife", heel=0.1, toe=1.0, kick=0.28, swing_pitch=38.0,
                   flex0=6.0, abd=-32.0, abd_side=0.0),
}


def smooth(u):
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def hermite(p0, p1, m0, m1, t):
    t2, t3 = t * t, t * t * t
    return (2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * p1 + (t3 - t2) * m1


LEG_LEN = None


def leg_length():
    global LEG_LEN
    if LEG_LEN is None:
        LEG_LEN = (np.linalg.norm(J["calf_l"] - J["thigh_l"]) + np.linalg.norm(J["foot_l"] - J["calf_l"]))
    return LEG_LEN


def rolled_ankle(side, ctrl_pos, yaw_deg, roll):
    """Ankle position after the rig's heel / ball / toe-tip roll (matches mr_rig drivers)."""
    a0 = ANKLE[side]
    fd = FOOT_DIR_L.copy()
    if side == "r":
        fd[0] *= -1
    R = rot_z(yaw_deg * DEG)
    fdw = R @ fd
    lat = np.cross(fdw, np.array([0, 0, 1.0]))
    heel = np.array([a0[0], a0[1], 0.0]) - 0.075 * fd
    ball = J["ball_" + side].copy()
    ball[2] = 0.0                  # roll pivot on the floor contact (matches mch_ballpivot)
    toe = J["toe_end_" + side].copy()
    toe[2] = 0.0
    off = ctrl_pos - a0          # translation of the flat foot control
    ank = ctrl_pos.copy()

    def rot_about(p, pivot, ang):
        from mr_anim import axis_angle
        Rm = axis_angle(lat, ang)
        return pivot + Rm @ (p - pivot)
    hp = R @ (heel - a0) + ctrl_pos
    bp = R @ (ball - a0) + ctrl_pos
    tp = R @ (toe - a0) + ctrl_pos
    if roll < 0:
        ank = rot_about(ank, hp, (-roll * 0.60))
    else:
        tb = min(roll, 0.5) * 1.30
        tt = max(roll - 0.5, 0.0) * 1.40
        if tt > 0:
            ank = rot_about(ank, tp, -tt)
            bp = rot_about(bp, tp, -tt)
        ank = rot_about(ank, bp, -tb)
    return ank


def gait_params(psi):
    """hip yaw (deg) and leg mode for a travel direction."""
    a = ((psi + 180) % 360) - 180
    if abs(a) <= 90.0 + 1e-6:
        return 0.5 * a if abs(a) < 60 else math.copysign(45.0, a), "fwd"
    back = a - math.copysign(180.0, a)          # e.g. 135 -> -45
    return 0.5 * back, "back"


def foot_state(side, phase, g, psi, hip_yaw, mode, L, T):
    """Returns ankle position (root space), foot yaw, roll value, pitch, toe."""
    d = g["d"]
    off = 0.0 if side == "l" else 0.5
    ph = (phase - off) % 1.0
    dirv = rot_z(psi * DEG) @ np.array([0, -1.0, 0])
    sgn = 1.0 if side == "l" else -1.0
    lat = rot_z(hip_yaw * DEG) @ np.array([sgn * g["w"] / 2.0, 0.0, 0.0])
    # sideways component reduces heel/toe action
    fwdness = abs(math.cos((psi - hip_yaw) * DEG))
    base = np.array([0.0, 0.0, ANKLE[side][2]]) + lat
    # small backward offset of the stance centre for walking (feet land slightly ahead of hips)
    if ph < d:
        u = ph / d
        s = (0.5 - u) * d * L
        h = 0.0
        swing = False
    else:
        u = (ph - d) / (1 - d)
        v_rel = -L / T                            # m/s relative to body during stance
        m = v_rel * (1 - d) * T                   # tangent scaled to swing duration
        s = hermite(-d * L / 2, d * L / 2, m * 0.55, m * 0.35, u)
        # lift: early peak (heel kick) for runs
        uk = u ** (1.0 - g["kick"]) if g["kick"] > 0 else u
        h = g["lift"] * math.sin(math.pi * uk) ** 1.3
        swing = True
    pos = base + dirv * s + np.array([0, 0, h])
    foot_yaw = hip_yaw + (4.0 if side == "l" else -4.0)
    roll = 0.0
    pitch = 0.0
    toe = 0.0
    if not swing:
        u = ph / d
        if mode == "fwd":
            # heel strike -> flat -> heel off -> toe off (foot roll property)
            hs = g["heel"] * fwdness
            if u < 0.14:
                roll = -hs * (1 - smooth(u / 0.14))
            elif u > 0.55:
                roll = g["toe"] * fwdness * smooth((u - 0.55) / 0.45) * 0.62 + 0.0
        else:
            if u < 0.18:
                roll = 0.35 * fwdness * (1 - smooth(u / 0.18))
            elif u > 0.65:
                roll = -0.45 * fwdness * smooth((u - 0.65) / 0.35)
    else:
        # continue the stance-end roll (toe/ball pivot keeps the toe tip above ground while lifting),
        # then pre-set the stance-start roll before contact; mid-swing plantarflexion in between
        if mode == "fwd":
            r_end = g["toe"] * fwdness * 0.62
            r_start = -g["heel"] * fwdness
        else:
            r_end = -0.45 * fwdness
            r_start = 0.35 * fwdness
        roll = r_end * (1 - smooth(u / 0.35)) + r_start * smooth((u - 0.72) / 0.28)
        sp = g.get("swing_pitch", 10.0) * fwdness
        pitch = -sp * math.sin(math.pi * min(1.0, u / 0.8)) * (1 if mode == "fwd" else -0.5)
        toe = 10.0 * (1 - smooth(u / 0.3))
    return pos, foot_yaw, roll, pitch, toe


def gait_clip(cid, kind, psi, frames=None, speed=None):
    g = dict(GAITS[kind])
    N = frames or g["N"]
    v = speed or g["v"]
    T = N / 30.0
    L = v * T
    hip_yaw, mode = gait_params(psi)
    clip = Clip(cid, N, loop=True, form="loop", root="in_place", speed=v * 100.0,
                layer="full_body", entry="locomotion", exit="locomotion",
                notes=f"{kind} cycle, travel {psi:+.0f} deg rel. facing, stride {L:.2f} m")
    clip.dense = True
    d = g["d"]
    fwd = mode == "fwd"
    dirv = rot_z(psi * DEG) @ np.array([0, -1.0, 0])
    side_amt = abs(math.sin(psi * DEG))
    poses = []
    for f in range(N + 1):
        ph = (f / N) % 1.0
        P = {}
        # pelvis height: two bobs per cycle
        if kind == "walk":
            z = -g["drop"] - g["bob"] * (0.5 + 0.5 * math.cos(4 * math.pi * ph))
        else:
            z = -g["drop"] - g["bob"] * (0.5 + 0.5 * math.cos(4 * math.pi * (ph - d / 2)))
        sway = g["sway"] * math.cos(2 * math.pi * (ph - d / 2))
        latv = rot_z(hip_yaw * DEG) @ np.array([sway, 0, 0])
        # forward surge: slight deceleration after contact
        surge = 0.006 * math.sin(4 * math.pi * ph) * (1 if kind == "walk" else 0.5)
        cog = latv + dirv * surge + np.array([0, 0, z])
        lean_dir = g["lean"] * (1.0 - 0.6 * side_amt) * (1 if fwd else -0.5)
        P["cog"] = tuple(cog)
        side_lean = -math.sin(psi * DEG) * g["lean"] * 0.35
        P["cog_rot"] = (lean_dir, 0.0, side_lean)
        yaw_osc = -g["hyaw"] * math.cos(2 * math.pi * ph) * (1 if fwd else -1)
        hroll = 3.0 * math.sin(4 * math.pi * ph) * (1 if kind == "walk" else 0.6)
        P["hips"] = (2.0 if kind != "walk" else 0.0, hip_yaw + yaw_osc, hroll)
        P["spine"] = (1.0 + (2.0 if kind != "walk" else 0.0), -hip_yaw * 0.88 - yaw_osc * 1.15, -hroll * 0.6)
        P["neck"] = (-lean_dir * 0.4, -hip_yaw * 0.12 + yaw_osc * 0.2, 0.0)
        P["head"] = (-lean_dir * 0.35, 0.0, 0.0)
        for side in "lr":
            pos, fy, roll, pitch, toe = foot_state(side, ph, g, psi, hip_yaw, mode, L, T)
            P["foot_" + side] = {"pos": tuple(pos), "yaw": fy, "pitch": pitch, "heelroll": roll, "toe": toe}
            # arms swing opposite to legs (facing frame)
            sg = -1.0 if side == "l" else 1.0
            sw = g["swing"] * (1.0 - 0.55 * side_amt) * (1 if fwd else 0.8)
            # swing biased backward so the hands pass beside (not across) the swinging thighs
            flex = sg * sw * math.cos(2 * math.pi * ph) + g["flex0"]
            e0, e1 = g["elbow"]
            elbow = e0 + (e1 - e0) * (0.5 + 0.5 * math.cos(2 * math.pi * ph) * -sg)
            abd = g["abd"] + g["abd_side"] * side_amt     # more clearance when legs cross/abduct
            P["arm_" + side] = {"fk": (flex, abd, 8.0), "elbow": elbow,
                                "wrist": (10.0 if kind == "walk" else 4.0, 0.0, 15.0)}
            P["clav_" + side] = (-2.0 + 1.5 * math.cos(2 * math.pi * ph) * sg, 3.0 * math.cos(2 * math.pi * ph) * sg)
            P["hand_" + side] = g["hand"]
        P["look"] = (0.0, -2.0)
        P["blade"] = 0.0
        P["cell"] = 0
        P["beacon"] = {"parent": 0}
        poses.append(P)
    # reach feasibility: lower the pelvis where a leg would over-extend
    Lleg = leg_length() * 0.985
    torso_rest = np.array([0.0, 0.02, 0.99])
    zfix = np.zeros(len(poses))
    for i, P in enumerate(poses):
        need = 0.0
        cog = np.array(P["cog"])
        hy = P["hips"][1]
        for side in "lr":
            hip = torso_rest + cog + rot_z(hy * DEG) @ (J["thigh_" + side] - torso_rest)
            ft = P["foot_" + side]
            ank = rolled_ankle(side, np.array(ft["pos"]), ft["yaw"], ft["heelroll"])
            dxy = np.linalg.norm((hip - ank)[:2])
            if dxy >= Lleg:
                zmax = hip[2] - 0.05
            else:
                zmax = ank[2] + math.sqrt(Lleg * Lleg - dxy * dxy)
            need = max(need, hip[2] - zmax)
        zfix[i] = need
    # smooth the correction (periodic) while keeping it >= the requirement
    for _ in range(6):
        sm = zfix.copy()
        for i in range(len(zfix)):
            sm[i] = max(zfix[i], 0.25 * zfix[i - 1] + 0.5 * zfix[i] + 0.25 * zfix[(i + 1) % len(zfix)])
        zfix = sm
    zfix[-1] = zfix[0] = max(zfix[0], zfix[-1])
    for i, P in enumerate(poses):
        c = list(P["cog"])
        c[2] -= zfix[i]
        P["cog"] = tuple(c)
        clip.key(i, P, "LINEAR")
    clip.extra["reach_drop_max_cm"] = round(float(zfix.max()) * 100, 2)
    clip.marker(0, "foot_l_down")
    clip.marker(round(N * 0.5), "foot_r_down")
    clip.marker(round(N * d), "foot_l_up")
    clip.marker(round(N * (0.5 + d)) % N, "foot_r_up")
    import math as _m
    clip.contacts = {"l": [(0, int(_m.floor(N * d)) - 1)],
                     "r": [(int(_m.ceil(N * 0.5)) + 1, min(N, int(_m.floor(N * (0.5 + d))) - 1))]}
    clip.extra["travel_dir"] = [float(x) for x in dirv]
    clip.extra["stride_m"] = L
    return clip

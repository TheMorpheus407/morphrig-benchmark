"""MorphRig locomotion transitions, jumps/falls/landings, root-motion dashes and blink.

In-place clips with travel (start/stop/pivot) plan foot plants in WORLD space and
convert them to root space with the nominal capsule displacement x(t), so a planted
foot is stationary in the world when the controller follows the documented speed
curve (exported as clip.extra['speed_curve_cms']).  Dashes are root motion: the root
bone translates 2 m and planted feet are counter-animated in root space.
"""
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, DEG, rot_z
import mr_poses as P
import mr_locomotion as LOC
from mr_author import Steps, smooth, smoother, Prober, settle
from clips_common import clip, expr, breathing, blinks, sway_noise, tremble, face_mix

A = P.ankle
C = P.COMBAT
RX = P.RELAXED
WALK = LOC.GAITS["walk"]


def gait_pose(kind, psi, phase):
    """Semantic pose of the generated gait at a phase (full dense clip evaluated once and cached)."""
    key = (kind, psi)
    if key not in _GAIT_CACHE:
        c = LOC.gait_clip("tmp", kind, psi)
        _GAIT_CACHE[key] = (c.frames, [k[1] for k in c.keys])
    n, poses = _GAIT_CACHE[key]
    f = int(round(phase * n)) % n
    return poses[f]


_GAIT_CACHE = {}


def shift_pose_feet(pose, dx=0.0, dy=0.0):
    p = dict(pose)
    for s in "lr":
        f = dict(p["foot_" + s])
        x, y, z = f["pos"]
        f["pos"] = (x + dx, y + dy, z)
        p["foot_" + s] = f
    return p


def travel_curve(nframes, v_of_t):
    """x(f) along the travel axis (m) by integrating v(t) (m/s) at 30 fps (trapezoid)."""
    x = np.zeros(nframes + 1)
    for f in range(1, nframes + 1):
        x[f] = x[f - 1] + 0.5 * (v_of_t((f - 1) / 30.0) + v_of_t(f / 30.0)) / 30.0
    return x


# ================================================================ start / stop
@clip("start_f")
def start_f(R):
    N = 28
    c = Clip("start_f", N, form="one_shot", root="in_place", speed=150.0, layer="full_body",
             entry="idle_relaxed|idle_combat", exit="walk_f@0.516",
             notes="accelerate from stand: lean, left step, right step into the walk cycle (exit phase 0.516)")
    T12 = 12 / 30.0

    def v(t):
        if t <= T12:
            return 1.5 * smooth(t / T12) ** 1.2
        return 1.5
    x = travel_curve(N, v)
    # world plants (travel along -Y): the root-space y = world_y + x(f)
    st = Steps(N)
    L0, R0 = A("l", 0.012), A("r", -0.012)
    g_end = gait_pose("walk", 0.0, 16 / 31.0)       # exit pose (phase 0.516)
    yl_end = g_end["foot_l"]["pos"][1]               # left foot root-space y at exit (behind)
    yr_end = g_end["foot_r"]["pos"][1]
    yl_world = yl_end - x[N]
    # the steps land at the walk cycle's width / yaw, so the hand-over to walk_f at the end needs no foot shift
    xl, xr = g_end["foot_l"]["pos"][0], g_end["foot_r"]["pos"][0]
    yawl, yawr = g_end["foot_l"].get("yaw", 4.0), g_end["foot_r"].get("yaw", -4.0)
    st.plant("l", 0, 3, (L0[0], L0[1]), 4.0, roll_out=0.25).plant("l", 12, None, (xl, yl_world), yawl, lift=0.07,
                                                                   roll_in=-0.35)
    st.plant("r", 0, 15, (R0[0], R0[1]), -4.0, roll_out=0.45).plant("r", 28, None, (xr, yr_end - x[N]), yawr,
                                                                    lift=0.075, roll_in=-0.3)
    base = merge(RX, {"face": expr("focus", 0.3)})
    for f in range(N + 1):
        w = smooth(f / 12.0)
        ph = max(0.0, (f - 12) / 31.0)
        g = gait_pose("walk", 0.0, ph if f >= 12 else 0.0)
        pose = {}
        # upper body blends from idle to the gait pose; lean forward during acceleration
        for k in ("cog_rot", "hips", "spine", "neck", "head", "clav_l", "clav_r"):
            a = np.asarray(base.get(k, (0, 0, 0)), float)
            b = np.asarray(g[k], float)
            pose[k] = tuple(a * (1 - w) + b * w)
        lean = 7.0 * math.sin(math.pi * min(1.0, f / 20.0))
        pose["cog_rot"] = (pose["cog_rot"][0] + lean, pose["cog_rot"][1], pose["cog_rot"][2])
        cg = np.asarray(base["cog"]) * (1 - w) + np.asarray(g["cog"]) * w
        cg[1] -= 0.03 * math.sin(math.pi * min(1.0, f / 16.0))    # body leads the feet
        pose["cog"] = tuple(cg)
        for s in "lr":
            fa = np.asarray(base["arm_" + s]["fk"]) * (1 - w) + np.asarray(g["arm_" + s]["fk"]) * w
            el = base["arm_" + s]["elbow"] * (1 - w) + g["arm_" + s]["elbow"] * w
            pose["arm_" + s] = {"fk": tuple(fa), "elbow": el, "wrist": g["arm_" + s]["wrist"]}
            pose["hand_" + s] = "relaxed"
            ft = st.foot_at(s, f)
            px, py, pz = ft["pos"]
            ft["pos"] = (px, py + x[f], pz)
            pose["foot_" + s] = ft
        if f >= N - 2:
            for s in "lr":
                pose["foot_" + s] = dict(g["foot_" + s])
        pose["look"] = (0.0, -2.0)
        pose["face"] = base["face"]
        c.key(f, merge(base, pose), "LINEAR")
    c.dense = True
    c.markers += [(3, "foot_l_up"), (12, "foot_l_down"), (15, "foot_r_up"), (27, "foot_r_down")]
    c.contacts = {"l": [(0, 2), (13, N)], "r": [(0, 14)]}
    c.extra["speed_curve_cms"] = [round(v(f / 30.0) * 100, 1) for f in range(N + 1)]
    c.extra["travel_dir"] = [0.0, -1.0, 0.0]
    c.extra["exit_phase"] = 16 / 31.0
    c.extra["world_travel_m"] = float(x[N])
    return c


@clip("stop_f")
def stop_f(R):
    N = 26
    c = Clip("stop_f", N, form="one_shot", root="in_place", speed=150.0, layer="full_body",
             entry="walk_f@0.0|run_f", exit="idle_combat",
             notes="brake from walk (enter at left heel strike): right foot plants beside, weight settles back")
    g0 = gait_pose("walk", 0.0, 0.0)
    # braking distance chosen so the planted left foot ends exactly in the combat stance
    need = C["foot_l"]["pos"][1] - g0["foot_l"]["pos"][1]
    T = 2.0 * need / 1.5

    def v(t):
        return 1.5 * (1 - smooth(min(1.0, t / T)))
    x = travel_curve(N, v)
    st = Steps(N)
    yl0 = g0["foot_l"]["pos"][1]
    yr0 = g0["foot_r"]["pos"][1]
    final = C
    fl = final["foot_l"]["pos"]
    fr = final["foot_r"]["pos"]
    # left foot planted from the heel strike until the end; right foot swings to its combat position
    st.plant("l", 0, None, (g0["foot_l"]["pos"][0], yl0), g0["foot_l"]["yaw"], roll_in=0.0)
    st.plant("r", 0, 3, (g0["foot_r"]["pos"][0], yr0), g0["foot_r"]["yaw"], roll_out=0.45)
    st.plant("r", 14, None, (fr[0], fr[1] - x[N]), final["foot_r"]["yaw"], lift=0.07, roll_in=-0.2)
    for f in range(N + 1):
        w = smooth(f / float(N))
        pose = {}
        for k in ("cog_rot", "hips", "spine", "neck", "head", "clav_l", "clav_r"):
            a = np.asarray(g0[k], float)
            b = np.asarray(final.get(k, (0, 0, 0)), float)
            pose[k] = tuple(a * (1 - w) + b * w)
        brake = -8.0 * math.sin(math.pi * min(1.0, f / 16.0))
        pose["cog_rot"] = (pose["cog_rot"][0] + brake, pose["cog_rot"][1], pose["cog_rot"][2])
        cg = np.asarray(g0["cog"]) * (1 - w) + np.asarray(final["cog"]) * w
        cg[1] += 0.035 * math.sin(math.pi * min(1.0, f / 14.0))
        pose["cog"] = tuple(cg)
        for s in "lr":
            fa = np.asarray(g0["arm_" + s]["fk"]) * (1 - w) + np.asarray(final["arm_" + s]["fk"]) * w
            el = g0["arm_" + s]["elbow"] * (1 - w) + final["arm_" + s]["elbow"] * w
            pose["arm_" + s] = {"fk": tuple(fa), "elbow": el, "wrist": final["arm_" + s]["wrist"]}
            pose["hand_" + s] = "relaxed" if f < 14 else "loose_fist"
            ft = st.foot_at(s, f)
            px, py, pz = ft["pos"]
            ft["pos"] = (px, py + x[f], pz)
            pose["foot_" + s] = ft
        pose["face"] = expr("focus", 0.3 * w)
        pose["look"] = (0.0, -2.0)
        c.key(f, merge(final, pose), "LINEAR")
    c.dense = True
    c.markers += [(0, "foot_l_down"), (3, "foot_r_up"), (14, "foot_r_down")]
    c.contacts = {"l": [(1, N)], "r": [(0, 2), (15, N)]}
    c.extra["speed_curve_cms"] = [round(v(f / 30.0) * 100, 1) for f in range(N + 1)]
    c.extra["travel_dir"] = [0.0, -1.0, 0.0]
    c.extra["world_travel_m"] = float(x[N])
    return c


# ================================================================ turns in place (actor rotates)
def _turn(cid, yaw_total, N):
    c = Clip(cid, N, form="one_shot", root="in_place", layer="full_body", entry="idle_combat|idle_relaxed",
             exit="idle_combat", notes=f"turn {yaw_total:+.0f} deg in place with two steps; the body rotates "
                                        f"relative to the root, the controller rotates the actor by the same "
                                        f"amount (turn_yaw curve) and counter-rotates the mesh")
    sg = 1.0 if yaw_total > 0 else -1.0
    lead = "l" if sg > 0 else "r"          # turning left: left foot opens first
    trail = "r" if lead == "l" else "l"
    base = C
    st = Steps(N)
    Rf = lambda xy, a: tuple(rot_z(a * DEG)[:2, :2] @ np.asarray(xy, float))
    lp = base["foot_" + lead]["pos"]
    tp = base["foot_" + trail]["pos"]
    ly = base["foot_" + lead]["yaw"]
    ty = base["foot_" + trail]["yaw"]
    mid_a = yaw_total * 0.55
    st.plant(lead, 0, 3, lp[:2], ly, roll_out=0.3).plant(lead, 11, None, Rf(lp[:2], mid_a), ly + mid_a, lift=0.05)
    # the lead foot's final spot is re-planted at full rotation near the end
    st.plants[lead][-1]["up"] = N - 9
    st.plant(lead, N - 2, None, Rf(lp[:2], yaw_total), ly + yaw_total, lift=0.04)
    st.plant(trail, 0, 9, tp[:2], ty, roll_out=0.4).plant(trail, 19, None, Rf(tp[:2], yaw_total), ty + yaw_total,
                                                          lift=0.06)
    yaws = []
    for f in range(N + 1):
        u = smoother(min(1.0, (f - 1) / (N - 4.0)))
        body = yaw_total * u
        head_lead = yaw_total * smoother(min(1.0, f / (N * 0.55)))
        yaws.append(body)
        pose = merge(base, {
            "cog_rot": (base["cog_rot"][0], base["cog_rot"][1] + body, base["cog_rot"][2]),
            "cog": tuple(rot_z(body * DEG) @ np.asarray(base["cog"], float) + np.array([0, 0, -0.012 * math.sin(math.pi * f / N)])),
            "neck": (base["neck"][0], base["neck"][1] + (head_lead - body) * 0.5, 0),
            "head": (base["head"][0], base["head"][1] + (head_lead - body) * 0.4, 0),
            "look": (max(-60, min(60, (head_lead - body) * 0.8)), -2)})
        for s in "lr":
            pose["foot_" + s] = st.foot_at(s, f)
        c.key(f, pose, "LINEAR")
    c.dense = True
    c.markers += [(3, f"foot_{lead}_up"), (11, f"foot_{lead}_down"), (9, f"foot_{trail}_up"),
                  (19, f"foot_{trail}_down"), (N - 2, f"foot_{lead}_down")]
    c.contacts = {lead: [(0, 2), (12, N - 10)], trail: [(0, 8), (20, N)]}
    c.extra["turn_yaw_deg"] = [round(y, 3) for y in yaws]
    c.extra["turn_total_deg"] = yaw_total
    return c


@clip("turn_l90")
def turn_l90(R):
    return _turn("turn_l90", 90.0, 26)


@clip("turn_r90")
def turn_r90(R):
    return _turn("turn_r90", -90.0, 26)


# ================================================================ pivots (moving 180 change)
def _pivot(cid, sign, N=30):
    """Run forward, brake step, pivot step turned 180 toward `sign`, push off into run_f (rotated)."""
    yaw_total = 180.0 * sign
    c = Clip(cid, N, form="one_shot", root="in_place", speed=400.0, layer="full_body", entry="run_f@0.0",
             exit="run_f@0.5 (rotated 180)", notes=f"moving direction change: pivot foot plants, brake step, "
                                                  f"pivot step {yaw_total:+.0f} deg, push off; world velocity "
                                                  "reverses (speed curve), actor yaw follows the turn_yaw curve")
    T = N / 30.0
    vmax = 4.0

    def vel(t):          # along the ORIGINAL forward axis (-Y): +vmax ... -vmax
        return vmax * math.cos(math.pi * min(1.0, t / T))
    x = travel_curve(N, vel)
    g0 = gait_pose("run", 0.0, 0.0)
    g1 = gait_pose("run", 0.0, 0.5)
    piv = "l" if sign > 0 else "r"
    oth = "r" if piv == "l" else "l"
    sgl = 1.0 if piv == "l" else -1.0
    Rt = rot_z(yaw_total * DEG)[:2, :2]

    def world(root_xy, f):
        return (root_xy[0], root_xy[1] - x[f])
    st = Steps(N)
    # pivot foot: heel strike in front (braking), lifts once the body has turned, re-plants in the new direction
    p0 = g0["foot_" + piv]["pos"]
    st.plant(piv, 0, 12, world((p0[0], p0[1]), 0), g0["foot_" + piv]["yaw"], roll_in=0.0, roll_out=0.3)
    # other foot: lifts behind, brake step beside the pivot foot turned 70 deg toward the turn
    o0 = g0["foot_" + oth]["pos"]
    st.plant(oth, 0, 2, world((o0[0], o0[1]), 0), g0["foot_" + oth]["yaw"], roll_out=0.5)
    brake_xy = (p0[0] - sgl * 0.26, p0[1] + 0.05)
    st.plant(oth, 9, 16, world(brake_xy, 0) if False else (brake_xy[0], brake_xy[1] - x[0]),
             g0["foot_" + oth]["yaw"] + 0.4 * yaw_total, lift=0.10, roll_in=-0.1, roll_out=0.4)
    # pivot foot lands facing the new direction (rotated gait stance at phase 0), other foot ends at phase 0.5
    n0 = Rt @ np.asarray(gait_pose("run", 0.0, 0.0)["foot_" + piv]["pos"][:2])
    st.plant(piv, 19, 25, (n0[0], n0[1] - x[19]), g0["foot_" + piv]["yaw"] + yaw_total, lift=0.10,
             roll_in=-0.2, roll_out=0.5)
    e1 = Rt @ np.asarray(g1["foot_" + oth]["pos"][:2])
    st.plant(oth, N, None, (e1[0], e1[1] - x[N]), g1["foot_" + oth]["yaw"] + yaw_total, lift=0.12, roll_in=-0.3)
    yaws = []
    for f in range(N + 1):
        u = smoother(min(1.0, max(0.0, (f - 2) / 20.0)))
        body = yaw_total * u
        yaws.append(body)
        w = smoother(min(1.0, max(0.0, (f - 16) / 12.0)))
        pose = {}
        for k in ("hips", "spine", "neck", "head", "clav_l", "clav_r"):
            a = np.asarray(g0[k], float)
            b = np.asarray(g1[k], float)
            pose[k] = tuple(a * (1 - w) + b * w)
        brake = -12.0 * math.sin(math.pi * min(1.0, f / 18.0))
        cr = np.asarray(g0["cog_rot"]) * (1 - w) + np.asarray(g1["cog_rot"]) * w
        pose["cog_rot"] = (cr[0] + brake, cr[1] + body, cr[2] + 6.0 * sgl * math.sin(math.pi * min(1.0, f / 22.0)))
        cg = np.asarray(g0["cog"]) * (1 - w) + np.asarray(g1["cog"]) * w
        cg[2] -= 0.07 * math.sin(math.pi * min(1.0, f / 24.0))
        pose["cog"] = tuple(rot_z(body * DEG) @ cg)
        for s_ in "lr":
            fa = np.asarray(g0["arm_" + s_]["fk"]) * (1 - w) + np.asarray(g1["arm_" + s_]["fk"]) * w
            el = g0["arm_" + s_]["elbow"] * (1 - w) + g1["arm_" + s_]["elbow"] * w
            if 3 < f < 20:
                fa = fa + np.array([0.0, 18.0 * math.sin(math.pi * (f - 3) / 17.0), 0.0])
            pose["arm_" + s_] = {"fk": tuple(fa), "elbow": el, "wrist": g1["arm_" + s_]["wrist"]}
            pose["hand_" + s_] = "loose_fist"
            ft = st.foot_at(s_, f)
            px, py, pz = ft["pos"]
            ft["pos"] = (px, py + x[f], pz)
            pose["foot_" + s_] = ft
        pose["face"] = expr("focus", 0.6)
        pose["look"] = (max(-60, min(60, 0.3 * (yaw_total * smoother(min(1.0, f / 14.0)) - body))), -2)
        c.key(f, merge(C, pose), "LINEAR")
    c.dense = True
    c.markers += [(0, f"foot_{piv}_down"), (2, f"foot_{oth}_up"), (9, f"foot_{oth}_down"), (12, f"foot_{piv}_up"),
                  (16, f"foot_{oth}_up"), (19, f"foot_{piv}_down"), (25, f"foot_{piv}_up"), (N, f"foot_{oth}_down")]
    c.contacts = {piv: [(1, 11), (20, 24)], oth: [(10, 15)]}
    c.extra["speed_curve_cms"] = [round(vel(f / 30.0) * 100, 1) for f in range(N + 1)]
    c.extra["travel_dir"] = [0.0, -1.0, 0.0]
    c.extra["turn_yaw_deg"] = [round(y, 3) for y in yaws]
    c.extra["turn_total_deg"] = yaw_total
    return c


@clip("pivot_l180")
def pivot_l180(R):
    return _pivot("pivot_l180", 1.0)


@clip("pivot_r180")
def pivot_r180(R):
    return _pivot("pivot_r180", -1.0)


# ================================================================ jump / fall / land
AIR = merge(C, {
    "cog": (0.0, 0.0, 0.06), "cog_rot": (6.0, -4.0, 0.0), "spine": (4, 4, 0), "neck": (-4, 0, 0),
    "leg_l": {"fk": (30.0, 6.0, 0.0), "knee": 42.0, "ankle": (-24.0, 0.0)},
    "leg_r": {"fk": (8.0, 6.0, 0.0), "knee": 36.0, "ankle": (-30.0, 0.0)},
    "arm_l": {"fk": (40.0, 30.0, 10.0), "elbow": 50.0}, "arm_r": {"fk": (30.0, 36.0, 0.0), "elbow": 56.0},
    "hand_l": "open", "hand_r": "loose_fist", "face": expr("focus", 0.6), "look": (0, -6)})
FALL = merge(C, {
    "cog": (0.0, 0.03, 0.05), "cog_rot": (-6.0, 0.0, 0.0), "spine": (-8, 0, 0), "neck": (14, 0, 0),
    "head": (14, 0, 0),
    "leg_l": {"fk": (16.0, 16.0, 0.0), "knee": 30.0, "ankle": (-20.0, 0.0)},
    "leg_r": {"fk": (-6.0, 14.0, 0.0), "knee": 44.0, "ankle": (-30.0, 0.0)},
    "arm_l": {"fk": (20.0, 88.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (26.0, 92.0, 0.0), "elbow": 36.0},
    "hand_l": "spread", "hand_r": "spread", "face": expr("surprise", 0.6), "jaw": 5.0, "look": (0, -30)})


@clip("jump_start")
def jump_start(R):
    c = Clip("jump_start", 16, form="one_shot", layer="full_body", entry="idle|locomotion", exit="jump_air",
             notes="anticipation crouch with arm back-swing, explosive extension; feet leave the floor at f12 "
                   "(controller launches the capsule on the 'takeoff' event)")
    crouch = merge(C, {"cog": (0.0, 0.03, -0.20), "cog_rot": (18.0, -8.0, 0.0), "spine": (14, 4, 0),
                       "arm_l": {"fk": (-30.0, -20.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (-30.0, -20.0, 0.0), "elbow": 36.0},
                       "hand_l": "open", "face": expr("focus", 0.9)})
    for s in "lr":
        crouch["foot_" + s] = dict(C["foot_" + s])
    ext = merge(C, {"cog": (0.0, -0.01, 0.05), "cog_rot": (4.0, -6.0, 0.0), "spine": (-4, 4, 0),
                    "arm_l": {"fk": (110.0, 10.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (100.0, 10.0, 0.0), "elbow": 40.0},
                    "hand_l": "open", "face": expr("focus", 1.0), "jaw": 3.0})
    ext["foot_l"] = dict(C["foot_l"], heelroll=0.95)
    ext["foot_r"] = dict(C["foot_r"], heelroll=0.95)
    c.key(0, C).key(7, crouch).key(11, ext).key(16, AIR)
    c.markers += [(7, "jump_load"), (12, "takeoff")]
    c.extra["no_floor_fix"] = True
    return c


@clip("jump_air")
def jump_air(R):
    c = Clip("jump_air", 24, loop=True, form="loop", layer="full_body", entry="jump_start", exit="jump_land|fall",
             notes="controllable airborne posture: gentle limb drift, looks toward the landing")
    b = merge(AIR, {"arm_l": {"fk": (46.0, 34.0, 10.0), "elbow": 44.0}, "arm_r": {"fk": (26.0, 40.0, 0.0), "elbow": 60.0},
                    "leg_l": {"fk": (26.0, 6.0, 0.0), "knee": 46.0, "ankle": (-20.0, 0.0)}})
    c.key(0, AIR).key(12, b).key(24, AIR)
    c.extra["no_floor_fix"] = True
    return c


@clip("jump_land")
def jump_land(R):
    c = Clip("jump_land", 20, form="one_shot", layer="full_body", entry="jump_air", exit="idle|locomotion",
             notes="soft landing: toes first, knees absorb, recover to the stance")
    touch = merge(C, {"cog": (0.0, 0.0, -0.05), "cog_rot": (6.0, -8.0, 0.0),
                      "arm_l": {"fk": (40.0, 26.0, 0.0), "elbow": 50.0}, "arm_r": {"fk": (30.0, 30.0, 0.0), "elbow": 50.0}})
    touch["foot_l"] = dict(C["foot_l"], heelroll=0.4)
    touch["foot_r"] = dict(C["foot_r"], heelroll=0.4)
    comp = merge(C, {"cog": (0.0, 0.04, -0.21), "cog_rot": (20.0, -10.0, 0.0), "spine": (12, 6, 0),
                     "arm_l": {"fk": (50.0, 10.0, 10.0), "elbow": 60.0}, "arm_r": {"fk": (40.0, 0.0, 0.0), "elbow": 70.0},
                     "face": expr("focus", 0.7), "jaw": 2.0})
    c.key(0, touch).key(5, comp).key(12, merge(comp, {"cog": (0.0, 0.03, -0.14), "cog_rot": (12.0, -12.0, 0.0)}))
    c.key(20, C)
    c.markers += [(0, "land_contact"), (0, "foot_l_down"), (1, "foot_r_down")]
    return c


@clip("fall")
def fall(R):
    c = Clip("fall", 30, loop=True, form="loop", layer="full_body", entry="jump_air|knockup_air|any",
             exit="jump_land|land_heavy", notes="long-fall posture: arms up and wide, legs apart, looks down")
    b = merge(FALL, {"arm_l": {"fk": (26.0, 96.0, 10.0), "elbow": 24.0}, "arm_r": {"fk": (16.0, 84.0, -6.0), "elbow": 44.0},
                     "leg_l": {"fk": (4.0, 18.0, 0.0), "knee": 40.0, "ankle": (-26.0, 0.0)},
                     "leg_r": {"fk": (12.0, 14.0, 0.0), "knee": 30.0, "ankle": (-20.0, 0.0)}})
    c.key(0, FALL).key(15, b).key(30, FALL)
    c.layers += [sway_noise(31, 1.5, ("spine_02.rot", "c_upperarm_fk_l.rot", "c_upperarm_fk_r.rot"), (1, 2, 3))]
    c.extra["no_floor_fix"] = True
    return c


@clip("land_heavy")
def land_heavy(R):
    c = Clip("land_heavy", 36, form="one_shot", layer="full_body", entry="fall", exit="idle_combat",
             notes="hard landing: deep compression with a left-hand floor touch, heavy recovery")
    pr = Prober(R)
    hit = merge(C, {"cog": (0.0, 0.0, -0.08), "cog_rot": (10.0, -6.0, 0.0),
                    "arm_l": {"fk": (30.0, 60.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (20.0, 60.0, 0.0), "elbow": 30.0}})
    hit["foot_l"] = dict(C["foot_l"], heelroll=0.3)
    hit["foot_r"] = dict(C["foot_r"], heelroll=0.3)
    deep = merge(C, {"cog": (0.0, 0.0, -0.43), "cog_rot": (36.0, -8.0, 0.0), "spine": (20, 4, 0), "neck": (-18, 0, 0),
                     "arm_l": {"ik": (0.26, -0.40, 0.045), "hand_rot": np.stack([np.array([1.0, 0, 0]), np.array([0, -1.0, 0]),
                                                                               np.array([0, 0, 1.0])], 1) @ np.eye(3),
                               "pole": (0.7, -0.2, 0.6)},
                     "arm_r": {"fk": (30.0, 10.0, 0.0), "elbow": 80.0}, "hand_l": "spread",
                     "face": expr("pain", 0.7), "jaw": 5.0})
    rise = merge(C, {"cog": (0.0, 0.02, -0.22), "cog_rot": (18.0, -10.0, 0.0), "spine": (12, 4, 0),
                     "face": expr("focus", 0.7)})
    c.key(0, hit).key(6, deep).key(14, deep).key(26, rise).key(36, C)
    c.markers += [(0, "land_contact"), (6, "hand_l_contact"), (18, "hand_l_release")]
    return c


# ================================================================ dashes (root motion 2 m)
def _dash(cid, psi):
    N = 16
    c = Clip(cid, N, form="one_shot", root="root_motion", layer="full_body", entry="combat|locomotion",
             exit="combat|locomotion", notes=f"ground dash {psi:+.0f} deg: root bone travels 2.0 m (drives the capsule)")
    d = rot_z(psi * DEG) @ np.array([0, -1.0, 0])
    dist = 2.0
    # root displacement profile: fast burst with ease out
    def xr(f):
        u = min(1.0, max(0.0, (f - 2) / 11.0))
        return dist * (1 - (1 - u) ** 2.2)
    X = np.array([xr(f) for f in range(N + 1)])
    base = C
    # lean into the dash direction (in the character frame)
    lean_f = math.cos(psi * DEG)
    lean_s = math.sin(psi * DEG)
    st = Steps(N)
    # world plants: start stance, then both feet re-plant near the end position
    for s in "lr":
        p0 = base["foot_" + s]["pos"]
        st.plant(s, 0, 3 if s == "r" else 5, (p0[0], p0[1]), base["foot_" + s]["yaw"], roll_out=0.6)
        pe = np.asarray(p0[:2]) + d[:2] * dist
        st.plant(s, 11 if s == "r" else 13, None, tuple(pe), base["foot_" + s]["yaw"], lift=0.10, roll_in=-0.2)
    for f in range(N + 1):
        u = X[f] / dist
        crouch = math.sin(math.pi * min(1.0, f / 13.0))
        pose = merge(base, {
            "root": (d[0] * X[f], d[1] * X[f], 0.0, 0.0),
            "cog": (base["cog"][0], base["cog"][1], base["cog"][2] - 0.10 * crouch),
            "cog_rot": (base["cog_rot"][0] + 16 * lean_f * crouch, base["cog_rot"][1], base["cog_rot"][2] - 14 * lean_s * crouch),
            "arm_l": {"fk": (20.0 - 30 * lean_f * crouch, -20.0 + 20 * crouch, 10.0), "elbow": 70.0},
            "arm_r": {"fk": (20.0 - 30 * lean_f * crouch, -20.0 + 20 * crouch, 0.0), "elbow": 80.0},
            "face": expr("focus", 0.9), "look": (0, -4)})
        for s in "lr":
            ft = st.foot_at(s, f)
            px, py, pz = ft["pos"]
            # root space = world - root displacement
            ft["pos"] = (px - d[0] * X[f], py - d[1] * X[f], pz)
            pose["foot_" + s] = ft
        c.key(f, pose, "LINEAR")
    c.dense = True
    c.markers += [(2, "dash_start"), (3, "foot_r_up"), (5, "foot_l_up"), (11, "foot_r_down"), (13, "foot_l_down"),
                  (14, "dash_end")]
    c.contacts = {"l": [(0, 4), (14, N)], "r": [(0, 2), (12, N)]}
    c.extra["root_travel_m"] = dist
    c.extra["dash_dir"] = [float(v) for v in d]
    return c


@clip("dash_f")
def dash_f(R):
    return _dash("dash_f", 0.0)


@clip("dash_b")
def dash_b(R):
    return _dash("dash_b", 180.0)


@clip("dash_l")
def dash_l(R):
    return _dash("dash_l", 90.0)


@clip("dash_r")
def dash_r(R):
    return _dash("dash_r", -90.0)


# ================================================================ blink (teleport is an event)
@clip("blink_out")
def blink_out(R):
    c = Clip("blink_out", 12, form="one_shot", layer="full_body", entry="combat|locomotion", exit="blink_in",
             notes="compress and vanish: gather, crouch, burst; actor teleport happens on 'blink_teleport' (no baked travel)")
    gather = merge(C, {"cog": (0.0, 0.02, -0.16), "cog_rot": (14.0, -8.0, 0.0), "spine": (12, 4, 0),
                       "arm_l": {"fk": (60.0, -10.0, 50.0), "elbow": 120.0}, "arm_r": {"fk": (60.0, -10.0, 50.0), "elbow": 120.0},
                       "hand_l": "fist", "hand_r": "fist", "face": expr("focus", 1.0), "look": (0, -10)})
    burst = merge(C, {"cog": (0.0, -0.02, -0.06), "cog_rot": (-4.0, -8.0, 0.0), "spine": (-6, 4, 0),
                      "arm_l": {"fk": (20.0, 40.0, -20.0), "elbow": 20.0}, "arm_r": {"fk": (20.0, 40.0, -20.0), "elbow": 20.0},
                      "hand_l": "spread", "hand_r": "spread", "face": expr("surprise", 0.3)})
    c.key(0, C).key(6, gather).key(10, burst).key(12, burst)
    c.markers += [(4, "blink_charge"), (11, "blink_teleport")]
    return c


@clip("blink_in")
def blink_in(R):
    c = Clip("blink_in", 14, form="one_shot", layer="full_body", entry="blink_out", exit="combat",
             notes="reappear compressed, plant and settle at the destination")
    appear = merge(C, {"cog": (0.0, 0.02, -0.18), "cog_rot": (16.0, -8.0, 0.0), "spine": (14, 4, 0),
                       "arm_l": {"fk": (60.0, -10.0, 50.0), "elbow": 120.0}, "arm_r": {"fk": (60.0, -10.0, 50.0), "elbow": 120.0},
                       "hand_l": "fist", "hand_r": "fist", "face": expr("focus", 1.0)})
    c.key(0, appear).key(5, merge(appear, {"cog": (0.0, 0.01, -0.12)})).key(14, C)
    c.markers += [(0, "blink_appear"), (0, "foot_l_down"), (0, "foot_r_down")]
    return c

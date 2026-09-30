"""MorphRig action clips: melee combo, ranged, reload, casts, channel, charge, deploy, uplink.

Key-pose authoring on the control rig.  Prop contacts (cell, beacon) and forearm
contacts (uplink console, channel support) use the Prober to read the exact
evaluated transforms of the other hand / forearm / holster at the contact frame.
"""
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, rot_z, axis_angle, DEG, to_M4
import mr_poses as P
from mr_author import Prober, hand_for_prop, hand_rot, aim_arm, nrm, smooth
from mr_face_list import EXPRESSIONS
from clips_common import clip, expr, breathing, blinks, sway_noise, tremble, face_mix

MELEE_READY = merge(P.COMBAT, {"blade": 1.0, "hand_r": "fist",
                               "arm_r": {"fk": (40.0, -24.0, -14.0), "elbow": 78.0, "wrist": (6.0, 0.0, 0.0)}})


# ================================================================ melee
@clip("melee_1")
def melee_1(R):
    c = Clip("melee_1", 22, form="one_shot", layer="full_body", entry="combat", exit="combat|melee_2",
             notes="diagonal forearm-blade slash high-right to low-left")
    f_focus = expr("focus", 0.8)
    windup = merge(P.COMBAT, {
        "cog": (-0.025, 0.035, -0.085), "cog_rot": (2.0, -32.0, -4.0), "spine": (-4, -16, -6), "neck": (-4, 12, 2),
        "arm_r": {"fk": (18.0, 92.0, -45.0), "elbow": 62.0, "wrist": (-18.0, 0.0, 0.0)},
        "arm_l": {"fk": (62.0, -18.0, 20.0), "elbow": 76.0, "wrist": (0.0, 0.0, 20.0)},
        "clav_r": (12, -4), "blade": 1.0, "hand_r": "fist", "face": f_focus, "look": (4, 0)})
    windup["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.0)
    slash = merge(P.COMBAT, {
        "cog": (0.02, -0.02, -0.105), "cog_rot": (10.0, 2.0, 2.0), "spine": (10, 18, 4), "neck": (-6, -8, 0),
        "arm_r": {"fk": (72.0, 34.0, 18.0), "elbow": 30.0, "wrist": (6.0, 0.0, 0.0)},
        "arm_l": {"fk": (30.0, -22.0, 10.0), "elbow": 92.0, "wrist": (0.0, 0.0, 15.0)},
        "blade": 1.0, "hand_r": "fist", "face": expr("anger", 0.7), "jaw": 4.0, "look": (-4, -8)})
    slash["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.25)
    follow = merge(slash, {
        "cog": (0.03, -0.03, -0.12), "cog_rot": (16.0, 12.0, 4.0), "spine": (16, 30, 6),
        "arm_r": {"fk": (58.0, -26.0, 42.0), "elbow": 18.0, "wrist": (12.0, 0.0, 0.0)},
        "arm_l": {"fk": (14.0, -26.0, 0.0), "elbow": 96.0}, "face": expr("anger", 0.5), "jaw": 2.0})
    settle = merge(follow, {"cog": (0.015, -0.01, -0.10), "cog_rot": (10.0, 4.0, 2.0), "spine": (8, 18, 3),
                            "arm_r": {"fk": (52.0, -18.0, 28.0), "elbow": 36.0}, "face": f_focus, "jaw": 0.0})
    settle["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.0)
    end = merge(MELEE_READY, {"face": f_focus})
    c.key(0, P.COMBAT).key(5, windup).key(9, slash).key(12, follow).key(16, settle).key(22, end)
    c.markers += [(2, "blade_out"), (8, "hit_start"), (11, "hit_end"), (14, "recovery_start"), (14, "combo_open"),
                  (21, "combo_close")]
    c.layers += [blinks([19])]
    return c


@clip("melee_2")
def melee_2(R):
    c = Clip("melee_2", 22, form="one_shot", layer="full_body", entry="combat|melee_1", exit="combat|melee_3",
             notes="reverse (backhand) slash left-to-right with weight shift onto the front foot then back")
    prep = merge(MELEE_READY, {
        "cog": (0.03, -0.02, -0.10), "cog_rot": (8.0, 22.0, 3.0), "spine": (6, 24, 4), "neck": (-4, -16, 0),
        "arm_r": {"fk": (64.0, 14.0, 64.0), "elbow": 118.0, "wrist": (10.0, 0.0, -20.0)},
        "arm_l": {"fk": (20.0, -30.0, 0.0), "elbow": 80.0},
        "face": expr("focus", 0.9), "look": (-6, -4)})
    prep["foot_l"] = dict(P.COMBAT["foot_l"], heelroll=0.0)
    prep["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.35)
    cut = merge(MELEE_READY, {
        "cog": (-0.01, 0.01, -0.11), "cog_rot": (6.0, -12.0, -4.0), "spine": (6, -14, -6), "neck": (-4, 10, 0),
        "arm_r": {"fk": (70.0, 58.0, -18.0), "elbow": 14.0, "wrist": (0.0, 0.0, 10.0)},
        "arm_l": {"fk": (40.0, -20.0, 20.0), "elbow": 96.0},
        "face": expr("anger", 0.8), "jaw": 5.0, "look": (6, -4)})
    follow = merge(cut, {"cog": (-0.03, 0.03, -0.10), "cog_rot": (2.0, -30.0, -6.0), "spine": (2, -24, -8),
                         "arm_r": {"fk": (46.0, 84.0, -40.0), "elbow": 10.0}, "face": expr("anger", 0.5),
                         "jaw": 2.0})
    end = merge(MELEE_READY, {"face": expr("focus", 0.8)})
    c.key(0, MELEE_READY).key(6, prep).key(11, cut).key(15, follow).key(22, end)
    c.markers += [(10, "hit_start"), (13, "hit_end"), (16, "recovery_start"), (16, "combo_open"), (21, "combo_close")]
    return c


@clip("melee_3")
def melee_3(R):
    c = Clip("melee_3", 34, form="one_shot", layer="full_body", entry="combat|melee_2", exit="combat",
             notes="committed overhead finisher with lunge step and blade retraction")
    A = P.ankle
    rise = merge(MELEE_READY, {
        "cog": (0.0, 0.05, -0.02), "cog_rot": (-6.0, -18.0, 0.0), "spine": (-12, 6, 0), "neck": (-6, 6, 0),
        "head": (-8, 0, 0),
        "arm_r": {"fk": (150.0, 16.0, -10.0), "elbow": 92.0, "wrist": (-20.0, 0.0, 0.0)},
        "arm_l": {"fk": (70.0, 0.0, 0.0), "elbow": 30.0, "wrist": (-20.0, 0.0, 0.0)}, "hand_l": "open",
        "face": expr("anger", 0.9), "jaw": 3.0, "look": (0, 8)})
    rise["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.3)
    lunge_foot = {"pos": A("l", 0.05, -0.39, 0.0), "yaw": 4.0}
    strike = merge(MELEE_READY, {
        "cog": (0.02, -0.16, -0.21), "cog_rot": (26.0, -6.0, 0.0), "spine": (18, 6, 0), "neck": (-14, 0, 0),
        "arm_r": {"fk": (64.0, -4.0, 0.0), "elbow": 8.0, "wrist": (10.0, 0.0, 0.0)},
        "arm_l": {"fk": (-10.0, -20.0, 0.0), "elbow": 60.0}, "hand_l": "loose_fist",
        "foot_l": lunge_foot, "face": expr("anger", 1.0), "jaw": 12.0, "look": (0, -30)})
    strike["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.55)
    impact = merge(strike, {"cog": (0.02, -0.18, -0.25), "cog_rot": (30.0, -6.0, 0.0),
                            "arm_r": {"fk": (50.0, -6.0, 0.0), "elbow": 6.0}, "jaw": 6.0})
    back = merge(MELEE_READY, {"cog": (0.0, -0.05, -0.12), "cog_rot": (10.0, -10.0, 0.0),
                               "foot_l": {"pos": A("l", 0.04, -0.26, 0.012), "yaw": 5.0},
                               "arm_r": {"fk": (40.0, -20.0, -10.0), "elbow": 60.0}, "face": expr("focus", 0.7)})
    end = merge(P.COMBAT, {"blade": 0.0, "face": expr("focus", 0.5)})
    mid_step = merge(rise, {"foot_l": {"pos": A("l", 0.045, -0.26, 0.05), "yaw": 5.0, "pitch": 8.0}})
    c.key(0, MELEE_READY).key(8, rise).key(10, mid_step).key(13, strike).key(17, impact)
    c.key(23, back).key(34, end)
    c.markers += [(12, "hit_start"), (16, "hit_end"), (21, "recovery_start"), (13, "foot_l_down"), (28, "foot_l_down"),
                  (30, "blade_in")]
    c.layers += [blinks([26])]
    return c


# ================================================================ ranged
def aim_pose(R, yaw=0.0, pitch=0.0, base=None, prober=None):
    """Upper body turned toward (yaw, pitch); right forearm exactly along the aim ray."""
    base = base or P.COMBAT
    pr = prober or Prober(R)
    ytw = yaw * 0.62
    pose = merge(base, {
        "cog_rot": (base["cog_rot"][0] - pitch * 0.08, base["cog_rot"][1] + yaw * 0.12 + 10.0, 0.0),
        "spine": (4 - pitch * 0.25, 4 + ytw, 0.0), "neck": (-4 - pitch * 0.25, (yaw - ytw) * 0.5, 0),
        "head": (-pitch * 0.25, (yaw - ytw) * 0.35, 0), "clav_r": (3 + max(0, pitch) * 0.12, 8),
        "arm_l": {"fk": (46.0, -26.0, 25.0), "elbow": 98.0, "wrist": (0.0, 0.0, 20.0)},
        "hand_r": "claw", "look": (yaw * 0.25, pitch * 0.35), "face": expr("focus", 0.9)})
    W = pr.world(pose, ["upperarm_r"])
    S = W["upperarm_r"][:3, 3]
    d = rot_z(yaw * DEG) @ axis_angle(np.array([1.0, 0, 0]), pitch * DEG) @ np.array([0, -1.0, 0])
    hand, elbow, pole = aim_arm(S, d, "r")
    back = nrm(np.cross(np.cross(d, np.array([0, 0, 1.0])), d))
    Rh = hand_rot(d, back) @ axis_angle(np.array([1.0, 0, 0]), 0.0)
    # flex the hand down a little so the dorsal emitter line is clear
    Rh = axis_angle(np.cross(d, back), 18 * DEG) @ Rh
    pose["arm_r"] = {"ik": tuple(hand), "hand_rot": Rh, "pole": tuple(pole)}
    pose["_aim"] = dict(dir=d, shoulder=S, hand=hand)
    return pose


@clip("ranged_fire")
def ranged_fire(R):
    c = Clip("ranged_fire", 12, form="one_shot", layer="upper_body", entry="any_locomotion", exit="previous",
             notes="wrist-emitter single shot with recoil; upper-body layer (legs untouched)")
    pr = Prober(R)
    aim = aim_pose(R, 0, 0, prober=pr)
    d = aim["_aim"]["dir"]
    hand = np.array(aim["arm_r"]["ik"])
    rec = merge(aim, {"clav_r": (6, 2), "spine": (1, 4, 0), "face": expr("anger", 0.6)})
    Rh = axis_angle(np.cross(d, np.array([0, 0, 1.0])), -10 * DEG) @ aim["arm_r"]["hand_rot"]
    rec["arm_r"] = dict(aim["arm_r"], ik=tuple(hand - d * 0.035 + np.array([0, 0, 0.035])), hand_rot=Rh)
    c.key(0, aim).key(2, aim).key(4, rec).key(12, aim)
    c.markers += [(2, "muzzle_fire")]
    return c


@clip("ranged_burst")
def ranged_burst(R):
    c = Clip("ranged_burst", 22, form="one_shot", layer="upper_body", entry="any_locomotion", exit="previous",
             notes="three-shot burst; three distinct muzzle events")
    pr = Prober(R)
    aim = aim_pose(R, 0, 0, prober=pr)
    d = aim["_aim"]["dir"]
    hand = np.array(aim["arm_r"]["ik"])
    c.key(0, aim)
    for i, f in enumerate((2, 8, 14)):
        amt = 1.0 - 0.15 * i
        rec = merge(aim, {"clav_r": (5, 3), "face": expr("anger", 0.5 + 0.1 * i)})
        Rh = axis_angle(np.cross(d, np.array([0, 0, 1.0])), -8 * amt * DEG) @ aim["arm_r"]["hand_rot"]
        rec["arm_r"] = dict(aim["arm_r"], ik=tuple(hand - d * 0.028 * amt + np.array([0, 0, 0.028 * amt])), hand_rot=Rh)
        c.key(f, aim).key(f + 2, rec)
        c.markers.append((f, f"muzzle_fire_{i + 1}"))
    c.key(22, aim)
    return c


# ================================================================ reload (cell manipulation)
@clip("reload")
def reload(R):
    c = Clip("reload", 56, form="one_shot", layer="upper_body", entry="combat|locomotion", exit="previous",
             notes="left hand pulls the power cell from the cyber-forearm cradle, recharges it on the hip pad, "
                   "flips and re-seats it; cell parent switches at grab/seat frames")
    pr = Prober(R)
    base = merge(P.COMBAT, {"face": expr("focus", 0.6)})
    # right forearm raised horizontally in front of the chest (IK), palm down
    rpos = np.array([-0.075, -0.33, 1.13])
    fwd = nrm(np.array([0.85, -0.35, 0.0]))            # forearm pointing to the left-front
    Rr = hand_rot(fwd, np.array([0, 0, 1.0]))
    arm_r = {"ik": tuple(rpos), "hand_rot": Rr, "pole": (-0.55, 0.05, 1.05)}
    hold = merge(base, {"arm_r": arm_r, "look": (8, -32), "head": (14, 6, 0), "neck": (8, 4, 0), "spine": (6, 14, 0),
                        "hand_r": "loose_fist"})
    # cell world transform while seated (probe)
    W = pr.world(hold, ["prop_cell", "hand_l"])
    cell_seated = W["prop_cell"]
    ax = nrm(cell_seated[:3, 1])       # cell long axis (bone Y)
    up = nrm(cell_seated[:3, 2])       # cradle 'top'

    def cell_at(offset_along=0.0, offset_up=0.0, spin_deg=0.0, pos=None, M=None):
        if M is None:
            M = cell_seated.copy()
        else:
            M = M.copy()
        if pos is not None:
            M[:3, 3] = pos
        M[:3, 3] = M[:3, 3] + ax * offset_along + up * offset_up
        if spin_deg:
            Rs = axis_angle(M[:3, 1], spin_deg * DEG)
            M[:3, :3] = Rs @ M[:3, :3]
        return M

    def lh(M, shape="grip_cell", blend=1.0):
        Hm = hand_for_prop(M, "cell")
        pole = Hm[:3, 3] + np.array([0.35, 0.25, -0.25])
        return {"ik": tuple(Hm[:3, 3]), "hand_rot": Hm[:3, :3], "pole": tuple(pole), "blend": blend}

    approach = merge(hold, {"arm_l": lh(cell_at(0.0, 0.06)), "hand_l": "open"})
    grab = merge(hold, {"arm_l": lh(cell_at()), "hand_l": "grip_cell"})
    pulled = merge(hold, {"arm_l": lh(cell_at(-0.07, 0.03)), "hand_l": "grip_cell", "cell": 1})
    lifted = merge(hold, {"arm_l": lh(cell_at(-0.05, 0.14, 40)), "hand_l": "grip_cell", "cell": 1,
                          "look": (18, -20)})
    # hip charger pad (front-left of the belt, see mr_costume.charger_frame), cell vertical,
    # cradle side facing away from the pad
    import mr_costume
    pad_face, pad_n = mr_costume.charger_frame()
    pad = pad_face + pad_n * 0.004
    Mpad = np.eye(4)
    Yc = np.array([0, 0, -1.0])
    Mpad[:3, :3] = np.stack([np.cross(Yc, pad_n), Yc, pad_n], 1)
    Mpad[:3, 3] = pad
    tap = merge(base, {"arm_r": arm_r, "arm_l": lh(Mpad), "hand_l": "grip_cell", "cell": 1, "look": (30, -38),
                       "head": (18, 20, 0), "spine": (10, 22, 4), "cog": (0.02, 0.0, -0.09)})
    tap_up = merge(tap, {"arm_l": lh(cell_at(pos=pad + np.array([0.02, -0.02, 0.06]), M=Mpad)), "cell": 1})
    flipped = cell_at(-0.05, 0.12, 180)
    carry = merge(hold, {"arm_l": lh(flipped), "hand_l": "grip_cell", "cell": 1, "look": (10, -30)})
    align = merge(hold, {"arm_l": lh(cell_at(-0.02, 0.04, 180)), "hand_l": "grip_cell", "cell": 1})
    seat = merge(hold, {"arm_l": lh(cell_at(0.0, 0.0, 180)), "hand_l": "grip_cell", "cell": 1})
    # after seating, the cell (spun 180 about its own axis) sits in the cradle; the rig's cradle space has the
    # original orientation, so the release pose uses the unflipped cradle transform (visually identical cell)
    seat_rel = merge(hold, {"arm_l": lh(cell_at()), "hand_l": "grip_cell", "cell": 0})
    release = merge(hold, {"arm_l": lh(cell_at(0.0, 0.07)), "hand_l": "open", "cell": 0})
    end = merge(base, {})
    c.key(0, base).key(8, hold).key(12, approach).key(15, grab, "CONSTANT").key(16, grab)
    c.key(22, pulled).key(26, lifted).key(31, tap).key(33, tap_up).key(38, carry).key(42, align)
    c.key(45, seat, "CONSTANT").key(46, seat_rel).key(50, release).key(56, end)
    c.markers += [(15, "cell_grab"), (22, "cell_out"), (31, "cell_charge"), (45, "cell_seated"), (47, "reload_handoff")]
    c.extra["contacts"] = {"cell_in_hand": [16, 45]}
    return c


# ================================================================ casts
@clip("cast_directional")
def cast_directional(R):
    c = Clip("cast_directional", 26, form="one_shot", layer="upper_body", entry="combat|locomotion",
             exit="previous", notes="left palm gathers at the right shoulder then thrusts toward the target")
    gather = merge(P.COMBAT, {"cog": (-0.02, 0.03, -0.10), "cog_rot": (4.0, -28.0, 0.0), "spine": (2, -14, -4),
                              "arm_l": {"fk": (46.0, -6.0, 64.0), "elbow": 128.0, "wrist": (20.0, 0.0, 30.0)},
                              "hand_l": "claw", "face": expr("focus", 1.0), "look": (6, 0)})
    thrust = merge(P.COMBAT, {"cog": (0.02, -0.04, -0.09), "cog_rot": (8.0, 16.0, 2.0), "spine": (6, 18, 2),
                              "neck": (-6, -10, 0),
                              "arm_l": {"fk": (86.0, 12.0, 0.0), "elbow": 6.0, "wrist": (-62.0, 0.0, 0.0)},
                              "hand_l": "spread", "face": expr("anger", 0.6), "jaw": 6.0, "look": (-4, 0)})
    thrust["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.3)
    hold = merge(thrust, {"cog": (0.02, -0.035, -0.095), "arm_l": {"fk": (82.0, 8.0, 0.0), "elbow": 12.0}, "jaw": 2.0})
    c.key(0, P.COMBAT).key(8, gather).key(12, thrust).key(17, hold).key(26, P.COMBAT)
    c.markers += [(4, "cast_gather"), (12, "cast_release")]
    return c


@clip("cast_ground")
def cast_ground(R):
    c = Clip("cast_ground", 32, form="one_shot", layer="full_body", entry="combat", exit="combat",
             notes="ground-targeted slam 2 m ahead with look-down")
    raise_ = merge(P.COMBAT, {"cog": (0.0, 0.02, -0.03), "cog_rot": (-2.0, -6.0, 0.0), "spine": (-6, 6, 0),
                              "arm_l": {"fk": (150.0, 20.0, 0.0), "elbow": 24.0, "wrist": (-20.0, 0.0, 0.0)},
                              "hand_l": "spread", "look": (0, -26), "head": (12, 0, 0),
                              "face": expr("focus", 1.0)})
    slam = merge(P.COMBAT, {"cog": (0.01, -0.05, -0.19), "cog_rot": (22.0, 4.0, 0.0), "spine": (16, 6, 0),
                            "neck": (6, 0, 0), "head": (16, 0, 0),
                            "arm_l": {"fk": (52.0, -2.0, 0.0), "elbow": 4.0, "wrist": (-50.0, 0.0, 0.0)},
                            "hand_l": "spread", "look": (0, -40), "face": expr("anger", 0.8), "jaw": 8.0})
    slam["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.2)
    hold = merge(slam, {"cog": (0.01, -0.045, -0.17), "jaw": 2.0})
    c.key(0, P.COMBAT).key(10, raise_).key(16, slam).key(22, hold).key(32, P.COMBAT)
    c.markers += [(6, "cast_gather"), (16, "cast_release")]
    c.extra["target_offset_cm"] = [0, 200, 0]
    return c


@clip("cast_self")
def cast_self(R):
    c = Clip("cast_self", 26, form="one_shot", layer="full_body", entry="combat", exit="combat",
             notes="defensive self-centred pulse: arms cross, then burst outward")
    cross = merge(P.COMBAT, {"cog": (0.0, 0.02, -0.14), "cog_rot": (10.0, -10.0, 0.0), "spine": (14, 6, 0),
                             "neck": (10, 0, 0),
                             "arm_l": {"fk": (82.0, -4.0, 60.0), "elbow": 124.0, "wrist": (10.0, 0.0, 10.0)},
                             "arm_r": {"fk": (86.0, -6.0, 60.0), "elbow": 122.0, "wrist": (10.0, 0.0, 10.0)},
                             "hand_l": "fist", "hand_r": "fist", "face": expr("focus", 1.0), "look": (0, -20)})
    burst = merge(P.COMBAT, {"cog": (0.0, 0.0, -0.05), "cog_rot": (-4.0, -10.0, 0.0), "spine": (-10, 6, 0),
                             "neck": (-8, 0, 0), "head": (-6, 0, 0),
                             "arm_l": {"fk": (18.0, 40.0, -20.0), "elbow": 20.0, "wrist": (-30.0, 0.0, 0.0)},
                             "arm_r": {"fk": (18.0, 40.0, -20.0), "elbow": 20.0, "wrist": (-30.0, 0.0, 0.0)},
                             "hand_l": "spread", "hand_r": "spread", "face": expr("surprise", 0.3), "jaw": 5.0,
                             "look": (0, 6)})
    c.key(0, P.COMBAT).key(8, cross).key(12, burst).key(17, burst).key(26, P.COMBAT)
    c.markers += [(4, "cast_gather"), (12, "cast_release")]
    return c


# ================================================================ channel
CHANNEL_BASE = merge(P.COMBAT, {
    "cog": (0.0, 0.0, -0.11), "cog_rot": (6.0, -8.0, 0.0), "spine": (2, 8, 0), "neck": (-2, 0, 0),
    "foot_l": {"pos": P.ankle("l", 0.05, -0.19, 0.0), "yaw": 6.0},
    "foot_r": {"pos": P.ankle("r", -0.06, 0.19, 0.0), "yaw": -30.0},
    "arm_l": {"fk": (86.0, 6.0, 0.0), "elbow": 8.0, "wrist": (-64.0, 0.0, 0.0)}, "hand_l": "spread",
    "face": expr("focus", 1.0), "look": (0, 0)})


def channel_pose(R, pr, extra=None):
    pose = merge(CHANNEL_BASE, extra or {})
    W = pr.world(pose, ["lowerarm_l", "hand_l"])
    e = W["lowerarm_l"][:3, 3]
    w = W["hand_l"][:3, 3]
    grip_pt = e + 0.62 * (w - e)
    fa = nrm(w - e)
    # right hand wraps the left forearm from below/side
    Rr = hand_rot(nrm(np.cross(fa, np.array([0, 0, 1.0])) * 1.0 + np.array([0, 0, 0.3])), nrm(-fa))
    pose["arm_r"] = {"ik": tuple(grip_pt + np.array([-0.02, 0.01, -0.045])), "hand_rot": Rr,
                     "pole": tuple(grip_pt + np.array([-0.45, 0.25, -0.2]))}
    pose["hand_r"] = "grip_cell"
    return pose


@clip("channel_start")
def channel_start(R):
    c = Clip("channel_start", 16, form="one_shot", layer="full_body", entry="combat", exit="channel_loop",
             notes="brace and raise the left palm, right hand supports the left forearm")
    pr = Prober(R)
    ch = channel_pose(R, pr)
    mid = merge(P.COMBAT, {"cog": (0.0, 0.01, -0.10), "arm_l": {"fk": (60.0, -6.0, 10.0), "elbow": 50.0},
                           "face": expr("focus", 0.8)})
    c.key(0, P.COMBAT).key(7, mid).key(16, ch)
    c.markers += [(10, "foot_l_down"), (16, "channel_begin")]
    return c


@clip("channel_loop")
def channel_loop(R):
    c = Clip("channel_loop", 40, loop=True, form="loop", layer="full_body", entry="channel_start",
             exit="channel_end|channel_interrupt", notes="sustained beam; restrained pulses and breathing")
    pr = Prober(R)
    a = channel_pose(R, pr)
    b = channel_pose(R, pr, {"cog": (0.0, 0.012, -0.115), "cog_rot": (4.0, -8.0, 0.0), "spine": (0, 8, 0)})
    c.key(0, a).key(20, b).key(40, a)
    c.layers += [tremble(["c_upperarm_fk_l.rot", "spine_03.rot"], 0.5, seed=3), breathing(0.8), blinks([27])]
    c.markers += [(0, "channel_pulse"), (20, "channel_pulse")]
    return c


@clip("channel_end")
def channel_end(R):
    c = Clip("channel_end", 18, form="one_shot", layer="full_body", entry="channel_loop", exit="combat",
             notes="deliberate successful release: final push then relax")
    pr = Prober(R)
    a = channel_pose(R, pr)
    push = channel_pose(R, pr, {"cog": (0.0, -0.03, -0.10), "cog_rot": (8.0, -6.0, 0.0),
                                "arm_l": {"fk": (88.0, 8.0, 0.0), "elbow": 2.0, "wrist": (-70.0, 0.0, 0.0)}})
    c.key(0, a).key(5, push).key(18, merge(P.COMBAT, {"face": expr("joy", 0.2)}))
    c.markers += [(6, "channel_complete")]
    return c


@clip("channel_interrupt")
def channel_interrupt(R):
    c = Clip("channel_interrupt", 14, form="one_shot", layer="full_body", entry="channel_loop|channel_start",
             exit="combat", notes="forced interruption: jolt back, arms thrown up, stagger step")
    pr = Prober(R)
    a = channel_pose(R, pr)
    jolt = merge(CHANNEL_BASE, {"cog": (0.0, 0.06, -0.08), "cog_rot": (-12.0, -8.0, 0.0), "spine": (-14, 4, 0),
                                "neck": (-12, 0, 0), "head": (-10, 0, 0),
                                "arm_l": {"fk": (120.0, 30.0, 0.0), "elbow": 40.0, "wrist": (-10.0, 0.0, 0.0)},
                                "arm_r": {"fk": (30.0, 30.0, 0.0), "elbow": 50.0}, "hand_r": "open",
                                "face": expr("pain", 0.8), "jaw": 9.0, "look": (0, 10)})
    step = merge(jolt, {"cog": (0.0, 0.10, -0.10), "cog_rot": (-4.0, -10.0, 0.0),
                        "foot_l": {"pos": P.ankle("l", 0.04, -0.06, 0.0), "yaw": 6.0}})
    mid = merge(step, {"foot_l": {"pos": P.ankle("l", 0.05, -0.12, 0.05), "yaw": 6.0}})
    c.key(0, a).key(2, jolt).key(5, mid).key(8, step).key(14, merge(P.COMBAT, {"face": expr("pain", 0.3)}))
    c.markers += [(1, "channel_broken"), (8, "foot_l_down")]
    return c


# ================================================================ charge
CHARGE_HOLD = merge(P.COMBAT, {
    "cog": (-0.02, 0.05, -0.13), "cog_rot": (4.0, -38.0, -3.0), "spine": (0, -12, -4), "neck": (-4, 24, 0),
    "arm_r": {"fk": (-34.0, -16.0, 10.0), "elbow": 112.0, "wrist": (0.0, 0.0, 0.0)}, "hand_r": "fist",
    "arm_l": {"fk": (64.0, -4.0, 10.0), "elbow": 36.0, "wrist": (-30.0, 0.0, 0.0)}, "hand_l": "open",
    "clav_r": (-4, -8), "face": expr("anger", 0.8), "jaw": 1.0, "look": (6, 0)})
CHARGE_HOLD["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.0)


@clip("charge_start")
def charge_start(R):
    c = Clip("charge_start", 20, form="one_shot", layer="full_body", entry="combat", exit="charge_hold",
             notes="coil the cyber fist back, accumulate energy")
    mid = merge(P.COMBAT, {"cog": (-0.01, 0.03, -0.11), "cog_rot": (4.0, -26.0, 0.0),
                           "arm_r": {"fk": (0.0, -20.0, 0.0), "elbow": 100.0}, "face": expr("focus", 1.0)})
    c.key(0, P.COMBAT).key(8, mid).key(20, CHARGE_HOLD)
    c.markers += [(4, "charge_begin"), (20, "charge_full")]
    return c


@clip("charge_hold")
def charge_hold(R):
    c = Clip("charge_hold", 30, loop=True, form="loop", layer="full_body", entry="charge_start",
             exit="charge_release|charge_cancel", notes="hold stored charge; trembling fist, breathing")
    b = merge(CHARGE_HOLD, {"cog": (-0.02, 0.052, -0.135), "arm_r": {"fk": (-36.0, -16.0, 12.0), "elbow": 114.0}})
    c.key(0, CHARGE_HOLD).key(15, b).key(30, CHARGE_HOLD)
    c.layers += [tremble(["c_upperarm_fk_r.rot", "c_lowerarm_fk_r.rot"], 0.9, seed=5), breathing(1.3, period=15)]
    return c


@clip("charge_release")
def charge_release(R):
    c = Clip("charge_release", 22, form="one_shot", layer="full_body", entry="charge_hold", exit="combat",
             notes="forceful cyber-fist punch with weight transfer onto the front foot")
    punch = merge(P.COMBAT, {"cog": (0.03, -0.08, -0.12), "cog_rot": (12.0, 22.0, 3.0), "spine": (6, 20, 4),
                             "neck": (-6, -18, 0),
                             "arm_r": {"fk": (86.0, -8.0, -10.0), "elbow": 2.0, "wrist": (4.0, 0.0, 0.0)},
                             "hand_r": "fist", "arm_l": {"fk": (10.0, -24.0, 0.0), "elbow": 104.0},
                             "face": expr("anger", 1.0), "jaw": 10.0, "look": (-4, 0)})
    punch["foot_r"] = dict(P.COMBAT["foot_r"], heelroll=0.6)
    follow = merge(punch, {"cog": (0.03, -0.09, -0.13), "jaw": 4.0,
                           "arm_r": {"fk": (80.0, -10.0, -10.0), "elbow": 8.0}})
    c.key(0, CHARGE_HOLD).key(4, merge(CHARGE_HOLD, {"cog": (-0.025, 0.055, -0.14)})).key(7, punch)
    c.key(12, follow).key(22, P.COMBAT)
    c.markers += [(7, "charge_release"), (8, "hit_start"), (10, "hit_end")]
    return c


@clip("charge_cancel")
def charge_cancel(R):
    c = Clip("charge_cancel", 16, form="one_shot", layer="full_body", entry="charge_hold|charge_start",
             exit="combat", notes="safely vent the stored charge: lower and shake out the arm")
    vent = merge(P.COMBAT, {"cog": (0.0, 0.02, -0.08), "cog_rot": (6.0, -18.0, 0.0),
                            "arm_r": {"fk": (10.0, -34.0, 0.0), "elbow": 30.0, "wrist": (20.0, 0.0, 0.0)},
                            "hand_r": "open", "face": expr("concern", 0.5), "look": (-14, -20)})
    shake = merge(vent, {"arm_r": {"fk": (14.0, -30.0, 10.0), "elbow": 36.0, "wrist": (-10.0, 0.0, 0.0)},
                         "hand_r": "spread"})
    c.key(0, CHARGE_HOLD).key(5, vent).key(8, shake).key(11, vent).key(16, P.COMBAT)
    c.markers += [(3, "charge_cancelled")]
    return c


# ================================================================ deploy beacon
@clip("deploy")
def deploy(R):
    c = Clip("deploy", 50, form="one_shot", layer="full_body", entry="combat", exit="combat",
             notes="left hand takes the beacon from the back holster, crouches and places it 55 cm ahead")
    pr = Prober(R)
    base = merge(P.COMBAT, {"face": expr("focus", 0.5)})
    reach = merge(base, {"cog_rot": (6.0, 16.0, 0.0), "spine": (4, 18, 0), "neck": (0, -20, 0),
                         "clav_l": (-4, -10), "look": (-20, -10)})
    W = pr.world(reach, ["prop_beacon"])
    Mh = W["prop_beacon"]
    Hm = hand_for_prop(Mh, "beacon")
    reach["arm_l"] = {"ik": tuple(Hm[:3, 3]), "hand_rot": Hm[:3, :3], "pole": tuple(Hm[:3, 3] + np.array([0.45, 0.1, 0.25]))}
    reach["hand_l"] = "grip_beacon"
    pre = merge(reach, {"arm_l": dict(reach["arm_l"], ik=tuple(Hm[:3, 3] + np.array([0.06, 0.0, 0.05]))),
                        "hand_l": "open"})
    grab = merge(reach, {"beacon": {"parent": 0}})
    grabbed = merge(reach, {"beacon": {"parent": 1}})
    # carry in front of the belly
    Mc = np.eye(4)
    Mc[:3, :3] = np.stack([np.array([1.0, 0, 0]), np.array([0, -1.0, 0]), np.array([0, 0, 1.0])], 1)
    Mc[:3, 3] = np.array([0.12, -0.32, 1.02])
    Hc = hand_for_prop(Mc, "beacon")
    carry = merge(base, {"beacon": {"parent": 1}, "hand_l": "grip_beacon", "look": (4, -35),
                         "arm_l": {"ik": tuple(Hc[:3, 3]), "hand_rot": Hc[:3, :3],
                                   "pole": tuple(Hc[:3, 3] + np.array([0.4, 0.2, -0.1]))}})
    # crouch and place on the ground
    gpos = np.array([0.10, -0.56, 0.021])
    Mg = np.eye(4)
    Mg[:3, :3] = np.stack([np.array([1.0, 0, 0]), np.array([0, -1.0, 0]), np.array([0, 0, 1.0])], 1)
    Mg[:3, 3] = gpos
    Hg = hand_for_prop(Mg, "beacon")
    crouch = merge(base, {"cog": (0.03, -0.10, -0.43), "cog_rot": (34.0, 6.0, 0.0), "spine": (24, 6, 0),
                          "neck": (10, 0, 0), "head": (10, 0, 0), "look": (0, -30),
                          "foot_l": {"pos": P.ankle("l", 0.04, -0.20, 0.0), "yaw": 8.0},
                          "foot_r": dict(P.COMBAT["foot_r"], heelroll=0.45),
                          "arm_r": {"fk": (40.0, -20.0, 0.0), "elbow": 60.0},
                          "beacon": {"parent": 1}, "hand_l": "grip_beacon",
                          "arm_l": {"ik": tuple(Hg[:3, 3]), "hand_rot": Hg[:3, :3],
                                    "pole": tuple(Hg[:3, 3] + np.array([0.35, 0.25, 0.3]))}})
    above = merge(crouch, {"arm_l": dict(crouch["arm_l"], ik=tuple(Hg[:3, 3] + np.array([0.0, 0.0, 0.05]))),
                           "cog": (0.03, -0.10, -0.40)})
    placed = merge(crouch, {"beacon": {"parent": 2, "pos": tuple(gpos), "yaw": 0.0}})
    release = merge(placed, {"arm_l": dict(crouch["arm_l"], ik=tuple(Hg[:3, 3] + np.array([0.0, 0.03, 0.09]))),
                             "hand_l": "open"})
    stand = merge(base, {"beacon": {"parent": 2, "pos": tuple(gpos), "yaw": 0.0}})
    mid_step = merge(carry, {"foot_l": {"pos": P.ankle("l", 0.04, -0.17, 0.05), "yaw": 7.0}})
    c.key(0, base).key(6, pre).key(10, grab, "CONSTANT").key(11, grabbed).key(18, carry).key(21, mid_step)
    c.key(26, above).key(30, crouch, "CONSTANT").key(31, placed).key(35, release)
    c.key(42, merge(placed, {"cog": (0.02, -0.06, -0.22), "cog_rot": (14.0, 4.0, 0.0), "hand_l": "relaxed",
                             "arm_l": {"fk": (30.0, -30.0, 10.0), "elbow": 60.0}}))
    c.key(50, merge(stand, {"foot_l": {"pos": P.ankle("l", 0.04, -0.20, 0.0), "yaw": 8.0}}))
    c.markers += [(10, "beacon_grab"), (24, "foot_l_down"), (30, "beacon_release"), (31, "beacon_deployed")]
    c.extra["contacts"] = {"beacon_in_hand": [11, 30]}
    return c


# ================================================================ uplink (recall console)
def uplink_pose(R, pr, tap=0.0, extra=None):
    base = merge(P.COMBAT, {"face": expr("focus", 0.6)})
    rpos = np.array([-0.05, -0.31, 1.15])
    fwd = nrm(np.array([0.9, -0.3, 0.05]))
    Rr = hand_rot(fwd, np.array([0, 0, 1.0]))
    pose = merge(base, {"arm_r": {"ik": tuple(rpos), "hand_rot": Rr, "pole": (-0.5, 0.1, 1.0)},
                        "look": (8, -38), "head": (16, 6, 0), "neck": (10, 4, 0), "spine": (6, 12, 0),
                        "hand_r": "loose_fist"})
    pose.update(extra or {})
    W = pr.world(pose, ["lowerarm_r", "hand_r"])
    e = W["lowerarm_r"][:3, 3]
    w = W["hand_r"][:3, 3]
    top = W["lowerarm_r"][:3, 2]     # forearm bone Z: forward... use world up as display normal
    disp = e + 0.72 * (w - e) + np.array([0, 0, 0.055])
    fa = nrm(w - e)
    # left index finger points down onto the display
    Rl = hand_rot(nrm(np.array([0.0, -0.3, -1.0]) + fa * 0.2), nrm(np.array([0.2, 1.0, 0.3])))
    tip_off = 0.16
    hand_pos = disp + np.array([0.0, 0.03, 1.0]) * 0.0 - Rl[:, 1] * tip_off + np.array([0, 0, tap])
    pose["arm_l"] = {"ik": tuple(hand_pos), "hand_rot": Rl, "pole": tuple(hand_pos + np.array([0.4, 0.2, -0.2]))}
    pose["hand_l"] = "point"
    return pose


@clip("uplink_start")
def uplink_start(R):
    c = Clip("uplink_start", 24, form="one_shot", layer="full_body", entry="combat", exit="uplink_loop",
             notes="raise the cyber forearm console; left index finger begins the recall sequence")
    pr = Prober(R)
    up = uplink_pose(R, pr, tap=0.04)
    touch = uplink_pose(R, pr, tap=0.0)
    c.key(0, P.COMBAT).key(12, up).key(20, touch).key(24, uplink_pose(R, pr, tap=0.02))
    c.markers += [(20, "uplink_begin")]
    return c


@clip("uplink_loop")
def uplink_loop(R):
    c = Clip("uplink_loop", 45, loop=True, form="loop", layer="full_body", entry="uplink_start",
             exit="uplink_end|uplink_cancel", notes="sustained console input: taps, feet planted")
    pr = Prober(R)
    hi = uplink_pose(R, pr, tap=0.02)
    lo = uplink_pose(R, pr, tap=0.0)
    lo2 = uplink_pose(R, pr, tap=0.0, extra={"look": (12, -36)})
    c.key(0, hi).key(5, lo).key(10, hi).key(16, lo2).key(22, hi).key(28, lo).key(34, hi).key(39, lo2).key(45, hi)
    c.layers += [breathing(0.7), blinks([30])]
    for f in (5, 16, 28, 39):
        c.markers.append((f, "uplink_tap"))
    return c


@clip("uplink_end")
def uplink_end(R):
    c = Clip("uplink_end", 18, form="one_shot", layer="full_body", entry="uplink_loop", exit="combat|blink_out",
             notes="successful completion cue: final tap, flourish, nod")
    pr = Prober(R)
    hi = uplink_pose(R, pr, tap=0.02)
    lo = uplink_pose(R, pr, tap=0.0)
    flourish = merge(hi, {"arm_l": {"fk": (70.0, 30.0, -20.0), "elbow": 60.0, "wrist": (-20.0, 0.0, 0.0)},
                          "hand_l": "open", "face": expr("joy", 0.5), "head": (4, 0, 0), "look": (0, -5)})
    c.key(0, hi).key(4, lo).key(8, flourish).key(18, merge(P.COMBAT, {"face": expr("joy", 0.35)}))
    c.markers += [(4, "uplink_tap"), (6, "uplink_complete")]
    return c


@clip("uplink_cancel")
def uplink_cancel(R):
    c = Clip("uplink_cancel", 15, form="one_shot", layer="full_body", entry="uplink_loop|uplink_start",
             exit="combat", notes="interrupted recall: swipe away and drop back to control")
    pr = Prober(R)
    hi = uplink_pose(R, pr, tap=0.02)
    swipe = merge(hi, {"arm_l": {"fk": (50.0, 40.0, -30.0), "elbow": 30.0}, "hand_l": "open",
                       "face": expr("anger", 0.5), "look": (20, -5)})
    c.key(0, hi).key(3, swipe).key(15, P.COMBAT)
    c.markers += [(2, "uplink_cancelled")]
    return c

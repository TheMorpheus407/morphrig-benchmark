"""MorphRig reaction clips: additive hits, stun, knockback/up/down, prone, get-ups, sleep,
deaths, dead poses and respawn.  Floor contacts use mesh-based settling (mr_author.settle)."""
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, DEG
import mr_poses as P
from mr_author import Prober, settle, settle_lying, settle_sitting, hand_rot, nrm
from clips_common import clip, expr, breathing, blinks, sway_noise, tremble, face_mix

A = P.ankle
C = P.COMBAT
_CACHE = {}


def cached(name, fn):
    if name not in _CACHE:
        _CACHE[name] = fn()
    return _CACHE[name]


def palm_down(fwd=(0, -1.0, 0)):
    return hand_rot(np.array(fwd, float), np.array([0, 0, 1.0]))


def palm_up(fwd=(0, -1.0, 0)):
    return hand_rot(np.array(fwd, float), np.array([0, 0, -1.0]))


# ---------------------------------------------------------------- floor poses
def prone_front(R):
    def mk():
        pr = Prober(R)
        p = merge(C, {
            "cog": (0.0, 0.05, -0.86), "cog_rot": (88.0, 0.0, 0.0), "hips": (-4, 0, 0), "spine": (-6, 0, 0),
            "neck": (-22, 4, 0), "head": (-12, 62, 4),
            "leg_l": {"fk": (-4.0, 7.0, -8.0), "knee": 10.0, "ankle": (-48.0, 0.0), "toe": 20.0},
            "leg_r": {"fk": (-6.0, 5.0, 10.0), "knee": 26.0, "ankle": (-40.0, 0.0), "toe": 20.0},
            "arm_l": {"ik": (0.27, -0.70, 0.035), "hand_rot": palm_down((0.1, -1.0, 0)), "pole": (0.6, -0.4, 0.4)},
            "arm_r": {"ik": (-0.25, -0.60, 0.04), "hand_rot": palm_down((-0.15, -1.0, 0)), "pole": (-0.6, -0.3, 0.4)},
            "hand_l": "relaxed", "hand_r": "relaxed", "clav_l": (8, 6), "clav_r": (8, 6),
            "face": face_mix(expr("pain", 0.25), {"blink_L": 0.35, "blink_R": 0.35}), "jaw": 3.0, "look": (0, 0)})
        return settle_lying(pr, p, face_up=False)
    return cached("prone_front", mk)


def prone_back(R):
    def mk():
        pr = Prober(R)
        p = merge(C, {
            "cog": (0.0, -0.05, -0.86), "cog_rot": (-88.0, 0.0, 0.0), "hips": (4, 0, 0), "spine": (4, 0, 0),
            "neck": (10, 0, 0), "head": (4, -24, 0),
            "leg_l": {"fk": (6.0, 8.0, 10.0), "knee": 14.0, "ankle": (-14.0, 0.0)},
            "leg_r": {"fk": (18.0, 5.0, -6.0), "knee": 34.0, "ankle": (-10.0, 0.0)},
            "arm_l": {"ik": (0.46, 0.20, 0.04), "hand_rot": palm_up((0.4, 0.8, 0)), "pole": (0.5, 0.5, 0.5)},
            "arm_r": {"ik": (-0.40, 0.12, 0.05), "hand_rot": palm_up((-0.5, 0.8, 0)), "pole": (-0.5, 0.5, 0.5)},
            "hand_l": "relaxed", "hand_r": "relaxed",
            "face": face_mix(expr("pain", 0.25), {"blink_L": 0.3, "blink_R": 0.3}), "jaw": 2.0, "look": (0, 10)})
        return settle_lying(pr, p, face_up=True)
    return cached("prone_back", mk)


def dead_front_pose(R):
    """Final pose of death_front: fell backward, face up, limp and asymmetric."""
    def mk():
        pr = Prober(R)
        p = merge(prone_back(R), {
            "head": (6, -48, 8), "neck": (6, -8, 0),
            "leg_l": {"fk": (10.0, 14.0, 20.0), "knee": 22.0, "ankle": (-20.0, 0.0)},
            "leg_r": {"fk": (4.0, 4.0, -12.0), "knee": 8.0, "ankle": (-24.0, 0.0)},
            "arm_l": {"ik": (0.12, -0.18, 0.13), "hand_rot": palm_down((-0.6, -0.4, -0.2)), "pole": (0.6, 0.0, 0.5)},
            "arm_r": {"ik": (-0.52, 0.28, 0.045), "hand_rot": palm_up((-0.4, 0.9, 0)), "pole": (-0.6, 0.4, 0.5)},
            "face": {"blink_L": 0.78, "blink_R": 0.72, "browInnerUp_L": 0.15, "browInnerUp_R": 0.15},
            "jaw": 5.0, "hand_l": "loose_fist", "hand_r": "relaxed"})
        return settle_lying(pr, p, face_up=True)
    return cached("dead_front", mk)


def dead_back_pose(R):
    """Final pose of death_back: fell forward, face down, head turned, arms limp at the sides."""
    def mk():
        pr = Prober(R)
        p = merge(prone_front(R), {
            "head": (-10, -64, -4), "neck": (-18, -4, 0),
            "leg_l": {"fk": (-2.0, 3.0, -14.0), "knee": 34.0, "ankle": (-45.0, 0.0), "toe": 18.0},
            "leg_r": {"fk": (-5.0, 10.0, 12.0), "knee": 6.0, "ankle": (-50.0, 0.0), "toe": 18.0},
            "arm_l": {"ik": (0.26, 0.10, 0.045), "hand_rot": palm_up((0.1, 1.0, 0)), "pole": (0.6, 0.0, 0.5)},
            "arm_r": {"ik": (-0.33, -0.52, 0.04), "hand_rot": palm_down((-0.3, -1.0, 0)), "pole": (-0.6, -0.3, 0.5)},
            "face": {"blink_L": 0.85, "blink_R": 0.8}, "jaw": 4.0})
        return settle_lying(pr, p, face_up=False)
    return cached("dead_back", mk)


def kneel(R, side="r", extra=None):
    """One knee on the floor (side), other foot planted forward."""
    key = "kneel_" + side + str(sorted((extra or {}).items()) if extra else "")

    def mk():
        pr = Prober(R)
        other = "l" if side == "r" else "r"
        sg = 1.0 if other == "l" else -1.0
        p = merge(C, {
            "cog": (0.0, -0.02, -0.50), "cog_rot": (10.0, 0.0, 0.0), "hips": (0, 0, 0), "spine": (8, 0, 0),
            "neck": (-6, 0, 0), "head": (-2, 0, 0),
            "foot_" + other: {"pos": A(other, 0.02 * sg, -0.36, 0.0), "yaw": 4.0 * sg},
            "leg_" + side: {"fk": (-4.0, 4.0, 0.0), "knee": 96.0, "ankle": (-30.0, 0.0), "toe": 45.0},
            "arm_l": {"fk": (20.0, -30.0, 10.0), "elbow": 30.0}, "arm_r": {"fk": (20.0, -30.0, 10.0), "elbow": 30.0}})
        if extra:
            p = merge(p, extra)
        return settle(pr, p, 0.006, ("MR_Suit",))
    return cached(key, mk)


def all_fours(R):
    def mk():
        pr = Prober(R)
        p = merge(C, {
            "cog": (0.0, -0.20, -0.52), "cog_rot": (72.0, 0.0, 0.0), "hips": (-10, 0, 0), "spine": (-8, 0, 0),
            "neck": (-30, 0, 0), "head": (-18, 0, 0),
            "leg_l": {"fk": (-58.0, 6.0, 0.0), "knee": 92.0, "ankle": (-40.0, 0.0), "toe": 40.0},
            "leg_r": {"fk": (-58.0, 6.0, 0.0), "knee": 92.0, "ankle": (-40.0, 0.0), "toe": 40.0},
            "arm_l": {"ik": (0.20, -0.66, 0.05), "hand_rot": palm_down((0.1, -1.0, 0)), "pole": (0.5, -0.3, 0.8)},
            "arm_r": {"ik": (-0.20, -0.66, 0.05), "hand_rot": palm_down((-0.1, -1.0, 0)), "pole": (-0.5, -0.3, 0.8)},
            "hand_l": "open", "hand_r": "open", "face": expr("pain", 0.4), "look": (0, 10)})
        return settle(pr, p, 0.008, ("MR_Suit",))
    return cached("all_fours", mk)


def sit_back(R):
    """Sitting on the floor, hands behind for support."""
    def mk():
        pr = Prober(R)
        p = merge(C, {
            "cog": (0.0, 0.08, -0.80), "cog_rot": (-20.0, 0.0, 0.0), "hips": (-10, 0, 0), "spine": (12, 0, 0),
            "neck": (8, 0, 0), "head": (6, 0, 0),
            "leg_l": {"fk": (70.0, 12.0, 10.0), "knee": 70.0, "ankle": (5.0, 0.0)},
            "leg_r": {"fk": (60.0, 8.0, -6.0), "knee": 40.0, "ankle": (-5.0, 0.0)},
            "arm_l": {"ik": (0.24, 0.30, 0.04), "hand_rot": palm_down((0.2, 1.0, 0)), "pole": (0.5, 0.6, 0.6)},
            "arm_r": {"ik": (-0.24, 0.30, 0.04), "hand_rot": palm_down((-0.2, 1.0, 0)), "pole": (-0.5, 0.6, 0.6)},
            "hand_l": "open", "hand_r": "open", "face": expr("pain", 0.3), "look": (0, 0)})
        return settle_sitting(pr, p)
    return cached("sit_back", mk)


# ================================================================ additive hits
def _hit(cid, pitch, roll, twist, head, arms, note):
    c = Clip(cid, 12, form="additive", layer="additive_upper", entry="any", exit="any",
             notes=note + "; additive relative to frame 0 (combat idle), legs untouched")
    peak = merge(C, {"spine": (C["spine"][0] + pitch, C["spine"][1] + twist, roll),
                     "neck": (C["neck"][0] + head[0] * 0.5, C["neck"][1] + head[1] * 0.5, head[2] * 0.5),
                     "head": (C["head"][0] + head[0] * 0.5, C["head"][1] + head[1] * 0.5, head[2] * 0.5),
                     "clav_l": (8, arms[0]), "clav_r": (8, arms[1]),
                     "face": expr("pain", 0.9), "jaw": 7.0})
    after = merge(C, {"spine": (C["spine"][0] + pitch * 0.35, C["spine"][1] + twist * 0.3, roll * 0.3),
                      "face": expr("pain", 0.4), "jaw": 2.0})
    c.key(0, C).key(2, peak).key(6, after).key(12, C)
    c.markers += [(0, "hit_impact")]
    return c


@clip("hit_f")
def hit_f(R):
    return _hit("hit_f", -12.0, 0.0, 0.0, (-16.0, 0.0, 0.0), (6, 6), "impact from the front: chest and head snap back")


@clip("hit_b")
def hit_b(R):
    return _hit("hit_b", 14.0, 0.0, 0.0, (12.0, 0.0, 0.0), (-8, -8), "impact from behind: torso lurches forward")


@clip("hit_l")
def hit_l(R):
    return _hit("hit_l", 2.0, 12.0, -10.0, (0.0, -8.0, 14.0), (-4, 8), "impact from the left: bend and twist right")


@clip("hit_r")
def hit_r(R):
    return _hit("hit_r", 2.0, -12.0, 10.0, (0.0, 8.0, -14.0), (8, -4), "impact from the right: bend and twist left")


# ================================================================ stun
STUN = merge(C, {"cog": (0.0, 0.03, -0.12), "cog_rot": (8.0, -6.0, 4.0), "spine": (12, 4, 6), "neck": (10, 0, 4),
                 "head": (8, 6, 10), "arm_l": {"fk": (6.0, -40.0, 10.0), "elbow": 24.0},
                 "arm_r": {"fk": (4.0, -38.0, 6.0), "elbow": 30.0}, "hand_l": "relaxed", "hand_r": "relaxed",
                 "face": face_mix(expr("concern", 0.4), {"blink_L": 0.45, "blink_R": 0.55}), "jaw": 5.0,
                 "look": (6, -12)})


@clip("stun_start")
def stun_start(R):
    c = Clip("stun_start", 24, form="one_shot", layer="full_body", entry="any", exit="stun_loop",
             notes="lose control: jolt, head snaps, knees buckle into the dazed stance")
    jolt = merge(C, {"cog": (0.0, 0.04, -0.07), "spine": (-8, 4, 0), "neck": (-14, 0, 0), "head": (-12, 0, 0),
                     "arm_l": {"fk": (40.0, 10.0, 0.0), "elbow": 60.0}, "arm_r": {"fk": (40.0, 10.0, 0.0), "elbow": 60.0},
                     "hand_l": "spread", "hand_r": "spread", "face": expr("surprise", 0.8), "jaw": 10.0})
    sag = merge(STUN, {"cog": (0.0, 0.03, -0.15), "head": (14, 0, 14)})
    c.key(0, C).key(3, jolt).key(12, sag).key(24, STUN)
    c.markers += [(1, "stun_applied")]
    return c


@clip("stun_loop")
def stun_loop(R):
    c = Clip("stun_loop", 60, loop=True, form="loop", layer="full_body", entry="stun_start", exit="stun_end",
             notes="disoriented: head circles, body sways, breathing; feet planted")
    a = merge(STUN, {"cog_rot": (8.0, -6.0, 6.0), "head": (8, 12, 10)})
    b = merge(STUN, {"cog_rot": (10.0, -4.0, -2.0), "head": (12, -6, -6), "cog": (0.0, 0.035, -0.13)})
    d = merge(STUN, {"cog_rot": (6.0, -8.0, 2.0), "head": (4, 2, 12)})
    c.key(0, a).key(20, b).key(40, d).key(60, a)
    c.layers += [breathing(1.2, period=30), blinks([15, 44], dur_close=4, dur_open=8, amount=0.5),
                 sway_noise(11, 1.0, ("head.rot", "neck_02.rot", "spine_03.rot"))]
    return c


@clip("stun_end")
def stun_end(R):
    c = Clip("stun_end", 26, form="one_shot", layer="full_body", entry="stun_loop", exit="combat",
             notes="shake it off and regain control without sliding the feet")
    shake1 = merge(STUN, {"head": (4, 18, 0), "face": expr("focus", 0.3), "jaw": 1.0})
    shake2 = merge(STUN, {"head": (2, -16, 0), "cog": (0.0, 0.02, -0.10)})
    c.key(0, STUN).key(6, shake1).key(10, shake2).key(14, merge(shake1, {"head": (0, 6, 0)}))
    c.key(26, merge(C, {"face": expr("focus", 0.8)}))
    c.markers += [(16, "control_regained")]
    return c


# ================================================================ knockback / knockup
@clip("knockback")
def knockback(R):
    c = Clip("knockback", 34, form="one_shot", layer="full_body", entry="any", exit="combat",
             notes="reaction to host-driven backward travel: braced, bent over the impact, arms thrown forward; "
                   "the controller moves the capsule back (feet skid visually)")
    hit = merge(C, {"cog": (0.0, 0.05, -0.16), "cog_rot": (26.0, -6.0, 0.0), "spine": (22, 4, 0), "neck": (-10, 0, 0),
                    "head": (-8, 0, 0), "arm_l": {"fk": (70.0, 10.0, 0.0), "elbow": 40.0},
                    "arm_r": {"fk": (66.0, 6.0, 0.0), "elbow": 44.0}, "hand_l": "spread", "hand_r": "spread",
                    "foot_l": {"pos": A("l", 0.05, -0.20, 0.0), "yaw": 8.0}, "face": expr("pain", 0.9), "jaw": 9.0})
    hit["foot_r"] = {"pos": A("r", -0.06, 0.20, 0.0), "yaw": -26.0, "heelroll": 0.3}
    brace = merge(hit, {"cog": (0.0, 0.06, -0.18), "cog_rot": (18.0, -8.0, 0.0), "spine": (14, 4, 0),
                        "face": expr("anger", 0.6), "jaw": 3.0})
    c.key(0, C).key(3, hit).key(16, brace).key(34, C)
    c.markers += [(0, "knockback_impact"), (22, "control_regained")]
    return c


KNOCKUP_AIR = merge(C, {
    "cog": (0.0, 0.05, 0.10), "cog_rot": (-16.0, 0.0, 6.0), "spine": (-14, 0, 4), "neck": (-16, 0, 0),
    "head": (-14, 0, 0),
    "leg_l": {"fk": (40.0, 14.0, 0.0), "knee": 70.0, "ankle": (-30.0, 0.0)},
    "leg_r": {"fk": (18.0, 10.0, 0.0), "knee": 50.0, "ankle": (-40.0, 0.0)},
    "arm_l": {"fk": (60.0, 70.0, 0.0), "elbow": 40.0}, "arm_r": {"fk": (40.0, 80.0, 0.0), "elbow": 50.0},
    "hand_l": "spread", "hand_r": "spread", "face": face_mix(expr("surprise", 0.6), expr("pain", 0.5)), "jaw": 12.0})


@clip("knockup_start")
def knockup_start(R):
    c = Clip("knockup_start", 16, form="one_shot", layer="full_body", entry="any", exit="knockup_air",
             notes="forced launch without anticipation: the body is flung up, legs leave the floor limp")
    c.key(0, C).key(2, merge(C, {"cog": (0.0, 0.03, -0.02), "spine": (-10, 0, 0), "head": (-16, 0, 0),
                                 "face": expr("pain", 0.8), "jaw": 10.0}))
    c.key(9, merge(KNOCKUP_AIR, {"cog": (0.0, 0.04, 0.06)})).key(16, KNOCKUP_AIR)
    c.markers += [(0, "knockup_impact"), (4, "feet_leave_ground")]
    return c


@clip("knockup_air")
def knockup_air(R):
    c = Clip("knockup_air", 30, loop=True, form="loop", layer="full_body", entry="knockup_start",
             exit="knockdown_front|knockdown_back|jump_land|land_heavy", notes="helpless airborne tumble")
    b = merge(KNOCKUP_AIR, {"cog_rot": (-22.0, 4.0, -6.0), "arm_l": {"fk": (80.0, 60.0, 20.0), "elbow": 30.0},
                            "arm_r": {"fk": (30.0, 90.0, -10.0), "elbow": 70.0},
                            "leg_l": {"fk": (20.0, 10.0, 0.0), "knee": 50.0, "ankle": (-40.0, 0.0)},
                            "leg_r": {"fk": (44.0, 16.0, 0.0), "knee": 80.0, "ankle": (-30.0, 0.0)}})
    c.key(0, KNOCKUP_AIR).key(15, b).key(30, KNOCKUP_AIR)
    c.layers += [sway_noise(21, 2.0, ("spine_02.rot", "head.rot", "c_upperarm_fk_l.rot", "c_upperarm_fk_r.rot"))]
    return c


# ================================================================ knockdowns / prone / get-ups
@clip("knockdown_front")
def knockdown_front(R):
    c = Clip("knockdown_front", 42, form="one_shot", layer="full_body", entry="any", exit="prone_front",
             notes="stumble forward onto the knees, hands catch, chest settles face-down")
    stumble = merge(C, {"cog": (0.0, -0.10, -0.12), "cog_rot": (24.0, 0.0, 0.0), "spine": (16, 0, 0),
                        "arm_l": {"fk": (70.0, 10.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (70.0, 10.0, 0.0), "elbow": 30.0},
                        "hand_l": "spread", "hand_r": "spread", "face": expr("pain", 0.9), "jaw": 8.0,
                        "foot_l": {"pos": A("l", 0.04, -0.34, 0.0), "yaw": 6.0}})
    stumble["foot_r"] = dict(C["foot_r"], heelroll=0.55)
    step = merge(stumble, {"foot_l": {"pos": A("l", 0.04, -0.25, 0.06), "yaw": 6.0}})
    knees = merge(all_fours(R), {"cog_rot": (40.0, 0.0, 0.0), "arm_l": {"fk": (80.0, 20.0, 0.0), "elbow": 20.0},
                                 "arm_r": {"fk": (80.0, 20.0, 0.0), "elbow": 20.0}})
    knees = settle(Prober(R), knees, 0.006, ("MR_Suit",))
    hands = all_fours(R)
    down = prone_front(R)
    c.key(0, C).key(5, step).key(9, stumble).key(18, knees).key(24, hands).key(34, down).key(42, down)
    c.markers += [(0, "knockdown_impact"), (9, "foot_l_down"), (18, "knees_contact"), (24, "hands_contact"),
                  (34, "body_contact")]
    return c


@clip("knockdown_back")
def knockdown_back(R):
    c = Clip("knockdown_back", 40, form="one_shot", layer="full_body", entry="any", exit="prone_back",
             notes="stagger back, sit down onto the hands, roll onto the back (chin tucked)")
    hit = merge(C, {"cog": (0.0, 0.08, -0.10), "cog_rot": (-14.0, 0.0, 0.0), "spine": (-10, 0, 0),
                    "neck": (-10, 0, 0), "arm_l": {"fk": (60.0, 30.0, 0.0), "elbow": 40.0},
                    "arm_r": {"fk": (60.0, 30.0, 0.0), "elbow": 40.0}, "hand_l": "spread", "hand_r": "spread",
                    "face": expr("pain", 0.9), "jaw": 9.0})
    back_step = merge(hit, {"foot_l": {"pos": A("l", 0.03, 0.10, 0.0), "yaw": 4.0}, "cog": (0.0, 0.14, -0.22)})
    mid = merge(hit, {"foot_l": {"pos": A("l", 0.03, -0.02, 0.06), "yaw": 4.0}})
    sit = sit_back(R)
    down = prone_back(R)
    rolling = merge(down, {"cog_rot": (-60.0, 0.0, 0.0), "neck": (22, 0, 0), "head": (14, 0, 0),
                           "leg_l": {"fk": (40.0, 10.0, 8.0), "knee": 50.0, "ankle": (-10.0, 0.0)},
                           "leg_r": {"fk": (46.0, 6.0, -6.0), "knee": 60.0, "ankle": (-10.0, 0.0)}})
    rolling = settle(Prober(R), rolling, 0.004, ("MR_Suit", "MR_Boot_L", "MR_Boot_R"))
    c.key(0, C).key(4, hit).key(7, mid).key(11, back_step).key(20, sit).key(28, rolling).key(34, down)
    c.key(40, down)
    c.markers += [(0, "knockdown_impact"), (11, "foot_l_down"), (20, "hips_contact"), (30, "back_contact")]
    return c


@clip("prone_front")
def prone_front_loop(R):
    c = Clip("prone_front", 60, loop=True, form="loop", layer="full_body", entry="knockdown_front",
             exit="getup_front", notes="face-down on the floor, restrained breathing")
    a = prone_front(R)
    b = merge(a, {"spine": (-7.5, 0, 0), "head": (-12, 60, 4)})
    c.key(0, a).key(30, b).key(60, a)
    c.layers += [breathing(1.4, period=30), blinks([20], dur_close=3, dur_open=6, amount=0.6)]
    return c


@clip("prone_back")
def prone_back_loop(R):
    c = Clip("prone_back", 60, loop=True, form="loop", layer="full_body", entry="knockdown_back",
             exit="getup_back", notes="face-up on the floor, restrained breathing")
    a = prone_back(R)
    b = merge(a, {"spine": (5.5, 0, 0), "head": (6, -20, 0)})
    c.key(0, a).key(30, b).key(60, a)
    c.layers += [breathing(1.5, period=30), blinks([40], dur_close=3, dur_open=6, amount=0.7)]
    return c


@clip("getup_front")
def getup_front(R):
    c = Clip("getup_front", 64, form="one_shot", layer="full_body", entry="prone_front", exit="combat",
             notes="push up with both hands, bring the right knee under, kneel, plant the left foot, stand")
    pr = Prober(R)
    down = prone_front(R)
    push = merge(down, {"cog_rot": (70.0, 0.0, 0.0), "cog": (down["cog"][0], down["cog"][1] - 0.10, down["cog"][2] + 0.14),
                        "neck": (-26, 0, 0), "head": (-14, 0, 0), "hands": None,
                        "arm_l": {"ik": (0.24, -0.58, 0.05), "hand_rot": palm_down((0.1, -1.0, 0)), "pole": (0.6, -0.2, 0.6)},
                        "arm_r": {"ik": (-0.24, -0.58, 0.05), "hand_rot": palm_down((-0.1, -1.0, 0)), "pole": (-0.6, -0.2, 0.6)},
                        "hand_l": "open", "hand_r": "open", "face": expr("pain", 0.6), "jaw": 5.0})
    push = settle(pr, push, 0.006, ("MR_Suit",))
    fours = all_fours(R)
    knee = kneel(R, "r", {"arm_l": {"fk": (40.0, -24.0, 10.0), "elbow": 50.0}, "face": expr("focus", 0.6)})
    rise = merge(C, {"cog": (0.0, -0.05, -0.28), "cog_rot": (22.0, 0.0, 0.0), "spine": (14, 0, 0),
                     "foot_l": {"pos": A("l", 0.02, -0.36, 0.0), "yaw": 4.0},
                     "foot_r": {"pos": A("r", -0.02, 0.16, 0.0), "yaw": -8.0, "heelroll": 0.5},
                     "arm_l": {"fk": (30.0, -30.0, 10.0), "elbow": 60.0}, "face": expr("focus", 0.7)})
    step_back = merge(C, {"foot_l": {"pos": A("l", 0.03, -0.24, 0.05), "yaw": 5.0}, "cog": (0.0, -0.02, -0.12)})
    c.key(0, down).key(10, push).key(22, fours).key(34, knee).key(46, rise).key(54, step_back).key(64, C)
    c.markers += [(10, "hands_contact"), (28, "foot_r_under"), (34, "knee_contact"), (46, "foot_l_down"),
                  (58, "foot_l_down"), (64, "control_regained")]
    return c


@clip("getup_back")
def getup_back(R):
    c = Clip("getup_back", 64, form="one_shot", layer="full_body", entry="prone_back", exit="combat",
             notes="sit up on the hands, roll onto the right knee, stand")
    pr = Prober(R)
    down = prone_back(R)
    sit = sit_back(R)
    turn = kneel(R, "r", {"cog_rot": (18.0, 30.0, 0.0), "spine": (12, 10, 0),
                          "arm_r": {"ik": (-0.30, -0.10, 0.05), "hand_rot": palm_down((-0.3, -1.0, 0)),
                                    "pole": (-0.6, 0.2, 0.6)},
                          "face": expr("focus", 0.6)})
    knee = kneel(R, "r", {"face": expr("focus", 0.7)})
    # the right hand swings out around the right thigh on its way from behind the hips to the floor in front
    swing = merge(sit, {"arm_r": {"ik": (-0.52, 0.10, 0.26), "hand_rot": palm_down((-0.5, -0.6, 0)),
                                  "pole": (-0.7, 0.4, 0.4)}, "face": expr("focus", 0.4)})
    rise = merge(C, {"cog": (0.0, -0.05, -0.28), "cog_rot": (20.0, 0.0, 0.0), "spine": (14, 0, 0),
                     "foot_l": {"pos": A("l", 0.02, -0.36, 0.0), "yaw": 4.0},
                     "foot_r": {"pos": A("r", -0.02, 0.16, 0.0), "yaw": -8.0, "heelroll": 0.5}})
    step_back = merge(C, {"foot_l": {"pos": A("l", 0.03, -0.24, 0.05), "yaw": 5.0}, "cog": (0.0, -0.02, -0.12)})
    c.key(0, down).key(14, sit).key(20, swing).key(28, turn).key(38, knee).key(48, rise).key(56, step_back).key(64, C)
    c.markers += [(14, "hips_contact"), (28, "knee_contact"), (48, "foot_l_down"), (60, "foot_l_down"),
                  (64, "control_regained")]
    return c


# ================================================================ sleep
def sleep_pose(R):
    return kneel(R, "r", {"cog_rot": (22.0, 0.0, 0.0), "spine": (20, 0, 0), "neck": (22, 0, 0),
                          "head": (18, 8, 6),
                          # left forearm rests on the raised left knee, hand hanging past it
                          "arm_l": {"ik": (0.13, -0.50, 0.555), "hand_rot": palm_down((0.0, -1.0, -0.45)),
                                    "pole": (0.7, 0.3, 0.0)},
                          "arm_r": {"fk": (14.0, -34.0, 20.0), "elbow": 40.0}, "hand_l": "relaxed",
                          "hand_r": "relaxed", "face": {"blink_L": 1.0, "blink_R": 1.0}, "jaw": 3.0})


@clip("sleep_start")
def sleep_start(R):
    c = Clip("sleep_start", 60, form="one_shot", layer="full_body", entry="any", exit="sleep_loop",
             notes="drowsy: head drops, knees fold, settles into a stable kneeling sleep posture")
    drowsy = merge(C, {"cog": (0.0, 0.02, -0.10), "neck": (14, 0, 0), "head": (10, 0, 6),
                       "arm_l": {"fk": (6.0, -38.0, 10.0), "elbow": 20.0}, "arm_r": {"fk": (6.0, -38.0, 10.0), "elbow": 20.0},
                       "face": {"blink_L": 0.6, "blink_R": 0.65}, "jaw": 4.0})
    c.key(0, C).key(14, drowsy).key(26, merge(drowsy, {"face": {"blink_L": 0.3, "blink_R": 0.3}}))
    c.key(40, kneel(R, "r", {"cog_rot": (18.0, 0.0, 0.0), "spine": (16, 0, 0), "head": (14, 0, 4), "neck": (16, 0, 0),
                             "face": {"blink_L": 0.8, "blink_R": 0.8},
                             "arm_l": {"ik": (0.14, -0.49, 0.58), "hand_rot": palm_down((0.0, -1.0, -0.3)),
                                       "pole": (0.7, 0.3, 0.0)}}))
    c.key(60, sleep_pose(R))
    c.markers += [(40, "knee_contact"), (60, "asleep")]
    return c


@clip("sleep_loop")
def sleep_loop(R):
    c = Clip("sleep_loop", 90, loop=True, form="loop", layer="full_body", entry="sleep_start", exit="sleep_end",
             notes="sustained sleep: slow breathing and slight head nod")
    a = sleep_pose(R)
    b = merge(a, {"head": (18, 8, 6), "spine": (23, 0, 0)})
    c.key(0, a).key(45, b).key(90, a)
    c.layers += [breathing(2.0, period=45)]
    return c


@clip("sleep_end")
def sleep_end(R):
    c = Clip("sleep_end", 45, form="one_shot", layer="full_body", entry="sleep_loop", exit="combat",
             notes="startled awake: head snaps up, eyes open, rises to readiness")
    a = sleep_pose(R)
    jerk = merge(a, {"neck": (-6, 0, 0), "head": (-10, 0, 0), "spine": (10, 0, 0),
                     "face": expr("surprise", 0.9), "jaw": 6.0})
    knee = kneel(R, "r", {"face": expr("focus", 0.8)})
    rise = merge(C, {"cog": (0.0, -0.05, -0.28), "cog_rot": (20.0, 0.0, 0.0), "spine": (14, 0, 0),
                     "foot_l": {"pos": A("l", 0.02, -0.36, 0.0), "yaw": 4.0},
                     "foot_r": {"pos": A("r", -0.02, 0.16, 0.0), "yaw": -8.0, "heelroll": 0.5}})
    step_back = merge(C, {"foot_l": {"pos": A("l", 0.03, -0.24, 0.05), "yaw": 5.0}, "cog": (0.0, -0.02, -0.12)})
    c.key(0, a).key(5, jerk).key(16, knee).key(28, rise).key(36, step_back).key(45, C)
    c.markers += [(5, "awake"), (40, "foot_l_down"), (45, "control_regained")]
    return c


# ================================================================ deaths
@clip("death_front")
def death_front(R):
    c = Clip("death_front", 66, form="one_shot", layer="full_body", entry="any", exit="dead_front",
             notes="front impact: thrown back, stagger step, knees give, falls onto the back (face up)")
    hit = merge(C, {"cog": (0.0, 0.06, -0.08), "cog_rot": (-16.0, 4.0, 0.0), "spine": (-14, 0, 0),
                    "neck": (-16, 0, 0), "head": (-14, 0, 0), "arm_l": {"fk": (60.0, 30.0, 0.0), "elbow": 30.0},
                    "arm_r": {"fk": (50.0, 40.0, 0.0), "elbow": 40.0}, "hand_l": "spread", "hand_r": "spread",
                    "face": expr("pain", 1.0), "jaw": 12.0})
    step = merge(hit, {"foot_l": {"pos": A("l", 0.04, 0.02, 0.07), "yaw": 6.0}, "cog": (0.0, 0.10, -0.12)})
    planted = merge(hit, {"foot_l": {"pos": A("l", 0.04, 0.12, 0.0), "yaw": 6.0}, "cog": (0.0, 0.16, -0.26),
                          "cog_rot": (-8.0, 4.0, 4.0), "spine": (8, 0, 4), "neck": (8, 0, 0), "head": (10, 0, 10),
                          "arm_l": {"fk": (20.0, -10.0, 0.0), "elbow": 20.0}, "arm_r": {"fk": (10.0, -10.0, 0.0), "elbow": 20.0},
                          "hand_l": "relaxed", "hand_r": "relaxed", "face": face_mix(expr("pain", 0.5), {"blink_L": 0.5, "blink_R": 0.5}),
                          "jaw": 6.0})
    sit = merge(sit_back(R), {"arm_l": {"fk": (10.0, 10.0, 0.0), "elbow": 10.0}, "arm_r": {"fk": (10.0, 10.0, 0.0), "elbow": 10.0},
                              "neck": (0, 0, 0), "face": {"blink_L": 0.7, "blink_R": 0.7}, "jaw": 6.0})
    sit = settle_sitting(Prober(R), sit)
    dead = dead_front_pose(R)
    bounce = merge(dead, {"spine": (dead["spine"][0] + 3, 0, 0)})
    c.key(0, C).key(3, hit).key(8, step).key(14, planted).key(28, sit).key(40, bounce).key(46, dead).key(66, dead)
    c.markers += [(0, "death_impact"), (14, "foot_l_down"), (28, "hips_contact"), (40, "body_contact"), (46, "dead")]
    return c


@clip("death_back")
def death_back(R):
    c = Clip("death_back", 66, form="one_shot", layer="full_body", entry="any", exit="dead_back",
             notes="back impact: chest thrown forward, stumbles, knees hit the floor, collapses face down; "
                   "no hand catch (distinct contacts from death_front)")
    hit = merge(C, {"cog": (0.0, -0.06, -0.08), "cog_rot": (18.0, -4.0, 0.0), "spine": (-10, 0, 0),
                    "neck": (-20, 0, 0), "head": (-12, 0, 0), "arm_l": {"fk": (-30.0, 20.0, 0.0), "elbow": 20.0},
                    "arm_r": {"fk": (-30.0, 20.0, 0.0), "elbow": 20.0}, "hand_l": "spread", "hand_r": "spread",
                    "face": expr("pain", 1.0), "jaw": 12.0})
    stumble = merge(hit, {"foot_r": {"pos": A("r", -0.04, -0.30, 0.0), "yaw": -6.0}, "cog": (0.0, -0.18, -0.20),
                          "cog_rot": (28.0, 0.0, 0.0), "spine": (14, 0, 0), "neck": (10, 0, 0)})
    mid = merge(hit, {"foot_r": {"pos": A("r", -0.04, -0.12, 0.07), "yaw": -6.0}})
    knees = merge(all_fours(R), {"cog_rot": (30.0, 0.0, 6.0), "spine": (18, 0, 4), "neck": (18, 0, 0), "head": (14, 0, 0),
                                 "arm_l": {"fk": (-10.0, -30.0, 0.0), "elbow": 20.0},
                                 "arm_r": {"fk": (-6.0, -30.0, 0.0), "elbow": 20.0},
                                 "hand_l": "relaxed", "hand_r": "relaxed",
                                 "face": {"blink_L": 0.7, "blink_R": 0.7}, "jaw": 6.0})
    knees = settle(Prober(R), knees, 0.006, ("MR_Suit",))
    dead = dead_back_pose(R)
    bounce = merge(dead, {"spine": (dead["spine"][0] - 3, 0, 0)})
    c.key(0, C).key(3, hit).key(7, mid).key(12, stumble).key(24, knees).key(38, bounce).key(44, dead).key(66, dead)
    c.markers += [(0, "death_impact"), (12, "foot_r_down"), (24, "knees_contact"), (38, "body_contact"), (44, "dead")]
    return c


@clip("dead_front")
def dead_front(R):
    c = Clip("dead_front", 1, form="pose", layer="full_body", entry="death_front", exit="respawn",
             notes="held final pose of death_front (identical to its last frame)")
    d = dead_front_pose(R)
    c.key(0, d).key(1, d)
    c.extra["pose_from"] = "death_front"
    return c


@clip("dead_back")
def dead_back(R):
    c = Clip("dead_back", 1, form="pose", layer="full_body", entry="death_back", exit="respawn",
             notes="held final pose of death_back (identical to its last frame)")
    d = dead_back_pose(R)
    c.key(0, d).key(1, d)
    c.extra["pose_from"] = "death_back"
    return c


@clip("respawn")
def respawn(R):
    c = Clip("respawn", 76, form="one_shot", layer="full_body", entry="dead_front|dead_back|any", exit="combat",
             notes="reconstruct kneeling with head down, power up, rise and settle into the ready stance")
    k0 = kneel(R, "r", {"cog_rot": (26.0, 0.0, 0.0), "spine": (24, 0, 0), "neck": (20, 0, 0), "head": (14, 0, 0),
                        "arm_l": {"fk": (10.0, -34.0, 20.0), "elbow": 40.0}, "arm_r": {"fk": (10.0, -34.0, 20.0), "elbow": 40.0},
                        "hand_l": "relaxed", "hand_r": "relaxed", "face": {"blink_L": 1.0, "blink_R": 1.0}})
    k1 = kneel(R, "r", {"cog_rot": (14.0, 0.0, 0.0), "spine": (6, 0, 0), "neck": (-4, 0, 0), "head": (-4, 0, 0),
                        "arm_r": {"fk": (50.0, -10.0, 0.0), "elbow": 90.0}, "hand_r": "fist",
                        "face": expr("focus", 1.0)})
    rise = merge(C, {"cog": (0.0, -0.05, -0.30), "cog_rot": (18.0, 0.0, 0.0), "spine": (10, 0, 0),
                     "foot_l": {"pos": A("l", 0.02, -0.36, 0.0), "yaw": 4.0},
                     "foot_r": {"pos": A("r", -0.02, 0.16, 0.0), "yaw": -8.0, "heelroll": 0.5},
                     "face": expr("focus", 1.0)})
    power = merge(C, {"cog": (0.0, 0.0, -0.02), "cog_rot": (-6.0, -10.0, 0.0), "spine": (-12, 6, 0),
                      "neck": (-8, 0, 0), "arm_l": {"fk": (20.0, 20.0, 0.0), "elbow": 30.0},
                      "arm_r": {"fk": (20.0, 20.0, 0.0), "elbow": 30.0}, "hand_l": "fist", "hand_r": "fist",
                      "foot_l": {"pos": A("l", 0.03, -0.22, 0.0), "yaw": 5.0},
                      "face": expr("joy", 0.4), "jaw": 2.0})
    c.key(0, k0).key(22, k0).key(34, k1).key(48, rise).key(58, power).key(76, C)
    c.layers += [breathing(1.2, period=38)]
    c.markers += [(0, "respawn_begin"), (22, "reconstructed"), (48, "foot_l_down"), (58, "activate"),
                  (76, "control_regained")]
    return c

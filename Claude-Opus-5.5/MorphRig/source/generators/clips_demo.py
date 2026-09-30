"""Extra (non-inventory) action demonstrating deformation in demanding poses:
overhead reach, deep squat, crossed-arm reach, large torso twist, kneeling, planted hand support
and closed-grip interaction.  Each pose is held for ~0.5 s.  Registered as 'demo_deformation'."""
import numpy as np
from mr_clip import Clip
from mr_anim import merge
from mr_author import hand_rot, nrm, Prober, settle
import mr_poses as P
from clips_common import clip, expr, breathing

EXTRA_CLIPS = ["demo_deformation"]


def _ik(pos, fingers, back, pole):
    return {"ik": tuple(pos), "hand_rot": hand_rot(np.asarray(fingers, float), np.asarray(back, float)),
            "pole": tuple(pole)}


@clip("demo_deformation")
def demo_deformation(R):
    c = Clip("demo_deformation", 330, form="one_shot", layer="full_body", entry="idle_relaxed",
             exit="idle_relaxed", notes="extra: deformation demonstration poses (not an inventory entry)")
    base = merge(P.RELAXED, {"face": expr("focus", 0.2)})
    # 1 overhead reach: both hands high, slight rise onto the balls of the feet
    reach = merge(base, {
        "cog": (0.0, 0.0, 0.03), "spine": (-6, 0, 0), "neck": (-10, 0, 0), "head": (-12, 0, 0), "look": (0, 30),
        "clav_l": (18, 0), "clav_r": (18, 0),
        "arm_l": _ik((0.16, -0.05, 2.12), (0, 0, 1), (0, 1, 0), (0.6, 0.2, 1.5)),
        "arm_r": _ik((-0.16, -0.05, 2.12), (0, 0, 1), (0, 1, 0), (-0.6, 0.2, 1.5)),
        "hand_l": "open", "hand_r": "open",
        "foot_l": {"pos": P.ankle("l", 0.012, 0.0, 0.035), "yaw": 4.0, "pitch": -24.0},
        "foot_r": {"pos": P.ankle("r", -0.012, 0.0, 0.035), "yaw": -4.0, "pitch": -24.0}})
    # 2 deep squat: FK legs (hips/knees fully flexed, knees out), then the body is lowered until
    #   the boots rest on the floor
    pr = Prober(R)
    FEET = ("MR_Boot_L", "MR_Boot_R")
    squat = merge(base, {
        "cog_rot": (24.0, 0.0, 0.0), "hips": (10, 0, 0), "spine": (14, 0, 0), "neck": (-22, 0, 0),
        "head": (-16, 0, 0), "look": (0, 8),
        "leg_l": {"fk": (118.0, 16.0, 12.0), "knee": 142.0, "ankle": (34.0, 0.0)},
        "leg_r": {"fk": (118.0, 16.0, 12.0), "knee": 142.0, "ankle": (34.0, 0.0)},
        "arm_l": {"fk": (82.0, -12.0, 0.0), "elbow": 16.0}, "arm_r": {"fk": (82.0, -12.0, 0.0), "elbow": 16.0}})
    squat["cog"] = (0.0, 0.06, -0.40)
    squat = settle(pr, squat, target=0.0, meshes=FEET, iters=6)
    # 3 crossed-arm reach: right hand reaches far to the left, left hand to the right, under it
    cross = merge(base, {
        "spine": (4, 18, 0), "cog_rot": (0, 8, 0), "head": (0, 14, 0), "look": (20, 0),
        "arm_r": _ik((0.32, -0.36, 1.30), (0.9, -0.3, 0.1), (0, -0.2, 1), (-0.2, 0.2, 1.1)),
        "arm_l": _ik((-0.26, -0.30, 1.08), (-0.9, -0.3, -0.1), (0, 0.2, -1), (0.45, 0.1, 0.9)),
        "hand_r": "open", "hand_l": "relaxed"})
    # 4 large torso twist (left), hips square
    twist = merge(base, {
        "spine": (2, 55, 0), "cog_rot": (0, 10, 0), "neck": (0, 20, 0), "head": (0, 15, 0), "look": (25, 0),
        "arm_l": {"fk": (-10.0, -30.0, 0.0), "elbow": 30.0}, "arm_r": {"fk": (40.0, -30.0, 0.0), "elbow": 50.0}})
    # 5 kneel on the right knee (shin on the floor, toes tucked), left foot planted forward
    kneel = merge(base, {
        "cog": (0.0, 0.05, -0.46), "cog_rot": (4.0, 0.0, 0.0), "spine": (2, 0, 0), "head": (2, 0, 0),
        "leg_l": {"fk": (86.0, 8.0, 0.0), "knee": 88.0, "ankle": (4.0, 0.0)},
        "leg_r": {"fk": (-6.0, 4.0, 0.0), "knee": 96.0, "ankle": (10.0, 0.0), "toe": 62.0},
        "arm_l": {"fk": (40.0, -30.0, 0.0), "elbow": 70.0}, "hand_l": "relaxed"})
    kneel = settle(pr, kneel, target=0.0, meshes=("MR_Suit", "MR_Boot_L", "MR_Boot_R", "MR_Gear"), iters=6)
    # 6 planted hand support: lean forward, right palm flat on the floor outside the left foot
    support = merge(kneel, {"cog_rot": (20.0, 6.0, 0.0), "spine": (16, -6, 0), "neck": (-6, 0, 0),
                            "head": (-10, 0, 0), "look": (0, -30)})
    support = settle(pr, support, target=0.0, meshes=("MR_Suit", "MR_Boot_L", "MR_Boot_R", "MR_Gear"), iters=6)
    Wf = pr.world(support, ["foot_l", "thigh_r"])
    fl = Wf["foot_l"][:3, 3]
    palm = np.array([fl[0] - 0.33, fl[1] + 0.02, 0.0])
    # hand bone: fingers forward, back of the hand up; wrist a palm-thickness above the floor
    support["arm_r"] = _ik(palm + np.array([0.0, 0.07, 0.030]), (0.05, -1.0, -0.05), (0, 0, 1),
                           (palm[0] - 0.5, palm[1] + 0.3, 0.7))
    support["hand_r"] = "open"
    # 7 closed grip: both fists clenched in front of the chest
    grip = merge(base, {
        "arm_l": {"fk": (60.0, -20.0, 20.0), "elbow": 95.0, "wrist": (0.0, 0.0, 0.0)},
        "arm_r": {"fk": (60.0, -20.0, 20.0), "elbow": 95.0, "wrist": (0.0, 0.0, 0.0)},
        "hand_l": "fist", "hand_r": "fist", "face": expr("anger", 0.5)})
    seq = [(0, base), (20, reach), (45, reach), (65, base), (85, squat), (110, squat), (130, base),
           (150, cross), (175, cross), (195, base), (212, twist), (237, twist), (255, kneel), (270, kneel),
           (285, support), (300, support), (315, grip), (330, grip)]
    for f, p in seq:
        c.key(f, p)
    c.layers += [breathing(0.5)]
    c.markers += [(30, "overhead_reach"), (95, "deep_squat"), (160, "crossed_arm_reach"), (225, "torso_twist"),
                  (262, "kneel"), (292, "hand_support"), (322, "closed_grip")]
    return c

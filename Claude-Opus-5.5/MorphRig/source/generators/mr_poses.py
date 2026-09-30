"""MorphRig base poses (semantic) shared by all clips."""
import numpy as np
from mr_params import J, FOOT_DIR_L, v
from mr_anim import merge

ANKLE = {"l": J["foot_l"].copy(), "r": J["foot_r"].copy()}


def ankle(side, dx=0.0, dy=0.0, dz=0.0):
    a = ANKLE[side]
    return (a[0] + dx, a[1] + dy, a[2] + dz)


# arms hanging relaxed from the A-pose rest (abduction lowers the arm toward the body)
ARM_DOWN_L = {"fk": (4.0, -38.0, 4.0), "elbow": 14.0, "wrist": (6.0, 0.0, 12.0)}
ARM_DOWN_R = {"fk": (4.0, -38.0, 4.0), "elbow": 16.0, "wrist": (4.0, 0.0, 8.0)}

RELAXED = {
    "cog": (0.0, 0.0, -0.012),
    "hips": (0, 0, 0), "spine": (1.5, 0, 0), "neck": (-2, 0, 0), "head": (1, 0, 0),
    "clav_l": (-2, 0), "clav_r": (-2, 0),
    "arm_l": ARM_DOWN_L, "arm_r": ARM_DOWN_R,
    "foot_l": {"pos": ankle("l", 0.012, 0.0, 0.0), "yaw": 4.0},
    "foot_r": {"pos": ankle("r", -0.012, 0.0, 0.0), "yaw": -4.0},
    "hand_l": "relaxed", "hand_r": "relaxed",
    "blade": 0.0, "cell": 0, "beacon": {"parent": 0},
    "look": (0, 0), "jaw": 0.0, "face": {},
}

# combat ready stance: left foot forward, right back, knees flexed, hands up and free
COMBAT = {
    "cog": (0.0, 0.015, -0.075), "cog_rot": (6.0, -14.0, 0.0),
    "hips": (4, 0, 0), "spine": (4, 10, 0), "neck": (-4, 3, 0), "head": (-2, 1, 0),
    "clav_l": (2, 4), "clav_r": (3, 6),
    "arm_l": {"fk": (48.0, -26.0, 25.0), "elbow": 100.0, "wrist": (0.0, 0.0, 22.0)},
    "arm_r": {"fk": (35.0, -28.0, -10.0), "elbow": 70.0, "wrist": (15.0, 0.0, 0.0)},
    "foot_l": {"pos": ankle("l", 0.035, -0.135, 0.0), "yaw": 6.0},
    "foot_r": {"pos": ankle("r", -0.05, 0.155, 0.0), "yaw": -32.0},
    "hand_l": "loose_fist", "hand_r": "loose_fist",
    "blade": 0.0, "cell": 0, "beacon": {"parent": 0},
    "look": (0, -2), "jaw": 0.0, "face": {"browDown_L": 0.2, "browDown_R": 0.2, "squint_L": 0.15, "squint_R": 0.15},
}

WOUNDED = merge(COMBAT, {
    "cog": (0.02, 0.035, -0.10), "cog_rot": (12.0, -10.0, 5.0),
    "hips": (6, 0, 4), "spine": (10, 6, 6), "neck": (-8, 2, -2),
    "arm_l": {"fk": (30.0, -34.0, 40.0), "elbow": 108.0, "wrist": (10.0, 0.0, 40.0)},   # clutching the ribs
    "arm_r": {"fk": (20.0, -30.0, -6.0), "elbow": 60.0, "wrist": (10.0, 0.0, 6.0)},
    "foot_l": {"pos": ankle("l", 0.03, -0.11, 0.0), "yaw": 8.0},
    "foot_r": {"pos": ankle("r", -0.04, 0.13, 0.0), "yaw": -28.0},
    "face": {"browInnerUp_L": 0.5, "browInnerUp_R": 0.5, "browDown_L": 0.3, "browDown_R": 0.3,
             "squint_L": 0.35, "squint_R": 0.35, "mouthStretch_L": 0.25, "mouthStretch_R": 0.2},
    "jaw": 2.0,
})

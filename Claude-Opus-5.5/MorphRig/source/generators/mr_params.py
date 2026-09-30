"""MorphRig Operative proportions and joint landmarks (rest A-pose).

Conventions (Blender source): metres, +Z up, the character faces -Y, the
character's left side is +X, ground plane Z=0, origin between the feet.
Standing height (sole to top of hair) = 1.80 m.
"""
import numpy as np

HEIGHT = 1.80


def v(*a):
    return np.array(a, dtype=np.float64)


def nrm(x):
    x = np.asarray(x, dtype=np.float64)
    return x / np.linalg.norm(x)


# ---------------------------------------------------------------- spine/head
J = {}
J["root"] = v(0, 0, 0)
J["pelvis"] = v(0, 0.015, 0.955)
J["spine_01"] = v(0, 0.025, 1.040)
J["spine_02"] = v(0, 0.035, 1.160)
J["spine_03"] = v(0, 0.035, 1.285)
J["neck_01"] = v(0, 0.036, 1.455)
J["neck_02"] = v(0, 0.026, 1.522)
J["head"] = v(0, 0.012, 1.588)
J["head_end"] = v(0, 0.012, 1.785)

# ---------------------------------------------------------------- arms (left, mirrored)
ARM_DOWN_DEG = 45.0
J["clavicle_l"] = v(0.022, -0.002, 1.432)
J["upperarm_l"] = v(0.178, 0.030, 1.428)
_d_up = nrm(v(np.cos(np.radians(ARM_DOWN_DEG)), -0.06, -np.sin(np.radians(ARM_DOWN_DEG))))
UPPERARM_LEN = 0.292
FOREARM_LEN = 0.252
J["lowerarm_l"] = J["upperarm_l"] + UPPERARM_LEN * _d_up
_d_fo = nrm(_d_up + v(0, -0.20, 0))
J["hand_l"] = J["lowerarm_l"] + FOREARM_LEN * _d_fo
ARM_DIR_UP = _d_up
ARM_DIR_FO = _d_fo
# palm faces down/inward in the frontal plane, thumb points forward (-Y)
_palm_n = nrm(np.cross(v(0, -1, 0), _d_fo))  # roughly (-0.7,0,-0.7)
if _palm_n[2] > 0:
    _palm_n = -_palm_n
PALM_NORMAL_L = _palm_n
HAND_THUMB_DIR_L = nrm(np.cross(_d_fo, _palm_n))  # should point toward -Y
if HAND_THUMB_DIR_L[1] > 0:
    HAND_THUMB_DIR_L = -HAND_THUMB_DIR_L

# ---------------------------------------------------------------- legs (left, mirrored)
J["thigh_l"] = v(0.092, 0.005, 0.930)
J["calf_l"] = v(0.100, -0.012, 0.505)
J["foot_l"] = v(0.106, 0.020, 0.095)
_toe_out = np.radians(6.0)
FOOT_DIR_L = v(np.sin(_toe_out), -np.cos(_toe_out), 0.0)
J["ball_l"] = v(J["foot_l"][0], J["foot_l"][1], 0.0) + 0.132 * FOOT_DIR_L + v(0, 0, 0.034)
J["toe_end_l"] = J["ball_l"] + 0.070 * FOOT_DIR_L + v(0, 0, -0.004)
J["heel_l"] = v(J["foot_l"][0], J["foot_l"][1], 0.0) - 0.075 * FOOT_DIR_L  # ground pivot

SOLE_THICKNESS = 0.026


def mirror(p):
    q = np.array(p, dtype=np.float64).copy()
    q[..., 0] *= -1
    return q


for _k in list(J):
    if _k.endswith("_l"):
        J[_k[:-2] + "_r"] = mirror(J[_k])

# ---------------------------------------------------------------- head landmarks
EYE_R = 0.0125  # eyeball radius
H = {
    "eye_l": v(0.0318, -0.0650, 1.6720),
    "mouth": v(0.0, -0.0935, 1.6030),     # lip contact line centre (front-most point)
    "mouth_half_width": 0.0252,
    "nose_tip": v(0.0, -0.1148, 1.6375),
    "chin": v(0.0, -0.0915, 1.5710),
    "jaw_pivot_l": v(0.052, 0.008, 1.626),  # TMJ
    "ear_l": v(0.0715, 0.004, 1.648),
    "crown": v(0.0, 0.020, 1.785),
}
H["eye_r"] = mirror(H["eye_l"])
H["jaw_pivot_r"] = mirror(H["jaw_pivot_l"])
H["ear_r"] = mirror(H["ear_l"])
H["jaw"] = v(0.0, 0.004, 1.626)  # jaw bone head (midpoint of TMJ axis)

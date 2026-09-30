"""MorphRig's wholly authored, deterministic 96-entry motion library.

Blender metres: right +X, forward -Y, up +Z. Targets are ABSOLUTE wrist
and ankle positions in character authoring space, already transformed for
turns and root motion. No stock motion or downloaded body is used. Curves
are sampled into editable IK control actions and baked by the parent tool.

Every finite action is a sequence of intentional contact/weight poses;
gaits use fixed world-support velocity plus airborne return trajectories.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from pathlib import Path

FPS = 30
PI = math.pi
TAU = 2 * PI
ROOT = Path(__file__).resolve().parents[2]
_ALIGNMENT = None

FACE_KEYS = (
    "blink.L", "blink.R", "squint.L", "squint.R", "brow_raise.L", "brow_raise.R",
    "brow_lower.L", "brow_lower.R", "cheek.L", "cheek.R", "jaw", "lip_close",
    "smile.L", "smile.R", "frown.L", "frown.R", "width", "pucker", "funnel", "tongue",
    "eye_yaw.L", "eye_yaw.R", "eye_pitch.L", "eye_pitch.R",
    "viseme_closure", "viseme_labiodental", "viseme_open", "viseme_wide",
    "viseme_round", "viseme_tongue", "viseme_consonant",
)


def face(**values):
    result = dict.fromkeys(FACE_KEYS, 0.0)
    result.update(values)
    return result


expression_presets = {
    "neutral": face(),
    "joy_confidence": face(**{"smile.L": .72, "smile.R": .54, "cheek.L": .62,
                               "cheek.R": .48, "brow_raise.L": .16, "squint.L": .14,
                               "squint.R": .10}),
    "anger": face(**{"brow_lower.L": .85, "brow_lower.R": .77, "squint.L": .55,
                      "squint.R": .50, "frown.L": .32, "frown.R": .25, "lip_close": .72}),
    "concern_sadness": face(**{"brow_raise.L": .58, "brow_raise.R": .42,
                                 "brow_lower.L": .20, "brow_lower.R": .12,
                                 "frown.L": .40, "frown.R": .32, "squint.R": .10}),
    "surprise": face(**{"brow_raise.L": .92, "brow_raise.R": .88, "jaw": .50,
                         "funnel": .52, "viseme_open": .30}),
    "pain": face(**{"brow_lower.L": .70, "brow_lower.R": .93, "squint.L": .68,
                     "squint.R": .82, "cheek.L": .20, "cheek.R": .28,
                     "frown.L": .64, "frown.R": .48, "jaw": .18}),
    "focus": face(**{"brow_lower.L": .30, "brow_lower.R": .24, "squint.L": .35,
                      "squint.R": .29, "lip_close": .18}),
}


def clamp(x, low=0., high=1.):
    return min(high, max(low, x))


def ease(x):
    x = clamp(x)
    return x*x*(3 - 2*x)


def smoother(x):
    x = clamp(x)
    return x*x*x*(x*(x*6 - 15) + 10)


def rotate_xyz(v, e):
    x, y, z = v
    cx, sx = math.cos(e[0]), math.sin(e[0])
    cy, sy = math.cos(e[1]), math.sin(e[1])
    cz, sz = math.cos(e[2]), math.sin(e[2])
    y, z = cx*y-sx*z, sx*y+cx*z
    x, z = cy*x+sy*z, -sy*x+cy*z
    return [cz*x-sz*y, sz*x+cz*y, z]


def joint_positions(p):
    """Exact source rig hip and shoulder heads, independent of bpy."""
    def pq(v):
        return rotate_xyz(v, p["pelvis_rot"])
    def tq(v):
        return pq(rotate_xyz(v, p["torso"]))
    def cq(v):
        return tq(rotate_xyz(v, p["chest"]))
    hips, shoulders = {}, {}
    for side, s in (("L", -1), ("R", 1)):
        offset = pq([s*.10, 0., 0.])
        hips[side] = [p["pelvis"][i]+offset[i] for i in range(3)]
        a, b, c = pq([0., 0., .11]), tq([0., 0., .25]), cq([s*.19, 0., .09])
        shoulders[side] = [p["pelvis"][i]+a[i]+b[i]+c[i] for i in range(3)]
    return hips, shoulders


def fit_leg_height(p, maximum=.838):
    """Lower hips from authored nominal height only when support reach needs it.

    Keep original foot trajectories and controller-canceling contact velocity.
    The same bound handles body yaw and independently rotated lying pelvis.
    """
    hips, _ = joint_positions(p)
    desired_z = p["pelvis"][2]
    for side in ("L", "R"):
        h, f = hips[side], p["feet"][side]
        horizontal2 = (h[0]-f[0])**2 + (h[1]-f[1])**2
        if horizontal2 < maximum**2:
            limit = f[2]+math.sqrt(maximum**2-horizontal2)-(h[2]-p["pelvis"][2])
            desired_z = min(desired_z, limit)
    p["pelvis"][2] = desired_z
    return p


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _unit(v):
    length = math.sqrt(_dot(v, v))
    return [x/length for x in v] if length > 1e-10 else [1., 0., 0.]


def _axis_rotate(v, n, angle):
    c, s = math.cos(angle), math.sin(angle)
    cross = _cross(n, v)
    dot = _dot(n, v)
    return [v[i]*c+cross[i]*s+n[i]*dot*(1-c) for i in range(3)]


FLOOR_CONTACT_ENTRIES = {
    "jump_start", "jump_land", "land_heavy", "deploy", "knockdown_front", "knockdown_back",
    "prone_front", "prone_back", "getup_front", "getup_back", "death_front", "death_back",
    "dead_front", "dead_back",
}


def fit_boot_contact(p):
    """Heel/toe pivots from the authored beveled sole and toe-box support.

    Rotating a tall toe-down boot around an unchanged ankle would put its
    bevel beneath the floor during kneel/getup transitions. Raise the ankle
    only by the geometry-required pivot height, retaining authored X/Y.
    """
    boxes = [([0., -.068, -.086], [.103, .220, .028], .009),
             ([0., -.064, -.042], [.099, .217, .106], .022),
             ([0., -.149, -.061], [.098, .070, .071], .015),
             ([0., -.175, -.035], [.065, .022, .016], .004)]
    for side in ("L", "R"):
        rotation = p["foot_rot"][side]
        normal = [rotate_xyz(v, rotation)[2] for v in ([1., 0., 0.], [0., 1., 0.], [0., 0., 1.])]
        needed = 0.
        for center, size, bevel in boxes:
            extent = sum(abs(normal[i])*(size[i]/2-bevel) for i in range(3))+bevel
            needed = max(needed, extent-_dot(normal, center))
        p["feet"][side][2] = max(p["feet"][side][2], needed+.0006)
    return p


def fit_support_planes(p):
    """Author contact bend planes using the FITTED IK pole-angle offsets.

    Wrist/ankle targets remain untouched. The old neutral-space pole targets
    incorrectly rotated elbows/knees underneath a low lying/supported body.
    Solve the two-bone joint circle and constrain its contact height, then
    inverse-rotate by the fitted solver offset to place the editable pole.
    Original clear planes remain exactly unchanged, including all high poses.
    """
    hips, shoulders = joint_positions(p)
    lengths = {"knee": (.410883195, .430726131), "elbow": (.283019434, .218918934)}
    for side in ("L", "R"):
        for kind, starts, group in (("knee", hips, "feet"), ("elbow", shoulders, "hands")):
            start, target = starts[side], p[group][side]
            delta = [target[i]-start[i] for i in range(3)]
            distance = math.sqrt(_dot(delta, delta))
            if distance < .015:
                continue
            axis = [x/distance for x in delta]
            first, second = lengths[kind]
            along = (first*first-second*second+distance*distance)/(2*distance)
            radius = math.sqrt(max(0., first*first-along*along))
            if radius < 1e-6:
                continue
            center = [start[i]+along*axis[i] for i in range(3)]
            original = [p["poles"][kind+"."+side][i]-start[i] for i in range(3)]
            axial = _dot(original, axis)
            radial = [original[i]-axis[i]*axial for i in range(3)]
            radial_length = math.sqrt(_dot(radial, radial))
            # Constant measured pole-to-joint bend offsets in this fitted rig.
            offset = (.22714080 if kind == "knee" else 1.50062950)*(1 if side == "L" else -1)
            bend = _axis_rotate(_unit(radial), axis, offset)
            minimum = .100 if kind == "knee" else (.150 if side == "L" else .190)
            if center[2]+radius*bend[2] >= minimum:
                continue
            up = [-axis[i]*axis[2]+(1. if i == 2 else 0.) for i in range(3)]
            up_length = math.sqrt(_dot(up, up))
            if up_length < 1e-6:
                continue
            up = [x/up_length for x in up]
            horizontal = _unit(_cross(axis, up))
            vertical_weight = clamp((minimum-center[2])/(radius*up_length), -1., 1.)
            horizontal_weight = math.sqrt(max(0., 1-vertical_weight*vertical_weight))
            if _dot(bend, horizontal) < 0:
                horizontal_weight *= -1
            desired = [up[i]*vertical_weight+horizontal[i]*horizontal_weight for i in range(3)]
            pole_direction = _axis_rotate(desired, axis, -offset)
            p["poles"][kind+"."+side] = [start[i]+axis[i]*axial+pole_direction[i]*radial_length for i in range(3)]
    # An open palm supports the low face-down states without curling the
    # thumb/tips into the ground; all held-prop manipulation stays separate.
    for side in ("L", "R"):
        height = p["hands"][side][2]
        rotation = p["hand_rot"][side]
        if height < .09 and rotation[0] > 1.2:
            weight = ease((.09-height)/.05)
            rotation[0] = lerp(rotation[0], PI/2+.12, weight)
            p["curls"][side] = [lerp(c, min(c, 0. if i == 0 else .025), weight)
                                 for i, c in enumerate(p["curls"][side])]
    return p


def lerp(a, b, f):
    return a + (b-a)*f


def blend(a, b, f):
    if isinstance(a, dict):
        return {k: blend(a.get(k, b.get(k)), b.get(k, a.get(k)), f) for k in set(a) | set(b)}
    if isinstance(a, (tuple, list)):
        return [blend(x, y, f) for x, y in zip(a, b)]
    return lerp(a, b, f)


def base(combat=True):
    p = {
        "root": [0., 0., 0.], "pelvis": [0., 0., .92 if combat else .94],
        "pelvis_rot": [0., 0., 0.], "torso": [.045 if combat else 0., 0., 0.],
        "chest": [0., 0., 0.], "head": [0., 0., 0.],
        "hands": {"L": [-.29, -.20, 1.14], "R": [.33, -.25, 1.23]} if combat else
                 {"L": [-.40, -.015, .94], "R": [.40, -.015, .94]},
        "feet": {"L": [-.125, -.045, .10], "R": [.135, .065, .10]} if combat else
                {"L": [-.11, 0., .10], "R": [.11, 0., .10]},
        "hand_rot": {"L": [-.65, .12, -.12], "R": [-.85, -.12, .12]} if combat else
                    {"L": [0., 0., 0.], "R": [0., 0., 0.]},
        "foot_rot": {"L": [0., 0., -.07], "R": [0., 0., .07]},
        "poles": {"elbow.L": [-.67, .10, 1.12], "elbow.R": [.67, .10, 1.12],
                  "knee.L": [-.16, -.48, .51], "knee.R": [.16, -.48, .51]},
        "curls": {"L": [.30, .18, .23, .28, .35], "R": [.35, .22, .26, .32, .38]},
        "spreads": {"L": .18, "R": .14}, "face": face(),
        "blade": 0.,
        "secondary": [0., 0., 0.],
    }
    return p


def pose(*, relaxed=False, pel=None, pelvis_rot=None, torso=None, chest=None,
         head=None, lh=None, rh=None, lf=None, rf=None, lrot=None, rrot=None,
         foot_l=None, foot_r=None, lc=None, rc=None, expression=None, f=None,
         blade=None, cell=None, beacon=None, poles=None, spreads=None):
    """Compact complete-pose notation; no stale controls survive a clip."""
    p = base(not relaxed)
    for key, value in (("pelvis", pel), ("pelvis_rot", pelvis_rot), ("torso", torso),
                       ("chest", chest), ("head", head), ("cell", cell), ("beacon", beacon)):
        if value is not None:
            p[key] = list(value)
    for key, side, value in (("hands", "L", lh), ("hands", "R", rh),
                             ("feet", "L", lf), ("feet", "R", rf),
                             ("hand_rot", "L", lrot), ("hand_rot", "R", rrot),
                             ("foot_rot", "L", foot_l), ("foot_rot", "R", foot_r),
                             ("curls", "L", lc), ("curls", "R", rc)):
        if value is not None:
            p[key][side] = list(value)
    if expression:
        p["face"].update(expression_presets[expression])
    if f:
        p["face"].update(f)
    if blade is not None:
        p["blade"] = blade
    if poles:
        p["poles"].update(poles)
    if spreads:
        p["spreads"].update(spreads)
    return p


def staged(stages, u):
    """Smooth piecewise key poses with exact authored endpoints/contact holds."""
    if u <= stages[0][0]:
        return copy.deepcopy(stages[0][1])
    for (a, pa), (b, pb) in zip(stages, stages[1:]):
        if u <= b:
            return blend(pa, pb, ease((u-a)/(b-a)))
    return copy.deepcopy(stages[-1][1])


def rotated(p, yaw):
    p = copy.deepcopy(p)
    c, s = math.cos(yaw), math.sin(yaw)
    def r(v):
        return [c*v[0]-s*v[1], s*v[0]+c*v[1], v[2]]
    for key in ("pelvis", "cell", "beacon"):
        if key in p:
            p[key] = r(p[key])
    for key in ("hands", "feet", "poles"):
        p[key] = {k: r(v) for k, v in p[key].items()}
    p["pelvis_rot"][2] += yaw
    for key in ("hand_rot", "foot_rot"):
        for side in ("L", "R"):
            p[key][side][2] += yaw
    return p


DIRECTIONS = {"f": (0., -1.), "fl": (-2**-.5, -2**-.5), "l": (-1., 0.),
              "bl": (-2**-.5, 2**-.5), "b": (0., 1.), "br": (2**-.5, 2**-.5),
              "r": (1., 0.), "fr": (2**-.5, -2**-.5)}


def gait(mode, direction, u, duration):
    """Facing-retained travel with analytical planted support, not yaw reuse.

    stance target derivative is exactly -nominal_speed in body space.
    Adding controller displacement makes the support ankle world-stationary.
    Lateral/diagonal swing arcs route around the other leg; leading and
    trailing feet retain asymmetric toe direction and cybernetic arm timing.
    """
    dx, dy = DIRECTIONS[direction]
    speed = {"walk": 1.5, "run": 4.0, "sprint": 6.5}[mode]
    stance = {"walk": .62, "run": .37, "sprint": .32}[mode]
    height = {"walk": .105, "run": .20, "sprint": .255}[mode]
    stride = speed * duration * stance
    p = base(False)
    lateral = abs(dx)
    width = .115 + .09*lateral
    p["pelvis"] = [dx*.018*math.sin(TAU*u), .008*math.sin(TAU*u),
                   {"walk": .925, "run": .875, "sprint": .85}[mode]
                   + {"walk": .016, "run": .045, "sprint": .055}[mode]*math.cos(2*TAU*u)]
    lean = {"walk": .07, "run": .19, "sprint": .34}[mode]
    p["torso"] = [-dy*lean, dx*lean*.70, .025*math.sin(TAU*u)]
    p["chest"] = [.01*math.sin(2*TAU*u), 0., -.045*math.sin(TAU*u)]
    p["head"] = [-p["torso"][0]*.50, -p["torso"][1]*.60, .02*math.sin(TAU*u)]
    for side, shift, sign in (("L", 0., -1), ("R", .5, 1)):
        ph = (u + shift) % 1
        airborne = ph > stance
        if not airborne:
            along = stride*(.5 - ph/stance)
            lift = 0.
            swing = 0.
            pitch = 0.  # planted sole remains flat; heel return starts airborne
        else:
            sw = (ph-stance)/(1-stance)
            along = stride*(-.5 + smoother(sw))
            lift = height*math.sin(PI*sw)**1.35
            swing = math.sin(PI*sw)
            pitch = -.25*math.sin(PI*sw)
        # Crossover steps pass on opposite fore/aft tracks rather than
        # intersecting the shins when travelling laterally.
        fore_track = sign*.070*lateral + sign*.095*lateral*swing
        p["feet"][side] = [sign*width + dx*along + sign*.035*lateral*swing,
                            dy*along + fore_track, .10 + lift]
        toe_yaw = dx*.10 + sign*.055
        p["foot_rot"][side] = [pitch, -.08*dx*swing, toe_yaw]
        p["poles"]["knee."+side] = [sign*.17 + dx*.12,
                                              -.42 + dy*.10, .52]
        arm = math.sin(TAU*(u+shift))
        amount = {"walk": .11, "run": .18, "sprint": .23}[mode]
        if mode == "walk":
            p["hands"][side] = [sign*.36-dx*amount*arm*.45,
                                  -.015-dy*amount*arm, .95+.025*math.cos(TAU*(u+shift))]
            p["hand_rot"][side] = [-.06-dy*.22*arm, sign*.05, sign*.07]
            p["curls"][side] = [.20, .13, .16, .20, .25]
        else:
            # Elbows folded and arms pumped across torso: a distinct run,
            # while full-effort sprint leans/flys and has higher heel return.
            asym = .018 if side == "R" else -.012
            p["hands"][side] = [sign*.29-dx*amount*arm*.40,
                                  -.22-dy*amount*arm, 1.19+amount*.40*arm+asym]
            p["hand_rot"][side] = [-1.0+arm*.18, sign*.1, sign*.1]
            p["curls"][side] = [.50, .54, .63, .69, .74]
    p["face"].update(expression_presets["focus"] if mode != "walk" else face())
    p["secondary"] = [.035*math.sin(TAU*u-.5), .024*math.sin(TAU*u-.8),
                       .017*math.sin(2*TAU*u-.3)]
    return fit_leg_height(p, .830)


def floor_pose(front=True, dead=False):
    if front:
        p = pose(pel=[-.018, .025, .135], pelvis_rot=[PI/2, 0., .035], torso=[0., 0., 0.],
                 chest=[-.045, 0., 0.], head=[-.13, .18, -.22],
                 lh=[-.29, -.52, .025], rh=[.34, -.44, .027],
                 lf=[-.13, .76, .190], rf=[.18, .70, .190],
                 lrot=[PI/2, 0., -.10], rrot=[PI/2, 0., .18],
                 foot_l=[PI/2, 0., -.07], foot_r=[PI/2, 0., .18],
                 lc=[.10, .05, .05, .10, .10], rc=[.12, .09, .10, .13, .16],
                 poles={"knee.L": [-.13, .36, .13], "knee.R": [.18, .35, .18],
                        "elbow.L": [-.50, -.25, .12], "elbow.R": [.54, -.18, .15]},
                 expression="pain")
    else:
        p = pose(pel=[.025, -.03, .16], pelvis_rot=[-PI/2, -.05, -.06], torso=[0., 0., 0.],
                 chest=[.06, 0., 0.], head=[.10, -.12, .12],
                 lh=[-.36, .25, .027], rh=[.39, .17, .055],
                 lf=[-.14, -.75, .055], rf=[.22, -.64, .055],
                 lrot=[-PI/2, .12, -.27], rrot=[-PI/2, -.10, .18],
                 foot_l=[-PI/2, 0., -.18], foot_r=[-PI/2, 0., .26],
                 lc=[.20, .10, .13, .18, .24], rc=[.22, .16, .21, .25, .31],
                 poles={"knee.L": [-.17, -.36, .22], "knee.R": [.22, -.29, .25],
                        "elbow.L": [-.57, .41, .13], "elbow.R": [.57, .37, .16]},
                 expression="pain")
    if dead:
        p["face"] = face(**{"blink.L": 1., "blink.R": 1., "jaw": .09,
                             "frown.L": .15, "frown.R": .11})
        if front:
            p["hands"]["L"] = [-.36, -.44, .025]
            p["hands"]["R"] = [.28, -.64, .027]
            p["head"] = [-.11, .30, -.28]
            p["curls"]["R"] = [.27, .18, .26, .30, .37]
        else:
            p["hands"]["L"] = [-.43, .18, .027]
            p["hands"]["R"] = [.30, .36, .055]
            p["head"] = [.10, -.28, .17]
            p["feet"]["R"] = [.25, -.62, .055]
            p["curls"]["L"] = [.18, .12, .17, .21, .26]
    return p


def channel_pose():
    return pose(pel=[0., .015, .91], torso=[.08, -.02, -.08], chest=[0., 0., .08],
                rh=[.22, -.445, 1.33], lh=[.06, -.31, 1.25],
                lrot=[-1.35, .15, -.18], rrot=[-PI/2, -.10, 0.],
                lc=[.35, .20, .28, .36, .42], rc=[.24, .10, .14, .23, .27],
                expression="focus", head=[-.06, 0., 0.])


def charge_pose():
    return pose(pel=[-.035, .045, .84], torso=[.12, -.06, -.23], chest=[0., 0., -.15],
                rh=[.35, .005, 1.32], lh=[-.04, -.20, 1.23],
                lf=[-.17, -.12, .10], rf=[.21, .16, .10],
                lrot=[-1.3, .15, .22], rrot=[-.80, -.28, .30],
                lc=[.15, .12, .12, .12, .16], rc=[.72, .75, .80, .82, .85],
                expression="focus", head=[-.02, .06, .32])


def uplink_pose():
    return pose(pel=[0., 0., .925], torso=[.035, 0., .10], chest=[0., 0., .06],
                rh=[.18, -.29, 1.16], lh=[-.01, -.34, 1.21],
                lrot=[-1.1, .15, .20], rrot=[-1.05, -.30, .38],
                lc=[.52, .08, .44, .58, .66], rc=[.20, .20, .25, .31, .37],
                head=[.20, 0., -.12], expression="focus")


def stun_pose():
    return pose(pel=[.035, .04, .85], torso=[-.12, .11, -.12], chest=[.06, -.14, .08],
                head=[.18, .23, -.16], lh=[-.39, -.09, 1.13], rh=[.42, -.04, 1.01],
                lrot=[-.52, .15, -.35], rrot=[-.15, -.25, .23],
                lc=[.21, .10, .13, .22, .30], rc=[.19, .15, .21, .29, .39],
                lf=[-.15, -.11, .10], rf=[.19, .14, .10],
                expression="concern_sadness", f={"blink.L": .21, "squint.R": .62})


def sleep_pose():
    # A compact supported sit, rather than an unsupported sleeping stand.
    return pose(pel=[-.015, .005, .27], pelvis_rot=[-.10, 0., -.12], torso=[.28, 0., .03],
                chest=[.18, 0., 0.], head=[.45, .12, -.08],
                lh=[-.14, -.28, .45], rh=[.18, -.31, .48],
                lf=[-.24, -.40, .12], rf=[.27, -.34, .11],
                lrot=[-.52, .18, -.18], rrot=[-.58, -.17, .23],
                lc=[.30, .25, .29, .34, .39], rc=[.30, .22, .28, .33, .40],
                poles={"knee.L": [-.35, -.26, .45], "knee.R": [.35, -.22, .47],
                       "elbow.L": [-.40, -.01, .56], "elbow.R": [.41, -.02, .57]},
                f={"blink.L": 1., "blink.R": 1., "jaw": .035},
                )


def alignment():
    global _ALIGNMENT
    if _ALIGNMENT is None:
        path = ROOT / "source/audio/dialogue_alignment.json"
        _ALIGNMENT = json.loads(path.read_text()) if path.exists() else {"duration_seconds": 15., "phonemes": [], "performance_cues": []}
    return _ALIGNMENT


# Frame INTERVALS; inclusive sample count is intervals + 1.
INTERVALS = {
    "idle_relaxed": 90, "idle_combat": 84, "idle_wounded": 96,
    "sprint_f": 12, "start_f": 18, "stop_f": 21, "turn_l90": 24, "turn_r90": 24,
    "pivot_l180": 27, "pivot_r180": 27, "jump_start": 21, "jump_air": 21,
    "jump_land": 24, "fall": 24, "land_heavy": 33,
    "dash_f": 15, "dash_b": 15, "dash_l": 15, "dash_r": 15,
    "blink_out": 12, "blink_in": 15,
    "melee_1": 27, "melee_2": 30, "melee_3": 33, "ranged_fire": 12, "ranged_burst": 21,
    "reload": 66, "cast_directional": 27, "cast_ground": 36, "cast_self": 27,
    "channel_start": 18, "channel_loop": 36, "channel_end": 18, "channel_interrupt": 15,
    "charge_start": 24, "charge_hold": 30, "charge_release": 24, "charge_cancel": 18,
    "deploy": 48, "uplink_start": 27, "uplink_loop": 45, "uplink_end": 21, "uplink_cancel": 18,
    "hit_f": 12, "hit_b": 12, "hit_l": 12, "hit_r": 12,
    "stun_start": 36, "stun_loop": 60, "stun_end": 33, "knockback": 39,
    "knockup_start": 24, "knockup_air": 27, "knockdown_front": 54, "knockdown_back": 57,
    "prone_front": 60, "prone_back": 60, "getup_front": 81, "getup_back": 84,
    "sleep_start": 66, "sleep_loop": 75, "sleep_end": 66,
    "death_front": 81, "death_back": 87, "respawn": 75, "greet": 72, "victory": 90, "defeat": 84,
}
for direction in DIRECTIONS:
    INTERVALS["walk_" + direction] = 24
    INTERVALS["run_" + direction] = 18


def _event(name, u, **data):
    return (name, u, data)


EVENTS = {
    "start_f": [_event("left_plant", .24), _event("locomotion_blend_begin", .40), _event("right_plant", .78)],
    "stop_f": [_event("brake_left_plant", .22), _event("right_plant", .63), _event("stable", .92)],
    "jump_start": [_event("anticipation", .18), _event("takeoff", .78)],
    "jump_land": [_event("land_contact", 0.), _event("compression", .32), _event("recover", .72)],
    "land_heavy": [_event("heavy_land_contact", 0.), _event("hand_support", .33), _event("recover", .76)],
    "blink_out": [_event("blink_anticipation", .25), _event("blink_disappear", .75), _event("teleport_actor", 1.)],
    "blink_in": [_event("blink_reappear", 0.), _event("feet_plant", .28), _event("stable", .87)],
    "melee_1": [_event("blade_extend", .13), _event("hit_window_open", .40), _event("hit_window_close", .57), _event("recovery", .68), _event("blade_retract", .94)],
    "melee_2": [_event("blade_extend", .10), _event("hit_window_open", .38), _event("hit_window_close", .57), _event("recovery", .71), _event("blade_retract", .95)],
    "melee_3": [_event("blade_extend", .13), _event("hit_window_open", .45), _event("hit_window_close", .65), _event("recovery", .76), _event("blade_retract", .97)],
    "ranged_fire": [_event("muzzle_fire", .25, shot=1), _event("recovery", .58)],
    "ranged_burst": [_event("muzzle_fire_1", .19, shot=1), _event("muzzle_fire_2", .43, shot=2), _event("muzzle_fire_3", .67, shot=3), _event("recovery", .78)],
    "reload": [_event("cell_left_grasp", .20), _event("cell_detach", .29), _event("cell_hand_transfer", .40), _event("cell_align", .59), _event("cell_insert", .74), _event("cell_attach_emitter", .77), _event("left_release", .83)],
    "cast_directional": [_event("cast_prepare", .15), _event("cast_release", .47), _event("recovery", .72)],
    "cast_ground": [_event("ground_look", .16), _event("cast_release", .50), _event("recovery", .76)],
    "cast_self": [_event("cast_prepare", .17), _event("cast_release", .51), _event("recovery", .74)],
    "channel_start": [_event("channel_enter", .82)],
    "channel_loop": [_event("channel_pulse", .50)],
    "channel_end": [_event("channel_complete", .15), _event("channel_exit", .92)],
    "channel_interrupt": [_event("channel_abort", 0.), _event("channel_recoil", .26), _event("control_restore", .90)],
    "charge_start": [_event("charge_enter", .73)],
    "charge_hold": [_event("charge_pulse", .50)],
    "charge_release": [_event("charge_release", .42), _event("recovery", .72)],
    "charge_cancel": [_event("charge_vent", .18), _event("charge_exit", .85)],
    "deploy": [_event("beacon_left_grasp", .13), _event("beacon_detach", .20), _event("beacon_contact", .57), _event("beacon_release", .65), _event("beacon_activate", .73)],
    "uplink_start": [_event("uplink_console_touch", .55), _event("uplink_enter", .86)],
    "uplink_loop": [_event("uplink_console_pulse", .43)],
    "uplink_end": [_event("uplink_complete", .22), _event("control_restore", .92)],
    "uplink_cancel": [_event("uplink_abort", 0.), _event("control_restore", .90)],
    "stun_start": [_event("control_lost", .18), _event("stun_enter", .84)],
    "stun_end": [_event("focus_return", .44), _event("control_restore", .90)],
    "knockback": [_event("forced_travel_begin", .10), _event("left_catch", .37), _event("right_catch", .66), _event("stable", .94)],
    "knockup_start": [_event("forced_launch", .22), _event("air_enter", .86)],
    "knockdown_front": [_event("left_knee_contact", .35), _event("palms_contact", .56), _event("front_floor_contact", .80)],
    "knockdown_back": [_event("seat_contact", .49), _event("right_hand_contact", .56), _event("back_floor_contact", .83)],
    "getup_front": [_event("palms_support", .12), _event("knees_support", .31), _event("left_foot_plant", .53), _event("right_foot_plant", .73), _event("control_restore", .95)],
    "getup_back": [_event("right_palm_support", .14), _event("seat_support", .27), _event("left_foot_plant", .50), _event("right_foot_plant", .67), _event("control_restore", .95)],
    "sleep_start": [_event("sleep_buckle", .21), _event("seat_contact", .62), _event("sleep_enter", .92)],
    "sleep_end": [_event("wake_eyes", .13), _event("left_foot_plant", .52), _event("right_foot_plant", .74), _event("control_restore", .95)],
    "death_front": [_event("death_commit", .06), _event("knees_contact", .30), _event("palms_contact", .49), _event("front_body_contact", .73), _event("terminal_pose", .94)],
    "death_back": [_event("death_commit", .06), _event("seat_contact", .43), _event("back_body_contact", .71), _event("terminal_pose", .94)],
    "respawn": [_event("respawn_activate", .18), _event("props_reset", .42), _event("feet_plant", .63), _event("control_restore", .94)],
    "greet": [_event("greeting_peak", .43), _event("settle", .87)],
    "victory": [_event("victory_raise", .40), _event("victory_salute", .60), _event("settle", .94)],
    "defeat": [_event("defeat_exhale", .41), _event("resolve_return", .77)],
}


def entry_metadata(row):
    name = row["id"]
    form = row["form"]
    if form == "pose":
        intervals = 1
    elif name == "dialogue":
        intervals = round(alignment()["duration_seconds"] * FPS)
    else:
        intervals = INTERVALS[name]
    duration = intervals / FPS
    states = {
        "channel_start": ("combat", "channel"), "channel_loop": ("channel", "channel"),
        "channel_end": ("channel", "combat"), "channel_interrupt": ("channel_any_phase", "combat"),
        "charge_start": ("combat", "charge"), "charge_hold": ("charge", "charge"),
        "charge_release": ("charge_any_phase", "combat"), "charge_cancel": ("charge_any_phase", "combat"),
        "uplink_start": ("combat", "uplink"), "uplink_loop": ("uplink", "uplink"),
        "uplink_end": ("uplink", "combat"), "uplink_cancel": ("uplink_any_phase", "combat"),
        "jump_start": ("grounded", "jump_air"), "jump_air": ("jump_air", "jump_air"),
        "fall": ("air", "fall"), "jump_land": ("jump_air", "grounded"), "land_heavy": ("fall", "grounded"),
        "stun_start": ("living", "stun"), "stun_loop": ("stun", "stun"), "stun_end": ("stun", "combat"),
        "knockup_start": ("living", "knockup_air"), "knockup_air": ("knockup_air", "knockup_air"),
        "knockdown_front": ("living", "prone_front"), "knockdown_back": ("living", "prone_back"),
        "prone_front": ("prone_front", "prone_front"), "prone_back": ("prone_back", "prone_back"),
        "getup_front": ("prone_front", "combat"), "getup_back": ("prone_back", "combat"),
        "sleep_start": ("living", "sleep"), "sleep_loop": ("sleep", "sleep"), "sleep_end": ("sleep", "combat"),
        "death_front": ("living_any_phase", "dead_front"), "death_back": ("living_any_phase", "dead_back"),
        "dead_front": ("dead_front", "dead_front"), "dead_back": ("dead_back", "dead_back"),
        "respawn": ("dead", "combat"), "blink_out": ("combat", "blink_hidden"), "blink_in": ("blink_hidden", "combat"),
    }
    state_in, state_out = states.get(name, ("combat", "combat"))
    if form == "loop" and name.startswith(("idle_", "walk_", "run_", "sprint_")):
        state_in = state_out = name
    layer = "full_body"
    if name.startswith(("idle_", "walk_", "run_", "sprint_", "turn_", "pivot_")) or name in ("start_f", "stop_f"):
        layer = "base_locomotion"
    elif name.startswith("aim_"):
        layer = "upper_body_pose"
        state_in = state_out = "aim"
    elif form == "additive":
        layer = "additive_upper_body"
        state_in = state_out = "living_base_preserved"
    elif name in ("ranged_fire", "ranged_burst", "cast_directional"):
        layer = "upper_body"
    speed = 150 if name.startswith("walk_") else 400 if name.startswith("run_") else 650 if name == "sprint_f" else 0
    ev = list(EVENTS.get(name, []))
    if name.startswith(("walk_", "run_", "sprint_")):
        stance = .62 if name.startswith("walk_") else .32 if name.startswith("sprint_") else .37
        ev = [_event("foot_contact.L", 0., side="L"), _event("foot_release.L", stance, side="L"),
              _event("foot_contact.R", .50, side="R"), _event("foot_release.R", (.50+stance)%1, side="R")]
    if name.startswith("dash_"):
        ev = [_event("dash_begin", .13), _event("dash_drive", .27), _event("dash_brake", .78), _event("dash_end", 1.)]
    if name.startswith(("turn_", "pivot_")):
        ev = [_event("pivot_support", .15), _event("swing_foot_plant", .54), _event("trailing_foot_plant", .81), _event("facing_commit", .94)]
    if name.startswith("hit_"):
        ev = [_event("impact_peak", .25), _event("recovery", .67)]
    if name == "dialogue":
        ev = [(cue["event"], cue["time"] / duration, {"description": cue["description"]}) for cue in alignment()["performance_cues"]]
    markers = []
    for marker, u, extra in ev:
        frame = 1 + round(clamp(u)*intervals)
        markers.append({"name": marker, "frame": frame, "time": (frame-1)/FPS, **extra})
    markers.sort(key=lambda x: (x["frame"], x["name"]))
    if layer == "base_locomotion":
        movement_rule = "base locomotion; capsule and CharacterMovement own travel; gait phase follows actual speed and planted turns commit actor facing on facing_commit"
    elif layer != "full_body":
        movement_rule = "base locomotion preserved; action, aim or additive reaction is masked above spine_01"
    elif name == "respawn":
        movement_rule = "explicit respawn bypasses dead, stasis and action gates; clears disables, facial overrides and deployed prop instances, then restores living locomotion"
    else:
        movement_rule = "full-body action owns stance; 140 ms snapshot crossfade from the captured evaluated pose; unrelated actions wait for recovery or explicit interruption"
    # Match AMorphOperative::Priority. Respawn is an explicit request exception,
    # not a priority greater than death; it clears the terminal/disable gates.
    priority = (100 if name.startswith(("death_", "dead_")) else
                85 if name.startswith("knockup_") else
                80 if name.startswith(("knockdown_", "prone_", "getup_")) else
                70 if name.startswith("stun_") else
                60 if name.startswith("sleep_") else 0)
    result = {"duration": duration, "duration_seconds": duration, "frame_count": intervals+1,
              "frame_start": 1, "frame_end": intervals+1, "sample_rate": FPS,
              "loop": form == "loop", "static_pose": form == "pose", "events": markers,
              "speed_cm_s": speed, "layer": layer, "intended_layer": layer, "entry_state": state_in, "exit_state": state_out,
              "authorship": "original procedural IK targets and authored pose-stage curves",
              "root_motion_policy": row["root_movement"],
              "movement_rule": movement_rule,
              "interrupt_blend_seconds": .14,
              "priority": priority}
    if name.startswith("dash_"):
        dx, dy = DIRECTIONS[name.split("_")[1]]
        result["nominal_root_displacement_m"] = [dx*2., dy*2., 0.]
    if name.startswith(("turn_", "pivot_")):
        result["facing_delta_degrees"] = (-1 if "_l" in name else 1)*(180 if name.startswith("pivot") else 90)
    if name.startswith("aim_"):
        _, pitch, yaw = name.split("_")
        result["aim_yaw_degrees"] = {"left": -60, "center": 0, "right": 60}[yaw]
        result["aim_pitch_degrees"] = {"down": -35, "level": 0, "up": 35}[pitch]
        result["aim_sign_convention"] = "yaw positive toward character right (+X); pitch positive up (+Z); facing -Y"
    if name in ("reload", "deploy"):
        result["contact_rule"] = "animated prop bone world target while held; attachment changes occur only on named contact/release events"
    return result


def changed(p, **values):
    q = copy.deepcopy(p)
    simple = {"pel": "pelvis", "pelvis_rot": "pelvis_rot", "torso": "torso",
              "chest": "chest", "head": "head", "cell": "cell", "beacon": "beacon"}
    paired = {"lh": ("hands", "L"), "rh": ("hands", "R"), "lf": ("feet", "L"),
              "rf": ("feet", "R"), "lrot": ("hand_rot", "L"), "rrot": ("hand_rot", "R"),
              "foot_l": ("foot_rot", "L"), "foot_r": ("foot_rot", "R"),
              "lc": ("curls", "L"), "rc": ("curls", "R")}
    for key, value in values.items():
        if key in simple:
            q[simple[key]] = list(value)
        elif key in paired:
            group, side = paired[key]
            q[group][side] = list(value)
        elif key == "expression":
            q["face"] = copy.deepcopy(expression_presets[value])
        elif key in ("f", "poles", "spreads"):
            q["face" if key == "f" else key].update(value)
        else:
            q[key] = value
    return q


def aim_pose(pitch, yaw):
    direction = [math.sin(yaw)*math.cos(pitch), -math.cos(yaw)*math.cos(pitch), math.sin(pitch)]
    shoulder_angle = .48*yaw
    shoulder = [.19*math.cos(shoulder_angle), .19*math.sin(shoulder_angle), 1.39]
    wrist = [shoulder[i] + .43*direction[i] for i in range(3)]
    support = [shoulder[i] + .16*direction[i] for i in range(3)]
    support[0] -= .13
    support[2] -= .10
    return pose(torso=[0., 0., .20*yaw], chest=[-.12*pitch, 0., .28*yaw],
                head=[-pitch*.40, 0., .52*yaw], rh=wrist, lh=support,
                lrot=[-1.10-pitch*.40, .18, yaw*.65],
                rrot=[-PI/2-pitch, 0., yaw], expression="focus",
                lc=[.40, .28, .32, .38, .44], rc=[.35, .18, .24, .32, .38],
                poles={"elbow.R": [.56*math.cos(yaw*.4), .12, 1.10],
                       "elbow.L": [-.46, .03, 1.16]})


def grasp_wrist(center, rotation, side="L"):
    # Palm/finger grip centre from this character's authored geometry,
    # including the palm surface and closed-finger envelope.
    offset = rotate_xyz([-.013 if side == "L" else .013, -.035, -.055], rotation)
    return [center[i]-offset[i] for i in range(3)]


def _rotation_quaternion(e):
    cx, sx = math.cos(e[0]/2), math.sin(e[0]/2)
    cy, sy = math.cos(e[1]/2), math.sin(e[1]/2)
    cz, sz = math.cos(e[2]/2), math.sin(e[2]/2)
    return [cx*cy*cz+sx*sy*sz, sx*cy*cz-cx*sy*sz,
            cx*sy*cz+sx*cy*sz, cx*cy*sz-sx*sy*cz]


def _quaternion_product(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]


def _quaternion_euler(q):
    w, x, y, z = q
    return [math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)),
            math.asin(clamp(2*(w*y-z*x), -1., 1.)),
            math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))]


# Exact evaluated forearm.R socket calibration from this authored skeleton,
# with the prop omitted in rig.apply_pose. The corresponding R-arm/torso
# stages below are unchanged. These are contact anchors, not another action
# or an external motion dependency. Rows are zero-based authored 30fps samples.
_RELOAD_MOUNT = [
    (13, [.119431615, -.215788841, 1.119231105], [-.198378205, 2.009101152, 1.601176858]),
    (14, [.119378030, -.215860963, 1.119200230], [-.198799312, 2.009831667, 1.601723433]),
    (15, [.119193673, -.216109529, 1.119095922], [-.200171158, 2.012289286, 1.603698850]),
    (16, [.118936092, -.216458648, 1.118952990], [-.201872230, 2.015588045, 1.606714725]),
    (17, [.118667096, -.216825992, 1.118807197], [-.203376442, 2.018870354, 1.610186219]),
    (18, [.118449777, -.217125192, 1.118690848], [-.204386875, 2.021409512, 1.613240242]),
    (19, [.118346483, -.217268169, 1.118635774], [-.204800472, 2.022581100, 1.614770651]),
    (20, [.118344635, -.217270702, 1.118634701], [-.204808086, 2.022600651, 1.614796281]),
    (33, [.118344635, -.217270702, 1.118634701], [-.204808086, 2.022600651, 1.614796281]),
    (34, [.118426859, -.217156798, 1.118678451], [-.204482540, 2.021669149, 1.613572598]),
    (35, [.118632257, -.216873869, 1.118788362], [-.203551754, 2.019284487, 1.610662103]),
    (36, [.118897587, -.216510922, 1.118932247], [-.202103928, 2.016067028, 1.607190371]),
    (37, [.119160503, -.216154099, 1.119077325], [-.200402707, 2.012721539, 1.604069829]),
    (38, [.119358867, -.215886638, 1.119189262], [-.198948368, 2.010089159, 1.601919770]),
    (39, [.119431615, -.215788841, 1.119231105], [-.198378205, 2.009101152, 1.601176858]),
    (54, [.119431615, -.215788841, 1.119231105], [-.198378205, 2.009101152, 1.601176858]),
]


def _reload_mount(u):
    sample = u*66
    a = _RELOAD_MOUNT[0]
    if sample <= a[0]:
        return list(a[1]), list(a[2])
    for b in _RELOAD_MOUNT[1:]:
        if sample <= b[0]:
            f = (sample-a[0])/(b[0]-a[0])
            return blend(a[1], b[1], f), blend(a[2], b[2], f)
        a = b
    return list(a[1]), list(a[2])


def _locomotion_transition(name, u):
    ready = base()
    if name == "start_f":
        prep = pose(pel=[0., .025, .86], torso=[.17, 0., 0.],
                    lh=[-.30, -.11, 1.18], rh=[.30, -.30, 1.22],
                    lf=[-.13, -.045, .10], rf=[.14, .14, .10], expression="focus")
        drive = pose(pel=[-.02, -.018, .85], torso=[.27, 0., .04],
                     lh=[-.30, -.31, 1.23], rh=[.31, -.05, 1.14],
                     lf=[-.13, -.25, .10], rf=[.14, .25, .18],
                     foot_r=[-.24, 0., .04], expression="focus")
        return staged([(0., ready), (.24, prep), (.64, drive), (1., gait("run", "f", 0., .6))], u)
    if name == "stop_f":
        moving = gait("run", "f", .10, .6)
        catch = pose(pel=[-.025, .075, .82], torso=[-.11, 0., -.04],
                     lf=[-.16, -.29, .10], rf=[.16, .19, .18],
                     lh=[-.37, -.27, 1.08], rh=[.35, -.19, 1.15],
                     foot_l=[-.13, 0., -.06], expression="focus")
        settle = changed(catch, pel=[.012, .025, .88], torso=[-.04, 0., .03],
                         rf=[.135, .065, .10], foot_l=[0., 0., -.07])
        return staged([(0., moving), (.22, catch), (.63, settle), (1., ready)], u)
    left = "_l" in name
    sign = -1 if left else 1
    angle = sign*(PI if name.startswith("pivot") else PI/2)
    support = "L" if left else "R"
    swing = "R" if left else "L"
    p = base()
    # Rotation begins in the shoulders, then the free foot opens, then the
    # support foot steps to the new heading; support does not spin on floor.
    yaw = angle*staged([(0., {"v": 0.}), (.15, {"v": .06}),
                       (.54, {"v": .56}), (.81, {"v": .93}), (1., {"v": 1.})], u)["v"]
    p["torso"] = [.10 if name.startswith("pivot") else .045, 0., angle*.12*math.sin(PI*u)]
    p["chest"][2] = angle*.10*math.sin(PI*u)
    p["head"][2] = angle*.15*math.sin(PI*u)
    p["pelvis"][2] -= (.10 if name.startswith("pivot") else .045)*math.sin(PI*u)**2
    p = rotated(p, yaw)
    if u < .54:
        # Fixed stance ankle while the torso and swing leg turn around it.
        p["feet"][support] = copy.deepcopy(base()["feet"][support])
        p["foot_rot"][support] = copy.deepcopy(base()["foot_rot"][support])
        sw = clamp((u-.15)/.39)
        p["feet"][swing][2] += .095*math.sin(PI*sw)
    elif u < .81:
        sw = (u-.54)/.27
        original = base()["feet"][support]
        final = rotated(base(), angle)["feet"][support]
        p["feet"][support] = [lerp(a, b, ease(sw)) for a, b in zip(original, final)]
        p["feet"][support][2] += .075*math.sin(PI*sw)
        p["feet"][swing] = rotated(base(), angle)["feet"][swing]
    p["face"].update(expression_presets["focus"])
    return p


def _jump(name, u):
    ready = base()
    crouch = pose(pel=[0., .01, .65], torso=[.38, 0., 0.], chest=[-.08, 0., 0.],
                  lh=[-.32, .03, .99], rh=[.32, .025, 1.02],
                  lf=[-.15, -.03, .10], rf=[.15, .03, .10],
                  foot_l=[0., 0., -.03], foot_r=[0., 0., .03], expression="focus")
    launch = pose(pel=[0., -.015, 1.0], torso=[.10, 0., 0.],
                  lh=[-.28, -.24, 1.54], rh=[.29, -.20, 1.50],
                  lf=[-.12, .03, .27], rf=[.12, .10, .32],
                  lrot=[-2.15, .15, -.08], rrot=[-2.0, -.14, .08],
                  foot_l=[-.35, 0., -.07], foot_r=[-.42, 0., .07], expression="focus")
    air = pose(pel=[0., 0., .965], torso=[.14, 0., 0.],
               lh=[-.40, -.13, 1.34], rh=[.39, -.19, 1.37],
               lf=[-.13, .08, .39], rf=[.15, .18, .43],
               foot_l=[-.48, 0., -.13], foot_r=[-.56, .08, .10],
               expression="focus")
    long_fall = pose(pel=[0., .02, .94], torso=[-.10, 0., .035], head=[.20, 0., -.035],
                    lh=[-.47, -.055, 1.41], rh=[.45, -.09, 1.43],
                    lf=[-.21, .06, .20], rf=[.20, -.025, .16],
                    lrot=[-1.7, .22, -.28], rrot=[-1.6, -.18, .24],
                    lc=[.12, .08, .08, .09, .12], rc=[.13, .09, .10, .12, .16],
                    expression="concern_sadness", f={"brow_raise.L": .70, "brow_raise.R": .58})
    if name == "jump_start":
        return staged([(0., ready), (.38, crouch), (.78, changed(crouch, pel=[0., 0., .74])), (1., launch)], u)
    if name in ("jump_air", "fall"):
        p = copy.deepcopy(air if name == "jump_air" else long_fall)
        amount = .012 if name == "jump_air" else .024
        p["head"][0] += amount*math.sin(TAU*u)
        p["chest"][2] += amount*math.sin(TAU*u)
        p["hands"]["L"][2] += amount*math.sin(TAU*u)
        p["hands"]["R"][2] -= amount*math.sin(TAU*u)
        p["feet"]["L"][2] += amount*math.cos(TAU*u)-amount
        return p
    contact = pose(pel=[0., .015, .91], torso=[.15, 0., 0.],
                   lh=[-.38, -.15, 1.27], rh=[.37, -.18, 1.30],
                   lf=[-.15, -.03, .10], rf=[.15, .03, .10])
    if name == "jump_land":
        compress = changed(crouch, lh=[-.37, -.24, 1.02], rh=[.37, -.20, 1.03],
                           pel=[0., .02, .72], torso=[.29, 0., 0.])
        return staged([(0., contact), (.32, compress), (.68, changed(ready, pel=[0., 0., .86])), (1., ready)], u)
    # Hard landing adds asymmetric floor support, a knee load and slower
    # pelvis rise; it cannot be mistaken for the soft landing at a new speed.
    impact = pose(pel=[.025, .02, .255], torso=[1.10, -.07, -.12], chest=[.16, 0., 0.],
                  lh=[-.28, -.35, .025], rh=[.27, -.19, .50],
                  lf=[-.17, -.19, .10], rf=[.18, .22, .10],
                  lrot=[PI/2, 0., -.22], lc=[.04, .02, .02, .03, .04],
                  poles={"knee.L": [-.24, -.42, .29], "knee.R": [.20, -.26, .12]},
                  expression="pain")
    recover = changed(ready, pel=[.02, .03, .70], torso=[.25, -.04, -.06],
                      lh=[-.25, -.26, .95], rh=[.28, -.19, 1.07], expression="focus")
    return staged([(0., contact), (.33, impact), (.53, changed(impact, head=[-.08, 0., 0.])),
                   (.76, recover), (1., ready)], u)


def _dash(name, u):
    dx, dy = DIRECTIONS[name.split("_")[1]]
    p = base()
    load = pose(pel=[-dx*.04, -dy*.04, .82], torso=[-dy*.20, dx*.12, 0.],
                lh=[-.30-dx*.035, -.14-dy*.08, 1.19],
                rh=[.30+dx*.05, -.26+dy*.04, 1.23],
                lf=[-.16-dx*.09, -.045-dy*.09, .10],
                rf=[.17-dx*.13, .065-dy*.13, .10], expression="focus")
    drive = pose(pel=[dx*.06, dy*.06, .83], torso=[-dy*.30, dx*.24, -dx*.10],
                 lh=[-.27-dx*.12, -.21-dy*.08, 1.23],
                 rh=[.32+dx*.10, -.14+dy*.10, 1.15],
                 lf=[-.15+dx*.22, -.01+dy*.22, .18],
                 rf=[.16-dx*.20, .03-dy*.20, .13], expression="focus")
    brake = pose(pel=[-dx*.045, -dy*.045, .80], torso=[dy*.14, -dx*.12, 0.],
                 lf=[-.16+dx*.20, -.045+dy*.20, .10],
                 rf=[.17-dx*.10, .065-dy*.10, .10],
                 lh=[-.33, -.19, 1.17], rh=[.35, -.23, 1.24], expression="focus")
    p = staged([(0., p), (.13, load), (.40, drive), (.78, brake), (1., base())], u)
    distance = 2*smoother((u-.13)/.75)
    p["root"] = [dx*distance, dy*distance, 0.]
    return p


def _blink(name, u):
    low = pose(pel=[0., 0., .80], torso=[.18, 0., -.08], chest=[0., 0., .06],
               lh=[-.15, -.21, 1.19], rh=[.19, -.22, 1.21],
               lf=[-.14, -.055, .10], rf=[.15, .06, .10],
               lc=[.72, .74, .77, .80, .83], rc=[.75, .77, .80, .83, .86],
               f={"blink.L": .65, "blink.R": .60, "brow_lower.L": .35, "brow_lower.R": .30})
    if name == "blink_out":
        gathered = changed(low, pel=[0., 0., .77], lh=[-.10, -.24, 1.21], rh=[.12, -.23, 1.24],
                           f={"blink.L": 1., "blink.R": 1.})
        return staged([(0., base()), (.25, low), (.75, gathered), (1., gathered)], u)
    plant = changed(low, pel=[0., .01, .81], lh=[-.34, -.16, 1.17], rh=[.36, -.20, 1.22],
                    expression="focus")
    return staged([(0., low), (.28, plant), (.72, changed(base(), pel=[0., 0., .90])), (1., base())], u)


def _melee(name, u):
    ready = base()
    if name == "melee_1":
        wind = pose(pel=[-.035, .035, .85], torso=[.12, -.03, -.25], chest=[0., 0., -.18],
                    head=[0., 0., .30], rh=[.36, -.035, 1.49], lh=[-.23, -.24, 1.16],
                    rrot=[-2.1, -.20, .65], lf=[-.15, -.11, .10], rf=[.18, .14, .10],
                    blade=1., rc=[.75, .86, .88, .89, .90], expression="anger")
        contact = pose(pel=[.055, -.035, .87], torso=[.18, .07, .36], chest=[0., 0., .24],
                       rh=[-.04, -.335, 1.22], lh=[-.32, -.11, 1.18],
                       rrot=[-1.45, -.35, -.70], head=[0., -.06, -.44],
                       lf=[-.15, -.11, .10], rf=[.18, .14, .10], blade=1.,
                       rc=[.75, .86, .88, .89, .90], expression="anger")
        follow = changed(contact, rh=[-.10, -.20, 1.15], torso=[.20, .10, .45],
                         chest=[0., 0., .20], rrot=[-.88, -.45, -.90])
        return staged([(0., ready), (.28, wind), (.47, contact), (.64, follow),
                       (.83, changed(ready, blade=1.)), (1., ready)], u)
    if name == "melee_2":
        wind = pose(pel=[.045, -.02, .84], torso=[.16, .05, .37], chest=[0., 0., .20],
                    rh=[-.07, -.28, 1.10], lh=[-.32, -.12, 1.24],
                    rrot=[-.9, -.32, -.75], head=[-.05, 0., -.38],
                    lf=[-.17, -.13, .10], rf=[.20, .15, .10], blade=1.,
                    rc=[.73, .85, .88, .90, .92], expression="anger")
        contact = pose(pel=[-.045, -.04, .90], torso=[.10, -.08, -.36], chest=[0., 0., -.24],
                       rh=[.43, -.27, 1.42], lh=[-.18, -.23, 1.17],
                       rrot=[-1.9, -.20, .70], head=[0., 0., .45],
                       lf=[-.17, -.13, .10], rf=[.20, .15, .10], blade=1.,
                       rc=[.73, .85, .88, .90, .92], expression="anger")
        follow = changed(contact, rh=[.40, -.02, 1.51], torso=[.08, -.12, -.46],
                         lrot=[-.60, .10, -.18])
        return staged([(0., ready), (.25, wind), (.48, contact), (.67, follow),
                       (.87, changed(ready, blade=1.)), (1., ready)], u)
    # Finisher has an overhead preparation, two-foot load, descending drive,
    # held low follow-through, and deliberate retraction.
    wind = pose(pel=[0., .055, .85], torso=[-.12, -.02, -.18], chest=[-.08, 0., -.16],
                rh=[.24, -.045, 1.75], lh=[-.06, -.15, 1.46],
                rrot=[-PI, -.18, .35], lrot=[-2.15, .15, .12],
                lf=[-.18, -.13, .10], rf=[.22, .18, .10], blade=1.,
                rc=[.85, .89, .91, .93, .94], expression="anger")
    contact = pose(pel=[.015, -.025, .65], torso=[.63, .06, .24], chest=[.12, 0., .15],
                   rh=[.13, -.50, .82], lh=[-.29, -.20, 1.00],
                   rrot=[-1.12, -.12, -.15], head=[-.26, 0., -.16],
                   lf=[-.18, -.13, .10], rf=[.22, .18, .10], blade=1.,
                   rc=[.85, .89, .91, .93, .94], expression="anger")
    follow = changed(contact, pel=[.03, -.035, .61], torso=[.74, .07, .30],
                     rh=[.04, -.46, .68], head=[-.22, .04, -.12])
    recover = changed(ready, pel=[.02, 0., .85], torso=[.14, 0., .10], blade=1.)
    return staged([(0., ready), (.32, wind), (.54, contact), (.70, follow), (.88, recover), (1., ready)], u)


def _ranged(name, u):
    ready = base()
    aim = aim_pose(0., 0.)
    if name == "ranged_fire":
        recoil = changed(aim, rh=[.19, -.37, 1.42], torso=[-.055, 0., -.04],
                         head=[-.04, 0., .025], rrot=[-1.73, -.05, 0.],
                         f={"squint.R": .53, "squint.L": .40})
        return staged([(0., ready), (.18, aim), (.25, aim), (.39, recoil), (.74, aim), (1., ready)], u)
    stages = [(0., ready), (.12, aim)]
    for shot in (.19, .43, .67):
        reco = changed(aim, rh=[.19, -.385, 1.415], torso=[-.05, 0., -.025],
                       rrot=[-1.72, -.04, .01], f={"squint.R": .50, "squint.L": .36})
        stages.extend([(shot, aim), (shot+.09, reco), (shot+.16, aim)])
    stages.append((1., ready))
    return staged(stages, u)


def _reload(u):
    nearest_sample = round(u*66)
    if abs(u*66-nearest_sample) < 1e-8:
        u = nearest_sample/66
    ready = base()
    inspect = pose(rh=[.18, -.27, 1.14], lh=[-.10, -.22, 1.19],
                   torso=[.05, 0., .11], chest=[0., 0., .07], head=[.22, 0., -.16],
                   expression="focus", rrot=[-1.03, -.28, .34])
    grasp = changed(inspect, lh=[.155, -.24, 1.23],
                    lc=[.79, .73, .77, .80, .82], lrot=[-1.50, .05, .45])
    extract = changed(grasp, lh=[.095, -.315, 1.25],
                      torso=[.08, 0., .08], head=[.18, 0., -.10])
    check = changed(extract, lh=[-.09, -.35, 1.17],
                    lrot=[-1.25, .25, -.10], head=[.18, .05, -.10])
    align = changed(grasp, lh=[.12, -.285, 1.28],
                    lrot=[-1.50, .05, .45], head=[.20, 0., -.14])
    insert = changed(grasp, lh=[.155, -.24, 1.23])
    socket_grasp, _ = _reload_mount(.20)
    for q in (grasp, extract, check, align, insert):
        q["hands"]["L"] = grasp_wrist(socket_grasp, q["hand_rot"]["L"])
    release = changed(insert, lh=[-.04, -.24, 1.20], lc=[.22, .10, .15, .22, .29])
    p = staged([(0., ready), (.14, inspect), (.20, grasp), (.29, extract), (.40, check),
                (.50, check), (.59, align), (.74, insert), (.77, insert), (.83, release), (1., ready)], u)
    # Named events are quantized to source samples: grasp14, detach20,
    # insertion50, attach52, organic-hand release56 (one-based frames).
    grasp_u, detach_u, attach_u = 13/66, 19/66, 51/66
    mount, mount_rotation = _reload_mount(u)
    center, rotation = mount, mount_rotation
    if detach_u <= u < attach_u:
        detach, detach_rotation = _reload_mount(detach_u)
        socket, socket_rotation = _reload_mount(attach_u)
        outward = rotate_xyz([0., .07, 0.], detach_rotation)
        extraction = [detach[i]+outward[i] for i in range(3)]
        align_outward = rotate_xyz([0., .055, 0.], socket_rotation)
        alignment = [socket[i]+align_outward[i] for i in range(3)]
        center = staged([(detach_u, {"p": detach}), (.36, {"p": extraction}),
                         (.45, {"p": [-.075, -.33, 1.17]}), (.52, {"p": [-.075, -.33, 1.17]}),
                         (.63, {"p": alignment}), (.74, {"p": socket}),
                         (attach_u, {"p": socket})], u)["p"]
        hand = _rotation_quaternion(p["hand_rot"]["L"])
        initial_hand = _rotation_quaternion([-1.50, .05, .45])
        inverse_hand = [initial_hand[0]]+[-x for x in initial_hand[1:]]
        carried = _quaternion_product(_quaternion_product(hand, inverse_hand),
                                      _rotation_quaternion(detach_rotation))
        fitted = _rotation_quaternion(socket_rotation)
        amount = ease((u-.52)/.11)
        if sum(a*b for a, b in zip(carried, fitted)) < 0:
            fitted = [-x for x in fitted]
        oriented = [lerp(a, b, amount) for a, b in zip(carried, fitted)]
        length = math.sqrt(sum(x*x for x in oriented))
        rotation = _quaternion_euler([x/length for x in oriented])
        p["cell"] = {"position": center, "rotation": rotation}
    # Omitted cell always follows the evaluated emitter mount, including
    # frame1, exact attachment frame52 and frame67; no socket guess overrides it.
    if grasp_u <= u <= attach_u:
        p["hands"]["L"] = grasp_wrist(center, p["hand_rot"]["L"])
    elif attach_u < u < .83:
        release_start = grasp_wrist(mount, p["hand_rot"]["L"])
        p["hands"]["L"] = blend(release_start, [-.04, -.24, 1.20], ease((u-attach_u)/(.83-attach_u)))
    return p


def _cast(name, u):
    ready = base()
    if name == "cast_directional":
        gather = pose(pel=[-.02, .04, .87], torso=[.10, -.03, -.20], chest=[0., 0., -.15],
                      rh=[.33, -.06, 1.38], lh=[-.08, -.28, 1.22],
                      rc=[.75, .74, .80, .83, .86], head=[-.04, 0., .25], expression="focus")
        release = changed(aim_pose(.07, -.15), pel=[.015, -.025, .90],
                          rh=[.13, -.45, 1.41], lh=[-.22, -.27, 1.19],
                          rc=[.14, .04, .06, .09, .12], torso=[.17, 0., .10])
        follow = changed(release, rh=[.14, -.40, 1.42], torso=[.10, 0., .06], expression="joy_confidence")
        return staged([(0., ready), (.28, gather), (.47, release), (.64, follow), (1., ready)], u)
    if name == "cast_ground":
        seek = pose(pel=[-.02, 0., .82], torso=[.25, 0., -.16], head=[.35, .02, -.24],
                    rh=[.22, -.27, 1.04], lh=[-.29, -.17, 1.15], expression="focus")
        place = pose(pel=[.015, -.02, .62], torso=[.46, .05, -.23], chest=[.12, 0., -.11],
                     rh=[.08, -.44, .70], lh=[-.29, -.18, .93], head=[.22, 0., -.08],
                     rrot=[-.55, -.12, -.32], rc=[.10, .03, .04, .08, .12],
                     lf=[-.16, -.12, .10], rf=[.18, .14, .10], expression="focus")
        return staged([(0., ready), (.25, seek), (.50, place), (.67, changed(place, rh=[.13, -.36, .79])), (1., ready)], u)
    gather = pose(pel=[0., 0., .81], torso=[.13, 0., 0.],
                  lh=[-.035, -.24, 1.25], rh=[.045, -.23, 1.30],
                  lrot=[-1.4, .30, -.1], rrot=[-1.4, -.30, .1],
                  lc=[.61, .50, .52, .56, .59], rc=[.65, .57, .58, .61, .66], expression="focus")
    release = pose(pel=[0., 0., .96], torso=[-.06, 0., 0.], chest=[-.07, 0., 0.],
                   lh=[-.42, -.16, 1.38], rh=[.43, -.16, 1.39],
                   lrot=[-1.65, .12, -.48], rrot=[-1.65, -.12, .48],
                   lc=[.07, .02, .03, .04, .06], rc=[.08, .03, .04, .06, .08],
                   head=[-.09, 0., 0.], expression="joy_confidence")
    return staged([(0., ready), (.30, gather), (.51, release), (.71, changed(release, pel=[0., 0., .93])), (1., ready)], u)


def _sustained(name, u):
    ready = base()
    if name.startswith("channel_"):
        hold = channel_pose()
        if name == "channel_start":
            load = changed(ready, pel=[-.02, .02, .86], rh=[.27, -.14, 1.30], lh=[-.04, -.25, 1.22], expression="focus")
            return staged([(0., ready), (.35, load), (.82, hold), (1., hold)], u)
        if name == "channel_loop":
            p = hold
            p["chest"][0] += .01*math.sin(TAU*u)
            p["hands"]["R"][2] += .009*math.sin(TAU*u)
            p["hands"]["L"][1] += .007*math.sin(TAU*u)
            p["face"]["squint.R"] += .08*(1-math.cos(TAU*u))
            return p
        if name == "channel_end":
            release = changed(hold, rh=[.27, -.365, 1.35], lh=[-.10, -.29, 1.23],
                              lc=[.15, .10, .15, .20, .26], expression="joy_confidence")
            return staged([(0., hold), (.15, release), (.60, changed(ready, rh=[.30, -.26, 1.25])), (1., ready)], u)
        recoil = changed(hold, pel=[.035, .035, .85], torso=[-.12, .08, -.19],
                         rh=[.36, -.22, 1.42], lh=[-.17, -.18, 1.29],
                         head=[-.14, -.08, .16], expression="pain")
        return staged([(0., hold), (.26, recoil), (.64, changed(recoil, rh=[.36, -.16, 1.26], expression="focus")), (1., ready)], u)
    if name.startswith("charge_"):
        hold = charge_pose()
        if name == "charge_start":
            fold = changed(ready, pel=[-.02, .035, .87], lh=[-.03, -.25, 1.26], rh=[.26, -.18, 1.28], expression="focus")
            return staged([(0., ready), (.33, fold), (.73, hold), (1., hold)], u)
        if name == "charge_hold":
            p = hold
            wave = math.sin(TAU*u)
            p["chest"][0] += .016*wave
            p["hands"]["L"][0] += .011*wave
            p["hands"]["R"][2] += .011*wave
            p["head"][2] -= .012*wave
            return p
        if name == "charge_release":
            throw = changed(aim_pose(.10, .08), pel=[.055, -.06, .86],
                            torso=[.29, .10, .30], chest=[.06, 0., .16],
                            rh=[.24, -.46, 1.36], lh=[-.34, -.19, 1.18],
                            rc=[.14, .06, .09, .13, .18], expression="anger")
            follow = changed(throw, pel=[.065, -.05, .85], rh=[.26, -.43, 1.31],
                             torso=[.25, .08, .36], head=[-.10, 0., -.20])
            return staged([(0., hold), (.20, changed(hold, pel=[-.04, .05, .81])),
                           (.42, throw), (.62, follow), (.86, changed(ready, expression="focus")), (1., ready)], u)
        vent = changed(hold, rh=[.32, -.10, 1.17], lh=[-.15, -.17, 1.15],
                       torso=[.09, -.02, -.15], rc=[.15, .07, .12, .18, .23], head=[.18, 0., .10])
        return staged([(0., hold), (.18, vent), (.56, changed(ready, pel=[0., 0., .88])), (1., ready)], u)
    hold = uplink_pose()
    if name == "uplink_start":
        inspect = changed(ready, rh=[.22, -.24, 1.16], lh=[-.12, -.26, 1.29],
                          head=[.18, 0., -.08], expression="focus")
        return staged([(0., ready), (.32, inspect), (.55, changed(hold, lh=[-.025, -.325, 1.205])), (.86, hold), (1., hold)], u)
    if name == "uplink_loop":
        p = hold
        tap = (.5-.5*math.cos(TAU*u))**5
        p["hands"]["L"][2] += .016*tap
        p["head"][2] += .015*math.sin(TAU*u)
        p["chest"][0] += .008*math.sin(TAU*u)
        return p
    if name == "uplink_end":
        confirm = changed(hold, lh=[-.03, -.32, 1.31], lc=[.58, .20, .63, .70, .76],
                          head=[-.06, 0., 0.], expression="joy_confidence")
        return staged([(0., hold), (.22, confirm), (.56, changed(ready, lh=[-.20, -.24, 1.26])), (1., ready)], u)
    withdraw = changed(hold, lh=[-.23, -.18, 1.25], rh=[.30, -.20, 1.19],
                       torso=[-.02, .04, -.05], head=[-.06, -.07, .22], expression="concern_sadness")
    return staged([(0., hold), (.24, withdraw), (.68, changed(ready, expression="focus")), (1., ready)], u)


def _deploy(u):
    ready = changed(base(), beacon=[-.14, .07, .88])
    grasp = changed(ready, lh=[-.14, .025, .89], lrot=[-.20, .15, -.15],
                    lc=[.80, .74, .76, .80, .83], head=[.18, 0., -.12])
    lift = changed(grasp, lh=[-.24, -.21, .97], beacon=[-.24, -.165, .96],
                   pel=[.025, .01, .74], torso=[.29, 0., -.10], expression="focus")
    place = pose(pel=[.035, .015, .235], torso=[.77, -.05, -.10], chest=[.25, 0., -.04],
                 lh=[-.26, -.385, .19], rh=[.28, -.19, .48],
                 lf=[-.17, -.15, .10], rf=[.18, .25, .105],
                 lrot=[.40, .05, -.08], rrot=[-.75, -.10, .18],
                 lc=[.80, .74, .76, .80, .83], head=[.10, 0., -.10],
                 poles={"knee.L": [-.20, -.31, .27], "knee.R": [.21, -.07, .11]},
                 beacon=[-.26, -.35, .045], expression="focus")
    for q in (grasp, lift, place):
        q["hands"]["L"] = grasp_wrist(q["beacon"], q["hand_rot"]["L"])
    contact = copy.deepcopy(place)
    release = changed(place, lh=[-.27, -.34, .19], lc=[.13, .05, .07, .10, .14])
    rise = changed(ready, pel=[.02, .02, .72], torso=[.23, 0., -.02],
                   lh=[-.26, -.22, .96], beacon=[-.26, -.35, .045], expression="focus")
    final = changed(base(), beacon=[-.26, -.35, .045])
    p = staged([(0., ready), (.13, grasp), (.20, lift), (.48, place), (.57, contact),
                (.65, release), (.73, changed(release, head=[-.03, 0., -.10])), (.88, rise), (1., final)], u)
    if .13 <= u <= .57:
        p["hands"]["L"] = grasp_wrist(p["beacon"], p["hand_rot"]["L"])
    return p


def _idle(name, u):
    wave = math.sin(TAU*u)
    soft = 1-math.cos(TAU*u)
    if name == "idle_relaxed":
        p = base(False)
        p["pelvis"][0] = .018*wave
        p["pelvis"][2] += .004*soft
        p["torso"] = [.004*soft, .015*wave, 0.]
        p["chest"] = [.010*wave, 0., -.012*wave]
        p["head"] = [0., -.008*wave, .035*wave]
        p["hands"]["L"][2] += .007*wave
        p["hands"]["R"][2] += .005*math.sin(TAU*u+.35)-.005*math.sin(.35)
        p["face"]["eye_yaw.L"] = .06*wave
        p["face"]["eye_yaw.R"] = .06*wave
        _, shoulders = joint_positions(p)
        for side, s in (("L", -1), ("R", 1)):
            offset = rotate_xyz([s*.205, -.015, -.442], p["chest"])
            offset = rotate_xyz(offset, p["torso"])
            p["hands"][side] = [shoulders[side][i]+offset[i] for i in range(3)]
    elif name == "idle_combat":
        p = base()
        p["pelvis"][0] = .012*wave
        p["pelvis"][2] += .006*soft
        p["torso"][2] = .018*wave
        p["chest"][0] = .012*wave
        p["hands"]["L"][1] += .007*wave
        p["hands"]["R"][2] += .005*wave
        p["head"][2] = -.025*wave
        p["face"].update(expression_presets["focus"])
    else:
        p = pose(pel=[-.035, .025, .87], torso=[.14, -.10, .07], chest=[.055, 0., -.04],
                 head=[-.05, .065, -.07], lh=[-.055, -.19, 1.035], rh=[.34, -.23, 1.15],
                 lf=[-.15, -.055, .10], rf=[.17, .10, .10],
                 lc=[.56, .37, .44, .51, .60], rc=[.36, .25, .30, .36, .44],
                 expression="pain", f={"eye_yaw.L": -.05, "eye_yaw.R": -.05})
        p["pelvis"][0] += .006*wave
        p["chest"][0] += .016*wave
        p["hands"]["L"][1] -= .005*soft
        p["head"][0] += .015*wave
        p["face"]["squint.R"] += .055*soft
    # Smooth independent blink. Timing is identical at loop boundaries.
    for side, center in (("L", .37), ("R", .378)):
        distance = abs(u-center)
        p["face"]["blink."+side] = ease(1-distance/.040) if distance < .040 else 0.
    p["secondary"] = [.018*wave, .013*(math.sin(TAU*u-.40)-math.sin(-.40)), .007*wave]
    return p


def _hit(name, u):
    p = base(False)
    # All lower-body values stay EXACTLY neutral: the runtime takes only
    # spine/clavicle/arm/head deltas, preserving gait phase and planted feet.
    weight = staged([(0., {"v": 0.}), (.25, {"v": 1.}), (.55, {"v": .32}), (1., {"v": 0.})], u)["v"]
    axis = name.split("_")[1]
    rx = {"f": -.22, "b": .25, "l": .035, "r": .035}[axis]*weight
    ry = {"f": 0., "b": 0., "l": .22, "r": -.22}[axis]*weight
    rz = {"f": -.035, "b": .045, "l": -.10, "r": .10}[axis]*weight
    p["torso"] = [rx, ry, rz]
    p["chest"] = [rx*.45, ry*.50, rz*.45]
    p["head"] = [rx*.60, ry*.70, -rz*.4]
    # Wrists follow the rotating shoulder/arm chains; this remains an arm
    # recoil rather than a new guard stance and cannot overextend an elbow.
    _, shoulders = joint_positions(p)
    for side, sign in (("L", -1), ("R", 1)):
        offset = rotate_xyz([sign*.208, -.015, -.447], p["chest"])
        offset = rotate_xyz(offset, p["torso"])
        p["hands"][side] = [shoulders[side][i]+offset[i] for i in range(3)]
    p["face"] = blend(face(), expression_presets["pain"], weight)
    return p


def _disable(name, u):
    ready = base()
    stunned = stun_pose()
    if name == "stun_start":
        shock = pose(pel=[.035, .045, .80], torso=[-.22, .13, -.17], chest=[-.04, -.10, .08],
                     lh=[-.37, -.055, 1.32], rh=[.39, -.10, 1.23], head=[-.14, .19, -.08],
                     lf=[-.15, -.11, .10], rf=[.19, .14, .10], expression="surprise")
        return staged([(0., ready), (.18, shock), (.48, changed(shock, head=[.29, -.16, .16], expression="pain")),
                       (.84, stunned), (1., stunned)], u)
    if name == "stun_loop":
        p = stunned
        p["torso"][1] += .045*math.sin(TAU*u)
        p["chest"][0] += .014*math.sin(2*TAU*u)
        p["head"][2] += .095*math.sin(TAU*u)
        p["head"][0] += .04*math.sin(2*TAU*u)
        p["hands"]["L"][2] += .018*math.sin(TAU*u)
        p["hands"]["R"][0] += .012*math.sin(TAU*u)
        p["face"]["eye_yaw.L"] = .15*math.sin(TAU*u)
        p["face"]["eye_yaw.R"] = .12*math.sin(TAU*u+.13)-.12*math.sin(.13)
        return p
    if name == "stun_end":
        focus = changed(stunned, pel=[.02, .02, .87], torso=[.07, .03, -.05],
                        head=[-.03, 0., 0.], lh=[-.28, -.22, 1.19], rh=[.32, -.21, 1.22],
                        expression="focus")
        return staged([(0., stunned), (.25, changed(stunned, head=[.22, -.07, -.08])), (.44, focus), (1., ready)], u)
    if name == "knockback":
        impact = pose(pel=[0., .065, .84], torso=[-.29, 0., -.08], head=[-.19, 0., .05],
                      lh=[-.39, -.14, 1.32], rh=[.40, -.15, 1.34],
                      lf=[-.15, -.08, .10], rf=[.16, .22, .17], expression="pain")
        catch = changed(impact, pel=[-.035, .05, .76], torso=[.16, 0., .05],
                        lf=[-.17, .29, .10], rf=[.18, -.15, .18], head=[.08, 0., -.08])
        second = changed(catch, pel=[.025, .015, .83], torso=[.05, .04, 0.],
                         rf=[.17, .14, .10], lh=[-.34, -.20, 1.17], rh=[.36, -.20, 1.23], expression="focus")
        return staged([(0., ready), (.10, impact), (.37, catch), (.66, second), (1., ready)], u)
    helpless = pose(pel=[.025, .035, .94], torso=[-.32, .06, -.08], chest=[-.07, -.05, .04],
                    head=[-.27, .13, .09], lh=[-.46, .09, 1.43], rh=[.43, .14, 1.48],
                    lf=[-.19, .13, .31], rf=[.21, -.10, .43],
                    lrot=[-1.9, .22, -.30], rrot=[-2.0, -.20, .36],
                    lc=[.12, .06, .08, .11, .15], rc=[.13, .08, .09, .12, .17],
                    foot_l=[-.52, -.08, -.20], foot_r=[-.63, .10, .18], expression="surprise")
    if name == "knockup_start":
        compress = changed(ready, pel=[0., 0., .80], torso=[.21, 0., .08],
                           rh=[.39, -.08, 1.12], lh=[-.35, -.12, 1.11], expression="pain")
        launch = changed(helpless, pel=[.025, .04, .97], lh=[-.43, .075, 1.53], rh=[.41, .11, 1.58])
        return staged([(0., ready), (.12, compress), (.22, launch), (.86, helpless), (1., helpless)], u)
    p = helpless
    w = math.sin(TAU*u)
    p["head"][1] += .075*w
    p["hands"]["L"][2] += .045*w
    p["hands"]["R"][1] -= .038*w
    p["feet"]["L"][1] += .055*w
    p["feet"]["R"][2] += .055*w
    p["face"]["jaw"] += .04*(1-math.cos(TAU*u))
    return p


def _knockdown(front, u, death=False):
    ready = base()
    terminal = floor_pose(front, death)
    if front:
        buckle = pose(pel=[-.02, .03, .66], torso=[.42, -.08, .12], head=[.19, 0., -.10],
                      lh=[-.27, -.31, .91], rh=[.30, -.34, 1.0],
                      lf=[-.16, -.13, .10], rf=[.18, .17, .10], expression="pain")
        knees = pose(pel=[-.02, .065, .44], pelvis_rot=[.25, 0., .03], torso=[.61, -.06, .06],
                     chest=[.14, 0., 0.], head=[-.20, .10, -.15],
                     lh=[-.28, -.45, .31], rh=[.32, -.41, .35],
                     lf=[-.15, .38, .135], rf=[.18, .34, .13],
                     lc=[.08, .03, .03, .04, .06], rc=[.09, .04, .05, .06, .08],
                     poles={"knee.L": [-.16, -.05, .12], "knee.R": [.17, -.02, .13]}, expression="pain")
        palms = pose(pel=[-.018, .055, .27], pelvis_rot=[.83, 0., .03], torso=[.47, 0., .02],
                     chest=[0., 0., 0.], head=[-.16, .16, -.15],
                     lh=[-.29, -.52, .025], rh=[.34, -.44, .027],
                     lf=[-.13, .62, .190], rf=[.18, .56, .190],
                     lrot=[PI/2, 0., -.10], rrot=[PI/2, 0., .18],
                     lc=[.07, .02, .02, .04, .06], rc=[.09, .04, .05, .07, .10],
                     poles={"knee.L": [-.13, .22, .13], "knee.R": [.18, .19, .15],
                            "elbow.L": [-.50, -.25, .12], "elbow.R": [.54, -.18, .15]}, expression="pain")
        if death:
            shock = changed(ready, torso=[-.08, -.12, .14], head=[-.14, .10, -.10],
                            lh=[-.06, -.20, 1.06], expression="pain")
            settle = changed(terminal, head=[-.10, .32, -.31],
                             rh=[.29, -.59, .027], lh=[-.35, -.45, .025], f={"blink.L": .89, "blink.R": .94})
            return staged([(0., ready), (.06, shock), (.18, buckle), (.30, knees), (.49, palms),
                           (.73, settle), (.94, terminal), (1., terminal)], u)
        return staged([(0., ready), (.18, buckle), (.35, knees), (.56, palms), (.80, terminal), (1., terminal)], u)
    arch = pose(pel=[.035, .065, .78], torso=[-.37, .08, -.16], chest=[-.12, 0., .03],
                head=[-.25, -.10, .08], lh=[-.40, -.13, 1.31], rh=[.43, -.025, 1.29],
                lf=[-.15, -.16, .10], rf=[.19, .18, .10], expression="pain")
    seat = pose(pel=[.035, .01, .235], pelvis_rot=[-.54, -.12, -.11], torso=[-.27, .48, .04],
                chest=[0., 0., 0.], head=[-.10, -.16, .10],
                lh=[-.32, .14, .36], rh=[.40, .14, .032],
                lf=[-.17, -.48, .13], rf=[.22, -.38, .15],
                lrot=[-.88, .25, -.23], rrot=[-PI/2, -.05, .24],
                poles={"knee.L": [-.20, -.32, .29], "knee.R": [.25, -.29, .30],
                       "elbow.R": [.61, .36, .18]}, expression="pain")
    back = changed(terminal, pel=[.025, -.03, .17], head=[.03, -.22, .09],
                   lh=[-.40, .24, .035], rh=[.39, .16, .055])
    if death:
        shock = changed(ready, pel=[.045, .02, .87], torso=[.16, .10, -.15],
                        rh=[.18, -.20, 1.08], head=[.10, -.18, .10], expression="pain")
        collapse = changed(seat, lh=[-.31, .17, .33], rh=[.33, .22, .032],
                           pelvis_rot=[-.73, -.13, -.12], head=[-.07, -.22, .13])
        return staged([(0., ready), (.06, shock), (.22, arch), (.43, collapse),
                       (.71, back), (.94, terminal), (1., terminal)], u)
    return staged([(0., ready), (.20, arch), (.49, seat), (.56, changed(seat, rh=[.39, .17, .032])),
                   (.83, back), (1., terminal)], u)


def _prone(front, u):
    p = floor_pose(front)
    wave = math.sin(TAU*u)
    p["chest"][0] += .010*wave
    p["head"][1] += (.016 if front else .020)*wave
    p["face"]["blink.L"] = .18+.10*(1-math.cos(TAU*u))
    p["face"]["blink.R"] = .23+.08*(1-math.cos(TAU*u))
    # Pelvis, wrists and ankles are fixed, giving restrained life without
    # horizontal body drift or palms skating through the floor.
    return p


def _getup(front, u):
    floor = floor_pose(front)
    ready = base()
    if front:
        push = changed(floor, pel=[-.01, .07, .29], pelvis_rot=[1.12, 0., .02],
                       torso=[.08, 0., 0.], chest=[-.08, 0., 0.], head=[-.35, .06, -.05],
                       expression="focus")
        tuck = pose(pel=[0., .075, .195], pelvis_rot=[.30, 0., 0.], torso=[.88, 0., 0.],
                    chest=[-.08, 0., 0.], head=[-.42, 0., 0.],
                    lh=[-.29, -.52, .025], rh=[.33, -.44, .027],
                    lf=[-.14, .42, .135], rf=[.18, .43, .13],
                    lrot=[PI/2, 0., -.10], rrot=[PI/2, 0., .18],
                    lc=[.04, .02, .02, .03, .05], rc=[.05, .02, .03, .04, .06],
                    poles={"knee.L": [-.16, .08, .11], "knee.R": [.19, .09, .12],
                           "elbow.L": [-.49, -.25, .18], "elbow.R": [.53, -.22, .20]}, expression="focus")
        half = pose(pel=[-.025, .015, .51], torso=[.43, 0., -.10], chest=[.03, 0., .02],
                    head=[-.14, 0., .08], lh=[-.18, -.24, .63], rh=[.29, -.18, .80],
                    lf=[-.15, -.24, .10], rf=[.18, .34, .13],
                    poles={"knee.L": [-.17, -.35, .43], "knee.R": [.18, .025, .12]}, expression="focus")
        stand = changed(ready, pel=[-.02, 0., .77], torso=[.20, 0., -.04],
                        lf=[-.15, -.24, .10], rf=[.135, .065, .10],
                        lh=[-.27, -.22, 1.03], rh=[.31, -.23, 1.13], expression="focus")
        return staged([(0., floor), (.12, push), (.31, tuck), (.53, half), (.73, stand), (1., ready)], u)
    roll = changed(floor, pel=[.025, -.02, .245], pelvis_rot=[-1.12, .27, -.15],
                   torso=[.08, .14, -.03], chest=[.06, 0., 0.], head=[.20, -.18, .08],
                   rh=[.39, .17, .032], lh=[-.18, .10, .43],
                   lf=[-.18, -.36, .115], rf=[.21, -.38, .13], expression="focus")
    seat = pose(pel=[.025, .025, .13], pelvis_rot=[-.09, .12, -.12], torso=[.50, .45, -.03],
                chest=[.02, .05, 0.], head=[-.14, 0., .10],
                rh=[.39, .17, .032], lh=[-.18, -.28, .41],
                lf=[-.19, -.39, .10], rf=[.22, -.30, .10],
                rrot=[-PI/2, -.04, .22], lrot=[-.60, .10, -.12],
                poles={"knee.L": [-.22, -.29, .44], "knee.R": [.25, -.22, .43],
                       "elbow.R": [.56, .29, .27]}, expression="focus")
    squat = pose(pel=[.025, .025, .45], torso=[.49, .02, -.08], chest=[.08, 0., .03],
                 head=[-.16, 0., .08], rh=[.30, -.15, .76], lh=[-.17, -.29, .68],
                 lf=[-.16, -.21, .10], rf=[.22, -.30, .10],
                 poles={"knee.L": [-.20, -.40, .38], "knee.R": [.25, -.42, .39]}, expression="focus")
    stand = changed(ready, pel=[.02, .01, .76], torso=[.23, .02, -.05],
                    lf=[-.16, -.21, .10], rf=[.135, .065, .10],
                    lh=[-.26, -.21, 1.02], rh=[.31, -.23, 1.11], expression="focus")
    return staged([(0., floor), (.14, roll), (.27, seat), (.50, squat), (.67, stand), (1., ready)], u)


def _sleep(name, u):
    ready = base()
    asleep = sleep_pose()
    if name == "sleep_start":
        heavy = pose(pel=[-.025, .025, .82], torso=[.20, -.08, -.10], head=[.34, .12, -.10],
                     lh=[-.31, -.20, .98], rh=[.33, -.18, 1.00], f={"blink.L": .68, "blink.R": .65})
        crouch = pose(pel=[-.01, .01, .51], torso=[.36, 0., -.12], head=[.37, .12, -.07],
                      lh=[-.19, -.28, .68], rh=[.21, -.25, .69],
                      lf=[-.22, -.25, .10], rf=[.24, -.21, .10],
                      poles={"knee.L": [-.30, -.40, .38], "knee.R": [.31, -.34, .39]},
                      f={"blink.L": .90, "blink.R": .91})
        return staged([(0., ready), (.21, heavy), (.43, crouch), (.62, asleep), (.92, asleep), (1., asleep)], u)
    if name == "sleep_loop":
        p = asleep
        wave = math.sin(TAU*u)
        p["chest"][0] += .016*wave
        p["head"][0] += .008*wave
        p["hands"]["L"][2] += .004*wave
        p["face"]["jaw"] += .012*(1-math.cos(TAU*u))
        return p
    wake = changed(asleep, head=[.28, .05, -.02], f={"blink.L": .22, "blink.R": .30,
                                                   "brow_raise.L": .45, "brow_raise.R": .36})
    scan = changed(wake, head=[.07, -.06, .18], lh=[-.19, -.29, .49], rh=[.24, -.22, .56],
                   expression="concern_sadness")
    squat = pose(pel=[-.01, .01, .47], torso=[.46, 0., -.08], head=[-.12, 0., .07],
                 lh=[-.18, -.27, .67], rh=[.26, -.22, .74],
                 lf=[-.17, -.20, .10], rf=[.25, -.30, .10],
                 poles={"knee.L": [-.22, -.39, .38], "knee.R": [.29, -.42, .39]}, expression="focus")
    stand = changed(ready, pel=[0., 0., .75], torso=[.25, 0., -.03],
                    lf=[-.17, -.20, .10], rf=[.135, .065, .10],
                    lh=[-.27, -.21, 1.03], rh=[.30, -.23, 1.13], expression="focus")
    return staged([(0., asleep), (.13, wake), (.32, scan), (.52, squat), (.74, stand), (1., ready)], u)


def _social(name, u):
    ready = base()
    if name == "respawn":
        dormant = pose(pel=[0., 0., .75], torso=[.20, 0., -.05], chest=[.10, 0., 0.],
                       head=[.38, 0., -.02], lh=[-.055, -.19, 1.12], rh=[.07, -.18, 1.15],
                       lc=[.66, .70, .74, .78, .82], rc=[.69, .74, .79, .82, .85],
                       f={"blink.L": 1., "blink.R": 1.})
        activate = changed(dormant, pel=[0., 0., .81], chest=[-.05, 0., 0.],
                           head=[.08, 0., 0.], expression="surprise", f={"jaw": .16})
        scan = pose(pel=[0., 0., .88], torso=[.03, 0., 0.],
                    lh=[-.36, -.20, 1.22], rh=[.37, -.19, 1.27], head=[-.07, 0., -.21],
                    lc=[.10, .04, .06, .09, .13], rc=[.12, .05, .08, .11, .16],
                    expression="focus", f={"eye_yaw.L": -.18, "eye_yaw.R": -.18})
        return staged([(0., dormant), (.18, activate), (.42, scan), (.63, changed(scan, head=[-.05, 0., .19],
                                                                                 f={"eye_yaw.L": .12, "eye_yaw.R": .12})),
                       (.82, changed(ready, expression="joy_confidence")), (1., ready)], u)
    if name == "greet":
        raise_hand = pose(pel=[.01, 0., .93], torso=[.03, 0., -.055], head=[-.04, 0., -.08],
                          lh=[-.33, -.12, 1.60], rh=[.34, -.20, 1.20],
                          lrot=[-2.70, .15, -.20], lc=[.16, .03, .04, .05, .08], expression="joy_confidence")
        wave_left = changed(raise_hand, lh=[-.38, -.13, 1.61], lrot=[-2.66, .12, -.42],
                            f={"brow_raise.L": .34})
        wave_right = changed(raise_hand, lh=[-.28, -.12, 1.62], lrot=[-2.76, .17, .04])
        return staged([(0., ready), (.25, raise_hand), (.35, wave_left), (.43, wave_right),
                       (.52, wave_left), (.61, raise_hand), (.81, changed(ready, expression="joy_confidence")), (1., ready)], u)
    if name == "victory":
        load = pose(pel=[.015, 0., .84], torso=[.13, 0., -.10],
                    lh=[-.19, -.25, 1.17], rh=[.28, -.22, 1.34],
                    rc=[.83, .88, .90, .92, .94], expression="joy_confidence")
        raised = pose(pel=[.02, 0., .96], torso=[-.06, .035, -.12], chest=[-.06, 0., -.08],
                      head=[-.13, 0., .12], lh=[-.24, -.19, 1.23], rh=[.31, .015, 1.77],
                      rrot=[-PI, -.18, .20], rc=[.83, .88, .90, .92, .94], expression="joy_confidence")
        salute = changed(raised, lh=[-.13, -.19, 1.67], lrot=[-2.90, .20, .20],
                         lc=[.22, .07, .10, .13, .17], head=[-.06, 0., -.09], f={"brow_raise.L": .32})
        return staged([(0., ready), (.18, load), (.40, raised), (.60, salute),
                       (.74, changed(raised, rh=[.30, -.07, 1.66])), (.90, changed(ready, expression="joy_confidence")), (1., ready)], u)
    slump = pose(pel=[-.025, .02, .90], torso=[.18, -.05, .04], chest=[.16, 0., -.02],
                 head=[.42, .08, -.13], lh=[-.36, -.05, .99], rh=[.36, -.08, 1.00],
                 lc=[.14, .08, .10, .15, .21], rc=[.17, .11, .14, .19, .25],
                 expression="concern_sadness", f={"eye_pitch.L": -.20, "eye_pitch.R": -.20})
    exhale = changed(slump, pel=[-.03, .02, .875], chest=[.20, 0., -.03],
                     head=[.47, .08, -.14], f={"blink.L": .65, "blink.R": .60})
    resolve = changed(ready, pel=[-.015, .01, .91], torso=[.07, -.02, .02],
                      head=[.08, 0., -.04], expression="focus")
    return staged([(0., ready), (.22, slump), (.41, exhale), (.61, slump), (.77, resolve), (1., ready)], u)


def _speech_face(seconds):
    data = alignment()
    cues = {c["event"]: c["time"] for c in data["performance_cues"]}
    shift = cues.get("confidence_shift", 8.6)
    emotion = ease((seconds-(shift-.35))/.75)
    f = blend(expression_presets["concern_sadness"], expression_presets["joy_confidence"], emotion)
    classes = {key: 0. for key in ("closure", "labiodental", "open", "wide", "round", "tongue", "consonant")}
    bilabial_seal = False
    # A 45 ms anticipation and 35 ms release form overlapping coarticulation
    # envelopes. Short plosives remain visible at 30 FPS rather than disappearing.
    for p in data["phonemes"]:
        key = p["viseme"]
        if key == "silence" or key not in classes:
            continue
        start, end = p["start"], p["end"]
        if key == "closure" and start-.012 <= seconds <= end+.010:
            bilabial_seal = True
        if start-.045 <= seconds <= end+.035:
            enter = ease((seconds-(start-.045))/.065)
            leave = ease(((end+.035)-seconds)/.060)
            classes[key] = max(classes[key], enter*leave)
    total = sum(classes.values())
    if total > 1.2:
        classes = {k: v*1.2/total for k, v in classes.items()}
    if bilabial_seal:
        # Actual /p b m/ holds include the nearest 30 FPS sample even when
        # the voiced stop itself is shorter than one frame.
        classes = {k: (1. if k == "closure" else v*.10) for k, v in classes.items()}
    for key, value in classes.items():
        f["viseme_"+key] = value
    c = classes
    f["jaw"] = clamp(.66*c["open"] + .37*c["wide"] + .32*c["round"] +
                     .12*c["tongue"] + .10*c["consonant"] + .07*c["labiodental"])
    f["jaw"] *= 1-.98*c["closure"]
    if bilabial_seal:
        f["jaw"] = 0.
    f["lip_close"] = clamp(c["closure"]*1.05)
    f["width"] = clamp(.74*c["wide"]+.25*c["labiodental"])
    f["pucker"] = clamp(.76*c["round"])
    f["funnel"] = clamp(.44*c["round"]+.10*c["open"])
    f["tongue"] = clamp(.84*c["tongue"])
    # Labiodental produces upper-teeth/lower-lip contact; the anatomical
    # implementation maps this slider independently from closure and jaw.
    f["frown.L"] *= 1-.35*min(1., total)
    f["frown.R"] *= 1-.35*min(1., total)
    f["smile.L"] *= 1-.50*c["round"]
    f["smile.R"] *= 1-.50*c["round"]
    wrist = cues.get("look_wrist", 2.136)
    crossing = cues.get("point_crossing", 6.395)
    breathe = cues.get("breath_release", 7.402)
    gaze = staged([(0., {"yaw": -.19, "pitch": .01}),
                   (wrist-.25, {"yaw": -.19, "pitch": .01}),
                   (wrist+.20, {"yaw": .17, "pitch": -.27}),
                   (4.65, {"yaw": .08, "pitch": -.09}),
                   (crossing-.40, {"yaw": -.25, "pitch": .015}),
                   (crossing+.35, {"yaw": -.25, "pitch": .015}),
                   (breathe+.25, {"yaw": 0., "pitch": 0.}),
                   (data["duration_seconds"], {"yaw": 0., "pitch": 0.})], seconds)
    for side, vergence in (("L", .012), ("R", -.012)):
        f["eye_yaw."+side] = gaze["yaw"] + vergence
        f["eye_pitch."+side] = gaze["pitch"]
        f["blink."+side] = 0.
        for blink_at in (.93, 4.72, breathe+.20, 9.56, 12.63):
            offset = 0. if side == "L" else .013
            distance = abs(seconds-blink_at-offset)
            if distance < .092:
                f["blink."+side] = max(f["blink."+side], ease(1-distance/.092))
    return f


def _dialogue(seconds, duration):
    data = alignment()
    cues = {c["event"]: c["time"] for c in data["performance_cues"]}
    ready = base()
    invite = pose(pel=[-.015, 0., .925], torso=[.045, 0., -.06], head=[.015, 0., -.09],
                  lh=[-.33, -.30, 1.26], rh=[.33, -.22, 1.21],
                  lc=[.16, .07, .08, .11, .17], lrot=[-1.45, .22, -.23])
    inspect = pose(pel=[.01, .01, .92], torso=[.035, 0., .07], head=[.17, 0., -.11],
                   rh=[.20, -.29, 1.16], lh=[-.02, -.30, 1.24],
                   rrot=[-1.0, -.27, .35], lrot=[-1.2, .15, .2], lc=[.46, .12, .42, .54, .63])
    promise = changed(ready, lh=[-.28, -.31, 1.32], head=[-.02, 0., -.06],
                      lc=[.20, .08, .10, .14, .20], lrot=[-1.60, .19, -.14])
    crossing = pose(pel=[-.015, 0., .925], torso=[.035, -.01, -.16], chest=[0., 0., -.06],
                    head=[-.02, 0., -.15], lh=[-.45, -.23, 1.38], rh=[.30, -.23, 1.23],
                    lrot=[-1.75, .16, -.45], lc=[.51, .02, .60, .68, .74])
    calm = changed(ready, pel=[0., 0., .935], chest=[-.028, 0., 0.], head=[-.035, 0., 0.],
                   lh=[-.30, -.20, 1.22], lc=[.15, .07, .10, .14, .21])
    signal = changed(calm, rh=[.24, -.30, 1.34], rrot=[-1.45, -.13, .13],
                     rc=[.26, .09, .18, .25, .31], head=[-.065, 0., .06], chest=[-.015, 0., .035])
    together = changed(calm, lh=[-.25, -.36, 1.30], lrot=[-1.53, .25, -.10],
                       lc=[.14, .05, .08, .12, .17], torso=[.08, 0., -.035], head=[-.02, 0., -.04])
    wrist_t = cues.get("look_wrist", 2.136)
    cross_t = cues.get("point_crossing", 6.395)
    breath_t = cues.get("breath_release", 7.402)
    signal_t = cues.get("confidence_shift", 8.621)
    together_t = cues.get("forward_gesture", 10.454)
    p = staged([(0., ready), (.45, invite), (1.7, invite), (wrist_t+.20, inspect),
                (3.3, inspect), (4.12, promise), (5.08, ready), (cross_t-.05, crossing),
                (cross_t+.46, crossing), (breath_t+.30, calm), (signal_t+.15, signal),
                (9.5, calm), (together_t+.15, together), (11.8, together),
                (duration-.25, calm), (duration, ready)], seconds)
    p["face"] = _speech_face(seconds)
    breathing = .007*math.sin(seconds*TAU/3.2)
    p["chest"][0] += breathing
    p["secondary"] = [.008*math.sin(seconds*TAU/2.7), .006*math.sin(seconds*TAU/2.7-.4), 0.]
    return p


def _pose_at_raw(name, t, duration):
    """Return a complete deterministic authored pose at seconds t.

    Omitted prop targets intentionally remain attached to their rig sockets.
    Dash body targets are local absolute coordinates before root movement;
    the baker applies root translation uniformly to every target.
    """
    u = clamp(t/duration) if duration > 0 else 0.
    if name.startswith("aim_"):
        _, pitch, yaw = name.split("_")
        return aim_pose(math.radians({"down": -35, "level": 0, "up": 35}[pitch]),
                        math.radians({"left": -60, "center": 0, "right": 60}[yaw]))
    if name == "dead_front":
        return floor_pose(True, True)
    if name == "dead_back":
        return floor_pose(False, True)
    if name.startswith("idle_"):
        return _idle(name, u)
    if name.startswith(("walk_", "run_", "sprint_")):
        mode, direction = name.split("_")
        return gait(mode, direction, u, duration)
    if name.startswith(("turn_", "pivot_")) or name in ("start_f", "stop_f"):
        return _locomotion_transition(name, u)
    if name in ("jump_start", "jump_air", "jump_land", "fall", "land_heavy"):
        return _jump(name, u)
    if name.startswith("dash_"):
        return _dash(name, u)
    if name.startswith("blink_"):
        return _blink(name, u)
    if name.startswith("melee_"):
        return _melee(name, u)
    if name in ("ranged_fire", "ranged_burst"):
        return _ranged(name, u)
    if name == "reload":
        return _reload(u)
    if name.startswith("cast_"):
        return _cast(name, u)
    if name.startswith(("channel_", "charge_", "uplink_")):
        return _sustained(name, u)
    if name == "deploy":
        return _deploy(u)
    if name.startswith("hit_"):
        return _hit(name, u)
    if name.startswith(("stun_", "knockup_")) or name == "knockback":
        return _disable(name, u)
    if name.startswith(("knockdown_", "death_")):
        return _knockdown(name.endswith("front"), u, name.startswith("death_"))
    if name.startswith("prone_"):
        return _prone(name.endswith("front"), u)
    if name.startswith("getup_"):
        return _getup(name.endswith("front"), u)
    if name.startswith("sleep_"):
        return _sleep(name, u)
    if name in ("respawn", "greet", "victory", "defeat"):
        return _social(name, u)
    if name == "dialogue":
        return _dialogue(t, duration)
    raise KeyError(f"Unknown required authored entry: {name}")


def pose_at(name, t, duration):
    p = _pose_at_raw(name, t, duration)
    if name in FLOOR_CONTACT_ENTRIES:
        p = fit_boot_contact(p)
    p = fit_leg_height(p, .838)
    return fit_support_planes(p) if name in FLOOR_CONTACT_ENTRIES else p


def _numeric_leaves(value):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _numeric_leaves(value[key])
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _numeric_leaves(item)
    else:
        yield float(value)


def _max_delta(a, b):
    va, vb = list(_numeric_leaves(a)), list(_numeric_leaves(b))
    assert len(va) == len(vb)
    return max(abs(x-y) for x, y in zip(va, vb))


def validate():
    """Check authored data, not a substitute for rendered deformation QA."""
    rows = list(csv.DictReader((ROOT / "required_animations.csv").open()))
    assert len(rows) == 96
    assert sum(r["form"] == "pose" for r in rows) == 11
    assert len({r["id"] for r in rows}) == 96
    fingerprints = {}
    max_loop = 0.
    maximum_arm_reach = maximum_leg_reach = 0.
    summaries = []
    for row in rows:
        name = row["id"]
        m = entry_metadata(row)
        duration = m["duration"]
        if row["duration_seconds"] != "pose":
            lo, hi = map(float, row["duration_seconds"].replace("–", "-").split("-"))
            assert lo <= duration <= hi, (name, duration)
        assert m["frame_count"] == round(duration*FPS)+1
        for event in m["events"]:
            assert 1 <= event["frame"] <= m["frame_count"]
            assert event["time"] == (event["frame"]-1)/FPS
        samples = [pose_at(name, duration*i/16, duration) for i in range(17)]
        for frame in range(m["frame_count"]):
            p = pose_at(name, frame/FPS, duration)
            hips, shoulders = joint_positions(p)
            for side in ("L", "R"):
                arm_distance = math.dist(shoulders[side], p["hands"][side])
                leg_distance = math.dist(hips[side], p["feet"][side])
                assert arm_distance <= .502677, (name, frame, side, "arm reach", arm_distance)
                assert leg_distance <= .838001, (name, frame, side, "leg reach", leg_distance)
                maximum_arm_reach = max(maximum_arm_reach, arm_distance)
                maximum_leg_reach = max(maximum_leg_reach, leg_distance)
            u = frame/(m["frame_count"]-1)
            if name == "reload" and 19/66 <= u < 51/66:
                assert math.dist(p["hands"]["L"], grasp_wrist(p["cell"]["position"], p["hand_rot"]["L"])) < 1e-10
            if name == "deploy" and .13 <= u <= .57:
                assert math.dist(p["hands"]["L"], grasp_wrist(p["beacon"], p["hand_rot"]["L"])) < 1e-10
        for p in samples:
            assert all(math.isfinite(v) for v in _numeric_leaves(p)), name
            assert all(0 <= c <= 1 for values in p["curls"].values() for c in values), name
            assert all(0 <= v <= 1 for k, v in p["face"].items() if not k.startswith("eye_")), name
            if row["root_movement"] == "in_place":
                assert p["root"] == [0., 0., 0.], name
        signature = hashlib.sha256(json.dumps(samples, sort_keys=True).encode()).hexdigest()
        assert signature not in fingerprints, (name, fingerprints.get(signature))
        fingerprints[signature] = name
        if m["loop"]:
            error = _max_delta(samples[0], samples[-1])
            assert error < 1e-7, (name, "loop discontinuity", error)
            max_loop = max(max_loop, error)
        elif m["static_pose"]:
            assert _max_delta(samples[0], samples[-1]) == 0., name
        elif name not in ("blink_out",):
            assert any(_max_delta(samples[0], p) > .015 for p in samples[1:]), name
        if row["root_movement"] == "root_motion":
            assert abs(math.sqrt(sum(v*v for v in samples[-1]["root"]))-2.) < 1e-10
        summaries.append({"id": name, "duration": duration, "frame_count": m["frame_count"],
                          "events": len(m["events"]), "unique_motion_sha256": signature})
    for side in ("front", "back"):
        m = entry_metadata(next(r for r in rows if r["id"] == "death_"+side))
        assert _max_delta(pose_at("death_"+side, m["duration"], m["duration"]),
                          pose_at("dead_"+side, 0., 1/FPS)) == 0.
    # The exact contact derivative must cancel controller travel velocity.
    for mode, dur, speed, stance in (("walk", .8, 1.5, .62), ("run", .6, 4., .37), ("sprint", .4, 6.5, .32)):
        for direction in (DIRECTIONS if mode != "sprint" else ("f",)):
            u, du = .12, .00001
            a = gait(mode, direction, u, dur)["feet"]["L"]
            b = gait(mode, direction, u+du, dur)["feet"]["L"]
            actual = [(b[i]-a[i])/(du*dur) for i in (0, 1)]
            expected = [-speed*d for d in DIRECTIONS[direction]]
            assert max(abs(x-y) for x, y in zip(actual, expected)) < 1e-7
            assert a[2] == .10 and b[2] == .10
    report = {"inventory_entries": 96, "motion_entries": 85, "static_pose_entries": 11,
              "unique_sampled_motion_signatures": len(fingerprints),
              "max_loop_numeric_delta": max_loop, "death_endpoints_exact": True,
              "nominal_dash_displacement_m": 2., "analytical_support_velocity_verified": True,
              "all_30fps_wrist_and_ankle_targets_reachable": True,
              "maximum_arm_reach_m": maximum_arm_reach, "maximum_leg_reach_m": maximum_leg_reach,
              "cell_and_beacon_grip_anchors_exact": True,
              "speech_wav_duration": alignment()["duration_seconds"], "entries": summaries,
              "scope": "Pure Python motion/timing/contact-policy validation; Blender and Unreal visual/skin deformation inspection is performed by the production pipeline."}
    destination = ROOT / "docs/motion_validation.json"
    destination.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k != "entries"}, indent=2))
    return report


if __name__ == "__main__":
    validate()

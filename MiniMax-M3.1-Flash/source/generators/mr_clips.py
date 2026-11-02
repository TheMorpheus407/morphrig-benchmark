"""MorphRig motion inventory: all 96 required clips.

Every clip is a function `fn(t, rig) -> Pose` where `t` is the normalised
clip time in [0, 1).  The clips are authored in place - only the four dash
clips translate the root bone, and those carry the 2 m nominal root motion.

Sign conventions
----------------
* yaw  positive  -> towards the character's right (+X)
* pitch positive  -> downwards
* hip  positive   -> the leg swings forward
* elbow positive  -> the elbow bends, the hand travels forward
"""

import math
import os

from mr_anim import (Pose, stance, breathe, look_at, blink, brows, jaw,
                     finger_curl, arm, arm_world, leg, pelvis_shift, TAU)

CLIPS = []
CLIP_INDEX = {}


def clip(name, frames, loop=False, markers=(), root_motion="in_place",
         speed=0.0, interp="BEZIER", form="one_shot"):
    def deco(fn):
        spec = dict(name=name, frames=frames, loop=loop, fn=fn,
                    markers=list(markers), root_motion=root_motion,
                    speed=speed, interp=interp, form=form)
        CLIPS.append(spec)
        CLIP_INDEX[name] = spec
        return fn
    return deco


def _lerp(a, b, t):
    return a + (b - a) * t


def _ease(t):
    return t * t * (3.0 - 2.0 * t)


def _ease_out(t):
    return 1.0 - (1.0 - t) ** 2


def _bell(t, centre=0.5, width=0.25):
    """0..1 bump used for anticipation / recovery shaping."""
    x = (t - centre) / max(width, 1e-6)
    return math.exp(-x * x)


X = (1.0, 0.0, 0.0)
Y = (0.0, 1.0, 0.0)
Z = (0.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# locomotion
# ---------------------------------------------------------------------------

def _gait_leg(u, stride, knee_lift, back=False):
    """Return (hip_forward, knee, ankle, toe) for one leg.

    `u` is the leg phase in [0, 1): 0 = heel strike, 0.25 = mid stance,
    0.5 = toe off.
    """
    s = math.sin(TAU * u)
    hip = stride * s
    if back:
        hip = -hip
    if u < 0.5:
        x = u / 0.5
        knee = knee_lift * math.sin(math.pi * (x ** 0.72))
        ankle = -14.0 * max(0.0, 1.0 - x / 0.18)
        toe = 4.0 * max(0.0, (x - 0.72) / 0.28)
    else:
        x = (u - 0.5) / 0.5
        knee = 6.0 * (math.sin(math.pi * x) ** 2)
        ankle = 16.0 * max(0.0, (x - 0.62) / 0.38)
        toe = 26.0 * max(0.0, (x - 0.58) / 0.42)
    return hip, knee, ankle, toe


def _walk(p, t, side, fwd, stride=24.0, knee_lift=30.0, arm_swing=16.0,
          lean=0.0, side_stride=0.0, bounce=0.018, arm_close=0.0):
    """A directional walk / run cycle.

    `side` is +1 for a step towards the character's right, `fwd` is +1 for
    forward travel.  Both are blended so the eight directions share one
    coherent gait.
    """
    for s, ph in (("l", 0.0), ("r", 0.5)):
        u = (t + ph) % 1.0
        hip, knee, ankle, toe = _gait_leg(u, stride, knee_lift)
        hip_side = side_stride * math.sin(TAU * u)
        leg(p, s, hip=hip * fwd, hip_yaw=hip_side, knee=knee, ankle=ankle,
            toe=toe)
    bob = bounce * (0.5 - 0.5 * math.cos(4.0 * math.pi * t))
    sway = 0.010 * side * math.sin(TAU * t)
    p.bone("pelvis", (Z, -2.2 * side * math.sin(TAU * t)), (X, lean),
           trans=(sway, 0.0, bob))
    p.bone("spine_01", (Z, 1.4 * side * math.sin(TAU * t)))
    p.bone("spine_02", (X, -2.0 * fwd), (Z, 1.8 * side * math.sin(TAU * t)))
    p.bone("spine_03", (X, -2.6 * fwd), (Z, 2.4 * side * math.sin(TAU * t)))
    p.bone("chest", (X, -2.0 * fwd), (Z, 2.6 * side * math.sin(TAU * t)))
    p.bone("neck_01", (X, 3.0 * fwd), (Z, -3.0 * side * math.sin(TAU * t)))
    for s, ph in (("l", 0.5), ("r", 0.0)):
        u = (t + ph) % 1.0
        sw = arm_swing * math.sin(TAU * u) * fwd
        arm(p, s, pitch=sw, yaw=(6.0 + arm_close) * side,
            elbow=18.0 + 12.0 * abs(math.sin(TAU * u)), wrist=-6.0)


@clip("walk_f", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_f(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.0, 1.0, stride=22.0, arm_swing=16.0)
    look_at(p, yaw=0.0, pitch=-2.0)
    return p


@clip("walk_fl", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_fl(t, rig):
    p = Pose(rig)
    _walk(p, t, -0.45, 0.89, stride=22.0, arm_swing=15.0, side_stride=7.0)
    look_at(p, yaw=-4.0, pitch=-2.0)
    return p


@clip("walk_l", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_l(t, rig):
    p = Pose(rig)
    _walk(p, t, -1.0, 0.05, stride=8.0, arm_swing=8.0, side_stride=17.0,
          lean=3.0)
    look_at(p, yaw=-8.0, pitch=-2.0)
    return p


@clip("walk_bl", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_bl(t, rig):
    p = Pose(rig)
    _walk(p, t, -0.45, -0.89, stride=20.0, arm_swing=12.0, side_stride=8.0)
    look_at(p, yaw=-4.0, pitch=-2.0)
    return p


@clip("walk_b", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_b(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.0, -1.0, stride=20.0, arm_swing=12.0)
    look_at(p, yaw=0.0, pitch=-2.0)
    return p


@clip("walk_br", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_br(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.45, -0.89, stride=20.0, arm_swing=12.0, side_stride=8.0)
    look_at(p, yaw=4.0, pitch=-2.0)
    return p


@clip("walk_r", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_r(t, rig):
    p = Pose(rig)
    _walk(p, t, 1.0, 0.05, stride=8.0, arm_swing=8.0, side_stride=17.0,
          lean=-3.0)
    look_at(p, yaw=8.0, pitch=-2.0)
    return p


@clip("walk_fr", 30, loop=True, form="loop", speed=1.5,
      markers=[("footstep_l", 8), ("footstep_r", 23)])
def walk_fr(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.45, 0.89, stride=22.0, arm_swing=15.0, side_stride=7.0)
    look_at(p, yaw=4.0, pitch=-2.0)
    return p


@clip("run_f", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_f(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.0, 1.0, stride=30.0, knee_lift=52.0, arm_swing=34.0,
          bounce=0.036)
    p.bone("spine_02", (X, -7.0))
    p.bone("spine_03", (X, -5.0))
    look_at(p, yaw=0.0, pitch=-4.0)
    return p


@clip("run_fl", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_fl(t, rig):
    p = Pose(rig)
    _walk(p, t, -0.45, 0.89, stride=30.0, knee_lift=52.0, arm_swing=30.0,
          side_stride=12.0, bounce=0.036)
    p.bone("spine_02", (X, -6.0))
    look_at(p, yaw=-5.0, pitch=-4.0)
    return p


@clip("run_l", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_l(t, rig):
    p = Pose(rig)
    _walk(p, t, -1.0, 0.05, stride=12.0, knee_lift=46.0, arm_swing=16.0,
          side_stride=24.0, lean=7.0, bounce=0.032)
    p.bone("spine_02", (X, -5.0))
    look_at(p, yaw=-12.0, pitch=-4.0)
    return p


@clip("run_bl", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_bl(t, rig):
    p = Pose(rig)
    _walk(p, t, -0.45, -0.89, stride=27.0, knee_lift=50.0, arm_swing=26.0,
          side_stride=12.0, bounce=0.036)
    look_at(p, yaw=-5.0, pitch=-4.0)
    return p


@clip("run_b", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_b(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.0, -1.0, stride=26.0, knee_lift=48.0, arm_swing=20.0,
          bounce=0.032)
    look_at(p, yaw=0.0, pitch=-4.0)
    return p


@clip("run_br", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_br(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.45, -0.89, stride=27.0, knee_lift=50.0, arm_swing=26.0,
          side_stride=12.0, bounce=0.036)
    look_at(p, yaw=5.0, pitch=-4.0)
    return p


@clip("run_r", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_r(t, rig):
    p = Pose(rig)
    _walk(p, t, 1.0, 0.05, stride=12.0, knee_lift=46.0, arm_swing=16.0,
          side_stride=24.0, lean=-7.0, bounce=0.032)
    p.bone("spine_02", (X, -5.0))
    look_at(p, yaw=12.0, pitch=-4.0)
    return p


@clip("run_fr", 24, loop=True, form="loop", speed=4.0,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def run_fr(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.45, 0.89, stride=30.0, knee_lift=52.0, arm_swing=30.0,
          side_stride=12.0, bounce=0.036)
    p.bone("spine_02", (X, -6.0))
    look_at(p, yaw=5.0, pitch=-4.0)
    return p


@clip("sprint_f", 24, loop=True, form="loop", speed=6.5,
      markers=[("footstep_l", 6), ("footstep_r", 18)])
def sprint_f(t, rig):
    p = Pose(rig)
    _walk(p, t, 0.0, 1.0, stride=36.0, knee_lift=64.0, arm_swing=46.0,
          bounce=0.050)
    p.bone("pelvis", (X, -12.0))
    p.bone("spine_01", (X, -6.0))
    p.bone("spine_02", (X, -8.0))
    p.bone("spine_03", (X, -6.0))
    p.bone("neck_01", (X, 8.0))
    for s in ("l", "r"):
        arm(p, s, pitch=0.0, yaw=18.0, elbow=95.0, wrist=-12.0)
    look_at(p, yaw=0.0, pitch=-8.0)
    return p


# ---------------------------------------------------------------------------
# idles
# ---------------------------------------------------------------------------

@clip("idle_relaxed", 90, loop=True, form="loop",
      markers=[("breath_in", 30), ("breath_out", 62)])
def idle_relaxed(t, rig):
    p = Pose(rig)
    stance(p)
    breathe(p, t, 1.0)
    sway = math.sin(TAU * t * 0.5)
    sway2 = math.sin(TAU * t * 0.5 + 2.1)
    p.bone("pelvis", (Z, 1.8 * sway), trans=(0.010 * sway, 0.0,
                                            -0.004 * abs(sway)))
    p.bone("spine_01", (Z, -1.4 * sway), (X, 1.0 * sway2))
    p.bone("chest", (Z, -2.2 * sway))
    p.bone("neck_01", (X, 1.5 * sway2))
    look_at(p, yaw=5.0 * math.sin(TAU * t * 0.5 + 0.6), pitch=1.5 * sway2)
    for s in ("l", "r"):
        arm(p, s, pitch=2.0 * sway2, yaw=1.0, elbow=12.0 + 2.0 * sway,
            wrist=-3.0)
        finger_curl(p, s, curl=0.12 + 0.05 * sway2, spread=0.2)
    return p


@clip("idle_combat", 90, loop=True, form="loop",
      markers=[("stance_shift", 34)])
def idle_combat(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    breathe(p, t, 1.2, phase=0.6)
    sway = math.sin(TAU * t * 0.5)
    sway2 = math.sin(TAU * t * 0.5 + 2.4)
    p.bone("pelvis", (Z, 2.6 * sway), trans=(0.008 * sway, 0.0,
                                            -0.008 * abs(sway)))
    p.bone("spine_01", (Z, -2.0 * sway))
    p.bone("spine_02", (X, -2.0), (Z, -2.4 * sway))
    p.bone("spine_03", (X, -2.6), (Z, -3.0 * sway))
    p.bone("chest", (X, -2.0), (Z, -3.2 * sway))
    p.bone("neck_01", (X, 3.0), (Z, -3.0 * sway))
    look_at(p, yaw=7.0 * math.sin(TAU * t * 0.5 + 1.2),
            pitch=3.0 + 2.0 * sway2, eye_yaw=3.0 * sway2, eye_pitch=1.0 * sway)
    arm(p, "r", pitch=-6.0 + 3.0 * sway2, yaw=10.0, elbow=48.0, wrist=-14.0)
    arm(p, "l", pitch=-2.0, yaw=14.0, elbow=52.0, wrist=-10.0)
    finger_curl(p, "r", curl=0.28 + 0.10 * sway2, spread=0.25)
    finger_curl(p, "l", curl=0.34 + 0.08 * sway2, spread=0.30)
    return p


@clip("idle_wounded", 90, loop=True, form="loop",
      markers=[("wound_shift", 40)])
def idle_wounded(t, rig):
    p = Pose(rig)
    stance(p)
    breathe(p, t, 1.35, phase=1.4)
    sway = math.sin(TAU * t * 0.5)
    p.bone("pelvis", (Z, 5.0), (X, 2.0), trans=(-0.016, 0.010, -0.030))
    p.bone("spine_01", (X, 6.0), (Z, -3.0))
    p.bone("spine_02", (X, 7.0), (Z, -3.5))
    p.bone("spine_03", (X, 6.0), (Z, -3.0))
    p.bone("chest", (X, 4.0), (Z, -2.5))
    p.bone("neck_01", (X, -3.0))
    leg(p, "l", hip=-6.0, knee=10.0, ankle=-4.0)
    leg(p, "r", hip=4.0, knee=14.0, ankle=-2.0)
    arm(p, "l", pitch=-14.0, yaw=6.0, elbow=40.0, wrist=-8.0)
    arm(p, "r", pitch=-2.0, yaw=-4.0, elbow=16.0, wrist=-4.0)
    finger_curl(p, "l", curl=0.55, spread=0.1)
    finger_curl(p, "r", curl=0.22, spread=0.15)
    look_at(p, yaw=-6.0 + 3.0 * sway, pitch=6.0 + 2.0 * sway)
    p.face(expr_concern=0.35)
    return p


# ---------------------------------------------------------------------------
# starts / stops / turns
# ---------------------------------------------------------------------------

@clip("start_f", 21, form="one_shot", speed=1.5,
      markers=[("accel_start", 1), ("accel_end", 21)])
def start_f(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease_out(t)
    _walk(p, t * 0.45, 0.0, 1.0, stride=22.0 * e, knee_lift=26.0 * e,
          arm_swing=14.0 * e, bounce=0.010 * e)
    p.bone("spine_02", (X, -8.0 * e))
    p.bone("spine_03", (X, -6.0 * e))
    p.bone("neck_01", (X, 6.0 * e))
    look_at(p, pitch=-3.0 * e)
    return p


@clip("stop_f", 18, form="one_shot",
      markers=[("brake_start", 1), ("plant", 12), ("brake_end", 18)])
def stop_f(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(t)
    leg(p, "r", hip=-26.0 * e, knee=18.0 * e, ankle=-6.0 * e)
    leg(p, "l", hip=16.0 * e, knee=22.0 * e, ankle=-4.0 * e)
    p.bone("pelvis", (X, -8.0 * e), trans=(0.0, 0.045 * e, -0.045 * e))
    p.bone("spine_02", (X, 8.0 * e))
    p.bone("spine_03", (X, 5.0 * e))
    p.bone("neck_01", (X, -4.0 * e))
    for s in ("l", "r"):
        arm(p, s, pitch=-26.0 * e, yaw=16.0, elbow=40.0 * e, wrist=-8.0)
    look_at(p, pitch=2.0 * e)
    return p


def _turn(p, t, side):
    """90 degree turn in place with foot placement."""
    e = _ease(t)
    s = "l" if side > 0 else "r"
    o = "r" if side > 0 else "l"
    leg(p, s, hip=-14.0 * e, hip_yaw=26.0 * e * side, knee=16.0 * e,
        ankle=-4.0 * e)
    leg(p, o, hip=10.0 * e, knee=12.0 * e, ankle=-3.0 * e)
    p.bone("pelvis", (Z, 22.0 * e * side))
    p.bone("spine_01", (Z, 8.0 * e * side))
    p.bone("spine_02", (Z, 10.0 * e * side))
    p.bone("spine_03", (Z, 12.0 * e * side))
    p.bone("chest", (Z, 12.0 * e * side))
    p.bone("neck_01", (Z, 6.0 * e * side))
    look_at(p, yaw=16.0 * e * side)
    for ss in ("l", "r"):
        arm(p, ss, pitch=-10.0 * e, yaw=12.0, elbow=34.0, wrist=-6.0)
    return p


@clip("turn_l90", 24, form="one_shot",
      markers=[("turn_start", 1), ("foot_pivot", 12), ("turn_end", 24)])
def turn_l90(t, rig):
    p = Pose(rig)
    _turn(p, t, 1)
    return p


@clip("turn_r90", 24, form="one_shot",
      markers=[("turn_start", 1), ("foot_pivot", 12), ("turn_end", 24)])
def turn_r90(t, rig):
    p = Pose(rig)
    _turn(p, t, -1)
    return p


def _pivot180(p, t, side):
    e = _ease(t)
    s = "l" if side > 0 else "r"
    o = "r" if side > 0 else "l"
    leg(p, s, hip=-20.0 * e, hip_yaw=40.0 * e * side, knee=20.0 * e,
        ankle=-6.0 * e)
    leg(p, o, hip=14.0 * e, knee=18.0 * e, ankle=-4.0 * e)
    p.bone("pelvis", (Z, 40.0 * e * side))
    p.bone("spine_01", (Z, 12.0 * e * side))
    p.bone("spine_02", (Z, 16.0 * e * side))
    p.bone("spine_03", (Z, 18.0 * e * side))
    p.bone("chest", (Z, 18.0 * e * side))
    p.bone("neck_01", (Z, 8.0 * e * side))
    look_at(p, yaw=24.0 * e * side)
    for ss in ("l", "r"):
        arm(p, ss, pitch=-16.0 * e, yaw=18.0, elbow=44.0, wrist=-8.0)
    return p


@clip("pivot_l180", 27, form="one_shot",
      markers=[("pivot_start", 1), ("foot_pivot", 15), ("pivot_end", 27)])
def pivot_l180(t, rig):
    p = Pose(rig)
    _pivot180(p, t, 1)
    return p


@clip("pivot_r180", 27, form="one_shot",
      markers=[("pivot_start", 1), ("foot_pivot", 15), ("pivot_end", 27)])
def pivot_r180(t, rig):
    p = Pose(rig)
    _pivot180(p, t, -1)
    return p


# ---------------------------------------------------------------------------
# jump / fall / land
# ---------------------------------------------------------------------------

@clip("jump_start", 24, form="one_shot",
      markers=[("anticipation", 1), ("takeoff", 18), ("takeoff_end", 24)])
def jump_start(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.65:
        e = _ease(t / 0.65)
        leg(p, "l", hip=-26.0 * e, knee=34.0 * e, ankle=-10.0 * e)
        leg(p, "r", hip=-26.0 * e, knee=34.0 * e, ankle=-10.0 * e)
        p.bone("pelvis", (X, -8.0 * e), trans=(0.0, -0.055 * e, -0.075 * e))
        p.bone("spine_02", (X, 10.0 * e))
        p.bone("spine_03", (X, 8.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=26.0 * e, yaw=22.0, elbow=54.0, wrist=-10.0)
    else:
        e = _ease_out((t - 0.65) / 0.35)
        leg(p, "l", hip=-26.0 + 14.0 * e, knee=34.0 - 22.0 * e,
            ankle=-10.0 + 8.0 * e)
        leg(p, "r", hip=-26.0 + 14.0 * e, knee=34.0 - 22.0 * e,
            ankle=-10.0 + 8.0 * e)
        p.bone("pelvis", (X, -8.0 + 10.0 * e),
               trans=(0.0, -0.055 + 0.055 * e, -0.075 + 0.085 * e))
        p.bone("spine_02", (X, 10.0 - 14.0 * e))
        p.bone("spine_03", (X, 8.0 - 12.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=26.0 - 54.0 * e, yaw=22.0,
                elbow=54.0 - 24.0 * e, wrist=-10.0)
    look_at(p, pitch=-6.0)
    return p


@clip("jump_air", 24, loop=True, form="loop", markers=[("apex", 12)])
def jump_air(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    tuck = math.sin(TAU * t)
    leg(p, "l", hip=-34.0 - 8.0 * tuck, knee=46.0 + 10.0 * tuck, ankle=-12.0)
    leg(p, "r", hip=-16.0 + 8.0 * tuck, knee=26.0 - 8.0 * tuck, ankle=-6.0)
    p.bone("pelvis", (X, -8.0), trans=(0.0, 0.0, 0.010))
    p.bone("spine_02", (X, -8.0))
    p.bone("spine_03", (X, -5.0))
    p.bone("neck_01", (X, 6.0))
    arm(p, "l", pitch=-24.0, yaw=26.0, elbow=40.0, wrist=-8.0)
    arm(p, "r", pitch=-52.0, yaw=16.0, elbow=52.0, wrist=-14.0)
    look_at(p, pitch=-6.0)
    return p


@clip("jump_land", 21, form="one_shot",
      markers=[("impact", 4), ("recovery", 14)])
def jump_land(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.35:
        e = _ease_out(t / 0.35)
        leg(p, "l", hip=-30.0 * e, knee=48.0 * e, ankle=-14.0 * e)
        leg(p, "r", hip=-30.0 * e, knee=48.0 * e, ankle=-14.0 * e)
        p.bone("pelvis", (X, 10.0 * e), trans=(0.0, 0.0, -0.085 * e))
        p.bone("spine_02", (X, 12.0 * e))
        p.bone("spine_03", (X, 9.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-18.0 * e, yaw=30.0, elbow=60.0 * e, wrist=-12.0)
    else:
        e = _ease((t - 0.35) / 0.65)
        leg(p, "l", hip=-30.0 + 26.0 * e, knee=48.0 - 36.0 * e,
            ankle=-14.0 + 11.0 * e)
        leg(p, "r", hip=-30.0 + 26.0 * e, knee=48.0 - 36.0 * e,
            ankle=-14.0 + 11.0 * e)
        p.bone("pelvis", (X, 10.0 - 12.0 * e),
               trans=(0.0, 0.0, -0.085 + 0.085 * e))
        p.bone("spine_02", (X, 12.0 - 15.0 * e))
        p.bone("spine_03", (X, 9.0 - 11.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-18.0 + 12.0 * e, yaw=30.0,
                elbow=60.0 - 22.0 * e, wrist=-12.0)
    look_at(p, pitch=-4.0)
    return p


@clip("fall", 30, loop=True, form="loop", markers=[("braced", 10)])
def fall(t, rig):
    p = Pose(rig)
    stance(p)
    flap = math.sin(TAU * t)
    leg(p, "l", hip=-16.0 - 4.0 * flap, knee=26.0, ankle=-8.0)
    leg(p, "r", hip=-10.0 + 4.0 * flap, knee=20.0, ankle=-6.0)
    p.bone("pelvis", (X, -14.0))
    p.bone("spine_01", (X, -6.0))
    p.bone("spine_02", (X, -6.0))
    p.bone("spine_03", (X, -4.0))
    p.bone("neck_01", (X, 8.0))
    arm(p, "l", pitch=-40.0 + 8.0 * flap, yaw=34.0, elbow=46.0, wrist=-12.0)
    arm(p, "r", pitch=-56.0 - 8.0 * flap, yaw=26.0, elbow=62.0, wrist=-16.0)
    look_at(p, pitch=-14.0)
    return p


@clip("land_heavy", 27, form="one_shot",
      markers=[("impact", 3), ("absorb", 10), ("recovery", 21)])
def land_heavy(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.30:
        e = _ease_out(t / 0.30)
        leg(p, "l", hip=-46.0 * e, knee=72.0 * e, ankle=-22.0 * e)
        leg(p, "r", hip=-46.0 * e, knee=72.0 * e, ankle=-22.0 * e)
        p.bone("pelvis", (X, 18.0 * e), trans=(0.0, 0.0, -0.165 * e))
        p.bone("spine_02", (X, 16.0 * e))
        p.bone("spine_03", (X, 12.0 * e))
        p.bone("chest", (X, 8.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-30.0 * e, yaw=44.0, elbow=72.0 * e, wrist=-16.0)
    else:
        e = _ease((t - 0.30) / 0.70)
        leg(p, "l", hip=-46.0 + 40.0 * e, knee=72.0 - 56.0 * e,
            ankle=-22.0 + 19.0 * e)
        leg(p, "r", hip=-46.0 + 40.0 * e, knee=72.0 - 56.0 * e,
            ankle=-22.0 + 19.0 * e)
        p.bone("pelvis", (X, 18.0 - 22.0 * e),
               trans=(0.0, 0.0, -0.165 + 0.165 * e))
        p.bone("spine_02", (X, 16.0 - 19.0 * e))
        p.bone("spine_03", (X, 12.0 - 14.0 * e))
        p.bone("chest", (X, 8.0 - 10.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-30.0 + 20.0 * e, yaw=44.0,
                elbow=72.0 - 34.0 * e, wrist=-16.0)
    look_at(p, pitch=-8.0)
    return p


# ---------------------------------------------------------------------------
# dashes (root motion, 2 m nominal displacement)
# ---------------------------------------------------------------------------

def _dash(p, t, lean, twist):
    """Body pose for a ground dash; the root translation is applied by the
    caller."""
    e = _ease_out(t)
    p.bone("pelvis", (X, lean * e), (Z, twist * e),
           trans=(0.0, 0.0, -0.055 * math.sin(math.pi * t)))
    p.bone("spine_01", (X, lean * 0.6 * e))
    p.bone("spine_02", (X, lean * 0.5 * e))
    p.bone("spine_03", (X, lean * 0.4 * e))
    p.bone("chest", (X, lean * 0.3 * e))
    leg(p, "l", hip=-38.0 * e, knee=48.0 * e, ankle=-14.0 * e)
    leg(p, "r", hip=26.0 * e, knee=22.0 * e, ankle=-6.0 * e)
    arm(p, "l", pitch=30.0 * e, yaw=28.0, elbow=70.0 * e, wrist=-12.0)
    arm(p, "r", pitch=-44.0 * e, yaw=12.0, elbow=54.0 * e, wrist=-14.0)
    return p


def _dash_root(p, t, dx, dy):
    """2 m of root translation over the clip (eased)."""
    e = _ease_out(min(t / 0.72, 1.0))
    p.bone("root", trans=(dx * 2.0 * e, dy * 2.0 * e, 0.0))
    return p


@clip("dash_f", 14, form="one_shot", root_motion="root_motion", speed=4.4,
      markers=[("dash_start", 1), ("dash_contact", 6), ("dash_end", 14)])
def dash_f(t, rig):
    p = Pose(rig)
    _dash_root(p, t, 0.0, -1.0)
    _dash(p, t, -22.0, 0.0)
    look_at(p, pitch=-4.0)
    return p


@clip("dash_b", 14, form="one_shot", root_motion="root_motion", speed=4.4,
      markers=[("dash_start", 1), ("dash_contact", 6), ("dash_end", 14)])
def dash_b(t, rig):
    p = Pose(rig)
    _dash_root(p, t, 0.0, 1.0)
    _dash(p, t, 16.0, 0.0)
    look_at(p, pitch=-4.0)
    return p


@clip("dash_l", 14, form="one_shot", root_motion="root_motion", speed=4.4,
      markers=[("dash_start", 1), ("dash_contact", 6), ("dash_end", 14)])
def dash_l(t, rig):
    p = Pose(rig)
    _dash_root(p, t, -1.0, 0.0)
    _dash(p, t, 0.0, -16.0)
    look_at(p, yaw=-6.0)
    return p


@clip("dash_r", 14, form="one_shot", root_motion="root_motion", speed=4.4,
      markers=[("dash_start", 1), ("dash_contact", 6), ("dash_end", 14)])
def dash_r(t, rig):
    p = Pose(rig)
    _dash_root(p, t, 1.0, 0.0)
    _dash(p, t, 0.0, 16.0)
    look_at(p, yaw=6.0)
    return p


# ---------------------------------------------------------------------------
# blink transitions
# ---------------------------------------------------------------------------

@clip("blink_out", 12, form="one_shot",
      markers=[("anticipation", 1), ("disappear", 8), ("blink_out_end", 12)])
def blink_out(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.55:
        e = _ease(t / 0.55)
        p.bone("pelvis", (X, -10.0 * e), trans=(0.0, -0.030 * e, -0.055 * e))
        p.bone("spine_02", (X, 8.0 * e))
        arm(p, "l", pitch=14.0 * e, yaw=26.0, elbow=40.0 * e)
        arm(p, "r", pitch=10.0 * e, yaw=22.0, elbow=36.0 * e)
        blink(p, e * 0.7)
        p.face(expr_focus=0.6 * e)
    else:
        e = _ease_out((t - 0.55) / 0.45)
        p.bone("pelvis", (X, -10.0 - 6.0 * e),
               trans=(0.0, -0.030, -0.055 - 0.020 * e))
        p.bone("spine_02", (X, 8.0 + 6.0 * e))
        arm(p, "l", pitch=14.0, yaw=26.0, elbow=40.0)
        arm(p, "r", pitch=10.0, yaw=22.0, elbow=36.0)
        blink(p, 0.7 + 0.3 * e)
    return p


@clip("blink_in", 14, form="one_shot",
      markers=[("appear", 1), ("plant", 8), ("blink_in_end", 14)])
def blink_in(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(min(t / 0.5, 1.0))
    p.bone("pelvis", (X, 8.0 * (1.0 - e)), trans=(0.0, 0.0, -0.075 * (1.0 - e)))
    p.bone("spine_02", (X, 6.0 * (1.0 - e)))
    arm(p, "l", pitch=-6.0 * e, yaw=22.0, elbow=44.0 * e)
    arm(p, "r", pitch=-4.0 * e, yaw=20.0, elbow=40.0 * e)
    blink(p, max(0.0, 1.0 - e * 1.6))
    look_at(p, pitch=-2.0 * e)
    return p


# ---------------------------------------------------------------------------
# combat
# ---------------------------------------------------------------------------

def _blade_slash(p, t, side, swing, wind):
    """Shared blade swing shaping.

    side  +1 right hand
    swing +1 diagonal up slash
    wind  preparation amount
    """
    s = "r" if side > 0 else "l"
    o = "l" if side > 0 else "r"
    if t < 0.35:
        e = _ease(t / 0.35)
        arm(p, s, pitch=wind * e, yaw=-18.0 * e, elbow=52.0 * e, wrist=-14.0 * e)
        arm(p, o, pitch=-12.0 * e, yaw=20.0, elbow=46.0 * e)
        p.bone("pelvis", (Z, -10.0 * e * side))
        p.bone("spine_02", (Z, -12.0 * e * side))
        p.bone("spine_03", (Z, -16.0 * e * side))
        p.bone("chest", (Z, -16.0 * e * side))
        p.bone("neck_01", (Z, -6.0 * e * side))
    elif t < 0.58:
        e = _ease_out((t - 0.35) / 0.23)
        arm(p, s, pitch=wind * (1.0 - e) + swing * e, yaw=-18.0 + 14.0 * e,
            elbow=52.0 - 30.0 * e, wrist=-14.0 + 26.0 * e)
        arm(p, o, pitch=-12.0 + 14.0 * e, yaw=20.0, elbow=46.0)
        p.bone("pelvis", (Z, (-10.0 + 14.0 * e) * side))
        p.bone("spine_02", (Z, (-12.0 + 16.0 * e) * side))
        p.bone("spine_03", (Z, (-16.0 + 22.0 * e) * side))
        p.bone("chest", (Z, (-16.0 + 24.0 * e) * side))
        p.bone("neck_01", (Z, (-6.0 + 8.0 * e) * side))
    else:
        e = _ease((t - 0.58) / 0.42)
        arm(p, s, pitch=swing * (1.0 - 0.35 * e), yaw=-4.0 - 6.0 * e,
            elbow=22.0 + 18.0 * e, wrist=12.0 + 6.0 * e)
        arm(p, o, pitch=2.0 + 6.0 * e, yaw=20.0, elbow=46.0)
        p.bone("pelvis", (Z, 14.0 * side * (1.0 - 0.4 * e)))
        p.bone("spine_02", (Z, 16.0 * side * (1.0 - 0.4 * e)))
        p.bone("spine_03", (Z, 22.0 * side * (1.0 - 0.4 * e)))
        p.bone("chest", (Z, 24.0 * side * (1.0 - 0.4 * e)))
        p.bone("neck_01", (Z, 8.0 * side * (1.0 - 0.4 * e)))
    return p


@clip("melee_1", 27, form="one_shot",
      markers=[("windup", 1), ("hit_window", 13), ("follow_through", 18),
               ("recovery", 24)])
def melee_1(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    _blade_slash(p, t, 1, swing=54.0, wind=-52.0)
    p.blade(1.0)
    finger_curl(p, "r", curl=0.55, spread=0.1)
    finger_curl(p, "l", curl=0.45, spread=0.15)
    look_at(p, yaw=10.0, pitch=-4.0)
    return p


@clip("melee_2", 27, form="one_shot",
      markers=[("windup", 1), ("hit_window", 12), ("follow_through", 19),
               ("recovery", 24)])
def melee_2(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    _blade_slash(p, t, 1, swing=-38.0, wind=62.0)
    p.blade(1.0)
    finger_curl(p, "r", curl=0.6, spread=0.05)
    finger_curl(p, "l", curl=0.5, spread=0.1)
    look_at(p, yaw=-8.0, pitch=-6.0)
    return p


@clip("melee_3", 30, form="one_shot",
      markers=[("windup", 1), ("charge", 10), ("hit_window", 16),
               ("follow_through", 22), ("recovery", 28)])
def melee_3(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.34:
        e = _ease(t / 0.34)
        arm(p, "r", pitch=-96.0 * e, yaw=-24.0 * e, elbow=70.0 * e,
            wrist=-20.0 * e)
        arm(p, "l", pitch=-30.0 * e, yaw=26.0, elbow=54.0 * e)
        p.bone("pelvis", (X, -14.0 * e), (Z, -18.0 * e),
               trans=(0.0, -0.040 * e, -0.045 * e))
        p.bone("spine_02", (X, -10.0 * e), (Z, -20.0 * e))
        p.bone("spine_03", (Z, -24.0 * e))
        p.bone("chest", (Z, -24.0 * e))
    elif t < 0.58:
        e = _ease_out((t - 0.34) / 0.24)
        arm(p, "r", pitch=-96.0 + 150.0 * e, yaw=-24.0 + 12.0 * e,
            elbow=70.0 - 40.0 * e, wrist=-20.0 + 46.0 * e)
        arm(p, "l", pitch=-30.0 + 24.0 * e, yaw=26.0, elbow=54.0)
        p.bone("pelvis", (X, -14.0 + 24.0 * e), (Z, -18.0 + 34.0 * e),
               trans=(0.0, -0.040 + 0.040 * e, -0.045 + 0.050 * e))
        p.bone("spine_02", (X, -10.0 + 20.0 * e), (Z, -20.0 + 36.0 * e))
        p.bone("spine_03", (Z, -24.0 + 40.0 * e))
        p.bone("chest", (Z, -24.0 + 42.0 * e))
    else:
        e = _ease((t - 0.58) / 0.42)
        arm(p, "r", pitch=54.0 - 14.0 * e, yaw=-12.0 - 8.0 * e,
            elbow=30.0 + 16.0 * e, wrist=26.0 - 6.0 * e)
        arm(p, "l", pitch=-6.0, yaw=26.0, elbow=54.0)
        p.bone("pelvis", (X, 10.0 * (1.0 - 0.5 * e)),
               (Z, 16.0 * (1.0 - 0.4 * e)))
        p.bone("spine_02", (X, 10.0 * (1.0 - 0.5 * e)),
               (Z, 16.0 * (1.0 - 0.4 * e)))
        p.bone("spine_03", (Z, 16.0 * (1.0 - 0.4 * e)))
        p.bone("chest", (Z, 18.0 * (1.0 - 0.4 * e)))
    p.blade(1.0)
    finger_curl(p, "r", curl=0.6, spread=0.05)
    finger_curl(p, "l", curl=0.5, spread=0.1)
    look_at(p, yaw=14.0, pitch=-6.0)
    return p


@clip("ranged_fire", 11, form="one_shot",
      markers=[("muzzle", 3), ("recover", 6)])
def ranged_fire(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    arm(p, "r", pitch=-64.0, yaw=12.0, elbow=62.0, wrist=-8.0)
    arm(p, "l", pitch=-20.0, yaw=18.0, elbow=48.0, wrist=-6.0)
    kick = _bell(t, 0.27, 0.14)
    p.bone("lowerarm_r", (X, 16.0 * kick))
    p.bone("hand_r", (Z, 7.0 * kick))
    p.bone("spine_02", (X, -3.0 * kick), (Z, -3.0 * kick))
    p.bone("spine_03", (Z, -4.0 * kick))
    p.bone("neck_01", (Z, -2.0 * kick))
    look_at(p, yaw=-6.0, pitch=-4.0, eye_yaw=-4.0, eye_pitch=-2.0)
    p.face(expr_focus=0.5)
    return p


@clip("ranged_burst", 18, form="one_shot",
      markers=[("muzzle_1", 3), ("muzzle_2", 9), ("muzzle_3", 15),
               ("recover", 17)])
def ranged_burst(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    arm(p, "r", pitch=-64.0, yaw=12.0, elbow=62.0, wrist=-8.0)
    arm(p, "l", pitch=-20.0, yaw=18.0, elbow=48.0, wrist=-6.0)
    kick = max(_bell(t, 0.16, 0.07), _bell(t, 0.48, 0.07), _bell(t, 0.82, 0.07))
    p.bone("lowerarm_r", (X, 15.0 * kick))
    p.bone("hand_r", (Z, 6.0 * kick))
    p.bone("spine_03", (Z, -3.0 * kick))
    look_at(p, yaw=-6.0, pitch=-4.0, eye_yaw=-4.0, eye_pitch=-2.0)
    p.face(expr_focus=0.65)
    return p


@clip("reload", 54, form="one_shot",
      markers=[("cell_release", 8), ("cell_out", 18), ("cell_in", 34),
               ("cell_seated", 42), ("reload_end", 54)])
def reload(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    arm(p, "r", pitch=-52.0, yaw=16.0, elbow=56.0, wrist=-10.0)
    if t < 0.28:
        e = _ease(t / 0.28)
        arm(p, "l", pitch=-30.0 * e, yaw=8.0 * e, elbow=66.0 * e, wrist=-10.0 * e)
        p.bone("pelvis", (Z, -8.0 * e))
        p.bone("spine_02", (X, 8.0 * e))
        p.bone("spine_03", (X, 6.0 * e))
        finger_curl(p, "l", curl=0.5 - 0.45 * e, spread=0.2 + 0.4 * e)
    elif t < 0.62:
        e = _ease((t - 0.28) / 0.34)
        arm(p, "l", pitch=-30.0 - 26.0 * e, yaw=8.0 + 4.0 * e,
            elbow=66.0 - 22.0 * e, wrist=-10.0)
        p.bone("pelvis", (Z, -8.0 + 8.0 * e))
        p.bone("spine_02", (X, 8.0 - 10.0 * e))
        p.bone("spine_03", (X, 6.0 - 8.0 * e))
        finger_curl(p, "l", curl=0.05 + 0.5 * e, spread=0.6 - 0.3 * e)
    else:
        e = _ease((t - 0.62) / 0.38)
        arm(p, "l", pitch=-56.0 + 26.0 * e, yaw=12.0 - 12.0 * e,
            elbow=44.0 - 10.0 * e, wrist=-10.0)
        p.bone("spine_02", (X, -2.0 * e))
        p.bone("spine_03", (X, -2.0 * e))
        finger_curl(p, "l", curl=0.55 - 0.2 * e, spread=0.3)
    finger_curl(p, "r", curl=0.32, spread=0.2)
    look_at(p, yaw=-8.0 - 6.0 * math.sin(math.pi * t), pitch=-8.0,
            eye_yaw=-6.0, eye_pitch=-4.0)
    return p


# ---------------------------------------------------------------------------
# casts / channel / charge
# ---------------------------------------------------------------------------

@clip("cast_directional", 27, form="one_shot",
      markers=[("cast_build", 1), ("cast_release", 15), ("cast_end", 27)])
def cast_directional(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.5:
        e = _ease(t / 0.5)
        arm(p, "r", pitch=-30.0 - 34.0 * e, yaw=10.0, elbow=70.0 * e,
            wrist=-14.0 * e)
        arm(p, "l", pitch=-14.0, yaw=20.0, elbow=52.0, wrist=-8.0)
        p.bone("spine_02", (X, -8.0 * e))
        p.bone("spine_03", (X, -6.0 * e))
        p.bone("chest", (X, -4.0 * e))
        p.bone("neck_01", (X, 4.0 * e))
        finger_curl(p, "r", curl=0.15 + 0.4 * e, spread=0.5)
    else:
        e = _ease_out((t - 0.5) / 0.5)
        arm(p, "r", pitch=-64.0 + 40.0 * e, yaw=10.0, elbow=70.0 - 50.0 * e,
            wrist=-14.0 + 22.0 * e)
        arm(p, "l", pitch=-14.0, yaw=20.0, elbow=52.0, wrist=-8.0)
        p.bone("spine_02", (X, -8.0 + 8.0 * e))
        p.bone("spine_03", (X, -6.0 + 6.0 * e))
        p.bone("chest", (X, -4.0 + 4.0 * e))
        p.bone("neck_01", (X, 4.0 - 4.0 * e))
        finger_curl(p, "r", curl=0.55 - 0.45 * e, spread=0.5 - 0.4 * e)
    look_at(p, pitch=-10.0, eye_pitch=-6.0)
    p.face(expr_focus=0.7)
    return p


@clip("cast_ground", 33, form="one_shot",
      markers=[("cast_build", 1), ("cast_release", 18), ("cast_end", 33)])
def cast_ground(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.55:
        e = _ease(t / 0.55)
        arm(p, "r", pitch=-46.0 - 30.0 * e, yaw=18.0, elbow=62.0 * e,
            wrist=-10.0 * e)
        arm(p, "l", pitch=-10.0, yaw=22.0, elbow=48.0, wrist=-8.0)
        p.bone("pelvis", (X, -6.0 * e))
        p.bone("spine_02", (X, -14.0 * e))
        p.bone("spine_03", (X, -10.0 * e))
        p.bone("chest", (X, -6.0 * e))
        p.bone("neck_01", (X, 18.0 * e))
        look_at(p, pitch=16.0 * e)
        finger_curl(p, "r", curl=0.2 + 0.35 * e, spread=0.45)
    else:
        e = _ease_out((t - 0.55) / 0.45)
        arm(p, "r", pitch=-76.0 + 30.0 * e, yaw=18.0, elbow=62.0 - 34.0 * e,
            wrist=-10.0 + 16.0 * e)
        arm(p, "l", pitch=-10.0, yaw=22.0, elbow=48.0, wrist=-8.0)
        p.bone("pelvis", (X, -6.0 + 6.0 * e))
        p.bone("spine_02", (X, -14.0 + 14.0 * e))
        p.bone("spine_03", (X, -10.0 + 10.0 * e))
        p.bone("chest", (X, -6.0 + 6.0 * e))
        p.bone("neck_01", (X, 18.0 - 16.0 * e))
        look_at(p, pitch=16.0 - 14.0 * e)
        finger_curl(p, "r", curl=0.55 - 0.4 * e, spread=0.45 - 0.35 * e)
    p.face(expr_focus=0.75)
    return p


@clip("cast_self", 24, form="one_shot",
      markers=[("cast_build", 1), ("cast_release", 12), ("cast_end", 24)])
def cast_self(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.5:
        e = _ease(t / 0.5)
        arm(p, "r", pitch=-36.0 - 18.0 * e, yaw=24.0 * e, elbow=76.0 * e,
            wrist=-16.0 * e)
        arm(p, "l", pitch=-36.0 - 18.0 * e, yaw=-24.0 * e, elbow=76.0 * e,
            wrist=-16.0 * e)
        p.bone("spine_02", (X, -10.0 * e))
        p.bone("spine_03", (X, -8.0 * e))
        p.bone("chest", (X, -6.0 * e))
        p.bone("neck_01", (X, 6.0 * e))
        finger_curl(p, "r", curl=0.15 + 0.45 * e, spread=0.5)
        finger_curl(p, "l", curl=0.15 + 0.45 * e, spread=0.5)
    else:
        e = _ease_out((t - 0.5) / 0.5)
        arm(p, "r", pitch=-54.0 + 12.0 * e, yaw=24.0, elbow=76.0 - 30.0 * e,
            wrist=-16.0 + 10.0 * e)
        arm(p, "l", pitch=-54.0 + 12.0 * e, yaw=-24.0, elbow=76.0 - 30.0 * e,
            wrist=-16.0 + 10.0 * e)
        p.bone("spine_02", (X, -10.0 + 10.0 * e))
        p.bone("spine_03", (X, -8.0 + 8.0 * e))
        p.bone("chest", (X, -6.0 + 6.0 * e))
        p.bone("neck_01", (X, 6.0 - 6.0 * e))
        finger_curl(p, "r", curl=0.6 - 0.4 * e, spread=0.5 - 0.4 * e)
        finger_curl(p, "l", curl=0.6 - 0.4 * e, spread=0.5 - 0.4 * e)
    look_at(p, pitch=-6.0)
    p.face(expr_focus=0.6)
    return p


@clip("channel_start", 15, form="one_shot",
      markers=[("channel_start", 1), ("channel_live", 15)])
def channel_start(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease(t)
    arm(p, "r", pitch=-30.0 - 42.0 * e, yaw=8.0, elbow=52.0 - 34.0 * e,
        wrist=-10.0)
    arm(p, "l", pitch=-30.0, yaw=24.0, elbow=62.0, wrist=-8.0)
    p.bone("spine_02", (X, -4.0 * e))
    p.bone("spine_03", (X, -3.0 * e))
    look_at(p, yaw=-4.0, pitch=-3.0)
    finger_curl(p, "r", curl=0.2, spread=0.6)
    return p


@clip("channel_loop", 42, loop=True, form="loop",
      markers=[("channel_pulse", 21)])
def channel_loop(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    w = math.sin(TAU * t)
    arm(p, "r", pitch=-72.0, yaw=8.0, elbow=18.0, wrist=-4.0)
    arm(p, "l", pitch=-30.0, yaw=24.0, elbow=62.0, wrist=-8.0)
    p.bone("spine_02", (X, -4.0), (Z, 1.4 * w))
    p.bone("spine_03", (X, -3.0), (Z, 1.8 * w))
    p.bone("neck_01", (X, 2.0))
    finger_curl(p, "r", curl=0.1, spread=0.7)
    finger_curl(p, "l", curl=0.45, spread=0.25)
    look_at(p, yaw=-4.0, pitch=-3.0)
    p.face(expr_focus=0.55)
    return p


@clip("channel_end", 15, form="one_shot",
      markers=[("channel_release", 4), ("channel_end", 15)])
def channel_end(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(t)
    arm(p, "r", pitch=-72.0 + 34.0 * e, yaw=8.0, elbow=18.0 + 24.0 * e,
        wrist=-4.0 - 4.0 * e)
    arm(p, "l", pitch=-30.0, yaw=24.0, elbow=62.0 - 12.0 * e, wrist=-8.0)
    p.bone("spine_02", (X, -4.0 + 4.0 * e))
    look_at(p, yaw=-4.0 + 4.0 * e, pitch=-3.0)
    finger_curl(p, "r", curl=0.1 + 0.2 * e, spread=0.7 - 0.3 * e)
    return p


@clip("channel_interrupt", 12, form="one_shot",
      markers=[("interrupt", 1), ("channel_end", 12)])
def channel_interrupt(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.35:
        e = _ease_out(t / 0.35)
        arm(p, "r", pitch=-72.0 + 26.0 * e, yaw=8.0 + 16.0 * e,
            elbow=18.0 + 40.0 * e, wrist=-4.0)
        arm(p, "l", pitch=-30.0 - 16.0 * e, yaw=24.0, elbow=62.0, wrist=-8.0)
        p.bone("pelvis", (Z, -6.0 * e), trans=(-0.012 * e, 0.0, -0.020 * e))
        p.bone("spine_02", (Z, -10.0 * e), (X, 6.0 * e))
        p.bone("spine_03", (Z, -12.0 * e))
        look_at(p, yaw=-10.0 * e, pitch=4.0 * e)
        p.face(expr_surprise=0.6 * e)
    else:
        e = _ease((t - 0.35) / 0.65)
        arm(p, "r", pitch=-46.0, yaw=24.0, elbow=58.0, wrist=-4.0)
        arm(p, "l", pitch=-46.0, yaw=24.0, elbow=62.0, wrist=-8.0)
        p.bone("pelvis", (Z, -6.0 * (1.0 - e)))
        p.bone("spine_02", (Z, -10.0 * (1.0 - e)))
        p.bone("spine_03", (Z, -12.0 * (1.0 - e)))
        look_at(p, yaw=-10.0 * (1.0 - e))
    return p


@clip("charge_start", 21, form="one_shot",
      markers=[("charge_start", 1), ("charge_full", 21)])
def charge_start(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease(t)
    arm(p, "r", pitch=-24.0 - 28.0 * e, yaw=14.0, elbow=64.0 * e, wrist=-12.0 * e)
    arm(p, "l", pitch=-18.0 - 14.0 * e, yaw=-18.0 * e, elbow=58.0 * e,
        wrist=-12.0 * e)
    p.bone("pelvis", (X, -6.0 * e), trans=(0.0, 0.0, -0.030 * e))
    p.bone("spine_02", (X, -8.0 * e))
    p.bone("spine_03", (X, -6.0 * e))
    p.bone("chest", (X, -4.0 * e))
    p.bone("neck_01", (X, 4.0 * e))
    finger_curl(p, "r", curl=0.2 + 0.35 * e, spread=0.45)
    finger_curl(p, "l", curl=0.2 + 0.35 * e, spread=0.45)
    look_at(p, pitch=-8.0 * e, eye_pitch=-4.0)
    p.face(expr_focus=0.8)
    return p


@clip("charge_hold", 30, loop=True, form="loop",
      markers=[("charge_pulse", 15)])
def charge_hold(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    w = math.sin(TAU * t)
    arm(p, "r", pitch=-52.0, yaw=14.0, elbow=64.0, wrist=-12.0)
    arm(p, "l", pitch=-32.0, yaw=-18.0, elbow=58.0, wrist=-12.0)
    p.bone("pelvis", (X, -6.0), trans=(0.0, 0.0, -0.030 + 0.004 * w))
    p.bone("spine_02", (X, -8.0 + 1.2 * w))
    p.bone("spine_03", (X, -6.0 + 1.0 * w))
    p.bone("neck_01", (X, 4.0 - 1.0 * w))
    finger_curl(p, "r", curl=0.55, spread=0.45)
    finger_curl(p, "l", curl=0.55, spread=0.45)
    look_at(p, pitch=-8.0, eye_pitch=-4.0)
    p.face(expr_focus=0.85)
    return p


@clip("charge_release", 21, form="one_shot",
      markers=[("charge_release", 4), ("charge_end", 21)])
def charge_release(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.35:
        e = _ease_out(t / 0.35)
        arm(p, "r", pitch=-52.0 + 28.0 * e, yaw=14.0, elbow=64.0 - 20.0 * e,
            wrist=-12.0)
        arm(p, "l", pitch=-32.0, yaw=-18.0, elbow=58.0, wrist=-12.0)
        p.bone("pelvis", (X, -6.0 + 8.0 * e))
        p.bone("spine_02", (X, -8.0 + 10.0 * e))
        p.bone("spine_03", (X, -6.0 + 8.0 * e))
        look_at(p, pitch=-8.0, eye_pitch=-4.0)
    else:
        e = _ease((t - 0.35) / 0.65)
        arm(p, "r", pitch=-24.0 - 6.0 * e, yaw=14.0, elbow=44.0 + 14.0 * e,
            wrist=-12.0)
        arm(p, "l", pitch=-32.0, yaw=-18.0, elbow=58.0, wrist=-12.0)
        p.bone("pelvis", (X, 2.0 - 4.0 * e))
        p.bone("spine_02", (X, 2.0 - 4.0 * e))
        p.bone("spine_03", (X, 2.0 - 4.0 * e))
        look_at(p, pitch=-4.0)
    p.face(expr_focus=0.5)
    return p


@clip("charge_cancel", 15, form="one_shot",
      markers=[("charge_cancel", 1), ("charge_end", 15)])
def charge_cancel(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(t)
    arm(p, "r", pitch=-52.0 + 26.0 * e, yaw=14.0, elbow=64.0 - 30.0 * e,
        wrist=-12.0 + 8.0 * e)
    arm(p, "l", pitch=-32.0 + 10.0 * e, yaw=-18.0, elbow=58.0 - 10.0 * e,
        wrist=-12.0)
    p.bone("pelvis", (X, -6.0 + 6.0 * e))
    p.bone("spine_02", (X, -8.0 + 8.0 * e))
    p.bone("spine_03", (X, -6.0 + 6.0 * e))
    look_at(p, pitch=-8.0 + 4.0 * e)
    p.face(expr_focus=0.85 - 0.4 * e)
    return p


# ---------------------------------------------------------------------------
# props
# ---------------------------------------------------------------------------

@clip("deploy", 36, form="one_shot",
      markers=[("beacon_grab", 4), ("beacon_out", 16), ("beacon_place", 24),
               ("deploy_end", 36)])
def deploy(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.42:
        e = _ease(t / 0.42)
        arm(p, "r", pitch=-40.0 + 10.0 * e, yaw=16.0, elbow=50.0, wrist=-10.0)
        arm(p, "l", pitch=-26.0 - 14.0 * e, yaw=14.0, elbow=62.0, wrist=-10.0)
        p.bone("pelvis", (Z, -6.0 * e))
        p.bone("spine_02", (X, 8.0 * e))
        p.bone("spine_03", (X, 6.0 * e))
        p.bone("neck_01", (X, -10.0 * e))
        look_at(p, pitch=16.0 * e)
        finger_curl(p, "l", curl=0.3 + 0.3 * e, spread=0.3)
    elif t < 0.68:
        e = _ease((t - 0.42) / 0.26)
        arm(p, "r", pitch=-30.0, yaw=16.0, elbow=50.0, wrist=-10.0)
        arm(p, "l", pitch=-40.0 + 16.0 * e, yaw=14.0, elbow=62.0 - 18.0 * e,
            wrist=-10.0)
        p.bone("pelvis", (Z, -6.0 + 6.0 * e))
        p.bone("spine_02", (X, 8.0 - 4.0 * e))
        p.bone("neck_01", (X, -10.0 + 8.0 * e))
        look_at(p, pitch=16.0 - 12.0 * e)
        finger_curl(p, "l", curl=0.6 - 0.2 * e, spread=0.3)
    else:
        e = _ease_out((t - 0.68) / 0.32)
        arm(p, "r", pitch=-30.0, yaw=16.0, elbow=50.0, wrist=-10.0)
        arm(p, "l", pitch=-24.0 - 8.0 * e, yaw=14.0 + 6.0 * e,
            elbow=44.0 + 12.0 * e, wrist=-10.0)
        p.bone("spine_02", (X, 4.0 - 2.0 * e))
        p.bone("neck_01", (X, -2.0 + 2.0 * e))
        look_at(p, pitch=4.0)
        finger_curl(p, "l", curl=0.4, spread=0.3)
    return p


def _uplink_pose(p, t, amount=1.0):
    """Both hands over the console / wrist, feet planted."""
    arm(p, "r", pitch=-62.0 * amount, yaw=16.0, elbow=74.0 * amount,
        wrist=-18.0)
    arm(p, "l", pitch=-58.0 * amount, yaw=-16.0, elbow=70.0 * amount,
        wrist=-16.0)
    p.bone("spine_02", (X, -6.0 * amount))
    p.bone("spine_03", (X, -4.0 * amount))
    p.bone("neck_01", (X, 10.0 * amount))
    finger_curl(p, "r", curl=0.35, spread=0.45)
    finger_curl(p, "l", curl=0.35, spread=0.45)
    look_at(p, pitch=-14.0 * amount, eye_pitch=-8.0)
    return p


@clip("uplink_start", 21, form="one_shot",
      markers=[("uplink_start", 1), ("uplink_live", 21)])
def uplink_start(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    _uplink_pose(p, t, _ease(t))
    return p


@clip("uplink_loop", 42, loop=True, form="loop",
      markers=[("uplink_pulse", 21)])
def uplink_loop(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    w = math.sin(TAU * t)
    _uplink_pose(p, t, 1.0)
    p.bone("spine_02", (X, -6.0 + 0.8 * w))
    p.bone("spine_03", (X, -4.0 + 0.8 * w))
    p.bone("neck_01", (X, 10.0 - 0.8 * w))
    p.face(expr_focus=0.55)
    return p


@clip("uplink_end", 15, form="one_shot",
      markers=[("uplink_complete", 3), ("uplink_end", 15)])
def uplink_end(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(t)
    _uplink_pose(p, t, 1.0 - 0.35 * e)
    look_at(p, pitch=-14.0 + 6.0 * e)
    p.face(expr_focus=0.55 - 0.3 * e, expr_joy=0.35 * e)
    return p


@clip("uplink_cancel", 15, form="one_shot",
      markers=[("uplink_cancel", 1), ("uplink_end", 15)])
def uplink_cancel(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    e = _ease_out(t)
    _uplink_pose(p, t, 1.0 - 0.6 * e)
    p.bone("pelvis", (Z, 4.0 * e))
    look_at(p, yaw=6.0 * e)
    p.face(expr_concern=0.4 * e)
    return p


# ---------------------------------------------------------------------------
# additive hit reactions
# ---------------------------------------------------------------------------

def _hit(p, t, dx, dy, dz):
    """Additive reaction: a sharp impulse that settles."""
    a = _bell(t, 0.16, 0.13)
    b = _bell(t, 0.52, 0.22)
    p.bone("pelvis", (Z, -dx * a * 6.0), (X, dy * a * 5.0),
           trans=(dx * a * 0.05, dy * a * 0.04, dz * a * 0.02))
    p.bone("spine_01", (X, dy * a * 5.0), (Z, -dx * a * 4.0))
    p.bone("spine_02", (X, dy * a * 6.0), (Z, -dx * a * 6.0))
    p.bone("spine_03", (X, dy * (a * 6.0 - b * 3.0)),
           (Z, -dx * (a * 7.0 - b * 3.0)))
    p.bone("chest", (X, dy * (a * 5.0 - b * 2.5)),
           (Z, -dx * (a * 6.0 - b * 2.5)))
    p.bone("neck_01", (X, dy * a * 6.0), (Z, -dx * a * 7.0))
    p.bone("head", (X, dy * a * 7.0), (Z, -dx * a * 8.0))
    return p


@clip("hit_f", 11, form="additive", root_motion="in_place",
      markers=[("impact", 2), ("settle", 8)])
def hit_f(t, rig):
    p = Pose(rig)
    _hit(p, t, 0.0, 1.0, -1.0)
    return p


@clip("hit_b", 11, form="additive", root_motion="in_place",
      markers=[("impact", 2), ("settle", 8)])
def hit_b(t, rig):
    p = Pose(rig)
    _hit(p, t, 0.0, -1.0, 1.0)
    return p


@clip("hit_l", 11, form="additive", root_motion="in_place",
      markers=[("impact", 2), ("settle", 8)])
def hit_l(t, rig):
    p = Pose(rig)
    _hit(p, t, 1.0, 0.0, 0.0)
    return p


@clip("hit_r", 11, form="additive", root_motion="in_place",
      markers=[("impact", 2), ("settle", 8)])
def hit_r(t, rig):
    p = Pose(rig)
    _hit(p, t, -1.0, 0.0, 0.0)
    return p


# ---------------------------------------------------------------------------
# stunned / knocked down / sleep / death
# ---------------------------------------------------------------------------

@clip("stun_start", 27, form="one_shot",
      markers=[("stun_start", 1), ("stun_live", 27)])
def stun_start(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.4:
        e = _ease_out(t / 0.4)
        p.bone("pelvis", (X, 14.0 * e), (Z, 8.0 * e),
               trans=(0.0, 0.020 * e, -0.060 * e))
        p.bone("spine_01", (X, 14.0 * e), (Z, 8.0 * e))
        p.bone("spine_02", (X, 12.0 * e))
        p.bone("spine_03", (X, 10.0 * e))
        p.bone("neck_01", (X, -6.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-8.0 * e, yaw=14.0 * e, elbow=30.0 * e)
        look_at(p, yaw=10.0 * e, pitch=8.0 * e)
    else:
        p.bone("pelvis", (X, 14.0), (Z, 8.0), trans=(0.0, 0.020, -0.060))
        p.bone("spine_01", (X, 14.0), (Z, 8.0))
        p.bone("spine_02", (X, 12.0))
        p.bone("spine_03", (X, 10.0))
        p.bone("neck_01", (X, -6.0))
        for s in ("l", "r"):
            arm(p, s, pitch=-8.0, yaw=14.0, elbow=30.0)
        look_at(p, yaw=10.0, pitch=8.0)
    p.face(expr_surprise=0.5 * _ease(t))
    return p


@clip("stun_loop", 60, loop=True, form="loop",
      markers=[("stun_breath", 30)])
def stun_loop(t, rig):
    p = Pose(rig)
    stance(p)
    w = math.sin(TAU * t)
    w2 = math.sin(TAU * t + 1.4)
    p.bone("pelvis", (X, 14.0 + 1.5 * w), (Z, 8.0 + 2.0 * w),
           trans=(0.0, 0.020, -0.060))
    p.bone("spine_01", (X, 14.0 + 1.5 * w), (Z, 8.0 + 2.0 * w))
    p.bone("spine_02", (X, 12.0 + 1.8 * w2))
    p.bone("spine_03", (X, 10.0 + 1.6 * w))
    p.bone("neck_01", (X, -6.0 + 2.0 * w2))
    for s in ("l", "r"):
        arm(p, s, pitch=-8.0 + 2.0 * w, yaw=14.0, elbow=30.0)
    look_at(p, yaw=10.0 + 4.0 * w2, pitch=8.0)
    p.face(expr_surprise=0.35)
    return p


@clip("stun_end", 27, form="one_shot",
      markers=[("recover_start", 1), ("recover_end", 27)])
def stun_end(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease(t)
    p.bone("pelvis", (X, 14.0 * (1.0 - e)), (Z, 8.0 * (1.0 - e)),
           trans=(0.0, 0.020 * (1.0 - e), -0.060 * (1.0 - e)))
    p.bone("spine_01", (X, 14.0 * (1.0 - e)), (Z, 8.0 * (1.0 - e)))
    p.bone("spine_02", (X, 12.0 * (1.0 - e)))
    p.bone("spine_03", (X, 10.0 * (1.0 - e)))
    p.bone("neck_01", (X, -6.0 * (1.0 - e)))
    for s in ("l", "r"):
        arm(p, s, pitch=-8.0 * (1.0 - e) - 4.0 * e,
            yaw=14.0 * (1.0 - e), elbow=30.0 * (1.0 - e) + 14.0 * e)
    look_at(p, yaw=10.0 * (1.0 - e), pitch=8.0 * (1.0 - e) - 2.0 * e)
    p.face(expr_surprise=0.35 * (1.0 - e))
    return p


@clip("knockback", 21, form="one_shot",
      markers=[("knock_start", 1), ("knock_end", 21)])
def knockback(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease_out(min(t / 0.4, 1.0))
    rec = _ease((t - 0.4) / 0.6)
    p.bone("pelvis", (X, -14.0 * e),
           trans=(0.0, 0.055 * e * (1.0 - 0.4 * rec), -0.030 * e))
    p.bone("spine_01", (X, -12.0 * e))
    p.bone("spine_02", (X, -10.0 * e))
    p.bone("spine_03", (X, -8.0 * e))
    p.bone("neck_01", (X, 10.0 * e))
    for s in ("l", "r"):
        arm(p, s, pitch=34.0 * e, yaw=30.0 * e, elbow=50.0 * e)
    leg(p, "l", hip=-24.0 * e, knee=30.0 * e, ankle=-8.0 * e)
    leg(p, "r", hip=-10.0 * e, knee=20.0 * e, ankle=-6.0 * e)
    look_at(p, pitch=-8.0 * e)
    return p


@clip("knockup_start", 21, form="one_shot",
      markers=[("launch", 1), ("knockup_air", 21)])
def knockup_start(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease_out(t)
    p.bone("pelvis", (X, -26.0 * e), trans=(0.0, 0.0, 0.03 * e))
    p.bone("spine_01", (X, -14.0 * e))
    p.bone("spine_02", (X, -10.0 * e))
    p.bone("spine_03", (X, -6.0 * e))
    p.bone("neck_01", (X, 12.0 * e))
    leg(p, "l", hip=-40.0 * e, knee=56.0 * e, ankle=-14.0 * e)
    leg(p, "r", hip=-32.0 * e, knee=48.0 * e, ankle=-12.0 * e)
    for s in ("l", "r"):
        arm(p, s, pitch=-30.0 * e, yaw=40.0 * e, elbow=30.0 * e)
    look_at(p, pitch=-10.0 * e)
    p.face(expr_surprise=0.5 * e)
    return p


@clip("knockup_air", 30, loop=True, form="loop",
      markers=[("knockup_tumble", 15)])
def knockup_air(t, rig):
    p = Pose(rig)
    stance(p)
    w = math.sin(TAU * t)
    p.bone("pelvis", (X, -22.0 + 4.0 * w), (Z, 8.0 * w),
           trans=(0.0, 0.0, 0.02))
    p.bone("spine_01", (X, -12.0 + 3.0 * w), (Z, 6.0 * w))
    p.bone("spine_02", (X, -9.0 + 3.0 * w))
    p.bone("neck_01", (X, 12.0 - 3.0 * w))
    leg(p, "l", hip=-36.0 + 8.0 * w, knee=50.0, ankle=-12.0)
    leg(p, "r", hip=-28.0 - 8.0 * w, knee=42.0, ankle=-10.0)
    for s in ("l", "r"):
        arm(p, s, pitch=-26.0 + 8.0 * w, yaw=36.0, elbow=36.0)
    look_at(p, pitch=-12.0)
    p.face(expr_surprise=0.55)
    return p


def _prone(p, t, front=True):
    """Face-down (front=True) or face-up floor pose."""
    w = math.sin(TAU * t)
    sign = 1.0 if front else -1.0
    p.bone("pelvis", (X, 84.0 * sign), trans=(0.0, 0.0, -0.80))
    p.bone("spine_01", (X, 4.0 * sign), (Z, 3.0 * w))
    p.bone("spine_02", (X, 3.0 * sign), (Z, 4.0 * w))
    p.bone("spine_03", (X, 2.0 * sign))
    p.bone("neck_01", (X, -16.0 * sign), (Z, 3.0 * w))
    for s in ("l", "r"):
        arm(p, s, pitch=-24.0 * sign, yaw=26.0, elbow=34.0)
    leg(p, "l", hip=-8.0 * sign, knee=14.0, ankle=-4.0)
    leg(p, "r", hip=-6.0 * sign, knee=12.0, ankle=-4.0)
    return p


@clip("knockdown_front", 42, form="one_shot",
      markers=[("impact", 4), ("fall", 14), ("ground", 30),
               ("knockdown_end", 42)])
def knockdown_front(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.25:
        e = _ease_out(t / 0.25)
        p.bone("pelvis", (X, 22.0 * e), trans=(0.0, 0.030 * e, -0.050 * e))
        p.bone("spine_01", (X, 16.0 * e))
        p.bone("spine_02", (X, 12.0 * e))
        p.bone("neck_01", (X, -14.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=26.0 * e, yaw=30.0 * e, elbow=40.0 * e)
        leg(p, "l", hip=-20.0 * e, knee=30.0 * e, ankle=-8.0 * e)
        leg(p, "r", hip=-14.0 * e, knee=24.0 * e, ankle=-6.0 * e)
    else:
        _prone(p, _ease((t - 0.25) / 0.75), front=True)
    return p


@clip("knockdown_back", 42, form="one_shot",
      markers=[("impact", 4), ("fall", 14), ("ground", 30),
               ("knockdown_end", 42)])
def knockdown_back(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.25:
        e = _ease_out(t / 0.25)
        p.bone("pelvis", (X, -18.0 * e), trans=(0.0, -0.030 * e, -0.040 * e))
        p.bone("spine_01", (X, -14.0 * e))
        p.bone("spine_02", (X, -10.0 * e))
        p.bone("neck_01", (X, 10.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-20.0 * e, yaw=26.0 * e, elbow=36.0 * e)
        leg(p, "l", hip=-16.0 * e, knee=26.0 * e, ankle=-8.0 * e)
        leg(p, "r", hip=-12.0 * e, knee=22.0 * e, ankle=-6.0 * e)
    else:
        _prone(p, _ease((t - 0.25) / 0.75), front=False)
    return p


@clip("prone_front", 60, loop=True, form="loop",
      markers=[("prone_breath", 30)])
def prone_front(t, rig):
    p = Pose(rig)
    _prone(p, t, front=True)
    return p


@clip("prone_back", 60, loop=True, form="loop",
      markers=[("prone_breath", 30)])
def prone_back(t, rig):
    p = Pose(rig)
    _prone(p, t, front=False)
    return p


def _getup(p, t, front=True):
    """Stand up from the floor, using a supporting hand."""
    sign = 1.0 if front else -1.0
    if t < 0.45:
        e = _ease(t / 0.45)
        p.bone("pelvis", (X, (84.0 - 44.0 * e) * sign), (Z, 8.0 * e),
               trans=(0.0, 0.0, -0.80 + 0.34 * e))
        p.bone("spine_01", (X, 4.0 * sign))
        p.bone("spine_02", (X, 3.0 * sign), (Z, 4.0 * e))
        p.bone("neck_01", (X, -16.0 * sign))
        arm(p, "l", pitch=-56.0 * sign, yaw=18.0, elbow=24.0 * e)
        arm(p, "r", pitch=-40.0 * sign, yaw=-14.0, elbow=40.0 * e)
        leg(p, "l", hip=-46.0 * e, knee=72.0 * e, ankle=-16.0 * e)
        leg(p, "r", hip=-24.0 * e, knee=48.0 * e, ankle=-10.0 * e)
    else:
        e = _ease((t - 0.45) / 0.55)
        p.bone("pelvis", (X, (40.0 - 46.0 * e) * sign), (Z, 8.0 * (1.0 - e)),
               trans=(0.0, 0.0, -0.46 + 0.46 * e))
        p.bone("spine_01", (X, 4.0 * sign * (1.0 - e)))
        p.bone("spine_02", (X, 3.0 * sign * (1.0 - e)), (Z, 4.0 * (1.0 - e)))
        p.bone("neck_01", (X, -16.0 * sign * (1.0 - e)))
        arm(p, "l", pitch=-56.0 * sign * (1.0 - e) - 16.0 * e, yaw=18.0,
            elbow=24.0 * (1.0 - e) + 34.0 * e)
        arm(p, "r", pitch=-40.0 * sign * (1.0 - e) - 4.0 * e, yaw=-14.0,
            elbow=40.0 * (1.0 - e) + 12.0 * e)
        leg(p, "l", hip=-46.0 * (1.0 - e) - 6.0 * e,
            knee=72.0 * (1.0 - e) - 60.0 * e, ankle=-16.0 * (1.0 - e))
        leg(p, "r", hip=-24.0 * (1.0 - e) - 4.0 * e,
            knee=48.0 * (1.0 - e) - 38.0 * e, ankle=-10.0 * (1.0 - e))
    return p


@clip("getup_front", 54, form="one_shot",
      markers=[("push_up", 6), ("knee_up", 26), ("stand", 40),
               ("getup_end", 54)])
def getup_front(t, rig):
    p = Pose(rig)
    _getup(p, t, front=True)
    return p


@clip("getup_back", 54, form="one_shot",
      markers=[("roll_up", 6), ("knee_up", 26), ("stand", 40),
               ("getup_end", 54)])
def getup_back(t, rig):
    p = Pose(rig)
    _getup(p, t, front=False)
    return p


def _sleep_pose(p, t):
    """Standing but slumped asleep, head dropped."""
    w = math.sin(TAU * t)
    p.bone("pelvis", (X, 6.0 + 1.0 * w), trans=(0.0, 0.012, -0.030))
    p.bone("spine_01", (X, 10.0 + 1.0 * w))
    p.bone("spine_02", (X, 9.0 + 1.2 * w))
    p.bone("spine_03", (X, 7.0 + 1.0 * w))
    p.bone("neck_01", (X, 14.0 + 1.2 * w))
    for s in ("l", "r"):
        arm(p, s, pitch=-2.0, yaw=3.0, elbow=12.0 + 1.0 * w)
        finger_curl(p, s, curl=0.25, spread=0.1)
    leg(p, "l", hip=-3.0, knee=7.0, ankle=-2.0)
    leg(p, "r", hip=-2.0, knee=6.0, ankle=-2.0)
    return p


@clip("sleep_start", 30, form="one_shot",
      markers=[("sleep_start", 1), ("sleep_live", 30)])
def sleep_start(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease(t)
    p.bone("pelvis", (X, 6.0 * e), trans=(0.0, 0.012 * e, -0.030 * e))
    p.bone("spine_01", (X, 10.0 * e))
    p.bone("spine_02", (X, 9.0 * e))
    p.bone("spine_03", (X, 7.0 * e))
    p.bone("neck_01", (X, 14.0 * e))
    for s in ("l", "r"):
        arm(p, s, pitch=-2.0 * e, yaw=3.0 * e, elbow=12.0 * e)
    blink(p, e)
    return p


@clip("sleep_loop", 75, loop=True, form="loop",
      markers=[("sleep_breath", 36)])
def sleep_loop(t, rig):
    p = Pose(rig)
    _sleep_pose(p, t)
    blink(p, 1.0)
    return p


@clip("sleep_end", 30, form="one_shot",
      markers=[("wake", 1), ("alert", 24), ("sleep_end", 30)])
def sleep_end(t, rig):
    p = Pose(rig)
    stance(p)
    e = _ease_out(t)
    p.bone("pelvis", (X, 6.0 * (1.0 - e)),
           trans=(0.0, 0.012 * (1.0 - e), -0.030 * (1.0 - e)))
    p.bone("spine_01", (X, 10.0 * (1.0 - e)))
    p.bone("spine_02", (X, 9.0 * (1.0 - e)))
    p.bone("spine_03", (X, 7.0 * (1.0 - e)))
    p.bone("neck_01", (X, 14.0 * (1.0 - e)))
    for s in ("l", "r"):
        arm(p, s, pitch=-2.0 * (1.0 - e), yaw=3.0 * (1.0 - e),
            elbow=12.0 * (1.0 - e) + 14.0 * e)
    blink(p, max(0.0, 1.0 - e * 1.8))
    look_at(p, yaw=4.0 * e, pitch=-4.0 * e)
    return p


def _death_pose(p, t, front=True):
    """Collapse to the floor; `front` decides the final orientation."""
    if t < 0.35:
        e = _ease_out(t / 0.35)
        p.bone("pelvis", (X, (22.0 if front else -20.0) * e),
               trans=(0.0, 0.0, -0.075 * e))
        p.bone("spine_01", (X, (16.0 if front else -14.0) * e))
        p.bone("spine_02", (X, (12.0 if front else -10.0) * e))
        p.bone("neck_01", (X, (-16.0 if front else 12.0) * e))
        for s in ("l", "r"):
            arm(p, s, pitch=(24.0 if front else -18.0) * e, yaw=28.0 * e,
                elbow=30.0 * e)
        leg(p, "l", hip=-16.0 * e, knee=26.0 * e, ankle=-8.0 * e)
        leg(p, "r", hip=-10.0 * e, knee=20.0 * e, ankle=-6.0 * e)
    else:
        _prone(p, _ease((t - 0.35) / 0.65), front=front)
        p.bone("neck_01", (X, -20.0 if front else 16.0))
        for s in ("l", "r"):
            arm(p, s, pitch=-30.0 if front else 26.0, yaw=34.0, elbow=18.0)
    return p


@clip("death_front", 60, form="one_shot",
      markers=[("impact", 6), ("collapse", 18), ("settled", 44),
               ("death_end", 60)])
def death_front(t, rig):
    p = Pose(rig)
    _death_pose(p, t, front=True)
    p.face(expr_pain=0.4)
    return p


@clip("death_back", 60, form="one_shot",
      markers=[("impact", 6), ("collapse", 18), ("settled", 44),
               ("death_end", 60)])
def death_back(t, rig):
    p = Pose(rig)
    _death_pose(p, t, front=False)
    p.face(expr_pain=0.3)
    return p


@clip("dead_front", 2, form="pose", root_motion="in_place",
      markers=[("dead", 1)])
def dead_front(t, rig):
    p = Pose(rig)
    _prone(p, 0.0, front=True)
    p.bone("neck_01", (X, -20.0))
    for s in ("l", "r"):
        arm(p, s, pitch=-30.0, yaw=34.0, elbow=18.0)
    return p


# two identical frames, so the exported sequence has a usable length
@clip("dead_back", 2, form="pose", root_motion="in_place",
      markers=[("dead", 1)])
def dead_back(t, rig):
    p = Pose(rig)
    _prone(p, 0.0, front=False)
    p.bone("neck_01", (X, 16.0))
    for s in ("l", "r"):
        arm(p, s, pitch=26.0, yaw=34.0, elbow=18.0)
    return p


@clip("respawn", 54, form="one_shot",
      markers=[("reconstruct", 1), ("materialise", 20), ("settle", 38),
               ("respawn_end", 54)])
def respawn(t, rig):
    p = Pose(rig)
    stance(p, combat=True)
    if t < 0.38:
        e = _ease_out(t / 0.38)
        p.bone("pelvis", (X, 18.0 * e), trans=(0.0, 0.0, -0.140 * e))
        p.bone("spine_01", (X, 16.0 * e))
        p.bone("spine_02", (X, 14.0 * e))
        p.bone("spine_03", (X, 10.0 * e))
        p.bone("neck_01", (X, -8.0 * e))
        leg(p, "l", hip=-40.0 * e, knee=68.0 * e, ankle=-18.0 * e)
        leg(p, "r", hip=-40.0 * e, knee=68.0 * e, ankle=-18.0 * e)
        for s in ("l", "r"):
            arm(p, s, pitch=-8.0 * e, yaw=16.0 * e, elbow=58.0 * e)
        blink(p, 1.0 - 0.3 * e)
    else:
        e = _ease((t - 0.38) / 0.62)
        stance(p, combat=True)
        p.bone("pelvis", (X, -14.0 * (1.0 - e)),
               trans=(0.0, 0.0, -0.140 * (1.0 - e)))
        p.bone("spine_02", (X, -14.0 * (1.0 - e)))
        p.bone("spine_03", (X, -10.0 * (1.0 - e)))
        leg(p, "l", hip=-40.0 * (1.0 - e) + 33.0 * e,
            knee=68.0 * (1.0 - e) - 58.0 * e, ankle=-18.0 * (1.0 - e) + 15.0 * e)
        leg(p, "r", hip=-40.0 * (1.0 - e) + 33.0 * e,
            knee=68.0 * (1.0 - e) - 58.0 * e, ankle=-18.0 * (1.0 - e) + 15.0 * e)
        for s in ("l", "r"):
            arm(p, s, pitch=-8.0 * (1.0 - e) - 12.0 * e,
                yaw=16.0 * (1.0 - e), elbow=58.0 * (1.0 - e) - 20.0 * e)
        blink(p, max(0.0, 0.7 * (1.0 - e) - 0.4 * e))
    look_at(p, pitch=-4.0)
    p.face(expr_focus=0.4 * _ease(t))
    return p


# ---------------------------------------------------------------------------
# social
# ---------------------------------------------------------------------------

@clip("greet", 48, form="one_shot",
      markers=[("greet_start", 1), ("gesture", 14), ("greet_end", 48)])
def greet(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.35:
        e = _ease(t / 0.35)
        arm(p, "r", pitch=-30.0 * e, yaw=-18.0 * e, elbow=70.0 * e,
            wrist=-20.0 * e)
        arm(p, "l", pitch=-4.0, yaw=8.0, elbow=18.0)
        p.bone("spine_02", (Z, -6.0 * e))
        look_at(p, yaw=-6.0 * e)
        finger_curl(p, "r", curl=0.2 + 0.3 * e, spread=0.4)
    elif t < 0.62:
        e = _ease((t - 0.35) / 0.27)
        arm(p, "r", pitch=-30.0 + 14.0 * e, yaw=-18.0 - 10.0 * e,
            elbow=70.0 - 30.0 * e, wrist=-20.0 + 14.0 * e)
        arm(p, "l", pitch=-4.0, yaw=8.0, elbow=18.0)
        look_at(p, yaw=-10.0 * e)
        finger_curl(p, "r", curl=0.5 - 0.3 * e, spread=0.4 + 0.4 * e)
        p.face(expr_joy=0.55 * e)
    else:
        e = _ease_out((t - 0.62) / 0.38)
        arm(p, "r", pitch=-16.0 * (1.0 - e), yaw=-28.0 * (1.0 - e),
            elbow=40.0 * (1.0 - e) + 18.0 * e, wrist=-6.0 * (1.0 - e))
        arm(p, "l", pitch=-4.0, yaw=8.0, elbow=18.0)
        look_at(p, yaw=-10.0 * (1.0 - e))
        finger_curl(p, "r", curl=0.2, spread=0.5)
        p.face(expr_joy=0.55 * (1.0 - e))
    return p


@clip("victory", 60, form="one_shot",
      markers=[("raise", 12), ("hold", 30), ("lower", 48)])
def victory(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.40:
        e = _ease(t / 0.40)
        arm(p, "r", pitch=-24.0 - 96.0 * e, yaw=-10.0 * e, elbow=52.0 * e,
            wrist=-18.0)
        arm(p, "l", pitch=-6.0 - 12.0 * e, yaw=10.0, elbow=30.0 * e)
        p.bone("spine_02", (X, -6.0 * e))
        p.bone("spine_03", (X, -4.0 * e))
        look_at(p, pitch=-14.0 * e)
        finger_curl(p, "r", curl=0.1, spread=0.55)
        p.face(expr_joy=0.7 * e)
    elif t < 0.72:
        arm(p, "r", pitch=-120.0, yaw=-10.0, elbow=52.0, wrist=-18.0)
        arm(p, "l", pitch=-18.0, yaw=10.0, elbow=30.0)
        p.bone("spine_02", (X, -6.0))
        p.bone("spine_03", (X, -4.0))
        look_at(p, pitch=-14.0)
        finger_curl(p, "r", curl=0.1, spread=0.55)
        p.face(expr_joy=0.85)
    else:
        e = _ease_out((t - 0.72) / 0.28)
        arm(p, "r", pitch=-120.0 + 60.0 * e, yaw=-10.0, elbow=52.0 - 14.0 * e,
            wrist=-18.0)
        arm(p, "l", pitch=-18.0 + 8.0 * e, yaw=10.0, elbow=30.0)
        p.bone("spine_02", (X, -6.0 * (1.0 - e)))
        look_at(p, pitch=-14.0 * (1.0 - e))
        finger_curl(p, "r", curl=0.1, spread=0.55)
        p.face(expr_joy=0.85 * (1.0 - 0.4 * e))
    return p


@clip("defeat", 48, form="one_shot",
      markers=[("sag", 10), ("hold", 26), ("recover", 40)])
def defeat(t, rig):
    p = Pose(rig)
    stance(p)
    if t < 0.42:
        e = _ease(t / 0.42)
        p.bone("pelvis", (X, 12.0 * e), trans=(0.0, 0.006 * e, -0.035 * e))
        p.bone("spine_01", (X, 12.0 * e))
        p.bone("spine_02", (X, 10.0 * e))
        p.bone("spine_03", (X, 7.0 * e))
        p.bone("neck_01", (X, 16.0 * e))
        for s in ("l", "r"):
            arm(p, s, pitch=-2.0 * e, yaw=4.0 * e, elbow=12.0 * e)
        look_at(p, pitch=10.0 * e)
        p.face(expr_concern=0.6 * e)
    elif t < 0.68:
        p.bone("pelvis", (X, 12.0), trans=(0.0, 0.006, -0.035))
        p.bone("spine_01", (X, 12.0))
        p.bone("spine_02", (X, 10.0))
        p.bone("spine_03", (X, 7.0))
        p.bone("neck_01", (X, 16.0))
        for s in ("l", "r"):
            arm(p, s, pitch=-2.0, yaw=4.0, elbow=12.0)
        look_at(p, pitch=10.0)
        p.face(expr_concern=0.6)
    else:
        e = _ease_out((t - 0.68) / 0.32)
        p.bone("pelvis", (X, 12.0 * (1.0 - e)),
               trans=(0.0, 0.006 * (1.0 - e), -0.035 * (1.0 - e)))
        p.bone("spine_01", (X, 12.0 * (1.0 - e)))
        p.bone("spine_02", (X, 10.0 * (1.0 - e)))
        p.bone("neck_01", (X, 16.0 * (1.0 - e)))
        for s in ("l", "r"):
            arm(p, s, pitch=-2.0 * (1.0 - e), yaw=4.0 * (1.0 - e),
                elbow=12.0 * (1.0 - e))
        look_at(p, pitch=10.0 * (1.0 - e))
        p.face(expr_concern=0.6 * (1.0 - e))
    return p


# ---------------------------------------------------------------------------
# aim grid (nine static upper body samples)
# ---------------------------------------------------------------------------

def _aim(p, yaw, pitch):
    """Aim pose: yaw positive = to the character's right, pitch positive = down."""
    stance(p, combat=True)
    p.bone("pelvis", (Z, yaw * 0.14))
    p.bone("spine_01", (Z, yaw * 0.22))
    p.bone("spine_02", (Z, yaw * 0.26), (X, pitch * 0.16))
    p.bone("spine_03", (Z, yaw * 0.24), (X, pitch * 0.18))
    p.bone("chest", (Z, yaw * 0.22), (X, pitch * 0.16))
    p.bone("neck_01", (Z, yaw * 0.10), (X, pitch * 0.12))
    look_at(p, yaw=yaw * 0.30, pitch=pitch * 0.55,
            eye_yaw=yaw * 0.10, eye_pitch=pitch * 0.25)
    p.bone("clavicle_r", (Z, -yaw * 0.10), (X, -6.0))
    p.bone("upperarm_r", (X, -66.0), (Y, -16.0), (Z, yaw * 0.18))
    p.bone("lowerarm_r", (X, -34.0), (Z, yaw * 0.12))
    p.bone("hand_r", (X, -26.0), (Z, yaw * 0.10))
    p.bone("clavicle_l", (Z, yaw * 0.08), (X, -4.0))
    p.bone("upperarm_l", (X, -44.0), (Y, 22.0), (Z, yaw * 0.14))
    p.bone("lowerarm_l", (X, -72.0), (Z, yaw * 0.10))
    p.bone("hand_l", (X, -12.0))
    finger_curl(p, "r", curl=0.42, spread=0.12)
    finger_curl(p, "l", curl=0.5, spread=0.2)
    p.face(expr_focus=0.55)
    return p


def _make_aim(name, yaw, pitch):
    def fn(t, rig):
        p = Pose(rig)
        _aim(p, yaw, pitch)
        return p
    fn.__name__ = name
    return fn


for _yaw, _ysuf in ((-60.0, "left"), (0.0, "center"), (60.0, "right")):
    for _pitch, _psuf in ((-35.0, "up"), (0.0, "level"), (35.0, "down")):
        _nm = "aim_%s_%s" % (_psuf, _ysuf)
        # two identical frames, so the exported sequence has a usable length
        CLIPS.append(dict(name=_nm, frames=2, loop=False,
                           fn=_make_aim(_nm, _yaw, _pitch),
                           markers=[("aim", 1)], root_motion="in_place",
                           speed=0.0, interp="BEZIER", form="pose"))
        CLIP_INDEX[_nm] = CLIPS[-1]


# ---------------------------------------------------------------------------
# dialogue (performance driven by the speech alignment file)
# ---------------------------------------------------------------------------

_ALIGNMENT = None


def _load_alignment():
    global _ALIGNMENT
    if _ALIGNMENT is None:
        import json
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "..", "audio", "dialogue_alignment.json")
        try:
            with open(path) as fh:
                _ALIGNMENT = json.load(fh)
        except Exception:
            _ALIGNMENT = {"words": [], "duration": 15.0}
    return _ALIGNMENT


def _viseme_for(word):
    """Map a word to a viseme name using simple letter heuristics."""
    w = word.lower()
    if not w:
        return "vis_sil"
    if "m" in w or "b" in w or "p" in w:
        return "vis_mb"
    if "f" in w or "v" in w:
        return "vis_ff"
    if "th" in w:
        return "vis_th"
    if "l" in w or "n" in w:
        return "vis_l"
    if any(c in w for c in "ou"):
        return "vis_oo"
    if any(c in w for c in "eiy"):
        return "vis_ee"
    if any(c in w for c in "ae"):
        return "vis_eh"
    return "vis_sil"


@clip("dialogue", 450, form="one_shot",
      markers=[("line_start", 1), ("line_end", 450)])
def dialogue(t, rig):
    """Authored spoken performance synchronised to the dialogue audio."""
    p = Pose(rig)
    stance(p)
    align = _load_alignment()
    # the clip is 450 frames at 30 fps; the alignment times are absolute
    # seconds inside that window
    now = t * (450 / 30.0)
    words = align.get("words", [])
    cur = None
    for i, w in enumerate(words):
        if w["start"] <= now <= w["end"]:
            cur = (w, i)
            break
    if cur is None:
        past = [w for w in words if w["end"] <= now]
        cur = (past[-1], len(past)) if past else (None, 0)
    word, widx = cur
    vis = _viseme_for(word["word"] if word else "")
    ph = 0.0
    if word:
        span = max(word["end"] - word["start"], 1e-3)
        ph = (now - word["start"]) / span
    amt = 0.0
    if word:
        amt = min(1.0, ph / 0.22) * min(1.0, (1.0 - ph) / 0.28 + 0.25)
    shape = {"vis_sil": 0.0, "vis_mb": 0.75, "vis_eh": 0.70, "vis_ee": 0.65,
             "vis_oo": 0.70, "vis_ff": 0.60, "vis_th": 0.55, "vis_l": 0.60}
    p.face(**{vis: shape.get(vis, 0.6) * amt})
    p.face(jaw_open=0.32 * amt)
    sway = math.sin(TAU * t * 1.5)
    sway2 = math.sin(TAU * t * 1.5 + 1.9)
    emphasis = _bell(t, 0.28, 0.06) + _bell(t, 0.62, 0.07)
    p.bone("pelvis", (Z, 2.0 * sway),
           trans=(0.012 * sway, 0.0, -0.006 * abs(sway)))
    p.bone("spine_01", (Z, -1.6 * sway))
    p.bone("spine_02", (X, -1.4))
    p.bone("spine_03", (X, -1.0), (Z, -1.8 * sway))
    p.bone("chest", (Z, -2.2 * sway))
    p.bone("neck_01", (X, 1.0))
    look_at(p, yaw=5.0 * sway2 + 6.0 * emphasis, pitch=-2.0 + 3.0 * sway,
            eye_yaw=3.0 * sway2 + 4.0 * emphasis, eye_pitch=1.5 * sway)
    arm(p, "r", pitch=-16.0 * emphasis - 4.0, yaw=12.0,
        elbow=44.0 + 18.0 * emphasis, wrist=-10.0)
    arm(p, "l", pitch=-10.0 * emphasis - 2.0, yaw=14.0,
        elbow=40.0 + 16.0 * emphasis, wrist=-8.0)
    finger_curl(p, "r", curl=0.28 + 0.25 * emphasis, spread=0.3)
    finger_curl(p, "l", curl=0.30 + 0.25 * emphasis, spread=0.3)
    shift = max(0.0, min(1.0, (t - 0.45) / 0.35))
    p.face(expr_focus=0.35 + 0.25 * shift)
    p.face(expr_joy=0.45 * shift)
    return p


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

def manifest():
    out = []
    for c in CLIPS:
        out.append(dict(id=c["name"], form=c.get("form", "one_shot"),
                        root_movement=c.get("root_motion", "in_place"),
                        frames=c["frames"], start=1, end=c["frames"],
                        duration=round(c["frames"] / 30.0, 4),
                        loop=bool(c.get("loop", False)),
                        speed=c.get("speed", 0.0),
                        markers=[m[0] for m in c.get("markers", [])]))
    return out

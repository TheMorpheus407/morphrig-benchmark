"""Hand-authored clips, part 1: idles, start/stop/turn/pivot, jump/fall/land, dash, blink.
Key poses use keypose.resolve(); world foot planting via keypose.plant()."""
import math
import numpy as np
from mathutils import Vector
import anim_lib as AL
from anim_lib import Pose
import face_lib as FL
import gait
import pose_lib as PL
from keypose import resolve, build_clip, plant, foot_rest, aim_dir
from anim_registry import clip

TAU = 2 * math.pi
FK = lambda **kw: ('fk', kw)
FKS = lambda **kw: ('fk', dict(kw, sagittal=True))     # abd = away from the body at any elevation (anim_lib.arm_fk); use above the shoulders


def relaxed(**o):
    k = dict(pelvis=(0.0, 0.0, -0.022), pelvis_rot=(0, 0, 0), spine=(0, 0, 0), neck=(0, 0, 0), fl=foot_rest('l'), fr=foot_rest('r'),
             al=FK(flex=4, abd=-20, elbow=14), ar=FK(flex=4, abd=-20, elbow=14), hl=dict(curl=0.25), hr=dict(curl=0.25))
    k.update(o)
    return k


def combat(**o):
    k = dict(pelvis=(0.0, 0.0, -0.095), pelvis_rot=(0, 3, -8), spine=(9, -16, 0), neck=(-8, 10, 0),
             fl=foot_rest('l', x=0.16, y=0.035, yaw=-10), fr=foot_rest('r', x=-0.14, y=-0.06, yaw=-25),
             al=FK(flex=62, abd=8, elbow=78), ar=FK(flex=38, abd=-14, elbow=104), hl=dict(curl=0.7), hr=dict(curl=0.85))
    k.update(o)
    return k


def add_blinks(c, frames, dur=6):
    """Blink keys at the given clip frames (lids closed for ~2 frames), zero at the clip ends."""
    for b in frames:
        for df, a in ((-1, 0.0), (2, 1.0), (3, 1.0), (dur, 0.0)):
            f = min(max(b + df, 0), c.frames)
            c.key(f, FL.blink_both(a))
    for f in (0, c.frames):
        c.key(f, FL.blink_both(0.0)) if not any(k[0] == 'ctl_lid_up_l' and f in d for k, d in c.keys.items()) else None


def add_gaze(c, seq):
    """seq: list of (frame, yaw, pitch)."""
    for f, y, p in seq:
        c.key(min(max(f, 0), c.frames), FL.gaze(y, p))


# ----------------------------------------------------------------------------- idles

@clip('idle_relaxed')
def idle_relaxed(e):
    N = e['frames']
    keys = []
    for i in range(13):
        t = i / 12
        s = math.sin(TAU * t)
        br = 0.5 - 0.5 * math.cos(2 * TAU * t)
        k = relaxed(pelvis=(0.0, 0.012 * s, -0.022 - 0.004 * br), spine=(1.4 * br + 0.5 * s, 2.0 * s, 0.9 * s),
                    neck=(-0.8 * br + 1.0 * math.sin(TAU * t + 1.0), 3.5 * math.sin(TAU * t + 0.6), 0.0),
                    al=FK(flex=4 + 1.2 * br, abd=-20 - 0.8 * br, elbow=14 + 1.5 * s), ar=FK(flex=4 + 1.2 * br, abd=-20 - 0.8 * br, elbow=14 - 1.5 * s),
                    fr=foot_rest('r', y=-0.004 * s, yaw=1.5 * s), fl=foot_rest('l', yaw=-1.0 * s))
        keys.append((t, k))
    c = build_clip('idle_relaxed', e, keys, note='relaxed breathing with a weight shift, head drift and blinks')
    add_blinks(c, [int(N * 0.31), int(N * 0.83)])
    add_gaze(c, [(0, 0, 0), (int(N * 0.2), -8, 2), (int(N * 0.45), 6, -1), (int(N * 0.72), 0, 3), (N, 0, 0)])
    return c


@clip('idle_combat')
def idle_combat(e):
    N = e['frames']
    keys = []
    for i in range(9):
        t = i / 8
        bounce = 0.5 - 0.5 * math.cos(2 * TAU * t)
        s = math.sin(TAU * t)
        k = combat(pelvis=(0.0, 0.006 * s, -0.095 - 0.012 * bounce), spine=(9 + 1.5 * bounce, -16 + 2.0 * s, 1.0 * s),
                   neck=(-8 + 0.8 * bounce, 10 + 5.0 * math.sin(TAU * t + 1.0), 0),
                   al=FK(flex=62 + 2.0 * math.sin(TAU * t + 0.8), abd=8, elbow=78 + 3.0 * bounce), ar=FK(flex=38 + 1.5 * bounce, abd=-14, elbow=104 - 2.0 * bounce))
        keys.append((t, k))
    c = build_clip('idle_combat', e, keys, note='ready stance with a breathing bounce and target scanning')
    add_blinks(c, [int(N * 0.42)])
    add_gaze(c, [(0, 0, 0), (int(N * 0.3), 10, 0), (int(N * 0.6), -10, 2), (N, 0, 0)])
    c.key(0, FL.expression('focus', 0.45))
    c.key(N, FL.expression('focus', 0.45))
    c.key(int(N * 0.5), FL.expression('focus', 0.6))
    return c


@clip('idle_wounded')
def idle_wounded(e):
    N = e['frames']
    keys = []
    for i in range(10):
        t = i / 9
        s = math.sin(TAU * t)
        br = 0.5 - 0.5 * math.cos(2 * TAU * t)
        k = relaxed(pelvis=(0.0, 0.032 + 0.008 * s, -0.078 - 0.006 * br), pelvis_rot=(3, 8, 6), spine=(16 + 3.0 * br, 6 * s, 4), neck=(10 + 1.5 * br, -5 + 4 * s, 3),
                    fl=foot_rest('l', x=-0.02, yaw=-6), fr=foot_rest('r', x=0.09, y=-0.03, yaw=-14, roll=18),
                    al=FK(flex=10, abd=-8, elbow=22, wflex=8), ar=('ik', dict(target=(0.11, 0.06, 1.13 + 0.006 * br), dir=(0.15, 0.85, -0.45), palm=(-0.3, 0.2, 0.9), elbow_hint=(-0.10, -0.24, 1.05))),
                    hl=dict(curl=0.15), hr=dict(curl=0.5, spread=-0.3))
        k['face'] = FL.expression('pain', 0.32 + 0.12 * math.sin(TAU * t * 2))
        keys.append((t, k))
    c = build_clip('idle_wounded', e, keys, note='hunched, right hand on the left flank, weight on the left leg, laboured breathing')
    add_blinks(c, [int(N * 0.2), int(N * 0.66), int(N * 0.72)])
    add_gaze(c, [(0, 0, -6), (int(N * 0.5), -6, -8), (N, 0, -6)])
    return c


# ----------------------------------------------------------------------------- start / stop / turn / pivot

WALK_T = 27 / 30.0


@clip('start_f')
def start_f(e):
    walk0 = gait.gait_model('walk', 0.0, 150, WALK_T)(0.0)
    keys = [
        (0.0, relaxed()),
        (0.22, relaxed(pelvis=(0.0, -0.02, -0.06), pelvis_rot=(0, 3, 0), spine=(4, 0, 0), fl=foot_rest('l', roll=22), al=FK(flex=2, abd=-18, elbow=18), ar=FK(flex=6, abd=-18, elbow=18))),
        (0.45, relaxed(pelvis=(0.0, -0.01, -0.07), pelvis_rot=(0, 5, 0), spine=(8, -4, 0), fl=foot_rest('l', x=0.26, z=0.10, roll=8), fr=foot_rest('r', x=-0.13, roll=14),
                       al=FK(flex=-14, abd=-18, elbow=32), ar=FK(flex=16, abd=-18, elbow=32), hl=dict(curl=0.4), hr=dict(curl=0.4))),
        (0.75, relaxed(pelvis=(0.0, 0.01, -0.075), pelvis_rot=(0, 3, -3), spine=(5, 2, 0), fl=foot_rest('l', x=0.40, z=0.02, roll=-8), fr=foot_rest('r', x=-0.24, roll=30),
                       al=FK(flex=-20, abd=-16, elbow=22), ar=FK(flex=20, abd=-16, elbow=22))),
        (1.0, walk0),
    ]
    c = build_clip('start_f', e, keys, note='stand to walk: weight shift, first left step, ends on the walk_f cycle start pose')
    c.event('foot_lift', 4, foot='l')
    c.event('foot_plant', 13, foot='l')
    c.event('foot_lift', 15, foot='r')
    c.event('control_return', 15)
    c.contacts = [{'foot': 'l', 'plant_frame': 13, 'lift_frame': 4}, {'foot': 'r', 'plant_frame': 0, 'lift_frame': 15}]
    return c


@clip('stop_f')
def stop_f(e):
    walk0 = gait.gait_model('walk', 0.0, 150, WALK_T)(0.0)
    keys = [
        (0.0, walk0),
        (0.30, relaxed(pelvis=(0.0, 0.0, -0.11), pelvis_rot=(0, -2, 0), spine=(-3, 0, 0), fl=foot_rest('l', x=0.12, roll=0), fr=foot_rest('r', x=0.24, z=0.07, roll=-8),
                       al=FK(flex=12, abd=-22, elbow=24), ar=FK(flex=-12, abd=-22, elbow=24))),
        (0.58, relaxed(pelvis=(0.0, 0.0, -0.10), pelvis_rot=(0, -3, 0), spine=(-5, 0, 0), neck=(4, 0, 0), fl=foot_rest('l', x=-0.04, y=0.02), fr=foot_rest('r', x=0.14, y=-0.03),
                       al=FK(flex=6, abd=-26, elbow=20), ar=FK(flex=6, abd=-26, elbow=20))),
        (1.0, relaxed()),
    ]
    c = build_clip('stop_f', e, keys, note='brake into a planted stance and settle to relaxed')
    c.event('foot_plant', 9, foot='r')
    c.event('control_return', 12)
    c.contacts = [{'foot': 'l', 'plant_frame': 0, 'lift_frame': 17}, {'foot': 'r', 'plant_frame': 9, 'lift_frame': 17}]
    return c


def _turn(e, cid, sign):
    """In-place turn about the root: root yaw carries the rotation, feet are planted in world space and step around."""
    ry = lambda t: sign * 90.0 * (t * t * (3 - 2 * t))
    L0 = (-0.008, 0.10)
    R0 = (-0.008, -0.10)
    # final world feet after the root has yawed by sign*90 (rest stance rotated)
    def rot(v, a):
        c_, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
        return (c_ * v[0] - s_ * v[1], s_ * v[0] + c_ * v[1])
    L1 = rot(L0, sign * 90.0)
    R1 = rot(R0, sign * 90.0)
    lead, trail = ('l', 'r') if sign > 0 else ('r', 'l')     # the foot on the turning side steps first
    W0 = {'l': L0, 'r': R0}
    W1 = {'l': L1, 'r': R1}
    keys = []
    sched = [
        # t, root yaw factor, foot states: (side -> (world xy, world yaw, z, roll))
        (0.0, 0.0, {'l': (L0, 0.0, 0, 0), 'r': (R0, 0.0, 0, 0)}),
        (0.18, 0.10, {'l': (L0, 0.0, 0, 0), 'r': (R0, 0.0, 0, 0)}),
        (0.40, 0.45, {lead: (W0[lead], 0.0, 0.0, 18), trail: (tuple(np.array(W1[trail]) * 0.4 + np.array(W0[trail]) * 0.6), sign * 60.0, 0.09, 8)}),
        (0.62, 0.78, {lead: (W0[lead], sign * 85.0, 0.0, 0), trail: (W1[trail], sign * 90.0, 0.0, -6)}),
        (0.86, 0.96, {lead: (tuple(np.array(W1[lead]) * 0.7 + np.array(W0[lead]) * 0.3), sign * 90.0, 0.06, 6), trail: (W1[trail], sign * 90.0, 0.0, 0)}),
        (1.0, 1.0, {'l': (L1, sign * 90.0, 0, 0), 'r': (R1, sign * 90.0, 0, 0)}),
    ]
    for t, yf, feet in sched:
        ryaw = sign * 90.0 * (yf * yf * (3 - 2 * yf))
        f = {}
        for s in ('l', 'r'):
            xy, yw, z, roll = feet[s]
            f[s] = plant(s, xy[0], xy[1], yw, z=z, roll=roll, root=(0, 0), root_yaw=ryaw)
        k = relaxed(root_yaw=ryaw, pelvis=(0, 0, -0.05 - 0.02 * math.sin(math.pi * t)), pelvis_rot=(0, 0, sign * 10 * math.sin(math.pi * t)),
                    spine=(2, sign * 22 * math.sin(math.pi * min(t * 1.2, 1.0)), 0), neck=(0, sign * 26 * math.sin(math.pi * min(t * 1.3, 1.0)), 0), fl=f['l'], fr=f['r'],
                    al=FK(flex=4 - 8 * math.sin(math.pi * t), abd=-20 - 4 * math.sin(math.pi * t), elbow=20), ar=FK(flex=4 + 8 * math.sin(math.pi * t), abd=-20 - 4 * math.sin(math.pi * t), elbow=20))
        keys.append((t, k))
    c = build_clip(cid, e, keys, root='in_place', note=f'in-place 90 degree turn, root yaw rotation {sign * 90} degrees, feet planted and stepped in world space')
    c.meta['root_yaw_deg'] = sign * 90.0
    c.event('foot_lift', 6, foot=trail)
    c.event('foot_plant', 12, foot=trail)
    c.event('foot_lift', 14, foot=lead)
    c.event('foot_plant', 18, foot=lead)
    c.event('control_return', 18)
    return c


clip('turn_l90')(lambda e: _turn(e, 'turn_l90', +1))
clip('turn_r90')(lambda e: _turn(e, 'turn_r90', -1))


def _pivot(e, cid, sign):
    """Running 180 degree direction change: outside foot plants, root yaw rotates by sign*180, exit on the run cycle pose."""
    Trun = 18 / 30.0
    run0 = gait.gait_model('run', 0.0, 400, Trun)(0.0)
    run_half = gait.gait_model('run', 0.0, 400, Trun)(0.0)
    def rotv(v, a):
        c_, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
        return (c_ * v[0] - s_ * v[1], s_ * v[0] + c_ * v[1])
    out_side, in_side = ('r', 'l') if sign > 0 else ('l', 'r')
    sgn = 1.0 if sign > 0 else -1.0
    keys = [(0.0, run0)]
    stages = [(0.28, 0.14, (0.42, -sgn * 0.20), (0.05, sgn * 0.06)), (0.55, 0.55, (0.42, -sgn * 0.20), (-0.02, sgn * 0.26)), (0.80, 0.90, (0.38, -sgn * 0.14), (-0.30, sgn * 0.22))]
    for t, yf, wo, wi in stages:
        ryaw = sign * 180.0 * (yf * yf * (3 - 2 * yf))
        yaw_out = sign * 30.0 + ryaw * 0.4
        fo = plant(out_side, wo[0], wo[1], yaw_out, z=0.0, roll=0 if t < 0.7 else 12, root=(0, 0), root_yaw=ryaw)
        fi = plant(in_side, wi[0], wi[1], sign * 120.0 * yf, z=0.10 if t < 0.7 else 0.03, roll=0, root=(0, 0), root_yaw=ryaw)
        lean = 14 * math.sin(math.pi * min(t / 0.8, 1.0))
        k = relaxed(root_yaw=ryaw, pelvis=(0.0, -sgn * 0.03, -0.17), pelvis_rot=(-sgn * 6, 8, sign * 15), spine=(12, sign * 25 * math.sin(math.pi * t), -sgn * lean * 0.5), neck=(-4, sign * 20, 0),
                    fl=fo if out_side == 'l' else fi, fr=fo if out_side == 'r' else fi,
                    al=FK(flex=30, abd=-30 if sign > 0 else 0, elbow=70), ar=FK(flex=30, abd=0 if sign > 0 else -30, elbow=70), hl=dict(curl=0.6), hr=dict(curl=0.6))
        keys.append((t, k))
    end = gait.gait_model('run', 0.0, 400, Trun)(0.0)
    end = Pose(end)
    end[('ctl_root', 'rot', 2)] = sign * 180.0
    keys.append((1.0, end))
    c = build_clip(cid, e, keys, root='in_place', note=f'running pivot, root yaw {sign * 180} degrees, exits on the run_f cycle start pose')
    c.meta['root_yaw_deg'] = sign * 180.0
    c.event('foot_plant', 6, foot=out_side)
    c.event('foot_lift', 13, foot=out_side)
    c.event('foot_plant', 15, foot=in_side)
    c.event('control_return', 19)
    return c


clip('pivot_l180')(lambda e: _pivot(e, 'pivot_l180', +1))
clip('pivot_r180')(lambda e: _pivot(e, 'pivot_r180', -1))


# ----------------------------------------------------------------------------- jump, fall, land

def air_pose(**o):
    k = relaxed(pelvis=(0.0, 0.0, -0.03), pelvis_rot=(0, 2, 0), spine=(4, 0, 0), neck=(-4, 0, 0),
                fl=foot_rest('l', x=0.10, z=0.18, roll=-8), fr=foot_rest('r', x=0.02, z=0.24, roll=-14),
                al=FK(flex=52, abd=26, elbow=28), ar=FK(flex=52, abd=26, elbow=28), hl=dict(curl=0.3, spread=0.5), hr=dict(curl=0.3, spread=0.5), reach=False)
    k.update(o)
    return k


@clip('jump_start')
def jump_start(e):
    keys = [
        (0.0, relaxed()),
        (0.22, relaxed(pelvis=(0.0, 0.0, -0.27), pelvis_rot=(0, 10, 0), spine=(24, 0, 0), neck=(-14, 0, 0), fl=foot_rest('l', x=0.02), fr=foot_rest('r', x=-0.02),
                       al=FK(flex=-30, abd=-10, elbow=26), ar=FK(flex=-30, abd=-10, elbow=26), hl=dict(curl=0.5), hr=dict(curl=0.5))),
        (0.64, relaxed(pelvis=(0.0, 0.0, 0.0), pelvis_rot=(0, -3, 0), spine=(-6, 0, 0), neck=(-2, 0, 0), fl=foot_rest('l', roll=40), fr=foot_rest('r', roll=40),
                       al=FKS(flex=98, abd=18, elbow=20), ar=FKS(flex=98, abd=18, elbow=20), hl=dict(curl=0.2), hr=dict(curl=0.2), reach=False)),
        (1.0, air_pose()),
    ]
    c = build_clip('jump_start', e, keys, note='crouch, explosive extension, take-off into the airborne posture')
    c.event('jump_takeoff', 0.64)
    c.contacts = [{'foot': 'l', 'plant_frame': 0, 'lift_frame': 9}, {'foot': 'r', 'plant_frame': 0, 'lift_frame': 9}]
    return c


@clip('jump_air')
def jump_air(e):
    keys = []
    for i in range(7):
        t = i / 6
        s = math.sin(TAU * t)
        keys.append((t, air_pose(pelvis=(0, 0, -0.03 + 0.005 * s), fl=foot_rest('l', x=0.10 + 0.02 * s, z=0.18 + 0.02 * s, roll=-8), fr=foot_rest('r', x=0.02 - 0.02 * s, z=0.24 - 0.02 * s, roll=-14),
                                 al=FK(flex=52 + 4 * s, abd=26 + 3 * s, elbow=28), ar=FK(flex=52 - 4 * s, abd=26 - 3 * s, elbow=28), neck=(-4 + 1 * s, 0, 0))))
    return build_clip('jump_air', e, keys, note='airborne posture for a controllable jump')


@clip('jump_land')
def jump_land(e):
    keys = [
        (0.0, air_pose(fl=foot_rest('l', x=0.08, z=0.12, roll=-6), fr=foot_rest('r', x=0.02, z=0.14, roll=-6))),
        (0.20, relaxed(pelvis=(0.0, 0.0, -0.10), pelvis_rot=(0, 3, 0), spine=(8, 0, 0), fl=foot_rest('l', x=0.06, roll=-6), fr=foot_rest('r', x=0.00, roll=-6),
                       al=FK(flex=52, abd=20, elbow=26), ar=FK(flex=52, abd=20, elbow=26))),
        (0.42, relaxed(pelvis=(0.0, 0.0, -0.30), pelvis_rot=(0, 8, 0), spine=(24, 0, 0), neck=(-14, 0, 0), fl=foot_rest('l', x=0.06), fr=foot_rest('r', x=0.00),
                       al=FK(flex=38, abd=6, elbow=44), ar=FK(flex=38, abd=6, elbow=44), hl=dict(curl=0.5), hr=dict(curl=0.5))),
        (0.72, relaxed(pelvis=(0.0, 0.0, -0.13), spine=(10, 0, 0), neck=(-6, 0, 0), fl=foot_rest('l', x=0.03), fr=foot_rest('r', x=0.0), al=FK(flex=14, abd=-14, elbow=24), ar=FK(flex=14, abd=-14, elbow=24))),
        (1.0, relaxed()),
    ]
    c = build_clip('jump_land', e, keys, note='soft landing with compression and recovery')
    c.event('land_contact', 0.2)
    c.event('control_return', 0.75)
    c.contacts = [{'foot': 'l', 'plant_frame': 3, 'lift_frame': 15}, {'foot': 'r', 'plant_frame': 3, 'lift_frame': 15}]
    return c


@clip('fall')
def fall(e):
    keys = []
    for i in range(7):
        t = i / 6
        s = math.sin(TAU * t)
        c_ = math.cos(TAU * t)
        keys.append((t, air_pose(pelvis=(0, 0, -0.0), pelvis_rot=(2 * s, -4, 3 * c_), spine=(-10, 3 * s, 2 * c_), neck=(16, 4 * s, 0),
                                 fl=foot_rest('l', x=-0.04 + 0.02 * s, z=0.12 + 0.02 * c_, roll=-45), fr=foot_rest('r', x=-0.08 - 0.02 * s, z=0.16 - 0.02 * c_, roll=-45),
                                 al=FKS(flex=150 + 8 * s, abd=34 + 6 * c_, elbow=20 + 6 * s), ar=FKS(flex=150 - 8 * s, abd=34 - 6 * c_, elbow=20 - 6 * s), hl=dict(curl=0.15, spread=0.9), hr=dict(curl=0.15, spread=0.9))))
    return build_clip('fall', e, keys, note='long-fall posture: arms raised, back arched, legs trailing (distinct from the jump apex)')


@clip('land_heavy')
def land_heavy(e):
    fall0 = air_pose(pelvis=(0, 0, 0.0), spine=(-10, 0, 0), neck=(16, 0, 0), fl=foot_rest('l', x=-0.04, z=0.10, roll=-40), fr=foot_rest('r', x=-0.08, z=0.14, roll=-40),
                     al=FKS(flex=150, abd=34, elbow=20), ar=FKS(flex=150, abd=34, elbow=20))
    low = relaxed(pelvis=(0.03, -0.02, -0.46), pelvis_rot=(0, 20, 0), spine=(34, 4, 0), neck=(-24, 0, 0), fl=foot_rest('l', x=0.20, y=0.06, yaw=-10), fr=foot_rest('r', x=-0.06, y=-0.08),
                  al=FK(flex=-30, abd=10, elbow=40), ar=('ik', dict(target=(0.28, -0.22, 0.03), dir=(0.75, 0.0, -0.55), palm=(0, 0, -1), elbow_hint=(-0.05, -0.36, 0.42))),
                  hl=dict(curl=0.3), hr=dict(curl=0.05, spread=0.6))
    # the arms lag the body: still up and out at the impact (f4), then come down over the next 7 frames
    mid = {**low, 'al': FKS(flex=112, abd=38, elbow=30), 'ar': FKS(flex=112, abd=38, elbow=30), 'hl': dict(curl=0.15, spread=0.8), 'hr': dict(curl=0.15, spread=0.8)}
    catch = {**low, 'al': FKS(flex=60, abd=36, elbow=40), 'ar': FKS(flex=60, abd=36, elbow=40), 'hr': dict(curl=0.3, spread=0.4)}
    keys = [
        (0.0, fall0),
        (0.20, relaxed(**mid)),
        (0.32, relaxed(**catch)),
        (0.46, low),
        (0.60, relaxed(**{**low, 'pelvis': (0.03, -0.02, -0.44), 'spine': (32, 4, 0)})),
        (0.82, relaxed(pelvis=(0.0, 0.0, -0.22), spine=(16, 0, 0), neck=(-10, 0, 0), fl=foot_rest('l', x=0.10), fr=foot_rest('r', x=-0.02), al=FK(flex=20, abd=-10, elbow=40), ar=FK(flex=30, abd=-12, elbow=50))),
        (1.0, relaxed()),
    ]
    c = build_clip('land_heavy', e, keys, note='hard landing: deep crouch with a supporting hand, slow recovery')
    c.event('land_impact_heavy', 0.16)
    c.event('control_return', 0.85)
    return c


# ----------------------------------------------------------------------------- dash and blink

def _dash(e, cid, direction):
    """2 m ground dash. Feet are planted in WORLD space along the travel axis; the root translation carries the motion."""
    D = 2.0
    ease_keys = [(0.0, 0.0), (0.12, 0.04), (0.30, 0.30), (0.55, 0.78), (0.80, 0.98), (1.0, 1.0)]
    rx = lambda t: np.interp(t, [a for a, _ in ease_keys], [b for _, b in ease_keys]) * D
    d = {'f': (1.0, 0.0), 'b': (-1.0, 0.0), 'l': (0.0, 1.0), 'r': (0.0, -1.0)}[direction]
    n = (-d[1], d[0])                                  # left of the travel direction
    W0 = {'l': (-0.008, 0.10), 'r': (-0.008, -0.10)}
    along0 = {s: W0[s][0] * d[0] + W0[s][1] * d[1] for s in W0}
    lead = 'l' if (along0['l'] > along0['r'] or (abs(along0['l'] - along0['r']) < 1e-6 and direction == 'f')) else 'r'
    trail = 'r' if lead == 'l' else 'l'
    ts = [0.0, 0.12, 0.30, 0.50, 0.68, 0.85, 1.0]
    sched = {
        lead: dict(along=[0, 0, 0.30, 1.25, 1.25, 1.40, 1.45], z=[0, 0, 0.13, 0, 0, 0.05, 0], roll=[0, 0, 20, -8, 30, 0, 0], side=[0, 0, 0.02, 0.0, 0.0, 0.0, 0.0]),
        trail: dict(along=[0, -0.06, 0.70, 0.70, 1.60, 1.98, 1.98], z=[0, 0, 0.05, 0, 0.10, 0, 0], roll=[0, 10, 6, -6, 20, -10, 0], side=[0, 0, 0.0, 0.0, 0.02, 0.0, 0.0]),
    }
    keys = []
    for i, t in enumerate(ts):
        r = rx(t)
        root = (d[0] * r, d[1] * r)
        ph = math.sin(math.pi * min(t / 0.85, 1.0))
        f = {}
        for s in ('l', 'r'):
            sc = sched[s]
            wx = W0[s][0] + d[0] * sc['along'][i] + n[0] * sc['side'][i]
            wy = W0[s][1] + d[1] * sc['along'][i] + n[1] * sc['side'][i]
            f[s] = plant(s, wx, wy, 0.0, z=sc['z'][i], roll=sc['roll'][i], root=root)
        if direction == 'f':
            spine, prot, neck = (24 * ph, 0, 0), (0, 10 * ph, 0), (-10 * ph, 0, 0)
        elif direction == 'b':
            spine, prot, neck = (-14 * ph, 0, 0), (0, -8 * ph, 0), (6 * ph, 0, 0)
        else:
            sg = 1.0 if direction == 'l' else -1.0
            spine, prot, neck = (6 * ph, 0, -sg * 16 * ph), (-sg * 12 * ph, 4 * ph, 0), (-4 * ph, 0, 0)
        arm_fl = -30 * ph if direction == 'f' else 40 * ph
        k = relaxed(root=(root[0], root[1], 0.0), pelvis=(0.0, 0.0, -0.12 - 0.10 * ph), pelvis_rot=prot, spine=spine, neck=neck, fl=f['l'], fr=f['r'],
                    al=FK(flex=arm_fl, abd=-14 + 24 * ph, elbow=50), ar=FK(flex=arm_fl, abd=-14 + 24 * ph, elbow=50), hl=dict(curl=0.7), hr=dict(curl=0.7))
        keys.append((t, k))
    c = build_clip(cid, e, keys, root='root_motion', note=f'ground dash {direction}, 2 m nominal; root translation carries the motion, feet planted in world space')
    c.event('dash_begin', 0.12)
    c.event('dash_end', 0.85)
    c.event('control_return', 0.95)
    return c


for d in ('f', 'b', 'l', 'r'):
    clip(f'dash_{d}')(lambda e, d=d: _dash(e, f'dash_{d}', d))


@clip('blink_out')
def blink_out(e):
    keys = [
        (0.0, combat()),
        (0.38, relaxed(pelvis=(0, 0, -0.24), pelvis_rot=(0, 8, 0), spine=(16, -22, 0), neck=(-14, 12, 0), fl=foot_rest('l', x=0.10, y=0.04), fr=foot_rest('r', x=-0.08, y=-0.04),
                       al=FK(flex=72, abd=-6, elbow=112), ar=FK(flex=72, abd=-6, elbow=116), hl=dict(curl=1.0), hr=dict(curl=1.0))),
        (0.72, relaxed(pelvis=(0, 0, 0.0), pelvis_rot=(0, -6, 0), spine=(-10, 8, 0), neck=(8, 0, 0), fl=foot_rest('l', roll=44, z=0.03), fr=foot_rest('r', roll=44, z=0.02),
                       al=FK(flex=40, abd=58, elbow=14), ar=FK(flex=40, abd=58, elbow=14), hl=dict(curl=0.0, spread=1.0), hr=dict(curl=0.0, spread=1.0), reach=False)),
        (1.0, air_pose(spine=(-14, 0, 0), al=FKS(flex=130, abd=40, elbow=16), ar=FKS(flex=130, abd=40, elbow=16))),
    ]
    c = build_clip('blink_out', e, keys, note='coil, burst upward with arms flung wide; the actor teleport is a runtime event')
    c.event('blink_vanish', 0.75)
    return c


@clip('blink_in')
def blink_in(e):
    keys = [
        (0.0, air_pose(spine=(-8, 0, 0), fl=foot_rest('l', x=0.10, z=0.22), fr=foot_rest('r', x=0.0, z=0.26), al=FKS(flex=100, abd=44, elbow=18), ar=FKS(flex=100, abd=44, elbow=18))),
        (0.40, relaxed(pelvis=(0.03, -0.02, -0.34), pelvis_rot=(0, 16, 0), spine=(28, 4, 0), neck=(-18, 0, 0), fl=foot_rest('l', x=0.20, y=0.05), fr=foot_rest('r', x=-0.05, y=-0.09),
                       al=FK(flex=-20, abd=16, elbow=40), ar=('ik', dict(target=(0.26, -0.20, 0.03), dir=(0.75, 0, -0.55), palm=(0, 0, -1), elbow_hint=(-0.05, -0.34, 0.45))), hr=dict(curl=0.05, spread=0.6))),
        (0.70, relaxed(pelvis=(0.0, 0.0, -0.20), pelvis_rot=(0, 8, -6), spine=(14, -10, 0), neck=(-8, 6, 0), fl=foot_rest('l', x=0.16, y=0.03, yaw=-10), fr=foot_rest('r', x=-0.12, y=-0.06, yaw=-20),
                       al=FK(flex=40, abd=6, elbow=70), ar=FK(flex=34, abd=-12, elbow=100))),
        (1.0, combat()),
    ]
    c = build_clip('blink_in', e, keys, note='reappear mid-air, plant with a supporting hand and settle into the ready stance')
    c.event('blink_appear', 0.0)
    c.event('land_contact', 0.40)
    c.event('control_return', 0.9)
    return c

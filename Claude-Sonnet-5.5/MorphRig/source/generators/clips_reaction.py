"""Hand-authored clips, part 3: hits, disables, knockdown/getup, sleep, death/respawn, greet/victory/defeat.
Lying poses rotate the world-aligned pelvis (pitch +90 = face down, -90 = face up) with feet and hands planted by IK."""
import math
import numpy as np
from mathutils import Vector, Matrix
import anim_lib as AL
from anim_lib import Pose
import face_lib as FL
import pose_lib as PL
from keypose import resolve, build_clip, plant, foot_rest, fk_like
from anim_registry import clip
from clips_basic import relaxed, combat, add_blinks, add_gaze, FK, FKS, TAU

# ----------------------------------------------------------------------------- hits (additive, first frame = reference)


def _hit(e, cid, kind):
    base = relaxed(pelvis=(0.0, 0.0, -0.022))
    def key(a, **o):
        k = dict(base)
        k.update(o)
        return k
    peaks = {
        'hit_f': dict(spine=(-11, 0, 0), neck=(-16, 0, 0), al=FK(flex=-10, abd=-14, elbow=24), ar=FK(flex=-10, abd=-14, elbow=24)),
        'hit_b': dict(spine=(13, 0, 0), neck=(12, 0, 0), al=FK(flex=22, abd=-14, elbow=10), ar=FK(flex=22, abd=-14, elbow=10)),
        'hit_l': dict(spine=(-2, 9, -9), neck=(-4, 6, -8), al=FK(flex=14, abd=-4, elbow=30), ar=FK(flex=-6, abd=-30, elbow=14)),
        'hit_r': dict(spine=(-2, -9, 9), neck=(-4, -6, 8), al=FK(flex=-6, abd=-30, elbow=14), ar=FK(flex=14, abd=-4, elbow=30)),
    }[cid]
    keys = [(0.0, key(0)), (0.22, key(1, **peaks)), (0.55, key(2, **{k: (v if not isinstance(v, tuple) or k in ('al', 'ar') else tuple(x * 0.35 for x in v)) for k, v in peaks.items()})), (1.0, key(3))]
    face = FL.expression('pain', 0.5)
    c = build_clip(cid, e, keys, note=f'additive hit reaction ({kind}); frame 0 is the neutral reference pose')
    c.key(0, FL.expression('neutral'))
    c.key(int(round(0.22 * e['frames'])), face)
    c.key(e['frames'], FL.expression('neutral'))
    c.event('hit_peak', 2)
    return c


for _cid, _k in (('hit_f', 'from the front'), ('hit_b', 'from the back'), ('hit_l', 'from the left'), ('hit_r', 'from the right')):
    clip(_cid)(lambda e, cid=_cid, k=_k: _hit(e, cid, k))


# ----------------------------------------------------------------------------- disables

def stun_pose(ph=0.0, amp=1.0, **o):
    s, c_ = math.sin(ph), math.cos(ph)
    k = relaxed(pelvis=(0.02 * s * amp, 0.03 * c_ * amp, -0.10), pelvis_rot=(4 * c_ * amp, 4, 6 * s * amp), spine=(10 + 3 * s * amp, 8 * c_ * amp, 6 * s * amp), neck=(8 + 4 * c_ * amp, 14 * s * amp, 8 * c_ * amp),
                fl=foot_rest('l', x=0.10, y=0.05, yaw=-10), fr=foot_rest('r', x=-0.12, y=-0.10, yaw=-24),
                al=FK(flex=8 + 4 * s * amp, abd=-16, elbow=30), ar=FK(flex=6 - 4 * s * amp, abd=-22, elbow=24), hl=dict(curl=0.2), hr=dict(curl=0.2))
    k['face'] = FL.expression('pain', 0.35)
    k.update(o)
    return k


@clip('stun_start')
def stun_start(e):
    keys = [
        (0.0, combat()),
        (0.22, relaxed(pelvis=(-0.08, 0.0, -0.16), pelvis_rot=(0, -6, 10), spine=(-16, 14, 4), neck=(-22, 18, 0), fl=foot_rest('l', x=0.12, y=0.05), fr=foot_rest('r', x=-0.30, y=-0.10),
                       al=FK(flex=60, abd=40, elbow=50), ar=FK(flex=50, abd=44, elbow=40), hl=dict(curl=-0.2, spread=1.0), hr=dict(curl=-0.2, spread=1.0), face=FL.expression('pain', 0.8))),
        (0.62, stun_pose(0.0, 1.4, pelvis=(0.0, 0.0, -0.18))),
        (1.0, stun_pose(0.0, 1.0)),
    ]
    c = build_clip('stun_start', e, keys, note='control lost: head snaps back, knees buckle, arms flail, settling into the dazed stance')
    c.event('stun_begin', 0.05)
    return c


@clip('stun_loop')
def stun_loop(e):
    keys = [(i / 12, stun_pose(TAU * i / 12, 1.0)) for i in range(13)]
    c = build_clip('stun_loop', e, keys, note='dazed sway: slow pelvis circle, head loll, arms dangling, breathing')
    add_blinks(c, [int(e['frames'] * 0.3), int(e['frames'] * 0.7)], dur=8)
    return c


@clip('stun_end')
def stun_end(e):
    keys = [(0.0, stun_pose(0.0, 1.0)), (0.35, relaxed(pelvis=(0.0, 0.0, -0.14), spine=(14, -6, 0), neck=(10, -14, 0), fl=foot_rest('l', x=0.08, y=0.04), fr=foot_rest('r', x=-0.10, y=-0.08),
                                                    al=FK(flex=14, abd=-16, elbow=36), ar=FK(flex=14, abd=-16, elbow=36))),
            (0.65, relaxed(pelvis=(0.0, 0.0, -0.11), spine=(10, 6, 0), neck=(-4, 16, 0), fl=foot_rest('l', x=0.14, y=0.04, yaw=-8), fr=foot_rest('r', x=-0.12, y=-0.06, yaw=-14), al=FK(flex=40, abd=6, elbow=70), ar=FK(flex=34, abd=-12, elbow=98))),
            (1.0, combat())]
    c = build_clip('stun_end', e, keys, note='regain control: a head shake, straighten and plant the feet without sliding')
    c.event('control_return', 0.9)
    return c


@clip('knockback')
def knockback(e):
    keys = [
        (0.0, combat()),
        (0.20, relaxed(pelvis=(-0.14, 0.0, -0.10), pelvis_rot=(0, -10, 6), spine=(-22, 6, 0), neck=(-16, 6, 0), fl=foot_rest('l', x=0.24, y=0.05, z=0.01, roll=-16), fr=foot_rest('r', x=0.14, y=-0.08, z=0.01, roll=-18),
                       al=FK(flex=76, abd=36, elbow=34), ar=FK(flex=66, abd=40, elbow=44), hl=dict(curl=-0.1, spread=1.0), hr=dict(curl=-0.1, spread=1.0), face=FL.expression('pain', 0.7))),
        (0.50, relaxed(pelvis=(-0.16, 0.0, -0.14), pelvis_rot=(0, -8, 4), spine=(-14, 4, 0), neck=(-8, 4, 0), fl=foot_rest('l', x=0.20, y=0.05, z=0.01, roll=-12), fr=foot_rest('r', x=0.10, y=-0.08, z=0.01, roll=-14),
                       al=FK(flex=50, abd=30, elbow=44), ar=FK(flex=44, abd=34, elbow=52), face=FL.expression('pain', 0.5))),
        (0.72, relaxed(pelvis=(0.0, 0.0, -0.20), pelvis_rot=(0, 6, -4), spine=(18, -6, 0), neck=(6, -6, 0), fl=foot_rest('l', x=0.18, y=0.05), fr=foot_rest('r', x=-0.06, y=-0.09, z=0.05),
                       al=FK(flex=24, abd=10, elbow=60), ar=FK(flex=24, abd=-8, elbow=70))),
        (1.0, combat()),
    ]
    c = build_clip('knockback', e, keys, note='reaction to backward forced travel: feet skid while the body leans back, then a recovery step (travel is host controlled)')
    c.event('hit_peak', 0.2)
    c.event('control_return', 0.9)
    return c


@clip('knockup_start')
def knockup_start(e):
    air = dict(pelvis=(-0.02, 0.0, -0.02), pelvis_rot=(0, -12, 0), spine=(-22, 0, 0), neck=(-14, 0, 0), fl=foot_rest('l', x=-0.10, z=0.16, roll=-30), fr=foot_rest('r', x=-0.16, z=0.20, roll=-36),
               al=FKS(flex=140, abd=38, elbow=26), ar=FKS(flex=136, abd=40, elbow=30), hl=dict(curl=-0.1, spread=1.0), hr=dict(curl=-0.1, spread=1.0), reach=False)
    keys = [(0.0, combat()), (0.30, relaxed(pelvis=(-0.04, 0.0, -0.26), pelvis_rot=(0, 10, 0), spine=(24, 0, 0), neck=(-8, 0, 0), al=FK(flex=-30, abd=10, elbow=60), ar=FK(flex=-30, abd=10, elbow=60))),
            (0.72, relaxed(**{**air, 'face': FL.expression('surprise', 0.7)})), (1.0, relaxed(**{**air, 'face': FL.expression('pain', 0.6)}))]
    c = build_clip('knockup_start', e, keys, note='forced launch: a buckle then the body is thrown up and back, arms flung, legs trailing')
    c.event('knockup_launch', 0.3)
    return c


@clip('knockup_air')
def knockup_air(e):
    keys = []
    for i in range(7):
        t = i / 6
        s, c_ = math.sin(TAU * t), math.cos(TAU * t)
        k = relaxed(pelvis=(0.0, 0.0, -0.02), pelvis_rot=(6 * s, -10 + 4 * c_, 8 * c_), spine=(-18 + 3 * s, 4 * c_, 3 * s), neck=(-10 + 4 * s, 6 * c_, 0),
                    fl=foot_rest('l', x=-0.10 + 0.03 * s, z=0.18 + 0.03 * c_, roll=-30), fr=foot_rest('r', x=-0.14 - 0.03 * s, z=0.22 - 0.03 * c_, roll=-34),
                    al=FKS(flex=120 + 8 * s, abd=44 + 6 * c_, elbow=30 + 6 * s), ar=FKS(flex=116 - 8 * s, abd=46 - 6 * c_, elbow=34 - 6 * s), hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8), reach=False)
        k['face'] = FL.expression('pain', 0.5)
        keys.append((t, k))
    return build_clip('knockup_air', e, keys, note='helpless airborne pose: limp limbs and a slow rocking tumble')


# ----------------------------------------------------------------------------- floor poses

def prone_front(ph=0.0, amp=1.0, **o):
    br = math.sin(ph) * amp
    k = relaxed(pelvis=(0.86, 0.0, -0.80), pelvis_rot=(0, 90, 0), spine=(-10 + 1.2 * br, 2, 0), neck=(-8, -70, 0),
                fl=foot_rest('l', x=0.02, y=0.02, z=0.19, pitch=55), fr=foot_rest('r', x=0.04, y=-0.04, z=0.25, pitch=48),
                al=('ik', dict(target=(1.60, 0.34, 0.06 + 0.004 * br), dir=(1.0, 0.0, -0.1), palm=(0, 0, -1), elbow_hint=(1.34, 0.80, 0.14))),
                ar=('ik', dict(target=(1.56, -0.32, 0.06), dir=(1.0, 0.0, -0.1), palm=(0, 0, -1), elbow_hint=(1.30, -0.80, 0.14))), hl=dict(curl=0.35), hr=dict(curl=0.3), reach=False)
    k['face'] = FL.expression('neutral')
    k.update(o)
    return k


def prone_back(ph=0.0, amp=1.0, **o):
    br = math.sin(ph) * amp
    k = relaxed(pelvis=(-0.86, 0.0, -0.792), pelvis_rot=(0, -90, 0), spine=(8 + 1.4 * br, -2, 0), neck=(6, 20, 0), fl=foot_rest('l', x=0.0, y=0.02, z=0.075, pitch=-55), fr=foot_rest('r', x=0.0, y=-0.05, z=0.095, pitch=-60),
                al=('ik', dict(target=(-0.80, 0.42, 0.06), dir=(1.0, 0.25, 0.0), palm=(0, 0, -1), elbow_hint=(-1.06, 0.58, 0.06))),
                ar=('ik', dict(target=(-0.80, -0.42, 0.06), dir=(1.0, -0.25, 0.0), palm=(0, 0, -1), elbow_hint=(-1.06, -0.58, 0.06))), hl=dict(curl=0.3), hr=dict(curl=0.4), reach=False)
    k.update(o)
    return k


@clip('prone_front')
def prone_front_clip(e):
    keys = [(i / 8, prone_front(TAU * i / 8, 1.0)) for i in range(9)]
    c = build_clip('prone_front', e, keys, note='face-down floor pose with restrained breathing')
    add_blinks(c, [int(e['frames'] * 0.5)])
    return c


@clip('prone_back')
def prone_back_clip(e):
    keys = [(i / 8, prone_back(TAU * i / 8, 1.0)) for i in range(9)]
    c = build_clip('prone_back', e, keys, note='face-up floor pose with restrained breathing')
    add_blinks(c, [int(e['frames'] * 0.4)])
    return c


@clip('knockdown_front')
def knockdown_front(e):
    keys = [
        (0.0, combat()),
        (0.14, relaxed(pelvis=(-0.06, 0.0, -0.10), pelvis_rot=(0, -6, 8), spine=(-16, 6, 0), neck=(-14, 4, 0), al=FK(flex=70, abd=30, elbow=40), ar=FK(flex=64, abd=34, elbow=44), face=FL.expression('pain', 0.7))),
        (0.32, relaxed(pelvis=(0.16, 0.0, -0.24), pelvis_rot=(0, 26, 0), spine=(24, 0, 0), neck=(-16, 0, 0), fl=foot_rest('l', x=0.02), fr=foot_rest('r', x=-0.06, z=0.03),
                       al=FK(flex=90, abd=20, elbow=20), ar=FK(flex=96, abd=20, elbow=16), hl=dict(curl=-0.1, spread=1.0), hr=dict(curl=-0.1, spread=1.0), reach=False)),
        (0.52, relaxed(pelvis=(0.52, 0.0, -0.52), pelvis_rot=(0, 58, 0), spine=(8, 0, 0), neck=(-24, 0, 0), fl=foot_rest('l', x=0.0, y=0.03, z=0.15, pitch=40), fr=foot_rest('r', x=0.0, y=-0.04, z=0.17, pitch=30),
                       al=('ik', dict(target=(0.90, 0.26, 0.34), dir=(0.9, 0.1, -0.4), palm=(0, 0, -1), elbow_hint=(0.42, 0.55, 0.40))), ar=('ik', dict(target=(0.80, -0.22, 0.10), dir=(0.9, 0.0, -0.4), palm=(0, 0, -1), elbow_hint=(0.4, -0.5, 0.35))), hl=dict(curl=0.0, spread=0.9), hr=dict(curl=0.0, spread=0.9), reach=False)),
        (0.72, prone_front(0, 0, pelvis=(0.88, 0.0, -0.805), spine=(-16, 0, 0), neck=(-22, -30, 0),
                           al=('ik', dict(target=(1.56, 0.48, 0.13), dir=(1.0, 0.1, -0.3), palm=(0, 0, -1), elbow_hint=(1.22, 0.86, 0.20))), ar=('ik', dict(target=(1.52, -0.46, 0.13), dir=(1.0, -0.1, -0.3), palm=(0, 0, -1), elbow_hint=(1.18, -0.84, 0.20))),
                           face=FL.expression('pain', 0.6))),
        (0.86, prone_front(0, 0, pelvis=(0.86, 0.0, -0.81), spine=(-6, 1, 0), neck=(-8, -60, 0),
                           al=('ik', dict(target=(1.42, 0.42, 0.09), dir=(1.0, 0.1, -0.2), palm=(0, 0, -1), elbow_hint=(1.16, 0.84, 0.14))), ar=('ik', dict(target=(1.36, -0.38, 0.09), dir=(1.0, -0.1, -0.2), palm=(0, 0, -1), elbow_hint=(1.12, -0.82, 0.14))))),
        (1.0, prone_front(0, 0)),
    ]
    c = build_clip('knockdown_front', e, keys, note='stumble forward, catch with a hand, fall face-down and settle into prone_front (ends on its first pose)')
    c.event('hit_peak', 0.1)
    c.event('ground_impact', 0.68)
    c.event('control_return', 0.98)
    return c


@clip('knockdown_back')
def knockdown_back(e):
    keys = [
        (0.0, combat()),
        (0.14, relaxed(pelvis=(-0.10, 0.0, -0.12), pelvis_rot=(0, -8, 8), spine=(-22, 6, 0), neck=(-16, 4, 0), fl=foot_rest('l', x=0.20, z=0.02), al=FK(flex=76, abd=34, elbow=40), ar=FK(flex=70, abd=36, elbow=44), face=FL.expression('pain', 0.7))),
        (0.34, relaxed(pelvis=(-0.28, 0.0, -0.34), pelvis_rot=(0, -30, 0), spine=(-14, 0, 0), neck=(-6, 0, 0), fl=foot_rest('l', x=0.34, z=0.10, roll=-20), fr=foot_rest('r', x=0.20, z=0.04, roll=-14),
                       al=FKS(flex=130, abd=32, elbow=24), ar=FKS(flex=126, abd=34, elbow=28), hl=dict(curl=-0.1, spread=1.0), hr=dict(curl=-0.1, spread=1.0), reach=False)),
        (0.56, relaxed(pelvis=(-0.60, 0.0, -0.66), pelvis_rot=(0, -62, 0), spine=(4, 0, 0), neck=(14, 0, 0), fl=foot_rest('l', x=0.08, y=0.03, z=0.08, pitch=-20), fr=foot_rest('r', x=0.10, y=-0.05, z=0.03, pitch=-30),
                       al=FKS(flex=110, abd=44, elbow=30), ar=FKS(flex=100, abd=48, elbow=36), reach=False)),
        (0.74, prone_back(0, 0, pelvis=(-0.88, 0.0, -0.805), neck=(20, 24, 0), spine=(14, 0, 0), al=FK(flex=60, abd=52, elbow=24), ar=FK(flex=40, abd=60, elbow=30), face=FL.expression('pain', 0.7))),
        (0.88, prone_back(0, 0, pelvis=(-0.87, 0.0, -0.81), neck=(10, 22, 0), spine=(10, -1, 0))),
        (1.0, prone_back(0, 0)),
    ]
    c = build_clip('knockdown_back', e, keys, note='recoil, stumble backward, fall onto the back with the arms flung and settle into prone_back')
    c.event('hit_peak', 0.1)
    c.event('ground_impact', 0.66)
    c.event('control_return', 0.98)
    return c


@clip('getup_front')
def getup_front(e):
    hands = ('ik', dict(target=(0.60, -0.24, 0.05), dir=(0.9, 0.0, -0.3), palm=(0, 0, -1), elbow_hint=(0.3, -0.5, 0.3)))
    handl = ('ik', dict(target=(0.60, 0.24, 0.05), dir=(0.9, 0.0, -0.3), palm=(0, 0, -1), elbow_hint=(0.3, 0.5, 0.3)))
    keys = [
        (0.0, prone_front(0, 0)),
        (0.16, prone_front(0, 0, pelvis=(0.85, 0.0, -0.81), spine=(-14, 0, 0), neck=(-16, -20, 0), al=handl, ar=hands, hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8))),
        (0.34, relaxed(pelvis=(0.60, 0.0, -0.66), pelvis_rot=(0, 72, 0), spine=(-16, 0, 0), neck=(-20, 0, 0), fl=foot_rest('l', x=0.0, y=0.05, z=0.27, pitch=60, roll=20), fr=foot_rest('r', x=0.0, y=-0.05, z=0.27, pitch=56, roll=20),
                       al=handl, ar=hands, hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8), reach=False)),
        (0.52, relaxed(pelvis=(0.30, 0.0, -0.50), pelvis_rot=(0, 46, 0), spine=(4, 0, 0), neck=(-24, 0, 0), fl=foot_rest('l', x=0.12, y=0.09, z=0.03, roll=36), fr=foot_rest('r', x=0.10, y=-0.11, z=0.03, roll=36),
                       al=handl, ar=hands, hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8))),
        (0.70, relaxed(pelvis=(0.10, 0.0, -0.30), pelvis_rot=(0, 22, -6), spine=(20, -6, 0), neck=(-14, 0, 0), fl=foot_rest('l', x=0.16, y=0.06, yaw=-8), fr=foot_rest('r', x=-0.04, y=-0.09, yaw=-16),
                       al=FK(flex=34, abd=6, elbow=70), ar=('ik', dict(target=(0.50, -0.24, 0.20), dir=(0.9, 0, -0.4), palm=(0, 0, -1), elbow_hint=(0.2, -0.45, 0.4))))),
        (0.86, combat(pelvis=(0.0, 0.0, -0.14), spine=(14, -10, 0))),
        (1.0, combat()),
    ]
    c = build_clip('getup_front', e, keys, note='from face-down: hands plant beside the chest, push up, feet gather under the hips, rise through a crouch to the ready stance')
    c.event('ground_impact', 0.16)
    c.event('getup_stand', 0.86)
    c.event('control_return', 0.94)
    return c


@clip('getup_back')
def getup_back(e):
    keys = [
        (0.0, prone_back(0, 0)),
        (0.14, prone_back(0, 0, pelvis=(-0.85, 0.0, -0.81), pelvis_rot=(0, -84, 0), spine=(22, 4, 0), neck=(14, 0, 0), al=FK(flex=20, abd=36, elbow=60), ar=FK(flex=18, abd=38, elbow=62))),
        (0.34, relaxed(pelvis=(-0.60, 0.0, -0.76), pelvis_rot=(0, -46, 0), spine=(30, 6, 0), neck=(10, 0, 0), fl=foot_rest('l', x=0.10, y=0.05), fr=foot_rest('r', x=0.06, y=-0.08),
                       al=('ik', dict(target=(-0.42, 0.26, 0.10), dir=(-0.4, 0.5, -0.8), palm=(0, 0, -1), elbow_hint=(-0.4, 0.5, 0.3))), ar=('ik', dict(target=(-0.42, -0.26, 0.10), dir=(-0.4, -0.5, -0.8), palm=(0, 0, -1), elbow_hint=(-0.4, -0.5, 0.3))),
                       hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8), reach=False)),
        (0.54, relaxed(pelvis=(-0.32, 0.0, -0.66), pelvis_rot=(0, -16, 0), spine=(26, 0, 0), neck=(-6, 0, 0), fl=foot_rest('l', x=0.30, y=0.10, roll=-8), fr=foot_rest('r', x=0.06, y=-0.12, roll=30),
                       al=('ik', dict(target=(-0.30, 0.26, 0.10), dir=(-0.2, 0.5, -0.8), palm=(0, 0, -1), elbow_hint=(-0.3, 0.5, 0.35))), ar=('ik', dict(target=(-0.22, -0.28, 0.10), dir=(0.2, -0.5, -0.8), palm=(0, 0, -1), elbow_hint=(-0.2, -0.5, 0.35))),
                       hl=dict(curl=0.0, spread=0.8), hr=dict(curl=0.0, spread=0.8), reach=False)),
        (0.74, relaxed(pelvis=(0.0, 0.0, -0.34), pelvis_rot=(0, 10, -8), spine=(22, -8, 0), neck=(-8, 0, 0), fl=foot_rest('l', x=0.20, y=0.06, yaw=-10), fr=foot_rest('r', x=-0.08, y=-0.10, yaw=-20),
                       al=FK(flex=40, abd=0, elbow=70), ar=('ik', dict(target=(0.34, -0.26, 0.20), dir=(0.9, 0, -0.4), palm=(0, 0, -1), elbow_hint=(0.1, -0.45, 0.4))))),
        (0.90, combat(pelvis=(0.0, 0.0, -0.14), spine=(14, -10, 0))),
        (1.0, combat()),
    ]
    c = build_clip('getup_back', e, keys, note='from face-up: sit up on both hands, draw the legs in, roll onto one knee and rise to the ready stance')
    c.event('ground_impact', 0.14)
    c.event('getup_stand', 0.9)
    c.event('control_return', 0.95)
    return c


# ----------------------------------------------------------------------------- sleep

def sleeping(ph=0.0, amp=1.0, **o):
    br = math.sin(ph) * amp
    k = relaxed(pelvis=(0.0, -0.06, -0.70), pelvis_rot=(90, 0, 0), spine=(16 + 1.5 * br, 0, 6 + br), neck=(16, 0, -10), fl=foot_rest('l', x=0.16, y=0.0, z=0.20, pitch=20), fr=foot_rest('r', x=0.20, y=-0.02, z=0.12, pitch=26),
                al=FK(flex=60, abd=24, elbow=100), ar=FK(flex=100, abd=30, elbow=120), hl=dict(curl=0.5), hr=dict(curl=0.6), reach=False)
    k['face'] = FL.expression('neutral')
    k.update(o)
    return k


@clip('sleep_start')
def sleep_start(e):
    roll_key = relaxed(pelvis=(-0.02, 0.06, -0.78), pelvis_rot=(-46, 6, 0), spine=(18, 0, -4), neck=(12, 0, 6), fl=foot_rest('l', x=0.22, y=0.02, z=0.09, pitch=20), fr=foot_rest('r', x=0.24, y=-0.04, z=0.09, pitch=24),
                       al=('ik', dict(target=(0.06, 0.24, 0.34), dir=(0.5, 0.2, -0.8), palm=(0, 0, -1), elbow_hint=(-0.20, 0.44, 0.46))), ar=('ik', dict(target=(0.0, -0.28, 0.10), dir=(0.5, -0.2, -0.8), palm=(0, 0, -1), elbow_hint=(-0.2, -0.5, 0.3))), reach=False)
    keys = [
        (0.0, relaxed()),
        (0.18, relaxed(pelvis=(-0.02, 0.0, -0.38), pelvis_rot=(0, 6, 0), spine=(16, 0, 0), neck=(6, 0, 0), fl=foot_rest('l', x=0.08, y=0.02), fr=foot_rest('r', x=-0.06, y=-0.02),
                       al=FK(flex=14, abd=-8, elbow=50), ar=FK(flex=14, abd=-8, elbow=50))),
        (0.38, relaxed(pelvis=(-0.10, 0.0, -0.74), pelvis_rot=(0, 10, 0), spine=(24, 0, 0), neck=(10, 0, 0), fl=foot_rest('l', x=0.34, y=0.06, z=0.06, pitch=16), fr=foot_rest('r', x=0.34, y=-0.06, z=0.06, pitch=16),
                       al=('ik', dict(target=(-0.20, 0.30, 0.10), dir=(0.3, 0.3, -0.9), palm=(0, 0, -1), elbow_hint=(-0.3, 0.5, 0.4))), ar=('ik', dict(target=(-0.20, -0.30, 0.10), dir=(0.3, -0.3, -0.9), palm=(0, 0, -1), elbow_hint=(-0.3, -0.5, 0.4))),
                       hl=dict(curl=0.1), hr=dict(curl=0.1), reach=False, face=FL.expression('neutral'))),
        (0.62, roll_key),
        (0.645, fk_like(roll_key)),        # the arms switch from IK to FK here, in the same pose, so no IK/FK blend runs across the last 20 frames
        (1.0, sleeping(0, 0)),
    ]
    c = build_clip('sleep_start', e, keys, note='kneel, sit and recline onto the left side into a curled sleeping posture')
    c.event('sleep_settle', 0.9)
    return c


@clip('sleep_loop')
def sleep_loop(e):
    keys = [(i / 10, sleeping(TAU * i / 10, 1.0)) for i in range(11)]
    c = build_clip('sleep_loop', e, keys, note='curled on the left side, slow breathing')
    return c


@clip('sleep_end')
def sleep_end(e):
    keys = [
        (0.0, sleeping(0, 0)),
        (0.22, sleeping(0, 0, spine=(6, 0, 0), neck=(-4, 0, 0), al=FK(flex=96, abd=34, elbow=50), ar=FK(flex=120, abd=44, elbow=24), hl=dict(curl=0.0, spread=1.0), hr=dict(curl=0.0, spread=1.0), face=FL.expression('surprise', 0.3))),
        (0.42, relaxed(pelvis=(-0.02, 0.06, -0.78), pelvis_rot=(-40, 6, 0), spine=(20, 0, 0), neck=(4, 0, 0), fl=foot_rest('l', x=0.30, y=0.04, z=0.04), fr=foot_rest('r', x=0.32, y=-0.04, z=0.04),
                       al=FK(flex=30, abd=20, elbow=60), ar=('ik', dict(target=(0.0, -0.28, 0.10), dir=(0.5, -0.2, -0.8), palm=(0, 0, -1), elbow_hint=(-0.2, -0.5, 0.3))), reach=False)),
        (0.62, relaxed(pelvis=(-0.02, 0.0, -0.60), pelvis_rot=(0, 8, -10), spine=(16, -10, 0), neck=(-4, 8, 0), fl=foot_rest('l', x=0.20, y=0.08, roll=-8), fr=foot_rest('r', x=-0.04, y=-0.10, roll=30),
                       al=FK(flex=30, abd=0, elbow=60), ar=('ik', dict(target=(0.20, -0.28, 0.10), dir=(0.9, 0, -0.4), palm=(0, 0, -1), elbow_hint=(0.0, -0.45, 0.4))))),
        (0.82, combat(pelvis=(0.0, 0.0, -0.15), spine=(12, -8, 0))),
        (1.0, combat()),
    ]
    c = build_clip('sleep_end', e, keys, note='wake up: stretch, sit up, get a hand under the body and rise to the ready stance')
    c.event('getup_stand', 0.82)
    c.event('control_return', 0.92)
    return c


# ----------------------------------------------------------------------------- death and respawn

def dead_front_pose():
    k = prone_front(0, 0, pelvis=(0.90, 0.02, -0.80), pelvis_rot=(6, 90, 8), spine=(-4, 6, 3), neck=(-6, -55, 6),
                    fl=foot_rest('l', x=-0.05, y=0.10, yaw=8, z=0.46, pitch=40), fr=foot_rest('r', x=0.12, y=-0.10, yaw=-12, z=0.20, pitch=58, roll=10),
                    al=('ik', dict(target=(1.85, 0.44, 0.05), dir=(1.0, 0.2, -0.1), palm=(0, 0, -1), elbow_hint=(1.50, 0.85, 0.12))),
                    ar=('ik', dict(target=(0.98, -0.52, 0.085), dir=(0.3, -0.9, -0.1), palm=(0, 0, -1), elbow_hint=(1.20, -0.85, 0.10))), hl=dict(curl=0.05, spread=0.8), hr=dict(curl=0.6))
    k['face'] = FL.expression('pain', 0.25)
    return k


def dead_back_pose():
    k = prone_back(0, 0, pelvis=(-0.90, -0.03, -0.792), pelvis_rot=(-8, -90, -14), spine=(8, 8, -4), neck=(12, 34, -8), fl=foot_rest('l', x=0.02, y=0.16, yaw=16, z=0.15, pitch=-54), fr=foot_rest('r', x=-0.04, y=-0.06, yaw=-8, z=0.11, pitch=-70),
                   al=('ik', dict(target=(-1.28, 0.82, 0.16), dir=(0.1, 1.0, 0.0), palm=(0, 0, -1), elbow_hint=(-1.30, 0.55, 0.16))),
                   ar=('ik', dict(target=(-0.92, -0.66, 0.06), dir=(0.6, -0.8, 0.0), palm=(0, 0, -1), elbow_hint=(-1.26, -0.56, 0.08))), hl=dict(curl=0.1, spread=1.0), hr=dict(curl=0.3))
    k['face'] = FL.expression('pain', 0.2)
    return k


@clip('death_front')
def death_front(e):
    keys = [
        (0.0, combat()),
        (0.10, relaxed(pelvis=(-0.08, 0.0, -0.10), pelvis_rot=(0, -8, 8), spine=(-24, 8, 0), neck=(-18, 6, 0), al=FK(flex=80, abd=40, elbow=34), ar=FK(flex=70, abd=44, elbow=40), face=FL.expression('pain', 0.9))),
        (0.30, relaxed(pelvis=(0.0, 0.02, -0.22), pelvis_rot=(4, 6, -6), spine=(20, -6, 0), neck=(8, -10, 0), fl=foot_rest('l', x=0.18, y=0.05, yaw=-10), fr=foot_rest('r', x=-0.14, y=-0.09, yaw=-20),
                       al=FK(flex=20, abd=8, elbow=44), ar=('ik', dict(target=(0.14, 0.02, 1.04), dir=(0.3, 0.9, -0.2), palm=(0, 0.3, 1), elbow_hint=(-0.1, -0.30, 0.95))), face=FL.expression('pain', 0.8))),
        (0.50, relaxed(pelvis=(0.10, 0.02, -0.52), pelvis_rot=(4, 24, -6), spine=(18, -6, 4), neck=(10, -14, 0), fl=foot_rest('l', x=0.18, y=0.05, z=0.04, yaw=-10, roll=18), fr=foot_rest('r', x=-0.30, y=-0.09, z=0.06, yaw=-20, roll=45),
                       al=FK(flex=30, abd=20, elbow=30), ar=FK(flex=40, abd=0, elbow=50), reach=False)),
        (0.68, relaxed(pelvis=(0.44, 0.02, -0.60), pelvis_rot=(6, 56, 4), spine=(6, 4, 2), neck=(-12, -20, 0), fl=foot_rest('l', x=0.10, y=0.06, yaw=4, z=0.12, pitch=30), fr=foot_rest('r', x=0.04, y=-0.10, z=0.12, pitch=28, roll=10),
                       al=('ik', dict(target=(1.10, 0.42, 0.26), dir=(1.0, 0.1, -0.5), palm=(0, 0, -1), elbow_hint=(0.80, 0.80, 0.45))), ar=('ik', dict(target=(0.96, -0.46, 0.28), dir=(0.9, -0.1, -0.5), palm=(0, 0, -1), elbow_hint=(0.70, -0.80, 0.45))), reach=False)),
        (0.84, {**dead_front_pose(), 'pelvis': (0.92, 0.02, -0.80), 'spine': (-10, 6, 3)}),
        (1.0, dead_front_pose()),
    ]
    c = build_clip('death_front', e, keys, note='front impact: recoil, a stagger with a hand to the wound, knees give, topple forward; the last frame equals dead_front')
    c.event('hit_peak', 0.1)
    c.event('death_impact', 0.78)
    return c


@clip('death_back')
def death_back(e):
    keys = [
        (0.0, combat()),
        (0.10, relaxed(pelvis=(-0.14, 0.0, -0.12), pelvis_rot=(0, -12, -8), spine=(-28, -8, 0), neck=(-20, -8, 0), fl=foot_rest('l', x=0.22, z=0.03), al=FKS(flex=90, abd=44, elbow=30), ar=FKS(flex=80, abd=46, elbow=34), face=FL.expression('pain', 0.9))),
        (0.32, relaxed(pelvis=(-0.24, 0.0, -0.26), pelvis_rot=(-6, -18, -10), spine=(-20, -12, 6), neck=(-12, -14, 0), fl=foot_rest('l', x=0.36, z=0.06, roll=-14), fr=foot_rest('r', x=-0.06, y=-0.11, yaw=-30, roll=24),
                       al=FKS(flex=120, abd=50, elbow=28), ar=FKS(flex=100, abd=54, elbow=40), reach=False, face=FL.expression('pain', 0.85))),
        (0.54, relaxed(pelvis=(-0.52, 0.0, -0.62), pelvis_rot=(-8, -58, -12), spine=(-2, 6, 2), neck=(8, 24, -4), fl=foot_rest('l', x=0.20, y=0.12, z=0.10, pitch=-14, roll=-30), fr=foot_rest('r', x=-0.06, y=-0.10, pitch=-26, roll=20),
                       al=FKS(flex=100, abd=64, elbow=24), ar=FKS(flex=40, abd=40, elbow=20), reach=False)),
        (0.72, {**dead_back_pose(), 'pelvis': (-0.90, -0.03, -0.806), 'neck': (16, 30, -8)}),
        (1.0, dead_back_pose()),
    ]
    c = build_clip('death_back', e, keys, note='back impact: arched recoil, a backward stagger with a crossing step, fall onto the back with the cyber arm flung wide; the last frame equals dead_back')
    c.event('hit_peak', 0.1)
    c.event('death_impact', 0.62)
    return c


@clip('dead_front')
def dead_front_clip(e):
    k = dead_front_pose()
    c = build_clip('dead_front', e, [(0.0, k), (1.0, k)], loop=False, note='held final pose of death_front (identical to its last frame)')
    c.meta['static'] = True
    return c


@clip('dead_back')
def dead_back_clip(e):
    k = dead_back_pose()
    c = build_clip('dead_back', e, [(0.0, k), (1.0, k)], loop=False, note='held final pose of death_back (identical to its last frame)')
    c.meta['static'] = True
    return c


@clip('respawn')
def respawn(e):
    kneel = relaxed(pelvis=(0.10, 0.0, -0.60), pelvis_rot=(0, 26, 0), spine=(38, 0, 0), neck=(30, 0, 0), fl=foot_rest('l', x=0.36, y=0.10, yaw=6, roll=10), fr=foot_rest('r', x=-0.14, y=-0.08, pitch=50, z=0.19, roll=40),
                    al=FK(flex=30, abd=-6, elbow=90), ar=('ik', dict(target=(0.30, -0.22, 0.05), dir=(0.9, 0, -0.4), palm=(0, 0, -1), elbow_hint=(0.0, -0.45, 0.35))), hl=dict(curl=0.9), hr=dict(curl=0.0, spread=0.6), reach=False)
    keys = [
        (0.0, kneel),
        (0.14, {**kneel, 'spine': (40, 0, 0), 'neck': (32, 0, 0)}),
        (0.30, relaxed(**{**kneel, 'pelvis': (0.10, 0.0, -0.56), 'spine': (34, 0, 0), 'neck': (24, 6, 0), 'hl': dict(curl=0.4, spread=0.8), 'face': FL.expression('focus', 0.6)})),
        (0.52, relaxed(pelvis=(0.06, 0.0, -0.36), pelvis_rot=(0, 16, -4), spine=(26, -6, 0), neck=(4, 10, 0), fl=foot_rest('l', x=0.26, y=0.08), fr=foot_rest('r', x=-0.08, y=-0.09, roll=24),
                       al=FK(flex=40, abd=20, elbow=70), ar=('ik', dict(target=(0.30, -0.24, 0.16), dir=(0.9, 0, -0.4), palm=(0, 0, -1), elbow_hint=(0.0, -0.45, 0.45))), hl=dict(curl=0.0, spread=1.0), face=FL.expression('focus', 0.8))),
        (0.72, relaxed(pelvis=(0.02, 0.0, -0.16), pelvis_rot=(0, 6, -6), spine=(14, -8, 0), neck=(-8, 0, 0), fl=foot_rest('l', x=0.16, y=0.05, yaw=-8), fr=foot_rest('r', x=-0.10, y=-0.08, yaw=-16),
                       al=FK(flex=20, abd=40, elbow=30), ar=FK(flex=20, abd=40, elbow=30), hl=dict(curl=0.0, spread=1.0), hr=dict(curl=0.0, spread=1.0), face=FL.expression('joy_confidence', 0.4))),
        (0.88, combat(pelvis=(0.0, 0.0, -0.12), spine=(12, -14, 0), neck=(-6, 10, 0), face=FL.expression('focus', 0.6))),
        (1.0, combat(face=FL.expression('focus', 0.45))),
    ]
    c = build_clip('respawn', e, keys, note='reactivation from a kneeling crouch: shudder, unfold, rise and settle into the ready stance (not a reversed death)')
    c.event('respawn_activate', 0.3)
    c.event('control_return', 0.95)
    return c


# ----------------------------------------------------------------------------- social

@clip('greet')
def greet(e):
    N = e['frames']
    keys = []
    for i in range(9):
        t = i / 8
        wave = math.sin(TAU * 3 * t) if 0.25 < t < 0.8 else 0.0
        up = 1.0 if 0.18 < t < 0.85 else 0.0
        env = min(max((t - 0.12) / 0.14, 0.0), 1.0) * min(max((0.9 - t) / 0.14, 0.0), 1.0)
        k = relaxed(pelvis=(0.0, 0.0, -0.03 - 0.008 * math.sin(TAU * t)), spine=(-2 * env, -6 * env, 0), neck=(2 - 6 * env * math.sin(TAU * 2 * t) * 0.3, -8 * env, 4 * env),
                    ar=FK(flex=10 * env, abd=68 * env - 20 * (1 - env), elbow=100 * env + 14 * (1 - env), wdev=22 * wave * env, wroll=10 * env), hr=dict(curl=-0.2 * env + 0.25 * (1 - env), spread=0.9 * env))
        k['face'] = FL.expression('joy_confidence', 0.65 * env)
        keys.append((t, k))
    c = build_clip('greet', e, keys, note='friendly greeting: right hand raised in a wave, nod and a warm expression')
    add_blinks(c, [int(N * 0.5)])
    c.event('control_return', 0.9)
    return c


@clip('victory')
def victory(e):
    N = e['frames']
    def vk(t):
        env = min(max((t - 0.10) / 0.16, 0.0), 1.0) * min(max((0.95 - t) / 0.12, 0.0), 1.0)
        pump = math.sin(TAU * 2.5 * t) if 0.3 < t < 0.75 else 0.0
        k = relaxed(pelvis=(0.0, 0.0, -0.02 + 0.03 * env - 0.02 * abs(pump) * env), spine=(-8 * env, 6 * env * pump, 0), neck=(6 * env, 8 * pump * env, 0),
                    fl=foot_rest('l', x=0.04, roll=40 * env), fr=foot_rest('r', x=-0.02, roll=38 * env),
                    al=FKS(flex=150 * env + 4 * (1 - env), abd=30 * env + 12 * (1 - env) + 8 * pump * env, elbow=50 * env + 14 * (1 - env) - 20 * pump * env, wflex=-10 * env),
                    ar=FKS(flex=140 * env + 4 * (1 - env), abd=34 * env + 12 * (1 - env), elbow=70 * env + 14 * (1 - env) + 24 * pump * env), hl=dict(curl=1.05 * env + 0.25 * (1 - env)), hr=dict(curl=1.05 * env + 0.25 * (1 - env)), reach=False)
        k['face'] = FL.expression('joy_confidence', 0.95 * env)
        k['extra'] = _blade(env)
        return k
    keys = [(i / 12, vk(i / 12)) for i in range(13)]
    c = build_clip('victory', e, keys, note='confident celebration: both fists up, chest out, a fist-pump with the blade flourish and a broad smile')
    c.event('blade_extend', 0.35)
    c.event('blade_retract', 0.8)
    return c


def _blade(env):
    p = Pose()
    p.loc('ctl_blade', (0.0, 0.22 * (1.0 if 0.4 < env < 0.95 and env > 0.9 else 0.0), 0.0))
    return p


@clip('defeat')
def defeat(e):
    N = e['frames']
    def dk(t):
        env = min(max((t - 0.08) / 0.2, 0.0), 1.0) * min(max((0.95 - t) / 0.18, 0.0), 1.0)
        br = 0.5 - 0.5 * math.cos(TAU * 2 * t)
        shake = math.sin(TAU * 1.5 * t) if 0.35 < t < 0.7 else 0.0
        k = relaxed(pelvis=(-0.01 * env, 0.0, -0.05 * env - 0.022), pelvis_rot=(0, 4 * env, 0), spine=(20 * env + 2.5 * br * env, 4 * shake, 0), neck=(26 * env, 12 * shake * env, 0),
                    al=FK(flex=8 * env + 4, abd=-14 * env - 6, elbow=20 * env + 14), ar=FK(flex=8 * env + 4, abd=-14 * env - 6, elbow=20 * env + 14), hl=dict(curl=0.15), hr=dict(curl=0.2), fl=foot_rest('l', x=0.02), fr=foot_rest('r', x=-0.02))
        k['face'] = FL.expression('concern_sadness', 0.85 * env)
        return k
    keys = [(i / 12, dk(i / 12)) for i in range(13)]
    c = build_clip('defeat', e, keys, note='disappointment: shoulders drop, head sinks, a slow shake of the head and a heavy exhale')
    add_blinks(c, [int(N * 0.4), int(N * 0.62)], dur=8)
    add_gaze(c, [(0, 0, 0), (int(N * 0.25), -4, -14), (int(N * 0.8), 0, -10), (N, 0, 0)])
    return c

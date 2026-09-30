"""Hand-authored clips, part 2: aim poses, ranged fire/burst, melee, reload, casts, channel, charge, deploy, uplink."""
import math
import numpy as np
from mathutils import Vector, Matrix
import skeleton_def as S
import anim_lib as AL
from anim_lib import Pose
import face_lib as FL
import pose_lib as PL
import cyber_arm as CA
from keypose import resolve, build_clip, plant, foot_rest, aim_dir
from anim_registry import clip
from clips_basic import relaxed, combat, add_blinks, add_gaze, FK, FKS, TAU

BLADE_EXT = 0.22


def aim_key(yaw=0.0, pitch=0.0, recoil=0.0, climb=0.0, reach=0.60, **o):
    """Upper-body aim pose; legs neutral. yaw + = left, pitch + = up (degrees). The left (emitter) arm is IK-aimed."""
    k = relaxed(pelvis=(0.0, 0.0, -0.05), pelvis_rot=(0, 0, 0.12 * yaw), spine=(-0.25 * pitch + 2, 0.45 * yaw, 0), neck=(-0.2 * pitch - 2, 0.25 * yaw, 0),
                fl=foot_rest('l', x=0.03), fr=foot_rest('r', x=-0.03),
                al=('aim', dict(yaw=yaw, pitch=pitch + climb, reach=reach - recoil, roll=0.0, elbow_hint=None)),
                ar=FK(flex=34, abd=-10, elbow=104), hl=dict(curl=0.15), hr=dict(curl=0.6))
    k.update(o)
    return k


def _aim_pose_clip(pitch_name, yaw_name):
    pitch = {'down': -35.0, 'level': 0.0, 'up': 35.0}[pitch_name]
    yaw = {'left': 60.0, 'center': 0.0, 'right': -60.0}[yaw_name]
    cid = f'aim_{pitch_name}_{yaw_name}'

    def gen(e):
        k = aim_key(yaw, pitch)
        c = build_clip(cid, e, [(0.0, k), (1.0, k)], loop=False,
                       note=f'aim pose yaw {yaw:+.0f} (positive = left), pitch {pitch:+.0f} (positive = up); legs identical in all nine samples',
                       meta={'aim_yaw_deg': yaw, 'aim_pitch_deg': pitch})
        c.meta['static'] = True
        return c
    clip(cid)(gen)


for _p in ('down', 'level', 'up'):
    for _y in ('left', 'center', 'right'):
        _aim_pose_clip(_p, _y)


@clip('ranged_fire')
def ranged_fire(e):
    keys = [(0.0, aim_key()), (0.11, aim_key(recoil=0.055, climb=5, spine=(-2, 0.0, 0))), (0.22, aim_key(recoil=0.02, climb=1.5)), (0.55, aim_key(recoil=-0.004, climb=-0.5)), (1.0, aim_key())]
    c = build_clip('ranged_fire', e, keys, note='single wrist-emitter shot with recoil and recovery (upper-body layer)')
    c.event('muzzle_fire', 1, index=0)
    c.event('cancel_window_begin', 6)
    return c


@clip('ranged_burst')
def ranged_burst(e):
    N = e['frames']
    keys = [(0.0, aim_key())]
    for i, tf in enumerate((0.11, 0.44, 0.77)):
        keys.append((tf, aim_key(recoil=0.05, climb=4 + 3 * i)))
        keys.append((tf + 0.14, aim_key(recoil=0.012, climb=2 + 3 * i)))
    keys.append((1.0, aim_key()))
    c = build_clip('ranged_burst', e, keys, note='three-shot burst with muzzle climb (upper-body layer)')
    for i, f in enumerate((2, 8, 14)):
        c.event('muzzle_fire', f, index=i)
    c.event('cancel_window_begin', 16)
    return c


# ----------------------------------------------------------------------------- melee

def _blade_pose(ext):
    p = Pose()
    p.loc('ctl_blade', (0.0, ext, 0.0))
    return p


def _melee_key(t_ext, **o):
    k = combat()
    k.update(o)
    k['extra'] = _blade_pose(BLADE_EXT * t_ext)
    return k


def _with_blade(c, ext_curve):
    """ext_curve: list of (frame, extension 0..1) keyed on ctl_blade Y (metres)."""
    for f, x in ext_curve:
        c.key(f, _blade_pose(BLADE_EXT * x))


@clip('melee_1')
def melee_1(e):
    a = dict(al=FK(flex=100, abd=-30, elbow=62, wflex=-10, roll=-20))
    keys = [
        (0.0, _melee_key(0.0)),
        (0.14, _melee_key(1.0, pelvis=(-0.02, -0.03, -0.11), pelvis_rot=(0, 3, -16), spine=(12, -34, 3), neck=(-8, -12, 0), fl=foot_rest('l', x=0.10, y=0.035, yaw=-10), fr=foot_rest('r', x=-0.16, y=-0.06, yaw=-25),
                          al=FK(flex=100, abd=-30, elbow=62, wflex=-10), ar=FK(flex=30, abd=-16, elbow=110))),
        (0.30, _melee_key(1.0, pelvis=(-0.03, -0.035, -0.12), pelvis_rot=(0, 3, -22), spine=(14, -42, 4), neck=(-8, -18, 0), fl=foot_rest('l', x=0.08, y=0.035, yaw=-10), fr=foot_rest('r', x=-0.18, y=-0.06, yaw=-25),
                          al=FK(flex=116, abd=-40, elbow=46, wflex=-14), ar=FK(flex=26, abd=-18, elbow=112))),
        (0.42, _melee_key(1.0, pelvis=(0.10, 0.01, -0.19), pelvis_rot=(3, 6, 4), spine=(18, 4, -4), neck=(-8, 18, 0), fl=foot_rest('l', x=0.46, y=0.05, yaw=-4, roll=-10), fr=foot_rest('r', x=-0.20, y=-0.07, yaw=-20, roll=24),
                          al=FK(flex=58, abd=16, elbow=22, wflex=6), ar=FK(flex=20, abd=-24, elbow=100))),
        (0.54, _melee_key(1.0, pelvis=(0.12, 0.03, -0.20), pelvis_rot=(4, 6, 14), spine=(22, 32, -6), neck=(-6, 26, 0), fl=foot_rest('l', x=0.48, y=0.06, yaw=4), fr=foot_rest('r', x=-0.20, y=-0.07, yaw=-16, roll=26),
                          al=FK(flex=22, abd=58, elbow=12, wflex=8), ar=FK(flex=24, abd=-30, elbow=96))),
        (0.72, _melee_key(1.0, pelvis=(0.08, 0.02, -0.17), pelvis_rot=(2, 5, 8), spine=(16, 22, -3), neck=(-6, 18, 0), fl=foot_rest('l', x=0.40, y=0.05), fr=foot_rest('r', x=-0.14, y=-0.06, yaw=-16),
                          al=FK(flex=30, abd=48, elbow=20), ar=FK(flex=26, abd=-26, elbow=100))),
        (1.0, _melee_key(0.0)),
    ]
    c = build_clip('melee_1', e, keys, note='diagonal forearm-blade slash from high right to low left with a lunge step')
    _with_blade(c, [(0, 0.0), (3, 1.0), (21, 1.0), (24, 0.0)])
    c.event('blade_extend', 2)
    c.event('melee_hit_begin', 10)
    c.event('melee_hit_end', 14)
    c.event('melee_recover', 17)
    c.event('blade_retract', 21)
    c.event('foot_plant', 12, foot='l')
    c.event('control_return', 22)
    return c


@clip('melee_2')
def melee_2(e):
    keys = [
        (0.0, _melee_key(0.0)),
        (0.16, _melee_key(1.0, pelvis=(-0.03, 0.05, -0.24), pelvis_rot=(-4, 8, 18), spine=(20, 32, -4), neck=(-10, 14, 0), fl=foot_rest('l', x=0.12, y=0.06, yaw=8), fr=foot_rest('r', x=-0.30, y=-0.10, yaw=-30, roll=8),
                          al=FK(flex=26, abd=52, elbow=18, wflex=10), ar=FK(flex=40, abd=-8, elbow=96))),
        (0.32, _melee_key(1.0, pelvis=(-0.04, 0.06, -0.26), pelvis_rot=(-5, 9, 24), spine=(22, 40, -5), neck=(-10, 20, 0), fl=foot_rest('l', x=0.10, y=0.07, yaw=10), fr=foot_rest('r', x=-0.32, y=-0.10, yaw=-30, roll=10),
                          al=FK(flex=18, abd=62, elbow=14, wflex=12), ar=FK(flex=44, abd=-6, elbow=94))),
        (0.44, _melee_key(1.0, pelvis=(0.08, -0.02, -0.17), pelvis_rot=(2, 4, -6), spine=(12, -8, 2), neck=(-8, -12, 0), fl=foot_rest('l', x=0.14, y=0.05, yaw=-2), fr=foot_rest('r', x=0.38, y=-0.08, yaw=-16, roll=-8),
                          al=FK(flex=70, abd=8, elbow=24, wflex=-4), ar=FK(flex=30, abd=-20, elbow=104))),
        (0.56, _melee_key(1.0, pelvis=(0.10, -0.03, -0.18), pelvis_rot=(3, 4, -16), spine=(10, -40, 4), neck=(-8, -24, 0), fl=foot_rest('l', x=0.10, y=0.05, yaw=-6, roll=18), fr=foot_rest('r', x=0.42, y=-0.09, yaw=-14),
                          al=FK(flex=118, abd=-38, elbow=28, wflex=-14), ar=FK(flex=24, abd=-24, elbow=100))),
        (0.74, _melee_key(1.0, pelvis=(0.06, -0.02, -0.15), pelvis_rot=(2, 4, -10), spine=(10, -28, 3), neck=(-8, -18, 0), fl=foot_rest('l', x=0.14, y=0.04, yaw=-8), fr=foot_rest('r', x=0.32, y=-0.08, yaw=-14),
                          al=FK(flex=104, abd=-30, elbow=36), ar=FK(flex=30, abd=-22, elbow=100))),
        (1.0, _melee_key(0.0)),
    ]
    c = build_clip('melee_2', e, keys, note='reverse rising slash from low left to high right, coiled crouch and a right-foot step')
    _with_blade(c, [(0, 0.0), (3, 1.0), (21, 1.0), (24, 0.0)])
    c.event('blade_extend', 2)
    c.event('melee_hit_begin', 11)
    c.event('melee_hit_end', 15)
    c.event('melee_recover', 18)
    c.event('blade_retract', 21)
    c.event('foot_plant', 13, foot='r')
    c.event('control_return', 22)
    return c


@clip('melee_3')
def melee_3(e):
    up = dict(pelvis=(-0.02, 0.0, -0.03), pelvis_rot=(0, -6, -4), spine=(-18, -6, 0), neck=(6, -6, 0), fl=foot_rest('l', x=0.04, y=0.04, roll=38), fr=foot_rest('r', x=-0.06, y=-0.08, roll=34),
              al=FK(flex=168, abd=-8, elbow=30, wflex=-16), ar=FK(flex=165, abd=-16, elbow=34), reach=False)
    keys = [
        (0.0, _melee_key(0.0)),
        (0.13, _melee_key(1.0, pelvis=(-0.03, 0.0, -0.20), pelvis_rot=(0, 8, -8), spine=(22, -14, 0), neck=(-8, -8, 0), fl=foot_rest('l', x=0.12, y=0.05), fr=foot_rest('r', x=-0.22, y=-0.08),
                          al=FK(flex=120, abd=-14, elbow=70), ar=FK(flex=110, abd=-14, elbow=84))),
        (0.30, {**_melee_key(1.0), **up, 'extra': _blade_pose(BLADE_EXT)}),
        (0.54, _melee_key(1.0, pelvis=(0.24, 0.02, -0.44), pelvis_rot=(2, 10, 8), spine=(44, 10, -3), neck=(-14, 8, 0), fl=foot_rest('l', x=0.66, y=0.05, yaw=2, roll=-12), fr=foot_rest('r', x=-0.30, y=-0.09, yaw=-14, roll=34),
                          al=FK(flex=52, abd=6, elbow=12, wflex=8), ar=FK(flex=58, abd=-12, elbow=18))),
        (0.68, _melee_key(1.0, pelvis=(0.24, 0.02, -0.46), pelvis_rot=(3, 12, 10), spine=(48, 16, -4), neck=(-16, 10, 0), fl=foot_rest('l', x=0.66, y=0.06, yaw=4), fr=foot_rest('r', x=-0.30, y=-0.09, yaw=-14, roll=34),
                          al=FK(flex=30, abd=34, elbow=10), ar=FK(flex=40, abd=8, elbow=20))),
        (0.86, _melee_key(1.0, pelvis=(0.14, 0.02, -0.30), pelvis_rot=(2, 8, 6), spine=(30, 12, -2), neck=(-10, 8, 0), fl=foot_rest('l', x=0.50, y=0.05), fr=foot_rest('r', x=-0.18, y=-0.08, roll=12),
                          al=FK(flex=46, abd=22, elbow=40), ar=FK(flex=40, abd=-8, elbow=70))),
        (1.0, _melee_key(0.0)),
    ]
    c = build_clip('melee_3', e, keys, note='committed overhead finisher: rise to a two-arm overhead raise, deep lunge chop, long follow-through and slow recovery')
    _with_blade(c, [(0, 0.0), (3, 1.0), (23, 1.0), (24, 0.0)])
    c.event('blade_extend', 2)
    c.event('melee_hit_begin', 12)
    c.event('melee_hit_end', 17)
    c.event('melee_recover', 20)
    c.event('blade_retract', 23)
    c.event('foot_plant', 13, foot='l')
    c.event('control_return', 23)
    return c


# ----------------------------------------------------------------------------- reload (uses matrix based grips)

def _forearm_front(ev):
    """Slot outward direction and forearm axis (world) from the evaluated left forearm."""
    fa = PL.world_of(ev, 'def_lowerarm_l')
    rest = PL.skel_rest('lowerarm_l')
    R = fa.to_3x3() @ rest.to_3x3().inverted()
    return (R @ Vector(CA.FRONT)).normalized(), (R @ Vector(CA.FA)).normalized()


@clip('reload')
def reload_clip(e):
    N = e['frames']
    left_up = dict(al=FK(flex=58, abd=-36, elbow=104, wflex=8, roll=30))
    base = combat(pelvis=(0.0, 0.0, -0.07), pelvis_rot=(0, 3, -4), spine=(8, -8, 0), neck=(-4, 0, 0), fl=foot_rest('l', x=0.10, y=0.03, yaw=-8), fr=foot_rest('r', x=-0.10, y=-0.06, yaw=-16), **left_up)
    base['ar'] = FK(flex=36, abd=-12, elbow=100)
    ev = PL.evaluate(resolve(base))
    Ms = PL.slot_matrix(ev)
    front, fa = _forearm_front(ev)
    Gc = PL.grip_matrix('cell', 'r')
    Gi = Gc.inverted()
    pouch_pos = Vector((0.055, -0.150, 1.045))
    Mp = PL.prop_world_matrix('cell', pouch_pos, axis=(0, 0, 1))
    M_hover = Matrix.Translation(front * 0.16) @ Ms
    M_lift = Matrix.Translation(front * 0.13) @ Ms
    M_hover2 = Matrix.Translation(front * 0.12) @ Ms
    def hk(M, **o):
        k = dict(base)
        k['ar'] = ('ikmat', dict(M=M @ Gi))
        k['hr'] = dict(curl=o.pop('curl', 0.9), thumb=0.3)
        k.update(o)
        return k
    keys = [
        (0.0, combat()),
        (0.14, {**base, 'ar': FK(flex=40, abd=-14, elbow=96)}),
        (0.26, hk(M_hover, curl=0.05)),
        (0.34, hk(Ms, curl=0.95)),                          # grip the seated cell
        (0.42, hk(M_lift, curl=0.95, spine=(9, -10, 0))),   # pull the cell out of the slot
        (0.56, hk(Mp, curl=0.95, spine=(12, -14, 0), neck=(-2, -6, 0))),   # to the hip pouch
        (0.62, hk(Mp, curl=0.10, spine=(12, -14, 0), neck=(-2, -6, 0))),   # hand-off: release
        (0.68, hk(Mp, curl=0.95, spine=(12, -14, 0), neck=(-2, -6, 0))),   # take the fresh cell
        (0.80, hk(M_hover2, curl=0.95)),
        (0.88, hk(Ms, curl=0.95)),                          # seat it
        (0.94, hk(M_hover, curl=0.10)),
        (1.0, combat()),
    ]
    def states(f, ev_):
        t = f / N
        if t < 0.34:
            return {'cell': 'slot', 'beacon': 'dock'}
        if t < 0.56:
            return {'cell': ('hand', 'r'), 'beacon': 'dock'}
        if t < 0.65:
            return {'cell': ('world', Mp), 'beacon': 'dock'}
        if t < 0.88:
            return {'cell': ('hand', 'r'), 'beacon': 'dock'}
        return {'cell': 'slot', 'beacon': 'dock'}
    c = build_clip('reload', e, keys, prop_states=states, note='physical cell swap: right hand pulls the cell from the forearm slot, stows it in the hip pouch, takes a fresh cell and seats it')
    c.event('reload_eject', 0.34)
    c.event('reload_handoff', 0.62)
    c.event('reload_insert', 0.88)
    c.event('reload_complete', 0.96)
    c.event('cancel_window_begin', 0.0)
    c.event('cancel_window_end', 0.30)
    return c


# ----------------------------------------------------------------------------- casts, channel, charge

def _cast_base(**o):
    k = relaxed(pelvis=(0.0, 0.0, -0.08), pelvis_rot=(0, 2, -6), spine=(6, -8, 0), neck=(-3, 6, 0), fl=foot_rest('l', x=0.12, y=0.04, yaw=-6), fr=foot_rest('r', x=-0.10, y=-0.06, yaw=-14),
                al=FK(flex=30, abd=6, elbow=70), ar=FK(flex=30, abd=-12, elbow=100), hl=dict(curl=0.4), hr=dict(curl=0.5))
    k.update(o)
    return k


@clip('cast_directional')
def cast_directional(e):
    keys = [
        (0.0, _cast_base()),
        (0.22, _cast_base(spine=(6, -22, 0), neck=(-3, -10, 0), pelvis_rot=(0, 2, -14), al=FK(flex=26, abd=14, elbow=60), ar=FK(flex=28, abd=-26, elbow=126, wflex=-20), hr=dict(curl=0.9))),
        (0.36, _cast_base(spine=(8, -26, 0), neck=(-3, -12, 0), pelvis_rot=(0, 3, -16), al=FK(flex=22, abd=18, elbow=56), ar=FK(flex=30, abd=-28, elbow=132, wflex=-24), hr=dict(curl=1.0))),
        (0.50, _cast_base(pelvis=(0.06, 0.0, -0.10), spine=(12, 16, 0), neck=(-4, 12, 0), pelvis_rot=(0, 5, 6), fl=foot_rest('l', x=0.24, y=0.04, yaw=-2), al=FK(flex=14, abd=26, elbow=64), ar=FK(flex=90, abd=-8, elbow=8, wflex=-58), hr=dict(curl=-0.2, spread=1.0))),
        (0.72, _cast_base(pelvis=(0.05, 0.0, -0.09), spine=(10, 12, 0), neck=(-3, 10, 0), fl=foot_rest('l', x=0.22, y=0.04), al=FK(flex=18, abd=22, elbow=66), ar=FK(flex=84, abd=-8, elbow=12, wflex=-50), hr=dict(curl=0.1, spread=0.8))),
        (1.0, _cast_base()),
    ]
    c = build_clip('cast_directional', e, keys, note='direction-targeted release: right hand winds back to the shoulder and thrusts forward palm out (upper-body layer)')
    c.event('cast_release', 12)
    c.event('cancel_window_begin', 16)
    return c


@clip('cast_ground')
def cast_ground(e):
    tgt = (0.62, -0.10, 0.03)
    def crouch(t, **o):
        return combat(pelvis=(0.10, 0.0, -0.32), pelvis_rot=(0, 16, -6), spine=(30, -10, 0), neck=(-24, 6, 0), fl=foot_rest('l', x=0.26, y=0.05), fr=foot_rest('r', x=-0.16, y=-0.08),
                      al=FK(flex=20, abd=18, elbow=60), ar=('ik', dict(target=tgt, dir=(0.6, 0.0, -0.8), palm=(0, 0, -1), elbow_hint=(0.12, -0.34, 0.42))), hr=dict(curl=0.05, spread=0.8), **o)
    keys = [
        (0.0, combat()),
        (0.24, combat(pelvis=(0.04, 0.0, -0.16), spine=(18, -14, 0), neck=(-14, 4, 0), ar=FK(flex=60, abd=-14, elbow=80), al=FK(flex=40, abd=12, elbow=70))),
        (0.46, crouch(0)),
        (0.62, crouch(0, extra=Pose().prop('ctl_hand_pose_r', 'curl', -0.4))),
        (0.80, combat(pelvis=(0.04, 0.0, -0.16), spine=(16, -12, 0), neck=(-12, 4, 0))),
        (1.0, combat()),
    ]
    c = build_clip('cast_ground', e, keys, note='crouch and place a ground-targeted cast with the right hand, looking at the target point')
    c.event('cast_release', 0.55)
    c.event('cancel_window_end', 0.45)
    c.event('control_return', 0.92)
    return c


@clip('cast_self')
def cast_self(e):
    cross = _cast_base(pelvis=(0.0, 0.0, -0.14), spine=(14, 0, 0), neck=(-10, 0, 0), pelvis_rot=(0, 4, 0), fl=foot_rest('l', x=0.06, y=0.02), fr=foot_rest('r', x=-0.06, y=-0.02),
                       al=FK(flex=88, abd=-40, elbow=132, roll=20), ar=FK(flex=90, abd=-40, elbow=134, roll=-20), hl=dict(curl=0.9), hr=dict(curl=0.9))
    burst = _cast_base(pelvis=(0.0, 0.0, -0.06), spine=(-8, 0, 0), neck=(8, 0, 0), pelvis_rot=(0, -3, 0), fl=foot_rest('l', x=0.10, y=0.10), fr=foot_rest('r', x=-0.10, y=-0.10),
                       al=FK(flex=36, abd=74, elbow=12), ar=FK(flex=36, abd=74, elbow=12), hl=dict(curl=-0.3, spread=1.0), hr=dict(curl=-0.3, spread=1.0))
    keys = [(0.0, combat()), (0.30, cross), (0.44, cross), (0.58, burst), (0.78, burst), (1.0, combat())]
    c = build_clip('cast_self', e, keys, note='self-centred emission: arms cross over the chest then open outward')
    c.event('cast_release', 0.56)
    c.event('control_return', 0.9)
    return c


def _channel_pose(shake=0.0, phase=0.0, pitch=2.0, **o):
    s1, s2 = math.sin(phase * 9.0), math.sin(phase * 7.3 + 1.0)
    k = relaxed(pelvis=(0.03, 0.0, -0.17 + 0.004 * s1), pelvis_rot=(0, 5, -6), spine=(14 + 0.8 * s2, -10, 0), neck=(-8, 4, 0),
                fl=foot_rest('l', x=0.26, y=0.06, yaw=-10), fr=foot_rest('r', x=-0.22, y=-0.09, yaw=-22),
                al=('aim', dict(yaw=0, pitch=pitch + shake * 0.8 * s1, reach=0.62, elbow_hint=None)), ar=FK(flex=52 + shake * s2, abd=8, elbow=72), hl=dict(curl=0.0, spread=0.6), hr=dict(curl=0.1, spread=0.4))
    k.update(o)
    return k


@clip('channel_start')
def channel_start(e):
    keys = [(0.0, combat()), (0.45, _channel_pose(pitch=0, pelvis=(0.0, 0.0, -0.12), al=('aim', dict(yaw=0, pitch=-10, reach=0.5)))), (1.0, _channel_pose())]
    c = build_clip('channel_start', e, keys, note='enter the sustained channel: wide braced stance, emitter arm extended, supporting arm')
    c.event('channel_sustain_begin', 0.95)
    c.event('cancel_window_begin', 0.3)
    return c


@clip('channel_loop')
def channel_loop(e):
    keys = []
    for i in range(13):
        t = i / 12
        keys.append((t, _channel_pose(shake=1.6, phase=TAU * t)))
    c = build_clip('channel_loop', e, keys, note='sustained beam emission with restrained tremble and breathing')
    return c


@clip('channel_end')
def channel_end(e):
    keys = [(0.0, _channel_pose()), (0.25, _channel_pose(pitch=10, pelvis=(0.06, 0.0, -0.15), al=('aim', dict(yaw=0, pitch=10, reach=0.66)))),
            (0.6, combat(pelvis=(0.02, 0.0, -0.12), spine=(12, -10, 0))), (1.0, combat())]
    c = build_clip('channel_end', e, keys, note='deliberate release: a small forward thrust, then the arm drops and the stance closes')
    c.event('channel_release', 0.25)
    c.event('control_return', 0.85)
    return c


@clip('channel_interrupt')
def channel_interrupt(e):
    hit = relaxed(pelvis=(-0.10, 0.02, -0.14), pelvis_rot=(4, -8, 14), spine=(-18, 20, 4), neck=(14, 16, 0), fl=foot_rest('l', x=0.02, y=0.05, roll=20), fr=foot_rest('r', x=-0.42, y=-0.10, yaw=-20, roll=10),
                  al=FKS(flex=112, abd=30, elbow=48, wflex=-30), ar=FK(flex=70, abd=24, elbow=60), hl=dict(curl=-0.2, spread=1.0), hr=dict(curl=0.2, spread=0.8))
    hit['face'] = FL.expression('pain', 0.7)
    keys = [(0.0, _channel_pose()), (0.38, hit), (0.78, combat(pelvis=(-0.06, 0.0, -0.18), spine=(18, -6, 0), neck=(6, 0, 0), fr=foot_rest('r', x=-0.30, y=-0.09, yaw=-22))), (1.0, combat())]
    c = build_clip('channel_interrupt', e, keys, note='forced interruption: the arm is knocked up and back, the body recoils and staggers')
    c.event('channel_interrupted', 0.1)
    c.event('control_return', 0.85)
    return c


def _charge_pose(shake=0.0, phase=0.0, **o):
    s1, s2 = math.sin(phase * 11.0), math.sin(phase * 8.7 + 0.7)
    k = relaxed(pelvis=(-0.03, 0.03, -0.22 + 0.006 * s1), pelvis_rot=(0, 8, -22), spine=(18 + s2 * shake, -28, 4), neck=(-8, -12, 0),
                fl=foot_rest('l', x=0.14, y=0.05, yaw=-14), fr=foot_rest('r', x=-0.22, y=-0.10, yaw=-32),
                al=FK(flex=-10 + shake * s1, abd=30, elbow=104, roll=20), ar=FK(flex=0 + shake * s2, abd=-6, elbow=116, roll=-20), hl=dict(curl=1.05), hr=dict(curl=1.1))
    k.update(o)
    return k


@clip('charge_start')
def charge_start(e):
    keys = [(0.0, combat()), (0.5, _charge_pose(shake=0.8, pelvis=(-0.02, 0.02, -0.16))), (1.0, _charge_pose(shake=1.2))]
    c = build_clip('charge_start', e, keys, note='wind-up: crouch and coil, both fists drawn back to the right hip')
    c.event('charge_full', 0.9)
    c.event('cancel_window_begin', 0.3)
    return c


@clip('charge_hold')
def charge_hold(e):
    keys = [(i / 12, _charge_pose(shake=2.0, phase=TAU * i / 12)) for i in range(13)]
    return build_clip('charge_hold', e, keys, note='held charge with tremble, breathing and a slow sway')


@clip('charge_release')
def charge_release(e):
    fwd = combat(pelvis=(0.26, 0.0, -0.30), pelvis_rot=(2, 10, 12), spine=(30, 26, -3), neck=(-14, 14, 0), fl=foot_rest('l', x=0.64, y=0.06, yaw=2, roll=-12), fr=foot_rest('r', x=-0.30, y=-0.09, yaw=-14, roll=34),
                 al=FK(flex=92, abd=8, elbow=10, wflex=-30), ar=FK(flex=88, abd=-10, elbow=14, wflex=-30), hl=dict(curl=-0.3, spread=1.0), hr=dict(curl=-0.3, spread=1.0))
    keys = [(0.0, _charge_pose(shake=2.0)), (0.34, fwd), (0.54, fwd), (0.78, combat(pelvis=(0.12, 0.0, -0.16), spine=(16, 6, 0), fl=foot_rest('l', x=0.36, y=0.04))), (1.0, combat())]
    c = build_clip('charge_release', e, keys, note='forceful release: lunge step, torso uncoils, both arms thrust forward palms open')
    c.event('charge_release', 0.28)
    c.event('foot_plant', 6, foot='l')
    c.event('control_return', 0.85)
    return c


@clip('charge_cancel')
def charge_cancel(e):
    keys = [(0.0, _charge_pose(shake=2.0)), (0.35, relaxed(pelvis=(0.0, 0.0, -0.14), pelvis_rot=(0, 4, -6), spine=(20, -6, 0), neck=(-6, 0, 0), fl=foot_rest('l', x=0.10, y=0.03), fr=foot_rest('r', x=-0.12, y=-0.06),
                                                        al=FK(flex=16, abd=-10, elbow=44), ar=FK(flex=16, abd=-10, elbow=50), hl=dict(curl=0.5), hr=dict(curl=0.5))),
            (1.0, combat())]
    c = build_clip('charge_cancel', e, keys, note='safe cancel: fists open, arms drop, a short exhale back to the ready stance')
    c.event('charge_cancel', 0.2)
    c.event('control_return', 0.8)
    return c


# ----------------------------------------------------------------------------- deploy and uplink

@clip('deploy')
def deploy(e):
    N = e['frames']
    base = combat(pelvis=(0.0, 0.0, -0.07), pelvis_rot=(0, 3, -4), spine=(8, -8, 0), neck=(-4, 0, 0), fl=foot_rest('l', x=0.08, y=0.03, yaw=-8), fr=foot_rest('r', x=-0.10, y=-0.07, yaw=-16),
                  al=FK(flex=40, abd=6, elbow=80))
    twist = dict(spine=(12, -34, 6), pelvis_rot=(0, 4, -12), neck=(-6, -16, 0))
    ev = PL.evaluate(resolve({**base, **twist}))
    Md = PL.dock_matrix(ev)
    Gi = PL.grip_matrix('beacon', 'r').inverted()
    floor_pos = Vector((0.46, -0.06, 0.0))
    Mf = PL.prop_world_matrix('beacon', floor_pos, axis=(0, 0, 1))
    Mf_hover = Matrix.Translation(Vector((0, 0, 0.16))) @ Mf
    Md_above = Matrix.Translation(Vector((0, 0, 0.12))) @ Md
    crouch = dict(pelvis=(0.10, 0.0, -0.30), pelvis_rot=(0, 14, -6), spine=(28, -8, 0), neck=(-22, 4, 0), fl=foot_rest('l', x=0.26, y=0.05), fr=foot_rest('r', x=-0.16, y=-0.09))
    def hk(M, curl=0.9, **o):
        k = {**base, **o}
        k['ar'] = ('ikmat', dict(M=M @ Gi))
        k['hr'] = dict(curl=curl, thumb=0.4)
        return k
    keys = [
        (0.0, combat()),
        (0.12, hk(Md_above, curl=0.1, **twist)),
        (0.22, hk(Md, curl=0.95, **twist)),
        (0.34, hk(Md_above, curl=0.95, **twist)),
        (0.52, hk(Mf_hover, curl=0.95, **crouch)),
        (0.64, hk(Mf, curl=0.95, **crouch)),
        (0.72, hk(Mf, curl=0.10, **crouch)),
        (0.84, hk(Mf_hover, curl=0.20, **{**crouch, 'pelvis': (0.06, 0.0, -0.18), 'spine': (18, -4, 0)})),
        (1.0, combat()),
    ]
    def states(f, ev_):
        t = f / N
        if t < 0.22:
            return {'cell': 'slot', 'beacon': 'dock'}
        if t < 0.70:
            return {'cell': 'slot', 'beacon': ('hand', 'r')}
        return {'cell': 'slot', 'beacon': ('world', Mf)}
    c = build_clip('deploy', e, keys, prop_states=states, note='take the beacon from the rear right dock, crouch and set it on the floor, release and rise')
    c.event('deploy_attach', 0.22)
    c.event('deploy_release', 0.70)
    c.event('deploy_settle', 0.86)
    c.event('control_return', 0.95)
    return c


CONSOLE_L = Vector((0.46, 0.17, 1.16))
CONSOLE_R = Vector((0.46, -0.15, 1.18))


def _uplink_pose(t_hand=1.0, wob=0.0, phase=0.0, taps=0.0, **o):
    """Both hands hovering over a virtual console at chest height (root-relative)."""
    wl = CONSOLE_L + Vector((0.02 * math.sin(phase), 0.02 * math.cos(phase), 0.008 * math.sin(2 * phase))) * wob
    wr = CONSOLE_R + Vector((0.02 * math.cos(phase + 1.0), 0.02 * math.sin(phase + 1.0), 0.008 * math.sin(2 * phase + 1))) * wob
    k = relaxed(pelvis=(0.03, 0.0, -0.08), pelvis_rot=(0, 3, 0), spine=(10, 0, 0), neck=(6, 0, 0), fl=foot_rest('l', x=0.08, y=0.06, yaw=0), fr=foot_rest('r', x=-0.08, y=-0.06, yaw=0),
                al=('ik', dict(target=tuple(wl), dir=(0.9, 0.05, -0.35), palm=(0, 0, -1), elbow_hint=(0.05, 0.36, 0.98))), ar=('ik', dict(target=tuple(wr), dir=(0.9, -0.05, -0.35), palm=(0, 0, -1), elbow_hint=(0.05, -0.36, 1.0))),
                hl=dict(curl=0.15 + 0.35 * taps, index=0.5 * taps, spread=0.4), hr=dict(curl=0.15 + 0.35 * (1 - taps), middle=0.5 * (1 - taps), spread=0.4))
    k.update(o)
    return k


@clip('uplink_start')
def uplink_start(e):
    keys = [(0.0, combat()), (0.5, _uplink_pose(wob=0.0, al=('ik', dict(target=tuple(CONSOLE_L + Vector((-0.08, 0.02, -0.1))), dir=(0.8, 0.1, -0.5), palm=(0, 0, -1), elbow_hint=(0.0, 0.36, 0.95))),
                                                ar=('ik', dict(target=tuple(CONSOLE_R + Vector((-0.08, -0.02, -0.1))), dir=(0.8, -0.1, -0.5), palm=(0, 0, -1), elbow_hint=(0.0, -0.36, 0.95))))), (1.0, _uplink_pose())]
    c = build_clip('uplink_start', e, keys, note='begin the recall gesture: both hands rise to the virtual console, head lowers to the display')
    c.event('uplink_sustain_begin', 0.95)
    c.event('cancel_window_begin', 0.2)
    return c


@clip('uplink_loop')
def uplink_loop(e):
    keys = []
    for i in range(13):
        t = i / 12
        ph = TAU * t
        keys.append((t, _uplink_pose(wob=1.0, phase=ph, taps=0.5 + 0.5 * math.sin(2 * ph), spine=(10 + 0.8 * math.sin(2 * ph), 0, 0), neck=(6 + 1.5 * math.sin(2 * ph + 1), 3 * math.sin(ph), 0))))
    c = build_clip('uplink_loop', e, keys, note='maintain the recall gesture: fingers tap and drift over the console, feet planted')
    return c


@clip('uplink_end')
def uplink_end(e):
    keys = [(0.0, _uplink_pose()), (0.30, _uplink_pose(taps=1.0, wob=0.0, pelvis=(0.03, 0.0, -0.10), neck=(10, 0, 0))), (0.55, _uplink_pose(wob=0.0, neck=(2, 0, 0))), (1.0, combat())]
    c = build_clip('uplink_end', e, keys, note='confirm tap, a short nod and the hands lower back to the ready stance')
    c.event('uplink_complete', 0.3)
    c.event('control_return', 0.85)
    return c


@clip('uplink_cancel')
def uplink_cancel(e):
    snap = combat(pelvis=(-0.05, 0.0, -0.14), pelvis_rot=(0, -4, 8), spine=(4, 14, 0), neck=(2, 18, 0), fl=foot_rest('l', x=0.02, y=0.05), fr=foot_rest('r', x=-0.26, y=-0.09),
                  al=FK(flex=52, abd=10, elbow=88, wflex=-10), ar=FK(flex=48, abd=-8, elbow=96, wflex=-10), hl=dict(curl=0.7), hr=dict(curl=0.7))
    keys = [(0.0, _uplink_pose(wob=1.0)), (0.30, snap), (0.62, combat(pelvis=(-0.02, 0.0, -0.12), neck=(-4, -14, 0))), (1.0, combat())]
    c = build_clip('uplink_cancel', e, keys, note='interrupted recall: hands snap back, a step back and a glance around before the ready stance')
    c.event('uplink_cancelled', 0.25)
    c.event('control_return', 0.8)
    return c

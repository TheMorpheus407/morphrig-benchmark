"""Maps every required clip id to its generator. Real generators live in clips_*.py and register themselves with @clip(id, ...);
ids without one fall back to placeholder_clip() so the full inventory always exists."""
import math
import clip_table as CT
from anim_lib import Clip, Pose, arm_fk, hand_pose, foot_ik, spine_pose, neck_head, lerp_pose, ease
import anim_lib as AL

GENERATORS = {}
DEG = math.pi / 180.0


def clip(*ids):
    def deco(fn):
        for i in ids:
            GENERATORS[i] = fn
        return fn
    return deco


def stand_pose():
    p = Pose()
    p.update(arm_fk('l', flex=4, abd=-20, elbow=14))
    p.update(arm_fk('r', flex=4, abd=-20, elbow=14))
    p.update(hand_pose('l', curl=0.25))
    p.update(hand_pose('r', curl=0.25))
    p.loc('ctl_pelvis', (0, 0, -0.015))
    return p


def placeholder_clip(entry):
    cid, N, loop = entry['id'], entry['frames'], entry['loop']
    root = 'root_motion' if cid in CT.ROOT_MOTION else 'in_place'
    c = Clip(cid, N, loop=loop, root=root, form=entry['form'], layer=entry['layer'], speed_cm_s=entry['speed'], note='placeholder motion')
    c.meta['placeholder'] = True
    step = 1 if N <= 40 else 3

    def env(f):
        t = f / max(N, 1)
        return math.sin(2 * math.pi * t) if loop else math.sin(math.pi * t)

    def pose_at(f):
        t = f / max(N, 1)
        e = env(f)
        p = stand_pose()
        if cid.startswith(('walk', 'run', 'sprint')):
            a = 0.18 if cid.startswith('walk') else (0.28 if cid.startswith('run') else 0.34)
            ph = 2 * math.pi * t
            for s, off in (('l', 0.0), ('r', math.pi)):
                lift = max(0.0, math.sin(ph + off))
                p.update(foot_ik(s, (a * math.cos(ph + off), 0, 0.10 * lift), roll=15 * lift))
            p.loc('ctl_pelvis', (0, 0.01 * math.sin(ph), -0.02 - 0.015 * abs(math.cos(ph))))
            p.update(spine_pose(flex=6 if not cid.startswith('walk') else 2, twist=6 * math.sin(ph)))
            p.update(arm_fk('l', flex=-25 * math.sin(ph), abd=-16, elbow=28))
            p.update(arm_fk('r', flex=25 * math.sin(ph), abd=-16, elbow=28))
        elif cid in CT.ROOT_MOTION:
            d = ease(t, 'inout5') * 2.0
            dx, dy = {'dash_f': (d, 0), 'dash_b': (-d, 0), 'dash_l': (0, d), 'dash_r': (0, -d)}[cid]
            p.loc('ctl_root', (dx, dy, 0))
            p.update(spine_pose(flex=18 * math.sin(math.pi * t)))
            p.loc('ctl_pelvis', (0, 0, -0.06 * math.sin(math.pi * t)))
        elif cid.startswith('aim_'):
            _, pitch, yaw = cid.split('_')
            yv = {'left': 60.0, 'center': 0.0, 'right': -60.0}[yaw]
            pv = {'down': -35.0, 'level': 0.0, 'up': 35.0}[pitch]
            p.update(spine_pose(flex=-pv * 0.3, twist=yv * 0.55))
            p.update(neck_head(flex=-pv * 0.3, twist=yv * 0.25))
            p.update(arm_fk('l', flex=85 + pv, abd=(yv * 0.25), elbow=10))
            p.update(arm_fk('r', flex=60 + pv * 0.8, abd=(yv * 0.2), elbow=40))
        elif cid in ('dead_front', 'dead_back'):
            sgn = 1.0 if cid == 'dead_front' else -1.0
            p.rot('ctl_root', (0, 90.0 * sgn, 0))
            p.loc('ctl_root', (0, 0, 0.12))
        elif cid.startswith('hit_'):
            d = {'hit_f': -1, 'hit_b': 1, 'hit_l': 0, 'hit_r': 0}[cid]
            side = {'hit_l': 1, 'hit_r': -1}.get(cid, 0)
            p.update(spine_pose(flex=-10 * d * e, side=8 * side * e, twist=4 * side * e))
            p.update(neck_head(flex=-14 * d * e, side=6 * side * e))
        else:
            p.update(spine_pose(flex=4 * e, twist=8 * e))
            p.update(arm_fk('l', flex=30 * e, abd=-10, elbow=30))
            p.update(arm_fk('r', flex=30 * e, abd=-10, elbow=30))
            p.loc('ctl_pelvis', (0, 0, -0.02 - 0.02 * abs(e)))
        return p
    if cid in CT.POSES:
        c.frames = 1
        c.key(0, pose_at(0))
        c.key(1, pose_at(0))
        c.meta['static'] = True
        return c
    AL.sample_clip_dense(c, pose_at, step=step)
    if loop:
        c.close_loop()
    return c


# Informational markers for loops, holds and pose entries that have no gameplay event of their own (fraction of the clip length).
DEFAULT_EVENTS = {
    'idle_relaxed': [('idle_breath', 0.25)], 'idle_combat': [('idle_breath', 0.25)], 'idle_wounded': [('idle_breath', 0.25)],
    'jump_air': [('jump_apex', 0.5)], 'fall': [('fall_loop_point', 0.0)],
    'channel_loop': [('channel_pulse', 0.25), ('channel_pulse', 0.75)], 'charge_hold': [('charge_pulse', 0.25), ('charge_pulse', 0.75)],
    'uplink_loop': [('uplink_pulse', 0.25), ('uplink_pulse', 0.75)], 'stun_loop': [('stun_sway_peak', 0.5)], 'knockup_air': [('tumble_half', 0.5)],
    'prone_front': [('breath_in', 0.25)], 'prone_back': [('breath_in', 0.25)], 'sleep_loop': [('breath_in', 0.25)],
    'dead_front': [('dead_hold', 0.0)], 'dead_back': [('dead_hold', 0.0)], 'defeat': [('defeat_slump', 0.5)],
}
for _p in ('down', 'level', 'up'):
    for _y in ('left', 'center', 'right'):
        DEFAULT_EVENTS[f'aim_{_p}_{_y}'] = [('aim_hold', 0.0)]


def make_all(table=None):
    table = table or CT.build_table()
    clips = {}
    for e in table:
        gen = GENERATORS.get(e['id'])
        c = gen(e) if gen else placeholder_clip(e)
        if not c.events:
            for name, frac in DEFAULT_EVENTS.get(e['id'], []):
                c.event(name, int(round(frac * c.frames)))
        clips[e['id']] = c
    return clips


def load_real_clips():
    import clips_locomotion  # noqa: F401  (registers generators)
    import clips_basic  # noqa: F401
    import clips_action  # noqa: F401
    import clips_reaction  # noqa: F401
    import clips_dialogue  # noqa: F401

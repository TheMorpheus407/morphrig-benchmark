"""Skinning demonstration poses (SPEC section 6): overhead reach, deep squat, crossed-arm reach, large torso twist, kneeling, planted hand
support and closed-grip interaction. They are one-frame actions `A_pt_<name>` in Operative.blend (not part of the 96 exported clips).
Render evidence: `blender -b source/Operative.blend -P source/generators/qa_pose_tests.py -- docs/skinning_pose_tests.png`."""
import math

import face_lib as FL
from anim_registry import Clip
from clips_basic import relaxed, FK
from keypose import build_clip, foot_rest

ENTRY = dict(frames=1, loop=False, form='pose', layer='pose', speed=0.0)


def _ik(target, dirn, palm, hint):
    return ('ik', dict(target=target, dir=dirn, palm=palm, elbow_hint=hint))


POSES = {
    # both arms straight overhead, chest lifted: shoulders must not collapse, armpits keep their volume
    'overhead_reach': relaxed(pelvis=(0.0, 0.0, -0.02), spine=(-8, 0, 0), neck=(-12, 0, 0),
                              al=_ik((0.02, 0.19, 1.99), (0.0, 0.0, 1.0), (0, -1, 0), (-0.10, 0.26, 1.72)),
                              ar=_ik((0.02, -0.19, 1.99), (0.0, 0.0, 1.0), (0, 1, 0), (-0.10, -0.26, 1.72)),
                              hl=dict(curl=0.0, spread=0.9), hr=dict(curl=0.0, spread=0.9), reach=False),
    # deep squat, feet flat, arms forward for balance: knees, hips and ankles fold, the boots stay planted
    'deep_squat': relaxed(pelvis=(-0.22, 0.0, -0.68), pelvis_rot=(0, 8, 0), spine=(24, 0, 0), neck=(-20, 0, 0),
                          fl=foot_rest('l', x=0.02, y=0.10, yaw=-14), fr=foot_rest('r', x=0.02, y=-0.10, yaw=14),
                          al=FK(flex=78, abd=10, elbow=14), ar=FK(flex=78, abd=10, elbow=14),
                          hl=dict(curl=0.35), hr=dict(curl=0.35), reach=False),
    # cross-body reach: each hand goes to the far side, the arms pass one above the other
    'crossed_arm_reach': relaxed(pelvis=(0.0, 0.0, -0.05), spine=(6, -16, 0), neck=(0, 8, 0),
                                 al=_ik((0.36, -0.30, 1.38), (0.5, -0.8, 0.1), (0, 0, -1), (0.10, 0.28, 1.42)),
                                 ar=_ik((0.34, 0.30, 1.16), (0.5, 0.8, 0.0), (0, 0, -1), (0.10, -0.30, 1.10)),
                                 hl=dict(curl=0.15, spread=0.4), hr=dict(curl=0.15, spread=0.4)),
    # torso twisted about 70 degrees against planted feet, arms open, head looking over the shoulder
    'torso_twist': relaxed(pelvis=(0.0, 0.0, -0.06), pelvis_rot=(0, 0, -6), spine=(4, 66, 0), neck=(0, 38, 0),
                           al=FK(flex=24, abd=84, elbow=10), ar=FK(flex=30, abd=84, elbow=10),
                           hl=dict(curl=0.1, spread=0.7), hr=dict(curl=0.1, spread=0.7), reach=False),
    # kneeling on the right knee, left foot forward, torso upright
    'kneeling': relaxed(pelvis=(-0.02, 0.0, -0.46), pelvis_rot=(0, 4, 0), spine=(10, 0, 0), neck=(-6, 0, 0),
                        fl=foot_rest('l', x=0.38, y=0.06, yaw=-6), fr=foot_rest('r', x=-0.50, y=-0.02, z=0.22, pitch=70, pole_h=0.10, pole_f=0.16),
                        al=FK(flex=52, abd=6, elbow=64), ar=FK(flex=28, abd=-4, elbow=40),
                        hl=dict(curl=0.5), hr=dict(curl=0.4), reach=False),
    # crouch with the right hand planted on the floor, the left hand on the knee
    'planted_hand': relaxed(pelvis=(-0.10, 0.0, -0.62), pelvis_rot=(0, 20, -8), spine=(46, -6, 0), neck=(-30, 6, 0),
                            fl=foot_rest('l', x=0.16, y=0.12, yaw=-10), fr=foot_rest('r', x=-0.06, y=-0.14, yaw=8),
                            al=_ik((0.26, 0.20, 0.44), (0.6, 0.2, -0.7), (0, 0.4, 0.9), (0.12, 0.36, 0.60)),
                            ar=_ik((0.32, -0.30, 0.12), (0.7, 0.0, -0.7), (0, 0, -1), (0.16, -0.40, 0.45)),
                            hl=dict(curl=0.5), hr=dict(curl=0.0, spread=0.8), reach=False),
    # closed grip around the beacon held in front of the chest (fingers wrapped, thumb over)
    'closed_grip': relaxed(pelvis=(0.0, 0.0, -0.03), spine=(4, 0, 0), neck=(6, 0, 0),
                           ar=('ik', dict(target=(0.38, -0.10, 1.20), dir=(1.0, 0.1, 0.25), palm=(0, 0.9, -0.2), elbow_hint=(0.04, -0.38, 1.05))),
                           hr=dict(curl=0.95, thumb=0.0, spread=0.0), hl=dict(curl=0.4)),
}
STATES = {'closed_grip': lambda f, ev: {'cell': 'slot', 'beacon': ('hand', 'r')}}


def build(ctl, skel):
    import pose_lib as PL
    out = {}
    for name, key in POSES.items():
        cid = 'pt_' + name
        c = build_clip(cid, ENTRY, [(0.0, key), (1.0, key)], loop=False, note=f'skinning demonstration pose ({name.replace("_", " ")})')
        c.meta['static'] = True
        c.meta['pose_test'] = True
        act = PL.finalize_clip(c, ctl, skel, STATES.get(name))
        out[cid] = act
    return out

"""Hit reactions, disables (stun / sleep / knock-up / knock-down), get-ups, deaths and respawn."""
import math
import numpy as np
from .animbuild import register
from .anim_base import (stand, ready, rotate_pose, foot_at, keys, breathe, with_face, fix_reach, rot2, interp, apply_dense, kneel,
                        foot_clear, dense_floor, extend_leg, tucked)
from .pose import floor_pass
from .pose import Pose, kneel_height

FINAL = {}        # final poses of the death clips (dead_* poses reuse them exactly)


# ------------------------------------------------------------------------------------ additive hits
def _hit(c, pitch, roll, yaw):
    """Authored on the ready pose; the runtime uses the difference to frame 0 as a local-space additive."""
    R = with_face(ready())
    peak = with_face(R.mod(spine=(R.spine[0] + pitch, R.spine[1] + yaw, roll), head=(R.head[0] - pitch * 0.75, R.head[1] - yaw * 0.5, -roll * 0.6),
                           clav_l=(R.clav_l[0] + 7.0, R.clav_l[1] + 5.0), clav_r=(R.clav_r[0] + 7.0, R.clav_r[1] + 5.0),
                           arm_l=dict(upper=(0.36, 0.44 + pitch * 0.004, -0.86), fore=(-0.36, 0.66, 0.60)),
                           arm_r=dict(upper=(0.36, -0.06 + pitch * 0.004, -1.0), fore=(-0.06, 0.94, 0.30))), expr_pain=0.75)
    over = with_face(R.mod(spine=(R.spine[0] - pitch * 0.22, R.spine[1] - yaw * 0.2, -roll * 0.2), head=(R.head[0] + pitch * 0.25, R.head[1], roll * 0.2)), expr_pain=0.3)
    keys(c, [(0, R), (2, peak), (6, over), (c.frames, R)])
    c.face(0, blink_l=0.0, blink_r=0.0)
    c.face(2, blink_l=1.0, blink_r=1.0)
    c.face(6, blink_l=0.0, blink_r=0.0)
    c.events_replace([('hit_peak', 2)])


@register('hit_f')
def hit_f(c):
    _hit(c, -15.0, 0.0, -5.0)       # struck from the front: torso driven backwards


@register('hit_b')
def hit_b(c):
    _hit(c, 17.0, 0.0, 4.0)         # struck from behind: torso thrown forwards


@register('hit_l')
def hit_l(c):
    _hit(c, 2.0, -15.0, -9.0)       # struck from the left: torso bends away to the right


@register('hit_r')
def hit_r(c):
    _hit(c, 2.0, 15.0, 9.0)


# ------------------------------------------------------------------------------------ stun
def stun_pose(sx=0.0, sy=0.0, head=(0.0, 0.0)):
    R = ready()
    p = R.mod(cog=(sx, -0.02 + sy, -0.11), cog_rot=(7.0 + sy * 60.0, -4.0, -sx * 70.0), hips=(4.0, -2.0, 0.0), spine=(20.0 + sy * 80.0, 2.0, -sx * 90.0),
              head=(24.0 + head[0], head[1], sx * 180.0), clav_l=(-3.0, 8.0), clav_r=(-3.0, 8.0),
              arm_l=dict(upper=(0.16 + sx * 1.2, 0.22 + sy * 1.5, -0.96), fore=None, bend=20.0, hint=(0.0, 1.0, 0.0), hand=(10.0, 0.0, 10.0)),
              arm_r=dict(upper=(0.18 - sx * 1.2, 0.18 + sy * 1.5, -0.96), fore=None, bend=24.0, hint=(0.0, 1.0, 0.0), hand=(10.0, 0.0, 10.0)))
    p.foot_l.update(pos=(0.165, 0.06, 0.0), yaw=14.0)
    p.foot_r.update(pos=(-0.170, -0.10, 0.0), yaw=-20.0, roll=0.0)
    p.fing_l.update(curl=0.32, thumb=0.2, spread=0.2)
    p.fing_r.update(curl=0.28, thumb=0.2, spread=0.2)
    p.look = (0.3, 1.0, 0.4)
    return with_face(p, expr_pain=0.35, blink_l=0.55, blink_r=0.6, jaw_open=0.16)


@register('stun_start')
def stun_start(c):
    R = with_face(ready())
    snap = with_face(R.mod(cog=(R.cog[0], R.cog[1] - 0.05, -0.06), cog_rot=(-6.0, -8.0, 0.0), spine=(-10.0, 4.0, 0.0), head=(-18.0, 4.0, 6.0),
                           arm_l=dict(upper=(0.55, 0.30, -0.75), fore=(0.25, 0.80, -0.20)), arm_r=dict(upper=(0.55, 0.10, -0.80), fore=(0.30, 0.75, -0.30))),
                     expr_pain=0.8, blink_l=1.0, blink_r=1.0)
    T = stun_pose()
    mid = Pose.blend(snap, T, 0.5)
    mid.foot_l = dict(R.foot_l, pos=(0.150, 0.08, 0.04), roll=0.0)
    mid.foot_r = dict(R.foot_r)
    m2 = Pose.blend(snap, T, 0.85)
    m2.foot_l = dict(T.foot_l)
    m2.foot_r = dict(R.foot_r, pos=(-0.16, -0.14, 0.04), yaw=-28.0, roll=0.0)
    keys(c, [(0, R), (3, snap), (6, mid), (10, m2), (c.frames, T)])
    c.events_replace([('stun_begin', 0), ('foot_l_contact', 8), ('foot_r_contact', 12)])


@register('stun_loop')
def stun_loop(c):
    n = c.frames
    seq = []
    for i in range(0, 9):
        a = 2 * math.pi * i / 8.0
        sx, sy = 0.030 * math.sin(a), 0.022 * math.cos(a)
        seq.append((n * i / 8.0, stun_pose(sx, sy, head=(4.0 * math.sin(2 * a), 9.0 * math.sin(a + 0.6)))))
    keys(c, seq)
    breathe(c, 2, 0.7)


@register('stun_end')
def stun_end(c):
    R = with_face(ready())
    T = stun_pose()
    a = stun_pose(head=(-14.0, 26.0)).mod(spine=(14.0, 4.0, 0.0))
    b = stun_pose(head=(-18.0, -24.0)).mod(spine=(10.0, 0.0, 0.0))
    a = with_face(a, expr_pain=0.2, blink_l=1.0, blink_r=1.0, jaw_open=0.0)
    b = with_face(b, expr_pain=0.1, blink_l=0.2, blink_r=0.2, jaw_open=0.0)
    up = Pose.blend(T, R, 0.7)
    up.foot_l = dict(T.foot_l)
    up.foot_r = dict(T.foot_r)
    s1 = R.copy()
    s1.foot_l = dict(R.foot_l, pos=(0.15, 0.085, 0.04), roll=0.0)
    s1.foot_r = dict(T.foot_r)
    s2 = R.copy()
    s2.foot_r = dict(R.foot_r, pos=(-0.16, -0.15, 0.04), roll=0.0)
    keys(c, [(0, T), (4, a), (7, b), (10, up), (13, s1), (15, s2), (c.frames, R)])
    c.events_replace([('foot_l_contact', 14), ('control_regained', 14), ('foot_r_contact', 16)])


# ------------------------------------------------------------------------------------ knock back / up
@register('knockback')
def knockback(c):
    """Shoved backwards by the host: hunched around the impact, heels dragging, then two recovery steps."""
    R = with_face(ready())
    imp = with_face(R.mod(cog=(R.cog[0], R.cog[1] - 0.06, -0.12), cog_rot=(16.0, -6.0, 0.0), spine=(24.0, 4.0, 0.0), head=(8.0, 6.0, 0.0),
                          arm_l=dict(upper=(0.40, 0.75, -0.50), fore=(0.10, 0.95, 0.20)), arm_r=dict(upper=(0.40, 0.70, -0.55), fore=(0.10, 0.95, 0.10))),
                    expr_pain=0.8, blink_l=1.0, blink_r=1.0)
    imp.foot_l.update(roll=-0.55)
    imp.foot_r.update(roll=-0.40)
    drag = with_face(R.mod(cog=(R.cog[0], R.cog[1] - 0.10, -0.20), cog_rot=(22.0, -6.0, 0.0), spine=(18.0, 4.0, 0.0), head=(-14.0, 6.0, 0.0),
                           arm_l=dict(upper=(0.60, 0.50, -0.60), fore=(0.30, 0.90, -0.10)), arm_r=dict(upper=(0.62, 0.40, -0.65), fore=(0.35, 0.88, -0.20))),
                     expr_pain=0.5)
    drag.foot_l.update(roll=-0.45)
    drag.foot_r.update(roll=-0.30)
    st1 = Pose.blend(drag, R, 0.5)
    st1.foot_l = dict(R.foot_l, pos=(0.14, 0.02, 0.07), roll=0.0, pitch=8.0)
    st1.foot_r = dict(R.foot_r, roll=-0.2)
    st2 = Pose.blend(drag, R, 0.8)
    st2.foot_l = dict(R.foot_l, roll=0.6)
    st2.foot_r = dict(R.foot_r, pos=(-0.15, -0.24, 0.07), roll=0.0, pitch=6.0)
    keys(c, [(0, R), (2, imp), (8, drag), (12, st1), (14, Pose.blend(st1, st2, 0.5).mod(foot_l=dict(R.foot_l, roll=0.8))), (16, st2), (18, R.mod(foot_r=dict(roll=0.8))), (c.frames, R)])
    c.events_replace([('knockback_begin', 0), ('foot_l_contact', 14), ('foot_r_contact', 18), ('control_regained', 20)])
    fix_reach([imp, drag, st1, st2])


def air_helpless(k=0.0):
    R = ready()
    p = R.mod(cog=(0.0, 0.0, 0.03), cog_rot=(-36.0 + 5.0 * k, -4.0, 4.0 * k), hips=(-6.0, 0.0, 0.0), spine=(-14.0 + 3.0 * k, 3.0, 0.0), head=(-16.0, 4.0, 5.0 * k),
              clav_l=(8.0, -6.0), clav_r=(8.0, -6.0),
              arm_l=dict(upper=(0.80, 0.30 + 0.10 * k, 0.45), fore=(0.60, 0.65, 0.40 - 0.2 * k), hand=(-15.0, 0.0, 10.0)),
              arm_r=dict(upper=(0.85, 0.10 - 0.10 * k, 0.30), fore=(0.70, 0.55, 0.35 + 0.2 * k), hand=(-15.0, 0.0, 10.0)))
    p.foot_l = foot_at((0.17, 0.30 + 0.05 * k, 0.42), yaw=10.0, pitch=-28.0, knee=(0.25, 1.0, 0.6))
    p.foot_r = foot_at((-0.20, 0.12 - 0.05 * k, 0.30), yaw=-14.0, pitch=-36.0, knee=(-0.25, 1.0, 0.4))
    p.fing_l.update(curl=0.2, spread=0.7, thumb=0.1)
    p.fing_r.update(curl=0.2, spread=0.7, thumb=0.1)
    p.look = (0.0, 1.0, 4.0)
    return with_face(p, expr_surprise=0.6, expr_pain=0.4, jaw_open=0.25)


@register('knockup_start')
def knockup_start(c):
    R = with_face(ready())
    hit = with_face(R.mod(cog=(R.cog[0], R.cog[1], -0.02), cog_rot=(-12.0, -6.0, 0.0), spine=(-16.0, 4.0, 0.0), head=(14.0, 4.0, 0.0),
                          arm_l=dict(upper=(0.55, 0.45, -0.70), fore=(0.40, 0.60, -0.70)), arm_r=dict(upper=(0.55, 0.35, -0.75), fore=(0.45, 0.50, -0.75))),
                    expr_surprise=0.8, jaw_open=0.3)
    hit.foot_l.update(roll=1.2)
    hit.foot_r.update(roll=1.3)
    A = air_helpless()
    mid = Pose.blend(hit, A, 0.6)
    mid.foot_l = foot_clear(0.15, 0.16, yaw=10.0, pitch=-45.0, clear=0.10, knee=(0.2, 1.0, 0.3))
    mid.foot_r = foot_clear(-0.17, -0.06, yaw=-20.0, pitch=-50.0, clear=0.08, knee=(-0.2, 1.0, 0.2))
    keys(c, [(0, R), (2, hit), (6, mid), (c.frames, A)])
    c.events_replace([('knockup_launch', 2)])
    fix_reach([hit])


@register('knockup_air')
def knockup_air(c):
    n = c.frames
    keys(c, [(0, air_helpless(0.0)), (n * 0.25, air_helpless(1.0)), (n * 0.5, air_helpless(0.0)), (n * 0.75, air_helpless(-1.0)), (n, air_helpless(0.0))])


# ------------------------------------------------------------------------------------ lying poses
def prone(k=0.0):
    """Face-down: cheek on the floor (head turned left), fore-arms beside the head, legs back."""
    p = Pose()
    p.cog = (0.0, 0.085, -0.878)
    p.cog_rot = (87.0, 0.0, 0.0)
    p.hips = (0.0, 0.0, 0.0)
    p.spine = (-7.0 - 1.5 * k, 0.0, 0.0)
    p.head = (-16.0, 62.0, 0.0)
    p.clav_l = (12.0, 4.0)
    p.clav_r = (12.0, 4.0)
    p.arm_l.update(ik=True, pos=(0.27, 0.640, 0.032), fingers=(-0.20, 0.98, 0.0), palm=(0.0, 0.0, -1.0), elbow=(0.95, -0.30, -0.10))
    p.arm_r.update(ik=True, pos=(-0.25, 0.560, 0.036), fingers=(0.15, 0.98, 0.0), palm=(0.0, 0.0, -1.0), elbow=(-0.95, -0.30, -0.10))
    p.fing_l.update(curl=0.22, thumb=0.1, spread=0.3)
    p.fing_r.update(curl=0.28, thumb=0.1, spread=0.3)
    extend_leg(p, 'l', out=0.06, direction=-1.0, ankle_z=0.058, yaw=-22.0, pitch=-172.0, knee=(0.3, 0.0, -1.0))
    extend_leg(p, 'r', out=0.04, direction=-1.0, ankle_z=0.058, yaw=18.0, pitch=-172.0, knee=(-0.3, 0.0, -1.0))
    p.look = (3.0, 0.9, 0.1)
    p.breath = 0.0
    p.blade = 0.0
    return with_face(p, blink_l=1.0, blink_r=1.0, expr_pain=0.3)


def supine(k=0.0):
    """Face-up: arms resting out to the sides, right knee slightly raised."""
    p = Pose()
    p.cog = (0.0, -0.060, -0.872)
    p.cog_rot = (-87.5, 0.0, 0.0)
    p.spine = (6.0 + 1.5 * k, 0.0, 0.0)
    p.head = (8.0, -14.0, 0.0)
    p.clav_l = (0.0, -6.0)
    p.clav_r = (0.0, -6.0)
    p.arm_l.update(ik=True, pos=(0.420, -0.300, 0.040), fingers=(0.55, 0.83, 0.0), palm=(0.0, 0.0, -1.0), elbow=(0.90, -0.40, -0.15))
    p.arm_r.update(ik=True, pos=(-0.400, -0.250, 0.045), fingers=(-0.60, 0.80, 0.0), palm=(0.0, 0.0, -1.0), elbow=(-0.90, -0.40, -0.15))
    p.fing_l.update(curl=0.35, thumb=0.2, spread=0.2)
    p.fing_r.update(curl=0.30, thumb=0.2, spread=0.2)
    extend_leg(p, 'l', out=0.07, direction=1.0, ankle_z=0.082, yaw=22.0, pitch=80.0, knee=(0.15, 0.0, 1.0))
    p.foot_r = foot_at((-0.170, 0.640, 0.105), yaw=-16.0, pitch=38.0, knee=(-0.20, 0.0, 1.0))
    p.look = (-1.0, -0.6, 5.0)
    p.breath = 0.0
    p.blade = 0.0
    return with_face(p, blink_l=1.0, blink_r=1.0, expr_pain=0.3)


@register('prone_front')
def prone_front(c):
    n = c.frames
    a = prone()
    b = prone(1.0).mod(head=(-14.0, 60.0, 0.0))
    b.fing_l.update(index=0.45, middle=0.40)
    dense_floor(c, [(0, a), (n * 0.5, b), (n, a)], breath=lambda f: 0.8 * math.sin(2 * math.pi * 2 * f / n))


@register('prone_back')
def prone_back(c):
    n = c.frames
    a = supine()
    b = supine(1.0).mod(head=(6.0, -18.0, 0.0))
    b.fing_r.update(index=0.50, middle=0.45)
    dense_floor(c, [(0, a), (n * 0.5, b), (n, a)], breath=lambda f: 0.8 * math.sin(2 * math.pi * 2 * f / n))


# ------------------------------------------------------------------------------------ knock downs
def _fall_back_seq(R, final, f_imp, f_set, n, pain=0.8):
    """Common key poses for falling onto the back (knock-down and front-impact death)."""
    hit = with_face(R.mod(cog=(R.cog[0], R.cog[1] - 0.06, -0.07), cog_rot=(-14.0, -6.0, 0.0), spine=(-14.0, 4.0, 0.0), head=(16.0, 4.0, 0.0),
                          arm_l=dict(upper=(0.50, 0.70, -0.30), fore=(0.20, 0.95, 0.20)), arm_r=dict(upper=(0.50, 0.65, -0.35), fore=(0.25, 0.92, 0.15))),
                    expr_pain=pain, blink_l=1.0, blink_r=1.0, jaw_open=0.3)
    hit.foot_l.update(roll=-0.4)
    hit.foot_r.update(roll=0.0)
    tip = with_face(R.mod(cog=(0.0, -0.20, -0.30), cog_rot=(-42.0, -3.0, 0.0), spine=(8.0, 2.0, 0.0), head=(22.0, 2.0, 0.0),
                          arm_l=dict(upper=(0.70, 0.60, 0.20), fore=(0.50, 0.80, 0.30)), arm_r=dict(upper=(0.72, 0.55, 0.15), fore=(0.55, 0.78, 0.25))),
                    expr_pain=pain * 0.7, expr_surprise=0.5, jaw_open=0.35)
    tip.foot_l = dict(R.foot_l, pos=(0.14, 0.16, 0.0), yaw=10.0, roll=-0.9, pitch=0.0)
    tip.foot_r = dict(R.foot_r, pos=(-0.15, 0.00, 0.0), yaw=-20.0, roll=-0.8, pitch=0.0)
    sit = final.copy()
    sit.cog = (0.0, final.cog[1] - 0.02, final.cog[2] + 0.02)
    sit.cog_rot = (-58.0, 0.0, 0.0)
    sit.spine = (22.0, 0.0, 0.0)
    sit.head = (26.0, 0.0, 0.0)
    sit.foot_l = foot_at((0.16, 0.55, 0.33), yaw=14.0, pitch=30.0, knee=(0.15, 0.2, 1.0))
    sit.foot_r = foot_at((-0.17, 0.48, 0.40), yaw=-14.0, pitch=20.0, knee=(-0.2, 0.2, 1.0))
    sit.arm_l.update(ik=True, pos=(0.36, -0.12, 0.30), fingers=(0.5, 0.6, -0.6), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.4, 0.1))
    sit.arm_r.update(ik=True, pos=(-0.36, -0.10, 0.32), fingers=(-0.5, 0.6, -0.6), palm=(0.0, 0.3, -0.95), elbow=(-0.9, -0.4, 0.1))
    sit = with_face(sit, expr_pain=pain, blink_l=1.0, blink_r=1.0, jaw_open=0.3)
    flat = final.copy()
    flat.spine = (final.spine[0] - 4.0, 0.0, 0.0)
    flat.head = (-6.0, 0.0, 0.0)
    flat.foot_l = foot_at((0.16, 0.72, 0.20), yaw=18.0, pitch=70.0, knee=(0.15, 0.0, 1.0))
    flat.foot_r = foot_at((-0.17, 0.62, 0.24), yaw=-14.0, pitch=50.0, knee=(-0.2, 0.0, 1.0))
    flat = with_face(flat, expr_pain=pain, blink_l=1.0, blink_r=1.0)
    # the IK arms need to exist from the first key on: express the standing arms as IK targets near the chest
    for p in (hit, tip):
        p.arm_l.update(ik=True, pos=p.chest_point((0.26, 0.40, 0.02)), fingers=p.chest_dir((0.2, 0.9, 0.4)), palm=p.chest_dir((0.0, 0.3, -0.95)), elbow=(0.8, -0.5, -0.3))
        p.arm_r.update(ik=True, pos=p.chest_point((-0.28, 0.38, -0.02)), fingers=p.chest_dir((-0.2, 0.9, 0.4)), palm=p.chest_dir((0.0, 0.3, -0.95)), elbow=(-0.8, -0.5, -0.3))
    tip.arm_l['pos'] = tip.chest_point((0.34, 0.36, 0.22))
    tip.arm_r['pos'] = tip.chest_point((-0.36, 0.34, 0.18))
    return hit, tip, sit, flat


def _ik_ready(R):
    p = R.copy()
    p.arm_l.update(ik=True, pos=R.chest_point((0.13, 0.33, 0.05)), fingers=R.chest_dir((-0.42, 0.62, 0.66)), palm=R.chest_dir((-0.8, -0.2, -0.5)), elbow=(0.6, -0.5, -0.6))
    p.arm_r.update(ik=True, pos=R.chest_point((-0.30, 0.30, -0.24)), fingers=R.chest_dir((0.10, 0.92, 0.36)), palm=R.chest_dir((0.5, 0.0, -0.85)), elbow=(-0.6, -0.6, -0.5))
    return p


@register('knockdown_back')
def knockdown_back(c):
    n = c.frames
    R = _ik_ready(with_face(ready()))
    final = supine()
    hit, tip, sit, flat = _fall_back_seq(R, final, 20, 32, n)
    fix_reach([hit, tip])
    dense_floor(c, [(0, R), (3, hit), (11, tip), (20, sit), (25, flat), (32, final), (n, final)])
    c.events_replace([('ground_impact', 20), ('settled', 32)])


@register('knockdown_front')
def knockdown_front(c):
    n = c.frames
    R = _ik_ready(with_face(ready()))
    final = prone()
    stumble = with_face(R.mod(cog=(0.0, 0.08, -0.10), cog_rot=(26.0, -4.0, 0.0), spine=(16.0, 2.0, 0.0), head=(-20.0, 4.0, 0.0)), expr_pain=0.8, blink_l=1.0, blink_r=1.0)
    stumble.arm_l.update(pos=stumble.chest_point((0.28, 0.48, 0.10)), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.4, 0.0))
    stumble.arm_r.update(pos=stumble.chest_point((-0.28, 0.46, 0.05)), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(-0.9, -0.4, 0.0))
    stumble.foot_l.update(roll=0.9)
    stumble.foot_r.update(roll=1.2)
    knees = with_face(final.mod(cog=(0.0, 0.02, -0.56), cog_rot=(48.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0), head=(-34.0, 10.0, 0.0)), expr_pain=0.8, blink_l=1.0, blink_r=1.0)
    knees.foot_l = tucked(0.150, -0.44, yaw=-6.0, pitch=-75.0, knee=(0.10, 1.0, -0.5))
    knees.foot_r = tucked(-0.135, -0.47, yaw=6.0, pitch=-75.0, knee=(-0.10, 1.0, -0.5))
    kneel_height(knees, 'l', knee_z=0.062)
    knees.arm_l.update(pos=(0.26, 0.56, 0.20), fingers=(-0.1, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.3, 0.3))
    knees.arm_r.update(pos=(-0.25, 0.50, 0.22), fingers=(0.1, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(-0.9, -0.3, 0.3))
    hands = with_face(final.mod(cog=(0.0, 0.06, -0.74), cog_rot=(70.0, 0.0, 0.0), spine=(-2.0, 0.0, 0.0), head=(-26.0, 30.0, 0.0)), expr_pain=0.9, blink_l=1.0, blink_r=1.0)
    hands.foot_l = foot_at((0.150, -0.62, 0.090), yaw=-14.0, pitch=-140.0, knee=(0.10, 0.2, -1.0))
    hands.foot_r = foot_at((-0.130, -0.64, 0.090), yaw=12.0, pitch=-140.0, knee=(-0.10, 0.2, -1.0))
    bounce = final.mod(spine=(-12.0, 0.0, 0.0), head=(-22.0, 50.0, 0.0))
    fix_reach([stumble])
    dense_floor(c, [(0, R), (5, stumble), (13, knees), (17, hands), (20, final.mod(spine=(-3.0, 0.0, 0.0), head=(-6.0, 40.0, 0.0))), (24, bounce), (32, final), (n, final)])
    c.events_replace([('ground_impact', 20), ('settled', 32)])


# ------------------------------------------------------------------------------------ get ups
@register('getup_front')
def getup_front(c):
    n = c.frames
    PF = prone()
    R = _ik_ready(with_face(ready()))
    plant = with_face(PF.mod(head=(-24.0, 20.0, 0.0), spine=(-10.0, 0.0, 0.0)), expr_pain=0.4, blink_l=0.3, blink_r=0.3)
    plant.arm_l.update(pos=(0.235, 0.455, 0.030), fingers=(-0.10, 1.0, 0.0), elbow=(0.80, -0.45, 0.40))
    plant.arm_r.update(pos=(-0.235, 0.445, 0.032), fingers=(0.10, 1.0, 0.0), elbow=(-0.80, -0.45, 0.40))
    plant.foot_l = tucked(0.150, -0.720, yaw=-8.0, pitch=-78.0, knee=(0.10, 0.2, -1.0))
    plant.foot_r = tucked(-0.130, -0.735, yaw=8.0, pitch=-78.0, knee=(-0.10, 0.2, -1.0))
    push = with_face(plant.mod(cog=(0.0, 0.03, -0.66), cog_rot=(66.0, 0.0, 0.0), spine=(-6.0, 0.0, 0.0), head=(-30.0, 6.0, 0.0), look=(0.0, 3.0, 0.4)), expr_focus=0.6, expr_pain=0.2)
    push.foot_l = tucked(0.150, -0.560, yaw=-6.0, pitch=-76.0, knee=(0.10, 1.0, -0.6))
    push.foot_r = tucked(-0.130, -0.575, yaw=6.0, pitch=-76.0, knee=(-0.10, 1.0, -0.6))
    kneel_height(push, 'l', knee_z=0.062)
    fours = with_face(plant.mod(cog=(0.0, -0.06, -0.52), cog_rot=(74.0, 0.0, 0.0), spine=(-4.0, 0.0, 0.0), head=(-36.0, 0.0, 0.0), look=(0.0, 4.0, 0.9)), expr_focus=0.7)
    fours.foot_l = tucked(0.150, -0.545, yaw=-6.0, pitch=-76.0, knee=(0.10, 1.0, -0.6))
    fours.foot_r = tucked(-0.130, -0.560, yaw=6.0, pitch=-76.0, knee=(-0.10, 1.0, -0.6))
    kneel_height(fours, 'l', knee_z=0.062)
    lunge = kneel(R, knee='l', lean=40.0, back=0.32)
    lunge.foot_r = dict(R.foot_r, pos=(-0.150, 0.06, 0.0), yaw=-10.0, roll=0.0)
    lunge = kneel(lunge.mod(foot_r=dict(pos=(-0.150, 0.06, 0.0), yaw=-10.0, roll=0.0)), knee='l', lean=40.0, back=0.30)
    lunge.arm_l.update(ik=True, pos=(0.24, 0.30, 0.20), fingers=(0.0, 0.8, -0.6), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.3, 0.3))
    lunge.arm_r.update(ik=True, pos=lunge.chest_point((-0.24, 0.26, -0.38)), fingers=(0.0, 0.8, -0.6), palm=(0.0, 0.3, -0.95), elbow=(-0.8, -0.5, 0.0))
    lunge = with_face(lunge, expr_focus=0.7)
    swing = Pose.blend(fours, lunge, 0.5)
    swing.foot_r = foot_clear(-0.150, -0.22, yaw=-6.0, pitch=-40.0, clear=0.04, knee=(-0.2, 1.0, 0.2))
    swing.foot_l = dict(fours.foot_l)
    swing.arm_l['pos'] = (0.24, 0.42, 0.10)
    swing.arm_r['pos'] = (-0.24, 0.40, 0.14)
    rise = Pose.blend(lunge, R, 0.6)
    rise.foot_r = dict(lunge.foot_r)
    rise.foot_l = foot_clear(0.135, -0.12, yaw=8.0, pitch=-35.0, clear=0.04, knee=(0.1, 1.0, 0.0))
    st = R.copy()
    st.foot_r = dict(lunge.foot_r)
    st.cog = (R.cog[0], R.cog[1] + 0.04, R.cog[2] - 0.04)
    st2 = R.copy()
    st2.foot_r = dict(R.foot_r, pos=(-0.150, -0.06, 0.07), roll=0.0, pitch=-8.0)
    fix_reach([rise, st, st2])
    dense_floor(c, [(0, PF), (10, plant), (17, push), (24, fours), (28, swing), (31, lunge), (36, lunge.mod(head=(-8.0, 0.0, 0.0))),
                    (40, rise), (43, st), (47, st2), (50, R), (n, R)])
    c.events_replace([('hand_plant', 10), ('foot_r_contact', 30), ('foot_l_contact', 42), ('control_regained', 48), ('foot_r_contact', 49)])


@register('getup_back')
def getup_back(c):
    n = c.frames
    PB = supine()
    R = _ik_ready(with_face(ready()))
    curl = with_face(PB.mod(cog=(0.0, -0.05, -0.868), cog_rot=(-70.0, 0.0, 0.0), spine=(26.0, 0.0, 0.0), head=(22.0, 0.0, 0.0), look=(0.0, 3.0, 1.0)), expr_pain=0.4, expr_focus=0.4)
    curl.arm_l.update(pos=(0.300, -0.300, 0.032), fingers=(0.30, -0.95, 0.0), elbow=(0.6, -0.8, 0.3))
    curl.arm_r.update(pos=(-0.300, -0.280, 0.036), fingers=(-0.30, -0.95, 0.0), elbow=(-0.6, -0.8, 0.3))
    curl.foot_l = foot_at((0.160, 0.560, 0.098), yaw=14.0, pitch=0.0, knee=(0.15, 0.0, 1.0))
    curl.foot_r = foot_at((-0.170, 0.500, 0.098), yaw=-14.0, pitch=0.0, knee=(-0.2, 0.0, 1.0))
    sit = with_face(curl.mod(cog=(0.0, -0.02, -0.860), cog_rot=(-22.0, 0.0, 0.0), spine=(22.0, 0.0, 0.0), head=(8.0, 0.0, 0.0), look=(0.0, 4.0, 1.2)), expr_focus=0.6)
    sit.foot_l = foot_at((0.165, 0.440, 0.098), yaw=14.0, pitch=0.0, knee=(0.2, 0.0, 1.0))
    sit.foot_r = foot_at((-0.175, 0.400, 0.098), yaw=-14.0, pitch=0.0, knee=(-0.2, 0.0, 1.0))
    sit.arm_l.update(pos=(0.300, -0.240, 0.032), fingers=(0.40, -0.90, 0.0), elbow=(0.7, -0.7, 0.3))
    sit.arm_r.update(pos=(-0.290, -0.200, 0.036), fingers=(-0.40, -0.90, 0.0), elbow=(-0.7, -0.7, 0.3))
    rock = with_face(R.mod(cog=(0.0, 0.22, -0.55), cog_rot=(34.0, 0.0, 0.0), hips=(10.0, 0.0, 0.0), spine=(18.0, 0.0, 0.0), head=(-20.0, 0.0, 0.0), look=(0.0, 4.0, 1.0)), expr_focus=0.7)
    rock.foot_l = foot_at((0.165, 0.360, 0.098), yaw=14.0, pitch=0.0, knee=(0.25, 1.0, 0.4))
    rock.foot_r = foot_at((-0.175, 0.320, 0.098), yaw=-14.0, pitch=0.0, knee=(-0.25, 1.0, 0.4))
    rock.arm_l.update(ik=True, pos=(0.30, 0.50, 0.40), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.3, 0.2))
    rock.arm_r.update(ik=True, pos=(-0.30, 0.48, 0.40), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(-0.9, -0.3, 0.2))
    squat = rock.mod(cog=(0.0, 0.30, -0.42), cog_rot=(28.0, 0.0, 0.0))
    squat.arm_l['pos'] = (0.28, 0.62, 0.62)
    squat.arm_r['pos'] = (-0.28, 0.60, 0.60)
    up = Pose.blend(squat, R, 0.6)
    up.foot_l = dict(rock.foot_l)
    up.foot_r = dict(rock.foot_r)
    up.cog = (0.0, 0.30, -0.16)
    # the feet ended ~0.35 m ahead of the root: two small steps bring the stance back under the capsule
    s1 = R.copy()
    s1.cog = (R.cog[0], 0.16, -0.10)
    s1.foot_l = dict(rock.foot_l)
    s1.foot_r = foot_clear(-0.160, 0.06, yaw=-25.0, pitch=-10.0, clear=0.05)
    s2 = R.copy()
    s2.cog = (R.cog[0], 0.03, -0.09)
    s2.foot_r = dict(R.foot_r)
    s2.foot_l = foot_clear(0.140, 0.22, yaw=12.0, pitch=-10.0, clear=0.05)
    fix_reach([rock, squat, up, s1, s2])
    lean = sit.mod(cog=(0.0, 0.02, -0.855), cog_rot=(-4.0, 0.0, 0.0), spine=(30.0, 0.0, 0.0))
    lean.arm_l.update(pos=(0.30, 0.20, 0.30), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(0.9, -0.3, 0.2))
    lean.arm_r.update(pos=(-0.30, 0.18, 0.30), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(-0.9, -0.3, 0.2))
    mid = R.mod(cog=(R.cog[0], 0.10, -0.09))
    mid.foot_l = dict(rock.foot_l)
    mid.foot_r = dict(R.foot_r)
    dense_floor(c, [(0, PB), (7, curl), (12, curl.mod(cog=(0.0, -0.05, -0.866), cog_rot=(-58.0, 0.0, 0.0))), (20, sit), (27, lean),
                    (34, rock), (39, squat), (45, up), (49, s1), (52, mid), (55, s2), (58, R), (n, R)])
    c.events_replace([('hand_plant', 12), ('foot_l_contact', 34), ('foot_r_contact', 34), ('foot_r_contact', 51), ('control_regained', 54), ('foot_l_contact', 57)])


# ------------------------------------------------------------------------------------ sleep
def sleep_pose(k=0.0):
    """Kneeling, sitting back on the heels, slumped forward with the chin on the chest."""
    p = Pose()
    p.cog = (0.0, -0.10, -0.700)
    p.cog_rot = (8.0 + 1.5 * k, 0.0, 2.0)
    p.hips = (-6.0, 0.0, 0.0)
    p.spine = (40.0 + 3.0 * k, 0.0, 3.0)
    p.head = (34.0 + 4.0 * k, -8.0, 6.0)
    p.clav_l = (-4.0, 12.0)
    p.clav_r = (-4.0, 12.0)
    p.foot_l = tucked(0.125, -0.265, yaw=-6.0, pitch=-76.0, knee=(0.16, 1.0, -0.5))
    p.foot_r = tucked(-0.125, -0.265, yaw=6.0, pitch=-76.0, knee=(-0.16, 1.0, -0.5))
    kneel_height(p, 'l', knee_z=0.062)
    p.arm_l.update(ik=True, pos=(0.150, 0.175, 0.305), fingers=(-0.25, 0.90, -0.35), palm=(0.0, 0.25, -0.97), elbow=(0.85, -0.45, -0.25))
    p.arm_r.update(ik=True, pos=(-0.155, 0.165, 0.310), fingers=(0.25, 0.90, -0.35), palm=(0.0, 0.25, -0.97), elbow=(-0.85, -0.45, -0.25))
    p.fing_l.update(curl=0.35, thumb=0.2)
    p.fing_r.update(curl=0.30, thumb=0.2)
    p.look = (0.0, 0.6, 0.2)
    p.breath = 0.0
    p.blade = 0.0
    return with_face(p, blink_l=1.0, blink_r=1.0, jaw_open=0.08)


@register('sleep_start')
def sleep_start(c):
    n = c.frames
    R = _ik_ready(with_face(ready()))
    SL = sleep_pose()
    droop = with_face(R.mod(cog=(R.cog[0], R.cog[1], -0.10), spine=(16.0, 4.0, 2.0), head=(20.0, 4.0, 6.0)), blink_l=0.75, blink_r=0.8)
    droop.arm_l.update(pos=droop.chest_point((0.22, 0.22, -0.36)), fingers=(0.0, 0.5, -0.86), palm=(-0.9, 0.0, -0.3), elbow=(0.7, -0.6, -0.3))
    droop.arm_r.update(pos=droop.chest_point((-0.24, 0.20, -0.38)), fingers=(0.0, 0.5, -0.86), palm=(0.9, 0.0, -0.3), elbow=(-0.7, -0.6, -0.3))
    k1 = kneel(R, knee='r', lean=14.0, back=0.30)
    k1 = with_face(k1, blink_l=0.9, blink_r=0.9)
    k1.arm_l.update(ik=True, pos=k1.chest_point((0.22, 0.20, -0.40)), fingers=(0.0, 0.5, -0.86), palm=(-0.9, 0.0, -0.3), elbow=(0.7, -0.6, -0.3))
    k1.arm_r.update(ik=True, pos=k1.chest_point((-0.24, 0.18, -0.42)), fingers=(0.0, 0.5, -0.86), palm=(0.9, 0.0, -0.3), elbow=(-0.7, -0.6, -0.3))
    # both knees down, still upright
    k2 = SL.mod(cog=(0.0, SL.cog[1] + 0.06, SL.cog[2]), cog_rot=(4.0, 0.0, 0.0), spine=(14.0, 0.0, 0.0), head=(18.0, 0.0, 4.0))
    k2.foot_l = dict(SL.foot_l)
    k2.foot_r = dict(k1.foot_r)
    kneel_height(k2, 'r', knee_z=0.062)
    k2.arm_l.update(pos=k2.chest_point((0.20, 0.20, -0.40)))
    k2.arm_r.update(pos=k2.chest_point((-0.22, 0.18, -0.42)))
    swing = Pose.blend(k1, k2, 0.5)
    swing.foot_r = dict(k1.foot_r)
    swing.foot_l = foot_clear(0.130, -0.10, yaw=4.0, pitch=-40.0, clear=0.04, knee=(0.1, 1.0, 0.0))
    back = SL.mod(spine=(20.0, 0.0, 0.0), head=(14.0, 0.0, 4.0))
    drop = Pose.blend(droop, k1, 0.5)
    drop.foot_l = dict(R.foot_l)
    drop.foot_r = foot_clear(-0.150, -0.32, yaw=-20.0, pitch=-45.0, clear=0.03, knee=(-0.1, 1.0, -0.2))
    fix_reach([droop, drop, swing])
    k3 = k2.copy()
    k3.foot_r = dict(SL.foot_r)
    kneel_height(k3, 'l', knee_z=0.062)
    sw2 = Pose.blend(k2, k3, 0.5)
    sw2.foot_l = dict(SL.foot_l)
    sw2.foot_r = foot_clear(-0.130, -0.30, yaw=4.0, pitch=-70.0, clear=0.03, knee=(-0.1, 1.0, -0.3))
    dense_floor(c, [(0, R), (8, droop), (14, drop), (19, k1), (23, swing), (26, k2), (29, sw2), (31, k3), (36, back), (40, SL), (n, SL)],
                breath=lambda f: -0.6 * math.sin(math.pi * f / n))
    c.events_replace([('sleep_begin', 0), ('settled', 40)])


@register('sleep_loop')
def sleep_loop(c):
    n = c.frames
    a = sleep_pose(0.0)
    b = sleep_pose(1.0)
    j = sleep_pose(-0.6)
    dense_floor(c, [(0, a), (30, b), (56, sleep_pose(1.3)), (62, j), (74, sleep_pose(0.3)), (n, a)], breath=lambda f: 0.9 * math.sin(2 * math.pi * 2 * f / n))


@register('sleep_end')
def sleep_end(c):
    n = c.frames
    SL = sleep_pose()
    R = _ik_ready(with_face(ready()))
    wake = with_face(SL.mod(spine=(14.0, 0.0, 0.0), head=(-14.0, 0.0, 0.0), look=(0.0, 6.0, 1.3)), expr_surprise=0.6)
    lookl = with_face(wake.mod(head=(-10.0, 34.0, 0.0), spine=(12.0, 8.0, 0.0)), expr_focus=0.5)
    k1 = kneel(R, knee='r', lean=16.0, back=0.30)
    k1.arm_l.update(ik=True, pos=k1.chest_point((0.22, 0.24, -0.34)), fingers=(0.0, 0.7, -0.7), palm=(-0.9, 0.0, -0.3), elbow=(0.7, -0.6, -0.3))
    k1.arm_r.update(ik=True, pos=k1.chest_point((-0.24, 0.24, -0.34)), fingers=(0.0, 0.7, -0.7), palm=(0.9, 0.0, -0.3), elbow=(-0.7, -0.6, -0.3))
    k1 = with_face(k1, expr_focus=0.6)
    rise0 = SL.mod(cog=(0.0, SL.cog[1] + 0.06, SL.cog[2]), cog_rot=(4.0, 0.0, 0.0), spine=(12.0, 0.0, 0.0), head=(-8.0, 10.0, 0.0), look=(0.0, 6.0, 1.3))
    rise0.foot_l = dict(SL.foot_l)
    rise0.foot_r = dict(SL.foot_r)
    kneel_height(rise0, 'l', knee_z=0.062)
    rise0.arm_l.update(pos=rise0.chest_point((0.20, 0.22, -0.38)))
    rise0.arm_r.update(pos=rise0.chest_point((-0.22, 0.20, -0.40)))
    rise0 = with_face(rise0, expr_focus=0.5)
    swing = Pose.blend(rise0, k1, 0.5)
    swing.foot_r = dict(k1.foot_r)
    swing.foot_l = foot_clear(0.130, -0.08, yaw=6.0, pitch=-35.0, clear=0.04, knee=(0.1, 1.0, 0.1))
    up = Pose.blend(k1, R, 0.6)
    up.foot_l = dict(R.foot_l)
    up.foot_r = foot_clear(-0.150, -0.28, yaw=-30.0, pitch=-35.0, clear=0.03, knee=(-0.1, 1.0, -0.1))
    fix_reach([swing, up])
    swing.foot_r = dict(SL.foot_r)
    kk = k1.copy()
    kk.foot_r = dict(SL.foot_r)
    kneel_height(kk, 'r', knee_z=0.062)
    dense_floor(c, [(0, SL), (5, wake), (10, lookl), (15, rise0), (19, swing), (22, kk), (27, up), (31, R.mod(foot_r=dict(roll=0.6))), (n, R)],
                breath=lambda f: 0.8 * math.sin(math.pi * f / n))
    c.events_replace([('foot_l_contact', 21), ('foot_r_contact', 30), ('control_regained', 30)])


# ------------------------------------------------------------------------------------ deaths
def dead_front_pose():
    """Front impact -> on the back: left hand on the abdomen, right arm thrown above the head, right knee fallen out."""
    p = supine()
    p.head = (10.0, 34.0, 4.0)
    p.spine = (4.0, -6.0, 0.0)
    p.arm_l.update(pos=(0.060, -0.175, 0.215), fingers=(-0.85, 0.35, -0.40), palm=(0.0, 0.25, -0.97), elbow=(0.90, 0.10, -0.40))
    p.arm_r.update(pos=(-0.300, -0.760, 0.045), fingers=(-0.30, -0.95, 0.0), palm=(0.0, 0.0, 1.0), elbow=(-0.95, 0.0, -0.20))
    p.fing_l.update(curl=0.40, thumb=0.25)
    p.fing_r.update(curl=0.55, thumb=0.35)
    p.foot_l = foot_at((0.150, 0.775, 0.070), yaw=34.0, pitch=74.0, knee=(0.30, 0.0, 1.0))
    p.foot_r = foot_at((-0.330, 0.480, 0.075), yaw=-62.0, pitch=20.0, lean=-50.0, knee=(-1.0, 0.25, 0.30))
    return with_face(p, blink_l=1.0, blink_r=1.0, jaw_open=0.22)


def dead_back_pose():
    """Back impact -> face down: right arm caught under the body, left arm stretched ahead, left knee drawn out."""
    p = prone()
    p.head = (-10.0, -58.0, 0.0)
    p.spine = (-4.0, 0.0, -4.0)
    p.cog_rot = (87.0, 0.0, -6.0)
    p.arm_l.update(pos=(0.200, 0.980, 0.032), fingers=(0.10, 0.99, 0.0), palm=(0.0, 0.0, -1.0), elbow=(0.90, 0.20, -0.10))
    p.arm_r.update(pos=(-0.040, 0.250, 0.050), fingers=(0.95, -0.30, 0.0), palm=(0.0, 0.0, 1.0), elbow=(-0.85, -0.50, -0.05))
    p.fing_l.update(curl=0.30, thumb=0.2, spread=0.4)
    p.fing_r.update(curl=0.55, thumb=0.3)
    p.foot_l = foot_at((0.400, -0.430, 0.060), yaw=-70.0, pitch=-172.0, knee=(1.0, 0.45, -0.20))
    p.foot_r = foot_at((-0.120, -0.760, 0.058), yaw=26.0, pitch=-172.0, knee=(-0.10, 0.0, -1.0))
    return with_face(p, blink_l=1.0, blink_r=1.0, jaw_open=0.15)


@register('death_front')
def death_front(c):
    n = c.frames
    R = _ik_ready(with_face(ready()))
    final = dead_front_pose()
    FINAL['death_front'] = final
    hit, tip, sit, flat = _fall_back_seq(R, final, 30, 54, n, pain=1.0)
    stag = with_face(R.mod(cog=(R.cog[0] - 0.02, R.cog[1] - 0.12, -0.10), cog_rot=(-8.0, -10.0, -3.0), spine=(6.0, 2.0, -4.0), head=(18.0, 0.0, 8.0)), expr_pain=1.0, blink_l=1.0, blink_r=1.0, jaw_open=0.35)
    stag.foot_l = dict(R.foot_l, roll=-0.3)
    stag.foot_r = dict(R.foot_r, pos=(-0.17, -0.36, 0.0), yaw=-30.0, roll=0.0)
    stag.arm_r.update(pos=stag.chest_point((-0.06, 0.150, 0.02)), fingers=stag.chest_dir((0.90, 0.20, 0.35)), palm=stag.chest_dir((0.0, -1.0, 0.0)), elbow=(-0.8, -0.3, -0.5))
    stag.arm_l.update(pos=stag.chest_point((0.42, 0.20, -0.10)), fingers=(0.5, 0.5, -0.7), palm=(0.0, 0.3, -0.95), elbow=(0.8, -0.5, -0.3))
    stag.fing_r.update(curl=0.5, thumb=0.3, spread=0.3)
    step = Pose.blend(hit, stag, 0.5)
    step.foot_l = dict(R.foot_l, roll=-0.3)
    step.foot_r = foot_clear(-0.16, -0.27, yaw=-34.0, pitch=10.0, clear=0.04)
    step.arm_r.update(pos=step.chest_point((-0.14, 0.22, 0.0)))
    buckle = with_face(stag.mod(cog=(-0.01, -0.22, -0.30), cog_rot=(-30.0, -4.0, 0.0), spine=(10.0, 0.0, -2.0), head=(26.0, 6.0, 8.0)), expr_pain=0.9, blink_l=1.0, blink_r=1.0, jaw_open=0.3)
    buckle.arm_r.update(pos=buckle.chest_point((-0.06, 0.150, 0.0)), fingers=buckle.chest_dir((0.90, 0.20, 0.35)), palm=buckle.chest_dir((0.0, -1.0, 0.0)))
    buckle.arm_l.update(pos=buckle.chest_point((0.50, 0.10, 0.10)), fingers=(0.6, 0.3, -0.7), palm=(0.0, 0.3, -0.95))
    buckle.foot_l = dict(R.foot_l, roll=-0.9)
    buckle.foot_r = dict(stag.foot_r, roll=-0.6)
    sit.arm_r.update(pos=(-0.34, -0.30, 0.34), fingers=(-0.4, -0.5, 0.76), palm=(0.0, 0.3, 0.95), elbow=(-0.9, 0.0, -0.3))
    sit.arm_l.update(pos=(0.10, -0.16, 0.42), fingers=(-0.8, 0.4, -0.4), palm=(0.0, 0.25, -0.97), elbow=(0.9, 0.1, -0.3))
    flat.arm_r.update(pos=(-0.32, -0.66, 0.18), fingers=(-0.3, -0.9, 0.3), palm=(0.0, 0.0, 1.0), elbow=(-0.95, 0.0, -0.2))
    flat.arm_l.update(pos=(0.07, -0.170, 0.26), fingers=(-0.85, 0.35, -0.40), palm=(0.0, 0.25, -0.97), elbow=(0.90, 0.10, -0.40))
    flat.foot_l = foot_at((0.150, 0.740, 0.180), yaw=24.0, pitch=70.0, knee=(0.25, 0.0, 1.0))
    flat.foot_r = foot_at((-0.220, 0.520, 0.200), yaw=-30.0, pitch=40.0, lean=-15.0, knee=(-0.5, 0.2, 1.0))
    legs = final.copy()
    legs.foot_r = foot_at((-0.250, 0.500, 0.110), yaw=-36.0, pitch=30.0, lean=-20.0, knee=(-0.6, 0.2, 0.9))
    legs.head = (8.0, 10.0, 0.0)
    fix_reach([hit, step, stag, buckle])
    floor_pass([final])
    dense_floor(c, [(0, R), (3, hit), (6, step), (9, stag), (16, buckle), (23, tip.mod(cog=(0.0, -0.20, -0.52), cog_rot=(-50.0, 0.0, 0.0))), (30, sit), (35, flat), (41, legs),
                    (48, final.mod(head=(10.0, 26.0, 2.0))), (54, final), (n, final)])
    c.events_replace([('death_begin', 0), ('foot_r_contact', 8), ('ground_impact', 30), ('death_settled', 54)])


@register('death_back')
def death_back(c):
    n = c.frames
    R = _ik_ready(with_face(ready()))
    final = dead_back_pose()
    FINAL['death_back'] = final
    arch = with_face(R.mod(cog=(R.cog[0], R.cog[1] + 0.07, -0.05), cog_rot=(-4.0, -6.0, 0.0), hips=(8.0, -4.0, 0.0), spine=(-22.0, 2.0, 0.0), head=(-22.0, 2.0, 4.0),
                           clav_l=(4.0, -14.0), clav_r=(4.0, -14.0)), expr_pain=1.0, expr_surprise=0.4, jaw_open=0.45)
    arch.arm_l.update(pos=arch.chest_point((0.46, -0.10, -0.20)), fingers=(0.4, -0.3, -0.87), palm=(0.9, 0.0, -0.4), elbow=(0.5, -0.85, 0.0))
    arch.arm_r.update(pos=arch.chest_point((-0.48, -0.12, -0.22)), fingers=(-0.4, -0.3, -0.87), palm=(-0.9, 0.0, -0.4), elbow=(-0.5, -0.85, 0.0))
    arch.fing_l.update(curl=0.1, spread=0.9)
    arch.fing_r.update(curl=0.1, spread=0.9)
    arch.foot_l.update(roll=0.5)
    arch.foot_r.update(roll=1.2)
    stum = with_face(R.mod(cog=(0.02, 0.20, -0.16), cog_rot=(18.0, -2.0, 3.0), spine=(-6.0, 0.0, 2.0), head=(12.0, 0.0, 6.0)), expr_pain=0.9, blink_l=1.0, blink_r=1.0, jaw_open=0.3)
    stum.foot_l = dict(R.foot_l, pos=(0.150, 0.46, 0.0), yaw=6.0, roll=-0.2)
    stum.foot_r = dict(R.foot_r, roll=1.3)
    stum.arm_l.update(pos=stum.chest_point((0.30, 0.10, -0.46)), fingers=(0.0, 0.3, -0.95), palm=(-0.9, 0.0, -0.3), elbow=(0.6, -0.7, -0.2))
    stum.arm_r.update(pos=stum.chest_point((-0.32, 0.08, -0.48)), fingers=(0.0, 0.3, -0.95), palm=(0.9, 0.0, -0.3), elbow=(-0.6, -0.7, -0.2))
    stepf = Pose.blend(arch, stum, 0.5)
    stepf.foot_r = dict(R.foot_r, roll=0.9)
    stepf.foot_l = foot_clear(0.145, 0.30, yaw=8.0, pitch=8.0, clear=0.05)
    knees = with_face(final.mod(cog=(0.0, 0.34, -0.52), cog_rot=(10.0, 0.0, 2.0), spine=(14.0, 0.0, 2.0), head=(28.0, 0.0, 8.0), hips=(0.0, 0.0, 0.0)), expr_pain=0.6, blink_l=1.0, blink_r=1.0, jaw_open=0.25)
    knees.foot_l = tucked(0.150, 0.130, yaw=-6.0, pitch=-76.0, knee=(0.14, 1.0, -0.5))
    knees.foot_r = tucked(-0.135, 0.070, yaw=6.0, pitch=-76.0, knee=(-0.14, 1.0, -0.5))
    kneel_height(knees, 'r', knee_z=0.062)
    knees.arm_l.update(pos=knees.chest_point((0.26, 0.10, -0.50)), fingers=(0.0, 0.2, -0.98), palm=(-0.9, 0.0, -0.3), elbow=(0.6, -0.7, -0.2))
    knees.arm_r.update(pos=knees.chest_point((-0.20, 0.16, -0.44)), fingers=(0.3, 0.2, -0.93), palm=(0.9, 0.0, -0.3), elbow=(-0.6, -0.7, -0.2))
    kdrop = Pose.blend(stum, knees, 0.5)
    kdrop.foot_l = dict(stum.foot_l, roll=1.3)
    kdrop.foot_r = foot_clear(-0.140, 0.00, yaw=0.0, pitch=-55.0, clear=0.04, knee=(-0.1, 1.0, -0.2))
    topple = with_face(final.mod(cog=(0.0, 0.20, -0.72), cog_rot=(52.0, 0.0, -3.0), spine=(4.0, 0.0, -2.0), head=(10.0, -20.0, 4.0)), blink_l=1.0, blink_r=1.0, jaw_open=0.2)
    topple.foot_l = foot_at((0.160, -0.280, 0.120), yaw=-14.0, pitch=-120.0, knee=(0.12, 0.6, -0.8))
    topple.foot_r = foot_at((-0.130, -0.330, 0.120), yaw=12.0, pitch=-120.0, knee=(-0.12, 0.6, -0.8))
    topple.arm_l.update(pos=(0.24, 0.74, 0.34), fingers=(0.0, 0.9, -0.4), palm=(0.0, 0.3, -0.95), elbow=(0.9, 0.0, 0.2))
    topple.arm_r.update(pos=(-0.10, 0.46, 0.36), fingers=(0.7, 0.3, -0.65), palm=(0.0, 0.3, -0.95), elbow=(-0.85, -0.3, 0.2))
    imp = final.mod(head=(-4.0, -30.0, 0.0), spine=(-8.0, 0.0, -4.0))
    imp.foot_l = foot_at((0.180, -0.700, 0.090), yaw=-24.0, pitch=-160.0, knee=(0.2, 0.0, -1.0))
    imp.arm_l.update(pos=(0.220, 0.900, 0.060))
    slide = final.copy()
    slide.foot_l = foot_at((0.300, -0.560, 0.070), yaw=-50.0, pitch=-170.0, knee=(0.7, 0.3, -0.5))
    fix_reach([arch, stepf, stum, kdrop])
    floor_pass([final])
    dense_floor(c, [(0, R), (3, arch), (6, stepf), (9, stum), (15, kdrop), (20, knees), (27, knees.mod(cog=(knees.cog[0], knees.cog[1] + 0.03, knees.cog[2]), cog_rot=(20.0, 0.0, 2.0))),
                    (32, topple), (36, imp), (42, final.mod(head=(-12.0, -50.0, 0.0), foot_l=dict(imp.foot_l))), (50, slide), (60, final), (n, final)])
    c.events_replace([('death_begin', 0), ('foot_l_contact', 8), ('ground_impact', 36), ('death_settled', 60)])


def _make_dead(which):
    def build(c):
        from .animbuild import REGISTRY
        if which not in FINAL:
            from .animkit import Clip
            REGISTRY[which](Clip(which))
        from .pose import canon
        p = canon(FINAL[which])
        p.apply(c, 0)
        p.apply(c, 1)
    return build


register('dead_front')(_make_dead('death_front'))
register('dead_back')(_make_dead('death_back'))


# ------------------------------------------------------------------------------------ respawn
@register('respawn')
def respawn(c):
    """Materialises kneeling with the fist on the ground, systems come up, rises into the ready stance."""
    n = c.frames
    R = _ik_ready(with_face(ready()))
    base = ready()
    base.foot_r = dict(base.foot_r, pos=(-0.150, 0.06, 0.0), yaw=-10.0, roll=0.0)
    fist = (-0.215, 0.290, 0.062)
    K = kneel(base, knee='l', lean=46.0, wrist=fist, wrist_side='r', back=0.30)
    K.arm_r.update(ik=True, pos=fist, fingers=(0.10, 0.55, -0.83), palm=(0.0, -0.85, -0.5), elbow=(-0.9, -0.2, 0.4))
    K.arm_l.update(ik=True, pos=K.chest_point((0.20, 0.30, -0.26)), fingers=(0.0, 0.8, -0.6), palm=(0.0, 0.3, -0.95), elbow=(0.8, -0.5, -0.2))
    K.fing_r.update(curl=1.0, thumb=0.8)
    K.fing_l.update(curl=0.5, thumb=0.3)
    K.head = (30.0, 0.0, 0.0)
    K.look = (0.0, 0.8, 0.0)
    K = with_face(K, blink_l=1.0, blink_r=1.0)
    wake = with_face(K.mod(head=(-6.0, 0.0, 0.0), look=(0.0, 6.0, 1.3)), expr_focus=0.8)
    flex = wake.copy()
    flex.arm_r.update(pos=flex.chest_point((-0.22, 0.34, -0.20)), fingers=flex.chest_dir((0.0, 0.7, 0.7)), palm=flex.chest_dir((0.9, 0.0, 0.4)), elbow=(-0.8, -0.5, -0.3))
    flex.fing_r.update(curl=0.0, thumb=0.0, spread=1.0)
    flex.head = (4.0, -16.0, 0.0)
    flex.look = (-0.3, 0.6, 1.0)
    flex2 = flex.copy()
    flex2.fing_r.update(curl=1.0, thumb=0.8, spread=0.0)
    flex2.head = (-4.0, 0.0, 0.0)
    flex2.look = (0.0, 6.0, 1.4)
    up = Pose.blend(K, R, 0.6)
    up.foot_r = dict(K.foot_r)
    up.foot_l = foot_clear(0.135, -0.12, yaw=8.0, pitch=-35.0, clear=0.04, knee=(0.1, 1.0, 0.0))
    up.arm_r.update(pos=up.chest_point((-0.28, 0.30, -0.24)))
    up.arm_l.update(pos=up.chest_point((0.16, 0.32, -0.05)))
    st = R.copy()
    st.foot_r = dict(K.foot_r)
    st.cog = (R.cog[0], R.cog[1] + 0.04, R.cog[2] - 0.03)
    st.clav_l = (10.0, -6.0)
    st.clav_r = (10.0, -6.0)
    st2 = R.copy()
    st2.foot_r = foot_clear(-0.150, -0.06, yaw=-28.0, pitch=-8.0, clear=0.05)
    fix_reach([up, st, st2])
    dense_floor(c, [(0, K), (14, K), (24, wake), (30, flex), (36, flex2), (42, flex2.mod(head=(-6.0, 0.0, 0.0))), (52, up), (57, st), (62, st2), (66, R), (n, R)],
                breath=lambda f: 0.8 * math.sin(2 * math.pi * 2 * f / n))
    c.events_replace([('respawn_materialize', 0), ('respawn_active', 40), ('foot_l_contact', 55), ('foot_r_contact', 64), ('control_regained', 68)])

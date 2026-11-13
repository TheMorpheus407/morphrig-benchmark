"""Aim grid, ranged attacks, melee combo, casts, channel, charge, uplink, reload and deploy."""
import math
import numpy as np
from .animbuild import register
from .anim_base import (stand, ready, rotate_pose, foot_at, keys, breathe, with_face, fix_reach, rot2, interp, apply_dense, kneel,
                        foot_clear, dense_floor)
from .pose import Pose
from .animkit import cs, q_to_m, m_to_q
from . import clips as clipdefs, skel


def _n(v):
    v = np.asarray(v, float)
    return tuple(v / max(np.linalg.norm(v), 1e-9))


# ------------------------------------------------------------------------------------ aim
def aim_pose(yaw=0.0, pitch=0.0, tuck=0.0, rise=0.0, base=None):
    """Upper body aiming the wrist emitter along (yaw, pitch) (deg; yaw + = left, pitch + = up).
    tuck pulls the arm back (recoil), rise adds extra muzzle climb in degrees."""
    R = base.copy() if base is not None else ready()
    p = R.copy()
    p.spine = (R.spine[0] - pitch * 0.28, R.spine[1] + yaw * 0.50, 0.0)
    p.head = (R.head[0] - pitch * 0.40, R.head[1] + yaw * 0.32, 0.0)
    p.clav_r = (4.0 + max(pitch, 0.0) * 0.15, 8.0)
    yr, pr = math.radians(yaw), math.radians(pitch + rise)
    d = (math.sin(yr) * math.cos(pr), math.cos(yr) * math.cos(pr), math.sin(pr))
    db = p.shoulder_R('r').T @ cs(d)
    dc = (float(db[0]), float(-db[1]), float(db[2]))                 # shoulder space (left, fwd, up)
    fore = _n((-dc[0], dc[1], dc[2]))                                 # right arm uses mirrored 'left'
    up = _n((fore[0] + 0.30, fore[1] - 0.35 * tuck, fore[2] - 0.55 - 0.55 * tuck))
    p.arm_r.update(ik=False, upper=up, fore=fore, hand=(-4.0, 0.0, 72.0))
    p.fing_r.update(curl=0.78, thumb=0.55, spread=0.0)
    # blade arm: low guard that follows the torso, hand near the sternum
    p.arm_l.update(upper=(0.32, 0.30, -0.90), fore=(-0.55, 0.62, 0.42), hand=(-6.0, 0.0, 20.0))
    p.fing_l.update(curl=0.6, thumb=0.4)
    look = (d[0] * 6.0, d[1] * 6.0, 1.60 + d[2] * 6.0)
    p.look = look
    p.face = dict(p.face, expr_focus=0.75)
    return p


def _make_aim(yv, pv):
    def build(c):
        p = with_face(aim_pose(yv, pv))
        p.apply(c, 0)
        p.apply(c, 1)
        c.notes.update(aim_yaw_deg=yv, aim_pitch_deg=pv)
    return build


for _pn, _pv in clipdefs.AIM_PITCH.items():
    for _yn, _yv in clipdefs.AIM_YAW.items():
        register('aim_%s_%s' % (_pn, _yn))(_make_aim(_yv, _pv))


@register('ranged_fire')
def ranged_fire(c):
    A = with_face(aim_pose())
    k = with_face(aim_pose(tuck=0.55, rise=7.0)).mod(spine=(A.spine[0] - 2.0, A.spine[1] - 5.0, 0.0), clav_r=(6.0, -2.0),
                                                     head=(A.head[0] + 1.0, A.head[1] + 2.0, 0.0))
    o = with_face(aim_pose(tuck=-0.08, rise=-1.5)).mod(spine=(A.spine[0] + 0.5, A.spine[1] + 1.0, 0.0))
    keys(c, [(0, A), (1, with_face(aim_pose(tuck=-0.05))), (3, k), (6, o), (c.frames, A)])
    c.face(2, blink_l=0.0, blink_r=0.0)
    c.face(3, blink_l=0.45, blink_r=0.45)
    c.face(6, blink_l=0.0, blink_r=0.0)
    c.events_replace([('muzzle_1', 2), ('recovery', 5)])


@register('ranged_burst')
def ranged_burst(c):
    A = with_face(aim_pose())
    seq = [(0, A)]
    for i, f in enumerate((2, 6, 10)):
        climb = 2.5 * i
        seq.append((f - 1, with_face(aim_pose(tuck=0.08 * i, rise=climb))))
        seq.append((f + 1, with_face(aim_pose(tuck=0.42 + 0.05 * i, rise=climb + 6.0)).mod(
            spine=(A.spine[0] - 1.5 - i, A.spine[1] - 4.0 - i, 0.0), clav_r=(6.0, -1.0))))
    seq.append((14, with_face(aim_pose(tuck=0.10, rise=3.0))))
    seq.append((c.frames, A))
    keys(c, seq)
    c.events_replace([('muzzle_1', 2), ('muzzle_2', 6), ('muzzle_3', 10), ('recovery', 13)])


# ------------------------------------------------------------------------------------ melee
def _blade_keys(c, seq):
    for f, v in seq:
        c.blade(f, v)


@register('melee_1')
def melee_1(c):
    """Diagonal fore-arm blade slash: high outside left -> low right, weight back -> front."""
    R = with_face(ready(), expr_anger=0.35, expr_focus=0.6)
    wind = R.mod(cog=(-0.03, -0.085, -0.10), cog_rot=(2.0, 14.0, -3.0), hips=(2.0, 6.0, 0.0), spine=(2.0, 30.0, -4.0), head=(-4.0, -30.0, 0.0),
                 clav_l=(10.0, -8.0), arm_l=dict(upper=(0.85, -0.10, 0.55), fore=(-0.25, -0.35, 0.90), hand=(-15.0, 10.0, 30.0)),
                 arm_r=dict(upper=(0.25, 0.35, -0.90), fore=(-0.40, 0.80, 0.30)))
    wind.foot_l.update(roll=-0.25)
    wind.foot_r.update(roll=0.0)
    mid = R.mod(cog=(0.0, 0.045, -0.13), cog_rot=(10.0, -18.0, 2.0), hips=(3.0, -10.0, 0.0), spine=(12.0, -6.0, 3.0), head=(-8.0, 20.0, 0.0),
                clav_l=(4.0, 14.0), arm_l=dict(upper=(0.35, 0.90, 0.15), fore=(-0.10, 0.98, -0.12), hand=(0.0, 8.0, 60.0)),
                arm_r=dict(upper=(0.45, -0.35, -0.80), fore=(0.10, 0.30, -0.95)))
    end = R.mod(cog=(0.02, 0.085, -0.17), cog_rot=(16.0, -38.0, 4.0), hips=(4.0, -14.0, 0.0), spine=(16.0, -28.0, 6.0), head=(-12.0, 52.0, -4.0),
                clav_l=(0.0, 18.0), arm_l=dict(upper=(-0.35, 0.65, -0.70), fore=(-0.80, 0.25, -0.55), hand=(10.0, -8.0, 80.0)),
                arm_r=dict(upper=(0.60, -0.60, -0.50), fore=(0.50, -0.50, -0.70)))
    end.foot_r.update(roll=0.9)
    settle = Pose.blend(end, R, 0.35)
    keys(c, [(0, R), (5, wind), (8, Pose.blend(wind, mid, 0.25)), (10, mid), (12, end), (16, settle), (c.frames, R)])
    _blade_keys(c, [(0, 0.0), (2, 0.15), (5, 1.0), (18, 1.0), (c.frames, 0.0)])
    c.fingers('l', 5, fist=1.0)
    c.fingers('l', 16, fist=1.0)
    c.events_replace([('blade_extend', 2), ('hit_begin', 8), ('hit_end', 12), ('combo_window', 13), ('recovery', 16)])
    fix_reach([wind, mid, end])


@register('melee_2')
def melee_2(c):
    """Reverse (backhand) slash: coiled low on the right -> rising to the outside left, weight front -> back."""
    R = with_face(ready(), expr_anger=0.4, expr_focus=0.6)
    coil = R.mod(cog=(0.02, 0.060, -0.16), cog_rot=(14.0, -34.0, 3.0), hips=(4.0, -12.0, 0.0), spine=(14.0, -26.0, 5.0), head=(-10.0, 48.0, -3.0),
                 clav_l=(0.0, 16.0), arm_l=dict(upper=(-0.30, 0.60, -0.75), fore=(-0.85, 0.05, -0.50), hand=(12.0, -6.0, 70.0)),
                 arm_r=dict(upper=(0.55, -0.45, -0.65), fore=(0.30, -0.10, -0.95)))
    coil.foot_r.update(roll=0.8)
    mid = R.mod(cog=(-0.005, 0.010, -0.11), cog_rot=(6.0, -4.0, 0.0), hips=(3.0, -2.0, 0.0), spine=(6.0, 4.0, 0.0), head=(-6.0, 8.0, 0.0),
                clav_l=(4.0, 12.0), arm_l=dict(upper=(0.30, 0.93, 0.05), fore=(0.20, 0.95, 0.20), hand=(-5.0, 0.0, -20.0)),
                arm_r=dict(upper=(0.35, 0.05, -0.95), fore=(-0.30, 0.75, 0.10)))
    end = R.mod(cog=(-0.035, -0.070, -0.09), cog_rot=(-3.0, 30.0, -4.0), hips=(2.0, 10.0, 0.0), spine=(-2.0, 32.0, -6.0), head=(-2.0, -34.0, 2.0),
                clav_l=(8.0, -10.0), arm_l=dict(upper=(0.95, 0.10, 0.30), fore=(0.90, -0.25, 0.45), hand=(-10.0, 0.0, -30.0)),
                arm_r=dict(upper=(0.20, 0.45, -0.85), fore=(-0.55, 0.70, 0.30)))
    end.foot_l.update(roll=-0.3)
    end.foot_r.update(roll=0.0)
    settle = Pose.blend(end, R, 0.4)
    keys(c, [(0, R), (5, coil), (8, Pose.blend(coil, mid, 0.3)), (10, mid), (12, end), (16, settle), (c.frames, R)])
    _blade_keys(c, [(0, 1.0), (18, 1.0), (c.frames, 0.0)])
    c.fingers('l', 0, fist=1.0)
    c.fingers('l', 16, fist=1.0)
    c.events_replace([('hit_begin', 8), ('hit_end', 12), ('combo_window', 13), ('recovery', 16)])
    fix_reach([coil, mid, end])


@register('melee_3')
def melee_3(c):
    """Finisher: step in with the right foot and drive the blade down from overhead into a deep lunge."""
    R = with_face(ready(), expr_anger=0.7, expr_focus=0.5)
    R0 = R.copy()
    rear = R.mod(cog=(-0.02, -0.11, -0.05), cog_rot=(-10.0, 10.0, 0.0), hips=(0.0, 6.0, 0.0), spine=(-14.0, 18.0, -2.0), head=(4.0, -16.0, 0.0),
                 clav_l=(16.0, -6.0), arm_l=dict(upper=(0.45, -0.05, 0.92), fore=(-0.10, -0.55, 0.80), hand=(-20.0, 0.0, 20.0)),
                 arm_r=dict(upper=(0.45, 0.50, -0.70), fore=(-0.20, 0.90, 0.30)))
    rear.foot_l.update(roll=-0.2)
    rear.foot_r = foot_at((-0.14, -0.02, 0.19), yaw=-12.0, pitch=-25.0, knee=(-0.15, 1.0, 0.1))
    strike = R.mod(cog=(-0.03, 0.20, -0.30), cog_rot=(26.0, -22.0, 0.0), hips=(8.0, -8.0, 0.0), spine=(22.0, -16.0, 4.0), head=(-22.0, 30.0, 0.0),
                   clav_l=(2.0, 16.0), arm_l=dict(upper=(0.10, 0.85, -0.45), fore=(-0.15, 0.80, -0.60), hand=(8.0, 0.0, 60.0)),
                   arm_r=dict(upper=(0.62, -0.55, -0.55), fore=(0.70, -0.45, -0.55)))
    strike.foot_r = dict(R.foot_r, pos=(-0.16, 0.42, 0.0), yaw=-10.0, roll=0.0, pitch=0.0)
    strike.foot_l = dict(R.foot_l, roll=1.2)
    low = strike.mod(cog=(-0.03, 0.23, -0.36), cog_rot=(30.0, -24.0, 0.0), spine=(26.0, -18.0, 4.0),
                     arm_l=dict(upper=(0.05, 0.78, -0.60), fore=(-0.20, 0.70, -0.70)))
    back = Pose.blend(low, R, 0.55)
    back.foot_r = foot_at((-0.15, 0.12, 0.17), yaw=-25.0, pitch=-10.0, knee=(-0.2, 1.0, 0.0))
    back.foot_l = dict(R.foot_l)
    lift0 = Pose.blend(R, rear, 0.35)
    lift0.foot_r = dict(R.foot_r, roll=1.3)
    fly = Pose.blend(rear, strike, 0.55)
    fly.foot_r = foot_at((-0.15, 0.26, 0.15), yaw=-10.0, pitch=8.0, knee=(-0.15, 1.0, 0.1))
    keys(c, [(0, R0), (3, lift0), (7, Pose.blend(R, rear, 0.85)), (10, rear), (12, fly), (14, strike), (17, low), (22, low.mod(cog=(-0.03, 0.22, -0.34))),
             (25, low.mod(cog=(-0.03, 0.20, -0.30), foot_r=dict(roll=0.9))), (28, back), (31, R0.mod(foot_r=dict(roll=-0.2))), (c.frames, R0)])
    _blade_keys(c, [(0, 1.0), (24, 1.0), (30, 0.0), (c.frames, 0.0)])
    c.fingers('l', 0, fist=1.0)
    c.fingers('l', 24, fist=1.0)
    c.events_replace([('foot_r_contact', 14), ('hit_begin', 12), ('hit_end', 17), ('recovery', 22), ('blade_retract', 27), ('foot_r_contact', 31)])
    c.events = sorted(c.events, key=lambda e: e['frame'])
    fix_reach([rear, strike, low, back])


# ------------------------------------------------------------------------------------ casts
@register('cast_directional')
def cast_directional(c):
    A = with_face(aim_pose())
    wind = with_face(aim_pose(tuck=1.1, rise=-4.0)).mod(spine=(A.spine[0] + 2.0, A.spine[1] - 24.0, 0.0), head=(A.head[0], A.head[1] + 22.0, 0.0),
                                                        clav_r=(2.0, -10.0), arm_l=dict(upper=(0.30, 0.80, -0.35), fore=(0.05, 0.98, 0.10), hand=(-20.0, 0.0, 40.0)))
    wind.fing_l.update(curl=0.05, spread=0.7, thumb=0.0)
    wind.fing_r.update(curl=1.0, thumb=0.8)
    rel = with_face(aim_pose(tuck=-0.25, rise=2.0), expr_anger=0.3).mod(spine=(A.spine[0] + 6.0, A.spine[1] + 16.0, 0.0), head=(A.head[0] - 2.0, A.head[1] - 14.0, 0.0),
                                                                     clav_r=(4.0, 18.0), arm_l=dict(upper=(0.45, -0.35, -0.80), fore=(0.20, 0.15, -0.95)))
    rel.arm_r['hand'] = (-25.0, 0.0, 72.0)
    rel.fing_r.update(curl=0.0, spread=0.9, thumb=0.0)
    hold = rel.mod(spine=(A.spine[0] + 4.0, A.spine[1] + 12.0, 0.0))
    keys(c, [(0, A), (6, wind), (9, Pose.blend(wind, rel, 0.35)), (11, rel), (16, hold), (c.frames, A)])
    c.events_replace([('cast_release', 11), ('recovery', 16)])


@register('cast_ground')
def cast_ground(c):
    """Raise the emitter hand, then drop to one knee and drive the palm into the ground at the target."""
    R = with_face(ready(), expr_focus=0.8)
    tgt = (0.0, 2.2, 0.0)
    up = R.mod(cog=(-0.01, -0.05, -0.04), cog_rot=(-6.0, -8.0, 0.0), spine=(-8.0, 6.0, 0.0), head=(14.0, 8.0, 0.0), look=tgt, clav_r=(18.0, 0.0),
               arm_l=dict(upper=(0.40, 0.55, -0.70), fore=(-0.20, 0.90, -0.20)))
    up.arm_r.update(ik=True, pos=up.chest_point((-0.30, 0.16, 0.56)), fingers=(0.0, 0.3, 0.95), palm=(0.0, 1.0, 0.0), elbow=(-0.9, -0.2, -0.3))
    up.fing_r.update(curl=0.1, spread=0.9, thumb=0.0)
    palm = (-0.19, 0.40, 0.050)
    slam = kneel(R, knee='r', lean=56.0, wrist=palm, wrist_side='r', back=0.33)
    slam.arm_r.update(ik=True, pos=palm, fingers=(0.05, 1.0, 0.0), palm=(0.0, 0.0, -1.0), elbow=(-0.9, -0.3, 0.4))
    slam.fing_r.update(curl=0.0, spread=1.0, thumb=0.0)
    slam.arm_l.update(upper=(0.70, -0.45, -0.30), fore=(0.75, -0.55, 0.25))
    slam.look = tgt
    slam.head = (-34.0, 6.0, 0.0)
    slam = with_face(slam, expr_anger=0.4, expr_focus=0.8)
    R2 = R.copy()
    R2.arm_r.update(ik=True, pos=R.chest_point((-0.30, 0.30, -0.24)), fingers=R.chest_dir((0.10, 0.92, 0.36)), palm=R.chest_dir((0.5, 0.0, -0.85)), elbow=(-0.6, -0.6, -0.5))
    drop = Pose.blend(up, slam, 0.45)
    drop.foot_l = dict(R.foot_l)
    drop.foot_r = foot_clear(-0.150, -0.30, yaw=-25.0, pitch=-45.0, clear=0.03, knee=(-0.1, 1.0, -0.2))
    drop.arm_r.update(ik=True, pos=(-0.24, 0.30, 0.75), fingers=(0.0, 0.8, -0.6), palm=(0.0, 0.5, -0.86), elbow=(-0.9, -0.3, 0.2))
    hold = slam.mod(head=(-28.0, 6.0, 0.0))
    rise = Pose.blend(slam, R2, 0.55)
    rise.foot_r = foot_clear(-0.150, -0.26, yaw=-30.0, pitch=-35.0, clear=0.03, knee=(-0.1, 1.0, -0.1))
    rise.arm_r.update(ik=True, pos=(-0.26, 0.30, 0.60), fingers=(0.0, 0.9, -0.3), palm=(0.2, -0.3, -0.9), elbow=(-0.8, -0.4, -0.2))
    fix_reach([up, drop, rise])
    dense_floor(c, [(0, R2), (9, up), (14, drop), (18, slam), (26, hold), (31, rise), (c.frames, R2)])
    c.events_replace([('cast_release', 18), ('recovery', 26), ('foot_r_contact', 34)])


@register('cast_self')
def cast_self(c):
    R = with_face(ready(), expr_focus=0.8)
    gather = R.mod(cog=(R.cog[0], R.cog[1], -0.19), cog_rot=(14.0, -8.0, 0.0), spine=(16.0, 8.0, 0.0), head=(-22.0, 8.0, 0.0), clav_l=(8.0, 18.0), clav_r=(8.0, 18.0),
                   arm_l=dict(upper=(0.30, 0.55, -0.75), fore=(-0.85, 0.35, 0.40), hand=(10.0, 0.0, 20.0)),
                   arm_r=dict(upper=(0.30, 0.55, -0.75), fore=(-0.85, 0.30, 0.25), hand=(10.0, 0.0, 20.0)))
    gather.fing_l.update(curl=1.0, thumb=0.8)
    gather.fing_r.update(curl=1.0, thumb=0.8)
    gather = with_face(gather, blink_l=1.0, blink_r=1.0, expr_focus=0.9)
    burst = R.mod(cog=(R.cog[0], R.cog[1] + 0.02, -0.02), cog_rot=(-6.0, -6.0, 0.0), spine=(-12.0, 6.0, 0.0), head=(10.0, 6.0, 0.0), clav_l=(4.0, -12.0), clav_r=(4.0, -12.0),
                  arm_l=dict(upper=(0.90, -0.15, -0.40), fore=(0.85, 0.10, -0.50), hand=(-30.0, 0.0, -60.0)),
                  arm_r=dict(upper=(0.90, -0.15, -0.40), fore=(0.85, 0.10, -0.50), hand=(-30.0, 0.0, -60.0)))
    burst.fing_l.update(curl=0.0, spread=1.0, thumb=0.0)
    burst.fing_r.update(curl=0.0, spread=1.0, thumb=0.0)
    burst.foot_l.update(roll=0.5)
    burst.foot_r.update(roll=0.9)
    burst = with_face(burst, expr_anger=0.5, jaw_open=0.35)
    hold = burst.mod(cog=(R.cog[0], R.cog[1] + 0.02, -0.04), spine=(-8.0, 6.0, 0.0))
    keys(c, [(0, R), (7, gather), (10, gather.mod(cog=(R.cog[0], R.cog[1], -0.21))), (13, burst), (21, hold), (c.frames, R)])
    c.events_replace([('cast_release', 13), ('recovery', 21)])
    fix_reach([gather, burst])


# ------------------------------------------------------------------------------------ channel
def channel_pose(shake=0.0, push=0.0):
    """Braced two-handed beam: right arm locked forward, left hand supports the fore-arm from below."""
    R = ready()
    p = R.mod(cog=(R.cog[0], R.cog[1] + 0.02 + 0.01 * push, -0.13), cog_rot=(11.0 + 2.0 * push, -10.0, 0.0), hips=(4.0, -6.0, 0.0),
              spine=(10.0 + shake, 12.0, 0.0), head=(-12.0, 8.0, 0.0), clav_r=(4.0, 14.0), clav_l=(2.0, 16.0))
    d = (0.0, 1.0, 0.0)
    db = p.shoulder_R('r').T @ cs(d)
    fore = _n((-float(db[0]), float(-db[1]), float(db[2]) + 0.01 * shake))
    p.arm_r.update(ik=False, upper=_n((fore[0] + 0.22, fore[1], fore[2] - 0.40)), fore=fore, hand=(-12.0, 0.0, 72.0))
    p.fing_r.update(curl=0.0, spread=0.8, thumb=0.0)
    p.arm_l.update(upper=(0.10, 0.70, -0.70), fore=(-0.72, 0.68, 0.10), hand=(-10.0, 0.0, -50.0))
    p.fing_l.update(curl=0.55, thumb=0.3, spread=0.2)
    p.foot_r.update(roll=0.15)
    p.face = dict(p.face, expr_focus=0.9, expr_anger=0.25)
    p.look = (0.0, 6.0, 1.45)
    return p


@register('channel_start')
def channel_start(c):
    R = with_face(ready())
    C = with_face(channel_pose())
    pre = Pose.blend(R, C, 0.45).mod(cog=(R.cog[0], R.cog[1] - 0.02, -0.15), spine=(12.0, 2.0, 0.0))
    keys(c, [(0, R), (4, pre), (9, with_face(channel_pose(push=1.5))), (c.frames, C)])
    c.events_replace([('channel_begin', 10)])
    fix_reach([pre, C])


@register('channel_loop')
def channel_loop(c):
    n = c.frames
    seq = []
    for i in range(0, 9):
        f = n * i / 8.0
        sh = 0.9 * math.sin(2 * math.pi * i / 4.0)
        seq.append((f, with_face(channel_pose(shake=sh, push=0.6 * math.cos(2 * math.pi * i / 8.0)))))
    keys(c, seq)
    breathe(c, 2, 0.5)
    c.events_replace([('channel_tick', 0), ('channel_tick', n // 2)])


@register('channel_end')
def channel_end(c):
    R = with_face(ready())
    C = with_face(channel_pose())
    flick = with_face(channel_pose(push=2.5)).mod(spine=(6.0, 14.0, 0.0), head=(-6.0, 6.0, 0.0))
    flick.arm_r.update(upper=_n((0.25, 0.80, -0.10)), fore=_n((0.02, 0.92, 0.38)))
    flick.arm_l.update(upper=(0.25, 0.45, -0.85), fore=(-0.45, 0.80, 0.05))
    rel = Pose.blend(flick, R, 0.5)
    keys(c, [(0, C), (3, flick), (8, rel), (c.frames, R)])
    breathe(c, 1, -0.7)
    c.events_replace([('channel_complete', 3)])


@register('channel_interrupt')
def channel_interrupt(c):
    R = with_face(ready())
    C = with_face(channel_pose())
    jolt = with_face(R.mod(cog=(R.cog[0] + 0.02, R.cog[1] - 0.09, -0.10), cog_rot=(-10.0, 6.0, 4.0), spine=(-12.0, -14.0, 6.0), head=(10.0, 20.0, 6.0),
                           clav_r=(10.0, -12.0), arm_r=dict(upper=(0.80, 0.15, 0.30), fore=(0.55, 0.35, 0.75), hand=(-20.0, 0.0, 20.0)),
                           arm_l=dict(upper=(0.55, -0.20, -0.75), fore=(0.30, 0.50, -0.70))), expr_pain=0.6, expr_surprise=0.4)
    jolt.fing_r.update(curl=0.1, spread=1.0, thumb=0.0)
    jolt.foot_l.update(roll=-0.5)
    rec = Pose.blend(jolt, R, 0.6)
    keys(c, [(0, C), (3, jolt), (7, rec), (c.frames, R)])
    c.events_replace([('channel_interrupted', 0)])


# ------------------------------------------------------------------------------------ charge
def charge_pose(k=1.0, tremble=0.0):
    """Coiled: emitter arm drawn back at the ribs, off hand sighting forward."""
    A = aim_pose()
    p = aim_pose(tuck=1.25 * k, rise=-6.0 * k)
    p = p.mod(cog=(A.cog[0], A.cog[1] - 0.03 * k, A.cog[2] - 0.05 * k), spine=(A.spine[0] + 3.0 * k, A.spine[1] - 26.0 * k + tremble, 0.0),
              head=(A.head[0], A.head[1] + 24.0 * k, 0.0), clav_r=(3.0 + tremble, -12.0 * k),
              arm_l=dict(upper=(0.28, 0.82, -0.30), fore=(0.02, 0.99, 0.12 + 0.01 * tremble), hand=(-25.0, 0.0, 40.0)))
    p.fing_l.update(curl=0.05, spread=0.6, thumb=0.0)
    p.fing_r.update(curl=1.0, thumb=0.9)
    p.face = dict(p.face, expr_focus=0.9, expr_anger=0.3 * k)
    return p


@register('charge_start')
def charge_start(c):
    A = with_face(aim_pose())
    keys(c, [(0, A), (5, with_face(charge_pose(0.45))), (12, with_face(charge_pose(1.08))), (c.frames, with_face(charge_pose(1.0)))])
    c.events_replace([('charge_begin', 3), ('charge_ready', 17)])


@register('charge_hold')
def charge_hold(c):
    n = c.frames
    seq = []
    for i in range(0, 11):
        f = n * i / 10.0
        tr = 0.7 * math.sin(2 * math.pi * i / 2.5) * (1 if i % 10 else 0)
        seq.append((f, with_face(charge_pose(1.0 + 0.03 * math.sin(2 * math.pi * i / 10.0), tremble=tr))))
    keys(c, seq)
    breathe(c, 1, 0.5)
    c.events_replace([('charge_pulse', 0)])


@register('charge_release')
def charge_release(c):
    A = with_face(aim_pose())
    C = with_face(charge_pose(1.0))
    thrust = with_face(aim_pose(tuck=-0.3, rise=1.0), expr_anger=0.6).mod(cog=(A.cog[0], A.cog[1] + 0.07, A.cog[2] - 0.04), cog_rot=(12.0, -22.0, 0.0),
                                                                        spine=(A.spine[0] + 8.0, A.spine[1] + 20.0, 0.0), head=(A.head[0] - 4.0, A.head[1] - 8.0, 0.0), clav_r=(4.0, 20.0),
                                                                        arm_l=dict(upper=(0.50, -0.45, -0.70), fore=(0.30, -0.10, -0.95)))
    thrust.fing_r.update(curl=0.0, spread=1.0, thumb=0.0)
    thrust.arm_r['hand'] = (-30.0, 0.0, 72.0)
    kick = with_face(aim_pose(tuck=0.75, rise=14.0)).mod(cog=(A.cog[0], A.cog[1] - 0.05, A.cog[2] - 0.02), spine=(A.spine[0] - 8.0, A.spine[1] - 10.0, 0.0),
                                                         head=(A.head[0] + 4.0, A.head[1] + 4.0, 0.0), clav_r=(8.0, -6.0))
    kick.foot_l.update(roll=-0.35)
    keys(c, [(0, C), (2, with_face(charge_pose(1.12))), (4, thrust), (8, kick), (12, with_face(aim_pose(tuck=0.2, rise=3.0))), (c.frames, A)])
    c.events_replace([('charge_released', 4), ('recovery', 12)])


@register('charge_cancel')
def charge_cancel(c):
    A = with_face(aim_pose())
    C = with_face(charge_pose(1.0))
    vent = with_face(ready()).mod(spine=(8.0, -4.0, 0.0), head=(-14.0, -6.0, 0.0), arm_r=dict(upper=(0.35, 0.10, -0.95), fore=(0.20, 0.55, -0.80), hand=(15.0, 0.0, 40.0)),
                                  arm_l=dict(upper=(0.28, 0.40, -0.88), fore=(-0.40, 0.75, 0.20)))
    vent.fing_r.update(curl=0.0, spread=1.0, thumb=0.0)
    v2 = vent.mod(arm_r=dict(upper=(0.38, 0.05, -0.95), fore=(0.32, 0.45, -0.85), hand=(-15.0, 10.0, 20.0)))
    v3 = vent.mod(arm_r=dict(upper=(0.33, 0.12, -0.95), fore=(0.12, 0.62, -0.78), hand=(20.0, -10.0, 55.0)))
    keys(c, [(0, C), (4, vent), (6, v2), (8, v3), (10, Pose.blend(v3, A, 0.5)), (c.frames, A)])
    breathe(c, 1, -0.6)
    c.events_replace([('charge_cancelled', 2)])


# ------------------------------------------------------------------------------------ uplink
def uplink_pose(tap=0.0, tap_x=0.0):
    """Wrist console: emitter fore-arm held level in front of the chest, left index finger working on it."""
    S = stand()
    p = S.mod(cog=(0.0, 0.0, -0.02), hips=(0.0, 0.0, 0.0), spine=(6.0, -3.0, 0.0), head=(22.0, -10.0, 0.0), look=(-0.10, 0.45, 1.20), clav_r=(4.0, 14.0), clav_l=(3.0, 14.0))
    p.foot_l.update(pos=(0.115, -0.02, 0.0), yaw=10.0)
    p.foot_r.update(pos=(-0.115, -0.02, 0.0), yaw=-10.0)
    p.arm_r.update(upper=(0.10, 0.70, -0.70), fore=(-0.96, 0.22, 0.14), hand=(-6.0, 0.0, 30.0))
    p.fing_r.update(curl=0.55, thumb=0.3)
    p.arm_l.update(upper=(0.22, 0.60, -0.76), fore=(-0.50 + 0.10 * tap_x, 0.66, 0.50 - 0.045 * tap), hand=(20.0 + 10.0 * tap, 0.0, 40.0))
    p.fing_l.update(curl=0.85, index=0.12 + 0.18 * tap, thumb=0.5)
    p.face = {'expr_focus': 0.7}
    return p


@register('uplink_start')
def uplink_start(c):
    R = with_face(ready())
    U = with_face(uplink_pose())
    mid = Pose.blend(R, U, 0.5)
    mid.foot_l = dict(R.foot_l)
    mid.foot_r = dict(R.foot_r, pos=(-0.13, -0.10, 0.06), yaw=-22.0, roll=0.0, pitch=-6.0)
    m2 = Pose.blend(R, U, 0.8)
    m2.foot_r = dict(U.foot_r)
    m2.foot_l = dict(R.foot_l, pos=(0.125, 0.04, 0.05), yaw=10.0, roll=0.0)
    pre = Pose.blend(R, U, 0.15)
    pre.foot_l = dict(R.foot_l)
    pre.foot_r = dict(R.foot_r, roll=1.2)
    m15 = Pose.blend(R, U, 0.65)
    m15.foot_r = dict(U.foot_r, roll=-0.2)
    m15.foot_l = dict(R.foot_l, roll=1.0)
    keys(c, [(0, R), (2, pre), (5, mid), (8, m15), (10, m2), (13, U.mod(foot_l=dict(roll=-0.2))), (14, U), (16, with_face(uplink_pose(tap=1.0))), (c.frames, U)])
    c.events_replace([('foot_r_contact', 8), ('foot_l_contact', 13), ('uplink_begin', 16)])


@register('uplink_loop')
def uplink_loop(c):
    n = c.frames
    taps = [(0, 0.0, 0.0), (5, 1.0, 0.0), (9, 0.0, 0.3), (14, 1.0, 0.6), (18, 0.0, 0.6), (24, 1.0, -0.4), (28, 0.1, -0.4), (33, 1.0, 0.2), (38, 0.0, 0.0), (n, 0.0, 0.0)]
    seq = []
    for f, t, x in taps:
        p = with_face(uplink_pose(t, x))
        p = p.mod(head=(22.0 + 2.0 * math.sin(f / n * 2 * math.pi), -10.0 + 5.0 * x, 0.0))
        seq.append((f, p))
    keys(c, seq)
    breathe(c, 1, 0.45)
    c.blink(20)
    c.events_replace([('uplink_pulse', 0)])


@register('uplink_end')
def uplink_end(c):
    S = with_face(stand())
    U = with_face(uplink_pose())
    tap = with_face(uplink_pose(tap=1.35, tap_x=0.1))
    done = S.mod(spine=(-2.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0), look=(0.0, 6.0, 1.9), arm_r=dict(upper=(0.20, 0.10, -1.0), bend=30.0), arm_l=dict(upper=(0.18, 0.05, -1.0), bend=26.0))
    done.foot_l = dict(U.foot_l)
    done.foot_r = dict(U.foot_r)
    done = with_face(done, expr_focus=0.4)
    keys(c, [(0, U), (3, with_face(uplink_pose(tap=-0.4))), (5, tap), (9, Pose.blend(tap, done, 0.5)), (c.frames, done)])
    breathe(c, 1, 0.8)
    c.events_replace([('uplink_complete', 5)])


@register('uplink_cancel')
def uplink_cancel(c):
    R = with_face(ready())
    U = with_face(uplink_pose())
    jerk = with_face(U.mod(spine=(0.0, 4.0, 0.0), head=(4.0, 14.0, 0.0), look=(1.5, 6.0, 1.6), arm_r=dict(upper=(0.40, 0.45, -0.80), fore=(-0.40, 0.75, 0.50)),
                           arm_l=dict(upper=(0.55, 0.30, -0.78), fore=(0.25, 0.80, 0.55), hand=(-10.0, 0.0, 10.0))), expr_surprise=0.5, expr_anger=0.3)
    jerk.fing_l.update(curl=0.1, index=0.0, spread=0.8)
    mid = Pose.blend(jerk, R, 0.6)
    mid.foot_l = dict(U.foot_l)
    mid.foot_r = dict(R.foot_r, pos=(-0.13, -0.10, 0.05), yaw=-25.0, roll=0.0)
    end = R.copy()
    jerk.foot_r = dict(U.foot_r, roll=1.0)
    mid.foot_l = dict(U.foot_l, roll=0.0)
    m10 = Pose.blend(jerk, R, 0.85)
    m10.foot_r = dict(R.foot_r, roll=-0.1)
    m10.foot_l = dict(U.foot_l, roll=1.0)
    m12 = R.copy()
    m12.foot_l = dict(R.foot_l, pos=(0.13, 0.05, 0.04), roll=0.0)
    keys(c, [(0, U), (3, jerk), (7, mid), (10, m10), (12, m12), (c.frames, end)])
    c.events_replace([('uplink_cancelled', 0), ('foot_r_contact', 10), ('foot_l_contact', 13)])


# ------------------------------------------------------------------------------------ reload / deploy (measured contacts)
def _mat(x, y, z, pos):
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, z, pos
    return m


# power cell in the left hand (hand bone space: X palmar, Y distal, Z thumb side). Pinch from above: the cell's
# top faces the palm, its narrow sides sit between thumb and fingers.
CELL_IN_HAND_L = _mat((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.052, 0.078, 0.004))
# beacon in the right hand (hand bone space: X dorsal, Y distal, Z thumb side): palm on the dome
BEACON_IN_HAND_R = _mat((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (-0.060, 0.066, 0.0))


def _hand_target(prop_world, prop_in_hand):
    H = prop_world @ np.linalg.inv(prop_in_hand)
    pos = H[:3, 3]
    return (float(pos[0]), float(-pos[1]), float(pos[2])), H[:3, :3]


def _ik_from_matrix(pose, side, M, elbow):
    a = getattr(pose, 'arm_' + side)
    a.update(ik=True, pos=(float(M[0, 3]), float(-M[1, 3]), float(M[2, 3])), elbow=elbow)
    a['rot_m'] = M[:3, :3].copy()


def _apply_hand_matrix(c, side, f, M, elbow):
    c.hand_ik(side, f, (float(M[0, 3]), float(-M[1, 3]), float(M[2, 3])), elbow=elbow, rot_m=M[:3, :3])
    c.arm_mode(side, f, True)


@register('reload')
def reload(c, ctx):
    """Left hand pulls the spent cell from the emitter, parks it in the rear belt cradle, takes the fresh cell from
    the front cradle, seats it and presses it home. Hand targets are measured from the posed props."""
    n = c.frames
    A = with_face(aim_pose(), expr_focus=0.5)
    R = with_face(ready(), expr_focus=0.5)
    # body: emitter fore-arm presented across the chest (dorsal side / cell up), eyes on the work
    present = R.mod(spine=(12.0, 2.0, 0.0), head=(16.0, -2.0, 0.0), look=(-0.05, 0.40, 1.18), clav_r=(4.0, 14.0),
                    arm_r=dict(ik=False, upper=(0.06, 0.74, -0.67), fore=(-0.97, 0.20, 0.10), hand=(-5.0, 0.0, 20.0)))
    present.fing_r.update(curl=0.6, thumb=0.35)
    tilt = present.mod(arm_r=dict(upper=(0.08, 0.72, -0.69), fore=(-0.96, 0.24, 0.14)), spine=(13.0, 0.0, 0.0))
    body = [(0, R), (8, present), (14, present), (20, tilt), (31, tilt.mod(head=(20.0, -22.0, 0.0), look=(0.6, 0.2, 0.95))), (40, present),
            (45, present.mod(spine=(13.5, 2.0, 0.0))), (48, present.mod(arm_r=dict(upper=(0.06, 0.72, -0.69), fore=(-0.97, 0.18, 0.06)))), (52, present), (n, R)]
    H0 = ctx.pose(R, ['hand_l'])['hand_l']               # ready pose hand, so the clip starts/ends on the idle
    for f, p in body:
        p.skip = ('arm_l', 'fing_l')
        p.apply(c, f)
    elbow_l = (0.75, -0.45, -0.45)
    need = ['prop_cell', 'prop_cell_spare', 'lowerarm_r', 'pelvis']
    smp = ctx.sample(c, list(range(0, n + 1)), need)
    cell = lambda f: smp[f]['lowerarm_r'] @ (np.linalg.inv(c.R.rest['lowerarm_r']) @ c.R.rest['prop_cell'])
    spare = lambda f: smp[f]['prop_cell_spare']
    G = CELL_IN_HAND_L
    up_b = np.array([0.0, 0.0, 1.0])

    def hand_for(prop_M):
        return prop_M @ np.linalg.inv(G)

    def lifted(M, along, dist):
        o = M.copy()
        o[:3, 3] = o[:3, 3] + along * dist
        return o
    eject_dir = lambda f: cell(f)[:3, 1]
    # rear cradle: the empty holder behind the spare cell on the belt (pelvis space)
    rest = c.R.rest
    from . import skel as _skel
    rear_local = np.linalg.inv(rest['pelvis']) @ _skel.rear_cradle_matrix()
    rear = lambda f: smp[f]['pelvis'] @ rear_local
    keysL = [
        (0, H0),
        (12, hand_for(lifted(cell(12), eject_dir(12), 0.035))),      # hover above the cell
        (14, hand_for(cell(14))),                                     # grip (reload_eject)
        (17, hand_for(lifted(cell(17), eject_dir(17), 0.050))),      # pulled clear
        (20, hand_for(lifted(cell(20), eject_dir(20), 0.085))),
        (24, hand_for(lifted(rear(26), up_b, 0.075))),               # above the rear cradle
        (26, hand_for(rear(26))),                                     # stow (reload_stow)
        (29, hand_for(lifted(spare(29), up_b, 0.040))),              # shift to the fresh cell
        (31, hand_for(spare(31))),                                    # grab (reload_grab_new)
        (34, hand_for(lifted(spare(31), up_b, 0.080))),
        (41, hand_for(lifted(cell(41), eject_dir(41), 0.075))),      # carried above the slot
        (45, hand_for(cell(45))),                                     # seated (reload_insert)
    ]
    for f, M in keysL:
        _apply_hand_matrix(c, 'l', f, M, elbow_l)
    # palm press: hand flattens onto the cap and pushes
    press = cell(50).copy()
    Hp = hand_for(lifted(press, eject_dir(50), 0.012))
    _apply_hand_matrix(c, 'l', 48, hand_for(lifted(cell(48), eject_dir(48), 0.030)), elbow_l)
    _apply_hand_matrix(c, 'l', 50, Hp, elbow_l)
    _apply_hand_matrix(c, 'l', 52, hand_for(lifted(cell(52), eject_dir(52), 0.035)), elbow_l)
    _apply_hand_matrix(c, 'l', n, H0, elbow_l)
    # fingers: open -> pinch -> open ...
    for f, curl, th in [(0, 0.62, 0.45), (10, 0.15, 0.05), (14, 0.52, 0.42), (26, 0.52, 0.42), (28, 0.18, 0.08), (31, 0.52, 0.42), (45, 0.52, 0.42),
                        (48, 0.10, 0.05), (52, 0.12, 0.10), (n, 0.62, 0.45)]:
        c.fingers('l', f, fist=0.0, spread=0.15, thumb=th, index=curl, middle=curl, ring=curl + 0.12, pinky=curl + 0.18)
    # prop ownership: constant grip while held (stepped keys)
    c.hold_grip('prop_cell', 'hand_l', 0, G)
    c.hold_grip('prop_cell_spare', 'hand_l', 0, G)
    for f, v in [(0, 0), (13, 0), (14, 1), (26, 1), (27, 0), (n, 0)]:
        c.prop_hold('prop_cell', 'hand_l', f, v)
    for f, v in [(0, 0), (30, 0), (31, 1), (45, 1), (46, 0), (n, 0)]:
        c.prop_hold('prop_cell_spare', 'hand_l', f, v)
    for ch in ('prop:hold_hand_l',):
        c.dense.add(('prop_cell', ch))
        c.dense.add(('prop_cell_spare', ch))
    # after release: spent cell rests in the rear cradle, fresh cell is seated in the emitter (relative to its rest parent)
    spent_basis = np.linalg.inv(rest['prop_cell_spare']) @ (rest['pelvis'] @ rear_local)          # as if it were the spare
    # prop_cell rests under lowerarm_r: express "rear cradle" relative to the fore-arm for the frames after stowing
    for f in range(27, n + 1):
        M = np.linalg.inv(smp[f]['lowerarm_r'] @ np.linalg.inv(rest['lowerarm_r']) @ rest['prop_cell']) @ rear(f)
        c.prop_basis('prop_cell', f, M)
    c.prop_basis('prop_cell', 0, np.eye(4))
    c.prop_basis('prop_cell', 26, np.eye(4))
    c.dense.add(('prop_cell', 'loc'))
    c.dense.add(('prop_cell', 'rot'))
    # fresh cell: seated = the emitter slot, expressed relative to the pelvis-parented spare bone
    slot_local = np.linalg.inv(rest['lowerarm_r']) @ rest['prop_cell']
    for f in range(45, n + 1):
        slot = smp[f]['lowerarm_r'] @ slot_local
        M = np.linalg.inv(smp[f]['pelvis'] @ np.linalg.inv(rest['pelvis']) @ rest['prop_cell_spare']) @ slot
        c.prop_basis('prop_cell_spare', f, M)
    c.prop_basis('prop_cell_spare', 0, np.eye(4))
    c.prop_basis('prop_cell_spare', 44, np.eye(4))
    c.dense.add(('prop_cell_spare', 'loc'))
    c.dense.add(('prop_cell_spare', 'rot'))
    c.events_replace([('reload_eject', 14), ('reload_stow', 26), ('reload_grab_new', 31), ('reload_insert', 45), ('reload_done', 50)])
    c.prop_tracks = [dict(prop='prop_cell', holder='hand_l', frame_start=14, frame_end=26),
                     dict(prop='prop_cell', holder='pelvis', frame_start=27, frame_end=n, note='stowed in the rear belt cradle (socket cell_cradle_rear)'),
                     dict(prop='prop_cell_spare', holder='hand_l', frame_start=31, frame_end=45),
                     dict(prop='prop_cell_spare', holder='lowerarm_r', frame_start=46, frame_end=n, note='seated in the emitter (socket cell_slot)')]
    c.notes.update(prop_swap='after the clip prop_cell_spare sits in the emitter and prop_cell in the rear belt cradle; '
                             'both snap to their rest mounts when the clip ends (identical cells, no visible change in the emitter)')


@register('deploy')
def deploy(c, ctx):
    """Right hand takes the beacon from the belt dock, the Operative kneels and sets it on the ground ahead."""
    n = c.frames
    R = with_face(ready(), expr_focus=0.6)
    reach_back = R.mod(spine=(4.0, -16.0, 0.0), head=(-2.0, 2.0, 0.0), clav_r=(2.0, -14.0))
    place = (-0.235, 0.34, 0.0)                                     # ground spot for the beacon (right-front of the knee)
    ground = np.eye(4)
    ground[:3, 3] = cs(place)
    ground[:3, 0], ground[:3, 1], ground[:3, 2] = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)
    Hg = ground @ np.linalg.inv(BEACON_IN_HAND_R)                # hand bone matrix while the beacon stands on the ground
    wrist_place = (float(Hg[0, 3]), float(-Hg[1, 3]), float(Hg[2, 3]))
    kn = kneel(R, knee='r', lean=54.0, wrist=wrist_place, wrist_side='r', back=0.34)
    kn.arm_l.update(upper=(0.40, 0.30, -0.86), fore=(0.10, 0.75, -0.65), hand=(0.0, 0.0, 30.0))
    kn.look = (place[0], place[1], 0.0)
    kn.head = (-10.0, -10.0, 0.0)
    mid_down = Pose.blend(R, kn, 0.5)
    mid_down.foot_l = dict(R.foot_l)
    mid_down.foot_r = foot_clear(-0.150, -0.30, yaw=-25.0, pitch=-45.0, clear=0.03, knee=(-0.1, 1.0, -0.2))
    hold = kn.mod(cog=(kn.cog[0], kn.cog[1], kn.cog[2] + 0.006))
    up = Pose.blend(kn, R, 0.6)
    up.foot_l = dict(R.foot_l)
    up.foot_r = foot_clear(-0.150, -0.26, yaw=-32.0, pitch=-35.0, clear=0.03, knee=(-0.1, 1.0, -0.1))
    kneel_p = kn
    body = [(0, R), (6, reach_back), (9, reach_back), (15, mid_down), (22, kneel_p), (27, hold), (33, hold.mod(head=(-2.0, 6.0, 0.0), look=(0.0, 3.0, 0.9))), (39, up), (n, R)]
    fix_reach([R, reach_back, mid_down, up])
    H0 = ctx.pose(R, ['hand_r'])['hand_r']
    from .pose import interp_dense, floor_pass
    dense = interp_dense(body, n)
    floor_pass(dense)
    for f, p in enumerate(dense):
        p.skip = ('arm_r', 'fing_r')
        p.apply(c, f, dense=True)
    need = ['prop_beacon', 'pelvis']
    smp = ctx.sample(c, [0, 6, 9, 12, n], need)
    G = BEACON_IN_HAND_R
    hand_for = lambda M: M @ np.linalg.inv(G)
    b9 = smp[9]['prop_beacon']
    out_dir = b9[:3, 2]                                    # dock normal
    def moved(M, v):
        o = M.copy()
        o[:3, 3] = o[:3, 3] + v
        return o
    carry1 = moved(b9, out_dir * 0.06 + np.array([-0.05, 0.0, 0.02]))
    carry2 = np.eye(4)
    carry2[:3, :3] = ground[:3, :3]
    carry2[:3, 3] = cs((-0.30, 0.16, 0.42))
    above = moved(ground, np.array([0.0, 0.0, 0.10]))
    elbow_r = (-0.85, -0.40, 0.10)
    for f, M, el in [(0, H0, (-0.6, -0.6, -0.5)), (6, hand_for(moved(b9, out_dir * 0.05)), (-0.8, -0.5, 0.3)), (9, hand_for(b9), (-0.8, -0.5, 0.3)),
                     (12, hand_for(carry1), (-0.9, -0.3, 0.2)), (17, hand_for(carry2), elbow_r), (23, hand_for(above), elbow_r),
                     (27, hand_for(ground), elbow_r), (30, hand_for(moved(ground, np.array([0.0, 0.03, 0.07]))), elbow_r), (n, H0, (-0.6, -0.6, -0.5))]:
        _apply_hand_matrix(c, 'r', f, M, el)
    Hrest = hand_for(moved(ground, np.array([0.02, 0.06, 0.16])))
    _apply_hand_matrix(c, 'r', 35, Hrest, elbow_r)
    for f, curl in [(0, 0.5), (6, 0.05), (9, 0.42), (27, 0.42), (29, 0.05), (36, 0.3), (n, 0.5)]:
        c.fingers('r', f, fist=0.0, spread=0.5 if curl < 0.2 else 0.25, thumb=curl * 0.8, index=curl, middle=curl, ring=curl, pinky=curl + 0.05)
    c.hold_grip('prop_beacon', 'hand_r', 0, G)
    for f, v in [(0, 0), (8, 0), (9, 1), (27, 1), (28, 0), (n, 0)]:
        c.prop_hold('prop_beacon', 'hand_r', f, v)
    c.dense.add(('prop_beacon', 'prop:hold_hand_r'))
    # after release the beacon stays on the ground: counter the pelvis motion frame by frame
    rest = c.R.rest
    smp2 = ctx.sample(c, list(range(28, n + 1)), ['pelvis'])
    for f in range(28, n + 1):
        M = np.linalg.inv(smp2[f]['pelvis'] @ np.linalg.inv(rest['pelvis']) @ rest['prop_beacon']) @ ground
        c.prop_basis('prop_beacon', f, M)
    c.prop_basis('prop_beacon', 0, np.eye(4))
    c.prop_basis('prop_beacon', 27, np.eye(4))
    c.dense.add(('prop_beacon', 'loc'))
    c.dense.add(('prop_beacon', 'rot'))
    c.events_replace([('deploy_grab', 9), ('deploy_release', 27), ('recovery', 34)])
    c.prop_tracks = [dict(prop='prop_beacon', holder='hand_r', frame_start=9, frame_end=27),
                     dict(prop='prop_beacon', holder='world', frame_start=28, frame_end=n, note='left on the ground (root space)')]

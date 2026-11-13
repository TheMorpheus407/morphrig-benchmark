"""Idles, starts/stops, turns, pivots, jumping, dashes and blink."""
import math
import numpy as np
from .animbuild import register
from .anim_base import (stand, ready, rotate_pose, foot_at, keys, breathe, gait_pose, with_face, fix_reach, rot2, interp,
                        FootPlan, apply_dense, kneel, foot_clear, dense_floor)
from .pose import Pose
from . import clips as clipdefs, gait


# ------------------------------------------------------------------------------------ idles
@register('idle_relaxed')
def idle_relaxed(c):
    S = with_face(stand())
    a = S
    b = S.mod(cog=(0.014, 0.004, -0.014), hips=(1.0, 2.0, 2.2), spine=(1.5, -3.0, -2.0), head=(-2.0, 12.0, 1.0),
              arm_l=dict(upper=(0.18, 0.05, -1.0), bend=22.0), arm_r=dict(upper=(0.20, -0.01, -1.0), bend=16.0), look=(1.6, 6.0, 1.70))
    b.foot_r['roll'] = 0.18
    d = S.mod(cog=(-0.018, -0.004, -0.016), hips=(1.0, -1.5, -2.6), spine=(0.5, 2.0, 2.4), head=(1.0, -9.0, -1.0),
              arm_l=dict(upper=(0.16, 0.00, -1.0), bend=15.0), arm_r=dict(upper=(0.19, 0.05, -1.0), bend=24.0), look=(-1.4, 6.0, 1.62))
    keys(c, [(0, a), (28, a.mod(head=(-1.0, 3.0, 0.0))), (46, b), (70, b.mod(head=(-3.0, 8.0, 1.5))), (92, d), (108, d.mod(head=(0.0, -4.0, 0.0))), (120, a)])
    breathe(c, 2, 0.55)
    c.blink(33)
    c.blink(97)
    c.fingers('l', 60, index=0.38, middle=0.30)
    c.fingers('l', 76, index=0.24, middle=0.26)


@register('idle_combat')
def idle_combat(c):
    R = with_face(ready())
    up = R.mod(cog=(R.cog[0] + 0.006, R.cog[1] + 0.01, R.cog[2] + 0.012), spine=(8.0, 10.0, 0.5), head=(-6.0, 15.0, 0.0),
               arm_l=dict(fore=(-0.38, 0.66, 0.64)), arm_r=dict(fore=(-0.10, 0.94, 0.33)))
    dn = R.mod(cog=(R.cog[0] - 0.006, R.cog[1] - 0.008, R.cog[2] - 0.010), spine=(10.0, 7.5, -0.5), head=(-5.0, 7.0, 0.0),
               arm_l=dict(fore=(-0.46, 0.58, 0.67)), arm_r=dict(fore=(-0.15, 0.90, 0.40)))
    up.foot_r['roll'] = 0.42
    dn.foot_r['roll'] = 0.22
    keys(c, [(0, R), (12, up), (30, dn), (45, R.mod(head=(-6.0, 4.0, 0.0), look=(-1.2, 6.0, 1.6))), (58, up), (75, dn), (90, R)])
    breathe(c, 2, 0.6)
    c.blink(40)


@register('idle_wounded')
def idle_wounded(c):
    R = ready()
    W = R.mod(cog=(0.030, -0.02, -0.105), cog_rot=(10.0, -6.0, -4.0), hips=(4.0, -4.0, 3.0), spine=(16.0, 4.0, -7.0),
              head=(-12.0, 6.0, 4.0), clav_l=(6.0, 10.0), clav_r=(-2.0, 0.0))
    W.foot_l.update(pos=(0.150, 0.06, 0.0), yaw=14.0)
    W.foot_r.update(pos=(-0.120, -0.10, 0.0), yaw=-22.0, roll=0.55)
    W.arm_r.update(upper=(0.22, 0.06, -1.0), fore=(0.02, 0.70, -0.60), hand=(10.0, 0.0, 20.0))
    W.fing_r.update(curl=0.35, thumb=0.2)
    W.fing_l.update(curl=0.30, thumb=0.25, spread=0.3)
    W = with_face(W, expr_pain=0.32, expr_focus=0.3)

    def clutch(p):
        """left hand pressed on the right flank (chest relative so it stays in contact while breathing)."""
        q = p.copy()
        q.arm_l.update(ik=True, pos=q.chest_point((-0.085, 0.118, -0.115)), fingers=q.chest_dir((-0.85, 0.10, -0.50)),
                       palm=q.chest_dir((0.25, -0.95, 0.10)), elbow=q.chest_dir((0.85, -0.10, -0.50)))
        return q
    a = clutch(W)
    b = clutch(W.mod(cog=(0.034, -0.016, -0.118), spine=(19.0, 3.0, -8.5), head=(-10.0, -8.0, 5.0), look=(-1.5, 6.0, 1.5)))
    b.face['expr_pain'] = 0.55
    d = clutch(W.mod(cog=(0.026, -0.024, -0.098), spine=(14.0, 6.0, -6.0), head=(-13.0, 16.0, 2.0), look=(1.5, 6.0, 1.6)))
    keys(c, [(0, a), (16, clutch(Pose.blend(W, b, 0.5))), (30, b), (52, a), (72, d), (96, a)])
    breathe(c, 3, 0.9)
    c.blink(20)
    c.blink(63, dur=7)


# ------------------------------------------------------------------------------------ start / stop
def _shift_from_speed(n, speed_fn, direction=(0.0, 1.0)):
    """Cumulative floor displacement (character space) for a forward speed profile in m/s."""
    acc = [0.0]
    for f in range(1, n + 2):
        acc.append(acc[-1] + 0.5 * (speed_fn(f - 1) + speed_fn(f)) / clipdefs.FPS)
    return lambda f: (-direction[0] * acc[int(min(max(f, 0), n + 1))], -direction[1] * acc[int(min(max(f, 0), n + 1))])


@register('start_f')
def start_f(c):
    n = c.frames
    v1 = clipdefs.RUN_SPEED / 100.0
    speed = lambda f: v1 * min(1.0, max(0.0, f) / float(n))
    shift = _shift_from_speed(n, speed)
    S = with_face(stand())
    G = with_face(gait_pose('run', 0.0), expr_focus=0.6)
    lean = Pose.blend(S, G, 0.35).mod(cog=(0.012, 0.050, -0.055), cog_rot=(9.0, 0.0, 1.0))
    drive = Pose.blend(S, G, 0.70).mod(cog=(0.0, 0.050, -0.090), cog_rot=(13.0, 0.0, 0.0))
    body = interp([(0, S), (3, lean), (6, drive), (n, G)], n)
    # left foot: planted, pushes off and lands as the loop's phase-0 contact; right foot: short first step
    gl, gr = G.foot_l, G.foot_r
    pl = FootPlan('l', S.foot_l['pos'], S.foot_l['yaw'], shift).step(6, n, gl['pos'], gl['yaw'], lift=0.16, roll_off=1.3, roll_on=gl['roll'], pitch=-45.0)
    # the right foot must be in the loop's early-swing pose at the last frame: contact at f4, lift-off at f9
    pr = FootPlan('r', S.foot_r['pos'], S.foot_r['yaw'], shift).step(1, 4, (-0.085, 0.24), -5.0, lift=0.07, roll_off=0.5, roll_on=-0.1, pitch=-8.0)
    pr.step(9, n + 6, (gr['pos'][0], 0.45), gr['yaw'], lift=0.26, roll_off=1.45, roll_on=0.0, pitch=-60.0)
    poses = apply_dense(c, body, [pl, pr])
    c.events_replace([('foot_r_contact', 4), ('foot_l_contact', n)])
    c.notes.update(speed_profile=[round(speed(f), 3) for f in range(n + 1)], exit_phase=0.0, exit_loop='run_f')


@register('stop_f')
def stop_f(c):
    n = c.frames
    v0 = clipdefs.RUN_SPEED / 100.0
    stop_at = n - 3
    speed = lambda f: v0 * max(0.0, 1.0 - max(0.0, f) / float(stop_at))
    shift = _shift_from_speed(n, speed)
    S = with_face(stand())
    G = with_face(gait_pose('run', 0.0), expr_focus=0.6)
    brake = Pose.blend(G, S, 0.30).mod(cog=(0.0, -0.045, -0.120), cog_rot=(-5.0, 0.0, 0.0), spine=(1.0, 0.0, 0.0))
    sink = Pose.blend(G, S, 0.65).mod(cog=(-0.015, -0.045, -0.150), cog_rot=(-2.0, 0.0, -1.0))
    rise = Pose.blend(G, S, 0.90).mod(cog=(-0.012, -0.015, -0.085), cog_rot=(2.0, 0.0, 0.0))
    body = interp([(0, G), (3, brake), (6, sink), (10, rise), (n, S)], n)
    total = lambda f: -shift(f)[1]
    end = total(n + 1)
    # right foot: currently swinging, lands as the braking step so that it ends exactly on its idle spot
    yr = S.foot_r['pos'][1] + (end - total(3))
    yl = S.foot_l['pos'][1] + (end - total(9))
    gl, gr = G.foot_l, G.foot_r
    pr = FootPlan('r', (gr['pos'][0], gr['pos'][1]), gr['yaw'], shift, roll=1.2)
    pr.segs[0]['f1'] = 0
    pr.segs = [dict(kind='stance', f0=-2, pos=(gr['pos'][0], gr['pos'][1] + (shift(0)[1] - shift(-2)[1]) * 0.0), yaw=gr['yaw'], roll_in=0.0, roll_out=1.2, f1=0)]
    pr.step(0, 3, (S.foot_r['pos'][0], yr), S.foot_r['yaw'], lift=0.10, roll_off=0.0, roll_on=-0.6, pitch=-10.0)
    pl = FootPlan('l', (gl['pos'][0], gl['pos'][1]), gl['yaw'], shift, roll=gl['roll'])
    pl.step(5, 9, (S.foot_l['pos'][0], yl), S.foot_l['yaw'], lift=0.10, roll_off=1.2, roll_on=-0.3, pitch=-25.0)
    poses = apply_dense(c, body, [pl, pr])
    # the incoming loop pose has the right foot already in the air: start the swing from where it is
    c.events_replace([('foot_r_contact', 3), ('foot_l_contact', 9)])
    c.notes.update(speed_profile=[round(speed(f), 3) for f in range(n + 1)], entry_phase=0.0, entry_loop='run_f')


# ------------------------------------------------------------------------------------ turns / pivots
def _turn_left(c, mirror=False):
    n = c.frames
    S = with_face(stand())
    E = rotate_pose(S, 90.0)
    lf, rf = E.foot_l, E.foot_r
    p3 = rotate_pose(S, 22.0).mod(head=(-2.0, 28.0, 0.0), look=rot2((0.0, 6.0, 1.66), 60.0))
    p3.foot_l = dict(S.foot_l, roll=0.5)
    p3.foot_r = dict(S.foot_r)
    p3.cog = (-0.03, 0.0, -0.03)
    p6 = rotate_pose(S, 45.0).mod(head=(-2.0, 22.0, 0.0))
    p6.foot_r = dict(S.foot_r)
    mid = tuple(0.5 * (a + b) for a, b in zip(S.foot_l['pos'], lf['pos']))
    p6.foot_l = dict(S.foot_l, pos=(mid[0], mid[1], 0.07), yaw=S.foot_l['yaw'] + 55.0, pitch=-10.0, roll=0.0)
    p6.cog = (-0.035, 0.0, -0.04)
    p8 = rotate_pose(S, 62.0).mod(head=(-1.0, 12.0, 0.0))
    p8.foot_l = dict(lf, roll=-0.2)
    p8.foot_r = dict(S.foot_r, roll=0.5)
    p8.cog = (-0.005, -0.01, -0.035)
    p11 = rotate_pose(S, 80.0).mod(head=(0.0, 5.0, 0.0))
    p11.foot_l = dict(lf)
    mid = tuple(0.5 * (a + b) for a, b in zip(S.foot_r['pos'], rf['pos']))
    p11.foot_r = dict(S.foot_r, pos=(mid[0], mid[1], 0.06), yaw=S.foot_r['yaw'] + 50.0, pitch=-8.0, roll=0.0)
    p11.cog = (E.cog[0] + 0.02, E.cog[1] + 0.0, -0.035)
    p14 = E.mod(cog=(E.cog[0], E.cog[1], -0.028))
    p14.foot_r = dict(rf, roll=-0.15)
    seq = [(0, S), (3, p3), (6, p6), (8, p8), (11, p11), (14, p14), (n, E)]
    ev = [('foot_l_contact', 8), ('foot_r_contact', 14)]
    if mirror:
        seq = [(f, p.mirrored()) for f, p in seq]
        ev = [('foot_r_contact', 8), ('foot_l_contact', 14)]
    keys(c, seq)
    c.events_replace(ev)
    c.notes.update(turn_yaw_deg=(-90.0 if mirror else 90.0))


@register('turn_l90')
def turn_l90(c):
    _turn_left(c, False)


@register('turn_r90')
def turn_r90(c):
    _turn_left(c, True)


def _pivot_left(c, mirror=False):
    """Run -> brake over the left foot, turn 180 degrees to the left -> run the other way (in place; the host
    reverses the travel velocity linearly over the clip)."""
    n = c.frames
    v = clipdefs.RUN_SPEED / 100.0
    half = n / 2.0
    speed = lambda f: v * (1.0 - min(max(f, 0), n) / half)
    shift = _shift_from_speed(n, speed)
    N = gait.CYCLE['run']['f']
    exit_phase = 5.0 / N
    G0 = with_face(gait_pose('run', 0.0), expr_focus=0.7)
    G1 = with_face(gait_pose('run', exit_phase), expr_focus=0.7)

    def body(t, yaw, drop, lean_back=0.0):
        p = Pose.blend(G0, G1, t)
        p = p.mod(cog=(p.cog[0], p.cog[1] - 0.03 * math.sin(math.pi * t), p.cog[2] - drop),
                  cog_rot=(p.cog_rot[0] * (1.0 - 1.6 * math.sin(math.pi * t)) - lean_back, p.cog_rot[1], 6.0 * math.sin(math.pi * t)),
                  head=(p.head[0], p.head[1] + 28.0 * math.sin(math.pi * t), 0.0))
        return rotate_pose(p, yaw)
    seq = [(0, body(0.0, 0.0, 0.0)), (3, body(0.22, 35.0, 0.13, 8.0)), (6, body(0.45, 95.0, 0.20, 4.0)), (9, body(0.65, 150.0, 0.17)),
           (12, body(0.85, 176.0, 0.08)), (n, body(1.0, 180.0, 0.0))]
    gl, gr = G0.foot_l, G0.foot_r
    e = rotate_pose(G1, 180.0)
    el, er = e.foot_l, e.foot_r
    sh = lambda f: shift(f)[1]
    yl_c = el['pos'][1] - (sh(n) - sh(11))
    pl = FootPlan('l', gl['pos'], gl['yaw'], shift, roll=gl['roll'])
    pl.step(6, 11, (el['pos'][0], yl_c), el['yaw'], lift=0.12, roll_off=0.8, roll_on=-0.1, pitch=-15.0)
    pr = FootPlan('r', gr['pos'], gr['yaw'], shift, roll=1.2)
    pr.segs = [dict(kind='stance', f0=-3, pos=(gr['pos'][0], gr['pos'][1]), yaw=gr['yaw'], roll_in=0.0, roll_out=1.2, f1=0)]
    pr.step(0, 4, (-0.24, 0.30), 80.0, lift=0.10, roll_off=0.0, roll_on=-0.2, pitch=-10.0)
    pr.step(12, n + 5, (er['pos'][0], er['pos'][1] - 0.35), er['yaw'], lift=0.22, roll_off=1.3, roll_on=0.0, pitch=-50.0)
    if mirror:
        seq = [(f, p.mirrored()) for f, p in seq]
        for plan in (pl, pr):
            plan.side = 'r' if plan.side == 'l' else 'l'
            for sg in plan.segs:
                sg['pos'] = (-sg['pos'][0], sg['pos'][1])
                sg['yaw'] = -sg['yaw']
    apply_dense(c, interp(seq, n), [pl, pr])
    ev = [('foot_r_contact', 4), ('foot_l_contact', 11)]
    if mirror:
        ev = [('foot_l_contact', 4), ('foot_r_contact', 11)]
    c.events_replace(ev)
    c.notes.update(turn_yaw_deg=(-180.0 if mirror else 180.0), entry_phase=(0.5 if mirror else 0.0),
                   exit_phase=((exit_phase + 0.5) % 1.0 if mirror else exit_phase), entry_loop='run_f', exit_loop='run_f',
                   speed_profile=[round(speed(f), 3) for f in range(n + 1)])


@register('pivot_l180')
def pivot_l180(c):
    _pivot_left(c, False)


@register('pivot_r180')
def pivot_r180(c):
    _pivot_left(c, True)


# ------------------------------------------------------------------------------------ air
def _air_tuck():
    R = with_face(ready(), expr_focus=0.6)
    p = R.mod(cog=(0.0, 0.0, 0.02), cog_rot=(6.0, -4.0, 0.0), hips=(8.0, -2.0, 0.0), spine=(8.0, 3.0, 0.0), head=(-8.0, 4.0, 0.0))
    p.foot_l = foot_at((0.11, 0.16, 0.36), yaw=4.0, pitch=-28.0, knee=(0.12, 1.0, 0.25))
    p.foot_r = foot_at((-0.12, -0.10, 0.26), yaw=-8.0, pitch=-42.0, knee=(-0.12, 1.0, 0.0))
    p.arm_l.update(upper=(0.62, 0.32, -0.50), fore=(0.25, 0.80, 0.30), hand=(0.0, 0.0, 30.0))
    p.arm_r.update(upper=(0.66, 0.10, -0.55), fore=(0.20, 0.88, 0.15), hand=(0.0, 0.0, 30.0))
    p.fing_l.update(curl=0.35, spread=0.4)
    p.fing_r.update(curl=0.35, spread=0.4)
    return p


@register('jump_start')
def jump_start(c):
    S = with_face(stand(), expr_focus=0.5)
    cr = S.mod(cog=(0.0, 0.02, -0.26), cog_rot=(18.0, 0.0, 0.0), hips=(10.0, 0.0, 0.0), spine=(10.0, 0.0, 0.0), head=(-18.0, 0.0, 0.0),
               arm_l=dict(upper=(0.28, -0.55, -0.80), bend=30.0), arm_r=dict(upper=(0.28, -0.55, -0.80), bend=30.0))
    cr.foot_l['roll'] = 0.0
    ext = S.mod(cog=(0.0, 0.03, 0.045), cog_rot=(-3.0, 0.0, 0.0), spine=(-4.0, 0.0, 0.0), head=(4.0, 0.0, 0.0),
                arm_l=dict(upper=(0.30, 0.55, 0.20), bend=40.0), arm_r=dict(upper=(0.30, 0.55, 0.20), bend=40.0))
    ext.foot_l.update(roll=1.35)
    ext.foot_r.update(roll=1.35)
    air = _air_tuck()
    off = Pose.blend(ext, air, 0.45)
    off.foot_l = foot_at((0.105, 0.02, 0.30), yaw=6.0, pitch=-55.0)
    off.foot_r = foot_at((-0.105, -0.03, 0.30), yaw=-6.0, pitch=-58.0)
    off.cog = (0.0, 0.02, 0.05)
    keys(c, [(0, S), (4, cr), (6, ext), (c.frames, off)])
    c.events_replace([('jump_takeoff', 6)])
    fix_reach([cr, ext])


@register('jump_air')
def jump_air(c):
    a = _air_tuck()
    b = a.mod(cog=(0.0, 0.0, 0.03), spine=(6.0, 2.0, 0.0), head=(-6.0, 4.0, 0.0),
              arm_l=dict(upper=(0.70, 0.22, -0.40), fore=(0.35, 0.78, 0.36)), arm_r=dict(upper=(0.72, 0.02, -0.46), fore=(0.28, 0.86, 0.22)))
    b.foot_l = foot_at((0.115, 0.13, 0.33), yaw=4.0, pitch=-24.0, knee=(0.12, 1.0, 0.25))
    b.foot_r = foot_at((-0.125, -0.13, 0.24), yaw=-8.0, pitch=-46.0, knee=(-0.12, 1.0, 0.0))
    keys(c, [(0, a), (10, b), (20, a)])


@register('fall')
def fall(c):
    R = with_face(ready(), expr_surprise=0.25, expr_focus=0.5)
    a = R.mod(cog=(0.0, 0.0, 0.03), cog_rot=(14.0, -3.0, 0.0), hips=(4.0, 0.0, 0.0), spine=(4.0, 2.0, 0.0), head=(8.0, 3.0, 0.0), look=(0.0, 2.0, 0.0))
    a.foot_l = foot_at((0.21, 0.10, 0.24), yaw=12.0, pitch=-30.0, knee=(0.30, 1.0, 0.0))
    a.foot_r = foot_at((-0.22, -0.16, 0.25), yaw=-14.0, pitch=-38.0, knee=(-0.30, 1.0, -0.1))
    a.arm_l.update(upper=(0.80, 0.10, 0.36), fore=(0.55, 0.30, 0.78), hand=(-10.0, 0.0, 20.0))
    a.arm_r.update(upper=(0.82, -0.05, 0.30), fore=(0.60, 0.25, 0.76), hand=(-10.0, 0.0, 20.0))
    a.fing_l.update(curl=0.15, spread=0.8)
    a.fing_r.update(curl=0.15, spread=0.8)
    b = a.mod(cog_rot=(17.0, 3.0, 2.0), spine=(6.0, -3.0, -2.0), arm_l=dict(upper=(0.76, 0.22, 0.46), fore=(0.42, 0.42, 0.80)),
              arm_r=dict(upper=(0.86, -0.16, 0.20), fore=(0.66, 0.12, 0.72)))
    b.foot_l = foot_at((0.19, 0.16, 0.27), yaw=10.0, pitch=-24.0, knee=(0.30, 1.0, 0.0))
    b.foot_r = foot_at((-0.24, -0.20, 0.24), yaw=-16.0, pitch=-40.0, knee=(-0.30, 1.0, -0.1))
    keys(c, [(0, a), (8, b), (16, a)])


@register('jump_land')
def jump_land(c):
    R = with_face(ready())
    hit = R.mod(cog=(0.0, 0.0, 0.02), cog_rot=(8.0, -8.0, 0.0), arm_l=dict(upper=(0.55, 0.35, -0.60), fore=(0.10, 0.85, 0.30)),
                arm_r=dict(upper=(0.58, 0.20, -0.62), fore=(0.05, 0.90, 0.25)))
    hit.foot_l.update(roll=0.9)
    hit.foot_r.update(roll=1.0)
    low = R.mod(cog=(R.cog[0], R.cog[1] + 0.02, -0.30), cog_rot=(20.0, -10.0, 0.0), hips=(10.0, -6.0, 0.0), spine=(12.0, 8.0, 0.0),
                head=(-20.0, 10.0, 0.0), arm_l=dict(upper=(0.45, 0.60, -0.55), fore=(-0.10, 0.80, -0.40)),
                arm_r=dict(upper=(0.50, 0.40, -0.70), fore=(-0.05, 0.85, -0.35)))
    low.foot_r.update(roll=0.55)
    keys(c, [(0, hit), (4, low), (9, Pose.blend(low, R, 0.75)), (c.frames, R)])
    c.events_replace([('land_impact', 0), ('foot_l_contact', 0), ('foot_r_contact', 0)])
    fix_reach([hit, low])


@register('land_heavy')
def land_heavy(c):
    """Three-point landing: left knee and right fist take the impact, then a deliberate push back up."""
    R = with_face(ready())
    hit = R.mod(cog=(0.0, 0.02, -0.04), cog_rot=(10.0, -6.0, 0.0), arm_l=dict(upper=(0.70, 0.20, -0.30), fore=(0.30, 0.70, 0.30)))
    hit.foot_r.update(pos=(-0.150, 0.06, 0.0), yaw=-10.0, roll=0.0)
    fist = (-0.20, 0.36, 0.060)
    low = kneel(hit, knee='l', lean=58.0, wrist=fist, wrist_side='r', back=0.30)
    hit.foot_l = dict(low.foot_l)                 # lands on the ball of the rear foot, knee still off the ground
    hit.foot_r = dict(low.foot_r)
    hit.cog = (low.cog[0], low.cog[1] + 0.03, low.cog[2] + 0.30)
    low.arm_r.update(ik=True, pos=fist, fingers=(0.10, 0.55, -0.83), palm=(0.0, -0.85, -0.5), elbow=(-0.9, -0.2, 0.4))
    low.fing_r.update(curl=1.0, thumb=0.8, spread=0.0)
    low.arm_l.update(upper=(0.80, -0.35, 0.10), fore=(0.70, -0.60, 0.40), hand=(0.0, 0.0, 20.0))
    low.head = (-30.0, 6.0, 0.0)
    low.look = (0.0, 3.0, 0.5)
    low = with_face(low, expr_pain=0.25, expr_focus=0.7)
    hit.arm_r.update(ik=True, pos=hit.chest_point((-0.26, 0.36, -0.30)), fingers=(0.0, 0.8, -0.6), palm=(0.0, -0.6, -0.8), elbow=(-0.8, -0.4, 0.0))
    hit.fing_r.update(curl=1.0, thumb=0.8)
    hold = low.mod(head=(-12.0, 6.0, 0.0), look=(0.0, 6.0, 1.3))
    up = Pose.blend(low, R, 0.55)
    up.foot_l = foot_clear(R.foot_l['pos'][0], R.foot_l['pos'][1] - 0.16, yaw=10.0, pitch=-35.0, clear=0.03, knee=(0.1, 1.0, -0.1))
    up.foot_r = dict(low.foot_r)
    up.arm_r.update(ik=True, pos=(-0.26, 0.30, 0.62), fingers=(0.0, 0.9, -0.3), palm=(0.2, -0.3, -0.9), elbow=(-0.8, -0.4, -0.2))
    Rk = R.copy()
    Rk.arm_r.update(ik=True, pos=Rk.chest_point((-0.26, 0.30, -0.26)), fingers=Rk.chest_dir((0.10, 0.92, 0.36)), palm=Rk.chest_dir((0.5, 0.0, -0.8)),
                    elbow=(-0.6, -0.6, -0.5))
    pre = Rk.copy()
    pre.foot_r = dict(R.foot_r, pos=(-0.150, -0.06, 0.07), roll=0.0, pitch=-8.0)
    fix_reach([hit, up, pre])
    dense_floor(c, [(0, hit), (5, low), (11, hold), (17, up), (21, pre), (c.frames, Rk)])
    c.events_replace([('land_impact', 0), ('foot_l_contact', 0), ('foot_r_contact', 0), ('hand_plant', 5), ('foot_l_contact', 19), ('foot_r_contact', 24)])


# ------------------------------------------------------------------------------------ dashes (root motion)
def _dash(c, direction):
    n = c.frames
    ang = {'f': 0.0, 'b': 180.0, 'l': 90.0, 'r': -90.0}[direction]
    d = rot2((0.0, 1.0), ang)                     # travel direction (left, forward)
    D = clipdefs.DASH_DISTANCE / 100.0

    def travel(f):
        # push-off eases in while the feet are still planted, the leap covers the distance, the landing eases out
        t = min(1.0, max(0.0, (f - 1.0) / (n - 3.0)))
        return D * (t * t * (3.0 - 2.0 * t))
    R = with_face(ready(), expr_focus=0.8)
    lean = 22.0
    low = R.mod(cog=(R.cog[0] + d[0] * 0.10, R.cog[1] + d[1] * 0.10, -0.20),
                cog_rot=(R.cog_rot[0] + lean * d[1], R.cog_rot[1], lean * d[0] * 0.8), spine=(R.spine[0] + 6.0 * d[1], R.spine[1], 6.0 * d[0]),
                head=(R.head[0] - 10.0 * d[1], R.head[1], -4.0 * d[0]))
    # leading / trailing legs relative to the dash direction
    lead = (d[0] * 0.26, d[1] * 0.26)
    trail = (-d[0] * 0.28, -d[1] * 0.28)
    side = (d[1] * 0.12, -d[0] * 0.12)             # perpendicular (to the character's left when dashing forward... rotated)
    if direction == 'f':
        low.foot_l = foot_at((0.12 + lead[0], lead[1] + 0.02, 0.14), yaw=6.0, pitch=10.0, knee=(0.1, 1.0, 0.1))
        low.foot_r = foot_at((-0.14 + trail[0], trail[1], 0.24), yaw=-20.0, pitch=-50.0, knee=(-0.2, 1.0, -0.2))
        low.arm_l.update(upper=(0.35, 0.10, -0.90), fore=(-0.30, 0.70, 0.55))
        low.arm_r.update(upper=(0.40, -0.55, -0.60), fore=(0.20, -0.20, -0.90))
    elif direction == 'b':
        low.foot_r = foot_at((-0.14 + lead[0], lead[1], 0.19), yaw=-30.0, pitch=-35.0, knee=(-0.3, 1.0, 0.0))
        low.foot_l = foot_at((0.13 + trail[0], trail[1] + 0.02, 0.13), yaw=8.0, pitch=24.0, knee=(0.15, 1.0, 0.2))
        low.arm_l.update(upper=(0.30, 0.65, -0.55), fore=(-0.25, 0.80, 0.45))
        low.arm_r.update(upper=(0.34, 0.45, -0.70), fore=(-0.10, 0.95, 0.20))
    elif direction == 'l':
        low.foot_l = foot_at((0.14 + lead[0], lead[1] + 0.05, 0.13), yaw=30.0, pitch=-10.0, knee=(0.5, 0.9, 0.0))
        low.foot_r = foot_at((-0.10 + trail[0], trail[1] - 0.10, 0.21), yaw=-10.0, pitch=-40.0, lean=-20.0, knee=(-0.1, 1.0, 0.0))
        low.arm_l.update(upper=(0.75, 0.25, -0.50), fore=(0.20, 0.85, 0.30))
        low.arm_r.update(upper=(0.25, 0.30, -0.90), fore=(-0.55, 0.70, 0.35))
    else:
        low.foot_r = foot_at((-0.16 + lead[0], lead[1] - 0.06, 0.13), yaw=-52.0, pitch=-10.0, knee=(-0.6, 0.8, 0.0))
        low.foot_l = foot_at((0.10 + trail[0], trail[1] + 0.06, 0.21), yaw=4.0, pitch=-40.0, lean=20.0, knee=(0.1, 1.0, 0.0))
        low.arm_r.update(upper=(0.75, 0.20, -0.50), fore=(0.20, 0.88, 0.25))
        low.arm_l.update(upper=(0.28, 0.55, -0.78), fore=(-0.55, 0.60, 0.50))
    shift = lambda f: (-d[0] * travel(min(max(f, 0), n)), -d[1] * travel(min(max(f, 0), n)))
    push = Pose.blend(R, low, 0.55)
    land = Pose.blend(low, R, 0.7)
    land.cog = (R.cog[0] - d[0] * 0.03, R.cog[1] - d[1] * 0.03, -0.20)
    seq = [(0, R), (2, push), (5, low), (8, low.mod(cog=(low.cog[0], low.cog[1], low.cog[2] + 0.02))), (n - 2, land), (n, R)]
    plans = []
    for s in ('l', 'r'):
        fr = getattr(R, 'foot_' + s)
        via = dict(getattr(low, 'foot_' + s))
        f_on = n - 2
        rem = (shift(n)[0] - shift(f_on)[0], shift(n)[1] - shift(f_on)[1])
        # the leg that trails the dash pushes one frame longer
        trailing = (d[0] * fr['pos'][0] + d[1] * fr['pos'][1]) < 0
        f_off = 3 if trailing else 2
        pl = FootPlan(s, fr['pos'], fr['yaw'], shift, roll=fr['roll'])
        pl.step(f_off, f_on, (fr['pos'][0] - rem[0], fr['pos'][1] - rem[1]), fr['yaw'], lift=0.12, roll_off=1.0,
                roll_on=(fr['roll'] if trailing else -0.3), via=via)
        plans.append(pl)
    apply_dense(c, interp(seq, n), plans)
    for f in range(0, n + 1):
        sv = travel(f)
        c.root(f, pos=(d[0] * sv, d[1] * sv, 0.0))
    c.dense.add(('root', 'loc'))
    c.dense.add(('root', 'rot'))
    c.events_replace([('dash_start', 2), ('dash_end', n - 2), ('foot_l_contact', n - 2), ('foot_r_contact', n - 2)])
    c.notes.update(root_travel=[round(travel(f), 4) for f in range(n + 1)])


def _make_dash(direction):
    def build(c):
        _dash(c, direction)
    return build


for _d in ('f', 'b', 'l', 'r'):
    register('dash_' + _d)(_make_dash(_d))


# ------------------------------------------------------------------------------------ blink
@register('blink_out')
def blink_out(c):
    R = with_face(ready(), expr_focus=0.8)
    coil = R.mod(cog=(R.cog[0], R.cog[1] - 0.02, -0.26), cog_rot=(16.0, -10.0, 0.0), spine=(14.0, 6.0, 0.0), head=(-14.0, 10.0, 0.0),
                 arm_l=dict(upper=(0.25, 0.30, -0.95), fore=(-0.50, 0.60, 0.45)), arm_r=dict(upper=(0.25, 0.20, -0.95), fore=(-0.45, 0.70, 0.40)))
    coil.fing_l.update(curl=0.9)
    coil.fing_r.update(curl=0.9)
    burst = R.mod(cog=(R.cog[0], R.cog[1] + 0.10, 0.03), cog_rot=(-4.0, -4.0, 0.0), spine=(-8.0, 4.0, 0.0), head=(8.0, 4.0, 0.0),
                  arm_l=dict(upper=(0.75, -0.25, -0.45), fore=(0.70, -0.50, -0.30)), arm_r=dict(upper=(0.75, -0.30, -0.45), fore=(0.70, -0.55, -0.30)))
    burst.foot_l.update(roll=1.4)
    burst.foot_r.update(roll=1.45)
    burst.fing_l.update(curl=0.0, spread=1.0)
    burst.fing_r.update(curl=0.0, spread=1.0)
    keys(c, [(0, R), (5, coil), (c.frames, burst)])
    c.events_replace([('blink_vanish', c.frames - 1)])
    fix_reach([coil, burst])


@register('blink_in')
def blink_in(c):
    R = with_face(ready(), expr_focus=0.8)
    arrive = R.mod(cog=(R.cog[0], R.cog[1] - 0.04, 0.02), cog_rot=(-6.0, -8.0, 0.0), spine=(-6.0, 6.0, 0.0), head=(6.0, 8.0, 0.0),
                   arm_l=dict(upper=(0.80, -0.10, -0.30), fore=(0.75, 0.20, 0.30)), arm_r=dict(upper=(0.80, -0.20, -0.30), fore=(0.75, 0.10, 0.25)))
    arrive.foot_l.update(roll=1.2)
    arrive.foot_r.update(roll=1.3)
    arrive.fing_l.update(curl=0.0, spread=1.0)
    arrive.fing_r.update(curl=0.0, spread=1.0)
    plant = R.mod(cog=(R.cog[0], R.cog[1] + 0.02, -0.25), cog_rot=(16.0, -12.0, 0.0), spine=(12.0, 9.0, 0.0), head=(-14.0, 11.0, 0.0),
                  arm_l=dict(upper=(0.45, 0.45, -0.70), fore=(-0.20, 0.80, 0.10)), arm_r=dict(upper=(0.50, 0.25, -0.80), fore=(-0.05, 0.90, 0.0)))
    keys(c, [(0, arrive), (4, plant), (8, Pose.blend(plant, R, 0.8)), (c.frames, R)])
    c.events_replace([('blink_appear', 0), ('foot_l_contact', 3), ('foot_r_contact', 3)])
    fix_reach([arrive, plant])

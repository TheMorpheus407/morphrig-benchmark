"""Procedural gait generator: directional walk, run and sprint cycles from a body-frame velocity.

Feet are IK targets on the ground: stance feet move at -v (planted in the world), swing feet follow a lifted arc, with heel-to-toe
roll (rig property `roll`). Pelvis bob, sway, yaw, torso counter-rotation and arm swing are phase functions; the pelvis height is
limited by a leg-reach clamp so IK never over-extends. Strafing and backward gaits use cross-behind steps to keep feet apart."""
import math
import numpy as np
from mathutils import Vector
import skeleton_def as S
import anim_lib as AL
from anim_lib import Pose, Clip, arm_fk, hand_pose, spine_pose, DEG, ease
import pose_lib as PL

LEG = 0.845          # usable leg length (hip joint to ankle), slightly less than 0.852 to stay off the singularity
HIP_H = 0.940
ANK_H = 0.088


def minjerk(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * s * (10 - 15 * s + 6 * s * s)


def softmin(a, b, k=50.0):
    return -math.log(math.exp(-k * a) + math.exp(-k * b)) / k


STYLES = {
    'walk': dict(duty=0.62, h=0.085, bob=0.022, sway=0.030, pyaw=5.0, spine=7.0, arm=24.0, elbow=(16, 10), heel=14.0, toe=34.0, drop=0.055, lean=2.0, flight=False, head_stab=0.6),
    'run': dict(duty=0.40, h=0.17, bob=0.040, sway=0.018, pyaw=8.0, spine=14.0, arm=46.0, elbow=(80, 28), heel=5.0, toe=42.0, drop=0.10, lean=9.0, flight=True, head_stab=0.7),
    'sprint': dict(duty=0.30, h=0.22, bob=0.050, sway=0.014, pyaw=10.0, spine=18.0, arm=62.0, elbow=(92, 30), heel=2.0, toe=48.0, drop=0.13, lean=20.0, flight=True, head_stab=0.8),
}


def foot_state(phi, T, v_b, st, cross_dx):
    """Foot offset (x, y, z), roll for a foot at phase phi in [0,1). v_b = body-frame velocity (m/s) as Vector(x,y)."""
    duty = st['duty']
    D = Vector((v_b.x, v_b.y)) * (T * duty)
    if phi < duty:
        u = phi / duty
        p = D * (0.5 - u)
        z = 0.0
        if u < 0.13:
            roll = -st['heel'] * (1 - u / 0.13)
        elif u < 0.55:
            roll = 0.0
        else:
            roll = st['toe'] * ((u - 0.55) / 0.45) ** 1.2
        return p.x, p.y, z, roll, u, True
    s = (phi - duty) / (1 - duty)
    e = minjerk(s)
    p = -D * 0.5 + D * e
    z = st['h'] * math.sin(math.pi * s) ** 0.9
    x_extra = -cross_dx * math.sin(math.pi * s)
    if s < 0.3:
        roll = st['toe'] * (1 - s / 0.3)
    else:
        roll = -st['heel'] * 0.7 * ((s - 0.3) / 0.7)
    return p.x + x_extra, p.y, z, roll, s, False


def gait_model(style, dir_deg, speed_cm_s, T, arm_l_scale=0.6):
    """Return f(phi) -> Pose for the gait (phi in [0,1)); T = cycle time in seconds."""
    st = STYLES[style]
    th = math.radians(dir_deg)
    v = speed_cm_s / 100.0
    v_b = Vector((v * math.cos(th), v * math.sin(th)))
    lat = abs(math.sin(th))
    back = max(0.0, -math.cos(th))
    cross = 0.13 * lat * (1.0 if style == 'walk' else 1.4)
    lean_f = st['lean'] * (math.cos(th) if math.cos(th) > 0 else 0.15 * math.cos(th))
    lean_side = -(6.0 if style == 'walk' else 9.0) * math.sin(th) * (v / (1.5 if style == 'walk' else 3.5))
    duty = st['duty']

    def pose_at(phi):
        phi = phi % 1.0
        p = Pose()
        feet = {}
        for s, off in (('l', 0.0), ('r', 0.5)):
            pf = (phi + off) % 1.0
            x, y, z, roll, u, stance = foot_state(pf, T, v_b, st, cross)
            yaw = 6.0 * math.sin(th) * (1 if s == 'l' else -1) * 0.4
            feet[s] = dict(x=x, y=y, z=z, roll=roll, yaw=yaw)
        if st['flight']:
            zb = -st['bob'] * math.cos(4 * math.pi * (phi - duty / 2))
        else:
            zb = st['bob'] * math.cos(4 * math.pi * (phi - duty / 2)) - st['bob'] * 0.8
        z_des = -st['drop'] + zb
        pel_y = st['sway'] * math.cos(2 * math.pi * (phi - duty / 2)) * (0.6 if lat > 0.5 else 1.0)
        pel_x = -0.010 * math.cos(4 * math.pi * phi)
        z_lim = 9.0
        for s, sy in (('l', 1.0), ('r', -1.0)):
            f_ = feet[s]
            ank_x = S.ANKLE[0] + f_['x']
            ank_y = sy * S.ANKLE[1] + f_['y']
            hip_x, hip_y = S.HIP[0] + pel_x, sy * S.HIP[1] + pel_y
            roll = f_['roll']
            ankle_z = ANK_H + f_['z']
            if roll > 0:
                r = math.radians(min(roll, 40.0))
                ankle_z += 0.136 * math.sin(r) + 0.088 * (math.cos(r) - 1)
            d2 = LEG ** 2 - (ank_x - hip_x) ** 2 - (ank_y - hip_y) ** 2
            z_lim = softmin(z_lim, math.sqrt(max(d2, 0.02)) + ankle_z - HIP_H - 0.004)
        pel_z = softmin(z_des, z_lim)
        p.update(PL.pelvis_pose(x=pel_x, y=pel_y, z=pel_z, roll=2.0 * math.sin(2 * math.pi * phi) * (1.0 if not st['flight'] else 0.6) + lean_side,
                                 pitch=lean_f * 0.5, yaw=-st['pyaw'] * math.cos(2 * math.pi * phi) * (0.5 if lat > 0.7 else 1.0)))
        p.update(PL.feet_pose(feet['l'], feet['r']))
        twist = st['spine'] * math.cos(2 * math.pi * phi) * (0.5 if lat > 0.7 else 1.0)
        p.update(spine_pose(flex=lean_f * 0.6, twist=twist, side=-1.5 * math.sin(2 * math.pi * phi)))
        p.update(AL.neck_head(flex=-lean_f * 0.55 * st['head_stab'], twist=-twist * 0.35, side=0.0))
        amp = st['arm'] * (0.45 if lat > 0.6 else 1.0) * (0.75 if back > 0.5 else 1.0)
        sw = math.cos(2 * math.pi * phi)
        e0, e1 = st['elbow']
        for s, sy in (('l', 1.0), ('r', -1.0)):
            sc = arm_l_scale if s == 'l' else 1.0
            ph = -sw if s == 'l' else sw
            flex = amp * sc * ph
            elbow = e0 + e1 * (0.5 - 0.5 * ph) * (0.6 if style == 'walk' else 1.0)
            abd = -16.0 - (4 if style != 'walk' else 0) + 3.0 * lat
            p.update(arm_fk(s, flex=flex + (0 if style == 'walk' else 10), abd=abd, elbow=elbow, wrist_flex=-6.0))
        p.update(hand_pose('l', curl=0.55 if style != 'walk' else 0.3))
        p.update(hand_pose('r', curl=0.55 if style != 'walk' else 0.3))
        return p
    return pose_at


def gait_clip(cid, entry, style, dir_deg, speed_cm_s, arm_l_scale=0.6):
    st = STYLES[style]
    N = entry['frames']
    T = N / AL.FPS
    duty = st['duty']
    clip = Clip(cid, N, loop=True, root='in_place', form='loop', layer='full', speed_cm_s=speed_cm_s,
                note=f'procedural {style} gait, direction {dir_deg} deg, nominal {speed_cm_s} cm/s')
    clip.meta.update({'generator': 'gait.py', 'style': style, 'direction_deg': dir_deg, 'duty': duty, 'cycle_s': T})
    model = gait_model(style, dir_deg, speed_cm_s, T, arm_l_scale)
    for f in range(N + 1):
        clip.key(f, model(f / N))
    contacts = []
    for s, off in (('l', 0.0), ('r', 0.5)):
        td = round(((0.0 - off) % 1.0) * N) % N
        lo = round((((duty - off) % 1.0)) * N) % N
        clip.event('foot_plant', td, foot=s)
        clip.event('foot_lift', lo, foot=s)
        contacts.append({'foot': s, 'plant_frame': td, 'lift_frame': lo})
    clip.contacts = contacts
    return clip

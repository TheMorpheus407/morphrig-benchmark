"""Semantic key poses for the hand-authored clips.

A key pose is a plain dict (see resolve()). Feet and hands can be given in WORLD coordinates (metres, +X forward, +Y left) and are
converted to root-relative controls, so planted feet stay planted while the root translates or yaws. The pelvis is world-aligned
(rotate it to lay the body down); ctl_root only carries root motion and turn yaw."""
import math
import numpy as np
from mathutils import Vector, Matrix, Quaternion
import skeleton_def as S
import anim_lib as AL
from anim_lib import Pose, Clip, DEG
import pose_lib as PL
import face_lib as FL

LEG = 0.845
HIP_H = 0.940
ANK_H = 0.088
REST_ANK = {s: np.array([S.BONE_BY_NAME[f'foot_{s}'].head[0], S.BONE_BY_NAME[f'foot_{s}'].head[1]]) for s in ('l', 'r')}
SHOULDER = {s: Vector((S.SHOULDER[0], sy * S.SHOULDER[1], S.SHOULDER[2])) for s, sy in (('l', 1.0), ('r', -1.0))}


def softmin(a, b, k=60.0):
    return -math.log(math.exp(-k * a) + math.exp(-k * b)) / k


def rot2(v, yaw_deg):
    c, s = math.cos(yaw_deg * DEG), math.sin(yaw_deg * DEG)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def plant(side, x, y, yaw=0.0, z=0.0, roll=0.0, root=(0.0, 0.0), root_yaw=0.0, pitch=0.0, bank=0.0):
    """World foot placement -> root-relative foot dict. (x, y) is the ground anchor under the ankle in world metres."""
    rel = rot2(np.array([x - root[0], y - root[1]]), -root_yaw) - REST_ANK[side]
    return dict(x=float(rel[0]), y=float(rel[1]), z=z, yaw=yaw - root_yaw, roll=roll, pitch=pitch, bank=bank)


def foot_rest(side, **kw):
    d = dict(x=0.0, y=0.0, z=0.0, yaw=0.0, roll=0.0, pitch=0.0, bank=0.0)
    d.update(kw)
    return d


def world_to_root(p_world, root=(0.0, 0.0, 0.0), root_yaw=0.0):
    p = np.array([p_world[0] - root[0], p_world[1] - root[1]])
    r = rot2(p, -root_yaw)
    return Vector((r[0], r[1], p_world[2] - root[2]))


def aim_dir(yaw_deg, pitch_deg):
    y, p = yaw_deg * DEG, pitch_deg * DEG
    return Vector((math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)))


def _reach_limit(pel, feet, ang_pitch=0.0):
    lim = 9.0
    for s, sy in (('l', 1.0), ('r', -1.0)):
        f = feet[s]
        ax = S.ANKLE[0] + f.get('x', 0.0)
        ay = sy * S.ANKLE[1] + f.get('y', 0.0)
        az = ANK_H + f.get('z', 0.0)
        roll = f.get('roll', 0.0)
        if roll > 0:
            r = math.radians(min(roll, 40.0))
            az += 0.136 * math.sin(r) + 0.088 * (math.cos(r) - 1)
        hx, hy = S.HIP[0] + pel[0], sy * S.HIP[1] + pel[1]
        d2 = LEG ** 2 - (ax - hx) ** 2 - (ay - hy) ** 2
        need = math.sqrt(max(d2, 0.02)) + az - HIP_H
        lim = softmin(lim, need - 0.004)
    return lim


def _elbow_hint(side, shoulder, target, out=(-0.35, 0.55, -0.55)):
    sy = 1.0 if side == 'l' else -1.0
    ax = (Vector(target) - shoulder)
    ln = max(ax.length, 1e-4)
    axn = ax / ln
    d = Vector((out[0], sy * out[1], out[2]))
    d = d - axn * d.dot(axn)
    if d.length < 1e-4:
        d = Vector((0, sy, 0))
    d.normalize()
    return (shoulder + Vector(target)) * 0.5 + d * 0.45


def resolve(k):
    """Resolve a key-pose dict to a Pose. Keys:
    root=(x,y,z) root_yaw   pelvis=(x,y,z) pelvis_rot=(roll,pitch,yaw)   spine=(flex,twist,side) neck=(flex,twist,side)
    fl, fr = foot dicts (root-relative; use plant())   al, ar = arm specs   hl, hr = hand dicts   face=Pose   extra=Pose
    arm spec: ('fk', {flex,abd,roll,elbow,wrist_flex,wrist_dev,wrist_roll,clav}) | ('ik', {target, dir, roll, elbow_hint})
              | ('aim', {yaw, pitch, reach, roll, elbow_hint})   (targets in root-relative metres)
    reach: False disables the pelvis reach clamp."""
    p = Pose()
    root = k.get('root', (0.0, 0.0, 0.0))
    p.loc('ctl_root', root)
    p.rot('ctl_root', (0.0, 0.0, k.get('root_yaw', 0.0)))
    pel = k.get('pelvis', (0.0, 0.0, -0.03))
    feet = {'l': k.get('fl') or foot_rest('l'), 'r': k.get('fr') or foot_rest('r')}
    pz = pel[2]
    if k.get('reach', True):
        pz = softmin(pel[2], _reach_limit(pel, feet))
    p.update(PL.pelvis_pose(x=pel[0], y=pel[1], z=pz, roll=k.get('pelvis_rot', (0, 0, 0))[0], pitch=k.get('pelvis_rot', (0, 0, 0))[1], yaw=k.get('pelvis_rot', (0, 0, 0))[2]))
    p.update(PL.feet_pose(feet['l'], feet['r']))
    sp = k.get('spine', (0.0, 0.0, 0.0))
    p.update(AL.spine_pose(flex=sp[0], twist=sp[1], side=sp[2]))
    nk = k.get('neck', (0.0, 0.0, 0.0))
    p.update(AL.neck_head(flex=nk[0], twist=nk[1], side=nk[2]))
    for s, key in (('l', 'hl'), ('r', 'hr')):
        h = k.get(key, {})
        p.update(AL.hand_pose(s, curl=h.get('curl', 0.25), spread=h.get('spread', 0.0), thumb=h.get('thumb', 0.0), index=h.get('index', 0.0),
                              middle=h.get('middle', 0.0), ring=h.get('ring', 0.0), pinky=h.get('pinky', 0.0)))
    arm_specs = {}
    for s, key in (('l', 'al'), ('r', 'ar')):
        spec = k.get(key) or ('fk', dict(flex=4, abd=-20, elbow=14))
        arm_specs[s] = spec
        if spec[0] == 'fk':
            d = dict(spec[1])
            if 'wflex' in d:
                d['wrist_flex'] = d.pop('wflex')
            if 'wdev' in d:
                d['wrist_dev'] = d.pop('wdev')
            if 'wroll' in d:
                d['wrist_roll'] = d.pop('wroll')
            p.update(AL.arm_fk(s, **d))
    if any(v[0] != 'fk' for v in arm_specs.values()):
        # evaluate the torso to get the real shoulder positions, then solve IK targets
        ev = PL.evaluate(p)
        for s in ('l', 'r'):
            spec = arm_specs[s]
            if spec[0] == 'fk':
                continue
            d = spec[1]
            sh = Vector(PL.head_of(ev, f'def_upperarm_{s}'))
            root_loc = Vector((p.get(('ctl_root', 'loc', 0), 0.0), p.get(('ctl_root', 'loc', 1), 0.0), p.get(('ctl_root', 'loc', 2), 0.0)))
            ryaw = p.get(('ctl_root', 'rot', 2), 0.0)
            sh_rel = world_to_root(sh, tuple(root_loc), ryaw)      # IK controls are children of ctl_root
            if spec[0] == 'ikmat':
                M = d['M']
                target = M.translation.copy()
                pr = PL.hand_ik_from_world(s, M)
            elif spec[0] == 'aim':
                dv = aim_dir(d.get('yaw', 0.0), d.get('pitch', 0.0))
                target = sh_rel + dv * d.get('reach', 0.55)
                pr = PL.arm_ik_pose(s, target, direction=dv, roll=d.get('roll', 0.0), palm=d.get('palm'))
            else:
                target = Vector(d['target'])
                dv = Vector(d['dir']) if d.get('dir') is not None else None
                pr = PL.arm_ik_pose(s, target, direction=dv, roll=d.get('roll', 0.0), rot=d.get('rot'), palm=d.get('palm'))
            hint = d.get('elbow_hint')
            hint = Vector(hint) if hint is not None else _elbow_hint(s, sh_rel, target, d.get('out', (-0.35, 0.55, -0.55)))
            pr.update(PL.arm_pole(s, hint))
            p.update(pr)
    if k.get('face') is not None:
        p.update(k['face'])
    if k.get('extra') is not None:
        p.update(k['extra'])
    return p


def fk_like(k):
    """Pose with only the FK arm channels (and ik_fk = 0) that reproduce the IK arms of key k: the rig's own FK <- IK snap (exact),
    read back as control rotations. A clip that reaches an FK pose from IK keys puts this pose one or two frames after the last IK key,
    where both give the same pose, instead of blending IK into FK over many frames (a blend between two far apart arm poses can pop the
    hand or the elbow within a frame). The torso is not keyed here, so its motion stays smooth."""
    import mr_tools as MT
    ctl = PL.CTX['ctl']
    PL.evaluate(resolve(k))
    out = Pose()
    for s in ('l', 'r'):
        spec = k.get('a' + s)
        if spec is not None and spec[0] != 'fk':
            names = MT._arm_names(s)
            MT.snap_fk_to_final(ctl, names)
            for bn in names['fk']:
                out.rot(bn, [math.degrees(a) for a in ctl.pose.bones[bn].rotation_euler])
            out.prop(f'ctl_hand_ik_{s}', 'ik_fk', 0.0)
    return out


def build_clip(cid, entry, keys, loop=None, events=(), prop_states=None, meta=None, contacts=None, note='', root=None):
    """keys: list of (t, keydict) with t in 0..1. Resolves each key pose; loop clips are closed with pose(N) == pose(0)."""
    loop = entry['loop'] if loop is None else loop
    N = entry['frames']
    c = Clip(cid, N, loop=loop, root=root or ('root_motion' if cid.startswith('dash') else 'in_place'), form=entry['form'], layer=entry['layer'],
             speed_cm_s=entry['speed'], note=note or 'authored with keypose.py')
    seen = set()
    for t, kd in keys:
        f = int(round(t * N))
        if f in seen:
            continue
        seen.add(f)
        c.key(f, kd if isinstance(kd, Pose) else resolve(kd))
    if loop:
        c.close_loop()
    for ev in events:
        name, t = ev[0], ev[1]
        params = ev[2] if len(ev) > 2 else {}
        c.event(name, int(round(t * N)) if t <= 1.0 else int(t), **params)
    if prop_states is not None:
        c.prop_states = prop_states
    if contacts:
        c.contacts = contacts
    if meta:
        c.meta.update(meta)
    return c

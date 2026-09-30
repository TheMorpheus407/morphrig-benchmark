"""Animation authoring framework for the Operative control rig (Blender).

A Clip holds sparse keyframes on control-rig channels. Poses are dicts {(bone, kind, index): value} where
kind is 'loc' (metres, bone local = world for the identity-oriented controls), 'rot' (Euler XYZ degrees) or a custom
property name. Clips are written as editable actions 'A_<id>' on the control rig; bake_clip() samples the deform skeleton
into per-frame keys used by the export.
Conventions: 30 fps; Blender frame = 1 + clip frame; loop clips repeat frames 0..N with pose(N) == pose(0).
"""
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix, Euler, Quaternion
import skeleton_def as S

FPS = 30
DEG = math.pi / 180.0
SIDES = (('l', 1.0), ('r', -1.0))


# ----------------------------------------------------------------------------- pose helpers

class Pose(dict):
    """Channel dict with convenience setters. Keys: (bone, kind, idx)."""

    def loc(self, bone, xyz):
        for i, v in enumerate(xyz):
            self[(bone, 'loc', i)] = float(v)
        return self

    def rot(self, bone, xyz_deg):
        for i, v in enumerate(xyz_deg):
            self[(bone, 'rot', i)] = float(v)
        return self

    def prop(self, bone, name, v):
        self[(bone, name, 0)] = float(v)
        return self

    def merged(self, other):
        p = Pose(self)
        p.update(other)
        return p

    def copy(self):
        return Pose(self)


def lerp_pose(a, b, t):
    keys = set(a) | set(b)
    out = Pose()
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va is None:
            va = REST_DEFAULT.get(k, 0.0)
        if vb is None:
            vb = REST_DEFAULT.get(k, 0.0)
        out[k] = va + (vb - va) * t
    return out


REST_DEFAULT = {}   # filled by setup_defaults(): default custom-property values


def ease(t, kind='smooth'):
    t = min(max(t, 0.0), 1.0)
    if kind == 'smooth':
        return t * t * (3 - 2 * t)
    if kind == 'in':
        return t * t
    if kind == 'out':
        return 1 - (1 - t) * (1 - t)
    if kind == 'inout5':
        return t * t * t * (t * (6 * t - 15) + 10)
    return t


def spine_pose(flex=0.0, twist=0.0, side=0.0, split=(0.30, 0.35, 0.35)):
    """Distribute total spine flexion/twist/side-bend over spine_01..03 (local X = flex, Y = twist, Z = side)."""
    p = Pose()
    for i, w in enumerate(split):
        p.rot(f'ctl_spine_0{i + 1}', (flex * w, twist * w, side * w))
    return p


def neck_head(flex=0.0, twist=0.0, side=0.0, head_share=0.6):
    p = Pose()
    p.rot('ctl_neck_01', (flex * (1 - head_share) * 0.5, twist * (1 - head_share) * 0.5, side * (1 - head_share) * 0.5))
    p.rot('ctl_neck_02', (flex * (1 - head_share) * 0.5, twist * (1 - head_share) * 0.5, side * (1 - head_share) * 0.5))
    p.rot('ctl_head', (flex * head_share, twist * head_share, side * head_share))
    return p


_ARM_REST = {}


def _arm_rest():
    """Rest orientation of the left FK upper-arm control (armature space) and how far its bone points out of the body's
    frontal plane at rest (the rig rests in an A-pose). Read once from the control rig."""
    if not _ARM_REST:
        ob = bpy.data.objects['Operative_Control']
        q = ob.data.bones['ctl_upperarm_fk_l'].matrix_local.to_3x3()
        d = q @ Vector((0.0, 1.0, 0.0))
        _ARM_REST.update(Q=q, tilt=math.atan2(d.y, -d.z))
    return _ARM_REST['Q'], _ARM_REST['tilt']


def arm_fk(side, flex=0.0, abd=0.0, roll=0.0, elbow=0.0, wrist_flex=0.0, wrist_dev=0.0, wrist_roll=0.0, clav=(0.0, 0.0, 0.0), sagittal=False):
    """FK arm in mirrored-frame semantics: flex +forward, abd +away from the body, elbow +bend, roll about the bone axis.
    The plain values are Euler angles of the control bone, whose rest pose is an A-pose: flexion turns about an axis tilted out
    of the body's lateral axis, so with plain values a raised arm (flex above about 90) swings across the body and raised arms
    cross. sagittal=True describes the upper arm in body terms instead: flex is the elevation about the body's lateral axis and
    abd is the angle between the arm and the body's sagittal plane at every elevation (about 12 = hanging at the side, 0 = in
    the plane, negative = across the body). The values are converted to the equivalent Euler XYZ angles of the control bone."""
    sy = 1.0 if side == 'l' else -1.0
    if sagittal:
        q, tilt = _arm_rest()
        world = Matrix.Rotation(-flex * DEG, 3, 'Y') @ Matrix.Rotation(abd * DEG - tilt, 3, 'X')     # body frame: X forward, Y left, Z up
        local = q.inverted() @ world @ q @ Matrix.Rotation(roll * DEG, 3, 'Y')
        e = local.to_euler('XYZ')
        flex, roll, abd = e.x / DEG, e.y / DEG, e.z / DEG
    p = Pose()
    p.rot(f'ctl_upperarm_fk_{side}', (flex, sy * roll, sy * abd))
    p.rot(f'ctl_lowerarm_fk_{side}', (elbow, 0.0, 0.0))
    p.rot(f'ctl_hand_fk_{side}', (wrist_flex, sy * wrist_roll, sy * wrist_dev))
    p.rot(f'ctl_clavicle_{side}', (clav[0], sy * clav[1], sy * clav[2]))
    p.prop(f'ctl_hand_ik_{side}', 'ik_fk', 0.0)
    return p


def hand_pose(side, curl=0.0, spread=0.0, thumb=0.0, index=0.0, middle=0.0, ring=0.0, pinky=0.0):
    n = f'ctl_hand_pose_{side}'
    p = Pose()
    for k, v in (('curl', curl), ('spread', spread), ('thumb_curl', thumb), ('index_curl', index), ('middle_curl', middle), ('ring_curl', ring), ('pinky_curl', pinky)):
        p.prop(n, k, v)
    return p


def foot_ik(side, xyz, yaw=0.0, roll=0.0, roll_break=None, pitch=0.0, bank=0.0):
    """IK foot: xyz = OFFSET of the ground anchor from its rest position (world axes), yaw about vertical, roll in degrees
    (negative = heel pivot, positive = ball then toe pivot)."""
    n = f'ctl_foot_ik_{side}'
    p = Pose()
    p.loc(n, xyz)
    p.rot(n, (bank, pitch, yaw))
    p.prop(n, 'roll', roll)
    p.prop(n, 'ik_fk', 1.0)
    if roll_break is not None:
        p.prop(n, 'roll_break', roll_break)
    return p


def hand_ik(side, xyz, rot=(0.0, 0.0, 0.0)):
    n = f'ctl_hand_ik_{side}'
    p = Pose()
    p.loc(n, xyz)
    p.rot(n, rot)
    p.prop(n, 'ik_fk', 1.0)
    return p


def rest_pos(name):
    b = S.BONE_BY_NAME[name]
    return np.array(b.head)


def euler_from_quat_xyz(q):
    return tuple(math.degrees(a) for a in q.to_euler('XYZ'))


# ----------------------------------------------------------------------------- clips

class Clip:
    def __init__(self, cid, frames, loop=False, root='in_place', form='one_shot', layer='full', speed_cm_s=0.0, note=''):
        self.id = cid
        self.frames = int(frames)          # number of intervals; keys live at 0..frames
        self.loop = loop
        self.root = root
        self.form = form
        self.layer = layer
        self.speed = speed_cm_s
        self.note = note
        self.keys = {}                     # (bone, kind, idx) -> {frame: value}
        self.events = []                   # (name, frame, params dict)
        self.contacts = []                 # foot contact info (frame, foot, 'plant'|'lift')
        self.meta = {}

    @property
    def duration(self):
        return self.frames / FPS

    def key(self, f, pose):
        for k, v in pose.items():
            self.keys.setdefault(k, {})[int(f)] = float(v)

    def event(self, name, frame, **params):
        """Marker at a clip frame. A float in 0..1 is a fraction of the clip length (0.5 = middle), an int is a frame number."""
        if isinstance(frame, float) and 0.0 <= frame <= 1.0:
            frame = frame * self.frames
        self.events.append((name, int(round(frame)), params))

    def close_loop(self):
        """Copy the first key of every channel to the last frame (pose(N) == pose(0))."""
        for k, d in self.keys.items():
            f0 = min(d)
            d[self.frames] = d[f0]

    def channel_frames(self):
        fs = set()
        for d in self.keys.values():
            fs.update(d)
        return sorted(fs)


def sample_clip_dense(clip, fn, step=1):
    """Key every `step` frames with pose fn(frame)->Pose (frame in 0..frames)."""
    for f in list(range(0, clip.frames + 1, step)) + ([clip.frames] if clip.frames % step else []):
        clip.key(f, fn(f))


# ----------------------------------------------------------------------------- writing actions

def _path(bone, kind):
    if kind == 'loc':
        return f'pose.bones["{bone}"].location'
    if kind == 'rot':
        return f'pose.bones["{bone}"].rotation_euler'
    if kind == 'scale':
        return f'pose.bones["{bone}"].scale'
    return f'pose.bones["{bone}"]["{kind}"]'


def write_action(ctl, clip, fake_user=True, frame_offset=1):
    import bpy_extras.anim_utils as au
    name = f'A_{clip.id}'
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    slot = act.slots.new(id_type='OBJECT', name=ctl.name)
    cb = au.action_ensure_channelbag_for_slot(act, slot)
    for (bone, kind, idx), d in sorted(clip.keys.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        if kind in ('loc', 'rot', 'scale'):
            dp, i = _path(bone, kind), idx
            scale = DEG if kind == 'rot' else 1.0
        else:
            dp, i, scale = _path(bone, kind), 0, 1.0
        fc = cb.fcurves.new(data_path=dp, index=i, group_name=bone)
        frames = sorted(d)
        n = len(frames)
        fc.keyframe_points.add(n)
        co = np.empty(n * 2)
        co[0::2] = [f + frame_offset for f in frames]
        co[1::2] = [d[f] * scale for f in frames]
        fc.keyframe_points.foreach_set('co', co)
        fc.update()
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'
        fc.update()
        if clip.loop:
            fc.modifiers.new('CYCLES')
    act.use_fake_user = True
    act.use_frame_range = True
    act.frame_start = frame_offset
    act.frame_end = frame_offset + clip.frames
    act.use_cyclic = bool(clip.loop)
    import json as _json
    act['mr_id'] = clip.id
    act['mr_fps'] = FPS
    act['mr_root'] = clip.root
    act['mr_form'] = clip.form
    act['mr_frames'] = clip.frames
    act['mr_loop'] = bool(clip.loop)
    act['mr_layer'] = clip.layer
    act['mr_speed_cm_s'] = clip.speed
    act['mr_events'] = _json.dumps([{'name': n, 'frame': f, 'params': pr} for n, f, pr in clip.events])
    act['mr_contacts'] = _json.dumps(clip.contacts)
    act['mr_meta'] = _json.dumps(clip.meta)
    act['mr_note'] = clip.note
    # timeline markers as pose markers on the action
    for name_, f, params in clip.events:
        m = act.pose_markers.new(name_)
        m.frame = f + frame_offset
    return act


def assign_action(ctl, act):
    ctl.animation_data_create()
    ctl.animation_data.action = act
    ctl.animation_data.action_slot = act.slots[0]


# ----------------------------------------------------------------------------- reset / defaults

def control_channels(ctl):
    """All animatable control channels of the rig with default values: {(bone, kind, idx): default}."""
    out = {}
    for pb in ctl.pose.bones:
        n = pb.name
        if not (n.startswith('ctl_')):
            continue
        for i in range(3):
            out[(n, 'loc', i)] = 0.0
            out[(n, 'rot', i)] = 0.0
        for k in pb.keys():
            if k.startswith('_'):
                continue
            try:
                out[(n, k, 0)] = float(pb[k])
            except (TypeError, ValueError):
                pass
    return out


def setup_defaults(ctl):
    REST_DEFAULT.clear()
    for k, v in control_channels(ctl).items():
        REST_DEFAULT[k] = v
    # face props: default 0
    return REST_DEFAULT


def apply_pose(ctl, pose, update=True):
    P = ctl.pose.bones
    for (bone, kind, idx), v in pose.items():
        pb = P.get(bone)
        if pb is None:
            continue
        if kind == 'loc':
            loc = list(pb.location)
            loc[idx] = v
            pb.location = loc
        elif kind == 'rot':
            e = list(pb.rotation_euler)
            e[idx] = v * DEG
            pb.rotation_euler = e
        else:
            pb[kind] = v
    if update:
        ctl.update_tag()
        bpy.context.view_layer.update()


def reset_pose(ctl):
    for pb in ctl.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    for (bone, kind, idx), v in REST_DEFAULT.items():
        if kind not in ('loc', 'rot'):
            ctl.pose.bones[bone][kind] = v
    ctl.update_tag()


# ----------------------------------------------------------------------------- baking to the deform skeleton

def skeleton_basis_table(skel):
    """Pre-computed rest data: for each bone, (parent name or None, rest_local_to_parent Matrix)."""
    tab = {}
    for b in skel.data.bones:
        rest = b.matrix_local.copy()
        if b.parent:
            rel = b.parent.matrix_local.inverted() @ rest
            tab[b.name] = (b.parent.name, rel)
        else:
            tab[b.name] = (None, rest)
    return tab


def bake_clip(ctl, skel, clip, act=None, frame_offset=1):
    """Sample skeleton bone basis transforms for every frame. Returns dict: loc (F,B,3), quat (F,B,4), scale (F,B,3), names."""
    if act is not None:
        assign_action(ctl, act)
    names = [b.name for b in skel.data.bones]
    tab = skeleton_basis_table(skel)
    nf = clip.frames + 1
    loc = np.zeros((nf, len(names), 3))
    quat = np.zeros((nf, len(names), 4))
    scl = np.ones((nf, len(names), 3))
    prev_q = [None] * len(names)
    sc = bpy.context.scene
    for f in range(nf):
        sc.frame_set(f + frame_offset)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = skel.evaluated_get(dg)
        mats = {n: ev.pose.bones[n].matrix.copy() for n in names}
        for bi, n in enumerate(names):
            parent, rel = tab[n]
            if parent is None:
                basis = rel.inverted() @ mats[n]
            else:
                # parent evaluated pose relative to its rest: parent_final @ rest_rel
                basis = (mats[parent] @ rel).inverted() @ mats[n]
            t, q, s = basis.decompose()
            if prev_q[bi] is not None and q.dot(prev_q[bi]) < 0:
                q = -q
            prev_q[bi] = q
            loc[f, bi] = t
            quat[f, bi] = (q.w, q.x, q.y, q.z)
            scl[f, bi] = s
    return {'names': names, 'loc': loc, 'quat': quat, 'scale': scl}


def face_channels_for_clip(clip):
    """Morph target curves used by the clip: {name: {frame: value}} read from ctl_face custom props in the clip keys."""
    out = {}
    for (bone, kind, idx), d in clip.keys.items():
        if bone == 'ctl_face' and kind in S.MORPH_TARGETS:
            out[kind] = d
    return out

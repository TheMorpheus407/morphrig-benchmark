"""MorphRig animator tools: one sidebar panel (3D View > Sidebar > MorphRig) for the Operative control rig.

  Rig       reset pose / reset face, global scale, look-at, secondary influence
  Limbs     IK/FK blend sliders with exact matching (snap FK to the current IK result, snap IK to the current FK pose) for both arms and legs
  Hands     finger curl / spread sliders and the fist, open and point presets
  Face      neutral + six expression presets with a weight, 14 viseme buttons (documented mapping), independent blinks and gaze
  Team      team A / team B accent variant and the optional rim outline (scene properties read by the MI_* materials)
  Clips     searchable list of the 96 clip actions (assign, set frame range)
  Bake      secondary motion (braid and cable spring chains) into the current action, visemes into the face controls, action onto the
            deformation skeleton

The script is stored inside Operative.blend as the text 'MorphRig_Tools.py' (run it once from the Text Editor, or enable auto-run for
this file); the same file lives in source/generators/mr_tools.py. All preset data is embedded at the end of the stored copy."""
import json
import math
import os

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Euler, Matrix, Vector

bl_info = {'name': 'MorphRig tools', 'author': 'MorphRig benchmark (Claude Sonnet 5.5)', 'version': (1, 0, 0), 'blender': (5, 1, 0),
           'location': '3D View > Sidebar > MorphRig', 'description': 'Control rig helpers for the Operative', 'category': 'Rigging'}

CTL = 'Operative_Control'
SKEL = 'Operative_Skeleton'
FPS = 30
MR_EMBEDDED_DATA = None          # replaced by install_into_blend() in the stored copy


# ----------------------------------------------------------------------------- data
def data():
    """Preset data: expressions, visemes, morph names. Embedded in the stored copy, generated from the generators otherwise."""
    if MR_EMBEDDED_DATA:
        return MR_EMBEDDED_DATA
    import face_lib
    import skeleton_def as S
    return export_data(face_lib, S)


def export_data(face_lib, S):
    return {
        'morphs': list(S.MORPH_TARGETS),
        'expressions': {k: {'morphs': v.get('morphs', {}), 'jaw': v.get('jaw', 0.0), 'lid_up': v.get('lid_up', 0.0)} for k, v in face_lib.EXPRESSIONS.items()},
        'visemes': {k: {'jaw_open': v['jaw_open'], 'morphs': v['morphs'], 'tongue': v.get('tongue', 0.0), 'phonemes': v.get('phonemes', '')} for k, v in S.VISEMES.items()},
        'jaw_max_deg': face_lib.JAW_MAX, 'lid_close_up_deg': face_lib.LID_CLOSE_UP, 'lid_close_lo_deg': face_lib.LID_CLOSE_LO,
    }


def ctl_obj(context=None):
    return bpy.data.objects.get(CTL)


def skel_obj():
    return bpy.data.objects.get(SKEL)


def evaluated(obj):
    """Evaluated copy of an object: constraints and drivers are applied there (the original pose bones keep only the channel values)."""
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get())


# ----------------------------------------------------------------------------- pose helpers
def _default_of(pb, key):
    try:
        d = pb.id_properties_ui(key).as_dict()
        return d.get('default', 0.0)
    except Exception:
        return 0.0


def reset_bones(ctl, bones=None, props=True):
    for pb in ctl.pose.bones:
        if bones is not None and pb.name not in bones:
            continue
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
        if props:
            for key in list(pb.keys()):
                if key.startswith('_'):
                    continue
                if isinstance(pb[key], (int, float)):
                    pb[key] = _default_of(pb, key)
    ctl.update_tag()


def set_pose_world(ctl, pb, M, parent_world=None):
    """Set the local channels of pose bone `pb` so that its armature-space matrix becomes M. The parent matrix can be given (used when the
    parent has just been set and the dependency graph has not been refreshed yet). Exact for bones without constraints."""
    bone = pb.bone
    rest = bone.matrix_local
    if bone.parent is None:
        basis = rest.inverted() @ M
    else:
        p_rest = bone.parent.matrix_local
        p_pose = parent_world if parent_world is not None else evaluated(ctl).pose.bones[bone.parent.name].matrix
        basis = (p_pose @ p_rest.inverted() @ rest).inverted() @ M
    pb.matrix_basis = basis
    return M


def _arm_names(s):
    return dict(fk=[f'ctl_upperarm_fk_{s}', f'ctl_lowerarm_fk_{s}', f'ctl_hand_fk_{s}'], final=[f'def_upperarm_{s}', f'def_lowerarm_{s}', f'def_hand_{s}'],
                ik=f'ctl_hand_ik_{s}', pole=f'ctl_pole_arm_{s}')


def _leg_names(s):
    return dict(fk=[f'ctl_thigh_fk_{s}', f'ctl_calf_fk_{s}', f'ctl_foot_fk_{s}', f'ctl_ball_fk_{s}'], final=[f'def_thigh_{s}', f'def_calf_{s}', f'def_foot_{s}', f'def_ball_{s}'],
                ik=f'ctl_foot_ik_{s}', pole=f'ctl_pole_leg_{s}')


def snap_fk_to_final(ctl, names):
    """FK controls take the pose of the final (blended) chain: exact, because control and deform bones share the rest orientation."""
    prev = None
    ev = evaluated(ctl)
    finals = [ev.pose.bones[fin].matrix.copy() for fin in names['final']]
    for fk, M in zip(names['fk'], finals):
        set_pose_world(ctl, ctl.pose.bones[fk], M, parent_world=prev if prev is not None else None)
        prev = M


def _pole_from_chain(a, b, c, dist, phi=0.0):
    """Pole target for chain a-b-c (b = elbow/knee): on the side the joint bends towards, rotated by phi radians about the a-c axis."""
    axis_n = (c - a).normalized()
    v = (b - a) - axis_n * (b - a).dot(axis_n)
    if v.length < 1e-6:
        v = Vector((0.0, 0.0, 1.0))
    v = v.normalized()
    if phi:
        v = Matrix.Rotation(phi, 3, axis_n) @ v
    return b + v * dist


def _refine_pole(ctl, names, a, b, c, dist):
    """Fine search of the pole direction (rotation about the shoulder-wrist / hip-ankle axis) so that the elbow or knee lands where it was."""
    pbp = ctl.pose.bones[names['pole']]
    rest = ctl.data.bones[names['pole']].head_local
    best = (1e9, 0.0)

    def trial(phi):
        pbp.location = _pole_from_chain(a, b, c, dist, phi) - rest
        ctl.update_tag()
        bpy.context.view_layer.update()
        joint = evaluated(ctl).pose.bones[names['final'][1]].matrix.translation
        return (joint - b).length

    for phi_deg in np.arange(-12.0, 12.01, 1.5):
        e = trial(math.radians(phi_deg))
        if e < best[0]:
            best = (e, math.radians(phi_deg))
    for phi_deg in np.arange(-1.4, 1.41, 0.2):
        phi = best[1] + math.radians(phi_deg)
        e = trial(phi)
        if e < best[0]:
            best = (e, phi)
    trial(best[1])
    return best


def snap_arm_ik_to_final(ctl, s):
    n = _arm_names(s)
    ik = ctl.pose.bones[n['ik']]
    ev = evaluated(ctl)
    hand = ev.pose.bones[n['final'][2]].matrix.copy()
    rest = ctl.data.bones[n['final'][2]].matrix_local
    R = hand.to_3x3() @ rest.to_3x3().inverted()
    M = Matrix.Translation(hand.translation) @ R.to_4x4()
    root_world = ev.pose.bones['ctl_root'].matrix.copy()
    a = ev.pose.bones[n['final'][0]].matrix.translation.copy()
    b = ev.pose.bones[n['final'][1]].matrix.translation.copy()
    c = hand.translation.copy()
    set_pose_world(ctl, ik, M, parent_world=root_world)
    ik['ik_fk'] = 1.0
    _refine_pole(ctl, n, a, b, c, 0.30)


def snap_leg_ik_to_final(ctl, s):
    n = _leg_names(s)
    ik = ctl.pose.bones[n['ik']]
    ev = evaluated(ctl)
    foot = ev.pose.bones[n['final'][2]].matrix.copy()
    rest = ctl.data.bones[n['final'][2]].matrix_local
    R = foot.to_3x3() @ rest.to_3x3().inverted()
    A0 = ctl.data.bones[n['ik']].head_local
    ankle_rest = rest.translation
    loc_world = foot.translation - R @ (ankle_rest - A0)          # position of the control head
    M = Matrix.Translation(loc_world) @ R.to_4x4()
    a = ev.pose.bones[n['final'][0]].matrix.translation.copy()
    b = ev.pose.bones[n['final'][1]].matrix.translation.copy()
    c = foot.translation.copy()
    set_pose_world(ctl, ik, M, parent_world=ev.pose.bones['ctl_root'].matrix.copy())
    ik['roll'] = 0.0
    ik['ik_fk'] = 1.0
    _refine_pole(ctl, n, a, b, c, 0.35)


def snap(ctl, limb, direction):
    kind, s = limb.split('_')[0], limb.split('_')[1]
    n = _arm_names(s) if kind == 'ARM' else _leg_names(s)
    ikpb = ctl.pose.bones[n['ik']]
    bpy.context.view_layer.update()
    if direction == 'FK_TO_IK':                     # make FK match what the IK produces now, then switch to FK
        snap_fk_to_final(ctl, n)
        ikpb['ik_fk'] = 0.0
    else:                                           # make IK match what the FK produces now, then switch to IK
        (snap_arm_ik_to_final if kind == 'ARM' else snap_leg_ik_to_final)(ctl, s)
        ikpb['ik_fk'] = 1.0
    ctl.update_tag()                                # custom property changes do not tag the object by themselves
    bpy.context.view_layer.update()


# ----------------------------------------------------------------------------- face
def apply_face(ctl, morphs=None, jaw01=0.0, lid_up_deg=0.0, tongue01=0.0, clear=True, w=1.0):
    d = data()
    pb = ctl.pose.bones['ctl_face']
    if clear:
        for m in d['morphs']:
            pb[m] = 0.0
    for m, v in (morphs or {}).items():
        pb[m] = min(1.0, max(0.0, (pb[m] if not clear else 0.0) + v * w))
    ctl.pose.bones['ctl_jaw'].rotation_euler = (math.radians(-d['jaw_max_deg'] * jaw01 * w), 0.0, 0.0)
    for s in ('l', 'r'):
        ctl.pose.bones[f'ctl_lid_up_{s}'].rotation_euler = (math.radians(lid_up_deg * w), 0.0, 0.0)
    for name, gain in (('ctl_tongue_01', -18.0), ('ctl_tongue_02', -22.0), ('ctl_tongue_03', -16.0)):
        ctl.pose.bones[name].rotation_euler = (math.radians(gain * tongue01 * w), 0.0, 0.0)
    ctl.update_tag()


def apply_expression(ctl, name, w=1.0):
    e = data()['expressions'][name]
    apply_face(ctl, e['morphs'], e['jaw'], e['lid_up'], 0.0, True, w)


def apply_viseme(ctl, name, w=1.0):
    d = data()
    v = d['visemes'][name]
    apply_face(ctl, v['morphs'], v['jaw_open'], 0.0, v.get('tongue', 0.0), True, w)
    ctl.pose.bones['ctl_face']['jaw_open_corr'] = min(1.0, v['jaw_open'] * w * 1.1)


def viseme_mix(weights):
    """Documented mapping: linear mix of the viseme targets (morph weights, jaw opening, tongue lift)."""
    d = data()
    morphs = {}
    jaw = tongue = 0.0
    for name, w in weights.items():
        if w <= 0.0:
            continue
        v = d['visemes'][name]
        for m, val in v['morphs'].items():
            morphs[m] = morphs.get(m, 0.0) + w * val
        jaw += w * v['jaw_open']
        tongue += w * v.get('tongue', 0.0)
    return morphs, jaw, tongue


# ----------------------------------------------------------------------------- secondary motion (braid and cable spring chains)
CHAINS = {'hair': dict(bones=[f'ctl_hair_{i:02d}' for i in range(1, 6)], stiffness=(0.30, 0.22, 0.16, 0.12, 0.09), damping=0.10, gravity=0.55, limit_deg=55.0),
          'cable': dict(bones=[f'ctl_cable_{i:02d}' for i in range(1, 6)], stiffness=(0.24, 0.18, 0.14, 0.11, 0.09), damping=0.08, gravity=0.70, limit_deg=65.0)}


def _chain_points(ctl, bones):
    b = ctl.data.bones
    pts = [b[bones[0]].head_local.copy()] + [b[n].tail_local.copy() for n in bones]
    return pts


def simulate_chain(ctl, chain, frames, passes=6, sub=2, influence=1.0):
    """Position-based spring chain attached to the parent bone; returns per-frame local rotation matrices (basis) of the chain bones.
    `frames` are scene frames; the pose of the parent is read from the (secondary-free) evaluated rig."""
    cfg = CHAINS[chain]
    bones = cfg['bones']
    rest_pts = _chain_points(ctl, bones)
    n = len(rest_pts)
    parent_name = ctl.data.bones[bones[0]].parent.name
    p_rest = ctl.data.bones[parent_name].matrix_local
    local_pts = [p_rest.inverted() @ p for p in rest_pts]
    seg_len = [(rest_pts[i + 1] - rest_pts[i]).length for i in range(n - 1)]
    sc = bpy.context.scene
    ps = []
    for f in frames:
        sc.frame_set(f)
        bpy.context.view_layer.update()
        ps.append(evaluated(ctl).pose.bones[parent_name].matrix.copy())
    dt = 1.0 / (FPS * sub)
    g = Vector((0.0, 0.0, -9.81 * cfg['gravity']))
    x = [p.copy() for p in (ps[0] @ q for q in local_pts)]
    xp = [p.copy() for p in x]
    out = []
    for pas in range(passes):
        out = []
        for fi, P in enumerate(ps):
            targets = [P @ q for q in local_pts]
            for _ in range(sub):
                x[0] = targets[0].copy()
                xp[0] = targets[0].copy()
                for i in range(1, n):
                    vel = (x[i] - xp[i]) * (1.0 - cfg['damping'])
                    xp[i] = x[i].copy()
                    x[i] = x[i] + vel + g * (dt * dt)
                    x[i] = x[i] + (targets[i] - x[i]) * cfg['stiffness'][i - 1]
                for _it in range(6):
                    for i in range(n - 1):
                        d = x[i + 1] - x[i]
                        L = max(d.length, 1e-9)
                        corr = d * ((L - seg_len[i]) / L)
                        if i == 0:
                            x[i + 1] = x[i + 1] - corr
                        else:
                            x[i] = x[i] + corr * 0.5
                            x[i + 1] = x[i + 1] - corr * 0.5
                    x[0] = targets[0].copy()
            # swing-only rotation per bone
            world_R = []
            basis = []
            parent_R = P.to_3x3()
            for i, bn in enumerate(bones):
                bone = ctl.data.bones[bn]
                rest_R = bone.matrix_local.to_3x3()
                prest_R = (ctl.data.bones[parent_name].matrix_local.to_3x3() if i == 0 else ctl.data.bones[bones[i - 1]].matrix_local.to_3x3())
                rigid = parent_R @ prest_R.inverted() @ rest_R                   # orientation when following the parent rigidly
                d = (x[i + 1] - x[i]).normalized()
                y_rigid = rigid.col[1].normalized()
                q = y_rigid.rotation_difference(d)
                ang = q.angle
                lim = math.radians(cfg['limit_deg'])
                if ang > lim:
                    q = Euler((0, 0, 0)).to_quaternion().slerp(q, lim / ang)
                Rw = q.to_matrix() @ rigid
                local = rigid.inverted() @ Rw
                if influence < 1.0:
                    local = Euler((0, 0, 0)).to_quaternion().slerp(local.to_quaternion(), influence).to_matrix()
                    Rw = rigid @ local
                basis.append(local)
                world_R.append(Rw)
                parent_R = Rw
            out.append(basis)
    return out


def bake_secondary(ctl, frame_start, frame_end, chains=('hair', 'cable'), influence=None):
    act = ctl.animation_data.action if ctl.animation_data else None
    if act is None:
        raise RuntimeError('assign a clip action first')
    sc = bpy.context.scene
    infl = ctl.pose.bones['ctl_root'].get('secondary_influence', 1.0) if influence is None else influence
    # clear old secondary keys and channels first so the parent motion is evaluated without them
    for chain in chains:
        for bn in CHAINS[chain]['bones']:
            ctl.pose.bones[bn].rotation_euler = (0.0, 0.0, 0.0)
            _remove_fcurves(ctl, act, f'pose.bones["{bn}"].rotation_euler')
    frames = list(range(frame_start, frame_end + 1))
    result = {}
    for chain in chains:
        result[chain] = simulate_chain(ctl, chain, frames, influence=infl)
        for fi, f in enumerate(frames):
            for bi, bn in enumerate(CHAINS[chain]['bones']):
                e = result[chain][fi][bi].to_euler('XYZ')
                pb = ctl.pose.bones[bn]
                pb.rotation_euler = e
                pb.keyframe_insert('rotation_euler', frame=f, group='Secondary')
    sc.frame_set(frame_start)
    return {c: len(frames) for c in chains}


def _remove_fcurves(obj, act, data_path_prefix):
    try:
        for slot in act.slots:
            for layer in act.layers:
                for strip in layer.strips:
                    cb = strip.channelbag(slot)
                    if cb is None:
                        continue
                    for fc in list(cb.fcurves):
                        if fc.data_path.startswith(data_path_prefix):
                            cb.fcurves.remove(fc)
    except AttributeError:
        for fc in list(getattr(act, 'fcurves', [])):
            if fc.data_path.startswith(data_path_prefix):
                act.fcurves.remove(fc)


# ----------------------------------------------------------------------------- bake to the deformation skeleton
def bake_to_skeleton(ctl, skel, frame_start, frame_end, name):
    sc = bpy.context.scene
    act = bpy.data.actions.new(name)
    if skel.animation_data is None:
        skel.animation_data_create()
    skel.animation_data.action = act
    try:
        skel.animation_data.action_slot = act.slots.new('OBJECT', skel.name)
    except Exception:
        pass
    for f in range(frame_start, frame_end + 1):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        ev = evaluated(skel)
        for pb in skel.pose.bones:
            if not pb.bone.use_deform and pb.name != 'root':
                continue
            m = ev.pose.bones[pb.name].matrix_basis.copy()
            pb.matrix_basis = m
            pb.keyframe_insert('location', frame=f, group=pb.name)
            pb.keyframe_insert('rotation_quaternion' if pb.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=f, group=pb.name)
    return act


# ----------------------------------------------------------------------------- operators
class MR_OT_reset_pose(bpy.types.Operator):
    bl_idname = 'mr.reset_pose'
    bl_label = 'Reset pose'
    bl_description = 'Reset every control bone to its rest transform and every control property to its default'
    bl_options = {'REGISTER', 'UNDO'}
    selected_only: BoolProperty(name='Selected bones only', default=False)

    def execute(self, context):
        ctl = ctl_obj()
        names = {b.name for b in ctl.pose.bones if b.bone.select} if self.selected_only else None
        reset_bones(ctl, names)
        return {'FINISHED'}


class MR_OT_reset_face(bpy.types.Operator):
    bl_idname = 'mr.reset_face'
    bl_label = 'Reset face'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ctl = ctl_obj()
        face = {n for n in ('ctl_face', 'ctl_jaw', 'ctl_lid_up_l', 'ctl_lid_up_r', 'ctl_lid_lo_l', 'ctl_lid_lo_r', 'ctl_eye_l', 'ctl_eye_r', 'ctl_tongue_01', 'ctl_tongue_02', 'ctl_tongue_03')}
        reset_bones(ctl, face)
        return {'FINISHED'}


class MR_OT_snap(bpy.types.Operator):
    bl_idname = 'mr.snap'
    bl_label = 'Snap IK/FK'
    bl_options = {'REGISTER', 'UNDO'}
    limb: EnumProperty(items=[('ARM_l', 'Left arm', ''), ('ARM_r', 'Right arm', ''), ('LEG_l', 'Left leg', ''), ('LEG_r', 'Right leg', '')])
    direction: EnumProperty(items=[('FK_TO_IK', 'FK to IK', 'Match FK controls to the IK result, then switch to FK'),
                                   ('IK_TO_FK', 'IK to FK', 'Match the IK control to the FK pose, then switch to IK')])

    def execute(self, context):
        snap(ctl_obj(), self.limb, self.direction)
        return {'FINISHED'}


class MR_OT_expression(bpy.types.Operator):
    bl_idname = 'mr.expression'
    bl_label = 'Apply expression'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty()
    weight: FloatProperty(default=1.0, min=0.0, max=1.5)

    def execute(self, context):
        apply_expression(ctl_obj(), self.name, self.weight)
        return {'FINISHED'}


class MR_OT_viseme(bpy.types.Operator):
    bl_idname = 'mr.viseme'
    bl_label = 'Apply viseme'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty()
    weight: FloatProperty(default=1.0, min=0.0, max=1.5)

    def execute(self, context):
        apply_viseme(ctl_obj(), self.name, self.weight)
        return {'FINISHED'}


class MR_OT_team(bpy.types.Operator):
    bl_idname = 'mr.team'
    bl_label = 'Team'
    index: IntProperty(default=0, min=0, max=1)

    def execute(self, context):
        context.scene['mr_team'] = self.index
        for area in context.screen.areas if context.screen else []:
            area.tag_redraw()
        return {'FINISHED'}


class MR_OT_assign_clip(bpy.types.Operator):
    bl_idname = 'mr.assign_clip'
    bl_label = 'Assign clip'
    bl_description = 'Assign the clip action to the control rig and set the scene frame range (30 fps)'
    action: StringProperty()

    def execute(self, context):
        act = bpy.data.actions.get(self.action)
        ctl = ctl_obj()
        if act is None or ctl is None:
            return {'CANCELLED'}
        ad = ctl.animation_data or ctl.animation_data_create()
        ad.action = act
        try:
            if act.slots:
                ad.action_slot = act.slots[0]
        except Exception:
            pass
        n = int(act.get('mr_frames', 30))
        sc = context.scene
        sc.render.fps = FPS
        sc.frame_start, sc.frame_end = 1, 1 + max(n, 1)
        sc.frame_set(1)
        return {'FINISHED'}


class MR_OT_bake_secondary(bpy.types.Operator):
    bl_idname = 'mr.bake_secondary'
    bl_label = 'Bake secondary motion'
    bl_description = 'Simulate the braid and cable spring chains over the scene frame range and key their controls in the current action'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        try:
            done = bake_secondary(ctl_obj(), sc.frame_start, sc.frame_end)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        self.report({'INFO'}, f'secondary motion baked: {done}')
        return {'FINISHED'}


class MR_OT_bake_visemes(bpy.types.Operator):
    bl_idname = 'mr.bake_visemes'
    bl_label = 'Bake visemes to face controls'
    bl_description = 'Convert the viseme_* weights animated on ctl_face into morph weights, jaw and tongue keys with the documented mapping'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ctl = ctl_obj()
        sc = context.scene
        d = data()
        pb = ctl.pose.bones['ctl_face']
        names = [n for n in d['visemes'] if n != 'sil']
        for f in range(sc.frame_start, sc.frame_end + 1):
            sc.frame_set(f)
            bpy.context.view_layer.update()
            morphs, jaw, tongue = viseme_mix({n: float(pb.get('viseme_' + n, 0.0)) for n in names})
            for m in d['morphs']:
                pb[m] = min(1.0, morphs.get(m, 0.0))
                pb.keyframe_insert(f'["{m}"]', frame=f, group='Face')
            ctl.pose.bones['ctl_jaw'].rotation_euler = (math.radians(-d['jaw_max_deg'] * min(1.0, jaw)), 0.0, 0.0)
            ctl.pose.bones['ctl_jaw'].keyframe_insert('rotation_euler', frame=f, group='Face')
        return {'FINISHED'}


class MR_OT_bake_skeleton(bpy.types.Operator):
    bl_idname = 'mr.bake_skeleton'
    bl_label = 'Bake to deformation skeleton'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ctl, skel = ctl_obj(), skel_obj()
        base = ctl.animation_data.action.name if ctl.animation_data and ctl.animation_data.action else 'pose'
        sc = context.scene
        bake_to_skeleton(ctl, skel, sc.frame_start, sc.frame_end, base + '_baked')
        return {'FINISHED'}


# ----------------------------------------------------------------------------- UI
class MR_UL_clips(bpy.types.UIList):
    def draw_item(self, context, layout, data_, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name[2:] if item.name.startswith('A_') else item.name)
        row.label(text=f"{int(item.get('mr_frames', 0))} f")
        op = row.operator('mr.assign_clip', text='', icon='PLAY')
        op.action = item.name

    def filter_items(self, context, data_, propname):
        items = getattr(data_, propname)
        flt = [self.bitflag_filter_item if it.name.startswith('A_') and (not self.filter_name or self.filter_name.lower() in it.name.lower()) else 0 for it in items]
        return flt, []


def _limb_row(layout, ctl, kind, s):
    n = _arm_names(s) if kind == 'ARM' else _leg_names(s)
    pb = ctl.pose.bones.get(n['ik'])
    if pb is None:
        return
    row = layout.row(align=True)
    row.label(text=('Arm ' if kind == 'ARM' else 'Leg ') + s.upper())
    row.prop(pb, '["ik_fk"]', text='IK/FK', slider=True)
    op = row.operator('mr.snap', text='FK<-IK')
    op.limb, op.direction = f'{kind}_{s}', 'FK_TO_IK'
    op = row.operator('mr.snap', text='IK<-FK')
    op.limb, op.direction = f'{kind}_{s}', 'IK_TO_FK'


class MR_PT_main(bpy.types.Panel):
    bl_label = 'MorphRig'
    bl_idname = 'MR_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'

    def draw(self, context):
        ctl = ctl_obj()
        col = self.layout.column(align=True)
        if ctl is None:
            col.label(text='Operative_Control not found')
            return
        row = col.row(align=True)
        row.operator('mr.reset_pose', text='Reset pose')
        row.operator('mr.reset_face', text='Reset face')
        root = ctl.pose.bones['ctl_root']
        col.prop(root, 'scale', index=0, text='Global scale')
        col.prop(root, '["secondary_influence"]', text='Secondary influence')
        lt = ctl.pose.bones['ctl_look_target']
        col.prop(lt, '["look_eyes"]', text='Look-at eyes')
        col.prop(lt, '["look_head"]', text='Look-at head')


class MR_PT_limbs(bpy.types.Panel):
    bl_label = 'IK / FK'
    bl_idname = 'MR_PT_limbs'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'

    def draw(self, context):
        ctl = ctl_obj()
        col = self.layout.column(align=True)
        for kind in ('ARM', 'LEG'):
            for s in ('l', 'r'):
                _limb_row(col, ctl, kind, s)
        for s in ('l', 'r'):
            pb = ctl.pose.bones[f'ctl_foot_ik_{s}']
            col.prop(pb, '["roll"]', text=f'Foot roll {s.upper()}')


class MR_PT_hands(bpy.types.Panel):
    bl_label = 'Hands'
    bl_idname = 'MR_PT_hands'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        ctl = ctl_obj()
        for s in ('l', 'r'):
            pb = ctl.pose.bones[f'ctl_hand_pose_{s}']
            box = self.layout.box()
            box.label(text=f'Hand {s.upper()}')
            box.prop(pb, '["curl"]', text='Curl', slider=True)
            box.prop(pb, '["spread"]', text='Spread', slider=True)
            for f in ('thumb', 'index', 'middle', 'ring', 'pinky'):
                box.prop(pb, f'["{f}_curl"]', text=f.capitalize(), slider=True)


class MR_PT_face(bpy.types.Panel):
    bl_label = 'Face'
    bl_idname = 'MR_PT_face'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'

    def draw(self, context):
        ctl = ctl_obj()
        d = data()
        lay = self.layout
        lay.prop(context.scene, 'mr_face_weight', text='Weight')
        grid = lay.grid_flow(columns=2, align=True)
        for name in d['expressions']:
            op = grid.operator('mr.expression', text=name.replace('_', ' '))
            op.name, op.weight = name, context.scene.mr_face_weight
        lay.label(text='Visemes')
        grid = lay.grid_flow(columns=4, align=True)
        for name in d['visemes']:
            op = grid.operator('mr.viseme', text=name)
            op.name, op.weight = name, context.scene.mr_face_weight
        col = lay.column(align=True)
        col.prop(context.scene, 'mr_blink_l', text='Blink L', slider=True)
        col.prop(context.scene, 'mr_blink_r', text='Blink R', slider=True)
        col.prop(context.scene, 'mr_gaze_yaw', text='Gaze yaw', slider=True)
        col.prop(context.scene, 'mr_gaze_pitch', text='Gaze pitch', slider=True)


class MR_PT_face_sliders(bpy.types.Panel):
    bl_label = 'Face controls (all)'
    bl_idname = 'MR_PT_face_sliders'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_face'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        pb = ctl_obj().pose.bones['ctl_face']
        col = self.layout.column(align=True)
        for m in data()['morphs']:
            col.prop(pb, f'["{m}"]', text=m, slider=True)


class MR_PT_team(bpy.types.Panel):
    bl_label = 'Team accent'
    bl_idname = 'MR_PT_team'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'

    def draw(self, context):
        row = self.layout.row(align=True)
        for i, label in enumerate(('A cyan / circle', 'B magenta / diamond')):
            op = row.operator('mr.team', text=label, depress=(int(context.scene.get('mr_team', 0)) == i))
            op.index = i
        self.layout.prop(context.scene, '["mr_outline"]', text='Rim outline', slider=True)


class MR_PT_clips(bpy.types.Panel):
    bl_label = 'Clips'
    bl_idname = 'MR_PT_clips'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'

    def draw(self, context):
        self.layout.template_list('MR_UL_clips', '', bpy.data, 'actions', context.scene, 'mr_clip_index', rows=8)


class MR_PT_bake(bpy.types.Panel):
    bl_label = 'Bake'
    bl_idname = 'MR_PT_bake'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MorphRig'
    bl_parent_id = 'MR_PT_main'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator('mr.bake_secondary')
        col.operator('mr.bake_visemes')
        col.operator('mr.bake_skeleton')


def _upd_blink(side):
    def f(self, context):
        ctl = ctl_obj()
        if ctl is None:
            return
        a = getattr(self, f'mr_blink_{side}')
        d = data()
        ctl.pose.bones[f'ctl_lid_up_{side}'].rotation_euler = (math.radians(d['lid_close_up_deg'] * a), 0, 0)
        ctl.pose.bones[f'ctl_lid_lo_{side}'].rotation_euler = (math.radians(d['lid_close_lo_deg'] * a), 0, 0)
    return f


def _upd_gaze(self, context):
    ctl = ctl_obj()
    if ctl is None:
        return
    for s in ('l', 'r'):
        ctl.pose.bones[f'ctl_eye_{s}'].rotation_euler = (math.radians(self.mr_gaze_pitch), 0.0, math.radians(self.mr_gaze_yaw))


CLASSES = (MR_OT_reset_pose, MR_OT_reset_face, MR_OT_snap, MR_OT_expression, MR_OT_viseme, MR_OT_team, MR_OT_assign_clip, MR_OT_bake_secondary,
           MR_OT_bake_visemes, MR_OT_bake_skeleton, MR_UL_clips, MR_PT_main, MR_PT_limbs, MR_PT_hands, MR_PT_face, MR_PT_face_sliders, MR_PT_team, MR_PT_clips, MR_PT_bake)


def register():
    for c in CLASSES:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            bpy.utils.unregister_class(c)
            bpy.utils.register_class(c)
    S = bpy.types.Scene
    S.mr_face_weight = FloatProperty(name='Face weight', default=1.0, min=0.0, max=1.5)
    S.mr_blink_l = FloatProperty(name='Blink L', default=0.0, min=0.0, max=1.0, update=_upd_blink('l'))
    S.mr_blink_r = FloatProperty(name='Blink R', default=0.0, min=0.0, max=1.0, update=_upd_blink('r'))
    S.mr_gaze_yaw = FloatProperty(name='Gaze yaw', default=0.0, min=-45.0, max=45.0, update=_upd_gaze)
    S.mr_gaze_pitch = FloatProperty(name='Gaze pitch', default=0.0, min=-35.0, max=35.0, update=_upd_gaze)
    S.mr_clip_index = IntProperty(default=0)


def unregister():
    for c in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except RuntimeError:
            pass
    for p in ('mr_face_weight', 'mr_blink_l', 'mr_blink_r', 'mr_gaze_yaw', 'mr_gaze_pitch', 'mr_clip_index'):
        if hasattr(bpy.types.Scene, p):
            delattr(bpy.types.Scene, p)


def install_into_blend(face_lib, S, source_path=None):
    """Store this script and its preset data as the text datablock 'MorphRig_Tools.py' (registered on load, needs script auto-run)."""
    src = open(source_path or __file__, encoding='utf-8').read()
    marker = 'MR_EMBEDDED_DATA = None'
    payload = 'MR_EMBEDDED_DATA = ' + repr(export_data(face_lib, S))
    text = src.replace(marker, payload, 1) + '\n\nregister()\n'
    t = bpy.data.texts.get('MorphRig_Tools.py') or bpy.data.texts.new('MorphRig_Tools.py')
    t.clear()
    t.write(text)
    t.use_module = True
    return t


if __name__ == '__main__':
    register()

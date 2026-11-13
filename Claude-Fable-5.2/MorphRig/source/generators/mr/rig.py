"""Animator control rig (RIG_Operative) and its link to the deformation skeleton (SKEL_Operative).

RIG_Operative contains, for every deformation bone, a bone of the same name that carries the final
transform (FK control, IK/FK result or mechanism), plus the animator controls and helper mechanisms.
SKEL_Operative only copies those transforms (Copy Transforms, world space) and is what gets baked/exported.

Controls (suffix _l/_r where mirrored):
  root, cog, hips, spine_01..03, neck_01, head, clavicle
  arms : upperarm_fk, lowerarm_fk, hand_fk | hand_ik, elbow_pole | props["arm_ik"] on hand_ik
  legs : thigh_fk, calf_fk, foot_fk, toe_fk | foot_ik (roll, bank, heel_pivot, toe_pivot, toe_bend), knee_pole
  hands: finger bones (FK) + props on fingers_<side>: curl_<finger>, spread, fist
  face : jaw, eye targets (look_target, eye_target_l/r), tongue, props on 'face' (controls, visemes, expressions)
  props: blade_l, prop_cell, prop_cell_spare, prop_beacon (+ hold_* props and HOLD_* grip bones)
  secondary: cable_01..04 (FK, simulated by tools)
"""
import math
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from . import skel, facedefs
from .skel import J, mirror_name
from .util import V, norm, mirror_x, frame_from

RIG_NAME = 'RIG_Operative'
SKEL_NAME = 'SKEL_Operative'

FINGER_NAMES = ['thumb', 'index', 'middle', 'ring', 'pinky']
CURL_DEG = {  # per phalanx flexion (deg) at curl = 1
    'thumb': (28.0, 52.0, 62.0), 'index': (82.0, 100.0, 68.0), 'middle': (84.0, 102.0, 70.0),
    'ring': (86.0, 104.0, 70.0), 'pinky': (88.0, 100.0, 68.0)}
SPREAD_DEG = {'thumb': 26.0, 'index': 11.0, 'middle': 2.5, 'ring': -7.0, 'pinky': -16.0}
FIST_EXTRA = {'thumb': 0.75, 'index': 1.0, 'middle': 1.0, 'ring': 1.0, 'pinky': 1.0}

FOOT = dict(heel=V(0.102, 0.066, 0.0), toe=V(0.107, -0.214, 0.0), inner=V(0.058, -0.110, 0.0), outer=V(0.154, -0.110, 0.0))

HOLDERS = {  # prop -> holders (result bone names) that can carry it
    'prop_cell': ['hand_l', 'hand_r'],
    'prop_cell_spare': ['hand_l', 'hand_r'],
    'prop_beacon': ['hand_l', 'hand_r'],
}

_defs = []       # bone definitions collected before edit mode


def _add(name, parent, head, tail, zhint, layer='MCH', deform_target=False):
    _defs.append(dict(name=name, parent=parent, head=np.array(head, float), tail=np.array(tail, float),
                      zhint=np.array(zhint, float), layer=layer, deform_target=deform_target))


def _copy_of(src, name, parent, layer='MCH', scale=1.0):
    b = skel.BONE_BY_NAME[src]
    tail = b['head'] + (b['tail'] - b['head']) * scale
    _add(name, parent, b['head'], tail, b['zhint'], layer)


def _sidevec(v, side):
    return np.array(v, float) if side == 'l' else mirror_x(v)


def define_bones():
    """Fill _defs with the complete control-rig bone list."""
    del _defs[:]
    B = skel.BONE_BY_NAME
    up, fwd, back = skel.UP, skel.FWD, skel.BACK
    # ---------------- root / torso
    _add('root', None, (0, 0, 0), (0, 0.20, 0), up, 'Root')
    _add('cog', 'root', J['pelvis'], J['pelvis'] + V(0, 0, 0.12), fwd, 'Torso')
    _add('hips', 'cog', J['pelvis'], J['pelvis'] + V(0, 0, -0.08), back, 'Torso')
    _copy_of('pelvis', 'pelvis', 'hips')
    _copy_of('spine_01', 'spine_01', 'cog', 'Torso')
    _copy_of('spine_02', 'MCH_spine_02', 'spine_01', scale=0.5)
    _copy_of('spine_02', 'spine_02', 'MCH_spine_02', 'Torso')
    _copy_of('spine_03', 'MCH_spine_03', 'spine_02', scale=0.5)
    _copy_of('spine_03', 'spine_03', 'MCH_spine_03', 'Torso')
    _copy_of('neck_01', 'neck_01', 'spine_03', 'Torso')
    _copy_of('head', 'head', 'neck_01', 'Torso')
    # head look-at mechanism: MCH_head_track damps towards the look target, head blends to it via property
    _add('look_target', 'root', V(0, -1.0, J['eye_l'][2]), V(0, -1.0, J['eye_l'][2] + 0.06), fwd, 'Face')
    # ---------------- face
    _add('face', 'head', V(0, -0.02, 1.86), V(0, -0.02, 1.90), fwd, 'Face')
    _add('MCH_jaw', 'head', B['jaw']['head'], B['jaw']['tail'], B['jaw']['zhint'])
    _copy_of('jaw', 'jaw', 'MCH_jaw', 'Face')
    _add('MCH_tongue_01', 'jaw', B['tongue_01']['head'], B['tongue_01']['tail'], B['tongue_01']['zhint'])
    _copy_of('tongue_01', 'tongue_01', 'MCH_tongue_01', 'Face')
    _add('MCH_tongue_02', 'tongue_01', B['tongue_02']['head'], B['tongue_02']['tail'], B['tongue_02']['zhint'])
    _copy_of('tongue_02', 'tongue_02', 'MCH_tongue_02', 'Face')
    for s in ('l', 'r'):
        e = J['eye_' + s]
        _add('eye_target_' + s, 'look_target', V(e[0], -1.0, e[2]), V(e[0], -1.0, e[2] + 0.03), fwd, 'Face')
        _add('MCH_eye_' + s, 'head', B['eye_' + s]['head'], B['eye_' + s]['tail'], B['eye_' + s]['zhint'])
        _copy_of('eye_' + s, 'eye_' + s, 'MCH_eye_' + s, 'Face')
        for lid in ('lid_upper_', 'lid_lower_'):
            n = lid + s
            _add('MCH_' + n, 'head', B[n]['head'], B[n]['tail'], B[n]['zhint'])
            _copy_of(n, n, 'MCH_' + n, 'Face')
    # ---------------- secondary cable (FK controls)
    par = 'head'
    for i in range(1, 5):
        n = 'cable_%02d' % i
        _copy_of(n, n, par, 'Secondary')
        par = n
    # ---------------- arms / hands
    for s in ('l', 'r'):
        L = lambda n: n + '_' + s
        _copy_of(L('clavicle'), L('MCH_clavicle'), 'spine_03', scale=0.5)
        _copy_of(L('clavicle'), L('clavicle'), L('MCH_clavicle'), 'Torso')
        # FK chain
        _copy_of(L('upperarm'), L('upperarm_fk'), L('clavicle'), 'Arm FK')
        _copy_of(L('lowerarm'), L('lowerarm_fk'), L('upperarm_fk'), 'Arm FK')
        _copy_of(L('hand'), L('hand_fk'), L('lowerarm_fk'), 'Arm FK')
        # IK chain
        _copy_of(L('upperarm'), L('MCH_upperarm_ik'), L('clavicle'))
        _copy_of(L('lowerarm'), L('MCH_lowerarm_ik'), L('MCH_upperarm_ik'))
        _copy_of(L('hand'), L('hand_ik'), 'root', 'Arm IK')
        _copy_of(L('hand'), L('MCH_hand_ik'), L('MCH_lowerarm_ik'))
        el = J[L('lowerarm')]
        pole = el + V(0, 0.32, -0.05)
        _add(L('elbow_pole'), 'root', pole, pole + V(0, 0.05, 0), up, 'Arm IK')
        # results
        _copy_of(L('upperarm'), L('upperarm'), L('clavicle'))
        _copy_of(L('lowerarm'), L('lowerarm'), L('upperarm'))
        _copy_of(L('hand'), L('hand'), L('lowerarm'))
        # twist / helpers
        _copy_of(L('upperarm_twist'), L('upperarm_twist'), L('clavicle'))
        _copy_of(L('shoulder_helper'), L('shoulder_helper'), L('clavicle'))
        _copy_of(L('elbow_helper'), L('elbow_helper'), L('upperarm'))
        _copy_of(L('lowerarm_twist'), L('lowerarm_twist'), L('lowerarm'))
        hb = B[L('hand')]
        hz = skel.bone_frame(L('hand'))[:, 2]
        _add(L('MCH_wrist_twist_tgt'), L('hand'), hb['head'] + hz * 0.10, hb['head'] + hz * 0.13, hb['zhint'])
        # fingers
        _add(L('fingers'), L('hand'), hb['head'] + skel.bone_frame(L('hand'))[:, 1] * 0.05 - skel.bone_frame(L('hand'))[:, 0] * 0.05,
             hb['head'] + skel.bone_frame(L('hand'))[:, 1] * 0.05 - skel.bone_frame(L('hand'))[:, 0] * 0.08, hb['zhint'], 'Fingers')
        for f in FINGER_NAMES:
            par = L('hand')
            for i in range(1, 4):
                n = '%s_%02d_%s' % (f, i, s)
                _add('MCH_' + n, par, B[n]['head'], B[n]['head'] + (B[n]['tail'] - B[n]['head']) * 0.5, B[n]['zhint'])
                _copy_of(n, n, 'MCH_' + n, 'Fingers')
                par = n
    # ---------------- legs
    for s in ('l', 'r'):
        L = lambda n: n + '_' + s
        sx = 1.0 if s == 'l' else -1.0
        _copy_of(L('thigh'), L('thigh_fk'), 'pelvis', 'Leg FK')
        _copy_of(L('calf'), L('calf_fk'), L('thigh_fk'), 'Leg FK')
        _copy_of(L('foot'), L('foot_fk'), L('calf_fk'), 'Leg FK')
        _copy_of(L('ball'), L('toe_fk'), L('foot_fk'), 'Leg FK')
        _copy_of(L('thigh'), L('MCH_thigh_ik'), 'pelvis')
        _copy_of(L('calf'), L('MCH_calf_ik'), L('MCH_thigh_ik'))
        ank = J[L('foot')]
        ball = J[L('ball')]
        heel = _sidevec(FOOT['heel'], s)
        toe = _sidevec(FOOT['toe'], s)
        inner = _sidevec(FOOT['inner'], s)
        outer = _sidevec(FOOT['outer'], s)
        # foot control: origin at the ankle, lying along the foot
        _add(L('foot_ik'), 'root', ank, ank + V(0, -0.14, 0), up, 'Leg IK')
        _add(L('MCH_foot_heel'), L('foot_ik'), heel, heel + V(0, -0.06, 0), up)
        _add(L('MCH_foot_toe'), L('MCH_foot_heel'), toe, toe + V(0, -0.05, 0), up)
        _add(L('MCH_foot_bank_in'), L('MCH_foot_toe'), inner, inner + V(0, -0.05, 0), up)
        _add(L('MCH_foot_bank_out'), L('MCH_foot_bank_in'), outer, outer + V(0, -0.05, 0), up)
        _add(L('MCH_foot_ball'), L('MCH_foot_bank_out'), ball, ball + V(0, 0.06, 0), up)
        _add(L('MCH_ankle_tgt'), L('MCH_foot_ball'), ank, ank + V(0, 0, 0.05), fwd)
        _copy_of(L('foot'), L('MCH_foot_ik'), L('MCH_foot_ball'))
        _copy_of(L('ball'), L('MCH_toe_ik'), L('MCH_foot_bank_out'))
        kn = J[L('calf')]
        pole = kn + V(0, -0.50, 0.0)
        _add(L('knee_pole'), 'root', pole, pole + V(0, -0.05, 0), up, 'Leg IK')
        _copy_of(L('thigh'), L('thigh'), 'pelvis')
        _copy_of(L('calf'), L('calf'), L('thigh'))
        _copy_of(L('foot'), L('foot'), L('calf'))
        _copy_of(L('ball'), L('ball'), L('foot'))
        _copy_of(L('thigh_twist'), L('thigh_twist'), 'pelvis')
        _copy_of(L('hip_helper'), L('hip_helper'), 'pelvis')
        _copy_of(L('knee_helper'), L('knee_helper'), L('thigh'))
    # ---------------- props
    _copy_of('blade_l', 'blade_l', 'lowerarm_l', 'Props')
    for prop, rest_parent in (('prop_cell', 'lowerarm_r'), ('prop_cell_spare', 'pelvis'), ('prop_beacon', 'pelvis')):
        _copy_of(prop, prop, rest_parent, 'Props')
        for holder in HOLDERS[prop]:
            hb = B[holder]
            fr = skel.bone_frame(holder)
            side = holder[-1]
            palm = hb['head'] + fr[:, 1] * 0.070 + fr[:, 0] * 0.030
            _add('HOLD_%s_%s' % (prop, holder), holder, palm, palm + fr[:, 2] * 0.06, fr[:, 1], 'Props')
    return _defs


LAYER_COLORS = {'Root': 'THEME09', 'Torso': 'THEME04', 'Arm IK': 'THEME01', 'Arm FK': 'THEME03', 'Leg IK': 'THEME01',
                'Leg FK': 'THEME03', 'Fingers': 'THEME02', 'Face': 'THEME06', 'Props': 'THEME07', 'Secondary': 'THEME11',
                'MCH': 'THEME10'}


# ------------------------------------------------------------------------------------ widgets
def _widget(name, verts, edges):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    return ob


def make_widgets(collection):
    w = {}
    n = 24
    circ = [(math.cos(2 * math.pi * i / n), 0.0, math.sin(2 * math.pi * i / n)) for i in range(n)]
    w['circle'] = _widget('WGT_circle', circ, [(i, (i + 1) % n) for i in range(n)])
    c = 0.5
    cube = [(-c, -c, -c), (c, -c, -c), (c, c, -c), (-c, c, -c), (-c, -c, c), (c, -c, c), (c, c, c), (-c, c, c)]
    w['cube'] = _widget('WGT_cube', cube, [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)])
    dia = [(0, 0, 1), (1, 0, 0), (0, 0, -1), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
    w['diamond'] = _widget('WGT_diamond', dia, [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4), (0, 5), (1, 5), (2, 5), (3, 5)])
    sq = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
    w['square'] = _widget('WGT_square', sq, [(0, 1), (1, 2), (2, 3), (3, 0)])
    arrow = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), (0, 0, 1), (0, 0, 1.6), (-0.3, 0, 1.3), (0.3, 0, 1.3)]
    w['root'] = _widget('WGT_root', arrow, [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (5, 7)])
    for ob in w.values():
        collection.objects.link(ob)
    return w


# ------------------------------------------------------------------------------------ helpers
def _pole_angle(base, ik, pole_loc):
    """Pole angle that keeps the rest pose unchanged (edit-space data bones)."""
    pole_normal = (ik.tail_local - base.head_local).cross(pole_loc - base.head_local)
    projected = pole_normal.cross(base.tail_local - base.head_local)
    x_axis = base.matrix_local.to_3x3().col[0]
    n = (base.tail_local - base.head_local).normalized()
    ang = x_axis.angle(projected)
    if x_axis.cross(projected).dot(n) > 0:
        ang = -ang
    return ang


def _prop(pb, name, default=0.0, lo=0.0, hi=1.0, desc=''):
    pb[name] = float(default)
    ui = pb.id_properties_ui(name)
    ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, default=float(default), description=desc)
    try:
        pb.property_overridable_library_set('["%s"]' % name, True)
    except Exception:
        pass


def _drv(owner, path, index, expr, variables, rig):
    """variables: {name: ('prop', bone, prop) | ('xform', bone, 'ROT_X', space)}"""
    fc = owner.driver_add(path, index) if index is not None else owner.driver_add(path)
    d = fc.driver
    d.type = 'SCRIPTED'
    for name, spec in variables.items():
        v = d.variables.new()
        v.name = name
        if spec[0] == 'prop':
            v.type = 'SINGLE_PROP'
            v.targets[0].id = rig
            v.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (spec[1], spec[2])
        else:
            v.type = 'TRANSFORMS'
            v.targets[0].id = rig
            v.targets[0].bone_target = spec[1]
            v.targets[0].transform_type = spec[2]
            v.targets[0].transform_space = spec[3]
            v.targets[0].rotation_mode = 'SWING_TWIST_Y' if len(spec) > 4 and spec[4] == 'twist' else 'AUTO'
    d.expression = expr
    return fc


def _lock(pb, loc=True, rot=False, scale=True):
    pb.lock_location = (loc, loc, loc)
    pb.lock_rotation = (rot, rot, rot)
    pb.lock_rotation_w = rot
    pb.lock_scale = (scale, scale, scale)


# ------------------------------------------------------------------------------------ build
def build_rig(collection=None, widget_collection=None):
    defs = define_bones()
    arm = bpy.data.armatures.new(RIG_NAME)
    rig = bpy.data.objects.new(RIG_NAME, arm)
    (collection or bpy.context.scene.collection).objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for d in defs:
        eb = arm.edit_bones.new(d['name'])
        eb.head = Vector(d['head'])
        eb.tail = Vector(d['tail'])
        eb.align_roll(Vector(d['zhint']))
        eb.use_deform = False
        eb.use_connect = False
    for d in defs:
        if d['parent']:
            arm.edit_bones[d['name']].parent = arm.edit_bones[d['parent']]
    bpy.ops.object.mode_set(mode='OBJECT')
    P = rig.pose.bones
    DB = arm.bones
    # ---- bone collections
    colls = {}
    for d in defs:
        lay = d['layer']
        if lay not in colls:
            colls[lay] = arm.collections.new(lay)
        colls[lay].assign(DB[d['name']])
    colls['MCH'].is_visible = False
    for pb in P:
        pb.rotation_mode = 'QUATERNION'
    layer_of = {d['name']: d['layer'] for d in defs}
    for name, lay in layer_of.items():
        try:
            P[name].color.palette = LAYER_COLORS.get(lay, 'DEFAULT')
        except Exception:
            pass

    def cn(bone, ctype, **kw):
        c = P[bone].constraints.new(ctype)
        if 'subtarget' in kw:
            c.target = rig
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    # ---------------- breathing layer (additive, lives under the FK controls)
    _prop(P['cog'], 'breath', 0.0, -1.0, 1.0, 'chest expansion: +1 inhaled, -1 exhaled')
    vb = {'b': ('prop', 'cog', 'breath')}
    for b, amt in (('MCH_spine_02', -0.010), ('MCH_spine_03', -0.020)):
        P[b].rotation_mode = 'XYZ'
        _drv(P[b], 'rotation_euler', 0, '%.4f*b' % amt, vb, rig)
    for sd, sg in (('l', 1.0), ('r', -1.0)):
        P['MCH_clavicle_' + sd].rotation_mode = 'XYZ'
        _drv(P['MCH_clavicle_' + sd], 'rotation_euler', 2, '%.4f*b' % (0.022 * sg), vb, rig)

    # ---------------- face properties
    face = P['face']
    for ctl in facedefs.CONTROLS:
        _prop(face, ctl, 0.0, 0.0, 1.0, 'face control')
    for vis in facedefs.VISEMES:
        if vis != 'sil':
            _prop(face, 'vis_' + vis, 0.0, 0.0, 1.0, 'viseme: ' + facedefs.VISEMES[vis][0])
    for ex in facedefs.EXPRESSIONS:
        if ex != 'neutral':
            _prop(face, 'expr_' + ex, 0.0, 0.0, 1.0, 'expression preset')
    _prop(face, 'eyes_track', 1.0, 0.0, 1.0, 'eyes follow look_target')
    _prop(face, 'head_track', 0.0, 0.0, 1.0, 'head follows look_target')
    _prop(face, 'lid_follow', 1.0, 0.0, 1.0, 'eyelids follow the eyeballs')

    # ---------------- eyes / lids / jaw / tongue
    for s in ('l', 'r'):
        c = cn('MCH_eye_' + s, 'DAMPED_TRACK', subtarget='eye_target_' + s, track_axis='TRACK_Y')
        _drv(c, 'influence', None, 'a', {'a': ('prop', 'face', 'eyes_track')}, rig)
        lim = cn('MCH_eye_' + s, 'LIMIT_ROTATION', owner_space='LOCAL')
        lim.use_limit_x = True
        lim.min_x = -math.radians(facedefs.EYE_LOOK['max_pitch_down_deg'])
        lim.max_x = math.radians(facedefs.EYE_LOOK['max_pitch_up_deg'])
        lim.use_limit_z = True
        lim.min_z = -math.radians(facedefs.EYE_LOOK['max_yaw_deg'])
        lim.max_z = math.radians(facedefs.EYE_LOOK['max_yaw_deg'])
    c = cn('head', 'DAMPED_TRACK', subtarget='look_target', track_axis='TRACK_Z')
    _drv(c, 'influence', None, 'a', {'a': ('prop', 'face', 'head_track')}, rig)

    def control_expr(ctl, prefix='a'):
        """(expression, variables) computing the final 0..1 value of a face control from direct/viseme/expression props."""
        variables = {prefix + '0': ('prop', 'face', ctl)}
        terms = [prefix + '0']
        k = 1
        for vis, (_, wmap) in facedefs.VISEMES.items():
            if ctl in wmap:
                vn = '%s%d' % (prefix, k)
                k += 1
                variables[vn] = ('prop', 'face', 'vis_' + vis)
                terms.append('%.4f*%s' % (wmap[ctl], vn))
        for ex, wmap in facedefs.EXPRESSIONS.items():
            if ctl in wmap:
                vn = '%s%d' % (prefix, k)
                k += 1
                variables[vn] = ('prop', 'face', 'expr_' + ex)
                terms.append('%.4f*%s' % (wmap[ctl], vn))
        return 'clamp(' + '+'.join(terms) + ',0,1)', variables

    # bone controls -> MCH bone channels
    chan = {}   # (bone, kind, axis) -> list of (control, amount)
    for ctl, items in facedefs.BONE_CONTROLS.items():
        for (bone, kind, axis, amount) in items:
            chan.setdefault((bone, kind, axis), []).append((ctl, amount))
    for (bone, kind, axis), lst in chan.items():
        mch = P['MCH_' + bone]
        mch.rotation_mode = 'XYZ'
        variables = {}
        terms = []
        for i, (ctl, amount) in enumerate(lst):
            expr, vs = control_expr(ctl, prefix='pqrstuvw'[i])
            variables.update(vs)
            amt = math.radians(amount) if kind == 'rot' else amount
            terms.append('%.6f*%s' % (amt, expr))
        full = '+'.join(terms)
        if bone.startswith('lid_') and kind == 'rot' and axis == 'X':
            s = bone[-1]
            follow = facedefs.EYE_LOOK['lid_upper_follow'] if 'upper' in bone else facedefs.EYE_LOOK['lid_lower_follow']
            variables['eyx'] = ('xform', 'MCH_eye_' + s, 'ROT_X', 'LOCAL_SPACE')
            variables['lf'] = ('prop', 'face', 'lid_follow')
            full += '+%.3f*eyx*lf' % follow
        idx = 'XYZ'.index(axis)
        _drv(mch, 'rotation_euler' if kind == 'rot' else 'location', idx, full, variables, rig)
    face_info = dict(control_expr=control_expr)

    # ---------------- arms
    for s in ('l', 'r'):
        L = lambda n: n + '_' + s
        hik = P[L('hand_ik')]
        _prop(hik, 'arm_ik', 0.0, 0.0, 1.0, '0 = FK, 1 = IK')
        ik = cn(L('MCH_lowerarm_ik'), 'IK', subtarget=L('hand_ik'), chain_count=2)
        ik.pole_target = rig
        ik.pole_subtarget = L('elbow_pole')
        ik.pole_angle = _pole_angle(DB[L('MCH_upperarm_ik')], DB[L('MCH_lowerarm_ik')], DB[L('elbow_pole')].head_local)
        ik.use_stretch = False
        cn(L('MCH_hand_ik'), 'COPY_ROTATION', subtarget=L('hand_ik'), target_space='WORLD', owner_space='WORLD')
        for res, fk, ikb in ((L('upperarm'), L('upperarm_fk'), L('MCH_upperarm_ik')), (L('lowerarm'), L('lowerarm_fk'), L('MCH_lowerarm_ik')),
                             (L('hand'), L('hand_fk'), L('MCH_hand_ik'))):
            cn(res, 'COPY_TRANSFORMS', subtarget=fk)
            c = cn(res, 'COPY_TRANSFORMS', subtarget=ikb)
            _drv(c, 'influence', None, 'a', {'a': ('prop', L('hand_ik'), 'arm_ik')}, rig)
        # twist + helpers
        cn(L('upperarm_twist'), 'COPY_LOCATION', subtarget=L('upperarm'))
        cn(L('upperarm_twist'), 'DAMPED_TRACK', subtarget=L('lowerarm'), track_axis='TRACK_Y')
        cn(L('shoulder_helper'), 'COPY_ROTATION', subtarget=L('upperarm'), target_space='LOCAL', owner_space='LOCAL', influence=0.5)
        cn(L('elbow_helper'), 'COPY_ROTATION', subtarget=L('lowerarm'), target_space='LOCAL', owner_space='LOCAL', influence=0.5)
        lt = cn(L('lowerarm_twist'), 'LOCKED_TRACK', subtarget=L('MCH_wrist_twist_tgt'), track_axis='TRACK_Z', lock_axis='LOCK_Y')
        # fingers
        fp = P[L('fingers')]
        for f in FINGER_NAMES:
            _prop(fp, 'curl_' + f, 0.0, -0.4, 1.2, 'finger curl')
        _prop(fp, 'spread', 0.0, -1.0, 1.0, 'finger spread')
        _prop(fp, 'fist', 0.0, 0.0, 1.0, 'close the whole hand')
        for f in FINGER_NAMES:
            for i in range(1, 4):
                n = 'MCH_%s_%02d_%s' % (f, i, s)
                mch = P[n]
                mch.rotation_mode = 'XYZ'
                ang = math.radians(CURL_DEG[f][i - 1])
                _drv(mch, 'rotation_euler', 0, '%.5f*(c+%.3f*f)' % (ang, FIST_EXTRA[f]),
                     {'c': ('prop', L('fingers'), 'curl_' + f), 'f': ('prop', L('fingers'), 'fist')}, rig)
                if i == 1:
                    sp = math.radians(SPREAD_DEG[f])
                    _drv(mch, 'rotation_euler', 2, '%.5f*sp*(1-0.8*f)' % sp,
                         {'sp': ('prop', L('fingers'), 'spread'), 'f': ('prop', L('fingers'), 'fist')}, rig)
    # ---------------- legs
    for s in ('l', 'r'):
        L = lambda n: n + '_' + s
        fik = P[L('foot_ik')]
        _prop(fik, 'leg_ik', 1.0, 0.0, 1.0, '0 = FK, 1 = IK')
        _prop(fik, 'roll', 0.0, -1.0, 1.5, 'heel (-) / ball / toe (+) roll, 1 = 30 deg on the ball')
        _prop(fik, 'bank', 0.0, -1.0, 1.0, 'side roll: - inner edge, + outer edge (30 deg at 1)')
        _prop(fik, 'heel_pivot', 0.0, -1.5, 1.5, 'yaw around the heel (rad)')
        _prop(fik, 'toe_pivot', 0.0, -1.5, 1.5, 'yaw around the toe tip (rad)')
        _prop(fik, 'toe_bend', 0.0, -2.0, 2.0, 'extra toe flex (45 deg at 1)')
        r30 = math.radians(30.0)
        for b in ('MCH_foot_heel', 'MCH_foot_toe', 'MCH_foot_bank_in', 'MCH_foot_bank_out', 'MCH_foot_ball', 'MCH_toe_ik'):
            P[L(b)].rotation_mode = 'XYZ'
        vr = {'r': ('prop', L('foot_ik'), 'roll')}
        # bones lie along -Y (forward) with Z up: X axis = Y x Z ; pitching the toe down is a rotation about local X
        sgn = 1.0
        _drv(P[L('MCH_foot_heel')], 'rotation_euler', 0, '%.5f*min(r,0)' % (-r30 * sgn), vr, rig)
        _drv(P[L('MCH_foot_heel')], 'rotation_euler', 2, 'a', {'a': ('prop', L('foot_ik'), 'heel_pivot')}, rig)
        _drv(P[L('MCH_foot_toe')], 'rotation_euler', 0, '%.5f*max(r-1,0)' % (-r30 * 2.0 * sgn), vr, rig)
        _drv(P[L('MCH_foot_toe')], 'rotation_euler', 2, 'a', {'a': ('prop', L('foot_ik'), 'toe_pivot')}, rig)
        side_sign = 1.0 if s == 'l' else -1.0
        _drv(P[L('MCH_foot_bank_in')], 'rotation_euler', 1, '%.5f*min(b,0)' % (-r30 * side_sign), {'b': ('prop', L('foot_ik'), 'bank')}, rig)
        _drv(P[L('MCH_foot_bank_out')], 'rotation_euler', 1, '%.5f*max(b,0)' % (-r30 * side_sign), {'b': ('prop', L('foot_ik'), 'bank')}, rig)
        # ball bone points backwards (+Y): heel lift = rotation about its local X
        _drv(P[L('MCH_foot_ball')], 'rotation_euler', 0, '%.5f*min(max(r,0),1)' % (r30), vr, rig)
        _drv(P[L('MCH_toe_ik')], 'rotation_euler', 0, '%.5f*t' % (math.radians(45.0)), {'t': ('prop', L('foot_ik'), 'toe_bend')}, rig)
        ik = cn(L('MCH_calf_ik'), 'IK', subtarget=L('MCH_ankle_tgt'), chain_count=2)
        ik.pole_target = rig
        ik.pole_subtarget = L('knee_pole')
        ik.pole_angle = _pole_angle(DB[L('MCH_thigh_ik')], DB[L('MCH_calf_ik')], DB[L('knee_pole')].head_local)
        ik.use_stretch = False
        for res, fk, ikb in ((L('thigh'), L('thigh_fk'), L('MCH_thigh_ik')), (L('calf'), L('calf_fk'), L('MCH_calf_ik')),
                             (L('foot'), L('foot_fk'), L('MCH_foot_ik')), (L('ball'), L('toe_fk'), L('MCH_toe_ik'))):
            cn(res, 'COPY_TRANSFORMS', subtarget=fk)
            c = cn(res, 'COPY_TRANSFORMS', subtarget=ikb)
            _drv(c, 'influence', None, 'a', {'a': ('prop', L('foot_ik'), 'leg_ik')}, rig)
        cn(L('thigh_twist'), 'COPY_LOCATION', subtarget=L('thigh'))
        cn(L('thigh_twist'), 'DAMPED_TRACK', subtarget=L('calf'), track_axis='TRACK_Y')
        cn(L('hip_helper'), 'COPY_ROTATION', subtarget=L('thigh'), target_space='LOCAL', owner_space='LOCAL', influence=0.5)
        cn(L('knee_helper'), 'COPY_ROTATION', subtarget=L('calf'), target_space='LOCAL', owner_space='LOCAL', influence=0.5)
    # ---------------- props
    for prop, holders in HOLDERS.items():
        pb = P[prop]
        for holder in holders:
            pn = 'hold_' + holder
            _prop(pb, pn, 0.0, 0.0, 1.0, 'prop is carried by ' + holder + ' (through its HOLD bone)')
            c = cn(prop, 'COPY_TRANSFORMS', subtarget='HOLD_%s_%s' % (prop, holder))
            c.name = 'Hold ' + holder
            _drv(c, 'influence', None, 'a', {'a': ('prop', prop, pn)}, rig)
    _lock(P['blade_l'], loc=False, rot=True, scale=True)
    P['blade_l'].lock_location = (True, False, True)
    lim = cn('blade_l', 'LIMIT_LOCATION', owner_space='LOCAL')
    lim.use_min_y = True
    lim.use_max_y = True
    lim.min_y = 0.0
    lim.max_y = skel.BLADE_TRAVEL
    lim.use_transform_limit = True

    # ---------------- widgets / display
    if widget_collection is None:
        widget_collection = bpy.data.collections.new('WGT')
        bpy.context.scene.collection.children.link(widget_collection)
    wg = make_widgets(widget_collection)
    widget_collection.hide_viewport = True
    widget_collection.hide_render = True

    def shape(bone, w, scale=1.0, rot=(0, 0, 0), loc=(0, 0, 0)):
        pb = P[bone]
        pb.custom_shape = wg[w]
        ln = DB[bone].length
        sc = scale / max(ln, 1e-6)
        pb.custom_shape_scale_xyz = (sc, sc, sc)
        pb.use_custom_shape_bone_size = True
        pb.custom_shape_rotation_euler = rot
        pb.custom_shape_translation = loc
    shape('root', 'root', 0.45, rot=(math.pi / 2, 0, 0))
    shape('cog', 'square', 0.26, rot=(math.pi / 2, 0, 0))
    shape('hips', 'circle', 0.21, rot=(0, 0, 0))
    for b, r in (('spine_01', 0.17), ('spine_02', 0.18), ('spine_03', 0.20), ('neck_01', 0.08), ('head', 0.12)):
        shape(b, 'circle', r)
    shape('look_target', 'diamond', 0.05)
    shape('face', 'square', 0.03)
    shape('jaw', 'diamond', 0.012, loc=(0, 0.11, 0))
    for s in ('l', 'r'):
        L = lambda n: n + '_' + s
        shape(L('eye_target'), 'circle', 0.02, rot=(math.pi / 2, 0, 0))
        shape(L('clavicle'), 'diamond', 0.035, loc=(0, 0.08, 0.06))
        shape(L('upperarm_fk'), 'circle', 0.07)
        shape(L('lowerarm_fk'), 'circle', 0.06)
        shape(L('hand_fk'), 'circle', 0.05)
        shape(L('hand_ik'), 'cube', 0.09)
        shape(L('elbow_pole'), 'diamond', 0.03)
        shape(L('fingers'), 'square', 0.02)
        shape(L('thigh_fk'), 'circle', 0.11)
        shape(L('calf_fk'), 'circle', 0.08)
        shape(L('foot_fk'), 'circle', 0.07)
        shape(L('toe_fk'), 'circle', 0.05)
        shape(L('foot_ik'), 'cube', 0.12, loc=(0, 0.03, -0.04))
        shape(L('knee_pole'), 'diamond', 0.03)
        for f in FINGER_NAMES:
            for i in range(1, 4):
                shape('%s_%02d_%s' % (f, i, s), 'circle', 0.011)
    for b in ('cable_01', 'cable_02', 'cable_03', 'cable_04'):
        shape(b, 'circle', 0.02)
    for b in ('blade_l', 'prop_cell', 'prop_cell_spare', 'prop_beacon'):
        shape(b, 'cube', 0.05)
    # transform locks for clarity
    for s in ('l', 'r'):
        for b in ('upperarm_fk', 'lowerarm_fk', 'hand_fk', 'thigh_fk', 'calf_fk', 'foot_fk', 'toe_fk', 'clavicle'):
            _lock(P[b + '_' + s], loc=True, rot=False, scale=True)
        for b in ('elbow_pole', 'knee_pole', 'eye_target'):
            _lock(P[b + '_' + s], loc=False, rot=True, scale=True)
        for f in FINGER_NAMES:
            for i in range(1, 4):
                _lock(P['%s_%02d_%s' % (f, i, s)], loc=True, rot=False, scale=True)
    for b in ('spine_01', 'spine_02', 'spine_03', 'neck_01', 'head', 'hips'):
        _lock(P[b], loc=True, rot=False, scale=True)
    arm.display_type = 'STICK'
    rig.show_in_front = True
    rig['rig_id'] = 'morphrig.operative/1'
    return rig, face_info


def link_skeleton(skel_ob, rig):
    """SKEL bones copy the world transform of the RIG bone with the same name."""
    for pb in skel_ob.pose.bones:
        if pb.name not in rig.pose.bones:
            raise RuntimeError('rig has no driver bone for ' + pb.name)
        for c in list(pb.constraints):
            pb.constraints.remove(c)
        c = pb.constraints.new('COPY_TRANSFORMS')
        c.name = 'RIG'
        c.target = rig
        c.subtarget = pb.name
    skel_ob['follow_rig'] = 1


def set_follow(skel_ob, on=True):
    for pb in skel_ob.pose.bones:
        for c in pb.constraints:
            if c.name == 'RIG':
                c.mute = not on
    skel_ob['follow_rig'] = 1 if on else 0


def check_simple_drivers(*ids):
    """All drivers must be 'simple expressions' so the rig works without auto-run Python scripts."""
    bad = []
    for idb in ids:
        ad = getattr(idb, 'animation_data', None)
        if ad is None:
            continue
        for fc in ad.drivers:
            if fc.driver.type == 'SCRIPTED' and not fc.driver.is_simple_expression:
                bad.append((idb.name, fc.data_path, fc.driver.expression))
    return bad


def add_shape_key_drivers(mesh_ob, rig, face_info):
    """Drive every facial shape key present on mesh_ob from the face control properties."""
    keys = mesh_ob.data.shape_keys
    if keys is None:
        return 0
    n = 0
    for name in facedefs.MORPHS:
        kb = keys.key_blocks.get(name)
        if kb is None:
            continue
        expr, variables = face_info['control_expr'](name)
        _drv(kb, 'value', None, expr, variables, rig)
        n += 1
    return n


def reset_pose(rig):
    """Rest pose: clear all transforms and restore property defaults."""
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
        for k in pb.keys():
            if k.startswith('_'):
                continue
            try:
                ui = pb.id_properties_ui(k).as_dict()
                pb[k] = ui.get('default', 0.0)
            except Exception:
                pass
    bpy.context.view_layer.update()

"""Operative animator control rig ('Operative_Control') driving the exportable deformation skeleton ('Operative_Skeleton').

Design rules (documented in docs/rig_usage.md):
  * Every FK control has exactly the rest frame of the deform bone it drives, so world-space copy constraints transfer pose 1:1.
  * World-aligned controls (root, pelvis, hand/foot IK, poles, look target, props) are identity-oriented; a child 'def' bone with the
    deform bone's frame carries their motion.
  * The deform skeleton follows the control rig with MR_FOLLOW copy-transform constraints; twist and half-angle helper bones are
    driven by LOCAL copy-rotation constraints on the skeleton itself (MR_TWIST / MR_HALF).
  * IK/FK blend per limb via the 'ik_fk' property (0 = FK, 1 = IK) on ctl_hand_ik_* / ctl_foot_ik_*.
"""
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix, Euler
import skeleton_def as S

CTL_NAME = 'Operative_Control'
SK_NAME = 'Operative_Skeleton'
DEG = math.pi / 180.0
SIDES = (('l', 1.0), ('r', -1.0))


def V3(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def m3(p, sy):
    return (p[0], sy * p[1], p[2])


class RigBuilder:
    def __init__(self, skel):
        self.skel = skel
        self.spec = {}        # name -> dict(head, tail, zaxis, parent, coll, shape, scale, deform)
        self.order = []
        self.colls = {}

    # ------------------------------------------------------------ spec helpers
    def bone(self, name, head, tail, z_axis, parent=None, coll='Mechanism', shape=None, scale=1.0, color=None, lock=None):
        assert name not in self.spec, name
        self.spec[name] = dict(head=V3(head), tail=V3(tail), z=V3(z_axis), parent=parent, coll=coll, shape=shape, scale=scale, color=color, lock=lock or {})
        self.order.append(name)

    def like(self, sname, name=None, parent=None, coll='FK', shape='sphere', scale=1.0, color=None, lock=None):
        """Control bone with exactly the frame of skeleton bone sname."""
        b = S.BONE_BY_NAME[sname]
        self.bone(name or sname, b.head, b.tail, S.bone_frame(b)[2], parent, coll, shape, scale, color, lock)

    def world(self, name, head, parent=None, coll='World', shape='circle', scale=1.0, length=0.10, color=None, lock=None):
        """Identity-oriented (world-aligned) control."""
        h = V3(head)
        self.bone(name, h, h + Vector((0, length, 0)), (0, 0, 1), parent, coll, shape, scale, color, lock)

    # ------------------------------------------------------------ specification of all bones
    def build_spec(self):
        B = S.BONE_BY_NAME
        self.world('ctl_root', (0, 0, 0), None, 'World', 'circle', 4.0, 0.2, 'root')
        self.world('ctl_pelvis', S.PELVIS_H, 'ctl_root', 'Torso', 'box', 2.0, 0.1, 'torso')
        self.like('pelvis', 'def_pelvis', 'ctl_pelvis', 'Mechanism', None)
        prev = 'def_pelvis'
        for n in ('spine_01', 'spine_02', 'spine_03'):
            self.like(n, 'ctl_' + n, prev, 'Torso', 'circle', 1.6, 'torso')
            prev = 'ctl_' + n
        self.like('neck_01', 'ctl_neck_01', 'ctl_spine_03', 'Torso', 'circle', 0.8, 'torso')
        self.like('neck_02', 'ctl_neck_02', 'ctl_neck_01', 'Torso', 'circle', 0.7, 'torso')
        self.like('head', 'ctl_head', 'ctl_neck_02', 'Torso', 'circle', 1.4, 'torso')
        self.like('head', 'def_head', 'ctl_head', 'Mechanism', None)
        self.world('ctl_look_target', (1.0, 0.0, 1.685), 'ctl_root', 'World', 'cross', 1.0, 0.10, 'look')
        # face
        self.like('jaw', 'ctl_jaw', 'def_head', 'Face', 'box', 0.6, 'face')
        for n in ('tongue_01', 'tongue_02', 'tongue_03'):
            self.like(n, 'ctl_' + n, 'ctl_jaw' if n == 'tongue_01' else 'ctl_' + {'tongue_02': 'tongue_01', 'tongue_03': 'tongue_02'}[n], 'Face', 'sphere', 0.4, 'face')
        for s, sy in SIDES:
            self.like(f'eye_{s}', f'ctl_eye_{s}', 'def_head', 'Face', 'circle', 0.5, 'face')
            self.like(f'eye_{s}', f'def_eye_{s}', 'def_head', 'Mechanism', None)
            self.like(f'lid_up_{s}', f'ctl_lid_up_{s}', 'def_head', 'Face', 'box', 0.4, 'face')
            self.like(f'lid_lo_{s}', f'ctl_lid_lo_{s}', 'def_head', 'Face', 'box', 0.4, 'face')
        self.bone('ctl_face', (0.05, 0.0, 1.86), (0.05, 0.0, 1.90), (1, 0, 0), 'def_head', 'Face', 'box', 1.0, 'face')
        # braid, cable
        prev = 'def_head'
        for i in range(1, 6):
            n = f'hair_{i:02d}'
            self.like(n, 'ctl_' + n, prev, 'Secondary', 'sphere', 0.6, 'secondary')
            prev = 'ctl_' + n
        # arms, hands, legs per side
        for s, sy in SIDES:
            self.like(f'clavicle_{s}', f'ctl_clavicle_{s}', 'ctl_spine_03', 'Torso', 'sphere', 1.0, 'torso')
            self.like(f'upperarm_{s}', f'ctl_upperarm_fk_{s}', f'ctl_clavicle_{s}', 'Arm FK', 'circle', 1.1, 'fk')
            self.like(f'lowerarm_{s}', f'ctl_lowerarm_fk_{s}', f'ctl_upperarm_fk_{s}', 'Arm FK', 'circle', 1.0, 'fk')
            self.like(f'hand_{s}', f'ctl_hand_fk_{s}', f'ctl_lowerarm_fk_{s}', 'Arm FK', 'box', 1.0, 'fk')
            self.like(f'upperarm_{s}', f'mch_upperarm_ik_{s}', f'ctl_clavicle_{s}', 'Mechanism', None)
            self.like(f'lowerarm_{s}', f'mch_lowerarm_ik_{s}', f'mch_upperarm_ik_{s}', 'Mechanism', None)
            self.like(f'hand_{s}', f'mch_hand_ik_{s}', f'mch_lowerarm_ik_{s}', 'Mechanism', None)
            self.world(f'ctl_hand_ik_{s}', m3(S.WRIST, sy), 'ctl_root', 'Arm IK', 'box', 1.4, 0.06, 'ik')
            self.like(f'hand_{s}', f'mch_hand_target_{s}', f'ctl_hand_ik_{s}', 'Mechanism', None)
            pole = (S.ELBOW[0] - 0.32, sy * (S.ELBOW[1] + 0.06), S.ELBOW[2] + 0.02)
            self.world(f'ctl_pole_arm_{s}', pole, 'ctl_root', 'Arm IK', 'diamond', 0.8, 0.06, 'ik')
            self.like(f'upperarm_{s}', f'def_upperarm_{s}', f'ctl_clavicle_{s}', 'Mechanism', None)
            self.like(f'lowerarm_{s}', f'def_lowerarm_{s}', f'def_upperarm_{s}', 'Mechanism', None)
            self.like(f'hand_{s}', f'def_hand_{s}', f'def_lowerarm_{s}', 'Mechanism', None)
            # hand pose bone with curl / spread properties
            hp = m3(S.add(S.WRIST, S.mul(S.HAND_DIR, 0.055)), sy)
            hp = (hp[0], hp[1] + sy * 0.09, hp[2])
            self.world(f'ctl_hand_pose_{s}', hp, f'def_hand_{s}', 'Fingers', 'diamond', 0.8, 0.05, 'fk')
            # fingers
            for f in ('index', 'middle', 'ring', 'pinky'):
                self.like(f'{f}_metacarpal_{s}', f'ctl_{f}_metacarpal_{s}', f'def_hand_{s}', 'Fingers', 'sphere', 0.35, 'finger')
                prev = f'ctl_{f}_metacarpal_{s}'
                for i in (1, 2, 3):
                    self.like(f'{f}_{i:02d}_{s}', f'ctl_{f}_{i:02d}_{s}', prev, 'Fingers', 'sphere', 0.35, 'finger')
                    prev = f'ctl_{f}_{i:02d}_{s}'
                prevd = f'ctl_{f}_metacarpal_{s}'
                for i in (1, 2, 3):
                    self.like(f'{f}_{i:02d}_{s}', f'def_{f}_{i:02d}_{s}', prevd, 'Mechanism', None)
                    self.like(f'{f}_{i:02d}_{s}', f'mch_curl_{f}_{i:02d}_{s}', 'ctl_root', 'Mechanism', None)
                    prevd = f'def_{f}_{i:02d}_{s}'
            prev = f'def_hand_{s}'
            prevd = f'def_hand_{s}'
            for i in (1, 2, 3):
                self.like(f'thumb_{i:02d}_{s}', f'ctl_thumb_{i:02d}_{s}', prev, 'Fingers', 'sphere', 0.35, 'finger')
                prev = f'ctl_thumb_{i:02d}_{s}'
            prevd = f'def_hand_{s}'
            for i in (1, 2, 3):
                self.like(f'thumb_{i:02d}_{s}', f'def_thumb_{i:02d}_{s}', prevd, 'Mechanism', None)
                self.like(f'thumb_{i:02d}_{s}', f'mch_curl_thumb_{i:02d}_{s}', 'ctl_root', 'Mechanism', None)
                prevd = f'def_thumb_{i:02d}_{s}'
            # legs
            self.like(f'thigh_{s}', f'ctl_thigh_fk_{s}', 'def_pelvis', 'Leg FK', 'circle', 1.4, 'fk')
            self.like(f'calf_{s}', f'ctl_calf_fk_{s}', f'ctl_thigh_fk_{s}', 'Leg FK', 'circle', 1.2, 'fk')
            self.like(f'foot_{s}', f'ctl_foot_fk_{s}', f'ctl_calf_fk_{s}', 'Leg FK', 'box', 1.0, 'fk')
            self.like(f'ball_{s}', f'ctl_ball_fk_{s}', f'ctl_foot_fk_{s}', 'Leg FK', 'box', 0.8, 'fk')
            self.like(f'thigh_{s}', f'mch_thigh_ik_{s}', 'def_pelvis', 'Mechanism', None)
            self.like(f'calf_{s}', f'mch_calf_ik_{s}', f'mch_thigh_ik_{s}', 'Mechanism', None)
            self.like(f'foot_{s}', f'mch_foot_ik_{s}', f'mch_calf_ik_{s}', 'Mechanism', None)
            ank = m3(S.ANKLE, sy)
            ball = m3(S.BALL, sy)
            self.world(f'ctl_foot_ik_{s}', (ank[0], ank[1], 0.0), 'ctl_root', 'Leg IK', 'foot', 1.0, 0.10, 'ik')
            heel = (ank[0] - 0.078, ank[1], 0.0)
            toe = (0.215, ank[1], 0.0)
            self.world(f'mch_roll_heel_{s}', heel, f'ctl_foot_ik_{s}', 'Mechanism', None, 1.0, 0.04)
            self.world(f'mch_roll_toe_{s}', toe, f'mch_roll_heel_{s}', 'Mechanism', None, 1.0, 0.04)
            self.world(f'mch_roll_ball_{s}', (ball[0], ball[1], 0.0), f'mch_roll_toe_{s}', 'Mechanism', None, 1.0, 0.04)
            self.like(f'foot_{s}', f'mch_ankle_{s}', f'mch_roll_ball_{s}', 'Mechanism', None)
            self.like(f'ball_{s}', f'mch_ball_{s}', f'mch_ankle_{s}', 'Mechanism', None)
            self.like(f'ball_{s}', f'mch_toe_flat_{s}', f'def_foot_{s}', 'Mechanism', None)
            kn = m3(S.KNEE, sy)
            self.world(f'ctl_pole_leg_{s}', (kn[0] + 0.36, kn[1], kn[2]), 'ctl_root', 'Leg IK', 'diamond', 0.8, 0.06, 'ik')
            self.like(f'thigh_{s}', f'def_thigh_{s}', 'def_pelvis', 'Mechanism', None)
            self.like(f'calf_{s}', f'def_calf_{s}', f'def_thigh_{s}', 'Mechanism', None)
            self.like(f'foot_{s}', f'def_foot_{s}', f'def_calf_{s}', 'Mechanism', None)
            self.like(f'ball_{s}', f'def_ball_{s}', f'def_foot_{s}', 'Mechanism', None)
        # cyber forearm cable + blade + props
        prev = 'def_lowerarm_l'
        for i in range(1, 6):
            n = f'cable_{i:02d}'
            self.like(n, 'ctl_' + n, prev, 'Secondary', 'sphere', 0.6, 'secondary')
            prev = 'ctl_' + n
        self.like('blade', 'ctl_blade', 'def_lowerarm_l', 'Props', 'arrow', 1.0, 'prop')
        self.like('prop_cell', 'ctl_cell', 'ctl_root', 'Props', 'box', 1.2, 'prop')
        self.like('prop_beacon', 'ctl_beacon', 'ctl_root', 'Props', 'box', 1.4, 'prop')

    # ------------------------------------------------------------ armature creation
    def create(self):
        data = bpy.data.armatures.new(CTL_NAME)
        ob = bpy.data.objects.new(CTL_NAME, data)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        eb = data.edit_bones
        for n in self.order:
            sp = self.spec[n]
            e = eb.new(n)
            e.head, e.tail = sp['head'], sp['tail']
            e.use_deform = False
        for n in self.order:
            sp = self.spec[n]
            e = eb[n]
            if sp['parent']:
                e.parent = eb[sp['parent']]
            e.align_roll(sp['z'])
        bpy.ops.object.mode_set(mode='OBJECT')
        self.ob = ob
        for n in self.order:
            sp = self.spec[n]
            cname = sp['coll']
            if cname not in self.colls:
                self.colls[cname] = data.collections.new(cname)
            self.colls[cname].assign(data.bones[n])
        for cname in ('Mechanism',):
            if cname in self.colls:
                self.colls[cname].is_visible = False
        data.display_type = 'OCTAHEDRAL'
        ob.show_in_front = True
        for n in self.order:
            pb = ob.pose.bones[n]
            pb.rotation_mode = 'XYZ'
        return ob


# ----------------------------------------------------------------------------- custom shapes

def make_shapes():
    coll = bpy.data.collections.get('MR_Shapes')
    if coll is None:
        coll = bpy.data.collections.new('MR_Shapes')
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = True
    coll.hide_render = True
    shapes = {}

    def mk(name, verts, edges):
        me = bpy.data.meshes.new('WGT_' + name)
        me.from_pydata(verts, edges, [])
        ob = bpy.data.objects.new('WGT_' + name, me)
        coll.objects.link(ob)
        shapes[name] = ob
    n = 32
    circ = [(math.cos(2 * math.pi * i / n) * 0.5, 0.0, math.sin(2 * math.pi * i / n) * 0.5) for i in range(n)]
    mk('circle', circ, [(i, (i + 1) % n) for i in range(n)])
    b = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    mk('box', b, [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)])
    sph = []
    ed = []
    for k in range(3):
        for i in range(24):
            a = 2 * math.pi * i / 24
            c, s = math.cos(a) * 0.5, math.sin(a) * 0.5
            sph.append([(c, s, 0), (c, 0, s), (0, c, s)][k])
            ed.append((k * 24 + i, k * 24 + (i + 1) % 24))
    mk('sphere', sph, ed)
    mk('cross', [(-0.5, 0, 0), (0.5, 0, 0), (0, -0.5, 0), (0, 0.5, 0), (0, 0, -0.5), (0, 0, 0.5)], [(0, 1), (2, 3), (4, 5)])
    mk('diamond', [(0.5, 0, 0), (-0.5, 0, 0), (0, 0.5, 0), (0, -0.5, 0), (0, 0, 0.5), (0, 0, -0.5)],
       [(0, 2), (2, 1), (1, 3), (3, 0), (0, 4), (4, 1), (1, 5), (5, 0), (2, 4), (4, 3), (3, 5), (5, 2)])
    mk('arrow', [(0, 0, 0), (0, 1.0, 0), (-0.2, 0.75, 0), (0.2, 0.75, 0), (0, 0.75, -0.2), (0, 0.75, 0.2)], [(0, 1), (1, 2), (1, 3), (1, 4), (1, 5)])
    mk('foot', [(-0.25, -0.5, 0), (0.6, -0.5, 0), (0.6, 0.5, 0), (-0.25, 0.5, 0), (-0.25, -0.5, 0.0)], [(0, 1), (1, 2), (2, 3), (3, 0)])
    return shapes


PALETTE = {'root': 'THEME01', 'torso': 'THEME04', 'fk': 'THEME03', 'ik': 'THEME02', 'look': 'THEME09', 'face': 'THEME08', 'secondary': 'THEME06',
           'prop': 'THEME10', 'finger': 'THEME05'}


def apply_shapes(rb, shapes):
    ob = rb.ob
    for n in rb.order:
        sp = rb.spec[n]
        pb = ob.pose.bones[n]
        if sp['shape']:
            pb.custom_shape = shapes[sp['shape']]
            pb.custom_shape_scale_xyz = (sp['scale'], sp['scale'], sp['scale'])
            if sp['shape'] in ('circle', 'foot', 'arrow'):
                pass
            pb.use_custom_shape_bone_size = False if sp['shape'] not in ('arrow',) else True
        if sp['color'] in PALETTE:
            pb.bone.color.palette = PALETTE[sp['color']]


# ----------------------------------------------------------------------------- constraints / drivers helpers

def add_con(pb, ctype, name, target=None, subtarget='', **kw):
    c = pb.constraints.new(ctype)
    c.name = name
    if target is not None:
        c.target = target
        c.subtarget = subtarget
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def add_driver(idref, path, index, expr, variables):
    """variables: dict name -> (id_object, data_path)."""
    fc = idref.driver_add(path, index) if index is not None else idref.driver_add(path)
    d = fc.driver
    d.type = 'SCRIPTED'
    d.expression = expr
    for vn, (target_id, dpath) in variables.items():
        v = d.variables.new()
        v.name = vn
        v.type = 'SINGLE_PROP'
        v.targets[0].id = target_id
        v.targets[0].data_path = dpath
    return fc


def prop(pb, name, value, lo=0.0, hi=1.0, desc=''):
    pb[name] = value
    ui = pb.id_properties_ui(name)
    ui.update(min=lo, max=hi, soft_min=lo, soft_max=hi, description=desc, default=value)


# ----------------------------------------------------------------------------- rig logic

def setup_logic(rb, skel):
    ctl = rb.ob
    P = ctl.pose.bones
    dp = lambda pbname, key: f'pose.bones["{pbname}"]["{key}"]'
    for s, sy in SIDES:
        # IK chains
        ik = add_con(P[f'mch_lowerarm_ik_{s}'], 'IK', 'MR_IK', ctl, f'mch_hand_target_{s}', pole_target=ctl, pole_subtarget=f'ctl_pole_arm_{s}',
                     chain_count=2, use_stretch=False, iterations=60)
        add_con(P[f'mch_hand_ik_{s}'], 'COPY_ROTATION', 'MR_IK_ORIENT', ctl, f'mch_hand_target_{s}', target_space='WORLD', owner_space='WORLD')
        ik2 = add_con(P[f'mch_calf_ik_{s}'], 'IK', 'MR_IK', ctl, f'mch_ankle_{s}', pole_target=ctl, pole_subtarget=f'ctl_pole_leg_{s}',
                      chain_count=2, use_stretch=False, iterations=60)
        add_con(P[f'mch_foot_ik_{s}'], 'COPY_ROTATION', 'MR_IK_ORIENT', ctl, f'mch_ankle_{s}', target_space='WORLD', owner_space='WORLD')
        # props holding ik_fk
        prop(P[f'ctl_hand_ik_{s}'], 'ik_fk', 0.0, 0.0, 1.0, '0 = FK, 1 = IK')
        prop(P[f'ctl_foot_ik_{s}'], 'ik_fk', 1.0, 0.0, 1.0, '0 = FK, 1 = IK')
        prop(P[f'ctl_foot_ik_{s}'], 'roll', 0.0, -45.0, 100.0, 'Foot roll in degrees: negative pivots on the heel, positive on the ball then the toe')
        prop(P[f'ctl_foot_ik_{s}'], 'roll_break', 40.0, 5.0, 90.0, 'Roll angle where the pivot moves from ball to toe tip')
        # FK/IK blend on def bones
        for seg, fk_src, ik_src in (('upperarm', f'ctl_upperarm_fk_{s}', f'mch_upperarm_ik_{s}'), ('lowerarm', f'ctl_lowerarm_fk_{s}', f'mch_lowerarm_ik_{s}'),
                                    ('hand', f'ctl_hand_fk_{s}', f'mch_hand_ik_{s}')):
            pb = P[f'def_{seg}_{s}']
            add_con(pb, 'COPY_TRANSFORMS', 'MR_FK', ctl, fk_src)
            c = add_con(pb, 'COPY_TRANSFORMS', 'MR_IK', ctl, ik_src)
            add_driver(c, 'influence', None, 'ik', {'ik': (ctl, dp(f'ctl_hand_ik_{s}', 'ik_fk'))})
        for seg, fk_src, ik_src in (('thigh', f'ctl_thigh_fk_{s}', f'mch_thigh_ik_{s}'), ('calf', f'ctl_calf_fk_{s}', f'mch_calf_ik_{s}'),
                                    ('foot', f'ctl_foot_fk_{s}', f'mch_foot_ik_{s}')):
            pb = P[f'def_{seg}_{s}']
            add_con(pb, 'COPY_TRANSFORMS', 'MR_FK', ctl, fk_src)
            c = add_con(pb, 'COPY_TRANSFORMS', 'MR_IK', ctl, ik_src)
            add_driver(c, 'influence', None, 'ik', {'ik': (ctl, dp(f'ctl_foot_ik_{s}', 'ik_fk'))})
        # ball: FK rotation, plus automatic toe-flat compensation while rolling (IK only)
        pbb = P[f'def_ball_{s}']
        add_con(pbb, 'COPY_ROTATION', 'MR_FK', ctl, f'ctl_ball_fk_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE')
        c = add_con(pbb, 'COPY_ROTATION', 'MR_TOEFLAT', ctl, f'mch_toe_flat_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='AFTER')
        add_driver(c, 'influence', None, 'ik', {'ik': (ctl, dp(f'ctl_foot_ik_{s}', 'ik_fk'))})
        # reverse-foot roll drivers (rotation about the world-left axis = local Y of the identity-oriented pivot bones)
        r = dp(f'ctl_foot_ik_{s}', 'roll')
        R1 = dp(f'ctl_foot_ik_{s}', 'roll_break')
        vars_ = {'r': (ctl, r), 'b': (ctl, R1)}
        k = DEG
        add_driver(P[f'mch_roll_heel_{s}'], 'rotation_euler', 1, f'(r-abs(r))*0.5*{k}', vars_)
        add_driver(P[f'mch_roll_ball_{s}'], 'rotation_euler', 1, f'((r+abs(r))*0.5+b-abs((r+abs(r))*0.5-b))*0.5*{k}', vars_)
        add_driver(P[f'mch_roll_toe_{s}'], 'rotation_euler', 1, f'((r-b)+abs(r-b))*0.5*{k}', vars_)
        add_driver(P[f'mch_toe_flat_{s}'], 'rotation_euler', 0, f'((r+abs(r))*0.5+b-abs((r+abs(r))*0.5-b))*0.5*{k}', vars_)
        for bn in (f'mch_roll_heel_{s}', f'mch_roll_toe_{s}', f'mch_roll_ball_{s}', f'mch_toe_flat_{s}'):
            P[bn].rotation_mode = 'XYZ'
        # finger curl / spread
        hp = P[f'ctl_hand_pose_{s}']
        for key, lo, hi in (('curl', -1.0, 1.5), ('spread', -1.0, 1.0), ('thumb_curl', -1.0, 1.5), ('index_curl', -1.0, 1.5), ('middle_curl', -1.0, 1.5),
                            ('ring_curl', -1.0, 1.5), ('pinky_curl', -1.0, 1.5)):
            prop(hp, key, 0.0, lo, hi, 'Finger pose helper (added on top of the FK finger controls)')
        gains = {1: 62.0, 2: 82.0, 3: 55.0}
        spreads = {'index': 10.0, 'middle': 0.0, 'ring': -9.0, 'pinky': -16.0}
        for f in ('index', 'middle', 'ring', 'pinky'):
            for i in (1, 2, 3):
                mb = P[f'mch_curl_{f}_{i:02d}_{s}']
                mb.rotation_mode = 'XYZ'
                v = {'c': (ctl, dp(f'ctl_hand_pose_{s}', 'curl')), 'fc': (ctl, dp(f'ctl_hand_pose_{s}', f'{f}_curl')), 'sp': (ctl, dp(f'ctl_hand_pose_{s}', 'spread'))}
                add_driver(mb, 'rotation_euler', 0, f'(c+fc)*{gains[i] * DEG}', v)
                if i == 1:
                    # the right-hand bones are mirrored, so rotations about Z need the opposite sign to spread (not close) the fingers
                    add_driver(mb, 'rotation_euler', 2, f'sp*{spreads[f] * DEG * (1.0 if s == "l" else -1.0)}', v)
                d = P[f'def_{f}_{i:02d}_{s}']
                add_con(d, 'COPY_ROTATION', 'MR_FK', ctl, f'ctl_{f}_{i:02d}_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE')
                add_con(d, 'COPY_ROTATION', 'MR_CURL', ctl, f'mch_curl_{f}_{i:02d}_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='AFTER')
        # thumb: flexion about X on all three joints; the first bone also swings across the palm (Z) and rolls (Y) so a fist closes
        # around the thumb the way a hand does (gains found by minimising the distance between the thumb tip and the middle phalanges)
        tg = {1: 111.0, 2: 91.0, 3: 80.0}
        sg = 1.0 if s == 'l' else -1.0          # mirrored bones: Y and Z rotations change sign on the right hand
        for i in (1, 2, 3):
            mb = P[f'mch_curl_thumb_{i:02d}_{s}']
            mb.rotation_mode = 'XYZ'
            v = {'c': (ctl, dp(f'ctl_hand_pose_{s}', 'curl')), 'fc': (ctl, dp(f'ctl_hand_pose_{s}', 'thumb_curl')), 'sp': (ctl, dp(f'ctl_hand_pose_{s}', 'spread'))}
            add_driver(mb, 'rotation_euler', 0, f'min(max(c*0.6+fc,-0.4),1.2)*{tg[i] * DEG}', v)
            if i == 1:
                add_driver(mb, 'rotation_euler', 1, f'min(max(c*0.6+fc,0),0.9)*{-95.0 * DEG * sg}', v)
                add_driver(mb, 'rotation_euler', 2, f'sp*{-14.0 * DEG * sg}+min(max(c*0.6+fc,0),0.9)*{-117.0 * DEG * sg}', v)
            d = P[f'def_thumb_{i:02d}_{s}']
            add_con(d, 'COPY_ROTATION', 'MR_FK', ctl, f'ctl_thumb_{i:02d}_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE')
            add_con(d, 'COPY_ROTATION', 'MR_CURL', ctl, f'mch_curl_thumb_{i:02d}_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='AFTER')
    # head + eyes: look-at
    lt = P['ctl_look_target']
    prop(lt, 'look_eyes', 0.0, 0.0, 1.0, 'How strongly the eyes track the look target')
    prop(lt, 'look_head', 0.0, 0.0, 1.0, 'How strongly the head aims at the look target')
    add_con(P['def_head'], 'COPY_TRANSFORMS', 'MR_FK', ctl, 'ctl_head')
    c = add_con(P['def_head'], 'DAMPED_TRACK', 'MR_LOOK', ctl, 'ctl_look_target', track_axis='TRACK_Z')
    add_driver(c, 'influence', None, 'h', {'h': (ctl, dp('ctl_look_target', 'look_head'))})
    for s, sy in SIDES:
        add_con(P[f'def_eye_{s}'], 'COPY_TRANSFORMS', 'MR_FK', ctl, f'ctl_eye_{s}')
        c = add_con(P[f'def_eye_{s}'], 'DAMPED_TRACK', 'MR_LOOK', ctl, 'ctl_look_target', track_axis='TRACK_Y')
        add_driver(c, 'influence', None, 'e', {'e': (ctl, dp('ctl_look_target', 'look_eyes'))})
    # global rig properties
    root = P['ctl_root']
    prop(root, 'secondary_influence', 1.0, 0.0, 1.0, 'Scales the baked secondary-motion simulation')
    prop(root, 'global_scale_note', 0.0, 0.0, 1.0, 'Scale ctl_root uniformly to scale the whole rig')


FOLLOW = {}


def follow_map():
    m = {'root': 'ctl_root', 'pelvis': 'def_pelvis', 'spine_01': 'ctl_spine_01', 'spine_02': 'ctl_spine_02', 'spine_03': 'ctl_spine_03',
         'neck_01': 'ctl_neck_01', 'neck_02': 'ctl_neck_02', 'head': 'def_head', 'jaw': 'ctl_jaw', 'blade': 'ctl_blade',
         'prop_cell': 'ctl_cell', 'prop_beacon': 'ctl_beacon'}
    for i in (1, 2, 3):
        m[f'tongue_{i:02d}'] = f'ctl_tongue_{i:02d}'
    for i in range(1, 6):
        m[f'hair_{i:02d}'] = f'ctl_hair_{i:02d}'
        m[f'cable_{i:02d}'] = f'ctl_cable_{i:02d}'
    for s, sy in SIDES:
        m[f'clavicle_{s}'] = f'ctl_clavicle_{s}'
        for seg in ('upperarm', 'lowerarm', 'hand'):
            m[f'{seg}_{s}'] = f'def_{seg}_{s}'
        for seg in ('thigh', 'calf', 'foot', 'ball'):
            m[f'{seg}_{s}'] = f'def_{seg}_{s}'
        m[f'eye_{s}'] = f'def_eye_{s}'
        m[f'lid_up_{s}'] = f'ctl_lid_up_{s}'
        m[f'lid_lo_{s}'] = f'ctl_lid_lo_{s}'
        for f in ('index', 'middle', 'ring', 'pinky'):
            m[f'{f}_metacarpal_{s}'] = f'ctl_{f}_metacarpal_{s}'
            for i in (1, 2, 3):
                m[f'{f}_{i:02d}_{s}'] = f'def_{f}_{i:02d}_{s}'
        for i in (1, 2, 3):
            m[f'thumb_{i:02d}_{s}'] = f'def_thumb_{i:02d}_{s}'
    return m


def link_skeleton(ctl, skel):
    fm = follow_map()
    for b in S.BONES:
        if b.name in fm:
            pb = skel.pose.bones[b.name]
            pb.rotation_mode = 'XYZ'
            add_con(pb, 'COPY_TRANSFORMS', 'MR_FOLLOW', ctl, fm[b.name])
    # twist and half-angle helpers on the skeleton itself
    P = skel.pose.bones
    for s, sy in SIDES:
        for seg, driver_child, fr in (('upperarm', None, (0.66, 0.33)), ('thigh', None, (0.66, 0.33))):
            # counter-rotate the roll of the parent joint so twist bones near the joint roll less (0.33 / 0.66 of the roll survive)
            for i, f in enumerate(fr):
                pb = P[f'{seg}_twist_{i + 1:02d}_{s}']
                add_con(pb, 'COPY_ROTATION', 'MR_TWIST', skel, f'{seg}_{s}', use_x=False, use_z=False, use_y=True, invert_y=True,
                        target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE', euler_order='YXZ').influence = f
        for seg, src, fr in (('lowerarm', 'hand', (0.33, 0.66)), ('calf', 'foot', (0.33, 0.66))):
            for i, f in enumerate(fr):
                pb = P[f'{seg}_twist_{i + 1:02d}_{s}']
                c = add_con(pb, 'COPY_ROTATION', 'MR_TWIST', skel, f'{src}_{s}', use_x=False, use_z=False, use_y=True,
                            target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE', euler_order='YXZ')
                c.influence = f
        for half, src in (('shoulder_half', 'upperarm'), ('elbow_half', 'lowerarm'), ('wrist_half', 'hand'), ('hip_half', 'thigh'), ('knee_half', 'calf')):
            pb = P[f'{half}_{s}']
            c = add_con(pb, 'COPY_ROTATION', 'MR_HALF', skel, f'{src}_{s}', target_space='LOCAL', owner_space='LOCAL', mix_mode='REPLACE')
            c.influence = 0.5
    # eyelids follow the eye pitch a little (added after the control-follow constraint)
    for s, sy in SIDES:
        for lid, f in (('lid_up', 0.45), ('lid_lo', 0.25)):
            pb = P[f'{lid}_{s}']
            c = add_con(pb, 'COPY_ROTATION', 'MR_LIDFOLLOW', skel, f'eye_{s}', use_y=False, use_z=False, target_space='LOCAL', owner_space='LOCAL', mix_mode='AFTER')
            c.influence = f


def calibrate_poles(rb, skel):
    """Pick pole angles so the IK chains reproduce the rest pose."""
    ctl = rb.ob
    for s, sy in SIDES:
        for kind, mch, con_owner, tail_bone in (('arm', f'mch_lowerarm_ik_{s}', f'mch_lowerarm_ik_{s}', f'mch_upperarm_ik_{s}'),
                                                ('leg', f'mch_calf_ik_{s}', f'mch_calf_ik_{s}', f'mch_thigh_ik_{s}')):
            pb = ctl.pose.bones[con_owner]
            con = pb.constraints['MR_IK']
            rest_mid = ctl.data.bones[mch].head_local.copy()
            best = None
            for step in (30, 5, 1):
                cands = [best[1] + d for d in range(-step * 3, step * 3 + 1, step)] if best else list(range(-180, 181, step))
                for ang in cands:
                    con.pole_angle = ang * DEG
                    bpy.context.view_layer.update()
                    dg = bpy.context.evaluated_depsgraph_get()
                    ev = ctl.evaluated_get(dg)
                    head = (ev.matrix_world @ ev.pose.bones[mch].head)
                    err = (head - rest_mid).length
                    if best is None or err < best[0]:
                        best = (err, ang)
            con.pole_angle = best[1] * DEG
            rb.pole_error = getattr(rb, 'pole_error', {})
            rb.pole_error[f'{kind}_{s}'] = best[0]


def build_rig(skel):
    rb = RigBuilder(skel)
    rb.build_spec()
    ctl = rb.create()
    shapes = make_shapes()
    apply_shapes(rb, shapes)
    setup_logic(rb, skel)
    link_skeleton(ctl, skel)
    bpy.context.view_layer.update()
    calibrate_poles(rb, skel)
    return rb

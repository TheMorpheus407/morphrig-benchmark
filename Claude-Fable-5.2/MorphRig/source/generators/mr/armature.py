"""Deformation skeleton construction and the reference implementation of the procedural
twist / half-rotation helper bones (the same rules are re-evaluated at runtime in Unreal)."""
import math
import bpy
import numpy as np
from mathutils import Matrix, Vector, Quaternion
from . import skel

SKEL_NAME = 'SKEL_Operative'

# helper rules: bone -> (kind, driver bone, amount)
#   'half'      : local rotation = slerp(identity, local rotation of driver, amount)  (driver shares the same rest frame)
#   'untwist'   : child of driver; local rotation = inverse(twist of driver's local rotation about its Y axis) * amount
#   'twist'     : child of the driver's parent; local rotation = twist of driver's local rotation about Y * amount
HELPER_RULES = {}
for s in ('l', 'r'):
    HELPER_RULES['shoulder_helper_' + s] = ('half', 'upperarm_' + s, 0.5)
    HELPER_RULES['elbow_helper_' + s] = ('half', 'lowerarm_' + s, 0.5)
    HELPER_RULES['hip_helper_' + s] = ('half', 'thigh_' + s, 0.5)
    HELPER_RULES['knee_helper_' + s] = ('half', 'calf_' + s, 0.5)
    HELPER_RULES['upperarm_twist_' + s] = ('untwist', 'upperarm_' + s, 1.0)
    HELPER_RULES['thigh_twist_' + s] = ('untwist', 'thigh_' + s, 1.0)
    HELPER_RULES['lowerarm_twist_' + s] = ('twist', 'hand_' + s, 1.0)


def build_skeleton(name=SKEL_NAME, bones=None, collection=None):
    bones = bones or skel.BONES
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    (collection or bpy.context.scene.collection).objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for b in bones:
        eb = arm.edit_bones.new(b['name'])
        eb.head = Vector(b['head'])
        eb.tail = Vector(b['tail'])
        eb.align_roll(Vector(b['zhint']))
        eb.use_deform = True
        eb.use_connect = False
    for b in bones:
        if b['parent']:
            arm.edit_bones[b['name']].parent = arm.edit_bones[b['parent']]
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    arm.display_type = 'OCTAHEDRAL'
    ob.show_in_front = True
    return ob


def bind(mesh_ob, arm_ob):
    mesh_ob.parent = arm_ob
    mod = mesh_ob.modifiers.get('Armature') or mesh_ob.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm_ob
    mod.use_deform_preserve_volume = False
    return mod


def swing_twist(q, axis=Vector((0, 1, 0))):
    """Decompose q = swing * twist with twist about axis (shortest arc swing)."""
    v = Vector((q.x, q.y, q.z))
    p = axis * v.dot(axis)
    tw = Quaternion((q.w, p.x, p.y, p.z))
    if tw.magnitude < 1e-9:
        tw = Quaternion((1, 0, 0, 0))
    else:
        tw.normalize()
    sw = q @ tw.inverted()
    return sw, tw


def apply_helpers(arm_ob):
    """Evaluate HELPER_RULES on the current pose of a plain deformation skeleton (no constraints)."""
    pbs = arm_ob.pose.bones
    for name, (kind, drv, amount) in HELPER_RULES.items():
        if name not in pbs or drv not in pbs:
            continue
        pb, d = pbs[name], pbs[drv]
        q = d.rotation_quaternion.copy() if d.rotation_mode == 'QUATERNION' else d.matrix_basis.to_quaternion()
        ident = Quaternion((1, 0, 0, 0))
        if kind == 'half':
            r = ident.slerp(q, amount)
        elif kind == 'untwist':
            sw, tw = swing_twist(q)
            r = ident.slerp(tw.inverted(), amount)
        else:
            sw, tw = swing_twist(q)
            r = ident.slerp(tw, amount)
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = r
    bpy.context.view_layer.update()


def reset_pose(arm_ob):
    for pb in arm_ob.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()

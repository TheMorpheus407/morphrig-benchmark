"""FBX export helpers.

Blender source data stays in metres (unit scale 1.0). Unreal expects centimetre joints with unit scale
factors of 1; Blender's FBX writer can only express metres through a 100x node scale on the armature
object, which Unreal would bake into the root joint. `to_centimetres()` therefore converts an in-memory
copy of the export data (rest joints, mesh/shape-key coordinates and translation curves x100, scene unit
scale 0.01) so that the written FBX carries unscaled joints in centimetres. The file on disk is never
saved in that state. The armature object is named "Armature" while exporting because Unreal's FBX
translator drops a Blender null node of exactly that name instead of turning it into an extra root joint.
"""
import bpy
from mathutils import Matrix

EXPORT_ARMATURE_NODE_NAME = 'Armature'


def iter_fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    yield fc


def to_centimetres(arm_ob, mesh_obs, actions, factor=100.0):
    sc = bpy.context.scene
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = arm_ob
    arm_ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in arm_ob.data.edit_bones:
        eb.head = eb.head * factor
        eb.tail = eb.tail * factor
    bpy.ops.object.mode_set(mode='OBJECT')
    done = set()
    for ob in mesh_obs:
        if ob.data.name in done:
            continue
        done.add(ob.data.name)
        ob.data.transform(Matrix.Scale(factor, 4), shape_keys=True)
        ob.data.update()
    for act in actions:
        for fc in iter_fcurves(act):
            if fc.data_path.endswith('location'):
                for kp in fc.keyframe_points:
                    kp.co[1] *= factor
                    kp.handle_left[1] *= factor
                    kp.handle_right[1] *= factor
                fc.update()
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0 / factor


def export_fbx(path, arm_ob, objs, anim=False):
    old_name = arm_ob.name
    arm_ob.name = EXPORT_ARMATURE_NODE_NAME
    try:
        bpy.ops.object.select_all(action='DESELECT')
        for o in [arm_ob] + list(objs):
            o.hide_set(False)
            o.hide_viewport = False
            o.select_set(True)
        bpy.context.view_layer.objects.active = arm_ob
        bpy.ops.export_scene.fbx(
            filepath=path, use_selection=True, global_scale=1.0, apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_NONE', object_types={'ARMATURE', 'MESH'}, use_mesh_modifiers=False,
            mesh_smooth_type='FACE', use_tspace=False, add_leaf_bones=False, primary_bone_axis='Y',
            secondary_bone_axis='X', use_armature_deform_only=False, armature_nodetype='NULL', bake_anim=anim,
            bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0,
            axis_forward='-Z', axis_up='Y')
    finally:
        arm_ob.name = old_name

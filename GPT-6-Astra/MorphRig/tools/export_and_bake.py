"""Reproducible Blender export. Run from any working directory:
blender -b MorphRig/source/Operative.blend -P MorphRig/tools/export_and_bake.py
Pass -- --mesh-only or --clips-only if appropriate. Source file is never overwritten.
"""
import bpy, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def prepare_centimeter_export(rig,meshes):
    """Explicit centimetre data avoids Unreal stripping the FBX armature unit scale."""
    from mathutils import Matrix
    scale=Matrix.Scale(100.,4)
    rig.data.transform(scale)
    for mesh in meshes:
        if mesh:mesh.data.transform(scale,shape_keys=True)
    for action in bpy.data.actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        if curve.data_path.startswith('pose.bones[') and curve.data_path.endswith('.location'):
                            for key in curve.keyframe_points:
                                key.co.y*=100.;key.handle_left.y*=100.;key.handle_right.y*=100.
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=.01
    bpy.context.view_layer.update()

def export():
    rig=bpy.data.objects.get('Operative_Rig')
    if not rig:raise RuntimeError('Open source/Operative.blend before export')
    rig.name='Armature'  # Unreal's Blender importer strips this object wrapper, preserving root bone.
    manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations']
    export_root=ROOT/'export';(export_root/'animations').mkdir(parents=True,exist_ok=True)
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    # Every clip receives evaluated FK curves; armature object's transform remains identity.
    for pb in rig.pose.bones:
        pb.rotation_mode='QUATERNION'
        for c in pb.constraints:c.mute=True
    for k in ('arm_ik.L','arm_ik.R','leg_ik.L','leg_ik.R'):
        if k in rig:rig[k]=0.
    for track in rig.animation_data.nla_tracks:track.mute=True
    for obj in bpy.data.objects:
        obj.select_set(False)
        if obj.type=='MESH' and obj.data.shape_keys and obj.data.shape_keys.animation_data:
            for track in obj.data.shape_keys.animation_data.nla_tracks:track.mute=True
    bpy.context.view_layer.objects.active=rig
    meshes=[bpy.data.objects.get('Operative_LOD'+str(i)) for i in range(3)]
    prepare_centimeter_export(rig,meshes)
    common=dict(use_selection=True,object_types={'ARMATURE','MESH'},axis_forward='-Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_space_transform=True,bake_space_transform=False,add_leaf_bones=False,use_armature_deform_only=True,armature_nodetype='NULL',mesh_smooth_type='FACE',use_mesh_modifiers=False,use_custom_props=True,path_mode='RELATIVE',embed_textures=False)
    def select(mesh):
        for obj in bpy.context.selected_objects:obj.select_set(False)
        rig.hide_set(False);rig.hide_viewport=False;rig.select_set(True)
        if mesh:mesh.hide_set(False);mesh.hide_viewport=False;mesh.select_set(True)
    def clear():
        rig.animation_data.action=None
        for pb in rig.pose.bones:
            pb.location=(0,0,0);pb.rotation_mode='QUATERNION';pb.rotation_quaternion=(1,0,0,0);pb.scale=(1,1,1)
        for mesh in meshes:
            if mesh and mesh.data.shape_keys:
                keys=mesh.data.shape_keys
                if keys.animation_data:keys.animation_data.action=None
                for key in keys.key_blocks:key.value=0
    if '--clips-only' not in args:
        clear();bpy.context.scene.frame_set(1)
        for i,mesh in enumerate(meshes):
            if not mesh:continue
            select(mesh);path=export_root/('Operative.fbx' if i==0 else 'Operative_LOD'+str(i)+'.fbx')
            bpy.ops.export_scene.fbx(filepath=str(path),bake_anim=False,**common)
            print('EXPORTED MESH',path,flush=True)
    if '--mesh-only' not in args:
        if '--clip' in args:manifest=[m for m in manifest if m['id']==args[args.index('--clip')+1]]
        if '--ids' in args:
            selected=set(args[args.index('--ids')+1].split(','));manifest=[m for m in manifest if m['id'] in selected]
        for item in manifest:
            id=item['id'];action=bpy.data.actions.get(id)
            if not action:raise RuntimeError('Missing baked action '+id)
            clear();select(meshes[0]);rig.animation_data.action=action
            if hasattr(rig.animation_data,'action_slot') and action.slots:rig.animation_data.action_slot=action.slots[0]
            keys=meshes[0].data.shape_keys if meshes[0] else None
            if keys:
                keys.animation_data_create();face=bpy.data.actions.get('FACE__'+id);keys.animation_data.action=face
                if face and hasattr(keys.animation_data,'action_slot') and face.slots:keys.animation_data.action_slot=face.slots[0]
            bpy.context.scene.frame_start=item['frame_start'];bpy.context.scene.frame_end=item['frame_end'];bpy.context.scene.frame_set(item['frame_start']);bpy.context.view_layer.update()
            # Include LOD0 to export morph animation with skeletal curves in one take.
            bpy.ops.export_scene.fbx(filepath=str(export_root/'animations'/f'{id}.fbx'),bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_use_all_bones=True,bake_anim_force_startend_keying=True,bake_anim_step=1.,bake_anim_simplify_factor=0.,**common)
            print('EXPORTED CLIP',id,flush=True)
    if '--clips-only' not in args:
        # The persistent prop is derived from the same saved authored source.
        # Its static FBX needs the native beacon socket basis and explicit cm.
        import runpy
        runpy.run_path(str(ROOT/'source/generators/export_props.py'),run_name='__main__')
    print('EXPORT COMPLETE',flush=True)
if __name__=='__main__':export()

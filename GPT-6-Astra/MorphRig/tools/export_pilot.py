import sys,bpy,math
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import *
rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];out=root/'export/pilot';out.mkdir(parents=True,exist_ok=True)
rig.name='Armature';rig.animation_data_create()
for pb in rig.pose.bones:
 for c in pb.constraints:c.mute=True
for obj in bpy.context.scene.objects:obj.select_set(False)
rig.select_set(True);mesh.hide_set(False);mesh.select_set(True);bpy.context.view_layer.objects.active=rig
for k in mesh.data.shape_keys.key_blocks:k.value=0
kw=dict(use_selection=True,object_types={'ARMATURE','MESH'},axis_forward='-Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_space_transform=True,bake_space_transform=False,add_leaf_bones=False,use_armature_deform_only=True,armature_nodetype='NULL',mesh_smooth_type='FACE',use_mesh_modifiers=False,use_custom_props=True,path_mode='RELATIVE')
reset(rig);bpy.context.view_layer.update();bpy.ops.export_scene.fbx(filepath=str(out/'Operative.fbx'),bake_anim=False,**kw)
for id in ('idle_combat','dash_f'):
 a=bpy.data.actions.new(id);rig.animation_data.action=a;n=round(DURATIONS[id]*30)
 for i in range(n+1):
  t=i/n;bpy.context.scene.frame_set(i+1);p=motion(id,t,n/30);apply_pose(rig,p,id,t)
  for pb in rig.pose.bones:
   if pb.bone.use_deform:pb.keyframe_insert('location',frame=i+1);pb.keyframe_insert('rotation_quaternion',frame=i+1);pb.keyframe_insert('scale',frame=i+1)
 bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=n+1;bpy.context.scene.render.fps=30
 bpy.ops.export_scene.fbx(filepath=str(out/(id+'.fbx')),bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_use_all_bones=True,bake_anim_step=1.,bake_anim_simplify_factor=0.,**kw)
print('PILOT EXPORTED',flush=True)

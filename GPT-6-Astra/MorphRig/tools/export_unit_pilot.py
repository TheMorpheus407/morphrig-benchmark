import sys,bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'))
from export_and_bake import prepare_centimeter_export
rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];out=root/'export/pilot_cm';out.mkdir(parents=True,exist_ok=True)
rig.name='Armature'
for p in rig.pose.bones:
 p.rotation_mode='QUATERNION'
 for c in p.constraints:c.mute=True
prepare_centimeter_export(rig,[mesh])
for o in bpy.context.scene.objects:o.select_set(False)
rig.select_set(True);mesh.hide_set(False);mesh.select_set(True);bpy.context.view_layer.objects.active=rig
kw=dict(use_selection=True,object_types={'ARMATURE','MESH'},axis_forward='-Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_space_transform=True,bake_space_transform=False,add_leaf_bones=False,use_armature_deform_only=True,armature_nodetype='NULL',mesh_smooth_type='FACE',use_mesh_modifiers=False,use_custom_props=True,path_mode='RELATIVE')
rig.animation_data.action=None
for p in rig.pose.bones:p.location=(0,0,0);p.rotation_quaternion=(1,0,0,0);p.scale=(1,1,1)
mesh.data.shape_keys.animation_data.action=None
for k in mesh.data.shape_keys.key_blocks:k.value=0
bpy.context.view_layer.update();bpy.ops.export_scene.fbx(filepath=str(out/'Operative.fbx'),bake_anim=False,**kw)
manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations']
for id in ('dash_f','prone_back','reload','deploy','run_f','idle_relaxed'):
 m=next(x for x in manifest if x['id']==id);a=bpy.data.actions[id];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=m['frame_end'];bpy.context.scene.frame_set(1)
 bpy.ops.export_scene.fbx(filepath=str(out/(id+'.fbx')),bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_use_all_bones=True,bake_anim_step=1.,bake_anim_simplify_factor=0.,**kw)
print('CENTIMETER PILOT READY',flush=True)

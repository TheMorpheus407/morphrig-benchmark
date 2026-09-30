"""Bake source controls onto the stable deformation skeleton and export FBX.
Usage: blender -b source/Operative.blend -P tools/export_and_bake.py
Optional after --: --clips idle_relaxed,dialogue ; --mesh-only ; --no-mesh
Preserves the complete editable source asset and adds BAKED_* source actions.
"""
import bpy, sys, json, math, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
source=bpy.data.objects['Operative_Rig'];scene=bpy.context.scene
source_unit_scale=scene.unit_settings.scale_length
# Explicit source metres -> export centimetres; FBX unit metadata remains cm.
scene.unit_settings.scale_length=.01
old_export=bpy.data.objects.get('Operative_Export_Skeleton')
if old_export:bpy.data.objects.remove(old_export,do_unlink=True)
manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text()) if (ROOT/'docs/animation_manifest.json').exists() else {'animations':[]}
rows=manifest['animations']
if '--clips' in args:
 names=args[args.index('--clips')+1].split(',');rows=[r for r in rows if r['id'] in names]

def export_armature():
 arm=source.data.copy();ob=bpy.data.objects.new('Armature',arm);bpy.context.collection.objects.link(ob);ob.matrix_world=source.matrix_world.copy()
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.mode_set(mode='EDIT')
 for b in list(arm.edit_bones):
  if not b.use_deform:arm.edit_bones.remove(b)
 for b in arm.edit_bones:b.head*=100;b.tail*=100
 bpy.ops.object.mode_set(mode='OBJECT')
 for p in ob.pose.bones:
  for c in list(p.constraints):p.constraints.remove(c)
  p.rotation_mode='QUATERNION';p.location=(0,0,0);p.rotation_quaternion=(1,0,0,0);p.scale=(1,1,1)
 ob.animation_data_clear();return ob

arm=export_armature()
def select(objects):
 bpy.ops.object.select_all(action='DESELECT')
 for ob in objects:ob.hide_set(False);ob.select_set(True)
 bpy.context.view_layer.objects.active=arm

def fbx(path,objects,animation=False):
 select(objects)
 bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'ARMATURE','MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',use_mesh_modifiers=False,mesh_smooth_type='FACE',use_tspace=False,add_leaf_bones=False,use_armature_deform_only=True,armature_nodetype='NULL',bake_anim=animation,bake_anim_use_all_bones=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_force_startend_keying=True,bake_anim_step=1.0,bake_anim_simplify_factor=0.0,path_mode='RELATIVE',embed_textures=False)
 print('EXPORTED',path.relative_to(ROOT),flush=True)

meshes=[]
if '--no-mesh' not in args:
 source.animation_data.action=None
 for p in source.pose.bones:p.location=(0,0,0);p.rotation_quaternion=(1,0,0,0);p.scale=(1,1,1)
 for i in range(3):
  original=bpy.data.objects['Operative_LOD'+str(i)];mesh=original.copy();mesh.data=original.data.copy();mesh.name='SK_Operative_LOD'+str(i);bpy.context.collection.objects.link(mesh);mesh.parent=arm
  if mesh.data.shape_keys:
   for key in mesh.data.shape_keys.key_blocks:
    for v in key.data:v.co*=100
  for v in mesh.data.vertices:v.co*=100
  mesh.data.update();bpy.context.view_layer.update()
  for mod in list(mesh.modifiers):
   if mod.type=='ARMATURE':mod.object=arm;mod.use_deform_preserve_volume=False
  if mesh.data.shape_keys:
   mesh.data.shape_keys.animation_data_clear()
   for k in mesh.data.shape_keys.key_blocks:k.value=0
  meshes.append(mesh);scene.frame_start=1;scene.frame_end=2
  fbx(ROOT/'export'/('Operative.fbx' if i==0 else f'Operative_LOD{i}.fbx'),[arm,mesh])
 # Prop extracted from original skinned geometry, transformed to local origin.
 original=bpy.data.objects['Operative_LOD0'];vg=original.vertex_groups['beacon'];indices={v.index for v in original.data.vertices if any(g.group==vg.index and g.weight>.99 for g in v.groups)}
 origin=source.data.bones['beacon'].head_local;verts=[];faces=[];mats=[];mapping={}
 for old in sorted(indices):mapping[old]=len(verts);verts.append(tuple((original.data.vertices[old].co-origin)*100))
 for p in original.data.polygons:
  if all(i in indices for i in p.vertices):faces.append([mapping[i] for i in p.vertices]);mats.append(p.material_index)
 data=bpy.data.meshes.new('Beacon');data.from_pydata(verts,[],faces);data.update();beacon=bpy.data.objects.new('Beacon',data);bpy.context.collection.objects.link(beacon)
 bpy.ops.object.select_all(action='DESELECT');beacon.select_set(True);bpy.context.view_layer.objects.active=beacon;bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=.01);bpy.ops.object.mode_set(mode='OBJECT')
 for m in original.data.materials:data.materials.append(m)
 for p,m in zip(data.polygons,mats):p.material_index=m;p.use_smooth=True
 fbx(ROOT/'export/Beacon.fbx',[beacon]);bpy.data.objects.remove(beacon,do_unlink=True)
 for f in (ROOT/'source/textures').glob('*.png'):shutil.copyfile(f,ROOT/'export/textures'/f.name)

if '--mesh-only' not in args:
 if not rows:raise RuntimeError('No source motion manifest; author sources before baking.')
 source.animation_data_create();arm.animation_data_create()
 for i,row in enumerate(rows):
  name=row['id'];source.animation_data.action=bpy.data.actions[name]
  action=bpy.data.actions.get('BAKED_'+name)
  if action:bpy.data.actions.remove(action)
  action=bpy.data.actions.new('BAKED_'+name);action.use_fake_user=True;arm.animation_data.action=action
  scene.frame_start=int(row['frame_start']);scene.frame_end=int(row['frame_end'])
  # Evaluate animator control constraints at each 30Hz source frame, then localize.
  for f in range(scene.frame_start,scene.frame_end+1):
   scene.frame_set(f);deps=bpy.context.evaluated_depsgraph_get();evaluated=source.evaluated_get(deps)
   globals={b.name:evaluated.pose.bones[b.name].matrix.copy() for b in arm.data.bones}
   for matrix in globals.values():matrix.translation*=100
   for b in arm.pose.bones:
    rest=b.bone.matrix_local
    if b.parent:
     parent_rest=b.parent.bone.matrix_local
     b.matrix_basis=(parent_rest.inverted()@rest).inverted()@globals[b.parent.name].inverted()@globals[b.name]
    else:b.matrix_basis=rest.inverted()@globals[b.name]
    b.keyframe_insert('location',frame=f,group=b.name);b.keyframe_insert('rotation_quaternion',frame=f,group=b.name);b.keyframe_insert('scale',frame=f,group=b.name)
  action['sample_rate']=30;action['source_control_action']=name;action['root_policy']=row['root_motion_policy']
  scene.frame_set(scene.frame_start);fbx(ROOT/row['export_file'],[arm],True)
  print('BAKED',i+1,len(rows),name,flush=True)
 # Baked actions retained in finished source with export skeleton, hidden from editing.
 arm.name='Operative_Export_Skeleton';arm.scale=(.01,.01,.01);arm.hide_set(True);arm.hide_render=True
 scene.unit_settings.scale_length=source_unit_scale
 source.animation_data.action=bpy.data.actions['idle_relaxed'];scene.frame_start=1;scene.frame_end=121;scene.frame_set(1)
 for mesh in meshes:bpy.data.objects.remove(mesh,do_unlink=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'source/Operative.blend'))
else:
 for mesh in meshes:bpy.data.objects.remove(mesh,do_unlink=True)
 bpy.data.objects.remove(arm,do_unlink=True)
scene.unit_settings.scale_length=source_unit_scale
print('EXPORT COMPLETE',flush=True)

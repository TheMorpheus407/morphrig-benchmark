"""Produce the finished authoritative asset from original parametric sources."""
import bpy, sys, json, math, os, time, argparse
from pathlib import Path
from mathutils import Vector, Euler
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'source/generators'))
import character, rig

def clear():
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 for d in bpy.data.actions:bpy.data.actions.remove(d)

def setup_scene():
 scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.;scene.render.fps=30
 world=bpy.data.worlds.new('Neutral studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.095,.12,.16,1);world.node_tree.nodes['Background'].inputs[1].default_value=.5;scene.world=world
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.003));floor=bpy.context.object;floor.name='Presentation_Floor';m=bpy.data.materials.new('Studio_floor');m.diffuse_color=(.095,.115,.14,1);m.use_nodes=True;m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.075,.09,.12,1);m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.78;floor.data.materials.append(m)
 for n,p,power,size,color in [('Key',(-2,-3,4),450,4,(.81,.90,1)),('Fill',(2,-1,2.4),240,3,(1,.85,.75)),('Rim',(1,2,3),500,3,(.63,.81,1))]:
  dat=bpy.data.lights.new(n,'AREA');dat.energy=power;dat.shape='DISK';dat.size=size;dat.color=color;ob=bpy.data.objects.new(n,dat);bpy.context.collection.objects.link(ob);ob.location=p;ob.rotation_euler=(Vector((0,0,1))-ob.location).to_track_quat('-Z','Y').to_euler()
 dat=bpy.data.cameras.new('Inspection');camera=bpy.data.objects.new('Inspection',dat);bpy.context.collection.objects.link(camera);camera.location=(2.4,-4,2.0);camera.rotation_euler=(Vector((0,0,.94))-camera.location).to_track_quat('-Z','Y').to_euler();dat.type='ORTHO';dat.ortho_scale=2.15;scene.camera=camera
 scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
 prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
 for d in prefs.devices:d.use=d.type in ['OPTIX','CUDA']
 scene.cycles.device='GPU';scene.render.resolution_x=900;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
 scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
 return scene


def make_morphs(mesh,ob):
 # Facial targets correspond to independent exposed runtime sliders; curves bake bones.
 mesh.shape_key_add(name='Basis');rig.reset(ob);rig.apply_face(ob,{});bpy.context.view_layer.update()
 deps=bpy.context.evaluated_depsgraph_get();neutral=[v.co.copy() for v in mesh.evaluated_get(deps).data.vertices]
 for name in rig.FACE_KEYS:
  if name.startswith('viseme_'):continue
  value=.3 if 'eye_' in name else 1.
  face={name:value}

  rig.apply_face(ob,face);bpy.context.view_layer.update();ev=mesh.evaluated_get(deps);coords=[v.co.copy() for v in ev.data.vertices]
  k=mesh.shape_key_add(name=name.replace('.','_'),from_mix=False)
  for i,(v,base,delta) in enumerate(zip(k.data,mesh.data.vertices,coords)):v.co=base.co+(delta-neutral[i])
  k.value=0
 rig.apply_face(ob,{});bpy.context.view_layer.update()
 # Original controlled volume corrections at demanding limb poses, kept editable.
 for name,bone,axis,amount in [('correct_shoulder_L','upper_arm.L',0,.010),('correct_shoulder_R','upper_arm.R',0,.010),('correct_hip_L','thigh.L',1,.006),('correct_hip_R','thigh.R',1,.006),('correct_wrist_L','hand.L',0,.002),('correct_wrist_R','hand.R',0,.002)]:
  k=mesh.shape_key_add(name=name,from_mix=False);g=mesh.vertex_groups.get(bone)
  if g:
   for i,v in enumerate(mesh.data.vertices):
    weight=next((x.weight for x in v.groups if x.group==g.index),0)
    if weight>0:
     center=ob.data.bones[bone].head_local;d=v.co-center
     if d.length<(.11 if 'shoulder' in name or 'hip' in name else .07):k.data[i].co+=d.normalized()*amount*weight*(1-d.length/.14)
  # Source drivers track actual bend about bone (bake/export preserves keyed target availability).
  dr=k.driver_add('value').driver;v=dr.variables.new();v.name='bend';v.type='TRANSFORMS';v.targets[0].id=ob;v.targets[0].bone_target=bone;v.targets[0].transform_type='ROT_X';v.targets[0].transform_space='LOCAL_SPACE';dr.expression='min(1,max(0,abs(bend)-0.5))'
 return mesh.data.shape_keys


def make_lods(mesh,ob):
 lods=[]
 # Decimation preserves skin groups and material borders; facial controls via skeleton on all LODs.
 for i,ratio in [(1,.53),(2,.27)]:
  new=mesh.copy();new.data=mesh.data.copy();new.name='Operative_LOD'+str(i);bpy.context.collection.objects.link(new)
  bpy.context.view_layer.objects.active=new;bpy.ops.object.select_all(action='DESELECT');new.select_set(True)
  if new.data.shape_keys:bpy.ops.object.shape_key_remove(all=True)
  dec=new.modifiers.new('Authored game reduction','DECIMATE');dec.ratio=ratio;dec.use_collapse_triangulate=True;dec.delimit={'MATERIAL','UV'}
  while new.modifiers.find(dec.name)>0:bpy.ops.object.modifier_move_up(modifier=dec.name)
  bpy.ops.object.modifier_apply(modifier=dec.name);new.hide_render=True;new.hide_set(True);lods.append(new)
 return lods


def frame_pose(ob,mesh,p,frame):
 rig.apply_pose(ob,p,frame/30)
 for b in ob.pose.bones:
  # Deformation face bones are driven by property, do not key driven channels.
  if not b.bone.use_deform:
   b.keyframe_insert('location',frame=frame,group=b.name);b.keyframe_insert('rotation_quaternion',frame=frame,group=b.name);b.keyframe_insert('scale',frame=frame,group=b.name)
 for k in ob.pose.bones['CTRL_settings'].keys():ob.pose.bones['CTRL_settings'].keyframe_insert(data_path='["'+k+'"]',frame=frame,group='Limb settings')
 for k in rig.FACE_KEYS:ob.pose.bones['CTRL_face'].keyframe_insert(data_path='["'+k+'"]',frame=frame,group='Face controls')


def create_actions(ob,mesh):
 import motions
 rows=list(__import__('csv').DictReader(open(ROOT/'required_animations.csv')));entries=[];ob.animation_data_create()
 for i,row in enumerate(rows):
  ident=row['id'];meta=motions.entry_metadata(row);duration=meta['duration'];count=int(meta.get('frame_count',round(duration*30)+1));count=max(2,count)
  action=bpy.data.actions.new(ident);action.use_fake_user=True;ob.animation_data.action=action
  for frame in range(1,count+1):
   t=(frame-1)/30;frame_pose(ob,mesh,motions.pose_at(ident,t,duration),frame)
  action['source']='Original authored control motion';action['fps']=30;action['duration']=(count-1)/30;action['root_policy']=row['root_movement'];action['loop']=row['form']=='loop'
  entry=dict(meta);entry.update(id=ident,source_action=ident,export_take='BAKED_'+ident,export_file=f'export/animations/{ident}.fbx',unreal_asset=f'/Game/Operative/Animations/{ident}',frame_start=1,frame_end=count,frame_count=count,fps=30,sample_rate=30,duration=(count-1)/30,loop=row['form']=='loop',form=row['form'],root_motion_policy=row['root_movement'],root_movement=row['root_movement'],required_behavior=row['required_behavior'])
  entry.setdefault('nominal_speed_cm_s',meta.get('speed_cm_s',0));entry.setdefault('intended_layer',meta.get('layer','full_body'));entry.setdefault('layer','full_body');entry.setdefault('events',[])
  entries.append(entry);print('AUTHORED',i+1,ident,count,flush=True)
 # Seven demanding deformation demonstrations are extra source QA actions.
 tests={
  'overhead_reach':{'hands':{'L':(-.20,-.05,1.86),'R':(.20,-.05,1.86)}},
  'deep_squat':{'pelvis':(0,.04,.60),'hands':{'L':(-.22,-.24,1.00),'R':(.22,-.24,1.00)},'torso':(.20,0,0)},
  'crossed_arm':{'hands':{'L':(.18,-.19,1.33),'R':(-.18,-.20,1.29)}},
  'torso_twist':{'torso':(0,0,1.05),'hands':{'L':(-.34,-.18,1.30),'R':(.18,.28,1.25)}},
  'kneeling':{'pelvis':(0,0,.60),'feet':{'L':(-.11,-.27,.10),'R':(.11,.35,.10)},'hands':{'L':(-.26,-.10,.83),'R':(.32,-.12,.9)}},
  'hand_support':{'blade':0,'pelvis':(0,.10,.255),'torso':(1.1,0,0),'hands':{'L':(-.25,-.29,.045),'R':(.25,-.29,.045)},'hand_rot':{'L':(math.pi/2,0,0),'R':(math.pi/2,0,0)}},
  'closed_grip':{'hands':{'L':(-.18,-.26,1.24),'R':(.18,-.26,1.24)},'curls':{'L':[.6,.9,.9,.9,.9],'R':[.6,.9,.9,.9,.9]}}
 }
 for name,p in tests.items():
  a=bpy.data.actions.new('QA_'+name);a.use_fake_user=True;ob.animation_data.action=a;frame_pose(ob,mesh,p,1);frame_pose(ob,mesh,p,31)
 ob.animation_data.action=bpy.data.actions.get('idle_relaxed');bpy.context.scene.frame_set(1)
 return entries


def skeleton_doc(ob):
 bones=[{'name':b.name,'unreal_name':b.name.replace('.','_'),'parent':b.parent.name if b.parent else None,'unreal_parent':b.parent.name.replace('.','_') if b.parent else None,'head_m':list(b.head_local),'tail_m':list(b.tail_local),'rest_matrix':[list(row) for row in b.matrix_local]} for b in ob.data.bones if b.use_deform]
 sockets=[{'name':'hand_L','bone':'hand.L','offset_m':[0,0,0]},{'name':'hand_R','bone':'hand.R','offset_m':[0,0,0]},{'name':'emitter_muzzle','bone':'forearm.R','position_m':[.39,-.08,.966]},{'name':'blade_base','bone':'blade','position_m':[.442,.012,1.087]},{'name':'blade_tip','bone':'blade','position_m':[.481,-.003,.825]},{'name':'effect_chest','bone':'chest','position_m':[0,-.12,1.30]},{'name':'cell_socket','bone':'forearm.R','position_m':[.395,.031,1.01]},{'name':'beacon_socket','bone':'pelvis','position_m':[-.125,.118,.96]}]
 for socket in sockets:socket['unreal_bone']=socket['bone'].replace('.','_')
 return {'source_units':'meters','source_axes':{'right':'+X','forward':'-Y','up':'+Z'},'unreal_units':'centimeters','unreal_axes':{'forward':'+X','anatomical_right':'-Y','up':'+Z'},'source_to_unreal_position_cm':['-100 * source_y','-100 * source_x','100 * source_z'],'fbx_export_units':'centimeters; geometry, bind and keyed translations explicitly multiplied by 100','retained_export_skeleton_display_scale':.01,'fbx_import_scale':1,'standing_height_m':1.80,'root':'root','bones':bones,'sockets':sockets}


def report(mesh,lods,ob):
 stats=[]
 for o in [mesh]+lods:
  o.data.calc_loop_triangles();stats.append({'name':o.name,'triangles':len(o.data.loop_triangles),'vertices':len(o.data.vertices),'material_slots':len(o.data.materials),'skin_max_influences':max(sum(g.weight>1e-5 for g in v.groups) for v in o.data.vertices)})
 return {'lods':stats,'deformation_bones':len([b for b in ob.data.bones if b.use_deform]),'materials':[{'name':n,'metallic':m,'roughness':r,'normal_texture':n+'_Normal.png' if n in ['Skin','Suit'] else None} for n,c,m,r in character.PALETTE],'textures':{'count':10,'max_dimension':256,'rgba8_bytes':10*256*256*4,'with_mipmaps_bytes':int(10*256*256*4*4/3)},'height_m':1.8,'object_transforms':{'mesh_scale':[1,1,1],'rig_scale':[1,1,1]},'normal_map_convention':{'source':'Tangent-space OpenGL (+Y), non-color data','unreal':'Flip green channel on import for Unreal tangent convention','strength':.55},'authorship':'Parametric original mesh, handcrafted cross-section anatomical proportions, fitted weights and controls; all motion authored for this project.'}


def main():
 args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
 preview='--preview' in args
 clear();mesh,mats=character.create_character(ROOT);ob=rig.create_rig(mesh);rig.add_face_drivers(ob);rig.add_limb_control_drivers(ob);rig.add_look_controls(ob);rig.install_panel();scene=setup_scene();morphs=make_morphs(mesh,ob);lods=make_lods(mesh,ob)
 if not preview:
  entries=create_actions(ob,mesh);(ROOT/'docs/animation_manifest.json').write_text(json.dumps({'schema_version':1,'sample_rate':30,'animations':entries},indent=2))
 (ROOT/'docs/skeleton_and_sockets.json').write_text(json.dumps(skeleton_doc(ob),indent=2));(ROOT/'docs/material_and_lod_report.json').write_text(json.dumps(report(mesh,lods,ob),indent=2))
 rig.apply_face(ob,{})
 for l in lods:l.hide_set(True);l.hide_render=True
 # Finished scene includes original generators, source control curves and face panel.
 bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
 for screen in bpy.data.screens:
  for area in screen.areas:
   if area.type=='VIEW_3D':area.spaces.active.region_3d.view_distance=3;area.spaces.active.region_3d.view_location=(0,0,.95);area.spaces.active.shading.type='MATERIAL'
 scene.frame_start=1;scene.frame_end=121
 bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'source/Operative.blend'))
 scene.render.filepath=str(ROOT/'verification/neutral.png');bpy.ops.render.render(write_still=True)
 print('FINISHED SOURCE',flush=True)
if __name__=='__main__':main()

"""Independent read-only source acceptance audit. Does not save the production file."""
import bpy,sys,json,math,csv
from pathlib import Path
from mathutils import Vector,kdtree
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source/generators'))
import rig_tools
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'source/Operative.blend'))
rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];scene=bpy.context.scene;out=ROOT/'docs/validation/acceptance';out.mkdir(exist_ok=True)
report={'source':str(Path('source/Operative.blend')),'source_mtime':(ROOT/'source/Operative.blend').stat().st_mtime,'stats':{},'ground_samples':[],'contact_samples':[],'renders':[],'presets':[]}
manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations'];required=list(csv.DictReader((ROOT.parent/'required_animations.csv').open()))
ids=[r['id'] for r in required];report['inventory']={'required':len(ids),'missing_baked':[i for i in ids if i not in bpy.data.actions],'missing_editable':[i for i in ids if 'EDIT__'+i not in bpy.data.actions],'missing_face':[i for i in ids if 'FACE__'+i not in bpy.data.actions],'manifest_entries':len(manifest),'fps':scene.render.fps}
for ob in bpy.data.objects:
 if ob.name.startswith('Operative_LOD'):
  used=set(i for p in ob.data.polygons for i in p.vertices)
  report['stats'][ob.name]={'triangles':sum(len(p.vertices)-2 for p in ob.data.polygons),'vertices':len(ob.data.vertices),'material_slots':len(ob.data.materials),'uv_layers':len(ob.data.uv_layers),'loose_vertices':len(ob.data.vertices)-len(used),'max_influences':max(len(v.groups) for v in ob.data.vertices),'unweighted':sum(not v.groups for v in ob.data.vertices),'shape_keys':len(ob.data.shape_keys.key_blocks)-1}
report['bones']={'deform':sum(b.use_deform for b in rig.data.bones),'roots':[b.name for b in rig.data.bones if not b.parent],'all_parented_except_root':all(b.parent or b.name=='root' for b in rig.data.bones)}
report['texture_images']=[{'name':im.name,'size':list(im.size),'packed':bool(im.packed_file),'file':im.filepath} for im in bpy.data.images if im.source=='FILE']
groups={vg.index:vg.name for vg in mesh.vertex_groups}
def indices(prefixes):return [v.index for v in mesh.data.vertices if any(g.weight>.15 and any(groups[g.group].startswith(p) for p in prefixes) for g in v.groups)]
parts={n:indices(p) for n,p in {'cell':['cell'],'beacon':['beacon'],'left_hand':['hand.L','thumb.','index.','middle.','ring.','pinky.'],'feet':['foot.','toe.'],'blade':['blade_base','blade_tip']}.items()}
# Restrict fingers to anatomical left; broad prefix selection above includes both.
parts['left_hand']=[v.index for v in mesh.data.vertices if any(g.weight>.15 and (groups[g.group]=='hand.L' or (groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ['thumb','index','middle','ring','pinky'])) for g in v.groups)]
def action(name,frame):
 rig.animation_data.action=bpy.data.actions[name]
 if rig.animation_data.action.slots:rig.animation_data.action_slot=rig.animation_data.action.slots[0]
 fa=bpy.data.actions.get('FACE__'+name)
 mesh.data.shape_keys.animation_data.action=fa
 if fa and fa.slots:mesh.data.shape_keys.animation_data.action_slot=fa.slots[0]
 scene.frame_set(frame);rig.update_tag();bpy.context.view_layer.update()
 ev=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
 return [ev.matrix_world@v.co for v in ev.data.vertices]
for clip in ['prone_front','prone_back','dead_front','dead_back','sleep_loop','getup_front','getup_back','knockdown_front','knockdown_back','death_front','death_back']:
 item=next(i for i in manifest if i['id']==clip)
 for f in sorted(set([1,(item['frame_end']+1)//2,item['frame_end']])):
  verts=action(clip,f);mi=min(range(len(verts)),key=lambda i:verts[i].z);v=mesh.data.vertices[mi]
  report['ground_samples'].append({'clip':clip,'frame':f,'min_z_m':verts[mi].z,'lowest_vertex_groups':[groups[g.group] for g in v.groups],'feet_min_z_m':min(verts[i].z for i in parts['feet']),'blade_min_z_m':min(verts[i].z for i in parts['blade'])})
for clip,prop,frames in [('reload','cell',[20,28,35,45,51,55]),('deploy','beacon',[14,20,30,35,40,55])]:
 for f in frames:
  verts=action(clip,f);tree=kdtree.KDTree(len(parts[prop]))
  for j,i in enumerate(parts[prop]):tree.insert(verts[i],j)
  tree.balance();dist=sorted(tree.find(verts[i])[2] for i in parts['left_hand']);bounds=[[min(verts[i][a] for i in parts[prop]),max(verts[i][a] for i in parts[prop])] for a in range(3)]
  report['contact_samples'].append({'clip':clip,'frame':f,'prop':prop,'prop_bounds_m':bounds,'nearest_hand_vertex_m':dist[0],'nearest_10_average_m':sum(dist[:10])/10})
scene.render.engine='CYCLES';scene.cycles.samples=20;scene.render.resolution_x=800;scene.render.resolution_y=800;cam=scene.camera;cam.data.type='ORTHO'
def render(label,target,offset,scale):
 cam.data.ortho_scale=scale;cam.location=Vector(target)+Vector(offset);cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(out/(label+'.png'));bpy.ops.render.render(write_still=True);report['renders'].append(label+'.png')
for clip,frame in [('reload',20),('reload',35),('reload',51),('deploy',20),('deploy',35),('deploy',40)]:
 verts=action(clip,frame);prop='cell' if clip=='reload' else 'beacon';target=sum((verts[i] for i in parts[prop]),Vector())/len(parts[prop]);render(clip+'_'+str(frame)+'_contact',target,(.75,-1.25,.55),.55)
for clip in ['prone_front','prone_back','dead_front','dead_back','sleep_loop']:
 verts=action(clip,1);render(clip+'_floor',(0,0,.36),(2.7,-2.7,1.3),1.95)
action('TEST__closed_grip',1);hand=rig.pose.bones['hand.L'].head;render('closed_grip',hand,(.5,-1.4,.45),.48)
rig_tools.reset_pose()
for preset in ['joy_confidence','anger','concern_sadness','surprise','pain','focus']:
 rig_tools.expression(preset);render('preset_'+preset,(0,-.025,1.685),(.05,-1,.01),.30);report['presets'].append(preset)
(out/'probe.json').write_text(json.dumps(report,indent=2));print('ACCEPTANCE_PROBE',json.dumps(report))

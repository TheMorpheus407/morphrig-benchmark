import bpy,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import motion,face_values,action_curves
m=next(x for x in json.loads((root/'docs/animation_manifest.json').read_text())['animations'] if x['id']=='dialogue')
alignment=json.loads((root/'source/audio/dialogue_alignment.json').read_text());keys=bpy.data.objects['Operative_LOD0'].data.shape_keys
old=bpy.data.actions.get('FACE__dialogue')
if old:bpy.data.actions.remove(old)
a=bpy.data.actions.new('FACE__dialogue');a.use_fake_user=True;keys.animation_data.action=a;samples=[]
for i in range(m['frame_count']):
 t=i/(m['frame_count']-1);p=motion('dialogue',t,m['duration']);v=face_values(p,'dialogue',t,m['duration'],alignment)
 for key in keys.key_blocks:
  if key.name!='Basis':key.value=v.get(key.name,0.);key.keyframe_insert('value',frame=i+1,group='Facial articulation')
 rounded={k:round(value,4) for k,value in v.items() if value>.0001}
 total=sum(value for key,value in rounded.items() if key.startswith('viseme_'))
 if total>1:
  key=max((key for key in rounded if key.startswith('viseme_')),key=lambda key:rounded[key]);rounded[key]=round(rounded[key]-(total-1),4)
 samples.append({'time':i/30,'values':rounded})
for fc in action_curves(a):
 for k in fc.keyframe_points:k.interpolation='LINEAR'
for o in bpy.data.objects:
 if o.type=='MESH' and o.data.shape_keys:
  o.data.shape_keys.animation_data_create();o.data.shape_keys.animation_data.action=bpy.data.actions['FACE__idle_relaxed']
  if o.data.shape_keys.animation_data.action.slots:o.data.shape_keys.animation_data.action_slot=o.data.shape_keys.animation_data.action.slots[0]
facepath=root/'docs/facial_animation_curves.json';data=json.loads(facepath.read_text());data['clips']['dialogue']=samples;facepath.write_text(json.dumps(data,separators=(',',':')))
report={'max_sum_visemes':max(sum(v for k,v in s['values'].items() if k.startswith('viseme_')) for s in samples),'redundant_alias_keys_enabled':any(s['values'].get(k,0)>0 for s in samples for k in ('jaw_open','lip_close','mouth_wide','pucker')),'closed_lip_frames':[i+1 for i,s in enumerate(samples) if s['values'].get('viseme_MBP',0)>.99],'peak_open_vowel_frames':[i+1 for i,s in enumerate(samples) if s['values'].get('viseme_AA',0)>.99]}
(root/'docs/dialogue_viseme_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
bpy.context.scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

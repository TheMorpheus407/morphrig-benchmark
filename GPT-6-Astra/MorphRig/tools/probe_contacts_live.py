import bpy,sys,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import *
rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];rig.animation_data.action=None
for pb in rig.pose.bones:
 for c in pb.constraints:c.mute=True
keys=mesh.data.shape_keys
if keys.animation_data:keys.animation_data.action=None
for k in keys.key_blocks:k.value=0
names={g.index:g.name for g in mesh.vertex_groups};props={s:[v.index for v in mesh.data.vertices if any(names[g.group]==s for g in v.groups)] for s in ('beacon','blade_base','blade_tip')};hands={s:[v.index for v in mesh.data.vertices if any(names[g.group].endswith('.'+s) and names[g.group].split('.')[0] in ('hand','thumb','index','middle','ring','pinky') for g in v.groups)] for s in ('L','R')}
report=[]
for id,phases in [('deploy',[.24,.36,.48,.52,.56,.60,.64,.72,1.]),('prone_front',[0,.5,1]),('prone_back',[0,.5,1]),('dead_front',[0]),('dead_back',[0]),('sleep_loop',[0]),('getup_front',[0,.25,.5]),('getup_back',[0,.25,.5])]:
 for t in phases:
  p=motion(id,t,DURATIONS.get(id,2));apply_pose(rig,p,id,t);ev=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh();verts=[v.co.copy() for v in me.vertices]
  item={'clip':id,'phase':t,'whole_minZ':min(v.z for v in verts),'fingers_minZ':{s:min(verts[i].z for i in hands[s]) for s in ('L','R')},'blade_minZ':min(verts[i].z for i in props['blade_base']+props['blade_tip'])}
  if id=='deploy':
   ps=[verts[i] for i in props['beacon']];hs=[verts[i] for i in hands['L']];item['beacon_bounds']=[[min(v[i] for v in ps),max(v[i] for v in ps)] for i in range(3)];item['nearest_hand_m']=min((a-b).length for a in ps for b in hs);item['hand']=list(rig.pose.bones['hand.L'].head);item['kneeR']=list(rig.pose.bones['shin.R'].head)
  lowest=min(range(len(verts)),key=lambda i:verts[i].z);item['lowest_groups']=[names[g.group] for g in mesh.data.vertices[lowest].groups];item['arm_joints']={s:[list(rig.pose.bones[b+'.'+s].head) for b in ('upper_arm','forearm','hand')] for s in ('L','R')}
  report.append(item);ev.to_mesh_clear()
(root/'docs/live_contact_probe.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

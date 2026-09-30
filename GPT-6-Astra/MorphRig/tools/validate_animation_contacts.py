"""Measure evaluated skeletal continuity and geometric ground contact in Blender."""
import bpy,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1];rig=bpy.data.objects['Operative_Rig'];obj=bpy.data.objects['Operative_LOD0']
manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations'];groups={g.index:g.name for g in obj.vertex_groups}
indices={s:[v.index for v in obj.data.vertices if sum(g.weight for g in v.groups if groups[g.group] in ('foot.'+s,'toe.'+s))>.99] for s in ('L','R')}
report={'chain_continuity_max_m':0,'chain_continuity_by_clip':{},'stance_sole_bounds_m':{},'floor_pose_surface_minimum_z_m':{}}
def set_action(id,f):
 a=bpy.data.actions[id];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 keys=obj.data.shape_keys;fa=bpy.data.actions.get('FACE__'+id)
 if fa:
  keys.animation_data_create();keys.animation_data.action=fa
  if fa.slots:keys.animation_data.action_slot=fa.slots[0]
 bpy.context.scene.frame_set(f);bpy.context.view_layer.update()
for m in manifest:
 id=m['id'];high=0.
 for phase in (0,.25,.5,.75,1):
  set_action(id,round(1+(m['frame_end']-1)*phase))
  for side in ('L','R'):
   for parent,child in [('thigh','shin'),('shin','foot'),('upper_arm','forearm'),('forearm','hand')]:
    high=max(high,(rig.pose.bones[parent+'.'+side].tail-rig.pose.bones[child+'.'+side].head).length)
 report['chain_continuity_by_clip'][id]=high;report['chain_continuity_max_m']=max(high,report['chain_continuity_max_m'])
 if id.startswith(('walk_','run_')) or id=='sprint_f':
  stance=.21 if id=='sprint_f' else .28 if id.startswith('run_') else .57
  if id.endswith(('_l','_r')):stance*=.78
  vals=[]
  for f in range(1,m['frame_end']):
   set_action(id,f);phase=(f-1)/(m['frame_end']-1);ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
   for side,offset in [('L',0),('R',.5)]:
    if (phase+offset)%1<stance:vals.append(min(mesh.vertices[i].co.z for i in indices[side]))
   ev.to_mesh_clear()
  report['stance_sole_bounds_m'][id]={'min':min(vals),'max':max(vals)}
for id in ('prone_front','prone_back','dead_front','dead_back','sleep_loop'):
 set_action(id,1);ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();res={}
 for label,bones in [('pelvis',('pelvis',)),('torso',('spine_01','spine_02','chest')),('head',('head',)),('left_hand',('hand.L','index.01.L')),('right_hand',('hand.R','index.01.R'))]:
  ids=[v.index for v in obj.data.vertices if any(groups[g.group] in bones and g.weight>.4 for g in v.groups)]
  res[label]=min(mesh.vertices[i].co.z for i in ids)
 report['floor_pose_surface_minimum_z_m'][id]=res;ev.to_mesh_clear()
(root/'docs/animation_contact_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'max_chain_gap':report['chain_continuity_max_m'],'stance':report['stance_sole_bounds_m'],'floor':report['floor_pose_surface_minimum_z_m']},indent=2))
assert report['chain_continuity_max_m']<.001

"""Read-only closed-beacon volume and floor audit for every baked deploy sample."""
import bpy,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
root=Path(__file__).resolve().parents[1]
rig=bpy.data.objects['Operative_Rig'];obj=bpy.data.objects['Operative_LOD0']
rig.animation_data.action=bpy.data.actions['deploy'];rig.animation_data.action_slot=rig.animation_data.action.slots[0]
keys=obj.data.shape_keys;keys.animation_data.action=bpy.data.actions['FACE__deploy'];keys.animation_data.action_slot=keys.animation_data.action.slots[0]
groups={g.index:g.name for g in obj.vertex_groups}
hand={v.index for v in obj.data.vertices if any(g.weight>.15 and groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ('hand','thumb','index','middle','ring','pinky') for g in v.groups)}
thumb={v.index for v in obj.data.vertices if any(g.weight>.15 and groups[g.group].startswith('thumb.') and groups[g.group].endswith('.L') for g in v.groups)}
prop={v.index for v in obj.data.vertices if any(g.weight>.15 and groups[g.group]=='beacon' for g in v.groups)}
polys=[tuple(p.vertices) for p in obj.data.polygons if p.material_index==3 and all(i in prop for i in p.vertices)]
rows=[]
for frame in range(1,56):
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
 ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());vs=[ev.matrix_world@v.co for v in ev.data.vertices];body=BVHTree.FromPolygons(vs,polys,all_triangles=False)
 depths=[];dist=[];thumb_dist=[]
 for i in hand:
  hit,n,face,d=body.find_nearest(vs[i]);dist.append(d)
  if i in thumb:thumb_dist.append(d)
  if (vs[i]-hit).dot(n)<-1e-7:depths.append(d)
 rows.append({'frame':frame,'phase':(frame-1)/54,'inside_vertices':len(depths),'maximum_depth_m':max(depths,default=0),'hand_to_body_distance_m':min(dist),'thumb_to_body_distance_m':min(thumb_dist),'mesh_floor_minimum_m':min(v.z for v in vs),'hand_floor_minimum_m':min(vs[i].z for i in hand),'beacon_floor_minimum_m':min(vs[i].z for i in prop)})
report={'clip':'deploy','source':'source/Operative.blend','sample_count':55,'maximum_penetration_m':max(r['maximum_depth_m'] for r in rows),'maximum_carry_contact_gap_m':max(r['hand_to_body_distance_m'] for r in rows if .24<=r['phase']<=.60),'maximum_opposing_thumb_gap_m':max(r['thumb_to_body_distance_m'] for r in rows if .24<=r['phase']<=.60),'floor_minimum_m':min(r['mesh_floor_minimum_m'] for r in rows),'released_beacon_floor_maximum_m':max(r['beacon_floor_minimum_m'] for r in rows if r['phase']>=.60),'samples':rows}
report['passed']=report['maximum_penetration_m']<.0001 and report['maximum_carry_contact_gap_m']<.002 and report['maximum_opposing_thumb_gap_m']<.002 and report['floor_minimum_m']>-.001 and abs(report['released_beacon_floor_maximum_m'])<.001
(root/'docs/deploy_grip_validation.json').write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k!='samples'});assert report['passed']

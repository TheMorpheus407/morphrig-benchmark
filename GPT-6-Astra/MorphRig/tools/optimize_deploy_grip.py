import bpy,sys,json,itertools
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'));import animations as A
rig=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];rig.animation_data.action=None
for pb in rig.pose.bones:
 for c in pb.constraints:c.mute=True
if o.data.shape_keys.animation_data:o.data.shape_keys.animation_data.action=None
for k in o.data.shape_keys.key_blocks:k.value=0
groups={g.index:g.name for g in o.vertex_groups};hi={v.index for v in o.data.vertices if any(g.weight>.15 and groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ('hand','thumb','index','middle','ring','pinky') for g in v.groups)};pi={v.index for v in o.data.vertices if any(groups[g.group]=='beacon' for g in v.groups)};polys=[tuple(p.vertices) for p in o.data.polygons if p.material_index==3 and all(i in pi for i in p.vertices)]
results=[]
for x,y,z in itertools.product((.015,),(.089,),(.115,)):
 A.DEPLOY_GRIP_OFFSET=Vector((x,y,z));worst=0.;gap=0.;minz=100;contact=[]
 for t in [f/54 for f in range(0,55)]:
  p=A.motion('deploy',t,1.8);A.apply_pose(rig,p,'deploy',t);ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());vs=[v.co.copy() for v in ev.data.vertices];bvh=BVHTree.FromPolygons(vs,polys,all_triangles=False);depths=[];dist=[]
  for i in hi:
   hit,normal,face,distance=bvh.find_nearest(vs[i]);dist.append(distance)
   if (vs[i]-hit).dot(normal)<-1e-7:depths.append(distance)
  worst=max(worst,max(depths,default=0));gap=max(gap,min(dist));minz=min(minz,min(vs[i].z for i in hi));contact.append({'phase':t,'penetration':max(depths,default=0),'gap':min(dist),'inside_count':len(depths)})
 score=worst*20+max(0,gap-.004)*5+max(0,-minz)*20
 results.append({'offset':[x,y,z],'max_penetration':worst,'max_gap':gap,'hand_min_z':minz,'score':score,'contacts':contact})
results.sort(key=lambda r:r['score']);(root/'docs/deploy_grip_search.json').write_text(json.dumps(results,indent=2));print(json.dumps(results[:4],indent=2))

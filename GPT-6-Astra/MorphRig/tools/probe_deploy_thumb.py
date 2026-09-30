import bpy,json,sys
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'));import animations as A
r=bpy.data.objects['Operative_Rig'];r.animation_data.action=None
for p in r.pose.bones:
 for c in p.constraints:c.mute=True
A.DEPLOY_THUMB_TARGET=Vector((-.037,.018,.068));A.apply_pose(r,A.motion('deploy',19/54,1.8),'deploy',19/54)
b=r.pose.bones['beacon'].head.copy()
for n in ['hand.L','thumb.01.L','thumb.02.L','thumb.03.L','index.03.L','middle.03.L']:
 p=r.pose.bones[n];print(n,'length',p.length,'head',list(p.head-b),'tail',list(p.tail-b),'location',list(p.location),'quat',list(p.rotation_quaternion))
o=bpy.data.objects['Operative_LOD0'];ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());groups={g.index:g.name for g in o.vertex_groups}
for bn in ['thumb.01.L','thumb.02.L','thumb.03.L']:
 vi=[v.index for v in o.data.vertices if any(groups[g.group]==bn and g.weight>.15 for g in v.groups)];print(bn,'bbox',[[min(ev.data.vertices[i].co[a]-b[a] for i in vi),max(ev.data.vertices[i].co[a]-b[a] for i in vi)] for a in range(3)])
from mathutils.bvhtree import BVHTree
pi={v.index for v in o.data.vertices if any(groups[g.group]=='beacon' for g in v.groups)};poly=[tuple(p.vertices) for p in o.data.polygons if p.material_index==3 and all(i in pi for i in p.vertices)];pool={i for p in poly for i in p};vs=[v.co for v in ev.data.vertices];body=BVHTree.FromPolygons(vs,poly,all_triangles=False);print('bodybbox',[[min(vs[i][a]-b[a] for i in pool),max(vs[i][a]-b[a] for i in pool)] for a in range(3)])
hi={v.index for v in o.data.vertices if any(groups[g.group].startswith('thumb.') and groups[g.group].endswith('.L') and g.weight>.15 for g in v.groups)}
rank=sorted([(body.find_nearest(vs[i])[3],i) for i in hi]);d,i=rank[0];hit,n,_,_=body.find_nearest(vs[i]);print('nearest',d,i,'v',list(vs[i]-b),'hit',list(hit-b),'n',list(n))

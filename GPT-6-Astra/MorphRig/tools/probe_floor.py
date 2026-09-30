import bpy,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import *
rig=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];rig.animation_data.action=None
for p in rig.pose.bones:
 for c in p.constraints:c.mute=True
for key in o.data.shape_keys.key_blocks:key.value=0
for id in ('prone_front','prone_back','dead_front','dead_back','sleep_loop'):
 p=motion(id,0,2);apply_pose(rig,p,id,0);ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();groups={g.index:g.name for g in o.vertex_groups};mins={}
 for region in [('pelvis',),('spine_01','spine_02','chest'),('head',),('foot.L','toe.L'),('hand.L','index.01.L')]:
  verts=[mesh.vertices[v.index].co.z for v in o.data.vertices if any(groups[g.group] in region and g.weight>.4 for g in v.groups)]
  mins[str(region)]=round(min(verts),5)
 print(id,mins);ev.to_mesh_clear()

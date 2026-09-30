import bpy,json
from pathlib import Path
rig=bpy.data.objects['Operative_Rig'];rig.animation_data.action=bpy.data.actions['idle_relaxed'];bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
for n in ('root','pelvis','thigh.L','shin.L','foot.L','toe.L','hand.L','foot.R'):
 p=rig.pose.bones[n];print(n,'head',tuple(p.head),'tail',tuple(p.tail),'loc',tuple(p.location),'constraints',[(c.name,c.influence,c.mute) for c in p.constraints])
o=bpy.data.objects['Operative_LOD0']; dg=bpy.context.evaluated_depsgraph_get();mesh=o.evaluated_get(dg).to_mesh();print('minZ',min(v.co.z for v in mesh.vertices))
for side in ('L','R'):
 groups={g.index:g.name for g in o.vertex_groups};ids=[v.index for v in o.data.vertices if any(groups[g.group].startswith(('foot.'+side,'toe.'+side)) and g.weight>.4 for g in v.groups)]
 print(side,'boot_minZ',min(mesh.vertices[i].co.z for i in ids),'verts',len(ids))

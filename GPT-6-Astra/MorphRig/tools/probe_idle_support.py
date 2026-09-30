import bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];rig=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];rig.animation_data.action=bpy.data.actions['idle_combat'];rig.animation_data.action_slot=rig.animation_data.action.slots[0];k=o.data.shape_keys;k.animation_data.action=bpy.data.actions['FACE__idle_combat'];k.animation_data.action_slot=k.animation_data.action.slots[0];bpy.context.scene.frame_set(31);bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());groups={g.index:g.name for g in o.vertex_groups};report={'clip':'idle_combat','frame':31,'time_s':1.0,'units':'meters','sides':{}}
for side in ['L','R']:
 ids=[v.index for v in o.data.vertices if sum(g.weight for g in v.groups if groups[g.group] in ['foot.'+side,'toe.'+side])>.99];vi=min(ids,key=lambda i:(ev.matrix_world@ev.data.vertices[i].co).z);vs=[ev.matrix_world@ev.data.vertices[i].co for i in ids];data={'boot_min_z':min(v.z for v in vs),'lowest_boot_point':list(ev.matrix_world@ev.data.vertices[vi].co),'boot_bounds':[[min(v[a] for v in vs),max(v[a] for v in vs)] for a in range(3)],'bones':{}}
 for bn in ['foot.'+side,'toe.'+side]:
  p=rig.pose.bones[bn];data['bones'][bn]={'head':list(rig.matrix_world@p.head),'tail':list(rig.matrix_world@p.tail),'world_matrix':[list(row) for row in rig.matrix_world@p.matrix]}
 report['sides'][side]=data
(root/'docs/validation/idle_support_final.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

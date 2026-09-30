import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source/generators'));import rig
ob=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];ob.animation_data_clear();rig.reset(ob);rig.apply_pose(ob,{'hands':{'L':(-.20,-.05,1.86),'R':(.20,-.05,1.86)}});ob.update_tag();bpy.context.view_layer.update()
i=1552;v=mesh.data.vertices[i];print('WEIGHTS',[(mesh.vertex_groups[g.group].name,g.weight) for g in v.groups])
for k in mesh.data.shape_keys.key_blocks:print('KEY',k.name,k.value,'delta',(k.data[i].co-v.co).length)
mat=ob.pose.bones['upper_arm.L'].matrix@ob.data.bones['upper_arm.L'].matrix_local.inverted();print('linear expected',mat@v.co)
for dv in [True,False]:
 mesh.modifiers[0].use_deform_preserve_volume=dv;mesh.update_tag();bpy.context.view_layer.update();print('DQ',dv,mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices[i].co)

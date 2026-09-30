import bpy,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source/generators'))
import rig
ob=bpy.data.objects['Operative_Rig'];ob.animation_data_clear()
for n,p in [('rest',{}),('up',{'hands':{'L':(-.20,-.05,1.86),'R':(.20,-.05,1.86)}}),('squat',{'pelvis':(0,.04,.60),'hands':{'L':(-.22,-.24,1.00),'R':(.22,-.24,1.00)},'torso':(.20,0,0)})]:
 rig.reset(ob);rig.apply_pose(ob,p);ob.update_tag();bpy.context.view_layer.update()
 print(n)
 for bone in ['clavicle.L','upper_arm.L','forearm.L','hand.L','thigh.L','shin.L','foot.L','upper_arm.R']:
  b=ob.pose.bones[bone];print(bone,'head',tuple(round(x,4) for x in b.head),'tail',tuple(round(x,4) for x in b.tail),'scale',tuple(round(x,4) for x in b.matrix.to_scale()),'rot',tuple(round(x,4) for x in b.matrix.to_quaternion()))
 mesh=bpy.data.objects['Operative_LOD0'];ev=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
 vg=mesh.vertex_groups['upper_arm.L'];verts=[(i,v.co) for i,v in enumerate(mesh.data.vertices) if any(g.group==vg.index and g.weight>.99 for g in v.groups)]
 print('raw',[(i,tuple(v)) for i,v in verts[:3]]);print('ev',[(i,tuple(ev.data.vertices[i].co)) for i,v in verts[:3]])

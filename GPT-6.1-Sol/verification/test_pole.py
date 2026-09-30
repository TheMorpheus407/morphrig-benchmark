import bpy,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source/generators'));import rig
ob=bpy.data.objects['Operative_Rig'];ob.animation_data_clear();rig.reset(ob);rig.apply_pose(ob,{'pelvis':(0,.04,.60)})
for side in ['L','R']:
 for a in [-math.pi,-math.pi*.5,0,math.pi*.5,math.pi]:
  c=ob.pose.bones['shin.'+side].constraints['Two-bone leg IK'];c.pole_angle=a;ob.update_tag();bpy.context.view_layer.update();print(side,a,ob.pose.bones['shin.'+side].head)

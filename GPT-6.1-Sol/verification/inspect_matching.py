import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source/generators'));import rig
exec(rig.PANEL_SCRIPT,{})
o=bpy.data.objects['Operative_Rig'];o.animation_data.action=None;rig.reset(o);rig.apply_pose(o,{'pelvis':(0,.04,.60)})
for stage in ['before','fk','ik']:
 if stage!='before':bpy.ops.morphrig.switch(side='L',limb='leg')
 print(stage)
 for n in ['pelvis','CTRL_pelvis','thigh.L','shin.L','foot.L','FK_thigh.L','FK_shin.L','FK_foot.L','IK_foot.L','MCH_ankle.L']:
  b=o.pose.bones[n];print(n,'head',tuple(round(x,5) for x in b.head),'tail',tuple(round(x,5) for x in b.tail),'scale',tuple(b.matrix.to_scale()))

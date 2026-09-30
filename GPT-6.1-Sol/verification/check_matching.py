import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source/generators'));import rig
exec(rig.PANEL_SCRIPT,{})
o=bpy.data.objects['Operative_Rig'];o.animation_data.action=None
for name,pose in [('up',{'hands':{'L':(-.20,-.05,1.86),'R':(.20,-.05,1.86)}}),('squat',{'pelvis':(0,.04,.60)})]:
 rig.reset(o);rig.apply_pose(o,pose)
 for side in ['L','R']:
  for limb,parts in [('arm',['upper_arm','forearm','hand']),('leg',['thigh','shin','foot'])]:
   before=[o.pose.bones[p+'.'+side].matrix.copy() for p in parts]
   bpy.ops.morphrig.switch(side=side,limb=limb);bpy.ops.morphrig.switch(side=side,limb=limb)
   after=[o.pose.bones[p+'.'+side].matrix.copy() for p in parts]
   print(name,side,limb,max((b.translation-a.translation).length for a,b in zip(before,after)),max(a.to_quaternion().rotation_difference(b.to_quaternion()).angle for a,b in zip(before,after)))

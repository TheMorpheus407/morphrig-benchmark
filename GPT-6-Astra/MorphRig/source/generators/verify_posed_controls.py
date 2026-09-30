import bpy,sys,json
from pathlib import Path
from mathutils import Euler
sys.path.insert(0,str(Path(__file__).parent))
import rig_tools
root=Path(__file__).resolve().parents[2]
bpy.ops.wm.open_mainfile(filepath=str(root/'source/Character_Master.blend'))
r=bpy.data.objects['Operative_Rig'];report={}
for side in ['L','R']:
 for limb,first,second in [('arm','upper_arm','forearm'),('leg','thigh','shin')]:
  rig_tools.reset_pose()
  for name,rot in [(first,(.25,.15,.45)),(second,(.05,0,-.8))]:
   p=r.pose.bones[name+'.'+side];p.rotation_mode='XYZ';p.rotation_euler=rot
  r.update_tag();bpy.context.view_layer.update()
  report[limb+'.'+side]=rig_tools.match_switch(limb,side,True)
print('POSED_MATCH',json.dumps(report))
p=root/'docs/rig_validation.json';data=json.loads(p.read_text());data['posed_ik_fk_matching']=report;p.write_text(json.dumps(data,indent=2))

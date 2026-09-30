"""Read-only control smoke test on the final animated deliverable."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'source/generators'))
import rig_tools
bpy.ops.wm.open_mainfile(filepath=str(root/'source/Operative.blend'))
rig=bpy.data.objects['Operative_Rig'];report={'source_mtime':(root/'source/Operative.blend').stat().st_mtime,'controls':{}}
for side in ['L','R']:
 for limb in ['arm','leg']:
  rig_tools.reset_pose()
  report['controls']['match_'+limb+'_'+side]=rig_tools.match_switch(limb,side,True)
  rig_tools.match_switch(limb,side,False)
 rig_tools.reset_pose();bone=rig.pose.bones['index.03.'+side];before=bone.tail.copy()
 rig['finger_curl.'+side]=1;rig.update_tag();bpy.context.view_layer.update()
 report['controls']['curl_'+side]={'tip_displacement_m':(bone.tail-before).length}
 rig_tools.reset_pose();rig_tools.match_switch('leg',side,True);bone=rig.pose.bones['foot.'+side];before=bone.head.copy()
 rig['foot_roll.'+side]=.5;rig.update_tag();bpy.context.view_layer.update()
 report['controls']['roll_'+side]={'ankle_displacement_m':(bone.head-before).length}
rig_tools.reset_pose();rig['global_scale']=1.25;rig.update_tag();bpy.context.view_layer.update()
report['controls']['global_scale']=list(rig.scale)
rig_tools.reset_pose();bpy.context.view_layer.update()
report['constraints']={p.name:[{'name':c.name,'muted':c.mute,'influence':c.influence} for c in p.constraints] for p in rig.pose.bones if p.constraints}
(root/'docs/validation/acceptance/live_controls.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report['controls'],indent=2))

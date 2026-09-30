import bpy,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1];rig=bpy.data.objects['Operative_Rig'];manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations'];report=[]
for m in manifest:
 if not m['id'].startswith('aim_'):continue
 a=bpy.data.actions[m['id']];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 bpy.context.scene.frame_set(1);bpy.context.view_layer.update();p=rig.pose.bones['emitter_muzzle'];d=(p.tail-p.head).normalized();yaw=math.degrees(math.atan2(-d.x,-d.y));pitch=math.degrees(math.asin(d.z));report.append({'id':m['id'],'requested_yaw':m['aim_yaw_degrees'],'requested_pitch':m['aim_pitch_degrees'],'measured_muzzle_yaw':yaw,'measured_muzzle_pitch':pitch,'yaw_error':yaw-m['aim_yaw_degrees'],'pitch_error':pitch-m['aim_pitch_degrees']})
(root/'docs/aim_calibration_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

"""Evaluate a matched IK edit, then confirm deform-only baking retains hand contact."""
import bpy,sys,json
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'tools'),str(root/'source/generators')]
from rebake_action import rebake
from rig_tools import match_switch
rig=bpy.data.objects['Operative_Rig'];source=bpy.data.actions['EDIT__ranged_fire'];rig.animation_data.action=source
if source.slots:rig.animation_data.action_slot=source.slots[0]
bpy.context.scene.frame_set(5);before=rig.pose.bones['hand.L'].head.copy();match=match_switch('arm','L',True,rig)
control=rig.pose.bones['CTRL_hand_ik.L'];m=control.matrix.copy();m.translation+=Vector((0,-.04,.04));control.matrix=m;rig.update_tag();bpy.context.view_layer.update()
for f in (1,10):
 control.keyframe_insert('location',frame=f);control.keyframe_insert('rotation_euler',frame=f);rig.keyframe_insert(data_path='["arm_ik.L"]',frame=f)
bpy.context.scene.frame_set(5);rig.update_tag();bpy.context.view_layer.update();expected=rig.pose.bones['hand.L'].matrix.copy();baked=rebake(rig,'ranged_fire')
for pb in rig.pose.bones:
 for c in pb.constraints:c.mute=True
rig.animation_data.action=baked
if baked.slots:rig.animation_data.action_slot=baked.slots[0]
bpy.context.scene.frame_set(5);bpy.context.view_layer.update();actual=rig.pose.bones['hand.L'].matrix.copy()
report={'match_error_m':match,'ik_hand_displacement_m':(expected.translation-before).length,'baked_vs_live_ik_hand_matrix_error':max(abs(actual[i][j]-expected[i][j]) for i in range(4) for j in range(4)),'source_saved':False}
report['passes']=report['baked_vs_live_ik_hand_matrix_error']<1e-5 and report['ik_hand_displacement_m']>.03
(root/'docs/rebake_ik_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert report['passes'],report

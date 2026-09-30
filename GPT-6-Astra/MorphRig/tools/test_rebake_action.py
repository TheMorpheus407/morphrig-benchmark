"""Non-destructive test: edit FK source, rebake, export, and compare reimported motion."""
import bpy,sys,json
from pathlib import Path
from mathutils import Quaternion
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'))
from rebake_action import rebake
rig=bpy.data.objects['Operative_Rig'];id='ranged_fire';source=bpy.data.actions['EDIT__'+id]
rig.animation_data.action=source
if source.slots:rig.animation_data.action_slot=source.slots[0]
bpy.context.scene.frame_set(5);bpy.context.view_layer.update();pb=rig.pose.bones['hand.L'];before=pb.matrix.copy()
for obj in bpy.context.scene.objects:obj.select_set(False)
rig.name='Armature';rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=10
out=root/'docs/validation';out.mkdir(exist_ok=True);baseline=out/'rebake_baseline.fbx';changed=out/'rebake_changed.fbx'
kw=dict(use_selection=True,object_types={'ARMATURE'},add_leaf_bones=False,use_armature_deform_only=True,bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,axis_forward='-Y',axis_up='Z',apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS')
bpy.ops.export_scene.fbx(filepath=str(baseline),**kw)
bpy.context.scene.frame_set(5);pb.rotation_quaternion=pb.rotation_quaternion@Quaternion((1,0,0),.35);pb.keyframe_insert('rotation_quaternion',frame=5,group=pb.name);bpy.context.view_layer.update();edited=pb.matrix.copy()
baked=rebake(rig,id)
for bone in rig.pose.bones:
 for con in bone.constraints:con.mute=True
rig.animation_data.action=baked
if baked.slots:rig.animation_data.action_slot=baked.slots[0]
bpy.context.scene.frame_set(5);bpy.context.view_layer.update();after=rig.pose.bones['hand.L'].matrix.copy()
error=max(abs(after[i][j]-edited[i][j]) for i in range(4) for j in range(4));change=max(abs(after[i][j]-before[i][j]) for i in range(4) for j in range(4))
report={'clip':id,'frame':5,'edited_bone':'hand.L','edited_rotation_radians':.35,'max_evaluated_matrix_error':error,'max_change_from_original':change,'source_retained':bpy.data.actions.get('EDIT__'+id) is not None,'production_blend_saved':False}
assert error<1e-5 and change>.05,report
bpy.ops.export_scene.fbx(filepath=str(changed),**kw)
def imported_pose(path):
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True,automatic_bone_orientation=False)
 arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');start=arm.animation_data.action.frame_range[0];bpy.context.scene.frame_set(round(start+4));bpy.context.view_layer.update();return arm.pose.bones['hand.L'].matrix.copy()
a=imported_pose(baseline);b=imported_pose(changed)
angle=a.to_quaternion().rotation_difference(b.to_quaternion()).angle
report['exported_pose_change_radians']=min(angle,2*__import__('math').pi-angle)
report['exported_fbx_bytes']=changed.stat().st_size
report['passes']=error<1e-5 and abs(report['exported_pose_change_radians']-.35)<.005
(root/'docs/rebake_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert report['passes'],report

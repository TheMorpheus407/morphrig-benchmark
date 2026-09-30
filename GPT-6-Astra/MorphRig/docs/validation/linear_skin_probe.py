"""Read-only side-by-side skin inspection using Unreal-equivalent linear skinning."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[2]
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
source=Path(args[0]).resolve() if args else root/'source/Operative.blend'
bpy.ops.wm.open_mainfile(filepath=str(source));scene=bpy.context.scene;rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0'];mod=next(m for m in mesh.modifiers if m.type=='ARMATURE')
out=root/'docs/validation/linear_skin';out.mkdir(exist_ok=True)
scene.render.resolution_x=850;scene.render.resolution_y=950;scene.render.resolution_percentage=100;scene.cycles.samples=20
cam=scene.camera;cam.data.type='ORTHO';cam.data.ortho_scale=1.9;cam.location=(2.7,-4,2.5);cam.rotation_euler=(Vector((0,0,.8))-cam.location).to_track_quat('-Z','Y').to_euler()
report=[]
for clip,frame in [('death_front',37),('respawn',11),('reload',35)]:
 rig.animation_data.action=bpy.data.actions[clip];rig.animation_data.action_slot=rig.animation_data.action.slots[0]
 fa=bpy.data.actions['FACE__'+clip];mesh.data.shape_keys.animation_data.action=fa;mesh.data.shape_keys.animation_data.action_slot=fa.slots[0]
 scene.frame_set(frame);bpy.context.view_layer.update()
 report.append({'clip':clip,'frame':frame,'active_shapes':{k.name:k.value for k in mesh.data.shape_keys.key_blocks if k.name!='Basis' and abs(k.value)>.001},'right_forearm_relative_rotation_deg':math.degrees(rig.pose.bones['upper_arm.R'].matrix.to_quaternion().rotation_difference(rig.pose.bones['forearm.R'].matrix.to_quaternion()).angle)})
 for dq in [False,True]:
  mod.use_deform_preserve_volume=dq;bpy.context.view_layer.update();scene.render.filepath=str(out/(clip+('_DQ' if dq else '_linear')+'.png'));bpy.ops.render.render(write_still=True)
(out/'pose_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

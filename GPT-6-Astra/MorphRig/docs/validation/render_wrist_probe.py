import bpy,sys
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[2]
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
path=Path(args[0]).resolve() if args and not args[0].startswith('--') else root/'source/Operative.blend'
bpy.ops.wm.open_mainfile(filepath=str(path))
scene=bpy.context.scene;rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0']
rig.animation_data.action=bpy.data.actions['deploy'];rig.animation_data.action_slot=rig.animation_data.action.slots[0]
if mesh.data.shape_keys.animation_data:mesh.data.shape_keys.animation_data.action=None
for key in mesh.data.shape_keys.key_blocks:
 if key.name!='Basis':key.value=0
scene.render.resolution_x=800;scene.render.resolution_y=800;scene.render.resolution_percentage=100;scene.cycles.samples=24
for frame in ([20,30,35] if '--deploy' in args else [35]):
 scene.frame_set(frame);bpy.context.view_layer.update()
 target=rig.pose.bones['beacon'].head+Vector((0,0,.036)) if '--deploy' in args else rig.pose.bones['hand.L'].head+Vector((0,0,-.025))
 cam=scene.camera;cam.data.type='ORTHO';cam.data.ortho_scale=.55 if '--deploy' in args else .31;cam.location=target+Vector((.75,-1.25,.55));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
 scene.render.filepath=str(root/(f'docs/validation/acceptance/deploy_{frame}_contact.png' if '--deploy' in args else 'docs/validation/wrist_weights_after.png'))
 bpy.ops.render.render(write_still=True)

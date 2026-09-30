import bpy,sys,json
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'source/generators'))
import rig_tools
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
path=Path(args[0]).resolve() if args else root/'docs/validation/Operative_Squint_Preview.blend'
bpy.ops.wm.open_mainfile(filepath=str(path));scene=bpy.context.scene;mesh=bpy.data.objects['Operative_LOD0'];rig=bpy.data.objects['Operative_Rig']
cam=scene.camera;cam.data.type='ORTHO';cam.data.ortho_scale=.26;cam.location=(0,-1,1.69);cam.rotation_euler=(Vector((0,0,1.69))-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.resolution_x=900;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.cycles.samples=24
for preset in ['anger','focus']:
 rig_tools.reset_pose();rig_tools.expression(preset);bpy.context.view_layer.update();scene.render.filepath=str(root/f'docs/validation/squint_{preset}_after.png');bpy.ops.render.render(write_still=True)
rig_tools.reset_pose();mesh.data.shape_keys.key_blocks['squint.L'].value=1;mesh.data.shape_keys.key_blocks['squint.R'].value=1;bpy.context.view_layer.update();scene.render.filepath=str(root/'docs/validation/squint_full_after.png');bpy.ops.render.render(write_still=True)

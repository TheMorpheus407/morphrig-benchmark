import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import character
bpy.ops.wm.open_mainfile(filepath=str(character.ROOT/'source/Character_Master.blend'))
o=bpy.data.objects['Operative_LOD0']
print('SHAPES',[(k.name,k.value) for k in o.data.shape_keys.key_blocks])
cam=bpy.context.scene.camera;cam.location=(0,-1,1.68);cam.rotation_euler=(1.5707963,0,0);cam.data.ortho_scale=.31
bpy.context.scene.render.resolution_x=1000;bpy.context.scene.render.resolution_y=1000;bpy.context.scene.render.filepath=str(character.ROOT/'docs/face_inspection.png');bpy.ops.render.render(write_still=True)

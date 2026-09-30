"""Actual delivered speech-action close-up inspection, with shape action assigned."""
import bpy
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'source/Operative.blend'))
scene=bpy.context.scene;rig=bpy.data.objects['Operative_Rig'];face=bpy.data.objects['Operative_LOD0']
rig.animation_data.action=bpy.data.actions['dialogue'];face.data.shape_keys.animation_data.action=bpy.data.actions['FACE__dialogue']
scene.render.resolution_x=800;scene.render.resolution_y=900;scene.cycles.samples=24;cam=scene.camera;cam.data.type='ORTHO';cam.data.ortho_scale=.38
for frame in [75,145,250]:
    scene.frame_set(frame);bpy.context.view_layer.update();head=rig.matrix_world@rig.pose.bones['head'].head;target=head+Vector((0,-.03,.075));cam.location=target+Vector((.15,-1,.015));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(ROOT/'docs/rig_validation'/('speech_'+str(frame)+'.png'));bpy.ops.render.render(write_still=True)

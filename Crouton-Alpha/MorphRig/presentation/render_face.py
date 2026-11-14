import bpy, math, os
from mathutils import Vector
BLEND="/home/candidate/workspace/MorphRig/source/Operative.blend"
OUT="/home/candidate/workspace/MorphRig/presentation"
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc=bpy.context.scene
sc.render.engine='CYCLES'; sc.cycles.samples=8; sc.cycles.use_denoising=True
sc.render.resolution_x=480; sc.render.resolution_y=480
sc.render.image_settings.file_format='PNG'
arm=bpy.data.objects['Operative_Deform']
ld=bpy.data.lights.new("sunv",'SUN'); lo=bpy.data.objects.new("sunv",ld)
sc.collection.objects.link(lo); lo.rotation_euler=(0.9,0.2,0.5); ld.energy=4
w=bpy.data.worlds.new("wv"); sc.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.08,0.08,0.10,1)
cam_data=bpy.data.cameras.new("facecam"); cam=bpy.data.objects.new("facecam",cam_data)
sc.collection.objects.link(cam); sc.camera=cam
cam.location=(0.35,-1.2,1.62)
d=Vector((0,0,1.62))-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
act=bpy.data.actions['dialogue']
arm.animation_data.action=act
if act.slots: arm.animation_data.action_slot=act.slots[0]
sc.frame_start=1; sc.frame_end=461
sc.render.filepath=os.path.join(OUT,"face_")
bpy.ops.render.render(animation=True)
print("face rendered")

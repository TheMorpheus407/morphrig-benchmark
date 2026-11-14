import bpy, math, os
BLEND="/home/candidate/workspace/MorphRig/source/Operative.blend"
OUT="/home/candidate/workspace/MorphRig/presentation"
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc=bpy.context.scene
sc.render.engine='CYCLES'; sc.cycles.samples=8; sc.cycles.use_denoising=True
sc.render.resolution_x=480; sc.render.resolution_y=480
sc.render.image_settings.file_format='PNG'
arm=bpy.data.objects['Operative_Deform']
def setup_cam():
    cam_data=bpy.data.cameras.new("vcam"); cam=bpy.data.objects.new("vcam",cam_data)
    sc.collection.objects.link(cam); sc.camera=cam
    return cam
setup_light_cam = None
ld=bpy.data.lights.new("sunv",'SUN'); lo=bpy.data.objects.new("sunv",ld)
sc.collection.objects.link(lo); lo.rotation_euler=(0.9,0.2,0.5); ld.energy=4
w=bpy.data.worlds.new("wv"); sc.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.08,0.08,0.10,1)
cam=setup_cam()
from mathutils import Vector
def look(target, dist, az):
    cam.location=(target[0]+dist*math.sin(az), target[1]-dist*math.cos(az), target[2])
    d=Vector(target)-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
def render_seq(clip, nframes, filepath, cam_fn):
    act=bpy.data.actions[clip]
    arm.animation_data.action=act
    if act.slots: arm.animation_data.action_slot=act.slots[0]
    sc.frame_start=1; sc.frame_end=nframes
    sc.render.filepath=filepath
    for f in range(1,nframes+1):
        sc.frame_set(f)
        cam_fn(f, nframes)
    bpy.ops.render.render(animation=True)
    print("rendered", filepath)
import math as _m
def turn(f,n):
    az = 2*_m.pi*(f-1)/n
    look((0,0,0.95),2.8,az)
render_seq("idle_combat",48,os.path.join(OUT,"turntable_"),turn)
def topdown(f,n):
    cam.location=(1.2,-2.4,2.2)
    d=Vector((0,0,0.9))-cam.location
    cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
render_seq("walk_f",36,os.path.join(OUT,"motion_walk_"),topdown)
# face performance: close-up dialogue
cam2_data=bpy.data.cameras.new("facecam"); cam2=bpy.data.objects.new("facecam",cam2_data)
sc.collection.objects.link(cam2); sc.camera=cam2
def facecam_fn(f,n):
    cam2.location=(0.35,-1.2,1.62)
    d=Vector((0,0,1.62))-cam2.location
    cam2.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
render_seq("dialogue",230,os.path.join(OUT,"face_"),facecam_fn)
print("videos done")

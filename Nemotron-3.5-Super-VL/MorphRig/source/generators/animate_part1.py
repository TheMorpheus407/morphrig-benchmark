#!/usr/bin/env python3
"""MORPHRIG - Author the 96 named animation actions at 30 FPS.
Loads Operative.blend, creates actions on the deformation skeleton + shape keys."""
import bpy, math, importlib.util, sys
from mathutils import Vector, Euler

spec = importlib.util.spec_from_file_location("anim_lib",
    "/home/candidate/workspace/MorphRig/source/generators/anim_lib.py")
anim_lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(anim_lib)
FPS = anim_lib.FPS; RAD = anim_lib.RAD
ARM = anim_lib.ARM

bpy.ops.wm.open_mainfile(filepath=anim_lib.BLEND)
arm = bpy.data.objects[ARM]
for o in bpy.context.view_layer.objects:
    o.select_set(False)
arm.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.context.scene.render.fps = 30
bpy.context.scene.render.fps_base = 1.0

ob_head = bpy.data.objects.get("Head")

def new_action(name):
    return anim_lib.make_action(name)

def frames_for(dur):
    return int(round(dur*FPS))

def pose(arm, f, loc=None, rot=None, scale=None):
    pass

def bone(arm, bname):
    return arm.pose.bones[bname]

def keyb(arm, bname, f, loc=None, rot=None, scale=None):
    pb = bone(arm,bname)
    if loc is not None:
        pb.location = Vector(loc); pb.keyframe_insert("location", frame=f)
    if rot is not None:
        pb.rotation_euler = Euler(rot,'XYZ'); pb.keyframe_insert("rotation_euler", frame=f)
    if scale is not None:
        pb.scale = Vector(scale); pb.keyframe_insert("scale", frame=f)

def keyshape(f, name, value):
    kb = ob_head.data.shape_keys.key_blocks[name]
    kb.value = value; kb.keyframe_insert("value", frame=f)

def zero_all(arm, f):
    for b in arm.pose.bones:
        b.location = Vector((0,0,0)); b.rotation_euler=Euler((0,0,0),'XYZ'); b.scale=Vector((1,1,1))
        b.keyframe_insert("location", frame=f); b.keyframe_insert("rotation_euler", frame=f); b.keyframe_insert("scale", frame=f)
    if ob_head and ob_head.data.shape_keys:
        for kb in ob_head.data.shape_keys.key_blocks:
            kb.value=0.0; kb.keyframe_insert("value", frame=f)

def marker(action, frame, name):
    action.markers.new(name, frame=frame)

def finalize(action, fs, fe, loop):
    action.frame_range[0]=fs; action.frame_range[1]=fe
    for fc in action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation='LINEAR'

ACTIONS = {}

def register(name, action):
    ACTIONS[name]=action
    if arm.animation_data is None:
        arm.animation_data_create()
    # bind last created action for viewing; keep list
    return action

# ============================================================
# IDLE (loops)
# ============================================================
def idle_fn(arm, gtype, dur):
    n = frames_for(dur); fs=0; fe=n
    for f in range(n+1):
        t = f/n
        zero_all(arm, f)
        # breathing
        breath = 0.015*math.sin(2*math.pi*t)
        keyb(arm,"pelvis",f,(0,0,0.95+breath))
        keyb(arm,"head",f,(0,0,breath*0.5))
        keyb(arm,"spine_02",f,(0,0,breath*0.3))
        # subtle weight shift
        shift = 0.02*math.sin(2*math.pi*t*0.5)
        keyb(arm,"spine_03",f,(shift,0,0))
        if gtype=="combat":
            keyb(arm,"upperarm_l",f,(0.0,0.15,0.0)); keyb(arm,"upperarm_r",f,(0.0,-0.15,0.0))
            keyb(arm,"thigh_l",f,(0.03,0,0)); keyb(arm,"thigh_r",f,(-0.03,0,0))
        if gtype=="wounded":
            keyb(arm,"head",f,(0.0,0.02,-0.05))
            keyb(arm,"upperarm_l",f,(0.0,0.0,0.2))  # hold arm
            keyb(arm,"spine_02",f,(0.0,0.0,0.05))
    return fs,fe

def make_idle(name, gtype, dur):
    ac = new_action(name); fs,fe = idle_fn(arm,gtype,dur); finalize(ac,fs,fe,True); register(name,ac)

make_idle("idle_relaxed","relaxed",3.0)
make_idle("idle_combat","combat",3.0)
make_idle("idle_wounded","wounded",3.0)

# ============================================================
# WALK/RUN 8 dirs (loops, in-place)
# ============================================================
DIRS = {
 "walk_f":(0,1,"walk"), "walk_fl":(-0.707,0.707,"walk"), "walk_l":(-1,0,"walk"),
 "walk_bl":(-0.707,-0.707,"walk"), "walk_b":(0,-1,"walk"), "walk_br":(0.707,-0.707,"walk"),
 "walk_r":(1,0,"walk"), "walk_fr":(0.707,0.707,"walk"),
 "run_f":(0,1,"run"), "run_fl":(-0.707,0.707,"run"), "run_l":(-1,0,"run"),
 "run_bl":(-0.707,-0.707,"run"), "run_b":(0,-1,"run"), "run_br":(0.707,-0.707,"run"),
 "run_r":(1,0,"run"), "run_fr":(0.707,0.707,"run"),
}
WALK_DUR = 1.0
RUN_DUR = 0.8
for name,(dx,dy,gtype) in DIRS.items():
    dur = WALK_DUR if gtype=="walk" else RUN_DUR
    n = frames_for(dur); fs=0; fe=n
    ac = new_action(name)
    for f in range(n+1):
        # repeat the gait cycle across n frames (one cycle)
        anim_lib.locomotion_cycle(arm, gtype, (dx,dy), n, loop=True)
    finalize(ac,fs,fe,True); register(name,ac)

# sprint forward
name="sprint_f"; dur=0.7; n=frames_for(dur); fs=0;fe=n
ac=new_action(name)
for f in range(n+1): anim_lib.locomotion_cycle(arm,"sprint",(0,1),n)
finalize(ac,fs,fe,True); register(name,ac)

# ============================================================
# Transitions
# ============================================================
def one_shot_fn(arm, n, fn, fs=0, fe=None):
    if fe is None: fe=n
    ac = bpy.data.actions.new("__tmp")
    for f in range(fs, fe+1):
        fn(arm, f, fs, fe)
    finalize(ac, fs, fe, False)
    return ac

def start_f(arm, f, fs, fe):
    t=(f-fs)/(fe-fs)
    zero_all(arm,f)
    # lean forward then plant
    keyb(arm,"pelvis",f,(0,0.08*t,0.95))
    keyb(arm,"spine_03",f,(0,0,-0.2*t))
    keyb(arm,"thigh_l",f,(0.0,0.12*t,0)); keyb(arm,"thigh_r",f,(0.0,-0.12*t,0))
    keyb(arm,"foot_l",f,(0.0, -0.05*t,0.02)); keyb(arm,"foot_r",f,(0.0,0.05*t,0.02))

def stop_f(arm, f, fs, fe):
    t=(f-fs)/(fe-fs)
    zero_all(arm,f)
    keyb(arm,"pelvis",f,(0,-0.06*t,0.95))
    keyb(arm,"spine_03",f,(0,0,0.25*t))
    keyb(arm,"foot_l",f,(0.0,0.08*t,0.0)); keyb(arm,"foot_r",f,(0.0,-0.08*t,0.0))

def turn(arm, f, fs, fe, sign):
    t=(f-fs)/(fe-fs)
    angle = sign*(90*RAD)*t
    zero_all(arm,f)
    keyb(arm,"root",f,(0,0,0))
    keyb(arm,"pelvis",f,(0,0,0.95))
    keyb(arm,"spine_03",f,(0,0,angle))
    keyb(arm,"head",f,(0,0,angle*0.5))
    # foot placement: pivot on ball
    keyb(arm,"foot_l",f,(0.0,0.0,0.0)); keyb(arm,"foot_r",f,(0.0,0.0,0.0))
    keyb(arm,"thigh_l",f,(0.0,0.1*math.sin(t*math.pi),0)); keyb(arm,"thigh_r",f,(0.0,-0.1*math.sin(t*math.pi),0))

for nm,sign in (("turn_l90",1.0),("turn_r90",-1.0)):
    dur=0.7;n=frames_for(dur);fs=0;fe=n
    ac=bpy.data.actions.new(nm)
    for f in range(fs,fe+1): turn(arm,f,fs,fe,sign)
    finalize(ac,fs,fe,False); register(nm,ac)

def pivot(arm,f,fs,fe,sign):
    t=(f-fs)/(fe-fs)
    angle=sign*(180*RAD)*t
    zero_all(arm,f)
    keyb(arm,"pelvis",f,(0,0.0,0.95))
    keyb(arm,"spine_03",f,(0,0,angle))
    keyb(arm,"head",f,(0,0,angle*0.6))
    # step around
    keyb(arm,"foot_l",f,(0.12*math.sin(t*math.pi),0.0,0.0))
    keyb(arm,"foot_r",f,(-0.12*math.sin(t*math.pi),0.0,0.0))
    keyb(arm,"thigh_l",f,(0.0,0.15*t,0)); keyb(arm,"thigh_r",f,(0.0,-0.15*t,0))

for nm,sign in (("pivot_l180",1.0),("pivot_r180",-1.0)):
    dur=0.7;n=frames_for(dur);fs=0;fe=n
    ac=bpy.data.actions.new(nm)
    for f in range(fs,fe+1): pivot(arm,f,fs,fe,sign)
    finalize(ac,fs,fe,False); register(nm,ac)

# start/stop
for nm,fn in (("start_f",start_f),("stop_f",stop_f)):
    dur=0.6;n=frames_for(dur);fs=0;fe=n
    ac=bpy.data.actions.new(nm)
    for f in range(fs,fe+1): fn(arm,f,fs,fe)
    finalize(ac,fs,fe,False); register(nm,ac)

print("Locomotion + transitions done:", len(ACTIONS)+8)
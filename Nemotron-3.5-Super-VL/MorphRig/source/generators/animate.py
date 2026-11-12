#!/usr/bin/env python3
"""MORPHRIG - Author all 96 named animation actions at 30 FPS on deform skeleton + shape keys.
Blender 5.1: keyframes are recorded into the active armature action; markers stored as custom props."""
import bpy, math, json
from mathutils import Vector, Euler

BLEND = "/home/candidate/workspace/MorphRig/source/Operative.blend"
FPS = 30.0; RAD = math.pi/180.0

bpy.ops.wm.open_mainfile(filepath=BLEND)
arm = bpy.data.objects["Operative_Armature"]
arm.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
bpy.context.scene.render.fps = 30; bpy.context.scene.render.fps_base = 1.0
ob_head = bpy.data.objects.get("Head")

def bone(arm,bname): return arm.pose.bones[bname]
ALL_BONES = [b.name for b in arm.pose.bones]

def new_action(name):
    if name in bpy.data.actions: bpy.data.actions.remove(bpy.data.actions[name])
    a = bpy.data.actions.new(name)
    a.use_fake_user = True
    targets = [arm, ob_head] + [o for o in bpy.data.objects if o.type=='MESH' and o.users_collection and any(c.name=="Props" for c in o.users_collection)]
    for t in targets:
        if t.animation_data is None: t.animation_data_create()
        t.animation_data.action = a
    return a
def keyb(arm,bname,f,loc=None,rot=None):
    pb=bone(arm,bname)
    if loc is not None: pb.location=Vector(loc); pb.keyframe_insert("location",frame=f)
    if rot is not None: pb.rotation_euler=Euler(rot,'XYZ'); pb.keyframe_insert("rotation_euler",frame=f)
def keyshape(f,name,value):
    kb=ob_head.data.shape_keys.key_blocks[name]; kb.value=value; kb.keyframe_insert("value",frame=f)
def rest_all(arm,f):
    for bn in ALL_BONES:
        pb=bone(arm,bn)
        pb.location=Vector((0,0,0)); pb.rotation_euler=Euler((0,0,0),'XYZ')
        pb.keyframe_insert("location",frame=f); pb.keyframe_insert("rotation_euler",frame=f)
    if ob_head and ob_head.data.shape_keys:
        for kb in ob_head.data.shape_keys.key_blocks:
            kb.value=0.0; kb.keyframe_insert("value",frame=f)
def marker(ac,f,name):
    ms = json.loads(ac.get("markers_json","[]"))
    ms=[m for m in ms if m[0]!=f]
    ms.append([f,name]); ac["markers_json"]=json.dumps(ms)
def finalize(ac,fs,fe,loop):
    ac.frame_start=float(fs); ac.frame_end=float(fe); ac.frame_range=(float(fs),float(fe))
REG={}
def reg(name,ac): REG[name]=ac
def frames(dur): return int(round(dur*FPS))

# ================================================================ IDLE
def idle(gtype,dur):
    n=frames(dur); fs=0; fe=n; ac=new_action("idle_"+gtype)
    rest_all(arm,fs)
    for f in range(n+1):
        t=f/n; breath=0.015*math.sin(2*math.pi*t)
        keyb(arm,"pelvis",f,(0,0,0.95+breath)); keyb(arm,"head",f,(0,0,breath*0.5))
        keyb(arm,"spine_02",f,(0,0,breath*0.3)); sh=0.02*math.sin(2*math.pi*t*0.5)
        keyb(arm,"spine_03",f,(sh,0,0))
        if gtype=="combat":
            keyb(arm,"upperarm_l",f,(0.0,0.15,0.0)); keyb(arm,"upperarm_r",f,(0.0,-0.15,0.0))
            keyb(arm,"thigh_l",f,(0.03,0,0)); keyb(arm,"thigh_r",f,(-0.03,0,0))
        elif gtype=="wounded":
            keyb(arm,"head",f,(0.0,0.02,-0.06)); keyb(arm,"upperarm_l",f,(0.0,0.0,0.25))
            keyb(arm,"spine_02",f,(0.0,0.0,0.06)); keyb(arm,"thigh_l",f,(0.0,0.0,0.08))
    finalize(ac,fs,fe,True); reg("idle_"+gtype,ac)
for g in ("relaxed","combat","wounded"): idle(g,3.0)

# ================================================================ LOCOMOTION
GAIT={"walk":{"bob":0.028,"swing":0.17,"knee":38},"run":{"bob":0.055,"swing":0.26,"knee":60},"sprint":{"bob":0.09,"swing":0.34,"knee":75}}
DIRS={"walk_f":(0,1,"walk"),"walk_fl":(-0.707,0.707,"walk"),"walk_l":(-1,0,"walk"),
 "walk_bl":(-0.707,-0.707,"walk"),"walk_b":(0,-1,"walk"),"walk_br":(0.707,-0.707,"walk"),
 "walk_r":(1,0,"walk"),"walk_fr":(0.707,0.707,"walk"),
 "run_f":(0,1,"run"),"run_fl":(-0.707,0.707,"run"),"run_l":(-1,0,"run"),
 "run_bl":(-0.707,-0.707,"run"),"run_b":(0,-1,"run"),"run_br":(0.707,-0.707,"run"),
 "run_r":(1,0,"run"),"run_fr":(0.707,0.707,"run")}
for name,(dx,dy,g) in DIRS.items():
    dur=1.0 if g=="walk" else 0.8; n=frames(dur); fs=0;fe=n; ac=new_action(name)
    rest_all(arm,fs)
    for f in range(n+1):
        phase=f/n*2*math.pi; g2=GAIT[g]; bob=abs(math.sin(phase))*g2["bob"]
        keyb(arm,"pelvis",f,(0,0,0.95+bob)); keyb(arm,"spine_01",f,(0,0,0.05*math.sin(phase)))
        lean=0.13*dx; keyb(arm,"spine_03",f,(0,0,lean)); keyb(arm,"neck",f,(0,0,-lean*0.5))
        sw=0.27*math.sin(phase)
        keyb(arm,"upperarm_l",f,(0,sw*0.6,-sw*0.4)); keyb(arm,"lowerarm_l",f,(0,0,sw*0.5))
        keyb(arm,"upperarm_r",f,(0,-sw*0.6,sw*0.4)); keyb(arm,"lowerarm_r",f,(0,0,-sw*0.5))
        for side,off in (("l",0.0),("r",math.pi)):
            p=phase+off
            keyb(arm,"thigh_"+side,f,(g2["swing"]*math.sin(p),0.0,0.0))
            kn=g2["knee"]*RAD*max(0.0,math.sin(p)); keyb(arm,"shin_"+side,f,(kn,0.0,0.0))
            lift=g2["swing"]*0.5*max(0.0,math.sin(p)) if math.sin(p)>0 else 0.0
            keyb(arm,"foot_"+side,f,((0.09 if side=="l" else -0.09),g2["swing"]*0.6*math.sin(p),-lift))
            keyb(arm,"foot_"+side,f,(-kn*0.5,0.0,0.0))
            keyb(arm,"toe_"+side,f,(0.0,0.0,0.0))
        keyb(arm,"head",f,(0,0,0.03*bob))
    finalize(ac,fs,fe,True); reg(name,ac)
n=frames(0.7);fs=0;fe=n;ac=new_action("sprint_f")
rest_all(arm,fs)
for f in range(n+1):
    phase=f/n*2*math.pi; g2=GAIT["sprint"]; bob=abs(math.sin(phase))*g2["bob"]
    keyb(arm,"pelvis",f,(0,0,0.95+bob)); keyb(arm,"spine_03",f,(0,0,0.1))
    sw=0.4*math.sin(phase)
    keyb(arm,"upperarm_l",f,(0,sw*0.7,-sw*0.5)); keyb(arm,"upperarm_r",f,(0,-sw*0.7,sw*0.5))
    for side,off in (("l",0.0),("r",math.pi)):
        p=phase+off; kn=g2["knee"]*RAD*max(0.0,math.sin(p))
        keyb(arm,"thigh_"+side,f,(g2["swing"]*math.sin(p),0.0,0.0)); keyb(arm,"shin_"+side,f,(kn,0.0,0.0))
        lift=g2["swing"]*0.7*max(0.0,math.sin(p)) if math.sin(p)>0 else 0.0
        keyb(arm,"foot_"+side,f,((0.09 if side=="l" else -0.09),g2["swing"]*0.8*math.sin(p),-lift))
    keyb(arm,"head",f,(0,0,0.05*bob))
finalize(ac,fs,fe,True); reg("sprint_f",ac)

# ================================================================ TRANSITIONS
def base_move(arm,f): keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"head",f,(0,0,0))
def start_f(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0.1*t,0.95)); keyb(arm,"spine_03",f,(0,0,-0.25*t))
    keyb(arm,"thigh_l",f,(0.0,0.14*t,0.0)); keyb(arm,"thigh_r",f,(0.0,-0.14*t,0.0))
def stop_f(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,-0.07*t,0.95)); keyb(arm,"spine_03",f,(0,0,0.3*t))
    keyb(arm,"foot_l",f,(0.0,0.09*t,0.0)); keyb(arm,"foot_r",f,(0.0,-0.09*t,0.0))
def turn(arm,f,fs,fe,sign):
    base_move(arm,f); t=(f-fs)/(fe-fs); ang=sign*(90*RAD)*t
    keyb(arm,"spine_03",f,(0,0,ang)); keyb(arm,"head",f,(0,0,ang*0.5))
    keyb(arm,"thigh_l",f,(0.0,0.12*math.sin(t*math.pi),0.0)); keyb(arm,"thigh_r",f,(0.0,-0.12*math.sin(t*math.pi),0.0))
def pivot(arm,f,fs,fe,sign):
    base_move(arm,f); t=(f-fs)/(fe-fs); ang=sign*(180*RAD)*t
    keyb(arm,"spine_03",f,(0,0,ang)); keyb(arm,"head",f,(0,0,ang*0.6))
    keyb(arm,"foot_l",f,(0.14*math.sin(t*math.pi),0.0,0.0)); keyb(arm,"foot_r",f,(-0.14*math.sin(t*math.pi),0.0,0.0))
    keyb(arm,"thigh_l",f,(0.0,0.16*t,0.0)); keyb(arm,"thigh_r",f,(0.0,-0.16*t,0.0))
def oneshot(name,dur,fn,markers=None):
    n=frames(dur);fs=0;fe=n;ac=new_action(name); rest_all(arm,fs)
    for f in range(fs,fe+1): fn(arm,f,fs,fe)
    if markers:
        for fr,nm in markers: marker(ac,fr,nm)
    finalize(ac,fs,fe,False); reg(name,ac)
oneshot("start_f",0.6,start_f)
oneshot("stop_f",0.6,stop_f)
oneshot("turn_l90",0.7,lambda a,f,s,e: turn(a,f,s,e,1.0))
oneshot("turn_r90",0.7,lambda a,f,s,e: turn(a,f,s,e,-1.0))
oneshot("pivot_l180",0.7,lambda a,f,s,e: pivot(a,f,s,e,1.0))
oneshot("pivot_r180",0.7,lambda a,f,s,e: pivot(a,f,s,e,-1.0))

# ================================================================ JUMP/FALL
def jump_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95-0.12*(1-t))); keyb(arm,"spine_03",f,(0,0,-0.2*t))
    keyb(arm,"thigh_l",f,(0.2*t,0.0,0.0)); keyb(arm,"thigh_r",f,(0.2*t,0.0,0.0))
    keyb(arm,"shin_l",f,(-0.5*t,0.0,0.0)); keyb(arm,"shin_r",f,(-0.5*t,0.0,0.0))
    if t>0.6: keyb(arm,"foot_l",f,(0.0,0.0,0.18*t)); keyb(arm,"foot_r",f,(0.0,0.0,0.18*t))
def jump_air(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95+0.35*math.sin(t*math.pi)))
    keyb(arm,"spine_03",f,(0,0,-0.1)); keyb(arm,"head",f,(0,0,-0.05))
    keyb(arm,"thigh_l",f,(0.25,0.0,0.0)); keyb(arm,"thigh_r",f,(0.25,0.0,0.0))
    keyb(arm,"shin_l",f,(-0.6,0.0,0.0)); keyb(arm,"shin_r",f,(-0.6,0.0,0.0))
    keyb(arm,"foot_l",f,(0.0,0.0,0.22)); keyb(arm,"foot_r",f,(0.0,0.0,0.22))
    keyb(arm,"upperarm_l",f,(0.2,0.0,0.0)); keyb(arm,"upperarm_r",f,(0.2,0.0,0.0))
def jump_land(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    comp=0.18*(1-t) if t<0.5 else 0.0
    keyb(arm,"pelvis",f,(0,0,0.95-comp)); keyb(arm,"spine_03",f,(0,0,0.2*t))
    keyb(arm,"thigh_l",f,(0.0,0.1*t,0.0)); keyb(arm,"thigh_r",f,(0.0,-0.1*t,0.0))
    keyb(arm,"shin_l",f,(0.3*t,0.0,0.0)); keyb(arm,"shin_r",f,(0.3*t,0.0,0.0))
def fall(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"spine_03",f,(0,0,0.15*math.sin(t*math.pi)))
    keyb(arm,"head",f,(0,0.05,0)); keyb(arm,"upperarm_l",f,(0.3,0.0,0.2))
    keyb(arm,"upperarm_r",f,(0.3,0.0,-0.2)); keyb(arm,"thigh_l",f,(0.2,0.0,0.0))
    keyb(arm,"thigh_r",f,(0.2,0.0,0.0)); keyb(arm,"shin_l",f,(-0.4,0.0,0.0))
    keyb(arm,"shin_r",f,(-0.4,0.0,0.0)); keyb(arm,"foot_l",f,(0.0,0.0,0.15))
    keyb(arm,"foot_r",f,(0.0,0.0,0.15))
def land_heavy(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    comp=0.32*(1-t) if t<0.4 else 0.0
    keyb(arm,"pelvis",f,(0,0,0.95-comp)); keyb(arm,"spine_03",f,(0,0,0.25*t))
    keyb(arm,"head",f,(0,0.03,-0.05*t)); keyb(arm,"thigh_l",f,(0.05,0.12*t,0.0))
    keyb(arm,"thigh_r",f,(0.05,-0.12*t,0.0)); keyb(arm,"shin_l",f,(0.4*t,0.0,0.0))
    keyb(arm,"shin_r",f,(0.4*t,0.0,0.0))
oneshot("jump_start",0.7,jump_start)
oneshot("jump_land",0.7,jump_land)
oneshot("land_heavy",0.7,land_heavy)
n=frames(0.8);fs=0;fe=n;ac=new_action("jump_air"); rest_all(arm,fs)
for f in range(fs,fe+1): jump_air(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("jump_air",ac)
n=frames(0.8);fs=0;fe=n;ac=new_action("fall"); rest_all(arm,fs)
for f in range(fs,fe+1): fall(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("fall",ac)

# ================================================================ DASH (root motion 2m)
def dash(arm,f,fs,fe,axis):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    et=t*t*(3-2*t); dist=2.0*et
    if axis=="f": keyb(arm,"root",f,(0,dist,0))
    elif axis=="b": keyb(arm,"root",f,(0,-dist,0))
    elif axis=="l": keyb(arm,"root",f,(-dist,0,0))
    elif axis=="r": keyb(arm,"root",f,(dist,0,0))
    keyb(arm,"spine_03",f,(0,0,-0.15*t))
    keyb(arm,"thigh_l",f,(0.15,0.0,0.0)); keyb(arm,"thigh_r",f,(0.15,0.0,0.0))
    keyb(arm,"shin_l",f,(-0.4,0.0,0.0)); keyb(arm,"shin_r",f,(-0.4,0.0,0.0))
    keyb(arm,"foot_l",f,(0.0,0.0,0.05)); keyb(arm,"foot_r",f,(0.0,0.0,0.05))
for ax in ("f","b","l","r"):
    oneshot("dash_"+ax,0.45,lambda a,f,s,e,ax=ax: dash(a,f,s,e,ax))

# ================================================================ BLINK
def blink_out(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"spine_03",f,(0,0,-0.2*t)); keyb(arm,"head",f,(0,0,-0.1*t))
    keyb(arm,"upperarm_l",f,(0.3,0.0,0.2)); keyb(arm,"upperarm_r",f,(0.3,0.0,-0.2))
    keyshape(f,"blink_L",min(1.0,t/0.4)); keyshape(f,"blink_R",min(1.0,t/0.4))
def blink_in(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"spine_03",f,(0,0,0.2*(1-t))); keyb(arm,"head",f,(0,0,0.1*(1-t)))
    keyshape(f,"blink_L",1.0-min(1.0,t/0.4)); keyshape(f,"blink_R",1.0-min(1.0,t/0.4))
oneshot("blink_out",0.4,blink_out)
oneshot("blink_in",0.4,blink_in)

# ================================================================ MELEE
def melee(arm,f,fs,fe,style):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    if t<0.25:
        w=t/0.25
        keyb(arm,"upperarm_r",f,(0.0,0.0,0.5*w)); keyb(arm,"lowerarm_r",f,(0.0,0.0,-1.2*w))
        keyb(arm,"spine_03",f,(0,0,0.2*w))
    elif t<0.55:
        w=(t-0.25)/0.3
        keyb(arm,"upperarm_r",f,(0.0,0.0,0.5-1.6*w)); keyb(arm,"lowerarm_r",f,(0.0,0.0,-1.2+2.6*w))
        keyb(arm,"spine_03",f,(0,0,0.2-0.4*w))
    else:
        w=(t-0.55)/0.45
        keyb(arm,"upperarm_r",f,(0.0,0.0,-1.1+1.1*w)); keyb(arm,"lowerarm_r",f,(0.0,0.0,1.4-1.4*w))
        keyb(arm,"spine_03",f,(0,0,-0.2+0.2*w))
    if style==2: keyb(arm,"spine_03",f,(0,0,-0.2*t))
    elif style==3: keyb(arm,"pelvis",f,(0,0.05*math.sin(t*math.pi),0.95))
oneshot("melee_1",0.8,lambda a,f,s,e: melee(a,f,s,e,1),markers=[(int(0.35*FPS),"melee_hit_1"),(int(0.75*FPS),"recover_1")])
oneshot("melee_2",0.9,lambda a,f,s,e: melee(a,f,s,e,2),markers=[(int(0.4*FPS),"melee_hit_2"),(int(0.8*FPS),"recover_2")])
oneshot("melee_3",1.0,lambda a,f,s,e: melee(a,f,s,e,3),markers=[(int(0.5*FPS),"melee_hit_3"),(int(0.9*FPS),"recover_3")])

# ================================================================ RANGED
def ranged_fire(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,0.2*t)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.5*t))
    keyb(arm,"spine_03",f,(0,0,0.1*math.sin(t*math.pi)))
    if t<0.3: keyb(arm,"head",f,(0,0.02,-0.05))
oneshot("ranged_fire",0.35,ranged_fire,markers=[(int(0.15*FPS),"muzzle_1")])
def ranged_burst(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,0.2*t)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.5*t))
    keyb(arm,"spine_03",f,(0,0,0.12*math.sin(t*math.pi)))
    keyb(arm,"head",f,(0,0.01,-0.03*t))
oneshot("ranged_burst",0.6,ranged_burst,markers=[(int(0.15*FPS),"muzzle_1"),(int(0.35*FPS),"muzzle_2"),(int(0.55*FPS),"muzzle_3")])

# ================================================================ RELOAD
def reload(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.2,0.1*t)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.8*t))
    keyb(arm,"hand_l",f,(0.0,0.1*t,0.0)); keyb(arm,"upperarm_r",f,(0.0,-0.1,0.0))
    keyb(arm,"spine_03",f,(0,0,0.05*t))
oneshot("reload",1.6,reload,markers=[(int(0.5*FPS),"cell_remove"),(int(1.1*FPS),"cell_insert"),(int(1.5*FPS),"reload_complete")])

# ================================================================ CASTS
def cast_directional(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,-0.4*t)); keyb(arm,"upperarm_r",f,(0.0,0.0,-0.4*t))
    keyb(arm,"spine_03",f,(0,0,0.1*math.sin(t*math.pi))); keyb(arm,"head",f,(0,0.03,0.0))
oneshot("cast_directional",0.7,cast_directional,markers=[(int(0.55*FPS),"cast_release")])
def cast_ground(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,-0.5*t)); keyb(arm,"upperarm_r",f,(0.0,0.0,-0.5*t))
    keyb(arm,"head",f,(0,-0.05,0.0))
oneshot("cast_ground",1.0,cast_ground,markers=[(int(0.8*FPS),"cast_release")])
def cast_self(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.25*t,0.0)); keyb(arm,"upperarm_r",f,(0.0,0.25*t,0.0))
    keyshape(f,"jaw_open",0.4*math.sin(t*math.pi))
oneshot("cast_self",0.7,cast_self)

# ================================================================ CHANNEL
def channel_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.2*t,0.0)); keyb(arm,"upperarm_r",f,(0.0,0.2*t,0.0))
oneshot("channel_start",0.5,channel_start)
def channel_loop(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95+0.01*math.sin(2*math.pi*t)))
    keyb(arm,"upperarm_l",f,(0.0,0.18,0.0)); keyb(arm,"upperarm_r",f,(0.0,0.18,0.0))
    keyshape(f,"jaw_open",0.15+0.05*math.sin(2*math.pi*t))
n=frames(1.2);fs=0;fe=n;ac=new_action("channel_loop"); rest_all(arm,fs)
for f in range(fs,fe+1): channel_loop(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("channel_loop",ac)
def channel_end(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.18*(1-t),0.0)); keyb(arm,"upperarm_r",f,(0.0,0.18*(1-t),0.0))
    keyshape(f,"jaw_open",0.2*(1-t))
oneshot("channel_end",0.5,channel_end)
def channel_interrupt(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.18*(1-t),0.0)); keyb(arm,"upperarm_r",f,(0.0,0.18*(1-t),0.0))
    keyb(arm,"spine_03",f,(0,0,0.15*t)); keyb(arm,"head",f,(0,0.05,0.0))
oneshot("channel_interrupt",0.4,channel_interrupt)

# ================================================================ CHARGE
def charge_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,-0.3*t)); keyb(arm,"upperarm_r",f,(0.0,0.0,-0.3*t))
    keyb(arm,"spine_03",f,(0,0,0.05*t)); keyshape(f,"jaw_open",0.2*t)
oneshot("charge_start",0.6,charge_start)
def charge_hold(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95+0.01*math.sin(2*math.pi*t)))
    keyb(arm,"upperarm_l",f,(0.0,0.0,-0.3)); keyb(arm,"upperarm_r",f,(0.0,0.0,-0.3))
    keyshape(f,"jaw_open",0.25+0.05*math.sin(2*math.pi*t))
n=frames(1.0);fs=0;fe=n;ac=new_action("charge_hold"); rest_all(arm,fs)
for f in range(fs,fe+1): charge_hold(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("charge_hold",ac)
def charge_release(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,-0.4*t,0.0)); keyb(arm,"upperarm_r",f,(0.0,-0.4*t,0.0))
    keyb(arm,"spine_03",f,(0,0,-0.1*t)); keyb(arm,"pelvis",f,(0,0.1*t,0.95))
oneshot("charge_release",0.5,charge_release)
def charge_cancel(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,-0.3*(1-t))); keyb(arm,"upperarm_r",f,(0.0,0.0,-0.3*(1-t)))
    keyshape(f,"jaw_open",0.25*(1-t))
oneshot("charge_cancel",0.5,charge_cancel)

# ================================================================ DEPLOY / UPLINK
def deploy(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.25*t,0.0)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.8*t))
    keyb(arm,"hand_l",f,(0.0,0.2*t,0.0)); keyb(arm,"spine_03",f,(0,0,0.05*t))
oneshot("deploy",1.2,deploy,markers=[(int(0.9*FPS),"deploy_attach")])
def uplink(arm,f,fs,fe,mode):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.2,0.1*t)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.6*t))
    keyb(arm,"hand_l",f,(0.0,0.2,0.0))
    if mode=="loop": keyshape(f,"jaw_open",0.1+0.05*math.sin(2*math.pi*t))
def uplink_start(arm,f,fs,fe): uplink(arm,f,fs,fe,"start")
def uplink_loop(arm,f,fs,fe): uplink(arm,f,fs,fe,"loop")
def uplink_end(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"hand_l",f,(0.0,0.2*(1-t),0.0)); keyshape(f,"smile",0.6*t)
def uplink_cancel(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"hand_l",f,(0.0,0.2*(1-t),0.0))
oneshot("uplink_start",0.7,uplink_start)
n=frames(1.5);fs=0;fe=n;ac=new_action("uplink_loop"); rest_all(arm,fs)
for f in range(fs,fe+1): uplink_loop(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("uplink_loop",ac)
oneshot("uplink_end",0.5,uplink_end)
oneshot("uplink_cancel",0.5,uplink_cancel)

# ================================================================ HIT
def hit(arm,f,fs,fe,dirv):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    kx,ky=dirv; jerk=0.25*(1-t)
    keyb(arm,"spine_02",f,(kx*jerk,ky*jerk,0.0))
    keyb(arm,"spine_03",f,(kx*jerk*0.6,ky*jerk*0.6,0.0))
    keyb(arm,"head",f,(kx*jerk*0.5,ky*jerk*0.5,-0.05*t))
    keyb(arm,"upperarm_l",f,(0.0,0.1*t,0.0)); keyb(arm,"upperarm_r",f,(0.0,-0.1*t,0.0))
for nm,d in (("hit_f",(0,-1,0)),("hit_b",(0,1,0)),("hit_l",(-1,0,0)),("hit_r",(1,0,0))):
    oneshot(nm,0.3,lambda a,f,s,e,d=d: hit(a,f,s,e,(d[0],d[1])))

# ================================================================ STUN
def stun_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95-0.05*t)); keyb(arm,"spine_03",f,(0,0,0.2*t))
    keyb(arm,"head",f,(0,0.05,0.1*t)); keyb(arm,"upperarm_l",f,(0.4,0.0,0.3))
    keyb(arm,"upperarm_r",f,(0.4,0.0,-0.3)); keyb(arm,"thigh_l",f,(0.2,0.0,0.0))
    keyb(arm,"thigh_r",f,(0.2,0.0,0.0)); keyshape(f,"jaw_open",0.3*t)
def stun_loop(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.9+0.03*math.sin(2*math.pi*t)))
    keyb(arm,"spine_03",f,(0.05*math.sin(2*math.pi*t),0,0.25))
    keyb(arm,"head",f,(0.05*math.sin(2*math.pi*t),0.05,0.1))
    keyb(arm,"upperarm_l",f,(0.5,0.0,0.4*math.sin(2*math.pi*t)))
    keyb(arm,"upperarm_r",f,(0.5,0.0,-0.4*math.sin(2*math.pi*t)))
    keyshape(f,"jaw_open",0.2+0.1*math.sin(2*math.pi*t))
def stun_end(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.9+0.05*t)); keyb(arm,"spine_03",f,(0.05*(1-t),0,0.25*(1-t)))
    keyb(arm,"head",f,(0.05*(1-t),0.0,0.1*(1-t)))
    keyb(arm,"upperarm_l",f,(0.5*(1-t),0.0,0.2)); keyb(arm,"upperarm_r",f,(0.5*(1-t),0.0,-0.2))
    keyshape(f,"jaw_open",0.3*(1-t))
oneshot("stun_start",0.8,stun_start)
n=frames(1.2);fs=0;fe=n;ac=new_action("stun_loop"); rest_all(arm,fs)
for f in range(fs,fe+1): stun_loop(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("stun_loop",ac)
oneshot("stun_end",0.8,stun_end)

# ================================================================ KNOCKBACK / KNOCKUP
def knockback(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,1.5*t,0))
    keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"spine_03",f,(0,0,0.15*t))
    keyb(arm,"head",f,(0,0.05,-0.05*t)); keyb(arm,"upperarm_l",f,(0.3,0.0,0.2))
    keyb(arm,"upperarm_r",f,(0.3,0.0,-0.2)); keyshape(f,"jaw_open",0.2*t)
oneshot("knockback",1.0,knockback)
def knockup_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,3.0*t))
    keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"spine_03",f,(0,0,-0.1*t))
    keyb(arm,"head",f,(0,0.05,0.0)); keyb(arm,"upperarm_l",f,(0.2,0.0,0.3))
    keyb(arm,"upperarm_r",f,(0.2,0.0,-0.3)); keyb(arm,"thigh_l",f,(0.3,0.0,0.0))
    keyb(arm,"thigh_r",f,(0.3,0.0,0.0)); keyb(arm,"shin_l",f,(-0.5,0.0,0.0))
    keyb(arm,"shin_r",f,(-0.5,0.0,0.0))
oneshot("knockup_start",0.8,knockup_start)
def knockup_air(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"spine_03",f,(0,0,-0.1))
    keyb(arm,"head",f,(0,0.05,0.0)); keyb(arm,"upperarm_l",f,(0.4,0.0,0.4))
    keyb(arm,"upperarm_r",f,(0.4,0.0,-0.4)); keyb(arm,"thigh_l",f,(0.4,0.0,0.0))
    keyb(arm,"thigh_r",f,(0.4,0.0,0.0)); keyb(arm,"shin_l",f,(-0.6,0.0,0.0))
    keyb(arm,"shin_r",f,(-0.6,0.0,0.0)); keyshape(f,"jaw_open",0.3)
n=frames(1.0);fs=0;fe=n;ac=new_action("knockup_air"); rest_all(arm,fs)
for f in range(fs,fe+1): knockup_air(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("knockup_air",ac)

# ================================================================ KNOCKDOWN / PRONE / GETUP
def knockdown_front(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*(1-t))); keyb(arm,"pelvis",f,(0,0,0.35*t))
    keyb(arm,"spine_03",f,(0,0,0.3*t)); keyb(arm,"head",f,(0,0.05,-0.2*t))
    keyb(arm,"thigh_l",f,(0.3*t,0.0,0.0)); keyb(arm,"thigh_r",f,(0.3*t,0.0,0.0))
    keyb(arm,"shin_l",f,(-0.2*t,0.0,0.0)); keyb(arm,"shin_r",f,(-0.2*t,0.0,0.0))
def knockdown_back(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*(1-t))); keyb(arm,"pelvis",f,(0,0,0.35*t))
    keyb(arm,"spine_03",f,(0,0,-0.25*t)); keyb(arm,"head",f,(0,-0.05,0.2*t))
    keyb(arm,"thigh_l",f,(-0.3*t,0.0,0.0)); keyb(arm,"thigh_r",f,(-0.3*t,0.0,0.0))
    keyb(arm,"shin_l",f,(0.2*t,0.0,0.0)); keyb(arm,"shin_r",f,(0.2*t,0.0,0.0))
def prone(arm,f,fs,fe,face_down):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.0)); keyb(arm,"pelvis",f,(0,0,0.12))
    keyb(arm,"spine_03",f,(0,0,0.25 if face_down else -0.2))
    keyb(arm,"head",f,(0,0.05 if face_down else -0.05, -0.15 if face_down else 0.15))
    keyb(arm,"upperarm_l",f,(0.5,0.0,0.2)); keyb(arm,"upperarm_r",f,(0.5,0.0,-0.2))
    keyb(arm,"thigh_l",f,(0.3,0.0,0.0)); keyb(arm,"thigh_r",f,(0.3,0.0,0.0))
    keyshape(f,"jaw_open",0.05+0.05*math.sin(2*math.pi*t))
def getup(arm,f,fs,fe,face_down):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*t)); keyb(arm,"pelvis",f,(0,0,0.35*(1-t)+0.95*t))
    keyb(arm,"spine_03",f,(0,0,(0.25 if face_down else -0.2)*(1-t)))
    keyb(arm,"head",f,(0,0.05*(1-t), -0.15*(1-t) if face_down else 0.15*(1-t)))
    keyb(arm,"upperarm_l",f,(0.5*(1-t),0.0,0.2*(1-t))); keyb(arm,"upperarm_r",f,(0.5*(1-t),0.0,-0.2*(1-t)))
    keyb(arm,"thigh_l",f,(0.3*(1-t),0.0,0.0)); keyb(arm,"thigh_r",f,(0.3*(1-t),0.0,0.0))
oneshot("knockdown_front",1.0,knockdown_front)
oneshot("knockdown_back",1.0,knockdown_back)
n=frames(1.2);fs=0;fe=n;ac=new_action("prone_front"); rest_all(arm,fs)
for f in range(fs,fe+1): prone(arm,f,fs,fe,True)
finalize(ac,fs,fe,True); reg("prone_front",ac)
n=frames(1.2);fs=0;fe=n;ac=new_action("prone_back"); rest_all(arm,fs)
for f in range(fs,fe+1): prone(arm,f,fs,fe,False)
finalize(ac,fs,fe,True); reg("prone_back",ac)
oneshot("getup_front",1.2,lambda a,f,s,e: getup(a,f,s,e,True))
oneshot("getup_back",1.2,lambda a,f,s,e: getup(a,f,s,e,False))

# ================================================================ SLEEP
def sleep_start(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*(1-t))); keyb(arm,"pelvis",f,(0,0,0.12))
    keyb(arm,"spine_03",f,(0,0,0.3*t)); keyb(arm,"head",f,(0,0.05,-0.2*t))
    keyshape(f,"jaw_open",0.05*(1-t)); keyshape(f,"blink_L",t); keyshape(f,"blink_R",t)
def sleep_loop(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.12+0.005*math.sin(2*math.pi*t)))
    keyb(arm,"spine_03",f,(0,0,0.3)); keyshape(f,"blink_L",0.9); keyshape(f,"blink_R",0.9)
    keyshape(f,"jaw_open",0.03)
def sleep_end(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*t)); keyb(arm,"pelvis",f,(0,0,0.12*(1-t)+0.95*t))
    keyb(arm,"spine_03",f,(0,0,0.3*(1-t))); keyb(arm,"head",f,(0,0.05*(1-t),-0.2*(1-t)))
    keyshape(f,"blink_L",1.0-t); keyshape(f,"blink_R",1.0-t)
    keyshape(f,"jaw_open",0.1*t)
oneshot("sleep_start",1.0,sleep_start)
n=frames(1.2);fs=0;fe=n;ac=new_action("sleep_loop"); rest_all(arm,fs)
for f in range(fs,fe+1): sleep_loop(arm,f,fs,fe)
finalize(ac,fs,fe,True); reg("sleep_loop",ac)
oneshot("sleep_end",1.0,sleep_end)

# ================================================================ DEATH / RESPAWN
def death(arm,f,fs,fe,back):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*(1-t))); keyb(arm,"pelvis",f,(0,0,0.10))
    if back:
        keyb(arm,"spine_03",f,(0,0,-0.3*t)); keyb(arm,"head",f,(0,-0.05,0.3*t))
        keyb(arm,"thigh_l",f,(-0.25*t,0.0,0.0)); keyb(arm,"thigh_r",f,(-0.25*t,0.0,0.0))
        keyb(arm,"upperarm_l",f,(0.5*t,0.0,0.1)); keyb(arm,"upperarm_r",f,(0.5*t,0.0,-0.1))
    else:
        keyb(arm,"spine_03",f,(0,0,0.3*t)); keyb(arm,"head",f,(0,0.05,-0.3*t))
        keyb(arm,"thigh_l",f,(0.25*t,0.0,0.0)); keyb(arm,"thigh_r",f,(0.25*t,0.0,0.0))
        keyb(arm,"upperarm_l",f,(0.5*t,0.0,-0.2)); keyb(arm,"upperarm_r",f,(0.5*t,0.0,0.2))
    keyshape(f,"jaw_open",0.15*min(1.0,t/0.7))
def respawn(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"root",f,(0,0,0.95*t)); keyb(arm,"pelvis",f,(0,0,0.10*(1-t)+0.95*t))
    keyb(arm,"spine_03",f,(0,0,-0.3*(1-t))); keyb(arm,"head",f,(0,-0.05*(1-t),0.3*(1-t)))
    keyb(arm,"upperarm_l",f,(0.5*(1-t),0.0,0.1)); keyb(arm,"upperarm_r",f,(0.5*(1-t),0.0,-0.1))
    keyb(arm,"thigh_l",f,(0.25*(1-t),0.0,0.0)); keyb(arm,"thigh_r",f,(0.25*(1-t),0.0,0.0))
    keyshape(f,"jaw_open",0.15*(1-t))
oneshot("death_front",1.8,lambda a,f,s,e: death(a,f,s,e,False),markers=[(frames(1.6),"death_settle")])
oneshot("death_back",1.8,lambda a,f,s,e: death(a,f,s,e,True),markers=[(frames(1.6),"death_settle")])
oneshot("respawn",2.0,respawn)

# ================================================================ GREET / VICTORY / DEFEAT
def greet(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.25*t,0.0)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.9*t))
    keyb(arm,"hand_l",f,(0.0,0.25*t,0.0)); keyb(arm,"spine_03",f,(0,0,0.05*t))
    keyb(arm,"head",f,(0,0.02,0.0)); keyshape(f,"smile",0.5*t)
oneshot("greet",1.8,greet)
def victory(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.3,0.2*t)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.6*t))
    keyb(arm,"upperarm_r",f,(0.0,0.3,-0.2*t)); keyb(arm,"lowerarm_r",f,(0.0,0.0,0.6*t))
    keyb(arm,"spine_03",f,(0,0,0.1*t)); keyb(arm,"head",f,(0,0.05,0.0))
    keyshape(f,"smile",0.7*t); keyshape(f,"brow_raise_L",0.3*t); keyshape(f,"brow_raise_R",0.3*t)
oneshot("victory",2.0,victory)
def defeat(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"upperarm_l",f,(0.0,0.0,0.3*t)); keyb(arm,"upperarm_r",f,(0.0,0.0,0.3*t))
    keyb(arm,"spine_03",f,(0,0,-0.15*t)); keyb(arm,"head",f,(0,0.0,-0.2*t))
    keyshape(f,"frown",0.6*t); keyshape(f,"brow_lower",0.5*t)
oneshot("defeat",2.0,defeat)

# ================================================================ DIALOGUE
def dialogue(arm,f,fs,fe):
    base_move(arm,f); t=(f-fs)/(fe-fs)
    keyb(arm,"pelvis",f,(0,0,0.95+0.01*math.sin(2*math.pi*t*0.5)))
    keyb(arm,"spine_03",f,(0.03*math.sin(2*math.pi*t*0.7),0,0.02*math.sin(2*math.pi*t)))
    keyb(arm,"head",f,(0.03*math.sin(2*math.pi*t*0.9),0.02*math.sin(2*math.pi*t*0.6),0.02*math.sin(2*math.pi*t*0.4)))
    keyb(arm,"upperarm_l",f,(0.0,0.15+0.1*math.sin(2*math.pi*t),0.05*math.sin(2*math.pi*t*1.1)))
    keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.4+0.2*math.sin(2*math.pi*t*1.1)))
    keyb(arm,"hand_l",f,(0.0,0.2+0.1*math.sin(2*math.pi*t*1.1),0.0))
    keyb(arm,"upperarm_r",f,(0.0,-0.1,0.0))
    mid=0.5
    keyshape(f,"jaw_open",0.25+0.15*abs(math.sin(2*math.pi*t*3.0)))
    keyshape(f,"lip_pucker",0.15*abs(math.sin(2*math.pi*t*2.0)))
    keyshape(f,"smile",0.25 if t<mid else 0.5)
    keyshape(f,"brow_raise_L",0.15 if t>mid else 0.05)
    keyshape(f,"brow_raise_R",0.15 if t>mid else 0.05)
    keyshape(f,"blink_L",0.9 if (int(t*10)%7==0) else 0.0)
    keyshape(f,"blink_R",0.9 if (int(t*10)%7==3) else 0.0)
n=frames(15.0);fs=0;fe=n;ac=new_action("dialogue"); rest_all(arm,fs)
for f in range(fs,fe+1): dialogue(arm,f,fs,fe)
marker(ac,frames(3.0),"gesture_hand")
marker(ac,frames(7.5),"emotion_shift")
marker(ac,frames(12.0),"phrase_end")
finalize(ac,fs,fe,False); reg("dialogue",ac)

# ================================================================ POSES
def aim_pose(arm,pname,yname,pval,yval):
    n=frames(1.0);fs=0;fe=n;ac=new_action("aim_"+pname+"_"+yname); rest_all(arm,fs)
    for f in range(n+1):
        keyb(arm,"pelvis",f,(0,0,0.95)); keyb(arm,"spine_03",f,(0,0,math.radians(yval)))
        keyb(arm,"spine_02",f,(math.radians(pval),0,0))
        keyb(arm,"neck",f,(math.radians(pval*0.4),0,math.radians(yval*0.5)))
        keyb(arm,"head",f,(math.radians(pval*0.4),0,math.radians(yval*0.5)))
        keyb(arm,"upperarm_l",f,(0.0,0.15,0.0)); keyb(arm,"lowerarm_l",f,(0.0,0.0,-0.3))
        keyb(arm,"upperarm_r",f,(0.0,-0.15,0.0)); keyb(arm,"lowerarm_r",f,(0.0,0.0,0.3))
        keyb(arm,"hand_l",f,(0.0,0.2,0.0)); keyb(arm,"hand_r",f,(0.0,-0.2,0.0))
        keyb(arm,"eye_l",f,(0.0,0.0,math.radians(yval*0.5)))
        keyb(arm,"eye_r",f,(0.0,0.0,math.radians(yval*0.5)))
    finalize(ac,fs,fe,False); reg("aim_"+pname+"_"+yname,ac)
for pitch in ("down","level","up"):
    for yaw in ("left","center","right"):
        pval={"down":-35,"level":0,"up":35}[pitch]
        yval={"left":-60,"center":0,"right":60}[yaw]
        aim_pose(arm,pitch,yaw,pval,yval)

def dead_pose(name,back):
    fs=0;fe=0;ac=new_action(name); rest_all(arm,fs)
    keyb(arm,"root",0,(0,0,0.19)); keyb(arm,"pelvis",0,(0,0,0.10))
    if back:
        keyb(arm,"spine_03",0,(0,0,-0.3)); keyb(arm,"head",0,(0,-0.05,0.3))
        keyb(arm,"thigh_l",0,(-0.25,0,0)); keyb(arm,"thigh_r",0,(-0.25,0,0))
        keyb(arm,"upperarm_l",0,(0.5,0,0.1)); keyb(arm,"upperarm_r",0,(0.5,0,-0.1))
    else:
        keyb(arm,"spine_03",0,(0,0,0.3)); keyb(arm,"head",0,(0,0.05,-0.3))
        keyb(arm,"thigh_l",0,(0.25,0,0)); keyb(arm,"thigh_r",0,(0.25,0,0))
        keyb(arm,"upperarm_l",0,(0.5,0,-0.2)); keyb(arm,"upperarm_r",0,(0.5,0,0.2))
    finalize(ac,fs,fe,False); reg(name,ac)
dead_pose("dead_front",False)
dead_pose("dead_back",True)

bpy.ops.wm.save_mainfile(filepath=BLEND)
print("TOTAL actions:", len(REG))
for k in sorted(REG): print("  ", k, "frames", REG[k].frame_range, "markers", REG[k].get("markers_json"))
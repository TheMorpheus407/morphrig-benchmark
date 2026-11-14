import bpy, os, json, math, random
from mathutils import Vector, Euler

BLEND="/home/candidate/workspace/MorphRig/source/Operative.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
arm = bpy.data.objects['Operative_Deform']
body = bpy.data.objects['Operative_Body']
scene = bpy.context.scene
scene.render.fps = 30

# Ensure pose mode
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
pb = arm.pose.bones

def reset_pose():
    for b in pb:
        b.location = Vector((0,0,0))
        b.rotation_euler = Euler((0,0,0))
        b.scale = Vector((1,1,1))
    # zero shape keys
    if body.data.shape_keys:
        for kb in body.data.shape_keys.key_blocks:
            kb.value = 0.0

def set_bone(name, loc=None, rot=None, scale=None):
    b = pb[name]
    if rot is not None:
        b.rotation_euler = Euler(rot, 'XYZ')
    if loc is not None:
        b.location = Vector(loc)
    if scale is not None:
        b.scale = Vector(scale)

FPS=30
# inventory: (id, form, root, dur_seconds or None for pose)
INV=[
("idle_relaxed","loop","in_place",3),("idle_combat","loop","in_place",3),("idle_wounded","loop","in_place",3),
("walk_f","loop","in_place",1.2),("walk_fl","loop","in_place",1.2),("walk_l","loop","in_place",1.2),("walk_bl","loop","in_place",1.2),
("walk_b","loop","in_place",1.2),("walk_br","loop","in_place",1.2),("walk_r","loop","in_place",1.2),("walk_fr","loop","in_place",1.2),
("run_f","loop","in_place",0.8),("run_fl","loop","in_place",0.8),("run_l","loop","in_place",0.8),("run_bl","loop","in_place",0.8),
("run_b","loop","in_place",0.8),("run_br","loop","in_place",0.8),("run_r","loop","in_place",0.8),("run_fr","loop","in_place",0.8),
("sprint_f","loop","in_place",0.6),("start_f","one_shot","in_place",0.6),("stop_f","one_shot","in_place",0.6),
("turn_l90","one_shot","in_place",0.6),("turn_r90","one_shot","in_place",0.6),
("pivot_l180","one_shot","in_place",0.7),("pivot_r180","one_shot","in_place",0.7),
("jump_start","one_shot","in_place",0.7),("jump_air","loop","in_place",0.8),("jump_land","one_shot","in_place",0.7),
("fall","loop","in_place",0.8),("land_heavy","one_shot","in_place",0.8),
("dash_f","one_shot","root_motion",0.5),("dash_b","one_shot","root_motion",0.5),
("dash_l","one_shot","root_motion",0.5),("dash_r","one_shot","root_motion",0.5),
("blink_out","one_shot","in_place",0.4),("blink_in","one_shot","in_place",0.4),
("melee_1","one_shot","in_place",0.8),("melee_2","one_shot","in_place",0.8),("melee_3","one_shot","in_place",1.0),
("ranged_fire","one_shot","in_place",0.35),("ranged_burst","one_shot","in_place",0.6),("reload","one_shot","in_place",1.8),
("cast_directional","one_shot","in_place",0.8),("cast_ground","one_shot","in_place",1.0),("cast_self","one_shot","in_place",0.8),
("channel_start","one_shot","in_place",0.5),("channel_loop","loop","in_place",1.2),
("channel_end","one_shot","in_place",0.5),("channel_interrupt","one_shot","in_place",0.4),
("charge_start","one_shot","in_place",0.65),("charge_hold","loop","in_place",1.0),
("charge_release","one_shot","in_place",0.65),("charge_cancel","one_shot","in_place",0.45),
("deploy","one_shot","in_place",1.2),("uplink_start","one_shot","in_place",0.7),
("uplink_loop","loop","in_place",1.5),("uplink_end","one_shot","in_place",0.5),("uplink_cancel","one_shot","in_place",0.45),
("hit_f","additive","in_place",0.33),("hit_b","additive","in_place",0.33),
("hit_l","additive","in_place",0.33),("hit_r","additive","in_place",0.33),
("stun_start","one_shot","in_place",1.5),("stun_loop","loop","in_place",2.0),("stun_end","one_shot","in_place",1.5),
("knockback","one_shot","in_place",1.0),("knockup_start","one_shot","in_place",1.0),
("knockup_air","loop","in_place",1.5),("knockdown_front","one_shot","in_place",1.5),("knockdown_back","one_shot","in_place",1.5),
("prone_front","loop","in_place",2.0),("prone_back","loop","in_place",2.0),
("getup_front","one_shot","in_place",1.5),("getup_back","one_shot","in_place",1.5),
("sleep_start","one_shot","in_place",1.5),("sleep_loop","loop","in_place",2.5),("sleep_end","one_shot","in_place",1.5),
("death_front","one_shot","in_place",2.5),("death_back","one_shot","in_place",2.5),
("dead_front","pose","in_place",None),("dead_back","pose","in_place",None),
("respawn","one_shot","in_place",2.5),("greet","one_shot","in_place",2.0),("victory","one_shot","in_place",2.5),
("defeat","one_shot","in_place",2.5),("dialogue","one_shot","in_place",15.35),
("aim_down_left","pose","in_place",None),("aim_down_center","pose","in_place",None),("aim_down_right","pose","in_place",None),
("aim_level_left","pose","in_place",None),("aim_level_center","pose","in_place",None),("aim_level_right","pose","in_place",None),
("aim_up_left","pose","in_place",None),("aim_up_center","pose","in_place",None),("aim_up_right","pose","in_place",None),
]
assert len(INV)==96, len(INV)

DIR_YAW={"f":0,"fl":45,"l":90,"bl":135,"b":180,"br":-135,"r":-90,"fr":-45}
def yaw_of(suffix):
    return math.radians(DIR_YAW[suffix])

def key_all(f, frames, neutral=False):
    for fr in frames:
        f(fr)

def kf(name, frame, rot=None, loc=None, scale=None):
    b = pb[name]
    if rot is not None:
        b.rotation_mode='XYZ'
        b.rotation_euler = Euler(rot,'XYZ')
        b.keyframe_insert(data_path="rotation_euler", frame=frame)
    if loc is not None:
        b.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        b.keyframe_insert(data_path="scale", frame=frame)

def sk(kb_name, frame, value):
    kb = body.data.shape_keys.key_blocks[kb_name]
    kb.value = value
    kb.keyframe_insert(data_path="value", frame=frame)

def set_pose_for(id_):
    reset_pose()
    amt = 0.0
    # --- base stance ---
    if id_.startswith("idle"):
        if id_=="idle_relaxed": amt=0.1
        elif id_=="idle_combat":
            set_bone("upperarm_L",model_rot=None) if False else None
            for n in ("upperarm_L","upperarm_R"):
                pb[n].rotation_euler = Euler((0,0, 0.25 if "L" in n else -0.25))
        elif id_=="idle_wounded":
            set_bone("spine_02",rot=(0.10,0,0.15)); set_bone("head",rot=(0.15,0,-0.1))
        set_bone("pelvis",rot=(0,0,0),loc=(0,0,0))
    # locomotion handled in function
    # special one-shots
    if id_ in ("jump_start",):
        pass
    return amt

def build_loop_body(anim_id, f1, f2, frames):
    # interpolate helper: set values at f1 and f2
    def interp(fn, f):
        a=(f-f1)/max(1,(f2-f1))
        fn(a)
    return interp

# generic key builders per category
def leg_cycle(phase, yaw_rad, amplitude, run=False):
    # returns dict bone->rot applied at phase 0..1
    s = math.sin(phase*2*math.pi); c = math.cos(phase*2*math.pi)
    # thigh swing
    thL = amplitude*s; thR = -amplitude*s
    kneeL = (amplitude*0.8*(s+1)/2 if run else amplitude*0.5*max(0,s))
    kneeR = (amplitude*0.8*(-s+1)/2 if run else amplitude*0.5*max(0,-s))
    # ankle compensation
    ankL = -0.2*s; ankR = 0.2*s
    return {"thigh_L":(thL,0,0),"thigh_R":(thR,0,0),"calf_L":(-max(0.0,thL)*0.7,0,0),"calf_R":(-max(0.0,thR)*0.7,0,0),
            "foot_L":(ankL,0,0),"foot_R":(ankR,0,0)}

def apply_leg(anim_id, frame, phase, yaw_deg, amplitude, run=False):
    s = math.sin(phase*2*math.pi)
    thL = amplitude*s; thR = -amplitude*s
    pb["thigh_L"].rotation_euler=Euler((thL,0,0))
    pb["thigh_R"].rotation_euler=Euler((thR,0,0))
    pb["calf_L"].rotation_euler=Euler((-max(0.0,thL)*0.9,0,0))
    pb["calf_R"].rotation_euler=Euler((-max(0.0,thR)*0.9,0,0))
    pb["foot_L"].rotation_euler=Euler((-0.15*s,0,0))
    pb["foot_R"].rotation_euler=Euler((0.15*s,0,0))
    # arms counter-swing
    uaL = amplitude*0.55*s; uaR = -amplitude*0.55*s
    pb["upperarm_L"].rotation_euler=Euler((uaL,0,0.18))
    pb["upperarm_R"].rotation_euler=Euler((uaR,0,-0.18))
    pb["lowerarm_L"].rotation_euler=Euler((-0.25-0.1*s,0,0))
    pb["lowerarm_R"].rotation_euler=Euler((-0.25+0.1*s,0,0))
    # pelvis bob + sway
    pb["pelvis"].rotation_euler=Euler((0,0,0.06*s))
    pb["pelvis"].location=Vector((0,0,-0.02*abs(s)))
    pb["spine_02"].rotation_euler=Euler((0,0,-0.05*s))
    # yaw toward direction: root rotation + slight spine yaw
    pb["root"].rotation_euler=Euler((0,0,yaw_deg))
    pb["pelvis"].rotation_euler=Euler((0,0,0.06*s+yaw_deg*0.3))

def author(anim_id, form, root_pol, dur):
    # create action
    act = bpy.data.actions.new(name=anim_id)
    act.use_fake_user=True
    arm.animation_data_create()
    arm.animation_data.action = act
    if form=="pose":
        f1,f2=1,1
    else:
        f1=1; f2=max(2,int(round(dur*FPS)))
    # Force slot creation (Blender 5 slotted actions): keyframe current pose once
    reset_pose()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    pb['pelvis'].keyframe_insert(data_path="location", frame=f1)
    scene.frame_start=f1; scene.frame_end=f2
    # remove existing fcurves from action (fresh)
    # build keyframes
    for f in range(f1,f2+1):
        if form=="loop":
            ph=(f-f1)/max(1,(f2-f1))
        elif form=="one_shot":
            ph=(f-f1)/max(1,(f2-f1))
        else:
            ph=1.0
        reset_pose()
        apply_authored(anim_id, ph, f, f1, f2)
        for bname in [b.name for b in pb]:
            _b = pb[bname]
            _b.keyframe_insert(data_path="location", frame=f)
            _b.keyframe_insert(data_path="rotation_euler", frame=f)
            _b.keyframe_insert(data_path="scale", frame=f)
        # shape keys for face if applicable
        keys_anim = face_anim(anim_id, ph)
        for kn,v in keys_anim.items():
            sk(kn, f, v)
    return (f1,f2)

def apply_authored(anim_id, ph, f, f1, f2):
    # locomotion loops
    if anim_id=="idle_relaxed" or anim_id=="idle_combat" or anim_id=="idle_wounded":
        br=math.sin(ph*2*math.pi)*0.02
        pb["spine_02"].rotation_euler=Euler((br,0,0.02*math.sin(ph*4*math.pi)))
        pb["spine_03"].rotation_euler=Euler((br*0.5,0,0))
        pb["chest" if "chest" in pb else "spine_03"].rotation_euler=Euler((br*0.5,0,0))
        pb["upperarm_L"].rotation_euler=Euler((0,0,0.28))
        pb["upperarm_R"].rotation_euler=Euler((0,0,-0.28))
        pb["lowerarm_L"].rotation_euler=Euler((-0.35,0,0))
        pb["lowerarm_R"].rotation_euler=Euler((-0.35,0,0))
        pb["head"].rotation_euler=Euler((0,0,0.08*math.sin(ph*2*math.pi)))
        pb["pelvis"].location=Vector((0,0,0.01*math.sin(ph*2*math.pi + 1.0)))
        if anim_id=="idle_combat":
            pb["thigh_L"].rotation_euler=Euler((0.15,0,0.10))
            pb["thigh_R"].rotation_euler=Euler((-0.10,0,-0.10))
            pb["spine_02"].rotation_euler=Euler((0.08,0,0.12)); pb["spine_03"].rotation_euler=Euler((0.05,0,0.08))
            pb["upperarm_L"].rotation_euler=Euler((-0.4,0,0.45)); pb["upperarm_R"].rotation_euler=Euler((-0.3,0,-0.35))
            pb["lowerarm_L"].rotation_euler=Euler((-0.7,0,0)); pb["lowerarm_R"].rotation_euler=Euler((-0.5,0,0))
        if anim_id=="idle_wounded":
            pb["spine_02"].rotation_euler=Euler((0.15,0,0.20)); pb["head"].rotation_euler=Euler((0.2,0,-0.12))
            pb["upperarm_L"].rotation_euler=Euler((0.1,0,0.2)); pb["lowerarm_L"].rotation_euler=Euler((-0.2,0,0))
            pb["pelvis"].location=Vector((0.01,0,-0.03))
    elif anim_id.startswith("walk_") or anim_id.startswith("run_") or anim_id=="sprint_f":
        suffix=anim_id.split("_",1)[1]
        yaw=math.radians(DIR_YAW[suffix])
        amp=0.55 if anim_id.startswith("walk") else (0.85 if anim_id.startswith("run") else 1.1)
        apply_leg(anim_id, f, ph, yaw, amp, run=anim_id.startswith("run") or anim_id=="sprint_f")
        # strafe: lean
        if suffix in ("l","r"):
            pb["pelvis"].rotation_euler=Euler((0,0, 0.06*math.sin(ph*2*math.pi) + (0.1 if suffix=="l" else -0.1)))
        if anim_id=="sprint_f":
            pb["spine_02"].rotation_euler=Euler((0.35,0,0)); pb["spine_03"].rotation_euler=Euler((0.25,0,0))
            pb["upperarm_L"].rotation_euler=Euler((1.0*math.sin(ph*2*math.pi+1.0),0,0.3)); pb["upperarm_R"].rotation_euler=Euler((-1.0*math.sin(ph*2*math.pi+1.0),0,-0.3))
    elif anim_id in ("start_f","stop_f"):
        if anim_id=="start_f":
            crouch=math.sin(ph*math.pi)*0.4
            pb["pelvis"].location=Vector((0,0,-0.12*crouch))
            pb["thigh_L"].rotation_euler=Euler((0.5*crouch,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.3*crouch,0,0))
            pb["calf_L"].rotation_euler=Euler((-0.4*crouch,0,0)); pb["calf_R"].rotation_euler=Euler((-0.25*crouch,0,0))
            # ease-in forward
            lean=ph*0.3; pb["spine_02"].rotation_euler=Euler((lean,0,0)); pb["spine_03"].rotation_euler=Euler((lean*0.7,0,0))
            pb["upperarm_L"].rotation_euler=Euler((0.6*ph,0,0.2)); pb["upperarm_R"].rotation_euler=Euler((-0.6*ph,0,-0.2))
            pb["root"].rotation_euler=Euler((0,0,0))
        else:
            pb["pelvis"].location=Vector((0,0,-0.08*(1-ph)))
            pb["spine_02"].rotation_euler=Euler((0.25*(1-ph),0,0)); pb["spine_03"].rotation_euler=Euler((0.15*(1-ph),0,0))
            pb["root"].rotation_euler=Euler((0,0,0))
    elif anim_id in ("turn_l90","turn_r90"):
        ang=math.radians(90 if anim_id=="turn_l90" else -90)*min(1.0, ph*1.2)
        sgn=1 if anim_id=="turn_l90" else -1
        pb["root"].rotation_euler=Euler((0,0,ang))
        pb["pelvis"].rotation_euler=Euler((0,0,ang*0.4))
        step=math.sin(ph*math.pi)
        pb["thigh_L"].rotation_euler=Euler((0.3*step,0,0.1*sgn)); pb["thigh_R"].rotation_euler=Euler((-0.3*step,0,-0.1*sgn))
        pb["spine_02"].rotation_euler=Euler((0,0,0.15*ang))
    elif anim_id in ("pivot_l180","pivot_r180"):
        ang=math.radians(180 if anim_id=="pivot_l180" else -180)*ph
        sgn=1 if anim_id=="pivot_l180" else -1
        pb["root"].rotation_euler=Euler((0,0,ang))
        pb["pelvis"].location=Vector((0,0,0.06*math.sin(ph*math.pi)))
        pb["thigh_L"].rotation_euler=Euler((0.4*math.sin(ph*2*math.pi),0,0)); pb["thigh_R"].rotation_euler=Euler((-0.4*math.sin(ph*2*math.pi),0,0))
        pb["spine_02"].rotation_euler=Euler((0,0,0.2*math.sin(ph*math.pi)))
    elif anim_id=="jump_start":
        pb["pelvis"].location=Vector((0,0,-0.15*math.sin(ph*math.pi)))
        pb["thigh_L"].rotation_euler=Euler((-0.5*math.sin(ph*math.pi),0,0)); pb["thigh_R"].rotation_euler=Euler((-0.5*math.sin(ph*math.pi),0,0))
        pb["calf_L"].rotation_euler=Euler((0.5*math.sin(ph*math.pi),0,0)); pb["calf_R"].rotation_euler=Euler((0.5*math.sin(ph*math.pi),0,0))
        pb["spine_02"].rotation_euler=Euler((-0.2*math.sin(ph*math.pi),0,0)); pb["spine_03"].rotation_euler=Euler((-0.1*math.sin(ph*math.pi),0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.8*math.sin(ph*math.pi),0,0.3)); pb["upperarm_R"].rotation_euler=Euler((0.8*math.sin(ph*math.pi),0,-0.3))
        pb["root"].location=Vector((0,0,0.25*ph*ph))
    elif anim_id=="jump_air":
        pb["root"].location=Vector((0,0,0.25))
        pb["thigh_L"].rotation_euler=Euler((-0.45+0.1*math.sin(ph*2*math.pi),0,0)); pb["thigh_R"].rotation_euler=Euler((0.25,0,0))
        pb["calf_L"].rotation_euler=Euler((0.45,0,0)); pb["calf_R"].rotation_euler=Euler((0.2,0,0))
        pb["spine_02"].rotation_euler=Euler((0.08,0,0)); pb["upperarm_L"].rotation_euler=Euler((0.5,0,0.35)); pb["upperarm_R"].rotation_euler=Euler((0.5,0,-0.35))
    elif anim_id=="fall":
        pb["root"].location=Vector((0,0,0.30))
        pb["thigh_L"].rotation_euler=Euler((0.7,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.3,0,0))
        pb["calf_L"].rotation_euler=Euler((0.3,0,0)); pb["calf_R"].rotation_euler=Euler((0.5,0,0))
        pb["spine_02"].rotation_euler=Euler((-0.15,0,0.1)); pb["head"].rotation_euler=Euler((-0.2,0,0))
        pb["upperarm_L"].rotation_euler=Euler((1.2+0.2*math.sin(ph*2*math.pi),0,0.6)); pb["upperarm_R"].rotation_euler=Euler((1.2,0,-0.6))
    elif anim_id in ("jump_land","land_heavy"):
        depth = 0.15 if anim_id=="jump_land" else 0.28
        comp=math.sin(ph*math.pi)
        pb["pelvis"].location=Vector((0,0,-depth*comp))
        pb["thigh_L"].rotation_euler=Euler((-0.7*comp,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.7*comp,0,0))
        pb["calf_L"].rotation_euler=Euler((0.8*comp,0,0)); pb["calf_R"].rotation_euler=Euler((0.8*comp,0,0))
        pb["spine_02"].rotation_euler=Euler((0.4*comp,0,0)); pb["spine_03"].rotation_euler=Euler((0.2*comp,0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.8*comp,0,0.4)); pb["upperarm_R"].rotation_euler=Euler((0.8*comp,0,-0.4))
        pb["root"].location=Vector((0,0,0.25-0.25*ph))
    elif anim_id.startswith("dash_"):
        suffix=anim_id.split("_")[1]
        yaw=math.radians({"f":0,"b":180,"l":90,"r":-90}[suffix])
        pb["root"].rotation_euler=Euler((0,0,yaw))
        # forward lean + arm pull; root motion 2m over clip: translate root along local Y? Blender root motion: move root bone location in world ground plane.
        # We animate root location so FBX export carries translation. Convert yaw to world XZ: forward is -Y in Blender. Use dir vector.
        d = 2.0*ph
        # world direction (Blender): facing -Y rotated by yaw
        import math as _m
        dx = -_m.sin(yaw)*d if suffix in ("f","l","r","b") else 0  # approximate: yaw about Z
        dy = -_m.cos(yaw)*d
        if suffix=="f": dx=0; dy=-d
        elif suffix=="b": dx=0; dy=d
        elif suffix=="l": dx=-d; dy=0
        elif suffix=="r": dx=d; dy=0
        pb["root"].location=Vector((dx,dy,0))
        pb["spine_02"].rotation_euler=Euler((0.4,0,0)); pb["spine_03"].rotation_euler=Euler((0.3,0,0))
        pb["thigh_L"].rotation_euler=Euler((0.8,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.7,0,0))
        pb["calf_L"].rotation_euler=Euler((0.4,0,0)); pb["calf_R"].rotation_euler=Euler((0.9,0,0))
        pb["upperarm_L"].rotation_euler=Euler((1.1,0,0.3)); pb["upperarm_R"].rotation_euler=Euler((-0.5,0,-0.3))
        pb["pelvis"].location=Vector((0,0,-0.05))
    elif anim_id in ("blink_out","blink_in"):
        pb["spine_02"].rotation_euler=Euler((0.1*math.sin(ph*math.pi),0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.3*math.sin(ph*math.pi),0,0.2)); pb["upperarm_R"].rotation_euler=Euler((0.3*math.sin(ph*math.pi),0,-0.2))
        pb["head"].rotation_euler=Euler((0.05*math.sin(ph*math.pi),0,0))
    elif anim_id.startswith("melee_"):
        # prep -> slash -> recover phases
        if ph<0.35: w=ph/0.35; arm_ang=1.2*w; spine= -0.25*w
        elif ph<0.65: w=(ph-0.35)/0.30; arm_ang=1.2-2.4*w; spine=-0.25+0.5*w
        else: w=(ph-0.65)/0.35; arm_ang=-1.2+1.2*w; spine=0.25-0.25*w
        if anim_id=="melee_2": arm_ang=-arm_ang
        if anim_id=="melee_3": arm_ang*=1.3; spine*=1.3
        pb["upperarm_L"].rotation_euler=Euler((arm_ang,0,0.3))
        pb["lowerarm_L"].rotation_euler=Euler((-0.3,0,0))
        pb["spine_02"].rotation_euler=Euler((0.1,0,spine)); pb["spine_03"].rotation_euler=Euler((0.05,0,spine*0.6))
        pb["pelvis"].rotation_euler=Euler((0,0,spine*0.3)); pb["pelvis"].location=Vector((0,0,-0.04*abs(spine)))
        pb["thigh_L"].rotation_euler=Euler((0.2*spine,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.2*spine,0,0))
        if anim_id=="melee_3":
            pb["head"].rotation_euler=Euler((0.15,0,spine*0.3))
    elif anim_id in ("ranged_fire","ranged_burst"):
        # right arm aim forward (emitter on R forearm)
        pb["upperarm_R"].rotation_euler=Euler((-1.3,0,-0.2)); pb["lowerarm_R"].rotation_euler=Euler((-0.15,0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.2,0,0.2))
        pb["spine_02"].rotation_euler=Euler((0.05,0,0.08)); pb["spine_03"].rotation_euler=Euler((0.03,0,0.05))
        pb["head"].rotation_euler=Euler((-0.05,0,0.05))
        if anim_id=="ranged_burst":
            reco=math.sin(ph*3*2*math.pi)*0.06
            pb["lowerarm_R"].rotation_euler=Euler((-0.15+reco,0,0))
    elif anim_id=="reload":
        # both hands manipulate cell
        pb["upperarm_R"].rotation_euler=Euler((-0.6,0,-0.3)); pb["lowerarm_R"].rotation_euler=Euler((-1.1,0,0))
        pb["upperarm_L"].rotation_euler=Euler((-0.6,0,0.3)); pb["lowerarm_L"].rotation_euler=Euler((-1.2,0,0))
        pb["head"].rotation_euler=Euler((0.35,0,0)); pb["spine_02"].rotation_euler=Euler((0.2,0,0)); pb["spine_03"].rotation_euler=Euler((0.15,0,0))
        # fingers curl to grip
        for side in ("L","R"):
            for fn in ("index","middle","ring","pinky"):
                pb[f"{fn}_01_{side}"].rotation_euler=Euler((0.5*math.sin(ph*math.pi),0,0))
            pb[f"thumb_01_{side}"].rotation_euler=Euler((0.3,0,0))
    elif anim_id=="cast_directional":
        pb["upperarm_L"].rotation_euler=Euler((-1.4*ph if ph<0.6 else -1.4*(2-ph*1.2),0,0.2)); pb["lowerarm_L"].rotation_euler=Euler((-0.1,0,0))
        pb["spine_02"].rotation_euler=Euler((0.1+0.15*ph,0,0.1)); pb["head"].rotation_euler=Euler((-0.1,0,0.1))
    elif anim_id=="cast_ground":
        pb["head"].rotation_euler=Euler((0.5,0,0)); pb["spine_02"].rotation_euler=Euler((0.35,0,0)); pb["spine_03"].rotation_euler=Euler((0.3,0,0))
        pb["upperarm_L"].rotation_euler=Euler((-0.7,0,0.1)); pb["lowerarm_L"].rotation_euler=Euler((-0.9,0,0))
        pb["pelvis"].location=Vector((0,0,-0.08))
    elif anim_id=="cast_self":
        pb["upperarm_L"].rotation_euler=Euler((-0.9*ph,0,0.7)); pb["upperarm_R"].rotation_euler=Euler((-0.9*ph,0,-0.7))
        pb["lowerarm_L"].rotation_euler=Euler((-1.2,0,0)); pb["lowerarm_R"].rotation_euler=Euler((-1.2,0,0))
        pb["spine_02"].rotation_euler=Euler((0.05,0,0)); pb["head"].rotation_euler=Euler((-0.1,0,0))
    elif anim_id in ("channel_start","channel_loop","channel_end","channel_interrupt"):
        pb["upperarm_L"].rotation_euler=Euler((-1.2,0,0.3)); pb["upperarm_R"].rotation_euler=Euler((-1.2,0,-0.3))
        pb["lowerarm_L"].rotation_euler=Euler((-0.2,0,0)); pb["lowerarm_R"].rotation_euler=Euler((-0.2,0,0))
        pb["spine_02"].rotation_euler=Euler((0.12,0,0)); pb["spine_03"].rotation_euler=Euler((0.08,0,0))
        pb["head"].rotation_euler=Euler((-0.08,0,0))
        if anim_id=="channel_interrupt":
            pb["spine_02"].rotation_euler=Euler((0.3,0,0.1)); pb["lowerarm_L"].rotation_euler=Euler((0.4,0,0)); pb["lowerarm_R"].rotation_euler=Euler((0.4,0,0))
        if anim_id=="channel_loop":
            sw=0.02*math.sin(ph*2*math.pi)
            pb["spine_02"].rotation_euler=Euler((0.12+sw,0,0.02*math.cos(ph*2*math.pi)))
    elif anim_id in ("charge_start","charge_hold","charge_release","charge_cancel"):
        pb["upperarm_L"].rotation_euler=Euler((-0.5,0,0)); pb["lowerarm_L"].rotation_euler=Euler((-1.8*ph if anim_id=="charge_start" else -1.8,0,0))
        pb["spine_02"].rotation_euler=Euler((0.15,0,-0.1))
        if anim_id=="charge_release":
            pb["upperarm_L"].rotation_euler=Euler((-1.6,0,0.2)); pb["lowerarm_L"].rotation_euler=Euler((-0.1,0,0))
            pb["spine_02"].rotation_euler=Euler((0.3,0,0.2)); pb["pelvis"].location=Vector((0,0,-0.05))
        if anim_id=="charge_hold":
            pb["spine_02"].rotation_euler=Euler((0.15+0.02*math.sin(ph*2*math.pi),0,-0.1))
    elif anim_id in ("deploy","uplink_start","uplink_loop","uplink_end","uplink_cancel"):
        pb["spine_02"].rotation_euler=Euler((0.25,0,0)); pb["spine_03"].rotation_euler=Euler((0.2,0,0)); pb["head"].rotation_euler=Euler((0.4,0,0))
        pb["upperarm_L"].rotation_euler=Euler((-0.8,0,0.2)); pb["lowerarm_L"].rotation_euler=Euler((-1.0,0,0))
        pb["pelvis"].location=Vector((0,0,-0.06))
        if anim_id=="deploy":
            kneel = math.sin(ph*math.pi)
            pb["thigh_L"].rotation_euler=Euler((-1.1*kneel,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.2*kneel,0,0))
            pb["calf_L"].rotation_euler=Euler((0.9*kneel,0,0)); pb["calf_R"].rotation_euler=Euler((0.2*kneel,0,0))
        if anim_id=="uplink_loop":
            pb["upperarm_L"].rotation_euler=Euler((-1.2+0.05*math.sin(ph*2*math.pi),0,0.2))
    elif anim_id.startswith("hit_"):
        d = {"f":(0.3,0),"b":(-0.3,0),"l":(0,0.3),"r":(0,-0.3)}[anim_id.split("_")[1]]
        w=math.sin(ph*math.pi)
        pb["spine_02"].rotation_euler=Euler((d[0]*w,0,d[1]*w)); pb["spine_03"].rotation_euler=Euler((d[0]*0.6*w,0,d[1]*0.6*w))
        pb["head"].rotation_euler=Euler((d[0]*0.5*w,0,d[1]*0.5*w))
        pb["pelvis"].rotation_euler=Euler((d[0]*0.3*w,0,d[1]*0.3*w))
    elif anim_id in ("stun_start","stun_loop","stun_end"):
        if anim_id=="stun_loop":
            pb["spine_02"].rotation_euler=Euler((0.2,0,0.15+0.05*math.sin(ph*2*math.pi))); pb["spine_03"].rotation_euler=Euler((0.15,0,0.1))
            pb["head"].rotation_euler=Euler((0.3,0,0.1*math.sin(ph*2*math.pi))); pb["pelvis"].location=Vector((0,0,-0.05))
            pb["upperarm_L"].rotation_euler=Euler((0.2,0,0.1)); pb["upperarm_R"].rotation_euler=Euler((0.2,0,-0.1))
        elif anim_id=="stun_start":
            w=ph; pb["spine_02"].rotation_euler=Euler((0.2*w,0,0.15*w)); pb["head"].rotation_euler=Euler((0.3*w,0,0)); pb["pelvis"].location=Vector((0,0,-0.05*w))
        else:
            w=1-ph; pb["spine_02"].rotation_euler=Euler((0.2*w,0,0.15*w)); pb["head"].rotation_euler=Euler((0.3*w,0,0)); pb["pelvis"].location=Vector((0,0,-0.05*w))
    elif anim_id=="knockback":
        w=math.sin(ph*math.pi)
        pb["spine_02"].rotation_euler=Euler((-0.3*w,0,0)); pb["spine_03"].rotation_euler=Euler((-0.2*w,0,0))
        pb["pelvis"].location=Vector((0,0.05*w,0)); pb["root"].rotation_euler=Euler((0,0,0))
    elif anim_id=="knockup_start":
        pb["root"].location=Vector((0,0,0.4*ph*ph)); pb["spine_02"].rotation_euler=Euler((-0.4*ph,0,0)); pb["head"].rotation_euler=Euler((-0.3*ph,0,0))
        pb["thigh_L"].rotation_euler=Euler((0.5*ph,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.4*ph,0,0))
    elif anim_id=="knockup_air":
        pb["root"].location=Vector((0,0,0.4)); pb["spine_02"].rotation_euler=Euler((-0.4,0,0.1)); pb["spine_03"].rotation_euler=Euler((-0.3,0,0))
        pb["thigh_L"].rotation_euler=Euler((0.5,0,0.1)); pb["thigh_R"].rotation_euler=Euler((-0.4,0,-0.1))
        pb["upperarm_L"].rotation_euler=Euler((0.8,0,0.4)); pb["upperarm_R"].rotation_euler=Euler((0.8,0,-0.4))
        pb["head"].rotation_euler=Euler((-0.3,0,0))
    elif anim_id in ("knockdown_front","knockdown_back","prone_front","prone_back","getup_front","getup_back"):
        front = "front" in anim_id
        if anim_id in ("prone_front","prone_back"):
            # lying: root at floor, body rotated. Simulate by rotating root 90deg about X and lowering.
            rot = math.radians(-85) if front else math.radians(85)
            # face-down: rotate forward (negative X rot -> face down?). Use X rotation on root+pelvis chain via root bone.
            pb["root"].rotation_euler=Euler((rot,0,0))
            pb["root"].location=Vector((0,0,0.12))
            pb["spine_02"].rotation_euler=Euler((0.1,0,0)); pb["head"].rotation_euler=Euler((-0.2,0,0))
            pb["thigh_L"].rotation_euler=Euler((0.05,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.05,0,0))
            pb["upperarm_L"].rotation_euler=Euler((0.3,0,0.2)); pb["upperarm_R"].rotation_euler=Euler((0.3,0,-0.2))
            br=0.01*math.sin(ph*2*math.pi)
            pb["spine_03"].rotation_euler=Euler((br,0,0))
        elif anim_id in ("knockdown_front","knockdown_back"):
            w=ph
            rot = math.radians(-85)*w if front else math.radians(85)*w
            pb["root"].rotation_euler=Euler((rot,0,0))
            pb["root"].location=Vector((0,0,0.12*w))
            pb["spine_02"].rotation_euler=Euler((0.3*w,0,0)); pb["upperarm_L"].rotation_euler=Euler((0.6*w,0,0.3)); pb["upperarm_R"].rotation_euler=Euler((0.6*w,0,-0.3))
        else: # getup
            w=1-ph
            rot = math.radians(-85)*w if front else math.radians(85)*w
            pb["root"].rotation_euler=Euler((rot,0,0))
            pb["root"].location=Vector((0,0,0.12*w))
            pb["spine_02"].rotation_euler=Euler((0.25*w,0,0)); pb["pelvis"].location=Vector((0,0,-0.1*w))
            pb["thigh_L"].rotation_euler=Euler((-0.8*w,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.8*w,0,0))
            pb["calf_L"].rotation_euler=Euler((0.6*w,0,0)); pb["calf_R"].rotation_euler=Euler((0.6*w,0,0))
    elif anim_id in ("sleep_start","sleep_loop","sleep_end"):
        if anim_id=="sleep_loop":
            pb["root"].rotation_euler=Euler((math.radians(70),0,0)); pb["root"].location=Vector((0,0,0.15))
            pb["head"].rotation_euler=Euler((0.2,0,0.15)); bre=0.02*math.sin(ph*2*math.pi)
            pb["spine_02"].rotation_euler=Euler((bre,0,0)); pb["spine_03"].rotation_euler=Euler((bre*0.5,0,0))
        else:
            w=ph if anim_id=="sleep_start" else 1-ph
            pb["root"].rotation_euler=Euler((math.radians(70)*w,0,0)); pb["root"].location=Vector((0,0,0.15*w))
            pb["head"].rotation_euler=Euler((0.2*w,0,0)); pb["pelvis"].location=Vector((0,0,-0.1*w))
    elif anim_id in ("death_front","death_back"):
        front = anim_id=="death_front"
        w=min(1.0, ph*1.4)
        rot = math.radians(-85)*w if front else math.radians(85)*w
        pb["root"].rotation_euler=Euler((rot,0,0)); pb["root"].location=Vector((0,0,0.12*w))
        pb["spine_02"].rotation_euler=Euler((0.35*w,0,0.1*w)); pb["head"].rotation_euler=Euler((0.3*w,0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.9*w,0,0.5*w)); pb["upperarm_R"].rotation_euler=Euler((0.9*w,0,-0.5*w))
        pb["thigh_L"].rotation_euler=Euler((0.15*w,0,0)); pb["thigh_R"].rotation_euler=Euler((-0.1*w,0,0))
    elif anim_id in ("dead_front","dead_back"):
        front = anim_id=="dead_front"
        rot = math.radians(-85) if front else math.radians(85)
        pb["root"].rotation_euler=Euler((rot,0,0)); pb["root"].location=Vector((0,0,0.12))
        pb["spine_02"].rotation_euler=Euler((0.35,0,0.1)); pb["head"].rotation_euler=Euler((0.3,0,0))
    elif anim_id=="respawn":
        w=ph
        pb["root"].location=Vector((0,0,-0.1*(1-w)))
        pb["spine_02"].rotation_euler=Euler((0.3*(1-w),0,0)); pb["spine_03"].rotation_euler=Euler((0.2*(1-w),0,0))
        pb["upperarm_L"].rotation_euler=Euler((0.8*(1-w),0,0.4*(1-w))); pb["upperarm_R"].rotation_euler=Euler((0.8*(1-w),0,-0.4*(1-w)))
        pb["head"].rotation_euler=Euler((0.25*(1-w),0,0))
    elif anim_id=="greet":
        pb["upperarm_R"].rotation_euler=Euler((-0.6*math.sin(ph*math.pi),0,-0.5))
        pb["lowerarm_R"].rotation_euler=Euler((-0.4+0.3*math.sin(ph*2*math.pi*2),0,0))
        pb["head"].rotation_euler=Euler((0.05,0,0.05))
    elif anim_id=="victory":
        w=math.sin(ph*math.pi)
        pb["upperarm_L"].rotation_euler=Euler((-2.8*w,0,0.4)); pb["upperarm_R"].rotation_euler=Euler((-2.8*w,0,-0.4))
        pb["head"].rotation_euler=Euler((-0.2*w,0,0)); pb["spine_02"].rotation_euler=Euler((-0.15*w,0,0))
        pb["pelvis"].location=Vector((0,0,0.05*w))
    elif anim_id=="defeat":
        pb["spine_02"].rotation_euler=Euler((0.35,0,0)); pb["spine_03"].rotation_euler=Euler((0.25,0,0)); pb["head"].rotation_euler=Euler((0.4,0,0))
        pb["pelvis"].location=Vector((0,0,-0.08)); pb["upperarm_L"].rotation_euler=Euler((0.1,0,0.15)); pb["upperarm_R"].rotation_euler=Euler((0.1,0,-0.15))
    elif anim_id=="dialogue":
        # 15.35s: gaze changes + emotional shift (sentence boundaries ~0.2,0.28,0.56,0.83 in phase)
        t=ph
        # hand gestures: right hand point on sent 1&3, open gesture sent 2, fist sent 4
        if t<0.2:
            pb["upperarm_R"].rotation_euler=Euler((-1.3,0,-0.2)); pb["lowerarm_R"].rotation_euler=Euler((-0.2,0,0))
        elif t<0.28:
            pb["upperarm_R"].rotation_euler=Euler((-0.4,0,-0.4)); pb["lowerarm_R"].rotation_euler=Euler((-0.8,0,0))
        elif t<0.56:
            pb["upperarm_R"].rotation_euler=Euler((-0.5,0,-0.3)); pb["lowerarm_R"].rotation_euler=Euler((-1.0,0,0))
        elif t<0.83:
            pb["upperarm_R"].rotation_euler=Euler((-1.4,0,-0.1)); pb["lowerarm_R"].rotation_euler=Euler((-0.15,0,0))
        else:
            pb["upperarm_R"].rotation_euler=Euler((-0.8,0,-0.2)); pb["lowerarm_R"].rotation_euler=Euler((-1.6,0,0))
        # gaze: head look left/right per sentence
        look = [0.25, -0.2, 0.35, 0.0]
        seg = 0 if t<0.2 else (1 if t<0.56 else (2 if t<0.83 else 3))
        pb["head"].rotation_euler=Euler((-0.05,0,look[seg]*0.7))
        pb["neck_01"].rotation_euler=Euler((0,0,look[seg]*0.3))
        pb["eye_L"].rotation_euler=Euler((0,0,look[seg])); pb["eye_R"].rotation_euler=Euler((0,0,look[seg]))
        pb["spine_02"].rotation_euler=Euler((0.05*math.sin(ph*2*math.pi*4),0,look[seg]*0.2))
    elif anim_id.startswith("aim_"):
        # aim_down/up + left/center/right
        pitch = -35 if "down" in anim_id else (35 if "up" in anim_id else 0)
        yaw = -60 if "left" in anim_id else (60 if "right" in anim_id else 0)
        # upper body layer: spine/head pitch/yaw, right arm aims forward (emitter)
        pr=math.radians(pitch); yw=math.radians(yaw)
        pb["upperarm_R"].rotation_euler=Euler((-1.35-pr,0,-0.15)); pb["lowerarm_R"].rotation_euler=Euler((-0.12,0,0))
        pb["spine_02"].rotation_euler=Euler((pr*0.4,0,yw*0.4)); pb["spine_03"].rotation_euler=Euler((pr*0.4,0,yw*0.4))
        pb["head"].rotation_euler=Euler((-pr*0.8,0,-yw*0.6))
        pb["upperarm_L"].rotation_euler=Euler((-0.5,0,0.3)); pb["lowerarm_L"].rotation_euler=Euler((-0.8,0,0))
    else:
        pass

def face_anim(anim_id, ph):
    d={}
    if anim_id.startswith("hit_"):
        d["Preset_Pain"]=math.sin(ph*math.pi)*0.8
    elif anim_id in ("death_front","death_back","dead_front","dead_back","prone_front","prone_back"):
        d["Preset_Sadness"]=0.6; d["JawOpen"]=0.3
    elif anim_id in ("victory",): d["Preset_Joy"]=math.sin(ph*math.pi)
    elif anim_id in ("defeat","idle_wounded"): d["Preset_Sadness"]=0.5
    elif anim_id in ("dialogue","greet"): d["Preset_Joy"]=0.3
    elif anim_id in ("stun_start","stun_loop"): d["Preset_Surprise"]=0.5
    # dialogue: visemes cycling per sentence + blink
    if anim_id=="dialogue":
        sents=[(0.0,0.20,"Viseme_A"),(0.06,0.10,"Viseme_O"),(0.12,0.16,"Viseme_I"),(0.16,0.20,"Viseme_M"),
               (0.28,0.38,"Viseme_E" if False else "Viseme_I"),(0.38,0.48,"Viseme_A"),(0.48,0.56,"Viseme_M"),
               (0.56,0.66,"Viseme_I"),(0.66,0.75,"Viseme_U"),(0.75,0.83,"Viseme_O"),
               (0.83,0.90,"Viseme_A"),(0.90,0.97,"Viseme_I"),(0.97,1.0,"Viseme_M")]
        # blink every ~5s: phase 0.33, 0.66 brief
        for a,b,nm in sents:
            if a<=ph<=b: d[nm]=0.9
        if d.get("Viseme_A",0)>0.5: d["JawOpen"]=0.7
        if (0.32<ph<0.34) or (0.65<ph<0.67): d["Blink_L"]=0.9; d["Blink_R"]=0.9
        # emotional shift: first half Focus, second half Joy
        if ph<0.5: d["Preset_Focus"]=0.6
        else: d["Preset_Joy"]=0.5
    if anim_id.startswith("idle") or anim_id in ("walk_f","run_f"):
        # occasional blink
        if 0.1<ph<0.14: d["Blink_L"]=0.8; d["Blink_R"]=0.8
    return d

manifest=[]
events_map={
 "melee_1":[("hit_start",0.4),("hit_end",0.65),("recovery",0.65)],
 "melee_2":[("hit_start",0.4),("hit_end",0.65),("recovery",0.65)],
 "melee_3":[("hit_start",0.45),("hit_end",0.7),("recovery",0.7)],
 "ranged_fire":[("muzzle",0.45)],
 "ranged_burst":[("muzzle_1",0.25),("muzzle_2",0.5),("muzzle_3",0.75)],
 "reload":[("handoff",0.45),("insert",0.7)],
 "deploy":[("attach",0.55),("release",0.8)],
 "cast_directional":[("release",0.6)],
 "cast_ground":[("release",0.62)],
 "cast_self":[("release",0.5)],
 "charge_release":[("release",0.5)],
 "channel_start":[("channel_enter",0.8)],
 "channel_end":[("channel_release",0.5)],
 "channel_interrupt":[("interrupt",0.4)],
 "blink_out":[("teleport_out",0.8)],
 "blink_in":[("teleport_in",0.15)],
 "jump_land":[("contact",0.2)],
 "walk_f":[("contact_L",0.0),("contact_R",0.5)],
 "run_f":[("contact_L",0.0),("contact_R",0.5)],
 "dash_f":[("contact",0.05)],
}
for (anim_id, form, root_pol, dur) in INV:
    f1,f2 = author(anim_id, form, root_pol, dur)
    n = f2-f1+1
    dur_s = (n-1)/FPS if form!="pose" else 0
    evs = [{"name":nm,"frame":f1+int(round(ph*(n-1))),"time_seconds":round(ph*(n-1)/FPS,3)} for nm,ph in events_map.get(anim_id,[])]
    # loop flag
    loop = (form=="loop")
    manifest.append({"id":anim_id,"form":form,"root_movement":root_pol,"frame_start":f1,"frame_end":f2,
        "frame_count":n,"fps":FPS,"duration_seconds":round(dur_s,3) if form!="pose" else None,
        "loop":loop,"layer":"full_body" if not anim_id.startswith("hit_") else "additive_upper",
        "events":evs,"blender_action":anim_id,"source_action":anim_id,
        "unreal_asset":f"/Game/MorphRig/Animations/{anim_id}.uasset" if form!="pose" else f"/Game/MorphRig/Poses/{anim_id}.uasset",
        "export_file":f"export/animations/{anim_id}.fbx","entry_state":"idle_combat","exit_state":"idle_combat"})

# dialogue action extra: key jaw + visemes at higher granularity already done per frame; add marker for audio
# Save
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
with open("/home/candidate/workspace/MorphRig/docs/animation_manifest.json","w") as fh:
    json.dump({"fps":FPS,"count":len(manifest),"animations":manifest},fh,indent=2)
print("AUTHORED", len(manifest))
result={"count":len(manifest)}

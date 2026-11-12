#!/usr/bin/env python3
"""MORPHRIG - Build deformation skeleton, animator controls, constraints, skinning.
Loads source/Operative.blend, saves back with rig + skin."""
import bpy
import math
from mathutils import Vector, Matrix, Euler

BLEND = "/home/candidate/workspace/MorphRig/source/Operative.blend"

bpy.ops.wm.open_mainfile(filepath=BLEND)

def clear_scene_keep_meshes():
    # remove armatures/controls only
    for o in list(bpy.data.objects):
        if o.type == 'ARMATURE' or o.name.startswith(('CTRL_','IK_','FK_','POLE_','ROLL_','LOOK_')):
            bpy.data.objects.remove(o, do_unlink=True)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)

def link(obj, col_name="Character"):
    col = bpy.data.collections.get(col_name)
    if col is None:
        col = bpy.data.collections.new(col_name); bpy.context.scene.collection.children.link(col)
    col.objects.link(obj)
    for c in obj.users_collection:
        if c.name != col_name:
            c.objects.unlink(obj)

def make_active(obj):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)

def select(obj, state=True):
    obj.select_set(state)

def new_empty(name, loc, size=0.05, shape='PLAIN_AXES'):
    bpy.ops.object.empty_add(type=PLAIN_AXES if shape=='PLAIN_AXES' else 'SPHERE', location=loc)
    o = bpy.context.active_object
    o.name = name
    o.empty_display_size = size
    if shape == 'CUBE':
        o.empty_display_type = 'CUBE'
    elif shape == 'SPHERE':
        o.empty_display_type = 'SPHERE'
    elif shape == 'CIRCLE':
        o.empty_display_type = 'PLAIN_AXES'
    return o

def new_ctrl(name, loc, size=0.06, shape='CUBE', color=(0.1,0.8,0.1)):
    o = new_empty(name, loc, size=size, shape=shape)
    # display color via custom property not needed
    return o

clear_scene_keep_meshes()
bpy.ops.object.mode_set(mode='OBJECT')

# ============ ARMATURE (deformation skeleton) ============
arm = bpy.data.armatures.new("Operative_Armature")
arm_obj = bpy.data.objects.new("Operative_Armature", arm)
link(arm_obj, "Character")
make_active(arm_obj)
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.edit_bones

def bone(name, head, tail, parent=None, roll=0.0):
    b = eb.new(name)
    b.head = Vector(head)
    b.tail = Vector(tail)
    b.roll = roll
    if parent:
        b.parent = eb[parent]
        b.use_connect = True
    return b

# Root separate from pelvis
bone("root", (0,0,0.0), (0,0,0.1))
bone("pelvis", (0,0,0.95), (0,0,1.05), parent="root")
bone("spine_01", (0,0,1.08), (0,0,1.20), parent="pelvis")
bone("spine_02", (0,0,1.20), (0,0,1.31), parent="spine_01")
bone("spine_03", (0,0,1.31), (0,0,1.40), parent="spine_02")
bone("neck", (0,0,1.45), (0,0,1.55), parent="spine_03")
bone("head", (0,0,1.57), (0,0,1.72), parent="neck")

# Clavicles
bone("clavicle_l", (0,0,1.39), (-0.23,0.02,1.41), parent="spine_03")
bone("clavicle_r", (0,0,1.39), (0.23,0.02,1.41), parent="spine_03")

# Arms (L organic, R cyber)
bone("upperarm_l", (-0.23,0.02,1.41), (-0.40,0.0,1.19), parent="clavicle_l")
bone("lowerarm_l", (-0.40,0.0,1.19), (-0.57,0.0,0.97), parent="upperarm_l")
bone("hand_l", (-0.57,0.0,0.97), (-0.67,0.0,0.91), parent="lowerarm_l")
bone("upperarm_r", (0.23,0.02,1.41), (0.40,0.0,1.19), parent="clavicle_r")
bone("lowerarm_r", (0.40,0.0,1.19), (0.57,0.0,0.97), parent="upperarm_r")
bone("hand_r", (0.57,0.0,0.97), (0.67,0.0,0.91), parent="lowerarm_r")

# Fingers: 5 x 3 phalanges, chain from hand
finger_offsets_l = [(-0.67,0.015,0.92),(-0.67,0.006,0.915),(-0.67,-0.012,0.91),(-0.67,-0.028,0.905),(-0.67,-0.042,0.90)]
finger_offsets_r = [(0.67,0.015,0.92),(0.67,0.006,0.915),(0.67,-0.012,0.91),(0.67,-0.028,0.905),(0.67,-0.042,0.90)]
finger_names = ["thumb","index","middle","ring","pinky"]
for side, offs in (("l",finger_offsets_l),("r",finger_offsets_r)):
    for fi, name in enumerate(finger_names):
        base = Vector(offs[fi])
        dir_vec = Vector((-1 if side=='l' else 1, 0, 0))
        prev = "hand_"+side
        for j in range(3):
            bn = f"{name}_{j+1}_{side}"
            h = base + dir_vec*(j*0.020)
            t = base + dir_vec*((j+1)*0.020)
            bone(bn, h, t, parent=prev)
            prev = bn

# Legs
bone("thigh_l", (0,0,0.95), (-0.11,0.0,0.68), parent="pelvis")
bone("shin_l", (-0.11,0.0,0.68), (-0.11,0.0,0.30), parent="thigh_l")
bone("foot_l", (-0.11,0.0,0.30), (-0.11,0.10,0.13), parent="shin_l")
bone("toe_l", (-0.11,0.10,0.13), (-0.11,0.18,0.05), parent="foot_l")
bone("thigh_r", (0,0,0.95), (0.11,0.0,0.68), parent="pelvis")
bone("shin_r", (0.11,0.0,0.68), (0.11,0.0,0.30), parent="shin_l" if False else "thigh_r")
bone("foot_r", (0.11,0.0,0.30), (0.11,0.10,0.13), parent="shin_r")
bone("toe_r", (0.11,0.10,0.13), (0.11,0.18,0.05), parent="foot_r")

# Eyes
bone("eye_l", (-0.065,0.13,1.625), (-0.09,0.15,1.625), parent="head")
bone("eye_r", (0.065,0.13,1.625), (0.09,0.15,1.625), parent="head")

# Facial bones (children of head)
bone("jaw", (0,0.03,1.56), (0,0.09,1.50), parent="head")
bone("lip_upper", (0,0.06,1.565), (0,0.10,1.565), parent="head")
bone("lip_lower", (0,0.03,1.545), (0,0.07,1.535), parent="head")
bone("brow_l", (-0.06,0.13,1.67), (-0.06,0.13,1.71), parent="head")
bone("brow_r", (0.06,0.13,1.67), (0.06,0.13,1.71), parent="head")
bone("cheek_l", (-0.09,0.10,1.60), (-0.12,0.10,1.56), parent="head")
bone("cheek_r", (0.09,0.10,1.60), (0.12,0.10,1.56), parent="head")
bone("mouth_corner_l", (-0.045,0.07,1.55), (-0.06,0.085,1.54), parent="head")
bone("mouth_corner_r", (0.045,0.07,1.55), (0.06,0.085,1.54), parent="head")
bone("tongue", (0,0.05,1.55), (0,0.09,1.51), parent="head")
bone("teeth_upper", (0,0.07,1.575), (0,0.07,1.565), parent="head")
bone("teeth_lower", (0,0.04,1.55), (0,0.04,1.54), parent="head")

bpy.ops.object.mode_set(mode='OBJECT')
arm_obj.data.display_type = 'STICK'
arm_obj.show_in_front = True

# ============ CONTROLS ============
def ctrl(name, loc, size=0.06, shape='CUBE'):
    return new_ctrl(name, loc, size=size, shape=shape)

root_ctrl = ctrl("CTRL_root", (0,0,0.1), size=0.12, shape='SPHERE')
pelvis_ctrl = ctrl("CTRL_pelvis", (0,0,1.0), size=0.1, shape='SPHERE')
spine_ctrl = ctrl("CTRL_spine", (0,0,1.25), size=0.09, shape='CUBE')
head_ctrl = ctrl("CTRL_head", (0,0,1.72), size=0.07, shape='SPHERE')
look_ctrl = ctrl("CTRL_look", (0,0.4,1.65), size=0.05, shape='SPHERE')
look_ctrl_l = ctrl("CTRL_look_l", (-0.065,0.25,1.66), size=0.04, shape='SPHERE')
look_ctrl_r = ctrl("CTRL_look_r", (0.065,0.25,1.66), size=0.04, shape='SPHERE')

# Arm FK/IK controls L
fk_ua_l = ctrl("FK_upperarm_l", (-0.23,0.02,1.41), size=0.045)
fk_la_l = ctrl("FK_lowerarm_l", (-0.40,0.0,1.19), size=0.04)
fk_hand_l = ctrl("FK_hand_l", (-0.57,0.0,0.97), size=0.045)
ik_hand_l = ctrl("IK_hand_l", (-0.67,0.0,0.91), size=0.05, shape='SPHERE')
pole_arm_l = ctrl("POLE_arm_l", (-0.45,0.35,1.10), size=0.04, shape='CUBE')
# Arm FK/IK controls R
fk_ua_r = ctrl("FK_upperarm_r", (0.23,0.02,1.41), size=0.045)
fk_la_r = ctrl("FK_lowerarm_r", (0.40,0.0,1.19), size=0.04)
fk_hand_r = ctrl("FK_hand_r", (0.57,0.0,0.97), size=0.045)
ik_hand_r = ctrl("IK_hand_r", (0.67,0.0,0.91), size=0.05, shape='SPHERE')
pole_arm_r = ctrl("POLE_arm_r", (0.45,0.35,1.10), size=0.04, shape='CUBE')

# Leg FK/IK controls
fk_thigh_l = ctrl("FK_thigh_l", (-0.11,0.0,0.68), size=0.05)
fk_shin_l = ctrl("FK_shin_l", (-0.11,0.0,0.30), size=0.045)
fk_foot_l = ctrl("FK_foot_l", (-0.11,0.10,0.13), size=0.05)
ik_foot_l = ctrl("IK_foot_l", (-0.11,0.10,0.13), size=0.05, shape='SPHERE')
pole_leg_l = ctrl("POLE_leg_l", (-0.11,0.4,0.45), size=0.04, shape='CUBE')
roll_foot_l = ctrl("ROLL_foot_l", (-0.11,0.14,0.06), size=0.05, shape='CUBE')
toe_l_ctrl = ctrl("TOE_l", (-0.11,0.20,0.05), size=0.04, shape='CUBE')

fk_thigh_r = ctrl("FK_thigh_r", (0.11,0.0,0.68), size=0.05)
fk_shin_r = ctrl("FK_shin_r", (0.11,0.0,0.30), size=0.045)
fk_foot_r = ctrl("FK_foot_r", (0.11,0.10,0.13), size=0.05)
ik_foot_r = ctrl("IK_foot_r", (0.11,0.10,0.13), size=0.05, shape='SPHERE')
pole_leg_r = ctrl("POLE_leg_r", (0.11,0.4,0.45), size=0.04, shape='CUBE')
roll_foot_r = ctrl("ROLL_foot_r", (0.11,0.14,0.06), size=0.05, shape='CUBE')
toe_r_ctrl = ctrl("TOE_r", (0.11,0.20,0.05), size=0.04, shape='CUBE')

# Facial controls
ctrl_jaw = ctrl("CTRL_jaw", (0,0.10,1.52), size=0.05, shape='SPHERE')
ctrl_brow_l = ctrl("CTRL_brow_l", (-0.06,0.13,1.71), size=0.04, shape='CUBE')
ctrl_brow_r = ctrl("CTRL_brow_r", (0.06,0.13,1.71), size=0.04, shape='CUBE')
ctrl_lip_u = ctrl("CTRL_lip_upper", (0,0.11,1.565), size=0.04, shape='CUBE')
ctrl_lip_d = ctrl("CTRL_lip_lower", (0,0.07,1.53), size=0.04, shape='CUBE')
ctrl_cheek_l = ctrl("CTRL_cheek_l", (-0.12,0.10,1.56), size=0.04, shape='CUBE')
ctrl_cheek_r = ctrl("CTRL_cheek_r", (0.12,0.10,1.56), size=0.04, shape='CUBE')
ctrl_mouth_l = ctrl("CTRL_mouth_l", (-0.06,0.085,1.54), size=0.04, shape='CUBE')
ctrl_mouth_r = ctrl("CTRL_mouth_r", (0.06,0.085,1.54), size=0.04, shape='CUBE')
ctrl_eyelid_u_l = ctrl("CTRL_eyelid_u_l", (-0.065,0.14,1.67), size=0.04, shape='CUBE')
ctrl_eyelid_u_r = ctrl("CTRL_eyelid_u_r", (0.065,0.14,1.67), size=0.04, shape='CUBE')

# IK/FK switch properties
for cname, cobj in (("arm_l",ik_hand_l),("arm_r",ik_hand_r),("leg_l",ik_foot_l),("leg_r",ik_foot_r)):
    cobj["ik_fk"] = 0.0

# ============ CONSTRAINTS ============
def put_pose_bone(arm_obj, bname):
    return arm_obj.pose.bones[bname]

def ccopy(owner, target_name, target_obj, influence_prop=None, influence=1.0):
    c = owner.constraints.new('COPY_TRANSFORMS')
    c.name = target_name
    c.target = target_obj
    c.influence = influence
    if influence_prop:
        c[influence_prop] = influence  # not a driver, just marker
    return c

def cik(owner, target, pole, chain, influence):
    c = owner.constraints.new('IK')
    c.target = target
    c.pole_target = pole
    c.chain_count = chain
    c.influence = influence
    return c

def influence_driver(ctrl_obj, prop, target_constraint):
    # driver: constraint.influence = ctrl_obj[prop]
    drv = target_constraint.driver_add("influence")
    drv.driver.type = 'SCRIPTED'
    drv.driver.expression = prop
    var = drv.driver.variables.new()
    var.name = prop
    var.targets[0].id = ctrl_obj
    var.targets[0].data_path = f'["{prop}"]'
    return drv

pose = arm_obj.pose

# --- Arms ---
# L arm: FK copytransforms influence (1-ik_fk), IK influence (ik_fk)
for bname, fkc in (("upperarm_l",fk_ua_l),("lowerarm_l",fk_la_l),("hand_l",fk_hand_l)):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = fkc; c.influence = 1.0
    drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "1.0 - ik_fk"
    v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_hand_l; v.targets[0].data_path='["ik_fk"]'
pb = pose.bones["hand_l"]
c = pb.constraints.new('IK'); c.target = ik_hand_l; c.pole_target = pole_arm_l; c.chain_count = 3
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "ik_fk"
v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_hand_l; v.targets[0].data_path='["ik_fk"]'

# R arm
for bname, fkc in (("upperarm_r",fk_ua_r),("lowerarm_r",fk_la_r),("hand_r",fk_hand_r)):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = fkc; c.influence = 1.0
    drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "1.0 - ik_fk"
    v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_hand_r; v.targets[0].data_path='["ik_fk"]'
pb = pose.bones["hand_r"]
c = pb.constraints.new('IK'); c.target = ik_hand_r; c.pole_target = pole_arm_r; c.chain_count = 3
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "ik_fk"
v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_hand_r; v.targets[0].data_path='["ik_fk"]'

# --- Legs ---
for bname, fkc in (("thigh_l",fk_thigh_l),("shin_l",fk_shin_l),("foot_l",fk_foot_l)):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = fkc; c.influence = 1.0
    drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "1.0 - ik_fk"
    v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_foot_l; v.targets[0].data_path='["ik_fk"]'
pb = pose.bones["foot_l"]
c = pb.constraints.new('IK'); c.target = ik_foot_l; c.pole_target = pole_leg_l; c.chain_count = 3
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "ik_fk"
v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_foot_l; v.targets[0].data_path='["ik_fk"]'
# foot roll: toe pivot
pb = pose.bones["toe_l"]
c = pb.constraints.new('COPY_TRANSFORMS'); c.target = toe_l_ctrl; c.influence = 1.0
# roll_foot rotates foot about heel->toe axis
pb = pose.bones["foot_l"]
c = pb.constraints.new('COPY_ROTATION'); c.target = roll_foot_l; c.use_z = True
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "roll"
v=drv.driver.variables.new(); v.name="roll"; v.targets[0].id = roll_foot_l; v.targets[0].data_path='["roll"]'
roll_foot_l["roll"] = 0.0

for bname, fkc in (("thigh_r",fk_thigh_r),("shin_r",fk_shin_r),("foot_r",fk_foot_r)):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = fkc; c.influence = 1.0
    drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "1.0 - ik_fk"
    v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_foot_r; v.targets[0].data_path='["ik_fk"]'
pb = pose.bones["foot_r"]
c = pb.constraints.new('IK'); c.target = ik_foot_r; c.pole_target = pole_leg_r; c.chain_count = 3
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "ik_fk"
v=drv.driver.variables.new(); v.name="ik_fk"; v.targets[0].id = ik_foot_r; v.targets[0].data_path='["ik_fk"]'
pb = pose.bones["toe_r"]
c = pb.constraints.new('COPY_TRANSFORMS'); c.target = toe_r_ctrl; c.influence = 1.0
pb = pose.bones["foot_r"]
c = pb.constraints.new('COPY_ROTATION'); c.target = roll_foot_r; c.use_z = True
drv = c.driver_add("influence"); drv.driver.type='SCRIPTED'; drv.driver.expression = "roll"
v=drv.driver.variables.new(); v.name="roll"; v.targets[0].id = roll_foot_r; v.targets[0].data_path='["roll"]'
roll_foot_r["roll"] = 0.0

# --- Spine / Head ---
for bname, ctr in (("spine_01",spine_ctrl),("spine_02",spine_ctrl),("spine_03",spine_ctrl),("neck",head_ctrl),("head",head_ctrl)):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = ctr; c.influence = 1.0
# head look: track to look_ctrl
pb = pose.bones["head"]
c = pb.constraints.new('TRACK_TO'); c.target = look_ctrl; c.track_axis = 'TRACK_Y'; c.up_axis = 'UP_Z'
c.influence = 1.0

# Clavicles follow spine
for bname in ("clavicle_l","clavicle_r"):
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = spine_ctrl; c.influence = 1.0

# --- Eyes follow look (independent L/R) ---
pb = pose.bones["eye_l"]
c = pb.constraints.new('TRACK_TO'); c.target = look_ctrl_l; c.track_axis = 'TRACK_Y'; c.up_axis = 'UP_Z'
c.influence = 1.0
pb = pose.bones["eye_r"]
c = pb.constraints.new('TRACK_TO'); c.target = look_ctrl_r; c.track_axis = 'TRACK_Y'; c.up_axis = 'UP_Z'
c.influence = 1.0

# --- Facial controls -> deform bones ---
face_map = [
    ("jaw", ctrl_jaw), ("lip_upper", ctrl_lip_u), ("lip_lower", ctrl_lip_d),
    ("brow_l", ctrl_brow_l), ("brow_r", ctrl_brow_r), ("cheek_l", ctrl_cheek_l),
    ("cheek_r", ctrl_cheek_r), ("mouth_corner_l", ctrl_mouth_l),
    ("mouth_corner_r", ctrl_mouth_r), ("tongue", ctrl_jaw),
    ("teeth_upper", ctrl_jaw), ("teeth_lower", ctrl_jaw),
]
for bname, ctr in face_map:
    pb = pose.bones[bname]
    c = pb.constraints.new('COPY_TRANSFORMS'); c.target = ctr; c.influence = 1.0
# eyelids
for bname, ctr in (("eyelid_upper_l",ctrl_eyelid_u_l),("eyelid_upper_r",ctrl_eyelid_u_r)):
    pass  # bones not created; skip (we'll add shape keys instead)

# ============ SKINNING ============
# Map mesh object -> primary deform bone(s) with blend
def obj_for(name):
    return bpy.data.objects.get(name)

skin_assignments = {
    # body
    "Head": ["head"], "Torso": ["spine_02","spine_03"], "Neck": ["neck"],
    "Clav_L": ["clavicle_l"], "Clav_R": ["clavicle_r"],
    "UpperArm_L": ["upperarm_l"], "LowerArm_L": ["lowerarm_l"], "Hand_L": ["hand_l"],
    "UpperArm_R": ["upperarm_r"], "LowerArm_R": ["lowerarm_r"], "Hand_R": ["hand_r"],
    "Thigh_L": ["thigh_l"], "Shin_L": ["shin_l"], "Foot_L": ["foot_l"], "Toe_L": ["toe_l"],
    "Thigh_R": ["thigh_r"], "Shin_R": ["shin_r"], "Foot_R": ["foot_r"], "Toe_R": ["toe_r"],
    "ChestArmor": ["spine_02"], "Paul_L": ["clavicle_l","upperarm_l"], "Paul_R": ["clavicle_r","upperarm_r"],
    "ThighArmor_L": ["thigh_l"], "ThighArmor_R": ["thigh_r"],
    "Undershirt": ["spine_02","spine_03","thigh_l","thigh_r"], "Pants": ["thigh_l","thigh_r"],
    "Hair": ["head"],
    # fingers (name pattern Finger{L/R}_{i}_p{j})
    "Eye_L": ["eye_l"], "Eye_R": ["eye_r"], "Pupil_L": ["eye_l"], "Pupil_R": ["eye_r"],
}

def add_armature_mod(obj, arm_obj):
    mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm_obj
    return mod

def weight_mesh(obj, bone_names, blend=0.0):
    """Assign vertices to bones. blend: for multi-bone, distribute by name list equally."""
    mod = add_armature_mod(obj, arm_obj)
    obj.vertex_groups.clear()
    n = len(bone_names)
    for bn in bone_names:
        vg = obj.vertex_groups.new(name=bn)
    # assign all vertices to each bone with weight 1/n (blend) or 1.0 if single
    verts = [v.index for v in obj.data.vertices]
    if n == 1:
        obj.vertex_groups[bone_names[0]].add(verts, 1.0, 'REPLACE')
    else:
        w = 1.0/n
        for bn in bone_names:
            obj.vertex_groups[bn].add(verts, w, 'REPLACE')

# Apply skinning to body parts
for mname, bnames in skin_assignments.items():
    o = obj_for(mname)
    if o and o.type == 'MESH':
        weight_mesh(o, bnames)

# Fingers: each phalanx to its finger bone
for o in bpy.data.objects:
    if o.type == 'MESH' and o.name.startswith("Finger"):
        # bone name e.g. thumb_1_l ... find matching
        bname = None
        for side in ("l","r"):
            if f"Finger{side.upper()}" in o.name or f"Finger{side}" in o.name:
                pass
        # parse: FingerL_0_p1 -> thumb_1_l
        import re
        m = re.match(r"Finger([LR])_(\d)_p(\d)", o.name)
        if m:
            side = m.group(1).lower()
            fi = int(m.group(2))  # 0..4
            pj = int(m.group(3))  # 1..3
            bn = f"{finger_names[fi]}_{pj}_{side}"
            if bn in arm.edit_bones if False else bn in [b.name for b in arm_obj.data.bones]:
                weight_mesh(o, [bn])

print("Rig + skinning built.")
bpy.ops.wm.save_mainfile(filepath=BLEND)
print("Saved", BLEND)
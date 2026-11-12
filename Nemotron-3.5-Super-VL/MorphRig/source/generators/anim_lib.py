#!/usr/bin/env python3
"""MORPHRIG animation library: helpers to key deform bones + shape keys at 30fps."""
import bpy
import math
from mathutils import Vector, Euler, Quaternion, Matrix

BLEND = "/home/candidate/workspace/MorphRig/source/Operative.blend"
FPS = 30.0

ARM = "Operative_Armature"
HEAD_MESH = "Head"

DEFORM_BONES = [
 "root","pelvis","spine_01","spine_02","spine_03","neck","head",
 "clavicle_l","clavicle_r",
 "upperarm_l","lowerarm_l","hand_l","upperarm_r","lowerarm_r","hand_r",
 "thumb_1_l","thumb_2_l","thumb_3_l","index_1_l","index_2_l","index_3_l",
 "middle_1_l","middle_2_l","middle_3_l","ring_1_l","ring_2_l","ring_3_l",
 "pinky_1_l","pinky_2_l","pinky_3_l",
 "thumb_1_r","thumb_2_r","thumb_3_r","index_1_r","index_2_r","index_3_r",
 "middle_1_r","middle_2_r","middle_3_r","ring_1_r","ring_2_r","ring_3_r",
 "pinky_1_r","pinky_2_r","pinky_3_r",
 "thigh_l","shin_l","foot_l","toe_l","thigh_r","shin_r","foot_r","toe_r",
 "eye_l","eye_r",
 "jaw","lip_upper","lip_lower","brow_l","brow_r","cheek_l","cheek_r",
 "mouth_corner_l","mouth_corner_r","tongue","teeth_upper","teeth_lower",
]

def open_blend():
    bpy.ops.wm.open_mainfile(filepath=BLEND)

def armature():
    return bpy.data.objects[ARM]

def pose_bone(arm, bname):
    return arm.pose.bones[bname]

def reset_pose(arm):
    for b in arm.pose.bones:
        b.location = Vector((0,0,0))
        b.rotation_euler = Euler((0,0,0),'XYZ')
        b.scale = Vector((1,1,1))
        b.keyframe_insert_delete("location")
        b.keyframe_insert_delete("rotation_euler")
        b.keyframe_insert_delete("scale")
    ob = bpy.data.objects.get(HEAD_MESH)
    if ob and ob.data.shape_keys:
        for kb in ob.data.shape_keys.key_blocks:
            kb.value = 0.0
            kb.keyframe_insert_delete("value")

def key_location(pb, frame, loc):
    pb.location = Vector(loc)
    pb.keyframe_insert(data_path="location", frame=frame)

def key_rotation(pb, frame, eul):
    pb.rotation_euler = Euler(eul, 'XYZ')
    pb.keyframe_insert(data_path="rotation_euler", frame=frame)

def key_scale(pb, frame, s):
    pb.scale = Vector(s)
    pb.keyframe_insert(data_path="scale", frame=frame)

def key_shape(ob, frame, name, value):
    kb = ob.data.shape_keys.key_blocks[name]
    kb.value = value
    kb.keyframe_insert(data_path="value", frame=frame)

def make_action(name):
    if name in bpy.data.actions:
        return bpy.data.actions[name]
    return bpy.data.actions.new(name)

def bind_action(arm, action):
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = action

def set_fcurve_interp(action, interp='LINEAR'):
    for fc in action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = interp

def finish_action(arm, action, frame_start, frame_end, loop=False):
    bind_action(arm, action)
    set_fcurve_interp(action)
    # set action range
    action.frame_range[0] = frame_start
    action.frame_range[1] = frame_end
    # ensure a key at end for loops to close
    return action

RAD = math.pi/180.0

def ease(t):  # smoothstep
    return t*t*(3-2*t)

def lerp(a,b,t):
    return a + (b-a)*t

# Locomotion gait parameters
GAIT = {
 "walk": {"step":0.60,"bob":0.025,"swing":0.16,"knee":35,"rate":1.0},
 "run":  {"step":0.85,"bob":0.05,"swing":0.24,"knee":55,"rate":1.6},
 "sprint":{"step":1.05,"bob":0.08,"swing":0.32,"knee":70,"rate":2.2},
}

def locomotion_cycle(arm, gtype, direction, frames, loop=True):
    """direction: (dx,dy) unit vector in the character's forward plane (X right, Y forward)."""
    g = GAIT[gtype]
    ob = bpy.data.objects.get(HEAD_MESH)
    half = frames//2
    for f in range(frames+1):
        t = f/frames
        phase = t*2*math.pi  # one cycle over the frames
        # foot phase: left foot forward at phase 0, right at pi
        # body bob
        bob = abs(math.sin(phase)) * g["bob"]
        # hips
        key_location(pose_bone(arm,"pelvis"), f, (0,0,0.95+bob))
        key_location(pose_bone(arm,"spine_01"), f, (0,0,0.05*math.sin(phase)))
        # lean into direction
        lean = 0.12*direction[0]
        key_rotation(pose_bone(arm,"spine_03"), f, (0,0,lean))
        key_rotation(pose_bone(arm,"neck"), f, (0,0,-lean*0.5))
        # arm swing (opposite to legs)
        armswing = 0.25*math.sin(phase)
        key_rotation(pose_bone(arm,"upperarm_l"), f, (0, armswing*0.6, -armswing*0.4))
        key_rotation(pose_bone(arm,"lowerarm_l"), f, (0,0, armswing*0.5))
        key_rotation(pose_bone(arm,"upperarm_r"), f, (0, -armswing*0.6, armswing*0.4))
        key_rotation(pose_bone(arm,"lowerarm_r"), f, (0,0, -armswing*0.5))
        # legs
        for side, off in (("l",0.0),("r",math.pi)):
            p = phase + off
            # foot plant: when sin(p)<0 the foot is back (pushing), when >0 forward (swing)
            swing_amp = g["swing"]
            # thigh swing forward/back
            thigh_swing = swing_amp*math.sin(p)
            key_rotation(pose_bone(arm,"thigh_"+side), f, (thigh_swing, 0.0, 0.0))
            # knee bend: max when leg is swinging forward (mid-swing)
            knee = g["knee"]*RAD * max(0.0, math.sin(p))
            key_rotation(pose_bone(arm,"shin_"+side), f, (knee, 0.0, 0.0))
            # foot placement: lift during swing
            lift = g["step"]*0.5 * max(0.0, math.sin(p)) if math.sin(p)>0 else 0.0
            # foot position relative: forward when swinging
            fwd = swing_amp*0.6*math.sin(p)
            side_off = (0.09 if side=='l' else -0.09) + 0.03*math.cos(p)
            key_location(pose_bone(arm,"foot_"+side), f, (side_off, fwd, -lift))
            key_rotation(pose_bone(arm,"foot_"+side), f, (-knee*0.5, 0.0, 0.0))
            key_location(pose_bone(arm,"toe_"+side), f, (0.0,0.0,0.0))
        # head bob
        key_location(pose_bone(arm,"head"), f, (0,0,0.03*bob))
    return frames
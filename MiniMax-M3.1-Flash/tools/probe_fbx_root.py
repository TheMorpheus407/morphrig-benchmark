"""Probe an exported animation FBX for root bone translation.

Re-imports the FBX into an empty Blender scene and prints the world space
location of the armature root bone over the length of the take.  Used to prove
whether the dash clips really carry the 2 m of root translation into Unreal.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
path = argv[0] if argv else ""

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=True)

arm = None
for obj in bpy.context.scene.objects:
    if obj.type == "ARMATURE":
        arm = obj
        break

if arm is None:
    print("PROBE no armature in %s" % path)
    sys.exit(0)

root = arm.data.bones[0]
print("PROBE file=%s root_bone=%s frames=%d fps=%.3f" %
      (os.path.basename(path), root.name, arm.animation_data.action.frame_range[1]
       if arm.animation_data and arm.animation_data.action else 0,
       bpy.context.scene.render.fps))

action = arm.animation_data.action if arm.animation_data else None
if action is None:
    print("PROBE no action")
    sys.exit(0)

def all_fcurves(action):
    """Blender 5 slotted actions: walk the layers and their channel bags."""
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


found = 0
for fc in all_fcurves(action):
    if fc.data_path.startswith('pose.bones["%s"]' % root.name):
        print("PROBE root fcurve %s" % fc.data_path)
        for kp in fc.keyframe_points:
            print("PROBE   key f=%.3f v=%.4f" % (kp.co[0], kp.co[1]))
        found += 1
if not found:
    for fc in all_fcurves(action):
        if "location" in fc.data_path:
            print("PROBE loc fcurve %s keys=%d first=%.4f last=%.4f" %
                  (fc.data_path, len(fc.keyframe_points),
                   fc.keyframe_points[0].co[1] if len(fc.keyframe_points) else 0.0,
                   fc.keyframe_points[-1].co[1] if len(fc.keyframe_points) else 0.0))

# world space sample of the root bone
scene = bpy.context.scene
for f in (0.0, 3.0, 6.0, 9.0, 12.0, 14.0):
    scene.frame_set(int(f))
    pb = arm.pose.bones[root.name]
    print("PROBE frame=%.1f world_loc=(%.4f, %.4f, %.4f)" %
          (f, pb.matrix_world.translation.x, pb.matrix_world.translation.y,
           pb.matrix_world.translation.z))

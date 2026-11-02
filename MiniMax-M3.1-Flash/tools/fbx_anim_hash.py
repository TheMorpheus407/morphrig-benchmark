"""Print a hash of the animation data inside an exported FBX.

    blender -b --factory-startup -P tools/fbx_anim_hash.py -- <file.fbx>

Two exports of the same clip have to produce the same hash.  The FBX binary
format stores its records with byte offsets, so two files of the same content
differ in size by a fixed metadata block and cannot be compared byte by byte.
This script imports the file and hashes every animated bone channel instead,
which is what the Unreal importer actually reads.
"""
import hashlib
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
    print("HASH %s no armature" % os.path.basename(path))
    sys.exit(0)

action = arm.animation_data.action
channels = []
for bag in action.layers[0].strips[0].channelbags:
    for fc in bag.fcurves:
        values = []
        for key in fc.keyframe_points:
            values.append((round(key.co[0], 4), round(key.co[1], 6),
                           round(key.handle_left[1], 6),
                           round(key.handle_right[1], 6)))
        channels.append((fc.data_path, fc.array_index, tuple(values)))

channels.sort()
digest = hashlib.sha256(repr(channels).encode("utf-8")).hexdigest()
print("HASH %s bones=%d channels=%d keys=%d sha256=%s"
      % (os.path.basename(path), len(arm.data.bones), len(channels),
         sum(len(c[2]) for c in channels), digest))

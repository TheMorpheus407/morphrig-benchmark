"""Render baked clips so the motion can be inspected visually.

    blender -b --factory-startup -P source/generators/render_clips.py -- \
        --outdir /tmp/morphrig_clips

Renders a grid of poses for a handful of representative clips.
"""

import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import build_preview_lib as P  # noqa: E402


CLIPS = [
    ("idle_relaxed", [1, 30, 60]),
    ("walk_f", [1, 8, 15, 23]),
    ("run_f", [1, 6, 12, 18]),
    ("idle_combat", [1, 30]),
    ("aim_level_center", [1]),
    ("aim_up_left", [1]),
    ("aim_down_right", [1]),
    ("melee_1", [1, 10, 13, 18, 24]),
    ("reload", [1, 12, 24]),
    ("jump_air", [1, 15]),
    ("prone_front", [1, 30]),
    ("prone_back", [1, 30]),
    ("death_front", [1, 30, 60]),
    ("greet", [1, 20, 48]),
    ("dash_f", [1, 10, 19]),
]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    outdir = "/tmp/morphrig_clips"
    if "--outdir" in argv:
        outdir = argv[argv.index("--outdir") + 1]
    root = os.path.abspath(os.path.join(HERE, "..", ".."))
    blend = os.path.join(root, "source", "Operative.blend")
    bpy.ops.wm.open_mainfile(filepath=blend)

    arm = bpy.data.objects.get("Operative_Rig")
    scn = bpy.context.scene
    scn.frame_start = 1
    scn.frame_end = 600

    cam = P.setup_render(res=(360, 540), samples=16)
    os.makedirs(outdir, exist_ok=True)
    dist = 4.0
    target = Vector((0.0, 0.0, 0.95))
    cam.data.ortho_scale = 2.15
    cam.location = (target.x + dist * math.sin(math.radians(22)) *
                    math.cos(math.radians(8)),
                    target.y - dist * math.cos(math.radians(22)) *
                    math.cos(math.radians(8)),
                    target.z + dist * math.sin(math.radians(8)))
    d = target - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    for clip_name, frames in CLIPS:
        act = bpy.data.actions.get("ACT_%s" % clip_name)
        if act is None:
            print("RENDER_MISSING %s" % clip_name)
            continue
        arm.animation_data.action = act
        for f in frames:
            scn.frame_set(f)
            scn.render.filepath = os.path.join(
                outdir, "clip_%s_%03d.png" % (clip_name, f))
            bpy.ops.render.render(write_still=True)
            print("RENDERED %s @ %d" % (clip_name, f))
    print("RENDER_DONE %s" % outdir)


import math  # noqa: E402

main()

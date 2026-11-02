"""Bake the MorphRig motion inventory.

    blender -b --factory-startup -P source/generators/build_animations.py -- \
        [--blend source/Operative.blend] [--out source/Operative.blend]

Creates one Blender action per required clip on the armature (plus a face
action for the shape keys) and writes `docs/animation_manifest.json`.
"""

import os
import sys
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy

import mr_anim
import mr_clips


REQUIRED = []


def load_required(path):
    ids = []
    with open(path) as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line or i == 0:
                continue
            parts = line.split(",")
            ids.append(parts[0])
    return ids


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(flag, default=None):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    root = os.path.abspath(os.path.join(HERE, "..", ".."))
    blend = arg("--blend", os.path.join(root, "source", "Operative.blend"))
    out = arg("--out", blend)
    manifest_path = arg("--manifest",
                         os.path.join(root, "docs", "animation_manifest.json"))
    required = load_required(os.path.join(root, "required_animations.csv"))

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    arm_obj = bpy.data.objects.get("Operative_Rig")
    body = bpy.data.objects.get("Operative_Body")
    if arm_obj is None:
        raise SystemExit("Operative_Rig not found in %s" % blend)
    rig = mr_anim.Rig(arm_obj)

    # The scene frame rate decides what the FBX exporter writes into the
    # header, and Unreal reads it back as the sample rate of the imported
    # sequence.  Blender defaults to 24 fps, the production is authored at 30.
    scene = bpy.context.scene
    scene.render.fps = mr_anim.FPS
    scene.render.fps_base = 1.0

    # Remove the actions of an earlier bake.  Blender would otherwise keep
    # them and rename the new ones to ACT_walk_f.001 and so on, which would
    # end up as extra clips in the export.
    if arm_obj.animation_data:
        arm_obj.animation_data.action = None
    if body.data.shape_keys and body.data.shape_keys.animation_data:
        body.data.shape_keys.animation_data.action = None
    stale = [a for a in bpy.data.actions if a.name.startswith("ACT_")]
    for action in stale:
        bpy.data.actions.remove(action, do_unlink=True)
    if stale:
        print("ANIM_CLEANED %d stale actions" % len(stale))

    have = set(c["name"] for c in mr_clips.CLIPS)
    missing = [r for r in required if r not in have]
    extra = [c for c in have if c not in required]
    if missing:
        raise SystemExit("missing clips: %s" % ", ".join(missing))
    if extra:
        print("ANIM_WARN extra clips: %s" % ", ".join(sorted(extra)))

    t0 = time.time()
    results = []
    for c in mr_clips.CLIPS:
        if c["name"] not in required:
            continue
        res = mr_anim.bake(rig, arm_obj, body, c, bpy.context.scene)
        results.append(res)
        print("ANIM_BAKED %-20s frames=%3d dur=%.2fs loop=%s markers=%d"
              % (res["name"], res["frames"], res["duration"], res["loop"],
                 len(res["markers"])))

    # organise the actions into collections for the animator
    coll = bpy.data.collections.get("MR_Animations")
    if coll is None:
        coll = bpy.data.collections.new("MR_Animations")
        bpy.context.scene.collection.children.link(coll)

    # the armature keeps the first clip active so the file opens on a pose
    arm_obj.animation_data.action = bpy.data.actions.get("ACT_idle_combat")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print("ANIM_SAVED %s" % out)

    manifest = {
        "character": "Operative",
        "fps": 30,
        "units": "meters",
        "forward_axis": "-Y",
        "up_axis": "+Z",
        "source": "source/generators/mr_clips.py",
        "clips": results,
    }
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print("ANIM_MANIFEST %s (%d clips)" % (manifest_path, len(results)))
    print("ANIM_DONE %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()

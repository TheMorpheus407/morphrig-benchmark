"""Validate the `mr_anim.Pose` math against Blender's own evaluation.

For a set of representative clips the script:
  1. builds the pose with `mr_clips`,
  2. resolves it to Blender basis matrices,
  3. writes them onto the armature,
  4. lets Blender evaluate the rig,
  5. compares every bone's evaluated matrix against the matrix the pose
     system intended.

Any mismatch means the authoring convention is wrong.
"""

import json
import os
import sys

import bpy
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mr_anim           # noqa: E402
import mr_clips          # noqa: E402

BLEND = os.path.join(HERE, "..", "Operative.blend")
REPORT = {}


def load():
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(BLEND))
    arm = bpy.data.objects.get("Operative_Rig")
    if arm is None:
        for o in bpy.data.objects:
            if o.type == 'ARMATURE':
                arm = o
                break
    mesh = bpy.data.objects.get("Operative")
    if mesh is None:
        for o in bpy.data.objects:
            if o.type == 'MESH':
                mesh = o
                break
    return arm, mesh


def reset_pose(arm):
    """Return every bone to its rest transform."""
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def compare(pose, arm, rig, tag, errs):
    reset_pose(arm)
    basis, shapes = pose.resolve()
    for name, mat in basis.items():
        pb = arm.pose.bones[name]
        loc, rot, sc = mat.decompose()
        pb.location = loc
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = rot
        pb.scale = sc
    sk = mesh.data.shape_keys if mesh is not None else None
    if sk is not None:
        for key, val in shapes.items():
            block = sk.key_blocks.get(key)
            if block is not None:
                block.value = val
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = arm.evaluated_get(dg)
    for name, want in pose.world.items():
        pb = ev.pose.bones.get(name)
        if pb is None:
            errs.append("%s: bone %s missing in eval" % (tag, name))
            continue
        got = pb.matrix.copy()
        d = max(abs(got[r][c] - want[r][c]) for r in range(4) for c in range(4))
        if d > 1e-4:
            errs.append("%s: %s matrix diff %.6f" % (tag, name, d))
    # shape keys
    sk = mesh.data.shape_keys if mesh is not None else None
    if sk is not None:
        for key, val in shapes.items():
            block = sk.key_blocks.get(key)
            if block is None:
                errs.append("%s: shape key %s missing" % (tag, key))
                continue
            if abs(block.value - val) > 1e-4:
                errs.append("%s: shape key %s value %.4f != %.4f"
                            % (tag, key, block.value, val))


arm, mesh = load()
REPORT["armature"] = arm.name
REPORT["mesh"] = mesh.name
rig = mr_anim.Rig(arm)
REPORT["bones"] = len(rig.rest)
REPORT["deform_bones"] = len(rig.deform)

TESTS = ["idle_relaxed", "walk_f", "run_f", "aim_level_center", "melee_1",
         "prone_front", "dash_f", "greet", "jump_air", "charge_release",
         "death_front", "uplink_loop", "hit_f", "reload", "cast_ground"]

errs = []
checked = 0
for clip_name in TESTS:
    spec = mr_clips.CLIP_INDEX.get(clip_name)
    if spec is None:
        errs.append("missing clip %s" % clip_name)
        continue
    frames = spec["frames"]
    picks = sorted({0, frames // 4, frames // 2, (3 * frames) // 4,
                    frames - 1})
    for fi in picks:
        t = fi / float(frames)
        pose = spec["fn"](t, rig)
        compare(pose, arm, rig, "%s@%d" % (clip_name, fi), errs)
        checked += 1

REPORT["poses_checked"] = checked
REPORT["errors"] = errs[:60]
REPORT["error_count"] = len(errs)

print("VALIDATE_BEGIN")
print(json.dumps(REPORT))
print("VALIDATE_END")

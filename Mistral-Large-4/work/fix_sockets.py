"""Rebuild the 12 socket empties in source/Operative_rig.blend.

The original empties were broken: gen_02 set matrix_world BEFORE parenting to
the bone, and a direct .parent assignment does not keep the world transform,
so every socket landed at a nonsense position.

Empirically (verified on Blender 5.1.1, see work/probe_sockets.py and
work/debug_parent.py), an object parented to a bone with matrix_basis B has,
at rest pose:

    world = P @ B,   P = bone.matrix_local @ Translation(0, bone.length, 0)

i.e. the object's basis is relative to the bone's TAIL frame (note that
bone.matrix_local has a unit Y column; the bone length lives in bone.length).
When the bone is posed the socket keeps its rest-relative transform:

    world_pose = pose_bone.matrix @ bone.matrix_local.inverted() @ world_rest

So the correct basis for a desired rest world matrix T is  P^-1 @ T.  This
script measures P per bone at runtime (identity-basis probe), so it does not
depend on the formula above.

Sockets (SPEC: right/left hand, emitter muzzle, blade base/tip and effect
anchors).  Positions are anatomical, measured from the mesh:
  - wrist cannon gadget front face at y = -0.065, emitter bone at y = +0.055
  - palm blade front point at y = -0.078, blade bone at y = -0.05
  - palms 6 cm down the hand bone, 2.5 cm along the palm normal
  - eyes at y = -0.095 z = 1.645, head top z = 1.79

Output:
  - source/Operative_rig.blend: 12 correct socket empties + synced rig_ops text
  - work/socket_data.json: per-socket world + bone-local matrices (for
    docs/skeleton_and_sockets.json and the UE socket import)
  - work/rig_spec.json: "sockets" array updated to the new format
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector, Matrix

TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
BLEND = os.path.join(TASK, "source", "Operative_rig.blend")
RIG_OPS = os.path.join(TASK, "tools", "rig_ops.py")
RIG_SPEC = os.path.join(TASK, "work", "rig_spec.json")
SOCKET_DATA = os.path.join(TASK, "work", "socket_data.json")
sys.path.insert(0, os.path.join(TASK, "tools"))
import rig_ops  # noqa: E402

bpy.ops.wm.open_mainfile(filepath=BLEND)
A = bpy.data.objects["Armature"]
ad = A.data
sc = bpy.context.scene

rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()

# barrel/blade socket orientation: +Y along the barrel (world -Y at rest),
# +Z up (world +Z) -> 180 deg rotation about world Z
R_BARREL = Matrix.Rotation(math.pi, 4, 'Z')


def palm_world(bone):
    """Palm center: 6 cm down the hand bone, 2.5 cm along the palm normal."""
    head = bone.matrix_local.to_translation()
    y = (bone.matrix_local.to_3x3().col[1]).normalized()
    z = (bone.matrix_local.to_3x3().col[2]).normalized()
    return head + 0.06 * y + 0.025 * z


# name, parent bone, world rest position, rotation mode, note
SOCKETS = [
    ("eye",          "head",       Vector((0.0, -0.115, 1.65)),  "world",
     "between the eyes, 2 cm in front of the eye line (face camera anchor)"),
    ("head",         "head",       Vector((0.0, 0.0, 1.79)),     "world",
     "top of the head (helmet / overhead camera anchor)"),
    ("hand_l",       "hand_L",     None,                        "world",
     "left palm center (grip / IK anchor)"),
    ("hand_r",       "hand_R",     None,                        "world",
     "right palm center (grip / IK anchor)"),
    ("weapon_r",     "emitter",    Vector((0.245, 0.055, 0.85)), "barrel",
     "wrist cannon mount origin; socket +Y points along the barrel"),
    ("muzzle_flash", "emitter",    Vector((0.245, -0.065, 0.85)), "barrel",
     "front face of the wrist cannon (muzzle flash spawn); +Y along the barrel"),
    ("blade_base",   "blade",      Vector((0.245, -0.05, 0.85)), "barrel",
     "base of the palm blade; +Y along the blade"),
    ("blade_tip",    "blade",      Vector((0.245, -0.078, 0.85)), "barrel",
     "tip of the palm blade; +Y along the blade"),
    ("cell_holster", "cell_new",   Vector((-0.199, 0.022, 0.9325)), "world",
     "fresh power cell on the left hip (holster slot)"),
    ("cell_emitter", "cell_spent", Vector((0.282, 0.015, 0.80)), "world",
     "spent cell slot on the right hip (reload target)"),
    ("beacon",       "beacon",     Vector((0.0, 0.24, 1.36)),    "world",
     "backpack beacon tip (effect anchor)"),
    ("backpack",     "spine_03",   Vector((0.0, 0.10, 1.42)),    "world",
     "upper back strap point"),
]

# ---- delete the broken empties
for o in list(bpy.data.objects):
    if o.name.startswith("socket_"):
        bpy.data.objects.remove(o)

# ---- rebuild
report = []
for name, bone_name, world, rot_mode, note in SOCKETS:
    bone = ad.bones[bone_name]
    if world is None:
        world = palm_world(bone)
    R = R_BARREL if rot_mode == "barrel" else Matrix.Identity(4)
    target = Matrix.Translation(world) @ R
    e = bpy.data.objects.new("socket_" + name, None)
    e.empty_display_type = 'CONE'
    e.empty_display_size = 0.02
    e.show_name = True
    sc.collection.objects.link(e)
    e.parent = A
    e.parent_type = 'BONE'
    e.parent_bone = bone_name
    # measure the bone-parent matrix P with an identity basis
    e.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    P = e.matrix_world.copy()
    # sanity: P must be arm_mat @ Translation(0, bone.length, 0), i.e. the
    # object's basis is relative to the bone's TAIL frame (bone.matrix_local
    # has a unit Y column; the length lives in bone.length)
    P_formula = bone.matrix_local @ Matrix.Translation(Vector((0.0, bone.length, 0.0)))
    ferr = max(abs((P - P_formula)[i][j]) for i in range(4) for j in range(4))
    assert ferr < 1e-6, "bone-parent formula mismatch on %s: %g" % (bone_name, ferr)
    # correct basis for the desired rest world matrix
    e.matrix_basis = P.inverted() @ target
    bpy.context.view_layer.update()
    err = max(abs((e.matrix_world - target)[i][j]) for i in range(4) for j in range(4))
    assert err < 1e-6, "socket %s rest placement err %g" % (name, err)
    # bone-local matrix (relative to the bone rest frame) for UE + docs
    local = bone.matrix_local.inverted() @ target
    report.append({
        "name": name,
        "bone": bone_name,
        "world_rest": [list(row) for row in target],
        "local": [list(row) for row in local],
        "rot_mode": rot_mode,
        "note": note,
    })
    print("  socket_%-13s bone=%-10s world=%s  rest_err=%.2e" %
          (name, bone_name, [round(v, 4) for v in world], err))

# ---- posed verification: sockets must follow their bone rigidly
fpb = A.pose.bones["forearm_R"]
fpb.rotation_euler = (math.radians(30), 0.0, math.radians(10))
bpy.context.view_layer.update()
worst = 0.0
for name, bone_name, world, rot_mode, note in SOCKETS:
    if bone_name not in ("emitter", "blade", "hand_R"):
        continue
    bone = ad.bones[bone_name]
    e = bpy.data.objects["socket_" + name]
    target = Matrix.Translation(world if world is not None else palm_world(bone)) \
        @ (R_BARREL if rot_mode == "barrel" else Matrix.Identity(4))
    pb = A.pose.bones[bone_name]
    expected = pb.matrix @ bone.matrix_local.inverted() @ target
    err = max(abs((e.matrix_world - expected)[i][j]) for i in range(4) for j in range(4))
    worst = max(worst, err)
    print("  posed follow %-13s err=%.2e" % (name, err))
assert worst < 1e-5, "posed follow broken: %g" % worst
print("posed follow OK (worst %.2e)" % worst)

# ---- back to rest, save
rig_ops.reset_pose()
rig_ops.apply_controls()
bpy.context.view_layer.update()

# ---- sync the embedded rig_ops Text datablock
src = open(RIG_OPS).read()
txt = bpy.data.texts.get("rig_ops.py")
if txt is None:
    txt = bpy.data.texts.new("rig_ops.py")
txt.clear()
txt.write(src)
txt.use_module = True
print("embedded rig_ops.py synced (%d bytes, use_module=%s)" % (len(src), txt.use_module))

bpy.ops.wm.save_mainfile(filepath=BLEND)
print("saved", BLEND)

# ---- dump socket data + update rig_spec.json
json.dump(report, open(SOCKET_DATA, "w"), indent=1)
spec = json.load(open(RIG_SPEC))
spec["sockets"] = [{"name": r["name"], "bone": r["bone"],
                    "world": [r["world_rest"][i][j] for i in range(3) for j in range(3)],
                    "world_t": [r["world_rest"][i][3] for i in range(3)],
                    "rot_mode": r["rot_mode"], "note": r["note"]} for r in report]
json.dump(spec, open(RIG_SPEC, "w"), indent=1)
print("wrote", SOCKET_DATA, "and updated rig_spec.json sockets")

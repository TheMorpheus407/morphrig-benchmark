"""gen_02_rig.py — build the deformation skeleton, facial shape keys, the
animator control rig and socket empties on top of source/Operative.blend.

Output: source/Operative_rig.blend
  - mesh "Operative" (+ 10 facial shape keys) parented to armature "Armature"
    with an Armature modifier (vertex groups from gen_01 match the 79 bones)
  - "Armature": the exportable deformation skeleton, exactly the 79 bones of
    work/rig_spec.json (names + order), explicit rest frames (documented axes)
  - "Operative_Controls": interactive animator control rig (FK chains, IK
    targets + pole vectors, foot roll, finger curl/spread, face controls,
    look-at, secondary motion) with a sidebar panel and bake/match/reset
    operators (tools/rig_ops.py, embedded as a registered Text datablock)
  - socket empties for every socket in the rig spec (visual reference; the
    Unreal sockets are created at import time from docs/skeleton_and_sockets.json)
"""
import bpy
import json
import math
import os
import sys
from mathutils import Vector, Matrix

GEN_DIR = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(os.path.dirname(GEN_DIR))
sys.path.insert(0, GEN_DIR)

from morphrig_lib import (bone_frame, x_hint_for, set_eb_frame,  # noqa: E402
                          clamp, smoothstep, FPS)

BLEND_IN = os.path.join(TASK, "source", "Operative.blend")
BLEND_OUT = os.path.join(TASK, "source", "Operative_rig.blend")
RIG_SPEC = os.path.join(TASK, "work", "rig_spec.json")
RIG_OPS = os.path.join(TASK, "tools", "rig_ops.py")

SPEC = json.load(open(RIG_SPEC))
BONES = SPEC["bones"]
SOCKETS = SPEC["sockets"]
MOUTH_C = Vector(SPEC["mouth_center"])

bpy.ops.wm.open_mainfile(filepath=BLEND_IN)
sc = bpy.context.scene
sc.render.fps = FPS
obj = bpy.data.objects["Operative"]
me = obj.data
print("MESH verts:", len(me.vertices), "faces:", len(me.polygons),
      "materials:", len(me.materials))

# ===================================================================== shape keys
# Facial morph targets (hybrid bone + shape-key facial rig, SPEC section 7).
LIP_RX, LIP_RZ = 0.046, 0.0075
N_OV = 128
OVAL = [Vector((LIP_RX * math.cos(2 * math.pi * i / N_OV), MOUTH_C.y,
                MOUTH_C.z + LIP_RZ * math.sin(2 * math.pi * i / N_OV)))
        for i in range(N_OV)]

def oval_dist(c):
    best = 1e9
    for o in OVAL:
        d = math.hypot(c.x - o.x, c.z - o.z)
        if d < best:
            best = d
    return best

# per-vertex material index (from adjacent polygons)
vert_mat = {}
for p in me.polygons:
    for vi in p.vertices:
        vert_mat[vi] = p.material_index

lip_verts = []      # the lip torus (skin), upper -> head / lower -> jaw weighted
cheek_verts = []    # face skin beside the mouth / under the eyes
tongue_verts = []   # tongue fan (mouth material)
for vi, v in enumerate(me.vertices):
    c = v.co
    if abs(c.y - MOUTH_C.y) < 0.012 and 1.545 < c.z < 1.585 and abs(c.x) < 0.060:
        if oval_dist(c) < 0.015:
            lip_verts.append(vi)
    if -0.125 < c.y < -0.055 and 1.575 < c.z < 1.635 and 0.030 < abs(c.x) < 0.100:
        cheek_verts.append(vi)
    if -0.062 < c.y < -0.048 and abs(c.x) < 0.020 and 1.545 < c.z < 1.567:
        if (c.x / 0.018) ** 2 + ((c.z - 1.556) / 0.011) ** 2 <= 1.0:
            tongue_verts.append(vi)
lip_verts = [vi for vi in lip_verts if vert_mat.get(vi) == 0]
cheek_verts = [vi for vi in cheek_verts if vert_mat.get(vi) == 0 and vi not in set(lip_verts)]
tongue_verts = [vi for vi in tongue_verts if vert_mat.get(vi) == 7]
print("SHAPEKEY verts: lip=%d cheek=%d tongue=%d" %
      (len(lip_verts), len(cheek_verts), len(tongue_verts)))

def corner_w(c):
    return smoothstep(clamp((abs(c.x) - 0.030) / 0.020, 0.0, 1.0))

MORPHS = {
    # seal the lips: upper lip down, lower lip up, both slightly forward
    "lip_close": {vi: Vector((0.0, -0.0015, (-1.0 if me.vertices[vi].co.z > MOUTH_C.z else 1.0) * 0.0045))
                  for vi in lip_verts},
    # smile / frown: mouth corners up-back / down (asymmetric capable, per side)
    "smile_L": {vi: Vector((0.0, 0.0020 * corner_w(me.vertices[vi].co), 0.0050 * corner_w(me.vertices[vi].co)))
                for vi in lip_verts if me.vertices[vi].co.x < 0},
    "smile_R": {vi: Vector((0.0, 0.0020 * corner_w(me.vertices[vi].co), 0.0050 * corner_w(me.vertices[vi].co)))
                for vi in lip_verts if me.vertices[vi].co.x > 0},
    "frown_L": {vi: Vector((0.0, 0.0, -0.0040 * corner_w(me.vertices[vi].co)))
                for vi in lip_verts if me.vertices[vi].co.x < 0},
    "frown_R": {vi: Vector((0.0, 0.0, -0.0040 * corner_w(me.vertices[vi].co)))
                for vi in lip_verts if me.vertices[vi].co.x > 0},
    # horizontal lip stretch (wide / narrow)
    "lip_width": {vi: Vector((0.20 * me.vertices[vi].co.x, 0.0, 0.0)) for vi in lip_verts},
    # pucker / funnel: lips forward, opening rounds and shrinks
    "pucker": {vi: Vector((-0.30 * me.vertices[vi].co.x, -0.0075,
                          -0.45 * (me.vertices[vi].co.z - MOUTH_C.z))) for vi in lip_verts},
    # cheek raise (under-eye / beside-mouth skin moves up and outward)
    "cheek_L": {vi: Vector((-0.0030, 0.0012, 0.0035)) for vi in cheek_verts
                if me.vertices[vi].co.x < 0},
    "cheek_R": {vi: Vector((0.0030, 0.0012, 0.0035)) for vi in cheek_verts
                if me.vertices[vi].co.x > 0},
    # tongue out: tip lifts toward the upper teeth (tongue-to-teeth visemes)
    "tongue_out": {},
}
for vi in tongue_verts:
    c = me.vertices[vi].co
    f = 1.0 - 0.5 * ((c.x / 0.016) ** 2 + ((c.z - 1.556) / 0.009) ** 2)
    MORPHS["tongue_out"][vi] = Vector((0.0, -0.0085 * f, 0.0085 * f))

obj.shape_key_add(name="Basis", from_mix=False)
for name, deltas in MORPHS.items():
    sk = obj.shape_key_add(name=name, from_mix=False)
    for vi, d in deltas.items():
        sk.data[vi].co = me.vertices[vi].co + d
    sk.slider_min = -1.0
    sk.slider_max = 1.0
    sk.value = 0.0
print("SHAPEKEYS:", [kb.name for kb in me.shape_keys.key_blocks])

# ===================================================================== deformation armature
adata = bpy.data.armatures.new("OperativeSkeleton")
A = bpy.data.objects.new("Armature", adata)
sc.collection.objects.link(A)
adata.display_type = 'OCTAHEDRAL'
bpy.context.view_layer.objects.active = A
bpy.ops.object.mode_set(mode='EDIT')
ebs = {}
for b in BONES:
    eb = adata.edit_bones.new(b["name"])
    hint = x_hint_for(b["name"], b["head"], b["tail"])
    set_eb_frame(eb, bone_frame(b["head"], b["tail"], hint))
    eb.use_deform = True
    eb.use_connect = False
    ebs[b["name"]] = eb
for b in BONES:
    if b["parent"]:
        ebs[b["name"]].parent = ebs[b["parent"]]
bpy.ops.object.mode_set(mode='OBJECT')
adata.pose_position = 'POSE'
print("ARMATURE bones:", len(adata.bones))

# ===================================================================== control rig
cdata = bpy.data.armatures.new("OperativeControls")
C = bpy.data.objects.new("Operative_Controls", cdata)
sc.collection.objects.link(C)
cdata.display_type = 'OCTAHEDRAL'

def spec_bone(name):
    return next(b for b in BONES if b["name"] == name)

CTRL_BONES = []  # (name, head, tail, parent_name, hint)
def add_ctrl(name, head, tail, parent, hint=None):
    CTRL_BONES.append((name, head, tail, parent, hint))

# ctrl_root must share the deformation root's rest frame EXACTLY (same head,
# tail and axes): apply_controls uses the control's pose matrix as the root's
# desired pose, so a different rest length would scale the whole body.
_rb = spec_bone("root")
add_ctrl("ctrl_root", _rb["head"], _rb["tail"], None, Vector((1, 0, 0)))
for nm, ctrl in (("pelvis", "ctrl_pelvis"), ("spine_02", "ctrl_chest"),
                 ("neck_01", "ctrl_neck"), ("head", "ctrl_head")):
    sb = spec_bone(nm)
    add_ctrl(ctrl, sb["head"], sb["tail"], None, Vector((1, 0, 0)))
# look target level with the head bone: the default auto-look then leaves
# head/neck/eyes exactly at rest (a level look direction is yaw=pitch=0)
_hb = spec_bone("head")
add_ctrl("ctrl_look", (0, -1.0, _hb["head"][2]), (0, -0.92, _hb["head"][2]), None, None)
for side in ("L", "R"):
    chain = [("clavicle_%s" % side, "ctrl_chest"),
             ("upper_arm_%s" % side, "fk_clavicle_%s" % side),
             ("forearm_%s" % side, "fk_upper_arm_%s" % side),
             ("hand_%s" % side, "fk_forearm_%s" % side)]
    for nm, parent in chain:
        sb = spec_bone(nm)
        add_ctrl("fk_" + nm, sb["head"], sb["tail"], parent,
                 x_hint_for(nm, sb["head"], sb["tail"]))
    hb = spec_bone("hand_%s" % side)
    add_ctrl("ik_hand_%s" % side, hb["head"],
             (hb["head"][0], hb["head"][1] - 0.06, hb["head"][2]), None, None)
    fb = spec_bone("forearm_%s" % side)
    add_ctrl("pole_elbow_%s" % side,
             (fb["head"][0], fb["head"][1] + 0.15, fb["head"][2]),
             (fb["head"][0], fb["head"][1] + 0.19, fb["head"][2]), None, None)
    lchain = [("thigh_%s" % side, "ctrl_pelvis"),
              ("shin_%s" % side, "fk_thigh_%s" % side),
              ("foot_%s" % side, "fk_shin_%s" % side),
              ("toe_%s" % side, "fk_foot_%s" % side)]
    for nm, parent in lchain:
        sb = spec_bone(nm)
        add_ctrl("fk_" + nm, sb["head"], sb["tail"], parent,
                 x_hint_for(nm, sb["head"], sb["tail"]))
    sb2 = spec_bone("shin_%s" % side)
    add_ctrl("pole_knee_%s" % side,
             (sb2["head"][0], sb2["head"][1] - 0.15, sb2["head"][2]),
             (sb2["head"][0], sb2["head"][1] - 0.15, sb2["head"][2] + 0.04), None, None)
    ftb = spec_bone("foot_%s" % side)
    add_ctrl("ik_foot_%s" % side, ftb["head"],
             (ftb["head"][0], ftb["head"][1] - 0.06, ftb["head"][2] - 0.02), None, None)
# parents of the body controls (fixed now that names exist)
parent_of = {"ctrl_pelvis": "ctrl_root", "ctrl_chest": "ctrl_pelvis",
             "ctrl_neck": "ctrl_chest", "ctrl_head": "ctrl_neck"}
bpy.context.view_layer.objects.active = C
bpy.ops.object.mode_set(mode='EDIT')
cebs = {}
for name, head, tail, parent, hint in CTRL_BONES:
    eb = cdata.edit_bones.new(name)
    set_eb_frame(eb, bone_frame(head, tail, hint))
    eb.use_deform = False
    cebs[name] = eb
for name, head, tail, parent, hint in CTRL_BONES:
    p = parent or parent_of.get(name)
    if p:
        cebs[name].parent = cebs[p]
# bone collections for visual grouping (must run in EDIT mode: EditBone refs)
try:
    groups = {"Body": ('THEME01', ["ctrl_root", "ctrl_pelvis", "ctrl_chest",
                                   "ctrl_neck", "ctrl_head", "ctrl_look"]),
              "FK": ('THEME04', [n for n, *_ in CTRL_BONES if n.startswith("fk_")]),
              "IK": ('THEME03', [n for n, *_ in CTRL_BONES
                                 if n.startswith(("ik_", "pole_"))])}
    for gname, (color, names) in groups.items():
        coll = cdata.collections.new(gname)
        try:
            coll.color = color
        except Exception:
            pass
        for n in names:
            if n in cebs:
                coll.assign(cebs[n])
except Exception as e:
    print("bone collections skipped:", e)
bpy.ops.object.mode_set(mode='OBJECT')
print("CONTROL bones:", len(cdata.bones))

# control custom properties (defaults live in tools/rig_ops.py DEFAULTS)
sys.path.insert(0, os.path.join(TASK, "tools"))
import rig_ops  # noqa: E402  (registers the operators in this session too)
for k, v in rig_ops.DEFAULTS.items():
    C[k] = v

# ===================================================================== parent mesh + modifier
obj.parent = A
mod = obj.modifiers.new("Armature", 'ARMATURE')
mod.object = A
mod.use_vertex_groups = True
mod.use_bone_envelopes = False

# ===================================================================== socket empties
# A bone-parented object's matrix_basis is relative to the bone's TAIL frame:
# world = (bone.matrix_local @ Translation(0, bone.length, 0)) @ basis
# (verified empirically on Blender 5.1.1, see work/fix_sockets.py).  The spec
# stores each socket's desired rest world matrix (world_t + rot_mode).
R_BARREL = Matrix.Rotation(math.pi, 4, 'Z')  # +Y along barrel, +Z up
for s in SOCKETS:
    bone = adata.bones.get(s["bone"])
    if bone is None:
        continue
    R = R_BARREL if s.get("rot_mode") == "barrel" else Matrix.Identity(4)
    target = Matrix.Translation(Vector(s["world_t"])) @ R
    P = bone.matrix_local @ Matrix.Translation(Vector((0.0, bone.length, 0.0)))
    e = bpy.data.objects.new("socket_" + s["name"], None)
    e.empty_display_type = 'CONE'
    e.empty_display_size = 0.02
    e.show_name = True
    sc.collection.objects.link(e)
    e.parent = A
    e.parent_type = 'BONE'
    e.parent_bone = s["bone"]
    e.matrix_basis = P.inverted() @ target
print("SOCKET empties:", len(SOCKETS))

# ===================================================================== embed rig operators
txt = bpy.data.texts.load(RIG_OPS)
txt.use_module = True
print("TEXT datablock:", txt.name, "use_module:", txt.use_module)

# ===================================================================== verify
bone_names = [b.name for b in adata.bones]
spec_names = [b["name"] for b in BONES]
# Blender stores armature.bones in hierarchy (DFS) order, not creation order;
# what must be stable is the name set and the parent attachments.
assert set(bone_names) == set(spec_names), "bone name set mismatch"
spec_parent = {b["name"]: b["parent"] for b in BONES}
for b in adata.bones:
    got = b.parent.name if b.parent else None
    assert got == spec_parent[b.name], "parent mismatch on %s: %s != %s" % (
        b.name, got, spec_parent[b.name])
roots = [b for b in adata.bones if b.parent is None]
assert len(roots) == 1 and roots[0].name == "root", "must have exactly one root bone"
def reaches_root(b):
    seen = set()
    while b is not None:
        if b.name in seen:
            return False
        seen.add(b.name)
        if b.name == "root":
            return True
        b = b.parent
    return False
assert all(reaches_root(b) for b in adata.bones), "disconnected bone"
assert adata.bones["pelvis"].parent.name == "root", "pelvis must be a child of root"

def rot_of(M):
    R = M.to_3x3().copy()
    for i in range(3):
        c = R.col[i]
        if c.length > 1e-9:
            R.col[i] = c / c.length
    return R

# every deformation bone's rest frame must match the spec exactly (head, tail,
# length and rotation) -- guards against EditBone frame-setting regressions
for b in BONES:
    bone = adata.bones[b["name"]]
    M = bone_frame(b["head"], b["tail"], x_hint_for(b["name"], b["head"], b["tail"]))
    head = Vector(b["head"]); tail = Vector(b["tail"])
    assert (bone.head_local - head).length < 1e-6, "head mismatch %s" % b["name"]
    assert (bone.tail_local - tail).length < 1e-6, "tail mismatch %s" % b["name"]
    assert abs(bone.length - (tail - head).length) < 1e-6, "length mismatch %s" % b["name"]
    d = max(abs(rot_of(bone.matrix_local)[i][j] - rot_of(M)[i][j])
            for i in range(3) for j in range(3))
    assert d < 1e-5, "rest frame mismatch on %s: %g" % (b["name"], d)
print("VERIFY deformation rest frames: %d/%d exact" % (len(BONES), len(BONES)))

# control bones: rest frames must match their authored frames exactly
for name, head, tail, parent, hint in CTRL_BONES:
    bone = cdata.bones[name]
    M = bone_frame(head, tail, hint)
    assert (bone.head_local - Vector(head)).length < 1e-6, "ctrl head %s" % name
    assert (bone.tail_local - Vector(tail)).length < 1e-6, "ctrl tail %s" % name
    d = max(abs(rot_of(bone.matrix_local)[i][j] - rot_of(M)[i][j])
            for i in range(3) for j in range(3))
    assert d < 1e-5, "control rest frame mismatch on %s: %g" % (name, d)
print("VERIFY control rest frames: %d/%d exact" % (len(CTRL_BONES), len(CTRL_BONES)))

groups = {g.name for g in obj.vertex_groups}
assert groups == set(spec_names), "vertex group mismatch: extra=%s missing=%s" % (
    sorted(groups - set(spec_names)), sorted(set(spec_names) - groups))
max_infl = 0
bad_sum = 0
for v in me.vertices:
    ws = [(g.weight, g.group) for g in v.groups if g.weight > 1e-6]
    max_infl = max(max_infl, len(ws))
    s = sum(w for w, _ in ws)
    if abs(s - 1.0) > 1e-3:
        bad_sum += 1
print("VERIFY weights: max influences=%d bad_sum=%d" % (max_infl, bad_sum))
assert max_infl <= 8 and bad_sum == 0
assert me.shape_keys is not None and len(me.shape_keys.key_blocks) == 11
for nm in ("eye_L", "eye_R", "lid_upper_L", "lid_lower_R"):
    D = adata.bones[nm].matrix_local.to_3x3() - Matrix.Identity(3)
    assert max(abs(x) for row in D for x in row) < 1e-6, nm + " must have identity rotation"
assert obj.parent == A and mod.object == A
print("VERIFY bones=%d roots=1 groups=%d shapekeys=%d" %
      (len(adata.bones), len(groups), len(me.shape_keys.key_blocks)))

sc.frame_start = 1
sc.frame_end = 250
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("SAVED", BLEND_OUT)
print("GEN2_DONE")

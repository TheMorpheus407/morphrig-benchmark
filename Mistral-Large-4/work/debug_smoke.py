"""debug_smoke.py — investigate smoke_rig check 7 (eye look) and check 10 (mesh)."""
import bpy
import json
import math
import os
import sys
from mathutils import Vector, Matrix

TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
sys.path.insert(0, os.path.join(TASK, "tools"))

BLEND = os.path.join(TASK, "source", "Operative_rig.blend")
SPEC = json.load(open(os.path.join(TASK, "work", "rig_spec.json")))
BONES = {b["name"]: b for b in SPEC["bones"]}

bpy.ops.wm.open_mainfile(filepath=BLEND)
import rig_ops  # noqa: E402

A = bpy.data.objects["Armature"]
C = bpy.data.objects["Operative_Controls"]
M = bpy.data.objects["Operative"]
pbs = A.pose.bones


def mdiff(M1, M2):
    return max(abs(M1[i][j] - M2[i][j]) for i in range(4) for j in range(4))


print("======== CHECK 7: eye look ========")
rig_ops.reset_pose()
C["look_auto"] = False
C["look_yaw"] = 30.0
C["look_pitch"] = 10.0
rig_ops.apply_controls()
bpy.context.view_layer.update()
eb = pbs["eye_L"].bone
pb = pbs["eye_L"]
print("eye_L matrix_local:\n", eb.matrix_local)
print("eye_L rotation_mode:", pb.rotation_mode)
print("eye_L matrix_basis:\n", pb.matrix_basis)
print("eye_L rotation_euler:", tuple(pb.rotation_euler))
print("eye_L location:", tuple(pb.location), "scale:", tuple(pb.scale))
print("eye_L pose matrix:\n", pb.matrix)
expect = (Matrix.Translation(eb.matrix_local.to_translation())
          @ Matrix.Rotation(math.radians(30.0), 4, 'Z')
          @ Matrix.Rotation(math.radians(-10.0), 4, 'X'))
print("expected:\n", expect)
print("diff:", mdiff(pb.matrix, expect))
hb = pbs["head"]
print("head pose matrix:\n", hb.matrix)
print("head rest matrix_local:\n", hb.bone.matrix_local)
print("head diff vs rest:", mdiff(hb.matrix, hb.bone.matrix_local))
# what would the eye pose be if its basis were identity?
noown = hb.matrix @ (hb.bone.matrix_local.inverted() @ eb.matrix_local)
print("diff if eye basis identity:", mdiff(noown, expect))
print("diff actual vs if-identity:", mdiff(pb.matrix, noown))

print("======== CHECK 10: mesh deformation ========")
rig_ops.reset_pose()
C["ik_fk_arm_L"] = 1.0
ikc = C.pose.bones["ik_hand_L"]
ikc.rotation_mode = 'XYZ'
ikc.location = (0.0, 0.10, -0.075)
rig_ops.apply_controls()
bpy.context.view_layer.update()
me = M.data
wrist_rest = Vector(BONES["hand_L"]["head"])
best = min(range(len(me.vertices)), key=lambda i: (me.vertices[i].co - wrist_rest).length)
v = me.vertices[best]
print("rest vertex %d co=%s dist=%.4f" % (best, tuple(v.co), (v.co - wrist_rest).length))
groups = [(g.group, g.weight) for g in v.groups]
print("vertex groups:", [(M.vertex_groups[g].name, round(w, 4)) for g, w in groups])
print("modifiers:", [(m.name, m.type, getattr(m, 'object', None)) for m in M.modifiers])
for m in M.modifiers:
    if m.type == 'ARMATURE':
        print("armature mod: object=%s vgroups=%s envelopes=%s vgroup=%r" %
              (m.object.name if m.object else None, m.use_vertex_groups,
               m.use_bone_envelopes, m.vertex_group))
print("M parent:", M.parent.name if M.parent else None, "matrix_world identity:",
      M.matrix_world == Matrix.Identity(4))
print("A matrix_world identity:", A.matrix_world == Matrix.Identity(4))
print("rest bbox:", [tuple(round(c, 4) for c in (min(v.co.x for v in me.vertices),
                                                 min(v.co.y for v in me.vertices),
                                                 min(v.co.z for v in me.vertices))),
      tuple(round(c, 4) for c in (max(v.co.x for v in me.vertices),
                                  max(v.co.y for v in me.vertices),
                                  max(v.co.z for v in me.vertices)))])
dg = bpy.context.evaluated_depsgraph_get()
mev = M.evaluated_get(dg).to_mesh()
print("eval verts:", len(mev.vertices), "rest verts:", len(me.vertices))
print("eval vertex %d co=%s (moved %.4f)" %
      (best, tuple(mev.vertices[best].co), (mev.vertices[best].co - v.co).length))
print("eval bbox:", [tuple(round(c, 4) for c in (min(v.co.x for v in mev.vertices),
                                                 min(v.co.y for v in mev.vertices),
                                                 min(v.co.z for v in mev.vertices))),
      tuple(round(c, 4) for c in (max(v.co.x for v in mev.vertices),
                                  max(v.co.y for v in mev.vertices),
                                  max(v.co.z for v in mev.vertices)))])
# how many vertices moved at all?
moved = sum(1 for i in range(len(me.vertices))
            if (mev.vertices[i].co - me.vertices[i].co).length > 1e-6)
print("vertices moved >1e-6:", moved, "/", len(me.vertices))
# vertex fully weighted to hand_L?
hand_vg = M.vertex_groups.get("hand_L")
print("hand_L group index:", hand_vg.index if hand_vg else None)
if hand_vg:
    cand = [i for i in range(len(me.vertices))
            if any(g.group == hand_vg.index and g.weight > 0.9 for g in me.vertices[i].groups)]
    print("verts >0.9 weighted to hand_L:", len(cand))
    if cand:
        i = cand[len(cand) // 2]
        print("sample %d rest=%s eval=%s moved=%.4f" %
              (i, tuple(me.vertices[i].co), tuple(mev.vertices[i].co),
               (mev.vertices[i].co - me.vertices[i].co).length))
M.evaluated_get(dg).to_mesh_clear()
print("DEBUG_DONE")

import bpy, json, os, sys
from mathutils import Vector, Matrix
GEN_DIR = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/generators"
TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
sys.path.insert(0, GEN_DIR)
from morphrig_lib import bone_frame, x_hint_for

SPEC = json.load(open(os.path.join(TASK, "work/rig_spec.json")))
BONES = SPEC["bones"]
bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source/Operative.blend"))
sc = bpy.context.scene
adata = bpy.data.armatures.new("T")
A = bpy.data.objects.new("TArm", adata)
sc.collection.objects.link(A)
bpy.context.view_layer.objects.active = A
bpy.ops.object.mode_set(mode='EDIT')
ebs = {}
for b in BONES:
    eb = adata.edit_bones.new(b["name"])
    eb.matrix = bone_frame(b["head"], b["tail"], x_hint_for(b["name"], b["head"], b["tail"]))
    ebs[b["name"]] = eb
for b in BONES:
    if b["parent"]:
        ebs[b["name"]].parent = ebs[b["parent"]]
bpy.ops.object.mode_set(mode='OBJECT')
names = [b.name for b in adata.bones]
spec_names = [b["name"] for b in BONES]
print("len", len(names), len(spec_names))
for i, (a, b) in enumerate(zip(names, spec_names)):
    if a != b:
        print("first mismatch at", i, "adata:", a, "spec:", b)
        print("adata around:", names[max(0,i-3):i+4])
        print("spec  around:", spec_names[max(0,i-3):i+4])
        break
else:
    print("prefix equal; tail adata:", names[len(spec_names):], "spec:", spec_names[len(names):])
# check topological validity of adata order
pos = {n: i for i, n in enumerate(names)}
bad = [(b.name, b.parent.name) for b in adata.bones if b.parent and pos[b.parent.name] > pos[b.name]]
print("parent-after-child violations:", bad[:5], "count", len(bad))

# ---- cheek vert survey
me = bpy.data.objects["Operative"].data
print("\n-- skin verts z in [1.55,1.70], |x|<0.12 (mat, x, y, z) --")
n = 0
for vi, v in enumerate(me.vertices):
    c = v.co
    if 1.55 < c.z < 1.70 and abs(c.x) < 0.12:
        # material
        m = None
        for p in me.polygons:
            if vi in p.vertices:
                m = p.material_index; break
        if m == 0:
            n += 1
print("skin verts in band:", n)
# window test with wider bounds
cnt = 0
for vi, v in enumerate(me.vertices):
    c = v.co
    if -0.125 < c.y < -0.055 and 1.580 < c.z < 1.632 and 0.035 < abs(c.x) < 0.095:
        cnt += 1
print("wide-window verts (no mat filter):", cnt)
# where are the skin verts in z 1.58..1.63?
zs = sorted(set(round(v.co.z, 4) for v in me.vertices if 1.58 < v.co.z < 1.63))
print("distinct z values in [1.58,1.63]:", zs[:40])

# material breakdown of the wide window
vert_mat = {}
for p in me.polygons:
    for vi in p.vertices:
        vert_mat[vi] = p.material_index
from collections import Counter
cnt = Counter()
samples = {}
for vi, v in enumerate(me.vertices):
    c = v.co
    if -0.125 < c.y < -0.055 and 1.580 < c.z < 1.632 and 0.035 < abs(c.x) < 0.095:
        m = vert_mat.get(vi)
        cnt[m] += 1
        samples.setdefault(m, []).append((round(c.x,4), round(c.y,4), round(c.z,4)))
print("material counts in wide window:", dict(cnt))
for m, ss in samples.items():
    print(" mat", m, "sample:", ss[:6])
# also: skin-only in window with slightly different bounds
n2 = 0
for vi, v in enumerate(me.vertices):
    c = v.co
    if vert_mat.get(vi) == 0 and -0.125 < c.y < -0.055 and 1.575 < c.z < 1.635 and 0.030 < abs(c.x) < 0.100:
        n2 += 1
print("skin verts in relaxed window:", n2)

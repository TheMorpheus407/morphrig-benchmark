import bpy, json, os, sys
GEN_DIR = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/generators"
sys.path.insert(0, GEN_DIR)
from morphrig_lib import bone_frame, x_hint_for
from mathutils import Matrix
SPEC = json.load(open("/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/work/rig_spec.json"))
B = {b["name"]: b for b in SPEC["bones"]}
bpy.ops.wm.open_mainfile(filepath="/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative.blend")
sc = bpy.context.scene
ad = bpy.data.armatures.new("T")
A = bpy.data.objects.new("TA", ad)
sc.collection.objects.link(A)
bpy.context.view_layer.objects.active = A
bpy.ops.object.mode_set(mode='EDIT')
eb = ad.edit_bones.new("eye_L")
M = bone_frame(B["eye_L"]["head"], B["eye_L"]["tail"], x_hint_for("eye_L", B["eye_L"]["head"], B["eye_L"]["tail"]))
print("bone_frame M:\n", M)
eb.matrix = M
print("eb.head", eb.head, "eb.tail", eb.tail, "eb.length", eb.length, "eb.roll", eb.roll)
bpy.ops.object.mode_set(mode='OBJECT')
b = ad.bones["eye_L"]
print("matrix_local:\n", b.matrix_local)
print("head", b.head_local, "tail", b.tail_local, "length", b.length)
D = b.matrix_local.to_3x3() - Matrix.Identity(3)
print("max diff:", max(abs(x) for row in D for x in row))

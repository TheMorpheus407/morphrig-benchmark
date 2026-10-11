import sys
TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
sys.path.insert(0, TASK + "/tools")
sys.path.insert(0, TASK + "/source/generators")
import bpy
bpy.ops.wm.open_mainfile(filepath=TASK + "/source/Operative_rig.blend")
import rig_ops
import anim_lib
from mathutils import Vector, Matrix

rig = anim_lib.Rig()
Pp = anim_lib.combat_pose(rig)

print("== root_off test: root local (0,0,2), root_off=(0,-2,0)")
rig.root_off = Vector((0.0, -2.0, 0.0))
Pp2 = anim_lib.P(Pp, root=(0.0, 0.0, 2.0))
anim_lib.apply_pose(rig, Pp2)
rig.apply()
print("pelvis ", tuple(round(v, 4) for v in rig.def_m["pelvis"].to_translation()))
print("foot_L ", tuple(round(v, 4) for v in rig.def_m["foot_L"].to_translation()))
print("ankleT ", tuple(round(v, 4) for v in Pp2["legs"]["L"]["ankle"]))
print("head   ", tuple(round(v, 4) for v in rig.def_m["head"].to_translation()))
print("cell_new", tuple(round(v, 4) for v in rig.def_m["cell_new"].to_translation()))
print("root bone", tuple(round(v, 4) for v in rig.def_m["root"].to_translation()))

print("== global_scale test: gs=0.5 on combat pose")
rig.root_off = Vector((0.0, 0.0, 0.0))
Pp3 = anim_lib.P(Pp, scale=0.5)
anim_lib.apply_pose(rig, Pp3)
rig.apply()
print("pelvis ", tuple(round(v, 4) for v in rig.def_m["pelvis"].to_translation()))
print("head   ", tuple(round(v, 4) for v in rig.def_m["head"].to_translation()))
print("foot_L ", tuple(round(v, 4) for v in rig.def_m["foot_L"].to_translation()))

print("== global_scale gs=0.02 (blink floor)")
Pp4 = anim_lib.P(Pp, scale=0.02)
anim_lib.apply_pose(rig, Pp4)
rig.apply()
print("pelvis ", tuple(round(v, 4) for v in rig.def_m["pelvis"].to_translation()))
print("head   ", tuple(round(v, 4) for v in rig.def_m["head"].to_translation()))
print("PROBE2 DONE")

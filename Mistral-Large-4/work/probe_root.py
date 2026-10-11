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
C = rig.C

print("== control hierarchy")
for cb in C.pose.bones:
    print("CTRL %-16s parent=%s" % (cb.name, cb.parent.name if cb.parent else None))

R = rig.rest["root"].to_3x3()
print("root rest colX", tuple(R.col[0]), "colY", tuple(R.col[1]), "colZ", tuple(R.col[2]))

# author a combat pose (ankle targets in the control frame, pelvis at origin)
Pp = anim_lib.combat_pose(rig)
anim_lib.apply_pose(rig, Pp)
rig.apply()
print("no root: pelvis", tuple(rig.def_m["pelvis"].to_translation()))
print("no root: foot_L", tuple(rig.def_m["foot_L"].to_translation()),
      "ankle target", Pp["legs"]["L"]["ankle"])

# now translate the root control by local (0, 0, 2)  (expect world -Y * 2 if +Z->-Y)
Pp2 = anim_lib.P(Pp, root=(0.0, 0.0, 2.0))
anim_lib.apply_pose(rig, Pp2)
rig.apply()
print("root(0,0,2): pelvis", tuple(rig.def_m["pelvis"].to_translation()))
print("root(0,0,2): foot_L", tuple(rig.def_m["foot_L"].to_translation()))
print("root(0,0,2): ik_foot_L ctrl world", tuple(C.pose.bones["ik_foot_L"].matrix.to_translation()))
print("root(0,0,2): ik_foot_L ctrl basis", tuple(C.pose.bones["ik_foot_L"].matrix_basis.to_translation()))
print("root(0,0,2): emitter", tuple(rig.def_m["emitter"].to_translation()))
print("root(0,0,2): cell_new", tuple(rig.def_m["cell_new"].to_translation()))

# root local (2, 0, 0) -> expect world +X * 2 (right)
Pp3 = anim_lib.P(Pp, root=(2.0, 0.0, 0.0))
anim_lib.apply_pose(rig, Pp3)
rig.apply()
print("root(2,0,0): pelvis", tuple(rig.def_m["pelvis"].to_translation()))

# hand bone rest world axes (for hand_R constructions)
for b in ("hand_L", "hand_R", "foot_L"):
    M = rig.rest[b]
    print("rest %s colX" % b, tuple(M.col[0].to_3d() if hasattr(M.col[0], 'to_3d') else M.col[0]),
          "colY", tuple(M.col[1]), "colZ", tuple(M.col[2]))
print("PROBE DONE")

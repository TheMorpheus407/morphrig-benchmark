"""Debug 3: numeric trace of the lying leg_s=0 leg IK solve."""
import sys, os, math

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))

import rig_ops
import anim_lib
from anim_lib import Rig, P, apply_pose, body_matrices, hip_pos, ANKLE_Z

rig = Rig()

Pp = P(pelvis__z=0.13, pelvis__lean=93.18, w=(1.0, 0.0, 0.0))
M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
legs = {}
for side in ("L", "R"):
    hip = hip_pos(rig, side, M_pel)
    ankle = Vector((hip.x, hip.y, ANKLE_Z))
    pole = hip + Vector((0.0, 0.25, 0.35))
    legs[side] = {"mode": "ik", "ankle": tuple(ankle), "yaw": 180.0,
                  "pitch": 0.0, "toe": 0.0, "pole": tuple(pole)}
Pp["legs"] = legs
# neutral arms (fk_param defaults) so nothing else interferes
apply_pose(rig, Pp)

print("== rest data")
for b in ("thigh_L", "shin_L", "foot_L", "toe_L"):
    print("   rest[%s].t = %s" % (b, tuple(round(v, 5) for v in rig.rest[b].to_translation())))
L1 = (rig.rest["shin_L"].to_translation() - rig.rest["thigh_L"].to_translation()).length
L2 = (rig.rest["foot_L"].to_translation() - rig.rest["shin_L"].to_translation()).length
print("   L1=%.5f L2=%.5f leg_len=%.5f rig.leg_len=%.5f" % (L1, L2, L1 + L2, rig.leg_len))
print("   rl[thigh_L].t =", tuple(round(v, 5) for v in rig.rl["thigh_L"].to_translation()))
print("   rl[shin_L].t  =", tuple(round(v, 5) for v in rig.rl["shin_L"].to_translation()))
print("   rl[foot_L].t  =", tuple(round(v, 5) for v in rig.rl["foot_L"].to_translation()))
print("   parent(shin_L) =", rig.pbs["shin_L"].bone.parent.name)
print("   parent(thigh_L) =", rig.pbs["thigh_L"].bone.parent.name)

print("")
print("== control world positions after apply_pose (pre-apply)")
for cn in ("ik_foot_L", "pole_knee_L", "fk_thigh_L", "fk_shin_L", "fk_foot_L"):
    cb = rig.cbs[cn]
    print("   ctrl_world[%s] = %s" % (cn, tuple(round(v, 4) for v in rig.ctrl_world[cn].to_translation())))
print("   ik_fk_leg_L prop =", rig.C.get("ik_fk_leg_L"))
print("   ctrl bone parent chain:")
for cn in ("ik_foot_L", "pole_knee_L"):
    b = rig.cbs[cn].bone
    print("      %s parent=%s rest_local.t=%s" % (cn, b.parent.name if b.parent else None,
          tuple(round(v, 4) for v in b.matrix_local.to_translation())))

print("")
print("== direct solver call")
A0 = (M_pel @ rig.rl["thigh_L"]).to_translation()
K0 = A0 + (rig.rest["shin_L"].to_translation() - rig.rest["thigh_L"].to_translation())
F0 = A0 + (rig.rest["foot_L"].to_translation() - rig.rest["thigh_L"].to_translation())
ankle = Vector(legs["L"]["ankle"])
pole = Vector(legs["L"]["pole"])
print("   A0 =", tuple(round(v, 5) for v in A0))
print("   ankle =", tuple(round(v, 5) for v in ankle), " d=%.5f" % (ankle - A0).length)
print("   pole =", tuple(round(v, 5) for v in pole))
K_new, F_new = rig_ops.solve_2bone_ik(A0, K0, F0, ankle, pole)
print("   K_new =", tuple(round(v, 5) for v in K_new))
print("   F_new =", tuple(round(v, 5) for v in F_new))

rig.apply()
rig.post_pose(Pp)
print("")
print("== def heads after apply+post_pose")
for b in ("thigh_L", "thigh_twist_L", "shin_L", "shin_twist_L", "foot_L", "toe_L"):
    t = rig.def_m[b].to_translation()
    print("   %-14s (%8.4f, %8.4f, %8.4f)" % (b, t.x, t.y, t.z))
th = rig.def_m["thigh_L"].to_translation()
sn = rig.def_m["shin_L"].to_translation()
ft = rig.def_m["foot_L"].to_translation()
print("   |shin-thigh| = %.5f (L1=%.5f)" % ((sn - th).length, L1))
print("   |foot-shin|  = %.5f (L2=%.5f)" % ((ft - sn).length, L2))
print("   |foot-ankle| = %.6f" % (ft - ankle).length)

print("")
print("== evaluated pose bone matrices from the control armature")
C = rig.C
bpy.context.view_layer.update()
for cn in ("ik_foot_L", "pole_knee_L"):
    print("   C %s world t = %s" % (cn, tuple(round(v, 4) for v in C.pose.bones[cn].matrix.to_translation())))
print("   gp ik_fk_leg_L =", rig_ops.gp("ik_fk_leg_L", None))

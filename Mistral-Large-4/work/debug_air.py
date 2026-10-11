"""Check air_legs knee direction: pole behind (current) vs pole in front.

Run:  blender -b --factory-startup --python work/debug_air.py
"""
import sys, os, math

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))
bpy.context.scene.render.fps = 30

import rig_ops
import anim_lib
from anim_lib import Rig, P, apply_pose, body_matrices, hip_pos, dir_of, ANKLE_Z
from morphrig_lib import FWD, UP

rig = Rig()


def ik_leg(ankle, yaw=0.0, pitch=0.0, toe=0.0, pole=None):
    return {"mode": "ik", "ankle": tuple(ankle), "yaw": yaw, "pitch": pitch,
            "toe": toe, "pole": tuple(pole)}


def pose(Pp):
    apply_pose(rig, Pp)
    rig.apply()
    rig.post_pose(Pp)


def air_legs2(rig, M_pel, lift, fwd, pitch, toe, pole_sign):
    u = dir_of(0.0, 0.0)
    legs = {}
    for side in ("L", "R"):
        hip = hip_pos(rig, side, M_pel)
        ankle = Vector((hip.x - fwd * u.x, hip.y - fwd * u.y, ANKLE_Z + lift))
        pole = hip + pole_sign * u * 0.30 + Vector((0.0, 0.0, 0.10))
        legs[side] = ik_leg(ankle, pitch=pitch, toe=toe, pole=pole)
    return legs


for label, sign in (("pole BEHIND hip (current air_legs)", -1.0),
                    ("pole IN FRONT of hip", +1.0)):
    print("== %s" % label)
    for tag, pz, lift, fwd, pitch, toe in (
            ("jump_air tuck ", 1.08, 0.28, 0.10, -15.0, 25.0),
            ("fall relaxed  ", 0.88, 0.12, 0.0, 15.0, 0.0),
            ("knockup flail ", 0.95, 0.18, 0.0, 25.0, 0.0)):
        Pp = P(pelvis__z=pz, pelvis__lean=4.0)
        M_root, M_pel, M_chest, M_spine03, sh = body_matrices(rig, Pp)
        Pp["legs"] = air_legs2(rig, M_pel, lift, fwd, pitch, toe, sign)
        pose(Pp)
        for side in ("L", "R"):
            hip = hip_pos(rig, side, M_pel)
            knee = rig.def_m["shin_%s" % side].to_translation()
            ankle = rig.def_m["foot_%s" % side].to_translation()
            ikerr = (ankle - Vector(Pp["legs"][side]["ankle"])).length
            print("   %s %s knee rel hip: (%+.3f, %+.3f, %+.3f)  ankle z=%.3f  ik=%.1e"
                  % (tag, side, knee.x - hip.x, knee.y - hip.y, knee.z - hip.z,
                     ankle.z, ikerr))
print("AIR DONE")

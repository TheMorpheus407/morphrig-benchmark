"""Debug 2: which bones own the below-floor verts in the leg_s=0 lying pose;
all bone head positions in that pose."""
import sys, os, math

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))

import bpy
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))

import rig_ops
import anim_lib
from anim_lib import (Rig, P, apply_pose, body_matrices, hip_pos, ANKLE_Z,
                      DEFORM_BONES)
from morphrig_lib import FWD, UP

rig = Rig()
PROP_OFF = {p: rig.rest["pelvis"].inverted() @ rig.rest[p]
            for p in ("cell_new", "cell_spent", "beacon")}


def rot_with_y(d, ref=None):
    y = Vector(d).normalized()
    z = Vector(ref) if ref is not None else UP.copy()
    z = z - y * z.dot(y)
    if z.length < 1e-6:
        z = Vector((1.0, 0.0, 0.0)) - y * y.x
    z.normalize()
    x = y.cross(z)
    return anim_lib.mat_cols(x, y, z)


def hand_M(palm_pos, y_dir, z_dir):
    y = Vector(y_dir).normalized()
    z = Vector(z_dir) - y * Vector(z_dir).dot(y)
    if z.length < 1e-6:
        z = UP - y * y.z
    z.normalize()
    x = y.cross(z)
    R = anim_lib.mat_cols(x, y, z)
    head = Vector(palm_pos) - 0.06 * y - 0.025 * z
    return Matrix.Translation(head) @ R


# minimal lying_pp (face-down, leg_s=0, arm_s=0, kind=side)
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
c = M_chest.to_translation()
for side, sgn in (("L", -1.0), ("R", 1.0)):
    palm = c + Vector((sgn * 0.35, -0.10, 0.0)) - UP * 0.10
    RH = rot_with_y(FWD, -UP)
    M_h = hand_M(palm, RH @ Vector((0.0, 1.0, 0.0)), RH @ Vector((0.0, 0.0, 1.0)))
    pole = sh[side] + Vector((0.0, -0.10, 0.30))
    Pp["arms"][side] = {"mode": "fk", "hand": M_h, "pole": tuple(pole),
                        "curl": 0.15, "spread": 0.05, "w": (1.0, 0.0, 0.0),
                        "swing": 0.0, "lift": 0.0, "yaw": 0.0, "elbow": 0.0,
                        "wrist": 0.0, "forearm": None, "target": None,
                        "hand_R": None}
gs = Pp["scale"]
for p in ("cell_new", "cell_spent", "beacon"):
    Pp["def"][p] = M_pel @ PROP_OFF[p]

apply_pose(rig, Pp)
rig.apply()
rig.post_pose(Pp)

print("== bone heads (z < 0.1 or notable)")
for name in DEFORM_BONES:
    t = rig.def_m[name].to_translation()
    if t.z < 0.30 or name in ("root", "pelvis", "head", "toe_L", "toe_R",
                              "foot_L", "foot_R", "shin_L", "shin_R",
                              "thigh_L", "thigh_R", "cable_01", "cable_02",
                              "cable_03", "jaw", "neck_01", "neck_02"):
        print("   %-16s (%7.3f, %7.3f, %7.3f)" % (name, t.x, t.y, t.z))

print("")
print("== lowest verts with group ownership")
dg = bpy.context.evaluated_depsgraph_get()
me = rig.M.evaluated_get(dg)
mm = me.to_mesh()
# vertex -> dominant group
vg_index = {}
for vg in rig.M.vertex_groups:
    vg_index[vg.index] = vg.name
low = sorted(mm.vertices, key=lambda v: v.co.z)[:12]
for v in low:
    best, bw = None, 0.0
    for g in v.groups:
        if g.weight > bw:
            bw = g.weight
            best = g.group
    print("   v(%7.3f, %7.3f, %7.4f)  dominant=%s w=%.2f" % (
        v.co.x, v.co.y, v.co.z, vg_index.get(best, best), bw))
me.to_mesh_clear()

print("")
print("== mesh z-histogram of lowest 40 verts")
dg = bpy.context.evaluated_depsgraph_get()
me = rig.M.evaluated_get(dg)
mm = me.to_mesh()
zs = sorted(v.co.z for v in mm.vertices)
print("   ", [round(z, 3) for z in zs[:40]])
me.to_mesh_clear()

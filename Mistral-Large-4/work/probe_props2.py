"""Probe prop mesh extents (vertices skinned to prop bones) for grip/seat constants."""
import sys, os, math
TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
sys.path.insert(0, os.path.join(TASK, "tools"))
sys.path.insert(0, os.path.join(TASK, "source", "generators"))
import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=os.path.join(TASK, "source", "Operative_rig.blend"))
import rig_ops

A = bpy.data.objects["Armature"]
M = bpy.data.objects["Operative"]
me = M.data
rig_ops.reset_pose()
bpy.context.view_layer.update()

# armature rest-space vertex positions (mesh is baked in rest space)
def vweight(g, vi):
    try:
        return g.weight(vi)
    except RuntimeError:
        return 0.0

props = ("cell_new", "cell_spent", "beacon", "emitter", "blade")
for p in props:
    g = M.vertex_groups.get(p)
    if g is None:
        print("%-10s NO GROUP" % p)
        continue
    vs = [v.co.copy() for v in me.vertices if vweight(g, v.index) > 0.5]
    if not vs:
        print("%-10s no verts >0.5" % p)
        continue
    mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    print("%-10s n=%4d  min=%s  max=%s  size=%s" % (
        p, len(vs),
        tuple(round(c, 4) for c in mn), tuple(round(c, 4) for c in mx),
        tuple(round(c, 4) for c in (mx - mn))))

# hand mesh extent (palm region) for hand_L/hand_R
for h in ("hand_L", "hand_R"):
    g = M.vertex_groups.get(h)
    vs = [v.co.copy() for v in me.vertices if vweight(g, v.index) > 0.5]
    mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    print("%-10s n=%4d  min=%s  max=%s" % (h, len(vs),
        tuple(round(c, 4) for c in mn), tuple(round(c, 4) for c in mx)))

# total mesh bounds + vertex/face count
vs = [v.co.copy() for v in me.vertices]
mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
print("MESH total: verts=%d faces=%d min=%s max=%s" % (
    len(me.vertices), len(me.polygons),
    tuple(round(c, 4) for c in mn), tuple(round(c, 4) for c in mx)))
print("PROBE2 DONE")

import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath="/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative.blend")
obj = bpy.data.objects["Operative"]
me = obj.data
groups = {g.name: g.index for g in obj.vertex_groups}
# finger vertex extents per group
for f in ("thumb", "index", "middle", "ring", "pinky"):
    for i in (1, 2, 3):
        nm = "f_%s_0%d_L" % (f, i)
        gi = groups.get(nm)
        if gi is None:
            print(nm, "NO GROUP"); continue
        vs = [v.co.copy() for v in me.vertices
              for g in v.groups if g.group == gi and g.weight > 0.5]
        if not vs:
            print(nm, "no verts"); continue
        xs = [v.x for v in vs]; ys = [v.y for v in vs]; zs = [v.z for v in vs]
        c = Vector((sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs)))
        # principal direction via spread
        d = Vector((max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)))
        print("%-14s n=%3d center (%.3f, %.3f, %.3f) extent (%.3f, %.3f, %.3f)" % (nm, len(vs), c.x, c.y, c.z, d.x, d.y, d.z))
# palm region: verts weighted to hand_L
gi = groups["hand_L"]
vs = [v.co.copy() for v in me.vertices for g in v.groups if g.group == gi and g.weight > 0.5]
xs=[v.x for v in vs]; ys=[v.y for v in vs]; zs=[v.z for v in vs]
print("hand_L verts n=%d x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f]" % (len(vs), min(xs),max(xs),min(ys),max(ys),min(zs),max(zs)))
print("CHECK_DONE")

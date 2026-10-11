import bpy
bpy.ops.wm.open_mainfile(filepath="/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative.blend")
me = bpy.data.objects["Operative"].data
vert_mat = {}
for p in me.polygons:
    for vi in p.vertices:
        vert_mat[vi] = p.material_index
hits = []
for vi, v in enumerate(me.vertices):
    c = v.co
    if -0.118 < c.y < -0.060 and 1.583 < c.z < 1.630 and 0.040 < abs(c.x) < 0.090:
        hits.append((vi, vert_mat.get(vi), round(c.x,4), round(c.y,4), round(c.z,4)))
print("gen_02 window hits:", len(hits))
for h in hits[:12]:
    print("  ", h)
# relaxed
n = 0
for vi, v in enumerate(me.vertices):
    c = v.co
    if vert_mat.get(vi) == 0 and -0.125 < c.y < -0.055 and 1.575 < c.z < 1.635 and 0.030 < abs(c.x) < 0.100:
        n += 1
print("relaxed skin window:", n)

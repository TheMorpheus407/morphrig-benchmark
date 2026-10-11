import bpy, math, json
from mathutils import Vector, Matrix

BLEND = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4/source/Operative_rig.blend"
bpy.ops.wm.open_mainfile(filepath=BLEND)
A = bpy.data.objects["Armature"]
M = bpy.data.objects["Operative"]
ad = A.data

print("== OBJECTS ==")
for o in bpy.data.objects:
    par = o.parent.name if o.parent else None
    pb = o.parent_bone if o.parent_type == 'BONE' else ""
    print("  %-22s %-8s parent=%-18s bone=%s" % (o.name, o.type, par, pb))

print("== MESH REGIONS (verts within radius) ==")
me = M.data
regions = [
    ("emitter_gadget", [0.245, 0.055, 0.85], 0.13),
    ("blade_gadget",   [0.245, -0.05, 0.85], 0.12),
    ("hand_R_palm",    [0.233, 0.0, 0.775], 0.11),
    ("hand_L_palm",    [-0.233, 0.0, 0.775], 0.11),
    ("cell_new_region", [-0.199, 0.022, 0.91], 0.09),
    ("cell_spent_region", [0.282, 0.015, 0.7775], 0.09),
    ("beacon_region",  [0, 0.215, 1.351], 0.09),
    ("head_top",       [0, 0.0, 1.7], 0.15),
]
for name, c, r in regions:
    c = Vector(c)
    vs = [v.co for v in me.vertices if (v.co - c).length < r]
    if vs:
        xs = [v.x for v in vs]; ys = [v.y for v in vs]; zs = [v.z for v in vs]
        print("  %-18s n=%3d  x[%.3f %.3f] y[%.3f %.3f] z[%.3f %.3f]"
              % (name, len(vs), min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    else:
        print("  %-18s NO VERTS" % name)

# finer: emitter gadget sliced along y to find barrel extent
print("== EMITTER SLICE (x in [0.20,0.30], z in [0.78,0.92]) ==")
vs = [v.co for v in me.vertices
      if 0.20 < v.co.x < 0.30 and 0.78 < v.co.z < 0.92]
if vs:
    ys = sorted(v.y for v in vs)
    print("  n=%d  y range [%.3f, %.3f]" % (len(vs), ys[0], ys[-1]))
    # histogram of y
    import collections
    h = collections.Counter(round(v.y, 2) for v in vs)
    for y in sorted(h):
        print("    y=%+.2f  n=%d" % (y, h[y]))
print("== BLADE SLICE (x in [0.20,0.30], z in [0.78,0.92], y<0) ==")
vs = [v.co for v in me.vertices
      if 0.20 < v.co.x < 0.30 and 0.78 < v.co.z < 0.92 and v.co.y < -0.005]
if vs:
    ys = sorted(v.y for v in vs)
    print("  n=%d  y range [%.3f, %.3f]" % (len(vs), ys[0], ys[-1]))

print("== BONE REST FRAMES ==")
for bn in ("root", "emitter", "blade", "hand_L", "hand_R", "head",
           "cell_new", "cell_spent", "beacon", "spine_03", "eye_L", "eye_R",
           "forearm_R", "jaw"):
    b = ad.bones.get(bn)
    if b is None:
        print("  no bone", bn)
        continue
    R = b.matrix_local.to_3x3()
    print("  %-11s t=[% .3f % .3f % .3f]  X=[% .2f % .2f % .2f]  Y=[% .2f % .2f % .2f]  Z=[% .2f % .2f % .2f]"
          % (bn, *b.matrix_local.to_translation(),
             *R.col[0].normalized(), *R.col[1].normalized(), *R.col[2].normalized()))

print("== EMPTY BONE-PARENT FORMULA TEST ==")
sc = bpy.context.scene
bone = ad.bones["emitter"]
target = bone.matrix_local @ Matrix.Translation(Vector((0, 0, -0.0725)))
for cand in ("A", "B"):
    e = bpy.data.objects.new("tmp_sock_" + cand, None)
    sc.collection.objects.link(e)
    e.parent = A
    e.parent_type = 'BONE'
    e.parent_bone = 'emitter'
    if cand == "A":
        e.matrix_basis = bone.matrix_local.inverted() @ target
    else:
        e.matrix_basis = target.copy()
    bpy.context.view_layer.update()
    err = (e.matrix_world.to_translation() - target.to_translation()).length
    # pose the parent bone (forearm_R) and check rigid follow
    fpb = A.pose.bones["forearm_R"]
    fpb.rotation_euler = (math.radians(25), 0.0, 0.0)
    fpb.location = (0.0, 0.02, 0.03)
    bpy.context.view_layer.update()
    pb = A.pose.bones["emitter"]
    expected = pb.matrix @ bone.matrix_local.inverted() @ target
    err2 = (e.matrix_world.to_translation() - expected.to_translation()).length
    q = e.matrix_world.to_3x3().to_quaternion().rotation_difference(
        expected.to_3x3().to_quaternion())
    err3 = math.degrees(abs(q.angle))
    print("  candidate %s: rest_pos_err=%.6f  posed_pos_err=%.6f  posed_rot_err=%.4f deg"
          % (cand, err, err2, err3))
    # cleanup pose
    fpb.rotation_euler = (0.0, 0.0, 0.0)
    fpb.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    bpy.data.objects.remove(e)

print("== EXISTING SOCKET EMPTIES ==")
for o in bpy.data.objects:
    if o.name.startswith("socket_"):
        print("  %-22s parent_bone=%-10s mw_t=%s" % (o.name, o.parent_bone,
              list(o.matrix_world.to_translation())))

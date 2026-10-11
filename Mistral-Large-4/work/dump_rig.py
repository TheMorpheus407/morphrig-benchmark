import bpy
bpy.ops.wm.open_mainfile(filepath="source/Operative_rig.blend")
arm = bpy.data.objects["Armature"]
ctrl = bpy.data.objects["Operative_Controls"]
print("== Armature bones (%d) ==" % len(arm.data.bones))
for b in arm.data.bones:
    par = b.parent.name if b.parent else "-"
    print("  %-22s parent=%-18s" % (b.name, par))
print("== pose bone constraints ==")
for pb in arm.pose.bones:
    cs = [(c.type, c.name, getattr(c,'target',None).name if getattr(c,'target',None) else None,
           c.subtarget if hasattr(c,'subtarget') else None) for c in pb.constraints]
    if cs: print("  %-22s %s" % (pb.name, cs))
print("== control bones (%d) ==" % len(ctrl.data.bones))
for b in ctrl.data.bones:
    par = b.parent.name if b.parent else "-"
    print("  %-22s parent=%-18s" % (b.name, par))
print("== control pose constraints ==")
for pb in ctrl.pose.bones:
    cs = [(c.type, c.name) for c in pb.constraints]
    if cs: print("  %-22s %s" % (pb.name, cs))
print("== shape keys ==")
sk = bpy.data.objects["Operative"].data.shape_keys
for kb in sk.key_blocks:
    print("  %-18s value=%.2f slider[%s,%s]" % (kb.name, kb.value, kb.slider_min, kb.slider_max))
print("== mesh vertex groups (first 100) ==")
vg = bpy.data.objects["Operative"].vertex_groups
print("  count:", len(vg))
for g in list(vg)[:100]:
    print("   ", g.name)
print("== max influences check ==")
import collections
mesh = bpy.data.objects["Operative"].data
cnt = collections.Counter()
for v in mesh.vertices:
    n = sum(1 for g in v.groups if g.weight > 0.001)
    cnt[n] += 1
print("  influence histogram:", dict(sorted(cnt.items())))
print("== custom props on control bones ==")
for pb in ctrl.pose.bones:
    props = {k: pb[k] for k in pb.keys()}
    if props: print("  %-22s %s" % (pb.name, props))
print("== custom props on armature pose bones ==")
for pb in arm.pose.bones:
    props = {k: pb[k] for k in pb.keys()}
    if props: print("  %-22s %s" % (pb.name, props))
print("== scene / units ==")
sc = bpy.context.scene
print("  unit scale:", sc.unit_settings.scale_length, "fps:", sc.render.fps)
print("== empties parented ==")
for o in bpy.data.objects:
    if o.type == "EMPTY":
        print("  %-22s parent=%s" % (o.name, o.parent.name if o.parent else None))

import bpy, json
bpy.ops.wm.open_mainfile(filepath="source/Operative_rig.blend")
print("== objects ==")
for o in bpy.data.objects:
    t = o.type
    extra = ""
    if t == "MESH":
        extra = "tris=%d verts=%d" % (len(o.data.polygons), len(o.data.vertices))
        mods = [m.type for m in o.modifiers]
        if mods: extra += " mods=%s" % mods
        if o.data.shape_keys: extra += " shapekeys=%d" % len(o.data.shape_keys.key_blocks)
        if o.parent and o.parent.type == "ARMATURE": extra += " parent=%s" % o.parent.name
    if t == "ARMATURE":
        extra = "bones=%d" % len(o.data.bones)
    print("  %-24s %-9s %s" % (o.name, t, extra))
print("== actions (%d) ==" % len(bpy.data.actions))
for a in bpy.data.actions:
    print("  %-24s frames=%s..%s" % (a.name, a.frame_range[0], a.frame_range[1]))
print("== materials ==", len(bpy.data.materials))
for m in bpy.data.materials:
    print("  ", m.name, "users=%d" % m.users)
print("== images ==", len(bpy.data.images))
for i in bpy.data.images:
    print("  ", i.name, i.size[:], i.filepath)
print("== scene ==", bpy.context.scene.render.fps, bpy.context.scene.frame_start, bpy.context.scene.frame_end)

import bpy, sys
f = sys.argv[sys.argv.index("--")+1]
bpy.ops.wm.open_mainfile(filepath=f)
for arm in bpy.data.objects:
    if arm.type == 'ARMATURE':
        bpy.context.view_layer.objects.active = arm
        bpy.ops.pose.armature_reset()
print("reset ok")

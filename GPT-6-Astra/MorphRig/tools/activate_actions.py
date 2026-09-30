import bpy
rig=bpy.data.objects['Operative_Rig']
for pb in rig.pose.bones:
 if pb.bone.use_deform:pb.rotation_mode='QUATERNION'
 else:pb.rotation_mode='XYZ'
bpy.context.scene.frame_set(2);bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

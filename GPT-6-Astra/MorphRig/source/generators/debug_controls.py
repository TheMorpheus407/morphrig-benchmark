import bpy
bpy.ops.wm.open_mainfile(filepath='MorphRig/source/Character_Master.blend')
r=bpy.data.objects['Operative_Rig']
for d in r.animation_data.drivers:print('DRIVER',d.data_path,d.is_valid,d.driver.expression)
r['global_scale']=1.25;r['finger_curl.L']=1;r['foot_roll.L']=.5
r.update_tag();bpy.context.view_layer.update()
print('SCALE',r.scale[:]);print('CURL',r.pose.bones['CTRL_index.01.L'].rotation_euler[:]);print('FOOT',r.pose.bones['CTRL_toe_pivot.L'].rotation_euler[:])

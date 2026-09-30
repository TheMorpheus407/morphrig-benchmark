import bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for filename in ('rebake_baseline.fbx','rebake_changed.fbx'):
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.fbx(filepath=str(root/'docs/validation'/filename),use_anim=True,automatic_bone_orientation=False)
 rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');print('FILE',filename,'ACTIONS',[(a.name,list(a.frame_range),[(s.identifier,s.target_id_type) for s in a.slots]) for a in bpy.data.actions]);print('RIG',rig.name,rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None)
 for a in bpy.data.actions:
  rig.animation_data.action=a
  if a.slots:rig.animation_data.action_slot=a.slots[0]
  for f in (1,4,5,6,10):
   bpy.context.scene.frame_set(f);bpy.context.view_layer.update();p=rig.pose.bones['hand.L'];print(f,p.rotation_mode,list(p.rotation_quaternion),list(p.rotation_euler),'head',list(p.head))

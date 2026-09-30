import bpy,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import motion,finger_quaternion,create_deformation_tests
rig=bpy.data.objects['Operative_Rig'];manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations']
for m in manifest:
 for action_name in (m['id'],'EDIT__'+m['id']):
  a=bpy.data.actions[action_name];rig.animation_data.action=a
  if a.slots:rig.animation_data.action_slot=a.slots[0]
  for frame in range(1,m['frame_end']+1):
   t=0 if m['static_pose'] else (frame-1)/(m['frame_end']-1);p=motion(m['id'],t,m['duration'])
   for side in ('L','R'):
    for finger in ('thumb','index','middle','ring','pinky'):
     for j in (1,2,3):
      pb=rig.pose.bones[f'{finger}.{j:02d}.{side}'];pb.rotation_mode='QUATERNION';pb.rotation_quaternion=finger_quaternion(side,finger,j,p['grip'+side]);pb.keyframe_insert('rotation_quaternion',frame=frame,group=pb.name)
 print('REFINED GRIP',m['id'],flush=True)
create_deformation_tests(rig,bpy.data.objects['Operative_LOD0'],root)
rig.animation_data.action=bpy.data.actions['idle_relaxed'];bpy.context.scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

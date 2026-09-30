import sys,bpy
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import *
rig=bpy.data.objects['Operative_Rig'];face=bpy.data.objects['Operative_LOD0']
for pb in rig.pose.bones:
 for c in pb.constraints:c.mute=True
for id,t,d in [('run_f',7/21,.7),('walk_f',6/24,.8),('reload',34/69,2.3),('knockdown_back',1,1.2)]:
 a=bpy.data.actions.new('preview_'+id);a.use_fake_user=True;rig.animation_data_create();rig.animation_data.action=a
 p=motion(id,t,d);apply_pose(rig,p,id,t)
 for pb in rig.pose.bones:
  pb.keyframe_insert('location',frame=1);pb.keyframe_insert('rotation_quaternion',frame=1);pb.keyframe_insert('scale',frame=1)
 for key in face.data.shape_keys.key_blocks:key.value=0
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Solver_Preview.blend'))

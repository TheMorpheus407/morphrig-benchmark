"""Read-only native compressed-pose probe; changes no assets."""
from pathlib import Path
import json
import unreal as u
mesh=u.load_asset('/Game/Operative/SK_Operative')
skel=mesh.get_editor_property('skeleton')
ref=u.AnimPoseExtensions.get_reference_pose(skel)
anim=u.load_asset('/Game/Operative/Animations/idle_combat')
opt=u.AnimPoseEvaluationOptions()
opt.set_editor_property('evaluation_type',u.AnimDataEvalType.COMPRESSED)
opt.set_editor_property('extract_root_motion',False)
opt.set_editor_property('incorporate_root_motion_into_pose',True)
rows=[]
for t in [0,1,2]:
    pose=u.AnimPoseExtensions.get_anim_pose_at_time(anim,t,opt)
    feet={}
    for side,sign in [('L',1),('R',-1)]:
        name='foot_'+side
        rest=u.AnimPoseExtensions.get_bone_pose(ref,name,u.AnimPoseSpaces.WORLD)
        current=u.AnimPoseExtensions.get_bone_pose(pose,name,u.AnimPoseSpaces.WORLD)
        # Actual boot loft bottom vertex, y=0.015m, radiusZ=0.079m, weight foot=1.
        # Source (-Y,-X,Z)*100 -> Unreal. No morph affects this sole vertex.
        sole=u.Vector(-1.5,-sign*10.5,0)
        local=u.MathLibrary.inverse_transform_location(rest,sole)
        p=u.MathLibrary.transform_location(current,local)
        feet[side]={'ankle_cm':[current.translation.x,current.translation.y,current.translation.z], 'rigid_sole_vertex_cm':[p.x,p.y,p.z]}
    rows.append({'clip':'idle_combat','time_s':t,'feet':feet})
result={'scope':'Native compressed sequence plus authoritative fully foot-weighted sole vertex. Mesh component runtime offset/contact correction separately documented. No assets modified.','samples':rows}
path=Path(__file__).resolve().parents[1]/'docs/validation/native_idle_sole.json'
path.write_text(json.dumps(result,indent=2))
u.log('NATIVE_IDLE_SOLE '+json.dumps(result))

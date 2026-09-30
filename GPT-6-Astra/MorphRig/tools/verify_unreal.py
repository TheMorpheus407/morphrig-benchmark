"""Read back native imported assets, sampled skeletal poses and root travel."""
from pathlib import Path
import json
import math
import unreal as u
u.load_module('AnimationBlueprintLibrary')
ROOT=Path(__file__).resolve().parents[1]
mesh=u.load_asset('/Game/Operative/SK_Operative')
skel=mesh.get_editor_property('skeleton')
ref=u.AnimPoseExtensions.get_reference_pose(skel)
names=[str(n) for n in u.AnimPoseExtensions.get_bone_names(ref)]
def point(t):
    p=t.translation
    return [p.x,p.y,p.z]
report={'root_name':names[0],'bones':names,'bone_count':len(names),'morphs':[x.get_name() for x in mesh.get_editor_property('morph_targets')],
        'reference_positions_cm':{n:point(u.AnimPoseExtensions.get_bone_pose(ref,n,u.AnimPoseSpaces.WORLD)) for n in ['root','pelvis','head','foot_L','foot_R','emitter_muzzle']},'animations':[]}
for clip in json.loads((ROOT/'docs/animation_manifest.json').read_text())['animations']:
    a=u.load_asset('/Game/Operative/Animations/'+clip['id'])
    if not a: continue
    row={'id':clip['id'],'duration':a.get_play_length()}
    if clip['root_motion_policy']=='root_motion':
        opt=u.AnimPoseEvaluationOptions()
        opt.set_editor_property('extract_root_motion',False)
        opt.set_editor_property('incorporate_root_motion_into_pose',True)
        start=u.AnimPoseExtensions.get_anim_pose_at_time(a,0,opt)
        end=u.AnimPoseExtensions.get_anim_pose_at_time(a,a.get_play_length(),opt)
        a0=point(u.AnimPoseExtensions.get_bone_pose(start,'root',u.AnimPoseSpaces.WORLD))
        a1=point(u.AnimPoseExtensions.get_bone_pose(end,'root',u.AnimPoseSpaces.WORLD))
        row['root_delta_cm']=[y-x for x,y in zip(a0,a1)]
    report['animations'].append(row)
(ROOT/'docs/unreal_pose_validation.json').write_text(json.dumps(report,indent=2))
u.log('MORPHRIG_POSE_VALIDATION '+json.dumps(report))
source_file=ROOT/'docs/blender_pose_samples.json'
if source_file.exists():
    source=json.loads(source_file.read_text())
    result={'coordinates':'Unreal +X forward, +Y right, +Z up; source position (-Y,-X,Z)*100','samples':[]}
    maximum=0
    for clip,samples in source['clips'].items():
        animation=u.load_asset('/Game/Operative/Animations/'+clip)
        if animation is None:continue
        for sample in samples:
            opt=u.AnimPoseEvaluationOptions()
            opt.set_editor_property('evaluation_type',u.AnimDataEvalType.COMPRESSED)
            opt.set_editor_property('extract_root_motion',False)
            opt.set_editor_property('incorporate_root_motion_into_pose',True)
            pose=u.AnimPoseExtensions.get_anim_pose_at_time(animation,sample['time'],opt)
            errors={}
            for bone,data in sample['bones'].items():
                imported=point(u.AnimPoseExtensions.get_bone_pose(pose,bone.replace('.','_'),u.AnimPoseSpaces.WORLD))
                sx,sy,sz=data['head_m'];expected=[-sy*100,-sx*100,sz*100]
                error=math.sqrt(sum((a-b)**2 for a,b in zip(expected,imported)))
                maximum=max(maximum,error)
                errors[bone]={'expected_cm':expected,'imported_cm':imported,'error_cm':error}
            result['samples'].append({'clip':clip,'time':sample['time'],'bones':errors})
    result['maximum_position_error_cm']=maximum
    (ROOT/'docs/unreal_source_pose_comparison.json').write_text(json.dumps(result,indent=2))
    u.log(f'MORPHRIG_SOURCE_POSE_MAX_ERROR_CM={maximum:.6f}')

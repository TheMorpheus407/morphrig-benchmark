"""Read native beacon dimensions and release transform without modifying assets."""
from pathlib import Path
import json
import unreal as u
u.load_module('AnimationBlueprintLibrary')
root=Path(__file__).resolve().parents[1]
mesh=u.load_asset('/Game/Operative/SM_Beacon')
box=mesh.get_bounding_box()
def xyz(v):return [v.x,v.y,v.z]
report={'static_asset':mesh.get_path_name(),'bounds_min_cm':xyz(box.min),'bounds_max_cm':xyz(box.max),'materials':[str(x.material_interface) for x in mesh.static_materials],'bone_samples':[]}
seq=u.load_asset('/Game/Operative/Animations/deploy')
for t in [1.10,1.133333,1.152,1.166667,1.20,1.30]:
    opt=u.AnimPoseEvaluationOptions()
    opt.set_editor_property('evaluation_type',u.AnimDataEvalType.COMPRESSED)
    pose=u.AnimPoseExtensions.get_anim_pose_at_time(seq,t,opt)
    tr=u.AnimPoseExtensions.get_bone_pose(pose,'beacon',u.AnimPoseSpaces.WORLD)
    report['bone_samples'].append({'time':t,'position_cm':xyz(tr.translation),'scale':xyz(tr.scale3d),'rotation_xyzw':[tr.rotation.x,tr.rotation.y,tr.rotation.z,tr.rotation.w]})
(root/'docs/validation/beacon_release_before/native_asset_probe.json').write_text(json.dumps(report,indent=2))
u.log('MORPH_BEACON_PROBE '+json.dumps(report))

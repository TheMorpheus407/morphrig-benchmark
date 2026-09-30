"""Read imported eye rest-frame axes; does not modify assets."""
from pathlib import Path
import json
import unreal as u
u.load_module('AnimationBlueprintLibrary')
root=Path(__file__).resolve().parents[1]
mesh=u.load_asset('/Game/Operative/SK_Operative')
pose=u.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton'))
report={}
for name in ['head','eye_L','eye_R']:
    transform=u.AnimPoseExtensions.get_bone_pose(pose,name,u.AnimPoseSpaces.WORLD)
    axes={}
    for key,axis in [('x',u.Vector(1,0,0)),('y',u.Vector(0,1,0)),('z',u.Vector(0,0,1))]:
        value=transform.rotation.rotate_vector(axis)
        axes[key]=[value.x,value.y,value.z]
    report[name]={'position':[transform.translation.x,transform.translation.y,transform.translation.z],'axes_component':axes}
(root/'docs/validation/native_eye_axes.json').write_text(json.dumps(report,indent=2))
u.log('MORPH_EYE_AXES '+json.dumps(report))

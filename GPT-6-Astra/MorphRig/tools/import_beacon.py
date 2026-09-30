"""Rebuild only the derived persistent beacon and record its imported geometry."""
from pathlib import Path
import json,runpy,math
import unreal as u
root=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(root/'tools/import_unreal.py'),run_name='helpers')
mesh=api['import_beacon']()
box=mesh.get_bounding_box()
xyz=lambda v:[v.x,v.y,v.z]
report={'bounds_min_cm':xyz(box.min),'bounds_max_cm':xyz(box.max),
        'materials':[str(x.material_slot_name) for x in mesh.static_materials],
        'section_count':mesh.get_num_sections(0)}
description=mesh.get_static_mesh_description(0)
vertices=[description.get_vertex_position(u.VertexID(i)) for i in range(description.get_vertex_count())]
contract=json.loads((root/'docs/beacon_export_contract.json').read_text())
native=[xyz(v) for v in vertices]
distance=lambda a,b:math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
report['max_local_vertex_error_cm']=max(min(distance(a,b) for b in native) for a in contract['native_local_vertices_cm'])
opt=u.AnimPoseEvaluationOptions();opt.set_editor_property('evaluation_type',u.AnimDataEvalType.COMPRESSED)
pose=u.AnimPoseExtensions.get_anim_pose_at_time(u.load_asset('/Game/Operative/Animations/deploy'),contract['source_sample_time'],opt)
transform=u.AnimPoseExtensions.get_bone_pose(pose,'beacon',u.AnimPoseSpaces.WORLD)
world=[xyz(transform.rotation.rotate_vector(v)+transform.translation) for v in vertices]
report['source_sample_time']=contract['source_sample_time']
report['max_world_vertex_error_cm']=max(min(distance(a,b) for b in world) for a in contract['source_world_vertices_native_cm'])
report['world_bounds_min_cm']=[min(v[i] for v in world) for i in range(3)]
report['world_bounds_max_cm']=[max(v[i] for v in world) for i in range(3)]
report['vertices']=len(vertices)
assert report['max_local_vertex_error_cm']<.001,report
assert report['max_world_vertex_error_cm']<.01,report
u.log('MORPH_BEACON_IMPORT '+json.dumps(report))
(root/'docs/validation/beacon_native_import.json').write_text(json.dumps(report,indent=2))

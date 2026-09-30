"""Export the authored beacon in Unreal beacon-bone local centimeters.

The static FBX importer maps Blender (x,y,z) to Unreal (-y,-x,z).
The skeletal FBX beacon frame maps Blender bone local (x,y,z) to
Unreal bone local (z,-x,y).  Bake that basis conversion into vertices;
the released component can then use the socket transform at unit scale.
"""
import bpy,json
from mathutils import Vector
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'source/Operative.blend'))
rig=bpy.data.objects['Operative_Rig'];source=bpy.data.objects['Operative_LOD0'];group=source.vertex_groups['beacon'].index
used={v.index for v in source.data.vertices if any(g.group==group and g.weight>.99 for g in v.groups)}
faces=[p for p in source.data.polygons if all(i in used for i in p.vertices)];indices=sorted(set(i for p in faces for i in p.vertices));mapping={old:new for new,old in enumerate(indices)}
transform=rig.data.bones['beacon'].matrix_local.inverted()
bone_local=[transform@source.data.vertices[i].co for i in indices]
verts=[Vector((v.x,-v.z,v.y))*100 for v in bone_local]
mesh=bpy.data.meshes.new('Beacon_Authored');mesh.from_pydata(verts,[],[tuple(mapping[i] for i in p.vertices) for p in faces]);mesh.update()
used_materials=sorted({p.material_index for p in faces})
material_map={old:new for new,old in enumerate(used_materials)}
for index in used_materials:mesh.materials.append(source.data.materials[index])
for dest,src in zip(mesh.polygons,faces):dest.material_index=material_map[src.material_index];dest.use_smooth=src.use_smooth
uv=mesh.uv_layers.new(name='UVMap');source_uv=source.data.uv_layers.active
for dp,sp in zip(mesh.polygons,faces):
    for dl,sl in zip(dp.loop_indices,sp.loop_indices):uv.data[dl].uv=source_uv.data[sl].uv
obj=bpy.data.objects.new('Beacon',mesh);bpy.context.scene.collection.objects.link(obj);bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
ROOT.joinpath('export').mkdir(exist_ok=True)
bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=.01
bpy.ops.export_scene.fbx(filepath=str(ROOT/'export/Beacon.fbx'),use_selection=True,object_types={'MESH'},global_scale=1.,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='-Y',axis_up='Z',bake_anim=False,add_leaf_bones=False,mesh_smooth_type='FACE',path_mode='RELATIVE',embed_textures=False)
report={'units':'centimeters','basis':'Blender beacon local (x,y,z) -> native bone local (z,-x,y)',
        'native_local_vertices_cm':[[v.z*100,-v.x*100,v.y*100] for v in bone_local],
        'materials':[source.data.materials[i].name for i in used_materials],
        'triangles_by_material':{source.data.materials[i].name:sum(len(p.vertices)-2 for p in faces if p.material_index==i) for i in used_materials}}
print('BEACON_EXPORTED',len(verts),sum(len(p.vertices)-2 for p in mesh.polygons))
# Preserve direct source-space evidence for the asymmetric lens, not only its box.
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'source/Operative.blend'))
rig=bpy.data.objects['Operative_Rig']
for pb in rig.pose.bones:
    pb.rotation_mode='QUATERNION'
    for constraint in pb.constraints:constraint.mute=True
for track in rig.animation_data.nla_tracks:track.mute=True
rig.animation_data.action=bpy.data.actions['deploy']
if rig.animation_data.action.slots:rig.animation_data.action_slot=rig.animation_data.action.slots[0]
bpy.context.scene.frame_set(34);bpy.context.view_layer.update()
posed=[rig.pose.bones['beacon'].matrix@v for v in bone_local]
report['source_sample_time']=1.1
report['source_world_vertices_native_cm']=[[-p.y*100,-p.x*100,p.z*100] for p in posed]
(ROOT/'docs/beacon_export_contract.json').write_text(json.dumps(report,indent=2))

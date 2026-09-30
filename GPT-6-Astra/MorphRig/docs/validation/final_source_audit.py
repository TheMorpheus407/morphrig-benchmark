"""Read-only checks against the final frozen Blender source and delivered docs."""
import bpy,json
from pathlib import Path
from mathutils import Vector
from hashlib import file_digest
root=Path(__file__).resolve().parents[2];source=root/'source/Operative.blend'
bpy.ops.wm.open_mainfile(filepath=str(source));rig=bpy.data.objects['Operative_Rig'];mesh=bpy.data.objects['Operative_LOD0']
doc=json.loads((root/'docs/skeleton_and_sockets.json').read_text())
errors=[];coordinate_error=0
for name,spec in doc['bones'].items():
 b=rig.data.bones.get(name)
 if not b:errors.append('Missing bone '+name);continue
 if (b.parent.name if b.parent else None)!=spec['parent']:errors.append('Parent mismatch '+name)
 coordinate_error=max(coordinate_error,(b.head_local-Vector(spec['head'])).length,(b.tail_local-Vector(spec['tail'])).length)
action=bpy.data.actions['FACE__dialogue'];curves={}
for layer in action.layers:
 for strip in layer.strips:
  for slot in action.slots:
   bag=strip.channelbag(slot)
   if bag:
    for fc in bag.fcurves:curves[fc.data_path]=fc
squint={}
for side in ['L','R']:
 path=f'key_blocks["squint.{side}"].value';fc=curves[path];values=[fc.evaluate(f) for f in range(1,422)]
 squint[side]={'curve_exists':True,'keyframes':len(fc.keyframe_points),'minimum':min(values),'maximum':max(values),'all_zero':all(abs(v)<1e-9 for v in values)}
lods=[]
for lod in range(3):
 ob=bpy.data.objects['Operative_LOD'+str(lod)];basis=ob.data.shape_keys.key_blocks['Basis'];nonempty=[]
 for key in ob.data.shape_keys.key_blocks:
  if key.name!='Basis' and max((x.co-y.co).length for x,y in zip(key.data,basis.data))>1e-8:nonempty.append(key.name)
 lods.append({'name':ob.name,'vertices':len(ob.data.vertices),'triangles':sum(len(p.vertices)-2 for p in ob.data.polygons),'material_slots':len(ob.data.materials),'max_influences':max(sum(g.weight>1e-8 for g in v.groups) for v in ob.data.vertices),'source_targets':len(ob.data.shape_keys.key_blocks)-1,'intentionally_nonempty_targets':len(nonempty),'zero_targets':[k.name for k in ob.data.shape_keys.key_blocks if k.name not in nonempty and k.name!='Basis']})
with source.open('rb') as f:sha=file_digest(f,'sha256').hexdigest()
report={'source':'source/Operative.blend','source_sha256':sha,'source_mtime':source.stat().st_mtime,'deformation_bones':sum(b.use_deform for b in rig.data.bones),'deformation_roots':[b.name for b in rig.data.bones if b.use_deform and not b.parent],'documented_rest_coordinate_max_error_m':coordinate_error,'skeleton_doc_errors':errors,'FACE__dialogue_squint':squint,'lods':lods}
(root/'docs/validation/final_source_audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

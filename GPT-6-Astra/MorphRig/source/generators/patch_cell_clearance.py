"""Author a compact tapered cell end to clear the organic wrist during reload.
Coordinates/keys only, all LODs; preserve actions, vertex order, UVs and weights.
INPUT.blend [OUTPUT.blend]
"""
import bpy,sys,json
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent));import character
args=sys.argv[sys.argv.index('--')+1:];src=Path(args[0]).resolve();dst=Path(args[1]).resolve() if len(args)>1 else src
bpy.ops.wm.open_mainfile(filepath=str(src));report=[]
for lod,detail in [(0,1.),(1,.62),(2,.38)]:
 o=bpy.data.objects['Operative_LOD'+str(lod)];auth=character.MeshBuilder(detail);character.build_body(auth)
 ids=[i for i,t in enumerate(auth.tags) if t.startswith('power_cell')]
 head=Vector(character.skeleton_spec()['cell']['head']);axis=(Vector(character.skeleton_spec()['cell']['tail'])-head).normalized()
 maximum=max((Vector(auth.v[i])-head).dot(axis) for i in ids)
 basis=o.data.shape_keys.key_blocks['Basis'];delta={i:Vector(auth.v[i])-basis.data[i].co for i in ids}
 end=.0215
 for key in o.data.shape_keys.key_blocks:
  for i,d in delta.items():key.data[i].co+=d
 for i in ids:o.data.vertices[i].co=basis.data[i].co
 o.data.update();report.append({'mesh':o.name,'cell_vertices':len(ids),'max_delta_m':max(d.length for d in delta.values()),'rest_cell_axis_y_max_authored_m':maximum,'rest_cell_axis_y_max_after_m':end})
text=bpy.data.texts.get('character.py')
if text:text.clear();text.write(Path(character.__file__).read_text())
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(dst));print('CELL_CLEARANCE_PATCH',json.dumps(report))

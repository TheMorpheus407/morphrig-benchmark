"""Recess the globe during squint, preserving all other shapes/actions/weights.
blender -b --factory-startup -P patch_squint_clearance.py -- INPUT.blend [OUTPUT.blend]
"""
import bpy,sys,json
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];src=Path(args[0]).resolve();dst=Path(args[1]).resolve() if len(args)>1 else src
bpy.ops.wm.open_mainfile(filepath=str(src));report=[]
for lod in range(3):
 obj=bpy.data.objects['Operative_LOD'+str(lod)];basis=obj.data.shape_keys.key_blocks['Basis']
 for side in ['L','R']:
  group=obj.vertex_groups['eye.'+side].index
  ids=[v.index for v in obj.data.vertices if any(g.group==group and g.weight>.9 for g in v.groups)]
  target=obj.data.shape_keys.key_blocks['squint.'+side]
  for i in ids:target.data[i].co.y=basis.data[i].co.y+.004
  report.append({'mesh':obj.name,'target':target.name,'eye_vertices':len(ids),'full_value_recession_m':.004})
 obj.data.update()
text=bpy.data.texts.get('character.py')
if text:text.clear();text.write(Path(__file__).with_name('character.py').read_text())
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(dst));print('SQUINT_CLEARANCE',json.dumps(report))

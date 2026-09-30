"""Update only armor-cuff vertices, preserving all vertex indices and actions.
blender -b --factory-startup -P patch_shoulder_clearance.py -- source/Operative.blend
"""
import bpy,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent))
import character
path=Path(sys.argv[sys.argv.index('--')+1]).resolve() if '--' in sys.argv else character.ROOT/'source/Character_Master.blend'
bpy.ops.wm.open_mainfile(filepath=str(path))
for lod,detail in [(0,1.),(1,.62),(2,.38)]:
    obj=bpy.data.objects['Operative_LOD'+str(lod)];m=character.MeshBuilder(detail);character.build_body(m)
    source=obj.data.shape_keys.key_blocks['Basis'].data if obj.data.shape_keys else obj.data.vertices
    indices=[i for i,t in enumerate(m.tags) if t.startswith('shoulder_shell.')]
    assert indices and max(indices)<len(source)
    changes={i:Vector(m.v[i])-source[i].co for i in indices}
    if obj.data.shape_keys:
        for key in obj.data.shape_keys.key_blocks:
            for i,delta in changes.items():key.data[i].co+=delta
    else:
        for i,delta in changes.items():obj.data.vertices[i].co+=delta
    obj.data.update();print('SHOULDER_CLEARANCE',obj.name,len(indices),max(d.length for d in changes.values()))
bpy.context.view_layer.update()
text=bpy.data.texts.get('character.py')
if text:text.clear();text.write(Path(character.__file__).read_text())
bpy.ops.wm.save_as_mainfile(filepath=str(path))

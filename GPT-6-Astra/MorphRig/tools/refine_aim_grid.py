import bpy,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import create_animations
ids=[m['id'] for m in json.loads((root/'docs/animation_manifest.json').read_text())['animations'] if m['id'].startswith('aim_')]
create_animations(bpy.data.objects['Operative_Rig'],bpy.data.objects['Operative_LOD0'],root,ids)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

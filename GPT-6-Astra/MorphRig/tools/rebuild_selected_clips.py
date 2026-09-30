import bpy,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import create_animations
args=sys.argv[sys.argv.index('--')+1:];ids=args[0].split(',')
create_animations(bpy.data.objects['Operative_Rig'],bpy.data.objects['Operative_LOD0'],root,ids)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

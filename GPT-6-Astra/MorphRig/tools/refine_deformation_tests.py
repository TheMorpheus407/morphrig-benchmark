import bpy,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import create_deformation_tests
create_deformation_tests(bpy.data.objects['Operative_Rig'],bpy.data.objects['Operative_LOD0'],root)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

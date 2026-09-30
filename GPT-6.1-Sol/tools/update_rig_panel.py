"""Update embedded animator UI without recreating geometry or animation.

Run: blender -b source/Operative.blend -P tools/update_rig_panel.py
"""
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'source/generators'))
import rig

armature = bpy.data.objects['Operative_Rig']
for name in ('CTRL_face', 'CTRL_settings'):
    control = armature.pose.bones[name]
    for key in control.keys():
        control[key] = float(control[key])
panel = bpy.data.texts.get('Operative_Animator_Panel.py')
if panel is None:
    panel = bpy.data.texts.new('Operative_Animator_Panel.py')
panel.clear()
panel.write(rig.PANEL_SCRIPT)
panel.use_module = True
armature.update_tag()
bpy.context.view_layer.update()
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'source/Operative.blend'))
print('UPDATED_ANIMATOR_PANEL')

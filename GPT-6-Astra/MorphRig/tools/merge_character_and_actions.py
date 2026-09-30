"""Open the final Character_Master and retain the individually-authored action library."""
import bpy
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ids={x['id'] for x in __import__('json').loads((root/'docs/animation_manifest.json').read_text())['animations']}
with bpy.data.libraries.load(str(root/'source/Operative.blend'),link=False) as (src,dst):
 dst.actions=[n for n in src.actions if n.startswith(('EDIT__','FACE__','TEST__')) or n in ids]
for a in bpy.data.actions:a.use_fake_user=True
rig=bpy.data.objects['Operative_Rig']
for pb in rig.pose.bones:
 if pb.bone.use_deform:pb.rotation_mode='QUATERNION'
rig.animation_data_create();rig.animation_data.action=bpy.data.actions['idle_relaxed']
if rig.animation_data.action.slots:rig.animation_data.action_slot=rig.animation_data.action.slots[0]
for o in bpy.data.objects:
 if o.type=='MESH' and o.data.shape_keys:
  key=o.data.shape_keys;key.animation_data_create();key.animation_data.action=bpy.data.actions['FACE__idle_relaxed']
  if key.animation_data.action.slots:key.animation_data.action_slot=key.animation_data.action.slots[0]
bpy.context.scene.render.fps=30;bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=109;bpy.context.scene.frame_set(1)
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative_Merged.blend'))
import os
os.replace(root/'source/Operative_Merged.blend',root/'source/Operative.blend')

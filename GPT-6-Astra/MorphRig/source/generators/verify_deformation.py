"""Render the seven authored deformation acceptance poses from final source."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
path=Path(sys.argv[sys.argv.index('--')+1]).resolve() if '--' in sys.argv else ROOT/'source/Operative.blend'
bpy.ops.wm.open_mainfile(filepath=str(path))
if not any(a.name.startswith('TEST__') for a in bpy.data.actions):
    with bpy.data.libraries.load(str(ROOT/'source/Operative.blend'),link=False) as (src,dst):dst.actions=[n for n in src.actions if n.startswith('TEST__')]
rig=bpy.data.objects['Operative_Rig'];scene=bpy.context.scene;cam=scene.camera
for pb in rig.pose.bones:
    if pb.bone.use_deform:pb.rotation_mode='QUATERNION'
scene.render.resolution_x=700;scene.render.resolution_y=840;scene.cycles.samples=24;cam.data.type='ORTHO';cam.data.ortho_scale=2.24
cam.location=(2.5,-4,2.25);cam.rotation_euler=(Vector((0,0,.95))-cam.location).to_track_quat('-Z','Y').to_euler()
out=ROOT/'docs/rig_validation';out.mkdir(exist_ok=True)
for ob in bpy.data.objects:
    if ob.name.startswith('Operative_LOD') and ob.data.shape_keys:
        if ob.data.shape_keys.animation_data:ob.data.shape_keys.animation_data.action=None
        for k in ob.data.shape_keys.key_blocks:
            if k.name!='Basis':k.value=0
for a in sorted(bpy.data.actions,key=lambda x:x.name):
    if a.name.startswith('TEST__'):
        rig.animation_data.action=a;scene.frame_set(1);bpy.context.view_layer.update();scene.render.filepath=str(out/(a.name+'.png'));bpy.ops.render.render(write_still=True)

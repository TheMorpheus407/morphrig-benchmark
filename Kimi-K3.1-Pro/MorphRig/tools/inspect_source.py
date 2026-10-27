"""Render inspection views of the authoritative Blender source; never alters the saved asset."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 20
scene.cycles.use_denoising = True
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_percentage = 100
cam_data = bpy.data.cameras.new("InspectionCamera")
cam = bpy.data.objects.new("InspectionCamera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

def render(name, location, target, resolution, lens=70, ortho=None):
    cam.location = location
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    if ortho:
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.filepath = str(OUT / name)
    bpy.ops.render.render(write_still=True)

render("source_full_body.png", (1.35, -3.9, 2.10), (0, 0, .94), (760, 1000), ortho=2.10)
render("source_face.png", (.13, -.62, 1.705), (0, -.01, 1.667), (800, 800), lens=70)
print("SOURCE_INSPECTION_RENDERED", flush=True)

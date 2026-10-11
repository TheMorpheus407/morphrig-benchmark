import bpy, os, math
from mathutils import Vector
TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
BLEND = os.path.join(TASK, "source", "Operative.blend")
OUT = os.path.join(TASK, "work", "preview")
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.render.resolution_x = 960
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = 'PNG'
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.cycles.samples = 32
sc.cycles.use_denoising = True

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 3.0
sun.location = (2.0, -2.5, 3.0)
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
sc.collection.objects.link(sun)
fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'AREA'))
fill.data.energy = 150.0; fill.data.size = 2.0; fill.data.color = (0.7, 0.8, 1.0)
fill.location = (-2.0, -1.0, 2.0)
fill.rotation_euler = (math.radians(60), 0, math.radians(-30))
sc.collection.objects.link(fill)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 85
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

SHOTS = [
    ("hand_side_L",  (-1.20, 0.00, 0.80), (-0.245, 0.02, 0.72)),
    ("hand_34_L",    (-0.90, -0.70, 0.95), (-0.245, 0.02, 0.72)),
]
for name, loc, tgt in SHOTS:
    cam.location = Vector(loc)
    d = Vector(tgt) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name, flush=True)
print("RENDER_DONE")

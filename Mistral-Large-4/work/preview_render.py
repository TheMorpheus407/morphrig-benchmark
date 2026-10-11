"""Preview renders of the Operative mesh (verification only, not a deliverable)."""
import bpy, os, math
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(TASK, "source", "Operative.blend")
OUT = os.path.join(TASK, "work", "preview")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 960
sc.render.resolution_y = 540
sc.render.image_settings.file_format = 'PNG'
try:
    sc.eevee.taa_render_samples = 16
except Exception:
    pass
sc.render.film_transparent = False

world = bpy.data.worlds.new("Studio")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.18, 0.18, 0.20, 1.0)
bg.inputs[1].default_value = 0.6
sc.world = world

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 3.0
sun.data.angle = math.radians(30)
sun.location = (2.0, -2.5, 3.0)
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
sc.collection.objects.link(sun)
fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'AREA'))
fill.data.energy = 120.0
fill.data.size = 2.0
fill.data.color = (0.7, 0.8, 1.0)
fill.location = (-2.0, -1.0, 2.0)
fill.rotation_euler = (math.radians(60), 0, math.radians(-30))
sc.collection.objects.link(fill)
# rim light from behind-right to separate silhouette
rim = bpy.data.objects.new("Rim", bpy.data.lights.new("Rim", 'AREA'))
rim.data.energy = 200.0
rim.data.size = 1.5
rim.data.color = (1.0, 0.85, 0.7)
rim.location = (1.5, 2.0, 1.5)
rim.rotation_euler = (math.radians(70), 0, math.radians(150))
sc.collection.objects.link(rim)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

shots = [
    ("front",    (0.0, -4.6, 0.95), (0, 0, 0.92), 50),
    ("side",     (4.6, 0.0, 0.95),  (0, 0, 0.92), 50),
    ("three_q",  (3.3, -3.3, 1.30), (0.05, 0, 1.0), 50),
    ("face",     (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35),
    ("forearm",  (1.10, -0.90, 1.00), (0.245, 0.0, 0.82), 35),
    ("back",     (0.0, 4.6, 0.95),  (0, 0, 0.92), 50),
]
for name, loc, tgt, lens in shots:
    cam.location = Vector(loc)
    cam_data.lens = lens
    look_at(cam, tgt)
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)
print("PREVIEWS_DONE")

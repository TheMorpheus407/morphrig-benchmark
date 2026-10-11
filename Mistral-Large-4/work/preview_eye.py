"""Tight face renders: eye slit + lids + brows + visor band, ID and lit."""
import bpy, os, math
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(TASK, "source", "Operative.blend")
OUT = os.path.join(TASK, "work", "preview")
os.makedirs(OUT, exist_ok=True)

ID_COLORS = [
    (0.90, 0.55, 0.40), (0.25, 0.28, 0.38), (0.60, 0.62, 0.70), (0.30, 0.75, 0.85),
    (0.95, 0.85, 0.20), (0.45, 0.25, 0.15), (0.95, 0.95, 0.95), (0.60, 0.10, 0.12),
]

def set_emission(mat, color, strength=1.0):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (*color, 1.0)
    em.inputs[1].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])

def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def add_lights(sc):
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 3.0
    sun.data.angle = math.radians(30)
    sun.location = (2.0, -2.5, 3.0)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
    sc.collection.objects.link(sun)
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'AREA'))
    fill.data.energy = 150.0
    fill.data.size = 2.0
    fill.data.color = (0.7, 0.8, 1.0)
    fill.location = (-2.0, -1.0, 2.0)
    fill.rotation_euler = (math.radians(60), 0, math.radians(-30))
    sc.collection.objects.link(fill)
    rim = bpy.data.objects.new("Rim", bpy.data.lights.new("Rim", 'AREA'))
    rim.data.energy = 250.0
    rim.data.size = 1.5
    rim.data.color = (1.0, 0.85, 0.7)
    rim.location = (1.5, 2.0, 1.5)
    rim.rotation_euler = (math.radians(70), 0, math.radians(150))
    sc.collection.objects.link(rim)

def black_world(sc):
    world = bpy.data.worlds.new("Black")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs[1].default_value = 0.0
    sc.world = world

SHOTS = [
    # name, loc, target, lens, samples, mode
    ("eye_id",  (0.0, -0.40, 1.645), (0.0, -0.03, 1.645), 65, 8, "id"),
    ("eye_lit", (0.0, -0.40, 1.645), (0.0, -0.03, 1.645), 65, 48, "lit"),
    ("eye_id_L", (-0.40, -0.40, 1.645), (-0.03, -0.03, 1.645), 65, 8, "id"),
]

for name, loc, tgt, lens, samples, mode in SHOTS:
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.resolution_x = 960
    sc.render.resolution_y = 1080
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.film_transparent = False
    sc.cycles.samples = samples
    sc.cycles.use_denoising = (samples >= 32)
    if mode == "id":
        black_world(sc)
        obj = bpy.data.objects["Operative"]
        for i, m in enumerate(obj.data.materials):
            if m is not None and i < len(ID_COLORS):
                set_emission(bpy.data.materials[m.name], ID_COLORS[i], 1.0)
    else:
        world = bpy.data.worlds.new("Studio")
        world.use_nodes = True
        bg = world.node_tree.nodes["Background"]
        bg.inputs[0].default_value = (0.18, 0.18, 0.20, 1.0)
        bg.inputs[1].default_value = 0.6
        sc.world = world
        add_lights(sc)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = lens
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(loc)
    look_at(cam, tgt)
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)
print("EYE_PREVIEWS_DONE")

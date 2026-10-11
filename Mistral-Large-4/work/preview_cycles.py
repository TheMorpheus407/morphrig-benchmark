"""Cycles-CPU preview renders (EEVEE is unreliable headless here; Cycles is deterministic)."""
import bpy, os, math
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
sc.render.film_transparent = False

MATS = list(bpy.data.materials)

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

ID_COLORS = [
    (0.90, 0.55, 0.40), (0.25, 0.28, 0.38), (0.60, 0.62, 0.70), (0.30, 0.75, 0.85),
    (0.95, 0.85, 0.20), (0.45, 0.25, 0.15), (0.95, 0.95, 0.95), (0.60, 0.10, 0.12),
]

def restore_materials():
    # reload original materials from disk
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    return bpy.context.scene

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

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

SHOTS = [
    # name, loc, target, lens, samples
    ("cyc_sil_front",   (0.0, -4.6, 0.95),  (0, 0, 0.92),      50, 8),
    ("cyc_sil_face",    (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35, 8),
    ("cyc_id_front",    (0.0, -4.6, 0.95),  (0, 0, 0.92),      50, 8),
    ("cyc_id_face",     (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35, 8),
    ("cyc_id_forearm",  (1.10, -0.90, 1.00), (0.245, 0.0, 0.82), 35, 8),
    ("cyc_lit_front",   (0.0, -4.6, 0.95),  (0, 0, 0.92),      50, 48),
    ("cyc_lit_face",    (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35, 48),
    ("cyc_lit_forearm", (1.10, -0.90, 1.00), (0.245, 0.0, 0.82), 35, 48),
]

for name, loc, tgt, lens, samples in SHOTS:
    # fresh scene per shot to avoid material state bleed
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
    if name.startswith("cyc_sil"):
        black_world(sc)
        for m in bpy.data.materials:
            set_emission(m, (1.0, 1.0, 1.0), 1.0)
    elif name.startswith("cyc_id"):
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
print("CYCLES_PREVIEWS_DONE")

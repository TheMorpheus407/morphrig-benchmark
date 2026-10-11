"""Silhouette + material-ID preview renders (verification only)."""
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
    sc.eevee.taa_render_samples = 4
except Exception:
    pass
sc.render.film_transparent = False

world = bpy.data.worlds.new("Black")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
bg.inputs[1].default_value = 0.0
sc.world = world
# remove all lights
for ob in list(sc.collection.objects):
    if ob.type == 'LIGHT':
        sc.collection.objects.unlink(ob)
        bpy.data.objects.remove(ob)

MATS = list(bpy.data.materials)
print("MATERIALS:", [m.name for m in MATS])

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

# distinct flat colors per material slot
ID_COLORS = [
    (0.90, 0.55, 0.40),  # 0 Skin   -> warm
    (0.25, 0.28, 0.38),  # 1 Suit   -> dark blue-gray
    (0.60, 0.62, 0.70),  # 2 Armor  -> light gray
    (0.30, 0.75, 0.85),  # 3 Cyber  -> cyan
    (0.95, 0.85, 0.20),  # 4 Emiss  -> yellow
    (0.45, 0.25, 0.15),  # 5 Hair   -> brown
    (0.95, 0.95, 0.95),  # 6 Eye    -> white
    (0.60, 0.10, 0.12),  # 7 Mouth  -> dark red
]

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

shots = [
    ("sil_front",   (0.0, -4.6, 0.95), (0, 0, 0.92), 50),
    ("sil_side",    (4.6, 0.0, 0.95),  (0, 0, 0.92), 50),
    ("sil_face",    (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35),
    ("sil_forearm", (1.10, -0.90, 1.00), (0.245, 0.0, 0.82), 35),
    ("id_front",    (0.0, -4.6, 0.95), (0, 0, 0.92), 50),
    ("id_face",     (0.0, -1.30, 1.62), (0.0, -0.02, 1.62), 35),
    ("id_forearm",  (1.10, -0.90, 1.00), (0.245, 0.0, 0.82), 35),
]

for name, loc, tgt, lens in shots:
    if name.startswith("sil"):
        for m in MATS:
            set_emission(m, (1.0, 1.0, 1.0), 1.0)
    else:
        obj = bpy.data.objects["Operative"]
        slots = obj.data.materials
        for i, m in enumerate(slots):
            if m is not None and i < len(ID_COLORS):
                set_emission(bpy.data.materials[m.name], ID_COLORS[i], 1.0)
    cam.location = Vector(loc)
    cam_data.lens = lens
    look_at(cam, tgt)
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)
print("PREVIEWS2_DONE")

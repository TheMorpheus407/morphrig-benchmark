"""Clean silhouette renders (no bloom, Standard view transform) for quantitative checks."""
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
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = 'PNG'
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
try:
    sc.eevee.taa_render_samples = 1
    sc.eevee.use_bloom = False
except Exception:
    pass
sc.render.film_transparent = False

world = bpy.data.worlds.new("Black")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
bg.inputs[1].default_value = 0.0
sc.world = world
for ob in list(sc.collection.objects):
    if ob.type == 'LIGHT':
        sc.collection.objects.unlink(ob)
        bpy.data.objects.remove(ob)

for mat in bpy.data.materials:
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    em.inputs[1].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs[0])

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 50
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

shots = [
    ("q_front", (0.0, -4.6, 0.95), (0, 0, 0.92)),
    ("q_side",  (4.6, 0.0, 0.95),  (0, 0, 0.92)),
]
for name, loc, tgt in shots:
    cam.location = Vector(loc)
    look_at(cam, tgt)
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)
print("PREVIEWS3_DONE")

"""Headless preview rendering helpers for the MorphRig generators (Blender Python).

render_views() renders several camera views of the current scene with Workbench/EEVEE and tiles them into one PNG,
so generators can be inspected without opening the Blender UI.
Character convention: faces +X, left = +Y, Z up.
"""
import math
import os
import bpy
import numpy as np
from mathutils import Vector, Euler

VIEWS = {
    # name: (direction the camera sits on (unit vector from target), rotation_euler)
    'front': ((1, 0, 0), (math.radians(90), 0, math.radians(90))),
    'back': ((-1, 0, 0), (math.radians(90), 0, math.radians(-90))),
    'left': ((0, 1, 0), (math.radians(90), 0, math.radians(180))),
    'right': ((0, -1, 0), (math.radians(90), 0, 0)),
    'top': ((0, 0, 1), (0, 0, math.radians(90))),
    'q_front_left': ((0.7071, 0.7071, 0.25), None),
    'q_front_right': ((0.7071, -0.7071, 0.25), None),
    'q_back_left': ((-0.7071, 0.7071, 0.25), None),
}


def _look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def setup_world(bg=(0.16, 0.17, 0.19)):
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new('mr_world')
    sc.world.use_nodes = True
    nt = sc.world.node_tree
    bgn = nt.nodes.get('Background')
    if bgn:
        bgn.inputs[0].default_value = (*bg, 1.0)
        bgn.inputs[1].default_value = 1.0


def render_views(out_png, views=('front', 'left', 'back', 'q_front_left'), target=(0, 0, 0.9), dist=4.0, ortho=1.0,
                 res=(480, 720), engine='BLENDER_WORKBENCH', wire=False, shading='STUDIO', color_type='MATERIAL',
                 perspective=None, samples=16, hide=(), light_energy=2.0, wire_thickness=0.0006):
    """Render the visible scene from the named views; tile horizontally. perspective: None -> ortho for axis views,
    persp for quarter views. Returns out_png."""
    sc = bpy.context.scene
    setup_world()
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    if engine == 'BLENDER_WORKBENCH':
        sd = sc.display.shading
        sd.type = 'SOLID'
        sd.light = shading
        sd.color_type = color_type
        sd.show_object_outline = False
        sd.show_specular_highlight = True
        try:
            sd.wireframe_color_type = 'SINGLE'
        except Exception:
            pass
    elif engine == 'CYCLES':
        sc.cycles.samples = samples
        sc.cycles.device = 'GPU'
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type == 'OPTIX')
    if engine == 'CYCLES':
        for ob in sc.objects:
            if ob.type == 'MESH':
                try:
                    ob.cycles.shadow_terminator_offset = 0.15
                    ob.cycles.shadow_terminator_geometry_offset = 0.15
                except Exception:
                    pass
    cam_data = bpy.data.cameras.new('mr_cam')
    cam = bpy.data.objects.new('mr_cam', cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    # key light
    ld = bpy.data.lights.new('mr_sun', 'SUN')
    ld.energy = light_energy
    ld.angle = math.radians(7.0)          # soft shadows in Cycles previews
    lo = bpy.data.objects.new('mr_sun', ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(50), math.radians(10), math.radians(120))
    tiles = []
    tmp_dir = os.path.dirname(out_png) or '.'
    wire_added = []
    if wire:
        line_mat = bpy.data.materials.get('mr_wire_line') or bpy.data.materials.new('mr_wire_line')
        line_mat.diffuse_color = (0.02, 0.02, 0.03, 1.0)
        for ob in list(sc.objects):
            if ob.type == 'MESH' and not ob.hide_render and ob.name not in hide and ob.visible_get():
                n0 = len(ob.data.materials)
                if n0 == 0:
                    m0 = bpy.data.materials.get('mr_wire_base') or bpy.data.materials.new('mr_wire_base')
                    m0.diffuse_color = (0.62, 0.60, 0.58, 1.0)
                    ob.data.materials.append(m0)
                    n0 = 1
                ob.data.materials.append(line_mat)
                md = ob.modifiers.new('mr_wire', 'WIREFRAME')
                md.thickness = wire_thickness
                md.use_replace = False
                md.material_offset = n0
                wire_added.append((ob, md, n0))
    for name in views:
        direction, rot = VIEWS[name]
        dvec = Vector(direction).normalized()
        cam.location = Vector(target) + dvec * dist
        if rot is None:
            _look_at(cam, target)
        else:
            cam.rotation_euler = rot
        use_persp = (rot is None) if perspective is None else perspective
        cam_data.type = 'PERSP' if use_persp else 'ORTHO'
        cam_data.ortho_scale = ortho
        cam_data.lens = 60.0
        cam_data.clip_start, cam_data.clip_end = 0.01 * max(1.0, dist / 4.0), max(50.0, dist * 3.0)
        p = os.path.join(tmp_dir, f'_tile_{name}.png')
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        tiles.append(p)
    imgs = []
    for p in tiles:
        im = bpy.data.images.load(p)
        w, h = im.size
        arr = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        imgs.append(arr)
        bpy.data.images.remove(im)
        os.remove(p)
    sheet = np.concatenate(imgs, axis=1)
    h, w, _ = sheet.shape
    out = bpy.data.images.new('mr_sheet', w, h, alpha=False)
    out.pixels = sheet.ravel().tolist() if w * h < 4_000_000 else sheet.ravel()
    out.filepath_raw = out_png
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    for ob, md, n0 in wire_added:
        ob.modifiers.remove(md)
        try:
            ob.data.materials.pop(index=len(ob.data.materials) - 1)
        except Exception:
            pass
    bpy.data.objects.remove(cam)
    bpy.data.objects.remove(lo)
    return out_png

"""Shared preview renderer for the MorphRig generators.

    import build_preview_lib
    build_preview_lib.render_views(outdir, obj)

Renders a set of orthographic clay views with Cycles on the CPU.
"""

import os
import math
import bpy
from mathutils import Vector

VIEWS = {
    "front": (0.0, 0.0),
    "side": (0.0, 90.0),
    "back": (0.0, 180.0),
    "q34": (24.0, 38.0),
    "head": (4.0, 8.0),
    "headside": (2.0, 78.0),
    "torso": (4.0, 4.0),
    "hands": (10.0, 20.0),
    "chin": (0.0, 0.0),
    "eye": (0.0, 0.0),
}

ZOOM = {
    "head": (1.672, 0.30),
    "headside": (1.660, 0.30),
    "torso": (1.30, 0.62),
    "hands": (0.95, 0.40),
    "chin": (1.575, 0.16),
    "eye": (1.664, 0.13),
}


def setup_render(res=(480, 720), samples=24):
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    scn.cycles.device = 'CPU'
    scn.cycles.samples = samples
    scn.cycles.use_denoising = False
    scn.render.resolution_x = res[0]
    scn.render.resolution_y = res[1]
    scn.render.film_transparent = False
    scn.view_settings.view_transform = 'Standard'

    world = bpy.data.worlds.new("W")
    scn.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.09, 0.10, 0.13, 1.0)
    bg.inputs[1].default_value = 1.0

    for name, loc, energy, size in (
            ("Key", (2.4, -3.0, 2.6), 160.0, 2.0),
            ("Fill", (-2.8, -1.6, 1.5), 55.0, 2.5),
            ("Rim", (0.4, 3.2, 2.4), 120.0, 1.8)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = Vector((0.0, 0.0, 0.95)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        scn.collection.objects.link(ob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 2.1
    cam = bpy.data.objects.new("Cam", cam_data)
    scn.collection.objects.link(cam)
    scn.camera = cam
    return cam


def render_views(outdir, obj=None, views=None, res=(480, 720), samples=24):
    cam = setup_render(res, samples)
    os.makedirs(outdir, exist_ok=True)
    dist = 4.0
    target = Vector((0.0, 0.0, 0.95))
    for name, (elev, azim) in (views or VIEWS).items():
        e = math.radians(elev)
        a = math.radians(azim)
        tz, sc = ZOOM.get(name, (0.95, 2.1))
        target = Vector((0.0, 0.0, tz))
        cam.data.ortho_scale = sc
        cam.location = (target.x + dist * math.sin(a) * math.cos(e),
                        target.y - dist * math.cos(a) * math.cos(e),
                        target.z + dist * math.sin(e))
        d = target - cam.location
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.render.filepath = os.path.join(outdir,
                                                        "prev_%s.png" % name)
        bpy.ops.render.render(write_still=True)
    return outdir

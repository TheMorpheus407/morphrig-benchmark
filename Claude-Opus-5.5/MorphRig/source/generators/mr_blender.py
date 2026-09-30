"""Blender-side helpers: Mesh -> bpy object, preview renders, contact sheets."""
import os
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler


def to_object(name, m, collection=None, smooth=True, groups=True, materials=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in m.v], [], [tuple(f) for f in m.f])
    me.validate(clean_customdata=False)
    me.update()
    if smooth:
        me.shade_smooth()
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    if groups:
        for gname, mask in m.groups.items():
            idx = np.nonzero(mask)[0].tolist()
            if not idx:
                continue
            vg = obj.vertex_groups.new(name=gname)
            vg.add(idx, 1.0, 'REPLACE')
    # seams / sharp edges
    if m.seams or m.sharp:
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        emap = {}
        for e in bm.edges:
            a, b = e.verts[0].index, e.verts[1].index
            emap[(min(a, b), max(a, b))] = e
        for key in m.seams:
            e = emap.get(key)
            if e is not None:
                e.seam = True
        for key in m.sharp:
            e = emap.get(key)
            if e is not None:
                e.smooth = False
        bm.to_mesh(me)
        bm.free()
    if materials:
        for mat in materials:
            me.materials.append(mat)
        if "mat" in m.face_attrs:
            mi = np.array(m.face_attrs["mat"], dtype=np.int32)
            me.polygons.foreach_set("material_index", mi)
    for key, vals in m.face_attrs.items():
        if key == "mat" or len(vals) != len(me.polygons):
            continue
        at = me.attributes.new(key, 'INT', 'FACE')
        at.data.foreach_set("value", np.array([int(x or 0) for x in vals], dtype=np.int32))
    return obj


def add_wire_overlay(obj, thickness=0.0012, color=(0.02, 0.02, 0.02, 1)):
    """Duplicate obj with a wireframe modifier (visualises topology in renders)."""
    dup = obj.copy()
    dup.data = obj.data.copy()
    dup.name = obj.name + "_wire"
    bpy.context.scene.collection.objects.link(dup)
    mod = dup.modifiers.new("wire", 'WIREFRAME')
    mod.thickness = thickness
    mod.use_replace = True
    mod.use_even_offset = False
    mat = bpy.data.materials.get("_wire") or bpy.data.materials.new("_wire")
    mat.diffuse_color = color
    dup.data.materials.clear()
    dup.data.materials.append(mat)
    dup.color = color
    return dup


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 30
    return sc


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def preview_render(path, views, res=(640, 900), engine='BLENDER_WORKBENCH', ortho=True,
                   target=(0, 0, 0.9), dist=3.0, ortho_scale=2.0, color_type='MATERIAL',
                   show_wire=False, samples=16, extra_setup=None):
    """Render several views and tile them into one PNG (contact sheet)."""
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    if sc.world is None:
        sc.world = bpy.data.worlds.new("PreviewWorld")
    sc.world.color = (0.18, 0.19, 0.21)
    if engine == 'BLENDER_WORKBENCH':
        sh = sc.display.shading
        sh.light = 'STUDIO'
        sh.color_type = color_type
        sh.show_cavity = False
        sh.show_object_outline = False
        sh.show_specular_highlight = True
        sc.display.shading.show_backface_culling = False
        if show_wire:
            pass
    elif engine == 'CYCLES':
        sc.cycles.samples = samples
        sc.cycles.device = 'GPU'
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'OPTIX'
            prefs.get_devices()
            for d in prefs.devices:
                d.use = (d.type == 'OPTIX')
        except Exception:
            pass
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.get("PreviewCam") or bpy.data.objects.new("PreviewCam", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    if extra_setup:
        extra_setup(sc)
    tiles = []
    tmpdir = os.path.dirname(path)
    for i, vw in enumerate(views):
        az = math.radians(vw.get("az", 0))
        el = math.radians(vw.get("el", 0))
        tgt = Vector(vw.get("target", target))
        dd = vw.get("dist", dist)
        cam.location = tgt + Vector((math.sin(az) * math.cos(el) * dd, -math.cos(az) * math.cos(el) * dd, math.sin(el) * dd))
        look_at(cam, tgt)
        if vw.get("ortho", ortho):
            cam_data.type = 'ORTHO'
            cam_data.ortho_scale = vw.get("ortho_scale", ortho_scale)
        else:
            cam_data.type = 'PERSP'
            cam_data.lens = vw.get("lens", 50)
        cam_data.clip_start = 0.01
        cam_data.clip_end = 100
        fp = os.path.join(tmpdir, f"_tile_{i}.png")
        sc.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(fp)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], img.channels)
        tiles.append(px[:, :, :4] if img.channels >= 4 else px)
        bpy.data.images.remove(img)
        os.remove(fp)
    # tile horizontally
    sheet = np.concatenate(tiles, axis=1)
    h, w = sheet.shape[:2]
    out = bpy.data.images.new("sheet", w, h, alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path


def preview_material(name, color, rough=0.5, sss=0.0, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if sss > 0:
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Radius"].default_value = (0.01, 0.004, 0.002)
        bsdf.inputs["Subsurface Scale"].default_value = 1.0
    mat.diffuse_color = (*color, 1)
    return mat


def studio_lights(target=(0, 0, 1.0), scale=1.0, world_strength=0.35):
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new("PreviewWorld")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.20, 0.21, 0.23, 1)
    bg.inputs[1].default_value = world_strength
    t = Vector(target)
    specs = [("Key", (-1.6, -2.2, 1.3), 900.0, 1.2, (1.0, 0.96, 0.9)),
             ("Fill", (2.0, -1.5, 0.4), 300.0, 2.0, (0.85, 0.9, 1.0)),
             ("Rim", (0.8, 2.2, 1.6), 700.0, 1.0, (0.9, 0.95, 1.0))]
    for name, off, power, size, col in specs:
        ld = bpy.data.lights.get("PV_" + name) or bpy.data.lights.new("PV_" + name, 'AREA')
        ld.energy = power * scale * scale
        ld.size = size * scale
        ld.color = col
        ob = bpy.data.objects.get("PV_" + name) or bpy.data.objects.new("PV_" + name, ld)
        if ob.name not in sc.collection.objects:
            sc.collection.objects.link(ob)
        ob.location = t + Vector(off) * scale
        look_at(ob, t)

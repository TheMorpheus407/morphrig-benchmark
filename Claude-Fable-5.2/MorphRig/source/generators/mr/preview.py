"""Quick look-dev renders used while iterating on the generators (Workbench / EEVEE, headless)."""
import math
import os
import bpy
from mathutils import Vector, Matrix


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 30
    return sc


def _cam(name='PreviewCam'):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        bpy.context.scene.collection.objects.link(cam)
    return cam


def look_at(cam, eye, target):
    eye = Vector(eye)
    target = Vector(target)
    fwd = (target - eye).normalized()
    up = Vector((0, 0, 1))
    if abs(fwd.dot(up)) > 0.999:
        up = Vector((0, 1, 0))
    right = fwd.cross(up).normalized()
    up2 = right.cross(fwd)
    m = Matrix((right, up2, -fwd)).transposed().to_4x4()
    m.translation = eye
    cam.matrix_world = m


VIEWS = {
    'front': ((0, -1, 0), 0.0),
    'back': ((0, 1, 0), 0.0),
    'left': ((1, 0, 0), 0.0),
    'right': ((-1, 0, 0), 0.0),
    'fl': ((0.7, -0.7, 0), 0.12),
    'fr': ((-0.7, -0.7, 0), 0.12),
    'bl': ((0.7, 0.7, 0), 0.12),
    'br': ((-0.7, 0.7, 0), 0.12),
    'top': ((0, -0.02, 1), 0.0),
    'topdown': ((0, -0.62, 0.78), 0.0),
}


def setup_workbench(sc, res=(900, 1200), matcap=True):
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'MATERIAL'
    sh.show_cavity = True
    sh.cavity_type = 'BOTH'
    sh.show_object_outline = False
    sh.show_shadows = False
    sh.show_specular_highlight = True
    sc.display.render_aa = '8'
    if sc.world is None:
        sc.world = bpy.data.worlds.new('World')
    sc.world.color = (0.20, 0.21, 0.23)
    sc.view_settings.view_transform = 'Standard'


def render_view(path, view='front', center=(0, 0, 0.9), height=1.95, ortho=True, dist=6.0, res=None, lens=85):
    sc = bpy.context.scene
    cam = _cam()
    sc.camera = cam
    if res:
        sc.render.resolution_x, sc.render.resolution_y = res
    d, lift = VIEWS[view] if isinstance(view, str) else view
    dv = Vector(d).normalized()
    eye = Vector(center) + dv * dist + Vector((0, 0, lift * dist))
    look_at(cam, eye, center)
    if ortho:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = height * max(1.0, sc.render.resolution_x / sc.render.resolution_y)
        if sc.render.resolution_x < sc.render.resolution_y:
            cam.data.ortho_scale = height
    else:
        cam.data.type = 'PERSP'
        cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100
    sc.render.filepath = path
    sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)


def sheet(paths, out, cols=None):
    """Tile images horizontally (or into a grid) with ffmpeg."""
    import subprocess
    cols = cols or len(paths)
    rows = int(math.ceil(len(paths) / cols))
    args = ['ffmpeg', '-y', '-loglevel', 'error']
    for p in paths:
        args += ['-i', p]
    if rows == 1:
        flt = ''.join('[%d:v]' % i for i in range(len(paths))) + 'hstack=inputs=%d' % len(paths) if len(paths) > 1 else 'null'
    else:
        layout = '|'.join('%s_%s' % ('+'.join(['w0'] * c) if c else '0', '+'.join(['h0'] * r) if r else '0')
                          for r in range(rows) for c in range(cols))[:]
        layout = '|'.join(layout.split('|')[:len(paths)])
        flt = ''.join('[%d:v]' % i for i in range(len(paths))) + 'xstack=inputs=%d:layout=%s:fill=black' % (len(paths), layout)
    args += ['-filter_complex', flt, '-frames:v', '1', '-update', '1', out]
    subprocess.run(args, check=True)
    for p in paths:
        if p != out and os.path.exists(p):
            os.remove(p)


def add_wire(ob, thickness=0.00025, color=(0.02, 0.02, 0.02, 1.0)):
    """Black wire overlay copy (Wireframe modifier) for topology renders."""
    dup = ob.copy()
    dup.data = ob.data.copy()
    dup.name = ob.name + '_wire'
    bpy.context.scene.collection.objects.link(dup)
    mat = bpy.data.materials.get('PV_Wire') or bpy.data.materials.new('PV_Wire')
    mat.diffuse_color = color
    dup.data.materials.clear()
    dup.data.materials.append(mat)
    m = dup.modifiers.new('Wire', 'WIREFRAME')
    m.thickness = thickness
    m.use_replace = True
    m.use_even_offset = False
    return dup

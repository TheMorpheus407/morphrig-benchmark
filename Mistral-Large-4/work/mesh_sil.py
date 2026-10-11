"""Project mesh vertices to the q_front/q_side cameras and print silhouette ASCII,
plus a ray-cast ground-truth map of what the render actually shows."""
import bpy, os
import numpy as np
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(TASK, "source", "Operative.blend")

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
obj = bpy.data.objects["Operative"]
me = obj.data
verts = np.array([v.co[:] for v in me.vertices], dtype=np.float64)

W, H = 960, 1080
SENSOR = 36.0

def setup_cam(loc, tgt, lens=50):
    cam_data = bpy.data.cameras.new("TmpCam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("TmpCam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = Vector(loc)
    d = Vector(tgt) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    return cam

def project(cam, pts, lens):
    """pts: (N,3) world -> (px, py, depth) or None if behind."""
    m = cam.matrix_world.inverted()
    P = (m @ Vector((0, 0, 0)))  # dummy
    out = []
    mw = cam.matrix_world
    mi = mw.inverted()
    for p in pts:
        pc = mi @ Vector(p)
        x, y, z = pc.x, pc.y, pc.z
        if z > -1e-6:
            out.append(None)
            continue
        f_px = lens * max(W, H) / SENSOR
        px = W / 2.0 + x / (-z) * f_px
        py = H / 2.0 - y / (-z) * f_px
        out.append((px, py, -z))
    return out

def ascii_map(mask_fn, w=90, title=""):
    nh = int(H * (w / W) * 0.5)
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, W - 1, w).astype(int)
    print("== " + title)
    for yy in ys:
        line = []
        for xx in xs:
            line.append("#" if mask_fn(xx, yy) else ".")
        print("".join(line))

for name, loc, tgt in (("front", (0.0, -4.6, 0.95), (0, 0, 0.92)),
                       ("side", (4.6, 0.0, 0.95), (0, 0, 0.92))):
    cam = setup_cam(loc, tgt)
    # vertex-based mask
    pro = [p for p in project(cam, verts, 50) if p is not None]
    def vmask(xx, yy, pro=pro):
        for (px, py, dep) in pro:
            if abs(px - xx) <= 5 and abs(py - yy) <= 9:
                return True
        return False
    ascii_map(vmask, title="MESH VERTS projected (%s)" % name)
    # triangle-rasterized mask (sample triangle interiors)
    def tmask(xx, yy):
        # quick: sample each triangle's bounding box at low res is slow; use barycentric on a coarse grid
        return False
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(bpy.data.cameras["TmpCam"])

# ray-cast ground truth for the render: what surface is at each pixel?
print()
for name, loc, tgt in (("front", (0.0, -4.6, 0.95), (0, 0, 0.92)),):
    cam = setup_cam(loc, tgt)
    mw = cam.matrix_world
    lens = 50
    f_px = lens * max(W, H) / SENSOR
    dg = bpy.context.evaluated_depsgraph_get()
    w, nh = 90, int(H * (90 / W) * 0.5)
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, W - 1, w).astype(int)
    print("== RAYCAST map (%s): letter = material slot of first hit, . = no hit" % name)
    letters = "01234567"
    for yy in ys:
        line = []
        for xx in xs:
            x_ndc = (xx + 0.5) / W * 2 - 1
            y_ndc = 1 - 2 * (yy + 0.5) / H
            d_cam = Vector((x_ndc * (W / 2) / f_px, y_ndc * (H / 2) / f_px, -1.0)).normalized()
            d_world = (mw.to_3x3() @ d_cam).normalized()
            hit, loc_h, nrm, idx, obj_h, mat_h = sc.ray_cast(dg, mw.translation, d_world)
            if hit:
                mi = me.polygons[idx].material_index if obj_h and obj_h.name == "Operative" else -1
                line.append(letters[mi] if 0 <= mi < 8 else "?")
            else:
                line.append(".")
        print("".join(line))
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(bpy.data.cameras["TmpCam"])
print("MESH_SIL_DONE")

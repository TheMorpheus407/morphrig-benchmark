"""Compare rendered silhouette row extents (in meters) against mesh-projected extents.
Correct for Blender sensor fit AUTO: sensor_width maps to the LARGER image dimension."""
import bpy, os
import numpy as np
from mathutils import Vector

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(TASK, "source", "Operative.blend")
OUT = os.path.join(TASK, "work", "preview")

bpy.ops.wm.open_mainfile(filepath=BLEND)
obj = bpy.data.objects["Operative"]
me = obj.data
verts = np.array([v.co[:] for v in me.vertices], dtype=np.float64)

cams = {
    "q_front": ((0.0, -4.6, 0.95), (0, 0, 0.92), 50),
    "q_side":  ((4.6, 0.0, 0.95), (0, 0, 0.92), 50),
}
SENSOR = 36.0

for name, (loc, tgt, lens) in cams.items():
    img = bpy.data.images.load(os.path.join(OUT, name + ".png"))
    W, H = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)
    lum = px[:, :, 0]
    fit = max(W, H)
    f_px = lens * fit / SENSOR          # px per meter at depth 1
    D = (Vector(tgt) - Vector(loc)).length
    vis_w = D * W / f_px                # visible width in m at target depth
    vis_h = D * H / f_px
    print("== %s  (%dx%d) f_px=%.0f vis=%.2fx%.2f m  white px: %d" %
          (name, W, H, f_px, vis_w, vis_h, int((lum > 0.5).sum())))
    d = (Vector(tgt) - Vector(loc)).normalized()
    up = Vector((0, 0, 1))
    right = d.cross(up).normalized()
    rel = verts - np.array(loc)
    cx = rel @ np.array(right)
    cy = rel @ np.array(up)
    cz = rel @ np.array(d)
    with np.errstate(divide='ignore', invalid='ignore'):
        ppx = W / 2.0 + cx / cz * f_px
        ppy = H / 2.0 - cy / cz * f_px
    bands = 27
    print("band  z_top  z_bot | render xmin xmax (m) | mesh xmin xmax (m) | verdict")
    for b in range(bands):
        y0 = b * H / bands
        y1 = (b + 1) * H / bands
        band = lum[int(y0):int(y1), :]
        cols = np.where((band > 0.5).any(axis=0))[0]
        m = (ppy >= y0) & (ppy < y1) & (cz > 1.0)
        mv = verts[m]
        mc = cx[m]
        mcy = cy[m]
        mcz = cz[m]
        if len(cols) == 0 and len(mv) == 0:
            continue
        if len(cols) and len(mv):
            rx0 = (cols.min() / W - 0.5) * vis_w
            rx1 = (cols.max() / W - 0.5) * vis_w
            # mesh camera-space x scaled to target depth, then to meters
            mx = mc / mcz * D
            mz = mcy / mcz * D + tgt[2]
            ok = abs(rx0 - mx.min()) < 0.05 and abs(rx1 - mx.max()) < 0.05
            print("%3d  %6.3f %6.3f | %+7.3f %+7.3f | %+7.3f %+7.3f | %s" %
                  (b, mz.max(), mz.min(), rx0, rx1, mx.min(), mx.max(), "OK" if ok else "DIFF"))
        else:
            print("%3d  render_cols=%d mesh_verts=%d  MISMATCH" % (b, len(cols), len(mv)))
    bpy.data.images.remove(img)
print("ANALYSIS_DONE")

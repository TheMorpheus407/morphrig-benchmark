"""Binary-threshold ASCII of the q_ silhouette renders."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")

for name in ("q_front", "q_side"):
    img = bpy.data.images.load(os.path.join(OUT, name + ".png"))
    W, H = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)
    lum = px[:, :, 0]
    w = 90
    nh = int(H * (w / W) * 0.5)
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, W - 1, w).astype(int)
    small = lum[np.ix_(ys, xs)]
    print("== %s (%dx%d)" % (name, W, H))
    for row in small:
        print("".join("#" if v > 0.5 else "." for v in row))
    bpy.data.images.remove(img)
    print()

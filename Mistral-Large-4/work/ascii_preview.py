"""Downsample preview PNGs to contrast-stretched ASCII luminance grids."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")

CH = " .:-=+*#%@"

def show(path, w=100):
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
    lum = (0.2126 * px[:, :, 0] + 0.7152 * px[:, :, 1] + 0.0722 * px[:, :, 2]) * px[:, :, 3]
    h = img.size[1]
    nh = max(1, int(h * (w / img.size[0]) * 0.5))
    ys = np.linspace(0, h - 1, nh).astype(int)
    xs = np.linspace(0, img.size[0] - 1, w).astype(int)
    small = lum[np.ix_(ys, xs)]
    lo, hi = np.percentile(small, 5), np.percentile(small, 98)
    rng = max(hi - lo, 1e-6)
    norm = np.clip((small - lo) / rng, 0, 1)
    print("== %s  (%dx%d)  mean=%.3f std=%.3f  p5=%.3f p98=%.3f" %
          (os.path.basename(path), img.size[0], img.size[1], lum.mean(), lum.std(), lo, hi))
    for row in norm:
        print("".join(CH[min(9, int(v * 9.999))] for v in row))
    bpy.data.images.remove(img)

for name in ("front", "side", "three_q", "face", "forearm", "back"):
    show(os.path.join(OUT, name + ".png"))
    print()

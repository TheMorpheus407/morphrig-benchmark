import bpy, os
import numpy as np
TASK = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
OUT = os.path.join(TASK, "work", "preview")
CH = " .:-=+*#%@"
def load(name):
    img = bpy.data.images.load(os.path.join(OUT, name + ".png"))
    W, H = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]
    return px[:, :, :3], W, H
def grid(arr, w, title):
    H = arr.shape[0]
    nh = max(1, int(H * (w / arr.shape[1]) * 0.5))
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, arr.shape[1] - 1, w).astype(int)
    small = arr[np.ix_(ys, xs)]
    print("== " + title)
    lum = small.mean(axis=2)
    lo, hi = np.percentile(lum, 5), np.percentile(lum, 99)
    norm = np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)
    for row in norm:
        print("".join(CH[min(9, int(v * 9.999))] for v in row))
    print()
for nm in ("hand_side_L", "hand_34_L"):
    px, W, H = load(nm)
    grid(px, 110, nm + " LIT (side view of left hand; char faces LEFT in this view)")

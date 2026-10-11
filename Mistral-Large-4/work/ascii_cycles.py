"""ASCII views of the Cycles previews: binary silhouettes, material-ID maps, lit luminance."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")
CH = " .:-=+*#%@"
ID_LETTERS = "01234567"
ID_COLORS = np.array([
    (0.90, 0.55, 0.40), (0.25, 0.28, 0.38), (0.60, 0.62, 0.70), (0.30, 0.75, 0.85),
    (0.95, 0.85, 0.20), (0.45, 0.25, 0.15), (0.95, 0.95, 0.95), (0.60, 0.10, 0.12),
], dtype=np.float32)

def load(name):
    img = bpy.data.images.load(os.path.join(OUT, name + ".png"))
    W, H = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]  # flip: Blender rows are bottom-up
    return px[:, :, :3], W, H

def grid(arr, w, mode, title):
    H = arr.shape[0]
    nh = max(1, int(H * (w / arr.shape[1]) * 0.5))
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, arr.shape[1] - 1, w).astype(int)
    small = arr[np.ix_(ys, xs)]
    print("== " + title)
    if mode == "binary":
        for row in small.mean(axis=2):
            print("".join("#" if v > 0.5 else "." for v in row))
    elif mode == "id":
        for row in small:
            line = []
            for p in row:
                d = np.abs(ID_COLORS - p).sum(axis=1)
                i = int(d.argmin())
                line.append(ID_LETTERS[i] if d[i] < 0.25 else ".")
            print("".join(line))
    else:  # lit, contrast-stretched
        lum = small.mean(axis=2)
        lo, hi = np.percentile(lum, 5), np.percentile(lum, 99)
        norm = np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)
        for row in norm:
            print("".join(CH[min(9, int(v * 9.999))] for v in row))
    print()

for name in ("cyc_sil_front", "cyc_sil_face"):
    px, W, H = load(name)
    grid(px, 90, "binary", name + " SILHOUETTE")
for name in ("cyc_id_front", "cyc_id_face", "cyc_id_forearm"):
    px, W, H = load(name)
    grid(px, 90, "id", name + " MATERIAL ID (0=Skin 1=Suit 2=Armor 3=Cyber 4=Emiss 5=Hair 6=Eye 7=Mouth)")
for name in ("cyc_lit_face", "cyc_lit_forearm"):
    px, W, H = load(name)
    grid(px, 90, "lit", name + " LIT")

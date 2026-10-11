"""ASCII view of the tight eye shots (id + lit)."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")
CH = " .:-=+*#%@"
ID_LETTERS = "01234567"
ID_NAMES = ["Skin", "Suit", "Armor", "Cyber", "Emiss", "Hair", "Eye", "Mouth"]
ID_COLORS = np.array([
    (0.90, 0.55, 0.40), (0.25, 0.28, 0.38), (0.60, 0.62, 0.70), (0.30, 0.75, 0.85),
    (0.95, 0.85, 0.20), (0.45, 0.25, 0.15), (0.95, 0.95, 0.95), (0.60, 0.10, 0.12),
], dtype=np.float32)

def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def load(name):
    img = bpy.data.images.load(os.path.join(OUT, name + ".png"))
    W, H = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]
    return px[:, :, :3], W, H

def grid(arr, w, mode, title):
    H = arr.shape[0]
    nh = max(1, int(H * (w / arr.shape[1]) * 0.5))
    ys = np.linspace(0, H - 1, nh).astype(int)
    xs = np.linspace(0, arr.shape[1] - 1, w).astype(int)
    small = arr[np.ix_(ys, xs)]
    print("== " + title)
    if mode == "id":
        lin = srgb_to_linear(small.reshape(-1, 3)).reshape(small.shape)
        for row in lin:
            line = []
            for p in row:
                d = np.abs(ID_COLORS - p).sum(axis=1)
                i = int(d.argmin())
                line.append(ID_LETTERS[i] if d[i] < 0.22 else ".")
            print("".join(line))
    else:
        lum = small.mean(axis=2)
        lo, hi = np.percentile(lum, 5), np.percentile(lum, 99)
        norm = np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)
        for row in norm:
            print("".join(CH[min(9, int(v * 9.999))] for v in row))
    print()

for name, mode, title in [
    ("eye_id", "id", "eye_id MATERIAL ID (0=Skin 1=Suit 2=Armor 3=Cyber 4=Emiss 5=Hair 6=Eye 7=Mouth)"),
    ("eye_id_L", "id", "eye_id_L (left-eye closeup) MATERIAL ID"),
    ("eye_lit", "lit", "eye_lit LIT"),
]:
    px, W, H = load(name)
    grid(px, 110, mode, title)
print("ASCII_EYE_DONE")

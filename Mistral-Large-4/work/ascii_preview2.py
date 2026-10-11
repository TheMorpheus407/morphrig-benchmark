"""ASCII views of silhouette (shape) and material-ID (slot) renders."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")

CH = " .:-=+*#%@"
ID_LETTERS = "01234567"  # material slot index -> letter (0=Skin 1=Suit 2=Armor 3=Cyber 4=Emiss 5=Hair 6=Eye 7=Mouth)
ID_COLORS = np.array([
    (0.90, 0.55, 0.40), (0.25, 0.28, 0.38), (0.60, 0.62, 0.70), (0.30, 0.75, 0.85),
    (0.95, 0.85, 0.20), (0.45, 0.25, 0.15), (0.95, 0.95, 0.95), (0.60, 0.10, 0.12),
], dtype=np.float32)

def grid(path, w, mode):
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[:, :, :3]
    h = img.size[1]
    nh = max(1, int(h * (w / img.size[0]) * 0.5))
    ys = np.linspace(0, h - 1, nh).astype(int)
    xs = np.linspace(0, img.size[0] - 1, w).astype(int)
    small = px[np.ix_(ys, xs)]
    if mode == "sil":
        lum = small.mean(axis=2)
        print("== %s  SILHOUETTE  max=%.2f" % (os.path.basename(path), lum.max()))
        for row in lum:
            print("".join(CH[min(9, int(v * 9.999))] for v in row))
    else:
        print("== %s  MATERIAL ID (0=Skin 1=Suit 2=Armor 3=Cyber 4=Emiss 5=Hair 6=Eye 7=Mouth)" % os.path.basename(path))
        for row in small:
            line = []
            for p in row:
                d = np.abs(ID_COLORS - p).sum(axis=1)
                i = int(d.argmin())
                line.append(ID_LETTERS[i] if d[i] < 0.18 else ".")
            print("".join(line))
    bpy.data.images.remove(img)

for name in ("sil_front", "sil_side", "sil_face", "sil_forearm"):
    grid(os.path.join(OUT, name + ".png"), 100, "sil")
    print()
for name in ("id_front", "id_face", "id_forearm"):
    grid(os.path.join(OUT, name + ".png"), 100, "id")
    print()

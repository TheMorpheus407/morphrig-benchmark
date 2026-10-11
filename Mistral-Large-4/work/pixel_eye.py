"""Pixel-level check of the lit eye render: horizontal + vertical scanlines
through the left-eye slit, expecting sclera (bright) at the almond edges,
teal iris mid, dark pupil at the center."""
import bpy, os
import numpy as np

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(TASK, "work", "preview")

img = bpy.data.images.load(os.path.join(OUT, "eye_lit.png"))
W, H = img.size[0], img.size[1]
px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]  # top-up
rgb = px[:, :, :3]

# left eye center ~ pixel (200, 540) per projection math; scan a horizontal band
print("horizontal scanline y=540, x=130..270 (left eye):")
for x in range(130, 271, 5):
    r, g, b = rgb[540, x]
    print(f"  x={x:4d}  rgb=({r:.3f},{g:.3f},{b:.3f})")
print("vertical scanline x=200, y=470..610:")
for y in range(470, 611, 5):
    r, g, b = rgb[y, 200]
    print(f"  y={y:4d}  rgb=({r:.3f},{g:.3f},{b:.3f})")
print("PIXEL_EYE_DONE")

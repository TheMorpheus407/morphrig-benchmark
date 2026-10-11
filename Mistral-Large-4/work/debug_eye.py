import bpy, os, math

ROOT = "/home/morpheus/Documents/Morpheus-Produktion/Benchmarks/MorphRig/Mistral-Large-4"
TEX = os.path.join(ROOT, "source/textures")

# --- 1) Eye_BC.png painted pixel check: pupil should be dark at (x=128, y=256) bottom-up
img = bpy.data.images.load(os.path.join(TEX, "Eye_BC.png"))
W, H = img.size
print("Eye_BC size:", W, H)
def px(x, y):  # y from bottom
    i = (y * W + x) * 4
    return tuple(round(img.pixels[i + k], 4) for k in range(4))
print("pupil center (128,256):", px(128, 256))
print("iris ring   (128+38,256):", px(128 + 38, 256))   # rad~0.15 -> iris
print("iris ring   (128+58,256):", px(128 + 58, 256))   # rad~0.23 -> iris edge
print("limbal      (128+70,256):", px(128 + 70, 256))   # rad~0.27 -> limbal
print("sclera      (128+90,256):", px(128 + 90, 256))   # rad~0.35 -> sclera
print("sclera up   (128,256+90):", px(128, 256 + 90))
print("corner      (10,10):", px(10, 10))
bpy.data.images.remove(img)

# --- 2) eye vert UVs + material links from the saved blend
bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "source/Operative.blend"))
obj = bpy.data.objects["Operative"]
me = obj.data
uvl = me.uv_layers["UVMap"]
print("UV layers:", [l.name for l in me.uv_layers])

# eye verts: material 6 (Eye), near (-0.042, -0.0947, 1.645) for L, (+0.042,...) for R
eyes = []
for v in me.vertices:
    if abs(v.co.x - 0.042) < 1e-4 or abs(v.co.x + 0.042) < 1e-4:
        # filter to those near eye center height
        if abs(v.co.y + 0.0947) < 0.02 and abs(v.co.z - 1.645) < 0.02:
            eyes.append(v)
print("eye-ish verts:", len(eyes))
# find the front-most vertex of each eye (min y)
for sgn, side in ((1.0, "R"), (-1.0, "L")):
    cand = [v for v in eyes if v.co.x * sgn > 0]
    if not cand:
        print(side, "no verts"); continue
    front = min(cand, key=lambda v: v.co.y)
    # UV of all loops at this vertex
    uvs = set()
    for lp in me.loops:
        if lp.vertex_index == front.index:
            uvs.add(tuple(round(c, 4) for c in uvl.data[lp.index].uv))
    print(f"{side} front vert co={tuple(round(c,5) for c in front.co)} uvs={sorted(uvs)}")

# UV range over all eye-material faces
lo = [9, 9]; hi = [-9, -9]
n = 0
for p in me.polygons:
    if p.material_index == 6:
        for li in p.loop_indices:
            u, v = uvl.data[li].uv
            lo[0] = min(lo[0], u); lo[1] = min(lo[1], v)
            hi[0] = max(hi[0], u); hi[1] = max(hi[1], v)
            n += 1
print("Eye-mat UV loops:", n, "u range", round(lo[0], 4), round(hi[0], 4),
      "v range", round(lo[1], 4), round(hi[1], 4))

# --- 3) Eye material node tree links
mat = bpy.data.materials["Eye"]
nt = mat.node_tree
print("--- Eye material nodes ---")
for nd in nt.nodes:
    print(" node:", nd.type, nd.name,
          "interp:", getattr(nd, "interpolation", None),
          "img:", (nd.image.name if getattr(nd, "image", None) else None))
print("--- Eye material links ---")
for lk in nt.links:
    print(" link:", lk.from_node.name, lk.from_socket.name, "->",
          lk.to_node.name, lk.to_socket.name)
bsdf = nt.nodes.get("Principled BSDF")
print("Base Color input links:", [lk.from_node.name for lk in bsdf.inputs["Base Color"].links])
print("Roughness input links:", [lk.from_node.name for lk in bsdf.inputs["Roughness"].links])
print("Normal input links:", [lk.from_node.name for lk in bsdf.inputs["Normal"].links])

# compare with Skin (also no team mask) and Suit (team mask)
for name in ("Skin", "Suit"):
    m2 = bpy.data.materials[name]
    b2 = m2.node_tree.nodes.get("Principled BSDF")
    print(f"{name} Base Color links:", [lk.from_node.name for lk in b2.inputs["Base Color"].links])

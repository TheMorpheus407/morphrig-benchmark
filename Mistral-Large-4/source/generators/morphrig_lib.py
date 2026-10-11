"""MorphRig shared library: mesh building, materials, textures, UV packing, rigging helpers.

Coordinate conventions (Blender scene):
  - Units: meters, scale_length = 1.0
  - Character stands at origin, feet on Z=0, up = +Z, forward (facing) = -Y, right = +X
  - Authored at 30 FPS
  - All skinned meshes keep IDENTITY object transforms; geometry is baked into mesh
    data in world (armature rest) space so armature deformation is not double-applied.
"""
import bpy
import bmesh
import math
import os
import zlib
from mathutils import Vector, Matrix, Euler, Quaternion

try:
    import numpy as np
    HAVE_NUMPY = True
except Exception:
    HAVE_NUMPY = False

FPS = 30
CHARACTER_HEIGHT = 1.80

MAT_SKIN = 0
MAT_SUIT = 1
MAT_ARMOR = 2
MAT_CYBER = 3
MAT_EMISSIVE = 4
MAT_HAIR = 5
MAT_EYE = 6
MAT_MOUTH = 7
MAT_NAMES = ["Skin", "Suit", "Armor", "CyberMetal", "Emissive", "Hair", "Eye", "Mouth"]

TEAM_COLORS = {
    "A": (0.10, 0.85, 0.80),
    "B": (1.00, 0.32, 0.18),
}

LM = {
    "pelvis":        Vector((0.0, 0.0, 0.955)),
    "spine_01":      Vector((0.0, 0.005, 1.045)),
    "spine_02":      Vector((0.0, 0.010, 1.175)),
    "spine_03":      Vector((0.0, 0.015, 1.315)),
    "neck_01":       Vector((0.0, 0.020, 1.435)),
    "neck_02":       Vector((0.0, 0.022, 1.500)),
    "head":          Vector((0.0, 0.015, 1.560)),
    "eye":           Vector((0.0, -0.0947, 1.645)),
    "jaw":           Vector((0.0, -0.030, 1.590)),
    "clavicle":      Vector((0.045, 0.020, 1.415)),
    "shoulder":      Vector((0.205, 0.018, 1.385)),
    "elbow":         Vector((0.232, 0.008, 1.075)),
    "wrist":         Vector((0.233, 0.000, 0.775)),
    "hand":          Vector((0.248, -0.030, 0.700)),
    "hip":           Vector((0.105, -0.010, 0.925)),
    "knee":          Vector((0.105, -0.022, 0.478)),
    "ankle":         Vector((0.105, -0.035, 0.105)),
    "toe":           Vector((0.105, -0.175, 0.040)),
    "heel":          Vector((0.105, 0.010, 0.035)),
    "skull_top":     Vector((0.0, 0.010, 1.800)),
    "chin":          Vector((0.0, -0.062, 1.548)),
    "mouth":         Vector((0.0, -0.080, 1.565)),
    "brow":          Vector((0.0465, -0.109, 1.682)),
    "nose":          Vector((0.0, -0.098, 1.615)),
}

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_v(a, b, t):
    return a.lerp(b, t)

def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

def cosine_ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)

def clamp(v, a, b):
    return max(a, min(b, v))

def frame_to_sec(f):
    return (f - 1) / FPS

def sec_to_frame(s):
    return int(round(s * FPS)) + 1

def stable_hash(s):
    """Deterministic string hash (Python's hash() is randomized per process)."""
    return zlib.crc32(str(s).encode("utf-8")) % 1000003

def ring_frame(tangent, prefer_front=True):
    T = tangent.normalized()
    if abs(T.z) > 0.7:
        Uref = Vector((0.0, -1.0, 0.0)) if prefer_front else Vector((0.0, 1.0, 0.0))
    else:
        Uref = Vector((0.0, 0.0, 1.0))
    A = T.cross(Uref)
    if A.length < 1e-6:
        A = Vector((1.0, 0.0, 0.0))
    A.normalize()
    B = T.cross(A)
    B.normalize()
    return A, B

def new_bmesh():
    return bmesh.new()

def bm_tube(bm, rings, segs, mat_index, phase=0.0, cap_start=False, cap_end=False):
    """Loft a tube through `rings` (dicts with c, rx, rz, optional mat, v, island).
    Returns (ring_vert_lists, cap_centers). cap_centers = {"start": BMVert|None,
    "end": BMVert|None}. Face normals point outward; caps face outward at each end.
    For a closed loop, append a duplicate of the first ring at the end of `rings`."""
    ring_vert_lists = []
    for ri, ring in enumerate(rings):
        c = ring["c"]
        rx, rz = ring["rx"], ring["rz"]
        if "T" in ring:
            T = Vector(ring["T"])
        elif len(rings) == 1:
            T = Vector((0.0, 0.0, 1.0))
        elif ri == 0:
            T = rings[1]["c"] - rings[0]["c"]
        elif ri == len(rings) - 1:
            T = rings[-1]["c"] - rings[-2]["c"]
        else:
            T = rings[ri + 1]["c"] - rings[ri - 1]["c"]
        if T.length < 1e-9:
            T = Vector((0.0, 0.0, 1.0))
        A, B = ring_frame(T)
        verts = []
        for j in range(segs):
            theta = 2.0 * math.pi * (j + phase) / segs
            p = c + A * (rx * math.cos(theta)) + B * (rz * math.sin(theta))
            verts.append(bm.verts.new(p))
        ring_vert_lists.append((verts, ring))
    for ri in range(len(ring_vert_lists) - 1):
        cur, _ = ring_vert_lists[ri]
        nxt, nring = ring_vert_lists[ri + 1]
        for j in range(segs):
            j2 = (j + 1) % segs
            try:
                f = bm.faces.new((cur[j], cur[j2], nxt[j2], nxt[j]))
                f.material_index = nring.get("mat", mat_index)
            except ValueError:
                pass
    caps = {"start": None, "end": None}
    if cap_end:
        last, _ = ring_vert_lists[-1]
        center = bm.verts.new(rings[-1]["c"])
        for j in range(segs):
            j2 = (j + 1) % segs
            try:
                f = bm.faces.new((last[j], last[j2], center))
                f.material_index = rings[-1].get("mat", mat_index)
            except ValueError:
                pass
        caps["end"] = center
    if cap_start:
        first, _ = ring_vert_lists[0]
        center = bm.verts.new(rings[0]["c"])
        for j in range(segs):
            j2 = (j + 1) % segs
            try:
                f = bm.faces.new((first[j2], first[j], center))
                f.material_index = rings[0].get("mat", mat_index)
            except ValueError:
                pass
        caps["start"] = center
    return ring_vert_lists, caps

def finish_mesh(name, bm, obj_name=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(obj_name or name, me)
    bpy.context.scene.collection.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True
    return obj

def planar_uv(obj, scale=1.0):
    me = obj.data
    uv = me.uv_layers.active
    if uv is None:
        uv = me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        n = p.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            if ax >= ay and ax >= az:
                u, vc = v.y, v.z
            elif ay >= az:
                u, vc = v.x, v.z
            else:
                u, vc = v.x, v.y
            uv.data[li].uv = ((u * scale) % 1.0, (vc * scale) % 1.0)

def planar_uv_fit(obj):
    """Planar UVs normalized so the object's bounding box maps to the full 0-1 square."""
    me = obj.data
    uv = me.uv_layers.active
    if uv is None:
        uv = me.uv_layers.new(name="UVMap")
    vs = [v.co.copy() for v in me.vertices]
    mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    d = Vector((max(mx.x - mn.x, 1e-6), max(mx.y - mn.y, 1e-6), max(mx.z - mn.z, 1e-6)))
    for p in me.polygons:
        n = p.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            if ax >= ay and ax >= az:
                u, vc = (v.y - mn.y) / d.y, (v.z - mn.z) / d.z
            elif ay >= az:
                u, vc = (v.x - mn.x) / d.x, (v.z - mn.z) / d.z
            else:
                u, vc = (v.x - mn.x) / d.x, (v.y - mn.y) / d.y
            uv.data[li].uv = (clamp(u, 0.0, 1.0), clamp(vc, 0.0, 1.0))

def box_mesh_bm(bm, sx, sy, sz, mat_index):
    """Create a box; only the new elements are touched. Returns (new_verts, new_faces)."""
    before_v = set(bm.verts)
    before_f = set(bm.faces)
    bmesh.ops.create_cube(bm, size=1.0)
    new_v = [v for v in bm.verts if v not in before_v]
    new_f = [f for f in bm.faces if f not in before_f]
    for v in new_v:
        v.co.x *= sx / 2.0
        v.co.y *= sy / 2.0
        v.co.z *= sz / 2.0
    for f in new_f:
        f.material_index = mat_index
    return new_v, new_f

def cylinder_mesh_bm(bm, radius, length, segs, mat_index, axis='Z',
                     mat_caps=None, mat_side=None):
    """Create a capped cylinder along `axis`, centered at the origin; only the new
    elements are touched. Returns (new_verts, new_faces)."""
    before_v = set(bm.verts)
    before_f = set(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                          radius1=radius, radius2=radius, depth=length)
    new_v = [v for v in bm.verts if v not in before_v]
    new_f = [f for f in bm.faces if f not in before_f]
    # classify caps in the local frame (cone axis is +Z at creation)
    for f in new_f:
        if abs(f.normal.z) > 0.9 and mat_caps is not None:
            f.material_index = mat_caps
        else:
            f.material_index = mat_side if mat_side is not None else mat_index
    if axis == 'Y':
        M = Matrix.Rotation(math.pi / 2.0, 4, 'X')
    elif axis == 'X':
        M = Matrix.Rotation(math.pi / 2.0, 4, 'Y')
    else:
        M = None
    if M is not None:
        for v in new_v:
            v.co = M @ v.co
    return new_v, new_f

def sphere_mesh_bm(bm, radius, segs=24, rings=16):
    """Create a UV sphere at the origin; only new elements are touched.
    Returns (new_verts, new_faces)."""
    before_v = set(bm.verts)
    before_f = set(bm.faces)
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    new_v = [v for v in bm.verts if v not in before_v]
    new_f = [f for f in bm.faces if f not in before_f]
    return new_v, new_f

def sphere_cap_bm(bm, radius, half_angle_deg, segs=20, rings=12, mat_index=0):
    """Closed spherical cap: the region of a sphere within half_angle_deg of +Z,
    closed with a fan facing -Z. Geometry stays in local frame (caller transforms).
    Only the cap's own elements are touched. Returns (cap_verts, cap_faces)."""
    before_v = set(bm.verts)
    before_f = set(bm.faces)
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    sv = [v for v in bm.verts if v not in before_v]
    limit = math.cos(math.radians(half_angle_deg))
    remove = [v for v in sv if v.co.z / radius < limit]
    if remove:
        bmesh.ops.delete(bm, geom=remove, context='VERTS')
    kept = set(sv) - set(remove)
    # rim = boundary edges of the kept sphere region only
    rim = [e for e in bm.edges
           if e.is_boundary and e.verts[0] in kept and e.verts[1] in kept]
    rim_verts = []
    for e in rim:
        for v in e.verts:
            if v not in rim_verts:
                rim_verts.append(v)
    cap_verts = list(kept)
    if rim_verts:
        rim_verts.sort(key=lambda v: math.atan2(v.co.y, v.co.x))
        center = bm.verts.new(Vector((0.0, 0.0, 0.0)))
        cap_verts.append(center)
        n = len(rim_verts)
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new((rim_verts[j], rim_verts[i], center))
            except ValueError:
                pass
    cap_faces = [f for f in bm.faces if f not in before_f]
    for f in cap_faces:
        f.material_index = mat_index
    return cap_verts, cap_faces

def ellipse_band_bm(bm, cx, cy, cz, rx, rz, height, radial, path_pts, cross_segs,
                    mat_index):
    """Closed elliptical band (a thin hoop) in the X-Y plane at height cz.
    Cross-section: `radial` thick (outward), `height` tall (along Z)."""
    rings = []
    pts = [Vector((cx + rx * math.cos(2 * math.pi * i / path_pts),
                   cy + rz * math.sin(2 * math.pi * i / path_pts), cz))
           for i in range(path_pts)]
    pts.append(pts[0].copy())  # close the loop
    for p in pts:
        rings.append(dict(c=p, rx=radial, rz=height / 2.0, mat=mat_index))
    rvl, _ = bm_tube(bm, rings, cross_segs, mat_index)
    return rvl

def vgroup(obj, name):
    g = obj.vertex_groups.get(name)
    if g is None:
        g = obj.vertex_groups.new(name=name)
    return g

def assign_weights(obj, vert_weights):
    groups = {}
    for vi, wmap in vert_weights.items():
        for bone, w in wmap.items():
            if bone not in groups:
                groups[bone] = vgroup(obj, bone)
            groups[bone].add([vi], w, 'REPLACE')

def cap_weights(obj, max_influences=8):
    for v in obj.data.vertices:
        entries = []
        for g in obj.vertex_groups:
            try:
                w = g.weight(v.index)
                if w > 1e-6:
                    entries.append((w, g))
            except RuntimeError:
                pass
        if not entries:
            continue
        entries.sort(key=lambda e: -e[0])
        keep = entries[:max_influences]
        s = sum(w for w, _ in keep)
        if s <= 0:
            continue
        for w, g in entries:
            g.remove([v.index])
        for w, g in keep:
            g.add([v.index], w / s, 'REPLACE')

def normalize_weights(obj):
    for v in obj.data.vertices:
        entries = []
        for g in obj.vertex_groups:
            try:
                w = g.weight(v.index)
                if w > 1e-6:
                    entries.append((w, g))
            except RuntimeError:
                pass
        total = sum(w for w, _ in entries)
        if total > 1e-6 and abs(total - 1.0) > 1e-4:
            for w, g in entries:
                g.add([v.index], w / total, 'REPLACE')

def hash_noise(x, y, seed=0):
    def h(n):
        n = (n * 374761393 + seed * 668265263) & 0xFFFFFFFF
        n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 4294967295.0
    xi = math.floor(x); yi = math.floor(y)
    xf = x - xi; yf = y - yi
    a = h(xi + yi * 57); b = h(xi + 1 + yi * 57)
    c = h(xi + (yi + 1) * 57); d = h(xi + 1 + (yi + 1) * 57)
    u = xf * xf * (3 - 2 * xf); v = yf * yf * (3 - 2 * yf)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v

def vnoise(x, y, seed=0):
    """Vectorized value noise. x, y are numpy float arrays; returns a float array."""
    xi = np.floor(x).astype(np.int64)
    yi = np.floor(y).astype(np.int64)
    xf = x - xi
    yf = y - yi
    def h(n):
        n = (n * np.int64(374761393) + np.int64(seed) * np.int64(668265263)) & np.int64(0xFFFFFFFF)
        n = ((n ^ (n >> np.int64(13))) * np.int64(1274126177)) & np.int64(0xFFFFFFFF)
        return ((n ^ (n >> np.int64(16))) & np.int64(0xFFFFFFFF)).astype(np.float64) / 4294967295.0
    a = h(xi + yi * np.int64(57))
    b = h(xi + np.int64(1) + yi * np.int64(57))
    c = h(xi + (yi + np.int64(1)) * np.int64(57))
    d = h(xi + np.int64(1) + (yi + np.int64(1)) * np.int64(57))
    u = xf * xf * (3 - 2 * xf)
    v = yf * yf * (3 - 2 * yf)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v

def write_png(path, size, pixel_fn):
    """pixel_fn(x, y) -> (r,g,b,a) scalars, or numpy mode: pixel_fn(X, Y) -> (R,G,B,A)
    float arrays of shape (size, size)."""
    img = bpy.data.images.new(os.path.basename(path), width=size, height=size,
                              alpha=True, float_buffer=False)
    if HAVE_NUMPY:
        ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
        out = pixel_fn(xs, ys)
        if isinstance(out, tuple) and len(out) == 4 and hasattr(out[0], "shape"):
            r, g, b, a = out
            px = np.empty((size, size, 4), dtype=np.float32)
            px[:, :, 0] = r; px[:, :, 1] = g; px[:, :, 2] = b; px[:, :, 3] = a
            img.pixels.foreach_set(px.ravel())
        else:
            px = [0.0] * (size * size * 4)
            for y in range(size):
                for x in range(size):
                    r, g, b, a = pixel_fn(x, y)
                    i = (y * size + x) * 4
                    px[i] = r; px[i + 1] = g; px[i + 2] = b; px[i + 3] = a
            img.pixels = px
    else:
        px = [0.0] * (size * size * 4)
        for y in range(size):
            for x in range(size):
                r, g, b, a = pixel_fn(x, y)
                i = (y * size + x) * 4
                px[i] = r; px[i + 1] = g; px[i + 2] = b; px[i + 3] = a
        img.pixels = px
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return path

def make_material(name, base_color, roughness, metallic=0.0, emissive_color=None,
                  emissive_strength=0.0, tex_prefix=None, tex_dir=None,
                  team_mask=None, team_color=None):
    """Create a material. If team_mask (filename) and team_color given, the base color
    is mixed with the team color using the mask's R channel (preview of team A)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emissive_color is not None:
        bsdf.inputs["Emission Color"].default_value = (*emissive_color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emissive_strength
    if tex_prefix and tex_dir:
        bc_tex = None
        for suffix, inp in (("_BC", "Base Color"), ("_R", "Roughness"), ("_N", "Normal")):
            path = os.path.join(tex_dir, tex_prefix + suffix + ".png")
            if os.path.exists(path):
                tex = nt.nodes.new("ShaderNodeTexImage")
                tex.image = bpy.data.images.load(path)
                tex.interpolation = 'Smart' if suffix == "_BC" else 'Closest'
                if suffix == "_N":
                    nmap = nt.nodes.new("ShaderNodeNormalMap")
                    nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
                    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
                elif suffix == "_BC":
                    bc_tex = tex
                else:
                    nt.links.new(tex.outputs["Color"], bsdf.inputs[inp])
        if team_mask and team_color and bc_tex is not None:
            tpath = os.path.join(tex_dir, team_mask)
            if os.path.exists(tpath):
                ttex = nt.nodes.new("ShaderNodeTexImage")
                ttex.image = bpy.data.images.load(tpath)
                ttex.interpolation = 'Closest'
                sep = nt.nodes.new("ShaderNodeSeparateXYZ")
                mix = nt.nodes.new("ShaderNodeMixRGB")
                mix.blend_type = 'MIX'
                mix.inputs["Color2"].default_value = (*team_color, 1.0)
                nt.links.new(ttex.outputs["Color"], sep.inputs["Vector"])
                nt.links.new(sep.outputs["X"], mix.inputs["Factor"])
                nt.links.new(bc_tex.outputs["Color"], mix.inputs["Color1"])
                nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
        if bc_tex is not None and not bsdf.inputs["Base Color"].links:
            nt.links.new(bc_tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = FPS
    sc.frame_start = 1
    sc.frame_end = 250
    sc.render.engine = 'BLENDER_EEVEE'
    return sc

# ===================================================================== rig math
# Bone-frame / pose helpers shared by the rig generator, the animation generator
# and the interactive control rig.  All matrices are armature-space (Blender
# scene space at rest), character faces -Y, up +Z, right +X.

FWD = Vector((0.0, -1.0, 0.0))
UP = Vector((0.0, 0.0, 1.0))
RIGHT = Vector((1.0, 0.0, 0.0))

ARM_BONES = ("upper_arm_L", "upper_arm_R", "forearm_L", "forearm_R", "hand_L", "hand_R",
             "upper_arm_twist_L", "upper_arm_twist_R", "forearm_twist_L", "forearm_twist_R")
LEG_BONES = ("thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R", "toe_L", "toe_R",
             "thigh_twist_L", "thigh_twist_R", "shin_twist_L", "shin_twist_R")
FINGER_BONES = tuple(n for n in () )  # filled by name pattern below
IDENTITY_BONES = ("eye_L", "eye_R", "lid_upper_L", "lid_lower_L", "lid_upper_R", "lid_lower_R")

def is_finger_bone(name):
    return name.startswith("f_") and ("_L" in name or "_R" in name)

def x_hint_for(name, head, tail):
    """Choose the bone local X axis (the primary bend/pose axis) for a bone.
    Convention (documented in docs/rig_usage.md):
      - fingers:  +X rotation curls the finger downward (closing the hand)
      - arms:     +X rotation flexes the elbow/forearm forward (-Y)
      - legs:     +X rotation flexes the knee/shin backward (+Y)
      - foot/toe: +X rotation plants the toe (heel rises)
      - clavicle: +X rotation raises the shoulder
      - jaw:      +X rotation opens the jaw
      - eyes/lids: identity frame; +X = pitch (down), +Z = yaw (right)
      - spine/neck/head/root/props: X = world +X
    Local Y always points head->tail; local Z = X x Y."""
    if name in IDENTITY_BONES:
        return None
    d = (Vector(tail) - Vector(head))
    dn = d.normalized() if d.length > 1e-9 else UP
    if is_finger_bone(name):
        h = UP.cross(dn) if abs(dn.z) < 0.9 else FWD.cross(dn)
        return h if h.length > 1e-4 else RIGHT
    if name in ARM_BONES:
        h = dn.cross(FWD) if abs(dn.y) < 0.9 else dn.cross(UP)
        return h if h.length > 1e-4 else RIGHT
    if name in LEG_BONES:
        h = FWD.cross(dn) if abs(dn.y) < 0.9 else UP.cross(dn)
        return h if h.length > 1e-4 else RIGHT
    if name == "jaw":
        return RIGHT
    if name.startswith("clavicle"):
        h = dn.cross(UP) if abs(dn.z) < 0.9 else FWD
        return h if h.length > 1e-4 else RIGHT
    return RIGHT

def bone_frame(head, tail, x_hint=None):
    """Armature-space rest matrix for a bone. The Y column is exactly tail-head
    so the bone keeps its length when assigned to an EditBone."""
    head = Vector(head)
    y_raw = Vector(tail) - head
    L = y_raw.length
    if L < 1e-7:
        raise ValueError("zero-length bone %s" % (head,))
    y = y_raw / L
    if x_hint is None:
        x = RIGHT if abs(y.x) < 0.95 else UP
    else:
        x = Vector(x_hint)
    x = x - y * x.dot(y)
    if x.length < 1e-4:
        x = UP if abs(y.z) < 0.9 else RIGHT
        x = x - y * x.dot(y)
    x.normalize()
    z = x.cross(y)
    R = Matrix((x, y_raw, z)).transposed().to_4x4()
    return Matrix.Translation(head) @ R

def set_eb_frame(eb, M):
    """Set an EditBone's complete rest frame (head, tail, direction, roll) from
    the armature-space matrix M produced by bone_frame() (Y column = tail-head).

    Blender 5.1 notes (verified empirically on 5.1.1): EditBone.matrix no
    longer carries the bone length -- its setter only applies rotation to bones
    that already have length and merely moves the head of zero-length bones --
    and EditBone.align_roll was removed.  The frame is therefore set through the
    primitive head/tail/roll properties.  The roll is recovered from the delta
    between Blender's default (roll=0) frame and the desired frame; the delta is
    always a pure rotation about the bone axis, and eb.roll takes the
    right-handed positive sense about the bone's local +Y.
    """
    head = M.to_translation()
    y_raw = M.to_3x3().col[1]
    eb.head = head
    eb.tail = head + y_raw
    R0 = eb.matrix.to_3x3()
    Rdes = M.to_3x3().copy()
    for R in (R0, Rdes):
        for i in range(3):
            c = R.col[i]
            if c.length > 1e-9:
                R.col[i] = c / c.length
    q = (R0.inverted() @ Rdes).to_quaternion()
    eb.roll = 2.0 * math.atan2(q.y, q.w)

def rest_local(bone):
    """Rest matrix of `bone` relative to its parent (armature space -> parent space)."""
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted() @ bone.matrix_local

def set_pose_matrix(pb, M):
    """Drive pose bone `pb` so its armature-space matrix becomes M, by writing
    location/rotation_euler/scale (basis). No shear is ever produced by callers."""
    bone = pb.bone
    if bone.parent is None:
        basis = bone.matrix_local.inverted() @ M
    else:
        basis = rest_local(bone).inverted() @ pb.parent.matrix.inverted() @ M
    loc = basis.to_translation()
    R = basis.to_3x3()
    sc = Vector((R.col[0].length, R.col[1].length, R.col[2].length))
    for i in range(3):
        if sc[i] > 1e-9:
            R.col[i] = R.col[i] / sc[i]
    pb.rotation_mode = 'XYZ'
    pb.location = loc
    pb.rotation_euler = R.to_euler('XYZ')
    pb.scale = sc

def solve_2bone_ik(A, E, W, target, pole):
    """Analytic 2-bone IK. A: upper-bone head, E: joint (upper tail = forearm head),
    W: chain end rest point. target/pole in armature space. Returns (E_new, T_new)
    (joint position and clamped effector position)."""
    A = Vector(A); E = Vector(E); W = Vector(W)
    L1 = (E - A).length
    L2 = (W - E).length
    T = Vector(target)
    d = (T - A).length
    d = min(max(d, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    u = (T - A)
    u = u.normalized() if u.length > 1e-9 else (W - A).normalized()
    cos_a = (L1 * L1 + d * d - L2 * L2) / (2.0 * L1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    pv = Vector(pole) - A
    v = pv - u * pv.dot(u)
    if v.length < 1e-6:
        v = UP - u * UP.dot(u)
        if v.length < 1e-6:
            v = RIGHT - u * RIGHT.dot(u)
    v.normalize()
    # law of cosines: the joint sits at distance L1 from A, at angle a from the
    # A->target axis, on the pole side.  (u*(L1*cos_a) + v*(L1*sin_a) has length
    # L1 and puts the effector exactly L2 from the joint.)
    E_new = A + (u * (L1 * cos_a) + v * (L1 * sin_a))
    T_new = A + u * d
    return E_new, T_new

def dir_pose_matrix(rest_M, new_dir, new_head=None):
    """Pose matrix that keeps the bone's rest frame but points its Y axis along
    new_dir (minimal rotation, roll preserved as well as possible)."""
    rest_dir = rest_M.col[1].normalized()
    nd = Vector(new_dir)
    if nd.length < 1e-9:
        return rest_M.copy()
    nd = nd.normalized()
    q = rest_dir.rotation_difference(nd)
    R = (q.to_matrix().to_4x4() @ rest_M.to_3x3().to_4x4())
    head = Vector(new_head) if new_head is not None else rest_M.to_translation()
    M = Matrix.Translation(head) @ R
    return M

def look_rotations(from_pos, to_pos):
    """(yaw, pitch) radians to look from from_pos toward to_pos.
    yaw > 0 turns toward +X (right), pitch > 0 looks up (+Z)."""
    d = Vector(to_pos) - Vector(from_pos)
    if d.length < 1e-9:
        return 0.0, 0.0
    d.normalize()
    yaw = math.atan2(d.x, -d.y)
    pitch = math.asin(max(-1.0, min(1.0, d.z)))
    return yaw, pitch

"""MorphRig UV layout: final material slots, unwrapping with generator seams, per-texture-set
packing (Blender side, runs at the end of build_character).

Texture sets (one material slot each, 7 in total):
  skin  - head + left hand                      4096
  suit  - body suit + cloth gear (vest, straps, collar, belt, bracer)   4096
  armor - hard plates, boots, belt hardware, hair band                   2048
  cyber - cybernetic forearm/hand/blade, ear comm, power cell, beacon   2048
  hair  - hair top + tail                                                 1024
  eye   - both eyeballs (shared layout)                                   1024
  mouth - teeth, gums, tongue                                             1024
"""
import math
import numpy as np
import bpy
import bmesh

TEXSETS = {"skin": 4096, "suit": 4096, "armor": 2048, "cyber": 2048, "hair": 1024, "eye": 1024, "mouth": 1024}
MATERIAL_NAME = {k: "M_" + k.capitalize() for k in TEXSETS}

OBJECT_SET = {"MR_Suit": "suit", "MR_Head": "skin", "MR_HandL": "skin", "MR_Boot_L": "armor", "MR_Boot_R": "armor",
              "MR_CyberArm": "cyber", "MR_PropCell": "cyber", "MR_PropBeacon": "cyber", "MR_Eye_L": "eye",
              "MR_Eye_R": "eye", "MR_Mouth": "mouth"}
SMART = {"MR_CyberArm", "MR_PropCell", "MR_PropBeacon", "MR_Mouth"}


def final_materials():
    """Create/return the 7 material datablocks (node trees are filled in by build_textures)."""
    from mr_blender import preview_material
    cols = {"skin": (0.55, 0.38, 0.30), "suit": (0.07, 0.075, 0.09), "armor": (0.62, 0.62, 0.60),
            "cyber": (0.20, 0.21, 0.23), "hair": (0.05, 0.035, 0.03), "eye": (0.8, 0.8, 0.78),
            "mouth": (0.85, 0.80, 0.74)}
    out = {}
    for k, nm in MATERIAL_NAME.items():
        mat = bpy.data.materials.get(nm)
        if mat is None:
            mat = preview_material(nm, cols[k], rough=0.5)
            mat.name = nm
        out[k] = mat
    return out


def assign_materials(objs, per_object_sets):
    """objs: name -> object; per_object_sets: name -> list of set names (slot order)."""
    mats = final_materials()
    for name, ob in objs.items():
        sets = per_object_sets.get(name) or [OBJECT_SET[name]]
        me = ob.data
        old_idx = np.zeros(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", old_idx)
        me.materials.clear()
        for s in sets:
            me.materials.append(mats[s])
        me.polygons.foreach_set("material_index", old_idx)
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)


def _set_active(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)


def _unwrap(ob, smart=False):
    _set_active(ob)
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    if smart:
        bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.004, area_weight=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
    else:
        bpy.ops.uv.unwrap(method='CONFORMAL', margin=0.003)
    bpy.ops.object.mode_set(mode='OBJECT')


def _eye_uv(ob, centre, radius):
    """Planar front projection: pupil at (0.5, 0.5), iris/sclera laid out radially."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers[0].data
    co = np.array([v.co for v in me.vertices])
    rel = (co - np.asarray(centre)) / (radius * 1.02)
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            x, y, z = rel[vi]
            # front hemisphere -> disk; back hemisphere squeezed to the outer ring (sclera)
            r = math.sqrt(x * x + z * z)
            ang = math.atan2(z, x)
            theta = math.acos(max(-1.0, min(1.0, -y)))          # 0 at the pupil
            rr = theta / math.pi * 0.98
            uv[li].uv = (0.5 + 0.5 * rr * math.cos(ang), 0.5 + 0.5 * rr * math.sin(ang))


def _pack(objs_faces, margin):
    """Pack the UV islands of the given (object, face mask) pairs together into 0-1."""
    obs = [o for o, _ in objs_faces]
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]
    sc = bpy.context.scene
    sc.tool_settings.mesh_select_mode = (False, False, True)
    sc.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    for o, mask in objs_faces:
        bm = bmesh.from_edit_mesh(o.data)
        bm.select_mode = {'FACE'}
        bm.faces.ensure_lookup_table()
        for f in bm.faces:
            f.select_set(bool(mask[f.index]))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(o.data)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, margin_method='SCALED', margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def layout(objs):
    """Unwrap every object and pack each texture set.  objs: name -> object."""
    from mr_params import H, EYE_R
    for name, ob in objs.items():
        if name.startswith("MR_Eye_"):
            _eye_uv(ob, H["eye_" + name[-1].lower()], EYE_R)
        else:
            _unwrap(ob, smart=name in SMART)
    # group faces by texture set via their material
    groups = {}
    for name, ob in objs.items():
        me = ob.data
        idx = np.zeros(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", idx)
        for slot, mat in enumerate(me.materials):
            s = next(k for k, v in MATERIAL_NAME.items() if v == mat.name)
            mask = idx == slot
            if mask.any():
                groups.setdefault(s, []).append((ob, mask))
    for s, items in groups.items():
        if s == "eye":
            continue
        _pack(items, margin=0.004 if TEXSETS[s] >= 2048 else 0.008)
    return groups


# ----------------------------------------------------------------- generator-side seams (numpy Mesh)
def head_seams(m):
    """Back midline (crown to neck opening) and the lip / mouth-bag boundary."""
    x, y = m.v[:, 0], m.v[:, 1]
    mid = (np.abs(x) < 1e-4) & (y > 0.01)
    bag = m.groups.get("mouth_bag")
    edge_faces = {}
    for fi, f in enumerate(m.f):
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (min(a, b), max(a, b))
            edge_faces.setdefault(key, []).append(fi)
            if mid[a] and mid[b]:
                m.seams.add(key)
    if bag is not None:
        in_bag = np.array([bool(bag[list(f)].all()) for f in m.f])
        for key, fs in edge_faces.items():
            if len(fs) == 2 and in_bag[fs[0]] != in_bag[fs[1]]:
                m.seams.add(key)


def ring_seams(m, rings, back=(0, 1, 0)):
    """Seam along the ring index that faces `back` on the first ring, plus the first ring loop."""
    r0 = np.asarray(rings[0])
    c = m.v[r0].mean(0)
    k = int(np.argmax((m.v[r0] - c) @ np.asarray(back, float)))
    m.mark_seam_path([int(np.asarray(r)[k]) for r in rings])
    m.mark_seam_loop([int(i) for i in r0])

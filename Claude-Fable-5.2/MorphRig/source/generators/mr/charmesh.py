"""Final character mesh: all generated parts joined into one skinned mesh with UVs, region ids and face shape keys."""
import bmesh
import bpy
import numpy as np
from . import assemble, meshkit, faceshapes, uvtools

MATERIAL_ORDER = ['M_Skin', 'M_EyesMouth', 'M_Hair', 'M_Suit', 'M_Armor', 'M_Cyber']
JOIN_ORDER = ['Head', 'Body', 'Lashes', 'Eyes', 'Teeth', 'Tongue', 'Hair', 'Outfit', 'Cyber']


def build_character(name='Operative', shapes=True, uv=True, collection=None):
    """Returns (object, info). info: parts (MeshData), build info, region_names, part vertex ranges, uv stats."""
    parts, info = assemble.build_parts()
    tags = []
    for k in JOIN_ORDER:
        for t in parts[k].ftag:
            if t not in tags:
                tags.append(t)
    for m in MATERIAL_ORDER:                      # fixed slot order regardless of the part order
        if m not in bpy.data.materials:
            bpy.data.materials.new(m)
    obs = {}
    ranges = {}
    off = 0
    for k in JOIN_ORDER:
        md = parts[k]
        ob = meshkit.to_object(md, collection=collection)
        me = ob.data
        local = list(me['region_names'])
        reg = np.empty(len(me.polygons), dtype=np.int32)
        me.attributes['region'].data.foreach_get('value', reg)
        remap = np.array([tags.index(t) for t in local], dtype=np.int32)
        me.attributes['region'].data.foreach_set('value', remap[reg])
        me['region_names'] = tags
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        ranges[k] = (off, off + len(me.vertices))
        off += len(me.vertices)
        obs[k] = ob
    if uv:
        for k in JOIN_ORDER:
            uvtools.unwrap_part(obs[k], k)
    # join: Head is the active object, its vertices stay first
    carrier = obs['Head']
    me = carrier.data
    have = [s.name for s in carrier.material_slots]
    bpy.ops.object.select_all(action='DESELECT')
    for k in JOIN_ORDER:
        obs[k].select_set(True)
    bpy.context.view_layer.objects.active = carrier
    bpy.ops.object.join()
    ob = carrier
    ob.name = name
    ob.data.name = name
    _order_materials(ob)
    ob.data['region_names'] = tags
    import time
    t0 = time.time()
    stats = uvtools.pack_by_material(ob, tags) if uv else {}
    info['pack_seconds'] = round(time.time() - t0, 1)
    if shapes:
        # shape keys are added last: edit-mode operators (unwrap, pack) and the join never see them.
        # Head is the active object of the join, so its vertices are the first block of the joined mesh.
        hs = faceshapes.build_face_shapes(parts['Head'], info['head'])
        n_head = len(parts['Head'].v)
        n_all = len(ob.data.vertices)
        co = np.empty(n_all * 3)
        ob.data.vertices.foreach_get('co', co)
        assert np.allclose(co.reshape(-1, 3)[:n_head], np.array(parts['Head'].v), atol=1e-5), 'head vertices are not the first block'
        full = {}
        for k, d in hs.items():
            a = np.zeros((n_all, 3))
            a[:n_head] = np.asarray(d).reshape(-1, 3)
            full[k] = a
        faceshapes.apply_shape_keys(ob, full)
        ob.active_shape_key_index = 0
        ob.show_only_shape_key = False
    info.update(parts=parts, region_names=tags, ranges=ranges, uv_stats=stats)
    return ob, info


def _order_materials(ob):
    """Material slots in MATERIAL_ORDER (stable section order for Unreal)."""
    me = ob.data
    cur = [s.material.name for s in ob.material_slots]
    order = [m for m in MATERIAL_ORDER if m in cur] + [m for m in cur if m not in MATERIAL_ORDER]
    idx = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get('material_index', idx)
    remap = np.array([order.index(n) for n in cur], dtype=np.int32)
    new = remap[idx]
    me.materials.clear()
    for n in order:
        me.materials.append(bpy.data.materials[n])
    me.polygons.foreach_set('material_index', new)
    me.update()

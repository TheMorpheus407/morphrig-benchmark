"""LOD1 / LOD2 of the Operative mesh.

The head skin (the only part that carries facial shape keys) keeps its exact topology and vertex order in every LOD, so
all 32 morph targets transfer 1:1. Everything else is reduced with a collapse decimation that keeps UVs, materials and
skin weights; weights are limited to 8 influences afterwards.
"""
import bpy
import numpy as np

# decimation ratio of the non-head geometry per LOD and how strongly small / important parts are protected
LODS = {1: dict(ratio=0.43, protect=0.75), 2: dict(ratio=0.19, protect=0.35)}
PROTECT_REGIONS = ('eye_l', 'eye_r', 'teeth_upper', 'teeth_lower', 'lash', 'hand', 'thumb', 'finger_index', 'finger_middle', 'finger_ring',
                   'finger_pinky', 'emitter_lens', 'ear_unit', 'ear_lens')


def _activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def _dup(ob, name):
    d = ob.copy()
    d.data = ob.data.copy()
    d.name = name
    d.data.name = name
    for c in ob.users_collection:
        c.objects.link(d)
    d.animation_data_clear()
    if d.data.shape_keys:
        d.data.shape_keys.animation_data_clear()
    return d


def _delete_verts(ob, mask):
    """Delete the vertices where mask is True (shape keys of the remaining vertices are kept)."""
    me = ob.data
    _activate(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    me.vertices.foreach_set('select', mask)
    me.update()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')
    bpy.ops.object.mode_set(mode='OBJECT')


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def max_influences(ob):
    return max((sum(1 for g in v.groups if g.weight > 1e-6) for v in ob.data.vertices), default=0)


def make_lod(src, level, n_head, name=None):
    """Create LOD <level> from the LOD0 object. n_head = number of head-skin vertices (first block of the mesh)."""
    cfg = LODS[level]
    name = name or 'Operative_LOD%d' % level
    nv = len(src.data.vertices)
    head_mask = np.zeros(nv, dtype=bool)
    head_mask[:n_head] = True
    # ---- head: identical copy with shape keys
    head = _dup(src, name)
    _delete_verts(head, ~head_mask)
    assert len(head.data.vertices) == n_head
    # ---- rest: decimated
    rest = _dup(src, name + '_rest')
    _activate(rest)
    if rest.data.shape_keys:
        rest.shape_key_clear()
    _delete_verts(rest, head_mask)
    me = rest.data
    names = list(me['region_names'])
    reg = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes['region'].data.foreach_get('value', reg)
    prot_ids = [names.index(n) for n in PROTECT_REGIONS if n in names]
    w = np.ones(len(me.vertices))
    for p in me.polygons:
        if reg[p.index] in prot_ids:
            for vi in p.vertices:
                w[vi] = 1.0 - cfg['protect']
    vg = rest.vertex_groups.new(name='_lod_weight')
    for i, val in enumerate(w):
        vg.add([i], float(val), 'REPLACE')
    mod = rest.modifiers.new('Decimate', 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = cfg['ratio']
    mod.use_collapse_triangulate = True
    mod.vertex_group = '_lod_weight'
    mod.vertex_group_factor = 3.0
    _activate(rest)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    rest.vertex_groups.remove(rest.vertex_groups['_lod_weight'])
    # the collapse can leave zero-area faces and stray vertices behind
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(rest.data)
    bmesh.ops.dissolve_degenerate(bm, dist=1.0e-6, edges=bm.edges[:])
    stray = [v for v in bm.verts if not v.link_faces]
    if stray:
        bmesh.ops.delete(bm, geom=stray, context='VERTS')
    bm.to_mesh(rest.data)
    bm.free()
    rest.data.update()
    # ---- join (head active: its vertices and keys stay first)
    bpy.ops.object.select_all(action='DESELECT')
    head.select_set(True)
    rest.select_set(True)
    bpy.context.view_layer.objects.active = head
    bpy.ops.object.join()
    lod = head
    lod.name = name
    lod.data.name = name
    if lod.data.shape_keys:
        for kb in lod.data.shape_keys.key_blocks[1:]:
            kb.value = 0.0
        lod.active_shape_key_index = 0
    _activate(lod)
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=8)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    return lod


def integrity(ob, area_eps=1.0e-12):
    """(vertices without a face, faces with (near) zero area, edges shared by more than two faces)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    loose = sum(1 for v in bm.verts if not v.link_faces)
    degen = sum(1 for f in bm.faces if f.calc_area() < area_eps)
    multi = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.free()
    return loose, degen, multi


def report(ob):
    me = ob.data
    loose, degen, multi = integrity(ob)
    return dict(object=ob.name, triangles=tri_count(ob), vertices=len(me.vertices), material_slots=len(ob.material_slots),
                max_bone_influences=max_influences(ob), morph_targets=(len(me.shape_keys.key_blocks) - 1) if me.shape_keys else 0,
                vertex_groups=len(ob.vertex_groups), loose_vertices=loose, zero_area_faces=degen, non_manifold_edges_over_2_faces=multi)

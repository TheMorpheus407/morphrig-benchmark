"""UV unwrapping (per part) and packing (per material) for the Operative mesh."""
import math
import bpy
import numpy as np

# parts with authored seams are unwrapped along them, hard-surface / small parts are projected by angle
PART_METHOD = {'Body': 'seams', 'Head': 'seams', 'Lashes': 'smart', 'Eyes': 'smart', 'Teeth': 'smart', 'Tongue': 'smart',
               'Hair': 'smart', 'Outfit': 'smart', 'Cyber': 'smart'}
SMART_ANGLE = {'Hair': 72.0, 'Outfit': 62.0, 'Cyber': 62.0, 'Eyes': 80.0}

HAND_REGIONS = ('hand', 'thumb', 'finger_index', 'finger_middle', 'finger_ring', 'finger_pinky', 'glove', 'glove_hem')

# texel density priority per region (1 = average); the face is what the close-up camera sees
PRIORITY = {'face': 2.1, 'lips': 2.1, 'lipskin': 2.1, 'eyelid_l': 2.1, 'eyelid_r': 2.1, 'scalp': 1.2, 'neck': 1.2,
            'eye_l': 2.6, 'eye_r': 2.6, 'teeth_upper': 1.3, 'teeth_lower': 1.3, 'tongue': 1.0, 'mouthbag': 0.5,
            'chest_plate': 1.25, 'back_plate': 1.25, 'pauldron_r': 1.25, 'hand': 1.2, 'lash': 1.6}


def _activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def unwrap_part(ob, part):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    _activate(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    if PART_METHOD.get(part, 'smart') == 'seams':
        if part == 'Head':
            bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', fill_holes=True, correct_aspect=True, margin_method='SCALED', margin=0.002,
                              iterations=200)
        else:
            bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin_method='SCALED', margin=0.002)
    else:
        bpy.ops.uv.smart_project(angle_limit=math.radians(SMART_ANGLE.get(part, 66.0)), island_margin=0.0, area_weight=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    if part == 'Body':
        # fingers are closed tubes: an angle based unwrap squeezes them, project the hand by face direction instead
        names = list(me['region_names'])
        hand_ids = [i for i, n in enumerate(names) if n in HAND_REGIONS]
        reg = np.empty(len(me.polygons), dtype=np.int32)
        me.attributes['region'].data.foreach_get('value', reg)
        sel = np.isin(reg, hand_ids)
        if sel.any():
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(type='FACE')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            me.polygons.foreach_set('select', sel)
            me.update()
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.uv.smart_project(angle_limit=math.radians(70.0), island_margin=0.0, area_weight=0.0, correct_aspect=True,
                                     scale_to_bounds=False)
            bpy.ops.object.mode_set(mode='OBJECT')


def _select_material(ob, mi):
    """Edit mode with exactly the faces of one material slot selected (UV sync selection)."""
    _activate(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    ob.active_material_index = mi
    bpy.ops.object.material_slot_select()


def _islands(me, poly_idx):
    """UV islands (lists of polygon indices) among the given polygons."""
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)
    key = {}
    parent = {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for pi in poly_idx:
        parent[pi] = pi
    for pi in poly_idx:
        p = me.polygons[pi]
        for li in p.loop_indices:
            k = (me.loops[li].vertex_index, round(float(uv[li, 0]), 5), round(float(uv[li, 1]), 5))
            o = key.get(k)
            if o is None:
                key[k] = pi
            else:
                ra, rb = find(o), find(pi)
                if ra != rb:
                    parent[ra] = rb
    out = {}
    for pi in poly_idx:
        out.setdefault(find(pi), []).append(pi)
    return list(out.values()), uv


def pack_by_material(ob, region_names, margin=0.0035):
    """Average the texel density, enlarge priority regions, then pack every material's islands into 0..1."""
    me = ob.data
    sc = bpy.context.scene
    sc.tool_settings.use_uv_select_sync = True
    reg = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes['region'].data.foreach_get('value', reg)
    mat = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get('material_index', mat)
    stats = {}
    for mi, slot in enumerate(ob.material_slots):
        sel = mat == mi
        if not sel.any():
            continue
        _select_material(ob, mi)
        bpy.ops.uv.average_islands_scale()
        bpy.ops.object.mode_set(mode='OBJECT')
        # priority scaling per island (about its centre)
        islands, uv = _islands(me, np.nonzero(sel)[0])
        for isl in islands:
            fac = max(PRIORITY.get(region_names[reg[pi]], 1.0) for pi in isl)
            if abs(fac - 1.0) < 1e-6:
                continue
            li = np.array([l for pi in isl for l in me.polygons[pi].loop_indices])
            c = uv[li].mean(axis=0)
            uv[li] = c + (uv[li] - c) * fac
        me.uv_layers.active.data.foreach_set('uv', uv.reshape(-1))
        _select_material(ob, mi)
        bpy.ops.uv.pack_islands(rotate=True, rotate_method='ANY', scale=True, merge_overlap=False, margin_method='FRACTION',
                                margin=margin, shape_method='CONCAVE')
        bpy.ops.object.mode_set(mode='OBJECT')
        stats[slot.name] = dict(islands=len(islands), faces=int(sel.sum()))
    return stats

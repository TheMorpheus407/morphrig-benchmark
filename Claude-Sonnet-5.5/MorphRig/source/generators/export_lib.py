"""Export helpers: centimetre-baked export scene (single 'root', scale 1 in Unreal), LOD mesh assembly, per-clip FBX.

The Blender source stays in metres. Export builds temporary objects: an armature named 'Armature' (Unreal drops that node,
leaving 'root' as the single root bone) whose bones and keys are scaled x100, joined meshes scaled x100, and a one-triangle
skinned 'morph proxy' that carries the shape-key animation so bone and morph curves land in one Unreal AnimSequence."""
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix
import skeleton_def as S

SC = 100.0


def _unlink_all(name_prefix):
    for o in list(bpy.data.objects):
        if o.name.startswith(name_prefix):
            bpy.data.objects.remove(o)


def cm_armature(src, name='Armature'):
    for o in list(bpy.data.objects):
        if o.name == name:
            bpy.data.objects.remove(o)
    data = src.data.copy()
    data.name = 'Armature'
    ob = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = list(data.edit_bones)
    conn = {eb.name: eb.use_connect for eb in ebs}
    for eb in ebs:                       # connected bones snap to their parent's tail: detach before scaling
        eb.use_connect = False
    for eb in ebs:
        eb.head = eb.head * SC
        eb.tail = eb.tail * SC
    for eb in ebs:
        eb.use_connect = conn[eb.name]
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


ORGANIC = {'Operative_Head', 'Operative_Body', 'Operative_Hand_R', 'Operative_Eyes', 'Operative_Mouth', 'Operative_Hair', 'Operative_Braid'}


def mark_sharp(me, angle_deg=38.0, organic_faces=None, organic_angle_deg=88.0):
    """Hard edges above `angle_deg` on hard-surface parts. Edges between two organic faces (skin, face, hair, teeth, eyes) only split
    above `organic_angle_deg`, so the nose ridge, lips and eyelid rims keep smooth shading instead of a knife-edge seam."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    lim = math.radians(angle_deg)
    lim_o = math.radians(organic_angle_deg)
    for e in bm.edges:
        e.smooth = True
        if len(e.link_faces) == 2:
            org = organic_faces is not None and organic_faces[e.link_faces[0].index] and organic_faces[e.link_faces[1].index]
            if e.calc_face_angle(0.0) > (lim_o if org else lim):
                e.smooth = False
    bm.to_mesh(me)
    bm.free()


def assemble_mesh(objs, name, armature_cm, shape_key_from=None, hard_angle=38.0, uv_name='UVMap'):
    """Join `objs` (source objects in metres) into one object in centimetres, keeping vertex groups, materials (by name),
    UVs and shape-key deltas (from `shape_key_from`, an object whose vertices are the first block of the join)."""
    verts, faces, uvs, mat_names_face, groups, attrs = [], [], [], [], [], []
    organic_flags = []
    off = 0
    per_obj = []
    for ob in objs:
        me = ob.data
        n = len(me.vertices)
        v = np.empty(n * 3)
        me.vertices.foreach_get('co', v)
        v = v.reshape(-1, 3) * SC
        verts.append(v)
        loops_v = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get('vertex_index', loops_v)
        starts = np.empty(len(me.polygons), dtype=np.int64)
        totals = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get('loop_start', starts)
        me.polygons.foreach_get('loop_total', totals)
        mi = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get('material_index', mi)
        for s, t, m in zip(starts, totals, mi):
            faces.append(tuple(int(x) + off for x in loops_v[s:s + t]))
            mat_names_face.append(me.materials[m].name if m < len(me.materials) else 'MI_armor')
            organic_flags.append(ob.name in ORGANIC)
        if me.uv_layers:
            uvl = me.uv_layers.active if me.uv_layers.active else me.uv_layers[0]
            u = np.empty(len(me.loops) * 2)
            uvl.data.foreach_get('uv', u)
            uvs.append(u.reshape(-1, 2))
            uv_starts = starts
        else:
            uvs.append(np.zeros((len(me.loops), 2)))
        # vertex groups
        gw = {}
        names = [g.name for g in ob.vertex_groups]
        for vi, vert in enumerate(me.vertices):
            for g in vert.groups:
                gw.setdefault(names[g.group], []).append((vi + off, g.weight))
        groups.append(gw)
        per_obj.append((off, n))
        off += n
    V = np.concatenate(verts)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in V], [], faces)
    me.update()
    # UVs per loop (polygon loop order matches faces order)
    uv_all = np.concatenate(uvs)
    lay = me.uv_layers.new(name=uv_name)
    if len(uv_all) == len(me.loops):
        lay.data.foreach_set('uv', uv_all.ravel())
    # materials
    slot_names = []
    for n in mat_names_face:
        if n not in slot_names:
            slot_names.append(n)
    for n in slot_names:
        me.materials.append(bpy.data.materials[n])
    idx = {n: i for i, n in enumerate(slot_names)}
    me.polygons.foreach_set('material_index', np.array([idx[n] for n in mat_names_face], dtype=np.int32))
    for p in me.polygons:
        p.use_smooth = True
    mark_sharp(me, hard_angle, organic_faces=organic_flags)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    # vertex groups
    allg = {}
    for gw in groups:
        for k, lst in gw.items():
            allg.setdefault(k, []).extend(lst)
    for k, lst in allg.items():
        vg = ob.vertex_groups.new(name=k)
        for vi, w in lst:
            vg.add([vi], w, 'REPLACE')
    md = ob.modifiers.new('Armature', 'ARMATURE')
    md.object = armature_cm
    ob.parent = armature_cm
    # shape keys from the head object (first `n_head` vertices block located at its offset)
    if shape_key_from is not None and shape_key_from.data.shape_keys:
        head_idx = objs.index(shape_key_from)
        hoff, hn = per_obj[head_idx]
        ob.shape_key_add(name='Basis')
        base = np.empty(hn * 3)
        shape_key_from.data.shape_keys.reference_key.data.foreach_get('co', base)
        base = base.reshape(-1, 3)
        for kb in shape_key_from.data.shape_keys.key_blocks[1:]:
            co = np.empty(hn * 3)
            kb.data.foreach_get('co', co)
            co = co.reshape(-1, 3)
            new = V.copy()
            new[hoff:hoff + hn] = V[hoff:hoff + hn] + (co - base) * SC
            sk = ob.shape_key_add(name=kb.name)
            sk.data.foreach_set('co', new.ravel())
    return ob


def make_morph_proxy(name, key_names, armature_cm):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.shape_key_add(name='Basis')
    for k in key_names:
        sk = ob.shape_key_add(name=k)
        sk.data[0].co.x += 0.001
    vg = ob.vertex_groups.new(name='root')
    vg.add([0, 1, 2], 1.0, 'REPLACE')
    md = ob.modifiers.new('Armature', 'ARMATURE')
    md.object = armature_cm
    ob.parent = armature_cm
    return ob


def write_export_action(arm_cm, name, baked, frame_offset=1):
    """Write baked per-frame keys (already in metres) on the cm armature, translations scaled x100."""
    import bpy_extras.anim_utils as au
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    slot = act.slots.new(id_type='OBJECT', name=arm_cm.name)
    cb = au.action_ensure_channelbag_for_slot(act, slot)
    names = baked['names']
    nf = baked['loc'].shape[0]
    frames = np.arange(nf, dtype=np.float64) + frame_offset
    for bi, n in enumerate(names):
        for path, arr, cnt, mul in (('location', baked['loc'][:, bi], 3, SC), ('rotation_quaternion', baked['quat'][:, bi], 4, 1.0), ('scale', baked['scale'][:, bi], 3, 1.0)):
            for k in range(cnt):
                fc = cb.fcurves.new(data_path=f'pose.bones["{n}"].{path}', index=k, group_name=n)
                fc.keyframe_points.add(nf)
                co = np.empty(nf * 2)
                co[0::2] = frames
                co[1::2] = arr[:, k] * mul
                fc.keyframe_points.foreach_set('co', co)
                fc.keyframe_points.foreach_set('interpolation', [1] * nf)
                fc.update()
    act.use_fake_user = False
    arm_cm.animation_data_create()
    arm_cm.animation_data.action = act
    arm_cm.animation_data.action_slot = slot
    return act


def write_morph_action(proxy, name, frames_n, curves, frame_offset=1):
    import bpy_extras.anim_utils as au
    keyd = proxy.data.shape_keys
    keyd.animation_data_create()
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    slot = act.slots.new(id_type='KEY', name='Key')
    cb = au.action_ensure_channelbag_for_slot(act, slot)
    frames = np.arange(frames_n, dtype=np.float64) + frame_offset
    for k, arr in curves.items():
        fc = cb.fcurves.new(data_path=f'key_blocks["{k}"].value', index=0)
        fc.keyframe_points.add(frames_n)
        co = np.empty(frames_n * 2)
        co[0::2] = frames
        co[1::2] = arr
        fc.keyframe_points.foreach_set('co', co)
        fc.keyframe_points.foreach_set('interpolation', [1] * frames_n)
        fc.update()
    keyd.animation_data.action = act
    keyd.animation_data.action_slot = slot
    return act


def fbx_export(path, objs, scene_units_cm=True, frame_range=None, **extra):
    sc = bpy.context.scene
    old_scale, old_len = sc.unit_settings.scale_length, sc.unit_settings.length_unit
    old_fr = (sc.frame_start, sc.frame_end, sc.render.fps, sc.render.fps_base)
    sc.render.fps, sc.render.fps_base = 30, 1.0
    if frame_range is not None:
        sc.frame_start, sc.frame_end = frame_range
    sc.unit_settings.scale_length = 0.01
    sc.unit_settings.length_unit = 'CENTIMETERS'
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_viewport = False
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    kw = dict(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False, bake_anim=True,
              bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True,
              bake_anim_simplify_factor=0.0, bake_anim_step=1.0, mesh_smooth_type='EDGE', use_armature_deform_only=False,
              axis_forward='-Z', axis_up='Y', primary_bone_axis='Y', secondary_bone_axis='X', apply_scale_options='FBX_SCALE_UNITS',
              use_tspace=True, use_custom_props=False, path_mode='COPY', embed_textures=False)
    kw.update(extra)
    bpy.ops.export_scene.fbx(**kw)
    sc.unit_settings.scale_length, sc.unit_settings.length_unit = old_scale, old_len
    sc.frame_start, sc.frame_end, sc.render.fps, sc.render.fps_base = old_fr

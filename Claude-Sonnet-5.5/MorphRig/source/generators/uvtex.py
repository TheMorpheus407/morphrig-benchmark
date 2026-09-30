"""UV layout, texture baking and material setup for the Operative (runs inside Blender).

  layout_uvs(objs)        one non-overlapping atlas per material: Smart UV Project + island packing across all objects that share the
                          material (temporary scaled copies give the head and hand a higher texel density); eyes use an analytic sphere map
  bake_textures(...)      rasterises position/normal/mask maps into every atlas and paints the texture set with paint.py
                          (procedural, no photographs). Files use Unreal conventions:
                          T_<Mat>_BC (sRGB base colour)  T_<Mat>_N (DirectX normal)  T_<Mat>_ORM (R=AO G=roughness B=metallic)
                          T_<Mat>_E (emission intensity, team coloured in the shader)  T_<Mat>_TM (R accent paint, G icon A, B icon B)
  build_materials(...)    Principled BSDF materials MI_* that read the same files, with a team switch (scene['mr_team'] 0/1)
                          and an optional rim outline (scene['mr_outline'])
"""
import hashlib
import json
import math
import os
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

import paint as PT

ATLAS = {'skin': 2048, 'suit': 2048, 'armor': 1024, 'cyber': 1024, 'hair': 1024, 'mouth': 512, 'eye': 1024}
UV_SCALE = {'Operative_Head': 1.7, 'Operative_Hand_R': 1.3, 'Operative_Mouth': 1.0}
MAT_TITLE = {'skin': 'Skin', 'suit': 'Suit', 'armor': 'Armor', 'cyber': 'Cyber', 'hair': 'Hair', 'mouth': 'Mouth', 'eye': 'Eye'}
EYE_C = {1: (0.0715, 0.031, 1.6855), -1: (0.0715, -0.031, 1.6855)}


def mesh_objects():
    return [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('Operative_')]


# ----------------------------------------------------------------------------- UV layout
def _select_faces(tmp, mat_name, hidden=None):
    """Select the faces of a material. hidden=True keeps only the faces that lie completely inside an eye pocket or the mouth cavity
    (region tag MR_MASKS.B of every vertex above 0.45), hidden=False keeps all the others, None keeps everything. Seen from the front the
    hidden faces lie behind the lids and lips, so they must not share an island with the visible skin (their UVs would overlap)."""
    bpy.ops.mesh.select_all(action='DESELECT')
    n = 0
    for _, t in tmp:
        idx = {i for i, m in enumerate(t.data.materials) if m is not None and m.name == 'MI_' + mat_name}
        if not idx:
            continue
        bm = bmesh.from_edit_mesh(t.data)
        bm.faces.ensure_lookup_table()
        lay = bm.verts.layers.float_color.get('MR_MASKS') if hidden is not None else None
        for f in bm.faces:
            if f.material_index in idx:
                if lay is not None:
                    is_hidden = all(v[lay][2] > 0.45 for v in f.verts)
                    if is_hidden != hidden:
                        continue
                f.select_set(True)
                n += 1
        bmesh.update_edit_mesh(t.data)
    return n


def layout_uvs(objs, margin=0.0035):
    sc = bpy.context.scene
    tmp = []
    for ob in objs:
        me = ob.data.copy()
        me.name = ob.data.name + '_uvtmp'
        while me.uv_layers:
            me.uv_layers.remove(me.uv_layers[0])
        s = UV_SCALE.get(ob.name, 1.0)
        if s != 1.0:
            me.transform(Matrix.Scale(s, 4))
        me.uv_layers.new(name='UVMap')
        t = bpy.data.objects.new(ob.name + '_uvtmp', me)
        sc.collection.objects.link(t)
        tmp.append((ob, t))
    bpy.ops.object.select_all(action='DESELECT')
    for _, t in tmp:
        t.select_set(True)
    bpy.context.view_layer.objects.active = tmp[0][1]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.use_uv_select_sync = True
    for mat in ('skin', 'suit', 'armor', 'cyber', 'hair', 'mouth'):
        for hidden in ((False, True) if mat == 'skin' else (None,)):
            if _select_faces(tmp, mat, hidden) > 0:
                bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.0, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
        _select_faces(tmp, mat)
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    for ob, t in tmp:
        n = len(t.data.loops)
        arr = np.empty(n * 2, np.float32)
        t.data.uv_layers['UVMap'].data.foreach_get('uv', arr)
        layer = ob.data.uv_layers.get('UVMap') or ob.data.uv_layers.new(name='UVMap')
        layer.data.foreach_set('uv', arr)
        layer.active = True
        layer.active_render = True
    # analytic sphere map for the eyes (the seam sits behind the eyeball, hidden inside the head)
    for ob in objs:
        if ob.name != 'Operative_Eyes':
            continue
        me = ob.data
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        vidx = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get('vertex_index', vidx)
        p = co[vidx]
        cen = np.where((p[:, 1] >= 0)[:, None], np.array(EYE_C[1], np.float32), np.array(EYE_C[-1], np.float32))
        d = p - cen
        d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        u = 0.5 + np.arctan2(d[:, 1], d[:, 0]) / (2 * math.pi)
        v = 0.5 + np.arcsin(np.clip(d[:, 2], -1, 1)) / math.pi
        # forward (+X) maps to u = 0.5; the wrap seam is at the back (-X)
        uv = np.stack([u, v], axis=1).astype(np.float32)
        uv[:, 0] = np.where(uv[:, 0] < 0, uv[:, 0] + 1.0, uv[:, 0])
        ob.data.uv_layers['UVMap'].data.foreach_set('uv', uv.ravel())
    for ob, t in tmp:
        me = t.data
        bpy.data.objects.remove(t)
        bpy.data.meshes.remove(me)


def uv_hash(objs):
    h = hashlib.sha1()
    for ob in sorted(objs, key=lambda o: o.name):
        me = ob.data
        arr = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers['UVMap'].data.foreach_get('uv', arr)
        h.update(ob.name.encode())
        h.update(np.round(arr, 5).tobytes())
    return h.hexdigest()


# ----------------------------------------------------------------------------- rasterisation
def _gather(objs, mat_name):
    tris = {'uv': [], 'pos': [], 'nrm': [], 'mask': [], 'oid': []}
    names = []
    for ob in objs:
        me = ob.data
        slots = [i for i, m in enumerate(me.materials) if m is not None and m.name == 'MI_' + mat_name]
        if not slots:
            continue
        oid = len(names)
        names.append(ob.name)
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        loops = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get('loops', loops)
        loops = loops.reshape(-1, 3)
        mi = np.empty(nt, np.int32)
        me.loop_triangles.foreach_get('material_index', mi)
        loops = loops[np.isin(mi, slots)]
        if len(loops) == 0:
            continue
        uv = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers['UVMap'].data.foreach_get('uv', uv)
        uv = uv.reshape(-1, 2)
        vidx = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get('vertex_index', vidx)
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        M4 = np.array(ob.matrix_world, np.float32)
        co = co @ M4[:3, :3].T + M4[:3, 3]
        cn = np.empty(len(me.loops) * 3, np.float32)
        me.corner_normals.foreach_get('vector', cn)
        cn = cn.reshape(-1, 3) @ M4[:3, :3].T
        cn = cn / np.maximum(np.linalg.norm(cn, axis=1, keepdims=True), 1e-9)
        attr = me.color_attributes.get('MR_MASKS')
        if attr is not None:
            cols = np.empty(len(me.vertices) * 4, np.float32)
            attr.data.foreach_get('color', cols)
            cols = cols.reshape(-1, 4)[:, :3]
        else:
            cols = np.zeros((len(me.vertices), 3), np.float32)
        tris['uv'].append(uv[loops])
        tris['pos'].append(co[vidx[loops]])
        tris['nrm'].append(cn[loops])
        mk = cols[vidx[loops]].copy()                 # (triangles, 3 corners, 3 channels)
        # region tags live on vertices: a triangle that mixes an eye pocket ring (0.5) with skin (0) or ear (0.25) vertices would fade the pocket colour
        # across skin next to the lid corners, so the pocket tag only counts on triangles that lie completely inside the pocket
        tg = mk[:, :, 2]
        pk = (tg > 0.4) & (tg < 0.6)
        mixed = pk.any(axis=1) & (tg < 0.4).any(axis=1)
        tg[mixed[:, None] & pk] = 0.0
        mk[:, :, 2] = tg
        tris['mask'].append(mk)
        tris['oid'].append(np.full(len(loops), oid, np.int16))
    return {k: np.concatenate(v) for k, v in tris.items()}, names


def rasterise(objs, mat_name, size):
    T, names = _gather(objs, mat_name)
    H = W = size
    pos = np.zeros((H, W, 3), np.float32)
    nrm = np.zeros((H, W, 3), np.float32)
    tx = np.zeros((H, W, 3), np.float32)
    ty = np.zeros((H, W, 3), np.float32)
    sx = np.zeros((H, W), np.float32)
    sy = np.zeros((H, W), np.float32)
    mask = np.zeros((H, W, 3), np.float32)
    oid = np.full((H, W), -1, np.int16)
    cov = np.zeros((H, W), bool)
    uv, P, N, MK, OID = T['uv'], T['pos'], T['nrm'], T['mask'], T['oid']
    eye = mat_name == 'eye'
    for i in range(len(uv)):
        q = uv[i]
        if eye and (q[:, 0].max() - q[:, 0].min()) > 0.5:
            continue                                                    # wraps over the hidden seam
        px = q[:, 0] * W
        py = q[:, 1] * H
        x0 = int(max(math.floor(px.min() - 0.5), 0))
        x1 = int(min(math.ceil(px.max() + 0.5), W - 1))
        y0 = int(max(math.floor(py.min() - 0.5), 0))
        y1 = int(min(math.ceil(py.max() + 0.5), H - 1))
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1, dtype=np.float32) + 0.5
        ys = np.arange(y0, y1 + 1, dtype=np.float32) + 0.5
        X, Y = np.meshgrid(xs, ys)
        ax, bx, cx = (float(v) for v in px)
        ay, by, cy = (float(v) for v in py)
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-10:
            continue
        l0 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / det
        l1 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / det
        l2 = 1.0 - l0 - l1
        eps = -0.02
        inside = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
        if not inside.any():
            continue
        p0, p1, p2 = P[i]
        e1, e2 = p1 - p0, p2 - p0
        d1, d2 = q[1] - q[0], q[2] - q[0]
        r = d1[0] * d2[1] - d2[0] * d1[1]
        if abs(r) < 1e-12:
            continue
        tu = (e1 * d2[1] - e2 * d1[1]) / r
        tv = (e2 * d1[0] - e1 * d2[0]) / r
        lu, lv = float(np.linalg.norm(tu)), float(np.linalg.norm(tv))
        yy, xx = np.nonzero(inside)
        L0, L1, L2 = l0[yy, xx][:, None], l1[yy, xx][:, None], l2[yy, xx][:, None]
        gy, gx = yy + y0, xx + x0
        pos[gy, gx] = L0 * p0 + L1 * p1 + L2 * p2
        nrm[gy, gx] = L0 * N[i][0] + L1 * N[i][1] + L2 * N[i][2]
        mask[gy, gx] = L0 * MK[i][0] + L1 * MK[i][1] + L2 * MK[i][2]
        tx[gy, gx] = tu / max(lu, 1e-9)
        ty[gy, gx] = tv / max(lv, 1e-9)
        sx[gy, gx] = lu / W
        sy[gy, gx] = lv / H
        oid[gy, gx] = OID[i]
        cov[gy, gx] = True
    ln = np.linalg.norm(nrm, axis=-1, keepdims=True)
    nrm = nrm / np.maximum(ln, 1e-9)
    M = dict(pos=pos, nrm=nrm, tx=tx, ty=ty, sx=sx, sy=sy, mask=mask, oid=oid, cov=cov, names=names)
    M['raw_cov'] = cov.copy()
    _dilate(M, max(2, size // 128))
    M['texel'] = 0.5 * (M['sx'] + M['sy'])
    return M


def _dilate(M, iters):
    arrs = [M[k] for k in ('pos', 'nrm', 'tx', 'ty', 'sx', 'sy', 'mask', 'oid')]
    cov = M['cov']
    for _ in range(iters):
        grow = ~cov
        new_cov = cov.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            src_cov = np.roll(cov, (dy, dx), axis=(0, 1))
            take = grow & src_cov & ~new_cov
            if not take.any():
                continue
            for a in arrs:
                a[take] = np.roll(a, (dy, dx), axis=(0, 1))[take]
            new_cov |= take
        cov = new_cov
    M['cov'] = cov


# ----------------------------------------------------------------------------- output
NORMAL_GAIN = {'skin': 7.0, 'suit': 5.0, 'armor': 3.0, 'cyber': 3.0, 'hair': 2.5, 'mouth': 3.0, 'eye': 1.0}


def _normal_from_height(h, M, gain=1.0):
    """Height (m) -> DirectX tangent normal map using the real texel size of every pixel (green points down the image)."""
    gx = np.zeros_like(h)
    gy = np.zeros_like(h)
    gx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) * 0.5
    gy[1:-1] = (h[2:] - h[:-2]) * 0.5
    sx = np.maximum(M['sx'], 2e-5)
    sy = np.maximum(M['sy'], 2e-5)
    gu = gain * gx / sx
    gv = gain * gy / sy
    n = np.stack([-gu, -gv, np.ones_like(gu)], axis=-1)          # OpenGL: +V up
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    n[..., 1] *= -1.0                                             # DirectX convention (Unreal)
    return n * 0.5 + 0.5


def _save(path, arr):
    H, W = arr.shape[:2]
    C = 1 if arr.ndim == 2 else arr.shape[2]
    rgba = np.ones((H, W, 4), np.float32)
    if C == 1:
        rgba[..., :3] = arr[..., None]
    else:
        rgba[..., :C] = arr
    img = bpy.data.images.new('mr_tmp', W, H, alpha=(C == 4), float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(np.clip(rgba, 0, 1).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def write_maps(mat, ch, M, out_dir):
    cov = M['cov']
    T = MAT_TITLE[mat]
    files = {}
    bc = np.clip(ch['bc'], 0, 1).copy()
    fill = bc[cov].mean(axis=0) if cov.any() else np.array([0.5, 0.5, 0.5], np.float32)
    bc[~cov] = fill
    _save(os.path.join(out_dir, f'T_{T}_BC.png'), bc)
    files['bc'] = f'T_{T}_BC.png'
    n = _normal_from_height(ch['height'], M, NORMAL_GAIN.get(mat, 1.0))
    n[~cov] = np.array([0.5, 0.5, 1.0], np.float32)
    _save(os.path.join(out_dir, f'T_{T}_N.png'), n.astype(np.float32))
    files['n'] = f'T_{T}_N.png'
    orm = np.stack([ch['ao'], ch['rough'], ch['metal']], axis=-1).astype(np.float32)
    orm[~cov] = np.array([1.0, 0.6, 0.0], np.float32)
    _save(os.path.join(out_dir, f'T_{T}_ORM.png'), orm)
    files['orm'] = f'T_{T}_ORM.png'
    if ch['emit'].max() > 0.01:
        e = ch['emit'].copy()
        e[~cov] = 0.0
        _save(os.path.join(out_dir, f'T_{T}_E.png'), e)
        files['e'] = f'T_{T}_E.png'
    tm = ch['tm'].copy()
    if tm[..., :3].max() > 0.01:
        tm[~cov] = np.array([0, 0, 0, 1], np.float32)
        _save(os.path.join(out_dir, f'T_{T}_TM.png'), tm)
        files['tm'] = f'T_{T}_TM.png'
    return files


def bake_textures(objs, out_dir, only=None, atlas=None, log=print):
    os.makedirs(out_dir, exist_ok=True)
    atlas = atlas or ATLAS
    manifest = {}
    for mat, size in atlas.items():
        if only and mat not in only:
            continue
        t0 = time.time()
        M = rasterise(objs, mat, size)
        t1 = time.time()
        ch = PT.PAINTERS[mat](M)
        files = write_maps(mat, ch, M, out_dir)
        log(f'[textures] {mat:6s} {size}x{size} island coverage {100.0 * M["raw_cov"].mean():.1f}% (padded {100.0 * M["cov"].mean():.1f}%)  raster {t1 - t0:.1f}s paint+write {time.time() - t1:.1f}s')
        manifest[mat] = dict(size=size, files=files, island_coverage=round(float(M['raw_cov'].mean()), 4), objects=M['names'])
    return manifest


# ----------------------------------------------------------------------------- materials
TEAM_COLORS = {'A': (0.05, 0.85, 1.0), 'B': (1.0, 0.10, 0.62)}


def _srgb_to_linear(c):
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c)


def team_group():
    ng = bpy.data.node_groups.get('MR_Team')
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new('MR_Team', 'ShaderNodeTree')
    ng.interface.new_socket('Color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket('Icon', in_out='OUTPUT', socket_type='NodeSocketFloat')
    ng.interface.new_socket('Rim', in_out='OUTPUT', socket_type='NodeSocketFloat')
    out = ng.nodes.new('NodeGroupOutput')
    out.location = (600, 0)
    a = ng.nodes.new('ShaderNodeRGB')
    a.name = 'ColorA'
    a.outputs[0].default_value = (*_srgb_to_linear(TEAM_COLORS['A']), 1.0)
    a.location = (-400, 100)
    b = ng.nodes.new('ShaderNodeRGB')
    b.name = 'ColorB'
    b.outputs[0].default_value = (*_srgb_to_linear(TEAM_COLORS['B']), 1.0)
    b.location = (-400, -100)
    mix = ng.nodes.new('ShaderNodeMix')
    mix.name = 'TeamMix'
    mix.data_type = 'RGBA'
    mix.location = (0, 0)
    ng.links.new(a.outputs[0], mix.inputs[6])
    ng.links.new(b.outputs[0], mix.inputs[7])
    ng.links.new(mix.outputs[2], out.inputs['Color'])
    ico = ng.nodes.new('ShaderNodeValue')
    ico.name = 'IconSel'
    ico.location = (0, -200)
    ng.links.new(ico.outputs[0], out.inputs['Icon'])
    lw = ng.nodes.new('ShaderNodeLayerWeight')
    lw.inputs['Blend'].default_value = 0.35
    lw.location = (-400, -350)
    rim_pow = ng.nodes.new('ShaderNodeMath')
    rim_pow.operation = 'POWER'
    rim_pow.inputs[1].default_value = 3.0
    rim_pow.location = (-200, -350)
    ng.links.new(lw.outputs['Fresnel'], rim_pow.inputs[0])
    rim_mul = ng.nodes.new('ShaderNodeMath')
    rim_mul.name = 'RimStrength'
    rim_mul.operation = 'MULTIPLY'
    rim_mul.inputs[1].default_value = 0.0
    rim_mul.location = (0, -350)
    ng.links.new(rim_pow.outputs[0], rim_mul.inputs[0])
    ng.links.new(rim_mul.outputs[0], out.inputs['Rim'])
    sc = bpy.context.scene
    sc['mr_team'] = sc.get('mr_team', 0)
    sc['mr_outline'] = sc.get('mr_outline', 0.0)
    for path, prop in (('nodes["TeamMix"].inputs[0].default_value', 'mr_team'), ('nodes["IconSel"].outputs[0].default_value', 'mr_team'),
                       ('nodes["RimStrength"].inputs[1].default_value', 'mr_outline')):
        fc = ng.driver_add(path)
        d = fc.driver
        d.type = 'AVERAGE'
        v = d.variables.new()
        v.name = 'v'
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'SCENE'
        v.targets[0].id = sc
        v.targets[0].data_path = f'["{prop}"]'
    return ng


def _img(nt, path, non_color, loc):
    n = nt.nodes.new('ShaderNodeTexImage')
    n.image = bpy.data.images.load(path, check_existing=True)
    n.image.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    n.interpolation = 'Linear'
    n.location = loc
    return n


def build_material(mat, tex_dir, files):
    name = 'MI_' + mat
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (1200, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (900, 0)
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    P = lambda f: os.path.join(tex_dir, f)
    bc = _img(nt, P(files['bc']), False, (-700, 400))
    orm = _img(nt, P(files['orm']), True, (-700, 100))
    nm = _img(nt, P(files['n']), True, (-700, -250))
    sep_orm = nt.nodes.new('ShaderNodeSeparateColor')
    sep_orm.location = (-420, 100)
    nt.links.new(orm.outputs['Color'], sep_orm.inputs['Color'])
    nt.links.new(sep_orm.outputs['Green'], bsdf.inputs['Roughness'])
    nt.links.new(sep_orm.outputs['Blue'], bsdf.inputs['Metallic'])
    # DirectX normal -> flip green -> Normal Map
    sep_n = nt.nodes.new('ShaderNodeSeparateColor')
    sep_n.location = (-420, -250)
    nt.links.new(nm.outputs['Color'], sep_n.inputs['Color'])
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    inv.location = (-250, -300)
    nt.links.new(sep_n.outputs['Green'], inv.inputs[1])
    comb = nt.nodes.new('ShaderNodeCombineColor')
    comb.location = (-80, -250)
    nt.links.new(sep_n.outputs['Red'], comb.inputs['Red'])
    nt.links.new(inv.outputs[0], comb.inputs['Green'])
    nt.links.new(sep_n.outputs['Blue'], comb.inputs['Blue'])
    nmap = nt.nodes.new('ShaderNodeNormalMap')
    nmap.uv_map = 'UVMap'
    nmap.location = (150, -250)
    nt.links.new(comb.outputs['Color'], nmap.inputs['Color'])
    nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    # base colour: AO multiplied in, team paint / icon tint
    ao_mul = nt.nodes.new('ShaderNodeMix')
    ao_mul.data_type = 'RGBA'
    ao_mul.blend_type = 'MULTIPLY'
    ao_mul.inputs[0].default_value = 0.8
    ao_mul.location = (-150, 350)
    nt.links.new(bc.outputs['Color'], ao_mul.inputs[6])
    nt.links.new(sep_orm.outputs['Red'], ao_mul.inputs[7])
    color_out = ao_mul.outputs[2]
    tg = nt.nodes.new('ShaderNodeGroup')
    tg.node_tree = team_group()
    tg.location = (-150, 650)
    if 'tm' in files:
        tm = _img(nt, P(files['tm']), True, (-700, 700))
        sep_tm = nt.nodes.new('ShaderNodeSeparateColor')
        sep_tm.location = (-420, 700)
        nt.links.new(tm.outputs['Color'], sep_tm.inputs['Color'])
        icon = nt.nodes.new('ShaderNodeMix')
        icon.data_type = 'FLOAT'
        icon.location = (-250, 600)
        nt.links.new(tg.outputs['Icon'], icon.inputs[0])
        nt.links.new(sep_tm.outputs['Green'], icon.inputs[2])
        nt.links.new(sep_tm.outputs['Blue'], icon.inputs[3])
        mask = nt.nodes.new('ShaderNodeMath')
        mask.operation = 'ADD'
        mask.use_clamp = True
        mask.location = (-80, 620)
        nt.links.new(sep_tm.outputs['Red'], mask.inputs[0])
        nt.links.new(icon.outputs[0], mask.inputs[1])
        tint = nt.nodes.new('ShaderNodeMix')
        tint.data_type = 'RGBA'
        tint.blend_type = 'MULTIPLY'
        tint.inputs[0].default_value = 1.0
        tint.location = (100, 480)
        nt.links.new(color_out, tint.inputs[6])
        nt.links.new(tg.outputs['Color'], tint.inputs[7])
        bright = nt.nodes.new('ShaderNodeMix')
        bright.data_type = 'RGBA'
        bright.blend_type = 'MIX'
        bright.location = (300, 420)
        nt.links.new(mask.outputs[0], bright.inputs[0])
        nt.links.new(color_out, bright.inputs[6])
        nt.links.new(tint.outputs[2], bright.inputs[7])
        color_out = bright.outputs[2]
        icon_glow = nt.nodes.new('ShaderNodeMath')            # the selected icon glows softly in the team colour (readable at night and from above)
        icon_glow.operation = 'MULTIPLY'
        icon_glow.inputs[1].default_value = 0.35
        icon_glow.location = (-80, 780)
        nt.links.new(icon.outputs[0], icon_glow.inputs[0])
        glow_col = nt.nodes.new('ShaderNodeMix')
        glow_col.data_type = 'RGBA'
        glow_col.blend_type = 'MULTIPLY'
        glow_col.inputs[0].default_value = 1.0
        glow_col.location = (100, 780)
        nt.links.new(tg.outputs['Color'], glow_col.inputs[6])
        nt.links.new(icon_glow.outputs[0], glow_col.inputs[7])
        icon_glow_out = glow_col.outputs[2]
    else:
        icon_glow_out = None
    nt.links.new(color_out, bsdf.inputs['Base Color'])
    # emission: authored strips tinted with the team colour, plus the optional rim outline
    emit_src = None
    if 'e' in files:
        e = _img(nt, P(files['e']), True, (-700, -600))
        emul = nt.nodes.new('ShaderNodeMix')
        emul.data_type = 'RGBA'
        emul.blend_type = 'MULTIPLY'
        emul.inputs[0].default_value = 1.0
        emul.location = (300, -600)
        nt.links.new(e.outputs['Color'], emul.inputs[6])
        nt.links.new(tg.outputs['Color'], emul.inputs[7])
        emit_src = emul.outputs[2]
    rim = nt.nodes.new('ShaderNodeMix')
    rim.data_type = 'RGBA'
    rim.blend_type = 'MULTIPLY'
    rim.inputs[0].default_value = 1.0
    rim.location = (300, -800)
    nt.links.new(tg.outputs['Color'], rim.inputs[6])
    nt.links.new(tg.outputs['Rim'], rim.inputs[7])
    emit_final = rim.outputs[2]
    for k, extra_src in enumerate([e for e in (emit_src, icon_glow_out) if e is not None]):
        add = nt.nodes.new('ShaderNodeMix')
        add.data_type = 'RGBA'
        add.blend_type = 'ADD'
        add.inputs[0].default_value = 1.0
        add.location = (600 + 200 * k, -650)
        nt.links.new(emit_final, add.inputs[6])
        nt.links.new(extra_src, add.inputs[7])
        emit_final = add.outputs[2]
    nt.links.new(emit_final, bsdf.inputs['Emission Color'])
    bsdf.inputs['Emission Strength'].default_value = 2.5 if 'e' in files else (2.0 if 'tm' in files else 1.0)
    if mat == 'eye':
        bsdf.inputs['Coat Weight'].default_value = 1.0
        bsdf.inputs['Coat Roughness'].default_value = 0.03
    return m


def build_materials(tex_dir, manifest):
    team_group()
    mats = {}
    for mat, info in manifest.items():
        mats[mat] = build_material(mat, tex_dir, info['files'])
    return mats


def load_manifest(tex_dir):
    p = os.path.join(tex_dir, 'texture_manifest.json')
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def save_manifest(tex_dir, manifest, uvh):
    with open(os.path.join(tex_dir, 'texture_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump({'uv_layout_sha1': uvh, 'materials': manifest}, fh, indent=1)

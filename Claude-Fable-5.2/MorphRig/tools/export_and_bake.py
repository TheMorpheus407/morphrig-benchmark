"""MORPHRIG production build: generates the Operative from the procedural sources, saves the editable Blender
file, bakes every clip onto the deformation skeleton and writes all exports and data documents.

    blender -b --factory-startup -P tools/export_and_bake.py -- [options]

Options
    --root <dir>        MorphRig folder (default: the parent of this script's folder)
    --tex-scale <f>     texture resolution factor (1.0 = final sizes, 0.25 = quick preview)
    --reuse-textures    keep the textures already in source/textures (skips painting and the AO bake)
    --clips a,b,c       only build these clips (development; the manifest is then marked partial)
    --no-export         stop after saving source/Operative.blend
    --no-blend          do not save the .blend (export only)
    --out <dir>         write all outputs below this folder instead of --root (development)
    --from-blend        (run with source/Operative.blend opened) re-bake and re-export the edited source actions of the
                        file instead of regenerating everything; combine with --clips

Writes
    source/Operative.blend, source/textures/*, export/Operative.fbx, export/Operative_LOD1.fbx, export/Operative_LOD2.fbx,
    export/animations/<clip>.fbx (96), export/props/SM_*.fbx, export/textures/*,
    docs/skeleton_and_sockets.json, docs/face_controls.json, docs/animation_manifest.json, docs/material_and_lod_report.json

Everything in the scene is created by the generators in source/generators (procedural source, no interactive edits).
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def opt(name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--') else True
    return default


ROOT = os.path.abspath(opt('--root', os.path.join(HERE, '..')))
sys.path.insert(0, os.path.join(ROOT, 'source', 'generators'))

import bpy                                                               # noqa: E402
import numpy as np                                                       # noqa: E402
from mathutils import Matrix, Vector                                     # noqa: E402
from mr import (preview, charmesh, texgen, materials, lod, armature, rig as rigmod, animkit, animbuild, animio, bake, clips, facedefs,
                docsgen, secondary, rigui, demoposes, skel)             # noqa: E402
from mr import export as mrexport                                        # noqa: E402

T0 = time.time()


def log(*a):
    print('[%7.1fs]' % (time.time() - T0), *a)
    sys.stdout.flush()


OUT = os.path.abspath(opt('--out', ROOT))                              # development: write everything somewhere else
SRC_TEX = os.path.join(OUT, 'source', 'textures')
EXP = os.path.join(OUT, 'export')
EXP_TEX = os.path.join(EXP, 'textures')
DOCS = os.path.join(OUT, 'docs')
BLEND = os.path.join(OUT, 'source', 'Operative.blend')
for d in (SRC_TEX, EXP_TEX, DOCS, os.path.dirname(BLEND), os.path.join(EXP, 'animations'), os.path.join(EXP, 'props')):
    os.makedirs(d, exist_ok=True)



def rebake_from_blend():
    """Re-bake and re-export edited source actions of the opened Operative.blend (no regeneration)."""
    sc = bpy.context.scene
    rg = bpy.data.objects[rigmod.RIG_NAME]
    sk = bpy.data.objects[rigmod.SKEL_NAME]
    proxy = bpy.data.objects['MorphProxy']
    man_path = os.path.join(DOCS, 'animation_manifest.json')
    man = json.load(open(man_path))
    by_id = {c['id']: c for c in man['clips']}
    only = opt('--clips')
    ids = [c['id'] for c in clips.CLIPS if c['id'] in bpy.data.actions]
    if only and only is not True:
        ids = [i for i in ids if i in set(only.split(','))]
    for o in (rg, sk, proxy):
        o.hide_viewport = False
        o.hide_set(False)
    rigmod.set_follow(sk, True)
    baked = {}
    for cid in ids:
        act = bpy.data.actions[cid]
        slot = act.slots[0]
        meta = clips.BY_ID[cid]
        is_pose = meta['form'] == 'pose'
        n = 1 if is_pose else int(round(act.frame_range[1]))
        frames, tracks, morphs, world = bake.sample_clip(cid, n, rg, sk, act, slot, is_pose)
        baked[cid] = bake.write_baked(cid, sk, proxy.data.shape_keys, frames, tracks, morphs)
        m = bake.metrics(meta, frames, tracks, world, {})
        e = by_id[cid]
        if not is_pose:
            e['frame_end'] = n
            e['sample_count'] = n + 1
            e['duration'] = round(n / float(clips.FPS), 6)
            if len(act.pose_markers):                        # event markers are the action's pose markers
                e['events'] = [dict(name=mk.name, frame=int(mk.frame)) for mk in sorted(act.pose_markers, key=lambda m: (m.frame, m.name))]
            for ev in e.get('events', []):
                ev['frame'] = max(0, min(int(ev['frame']), n))
                ev['time'] = round(ev['frame'] / float(clips.FPS), 6)
                ev['normalized'] = round(ev['frame'] / float(max(1, n)), 6)
        e['root_motion']['displacement_cm'] = m['root_displacement_cm']
        e['rebaked_from_blend'] = True
        log('re-baked', cid, 'frames', n, 'slide %.2f cm/s' % m['slide_max_cm_s'], 'lowest sole %.2f cm' % m['min_sole_height_cm'])
    docsgen.write_json(man_path, man)
    rigmod.reset_pose(rg)
    bpy.ops.wm.save_mainfile()
    # export from an in-memory centimetre copy (never saved)
    rigmod.set_follow(sk, False)
    if rg.animation_data:
        rg.animation_data.action = None
    mrexport.to_centimetres(sk, [proxy], [a for (a, s, k) in baked.values()])
    armature.reset_pose(sk)
    scene_name = sc.name
    for cid in ids:
        act, slot, kact = baked[cid]
        armature.reset_pose(sk)
        animio.assign(sk, act, slot)
        kd = proxy.data.shape_keys
        for kb in kd.key_blocks:
            kb.value = 0.0
        if kact is not None:
            animio.assign(kd, kact)
        elif kd.animation_data:
            kd.animation_data.action = None
        sc.frame_start = 0
        sc.frame_end = by_id[cid]['frame_end']
        sc.name = cid
        mrexport.export_fbx(os.path.join(EXP, 'animations', cid + '.fbx'), sk, [proxy], True)
    sc.name = scene_name
    log('re-exported', len(ids), 'clips; re-import in Unreal with tools/ue_import.sh')


if opt('--from-blend'):
    assert bpy.data.filepath, 'open source/Operative.blend:  blender -b source/Operative.blend -P tools/export_and_bake.py -- --from-blend'
    rebake_from_blend()
    sys.exit(0)

probs = clips.check_against_csv(os.path.join(ROOT, '..', 'required_animations.csv')) if os.path.exists(os.path.join(ROOT, '..', 'required_animations.csv')) else []
assert not probs, probs

# ------------------------------------------------------------------------------------------------ scene
sc = preview.reset_scene()
sc.name = 'Operative'
sc.render.fps = clips.FPS
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 1.0


def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or sc.collection
    if c.name not in [x.name for x in par.children]:
        par.children.link(c)
    return c


C_CHAR = collection('Character')
C_LOD = collection('LODs', C_CHAR)
C_RIG = collection('Rig')
C_WGT = collection('Widgets', C_RIG)
C_EXPORT = collection('Export')
C_PROPS = collection('Props', C_EXPORT)


def move_to(ob, coll):
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)


# ------------------------------------------------------------------------------------------------ mesh, UVs, textures
ob, info = charmesh.build_character(name='Operative_LOD0')
n_head = len(info['parts']['Head'].v)
move_to(ob, C_CHAR)
log('mesh', len(ob.data.vertices), 'verts,', lod.tri_count(ob), 'tris, uv', info['uv_stats'])

tex_scale = float(opt('--tex-scale', 1.0))
man_path = os.path.join(SRC_TEX, 'texture_manifest.json')
if opt('--reuse-textures') and os.path.exists(man_path):
    tex_doc = json.load(open(man_path))
    log('textures reused')
else:
    tex_doc = texgen.generate(ob, [SRC_TEX], scale=tex_scale, log=log)
for fn in os.listdir(SRC_TEX):
    shutil.copy2(os.path.join(SRC_TEX, fn), os.path.join(EXP_TEX, fn))
materials.build_materials(ob, SRC_TEX, tex_doc)

# ------------------------------------------------------------------------------------------------ LODs
lods = [ob]
for lv in (1, 2):
    lo = lod.make_lod(ob, lv, n_head)
    move_to(lo, C_LOD)
    materials.set_team(lo, 'A')
    lods.append(lo)
    log('LOD%d' % lv, lod.report(lo))

# ------------------------------------------------------------------------------------------------ skeleton, rig, binding
animkit.reset_rest()
sk = armature.build_skeleton()
move_to(sk, C_EXPORT)
for m in lods:
    armature.bind(m, sk)
rg, finfo = rigmod.build_rig(collection=C_RIG, widget_collection=C_WGT)
rigmod.link_skeleton(sk, rg)
for m in lods:
    rigmod.add_shape_key_drivers(m, rg, finfo)
bad = rigmod.check_simple_drivers(rg, *[m.data.shape_keys for m in lods])
assert not bad, bad
for m in lods[1:]:
    m.hide_viewport = True
    m.hide_render = True
log('rig', len(rg.data.bones), 'bones; skeleton', len(sk.data.bones), 'deform bones')

# morph proxy: carries the baked morph curves inside every animation FBX
pm = bpy.data.meshes.new('MorphProxy')
pm.from_pydata([(0, 0, 0), (0.001, 0, 0), (0, 0, 0.001)], [], [(0, 1, 2)])
proxy = bpy.data.objects.new('MorphProxy', pm)
C_EXPORT.objects.link(proxy)
proxy.vertex_groups.new(name='root').add([0, 1, 2], 1.0, 'REPLACE')
armature.bind(proxy, sk)
proxy.shape_key_add(name='Basis')
for name in facedefs.MORPHS:
    kb = proxy.shape_key_add(name=name)
    kb.value = 0.0
    kb.data[0].co = Vector((0, 0, 0.001))
proxy.hide_render = True

# ------------------------------------------------------------------------------------------------ animation
animbuild.load_clip_modules()
only = opt('--clips')
ids = [c['id'] for c in clips.CLIPS]
if only:
    ids = [i for i in ids if i in set(only.split(','))]
missing = [i for i in ids if i not in animbuild.REGISTRY]
assert not missing, missing
FLOOR_CONTACT = {'land_heavy', 'cast_ground', 'deploy', 'knockdown_front', 'knockdown_back', 'prone_front', 'prone_back', 'getup_front',
                 'getup_back', 'sleep_start', 'sleep_loop', 'sleep_end', 'death_front', 'death_back', 'dead_front', 'dead_back', 'respawn'}
clip_infos = {}
baked = {}
sources = {}
worst = dict(loop=(0.0, None), slide=(0.0, None), pen=(1.0, None))
for k, cid in enumerate(ids):
    clip, act, slot = animbuild.build_clip(cid, rg)
    is_pose = clip.meta['form'] == 'pose'
    pose_of = clip.meta.get('pose_of')
    if is_pose and pose_of and pose_of[0] in sources:
        # held pose of another clip: take the cable exactly as that clip leaves it
        sa, ss, sn = sources[pose_of[0]]
        secondary.copy_cable_end(rg, sa, ss, sn if pose_of[1] == 'last' else 0, act, slot)
    else:
        secondary.bake_cable(rg, act, slot, clip.frames, loop=clip.loop, is_pose=is_pose)
    sources[cid] = (act, slot, clip.frames)
    act['loop'] = bool(clip.loop)
    act['clip_form'] = clip.meta['form']
    for ev in clip.events:                                   # event markers travel with the action (editable in Blender)
        mk = act.pose_markers.new(ev['name'])
        mk.frame = int(ev['frame'])
    res = animbuild.bake_clip(clip, act, slot, rg, sk, proxy.data.shape_keys, write=True)
    m = res['metrics']
    baked[cid] = res['baked']
    qa = dict(slide_max_cm_s=m['slide_max_cm_s'], min_sole_height_cm=m['min_sole_height_cm'], body_clear_cm=m['body_clear_cm'])
    if 'loop_error' in m:
        qa['loop_error'] = round(m['loop_error'], 6)
        if m['loop_error'] > worst['loop'][0]:
            worst['loop'] = (m['loop_error'], cid)
    if clip.meta['layer'] == 'locomotion' and m['slide_max_cm_s'] > worst['slide'][0]:
        worst['slide'] = (m['slide_max_cm_s'], cid)
    if m['min_sole_height_cm'] < worst['pen'][0]:
        worst['pen'] = (m['min_sole_height_cm'], cid)
    dense = sum(1 for key in clip.keys if key in clip.dense)
    clip_infos[cid] = dict(frames=clip.frames, events=clip.events, root_displacement_cm=m['root_displacement_cm'], source_action=act.name,
                           baked_action='BAKED_' + cid, prop_tracks=list(clip.prop_tracks), notes=dict(clip.notes),
                           floor_contact=cid in FLOOR_CONTACT, qa=qa,
                           source_keys='dense' if dense > 0.5 * max(1, len(clip.keys)) else 'sparse')
    if (k + 1) % 16 == 0:
        log('clips', k + 1, '/', len(ids))
log('baked', len(baked), 'clips; worst loop error %.2g (%s), locomotion slide %.2f cm/s (%s), lowest sole %.2f cm (%s)' % (
    worst['loop'][0], worst['loop'][1], worst['slide'][0], worst['slide'][1], worst['pen'][0], worst['pen'][1]))

demo = demoposes.install(rg)
rigui.install()

# ------------------------------------------------------------------------------------------------ documents
docsgen.write_json(os.path.join(DOCS, 'skeleton_and_sockets.json'), docsgen.skeleton_doc(placeholder=False))
docsgen.write_json(os.path.join(DOCS, 'face_controls.json'), docsgen.face_doc())
man = docsgen.manifest_doc(clip_infos, placeholder=False)
if only:
    man['partial'] = True
docsgen.write_json(os.path.join(DOCS, 'animation_manifest.json'), man)

lod_rep = [lod.report(m) for m in lods]
for r, lim in zip(lod_rep, (80000, 40000, 20000)):
    r['triangle_limit'] = lim
    assert r['triangles'] <= lim and r['max_bone_influences'] <= 8 and r['material_slots'] <= 8, r
    assert r['loose_vertices'] == 0 and r['zero_area_faces'] == 0 and r['non_manifold_edges_over_2_faces'] == 0, r
tex_files = []
mem = 0.0
for m in tex_doc['materials']:
    for key in ('base_color', 'normal', 'orm', 'mask'):
        fn = m.get(key)
        if not fn:
            continue
        img = bpy.data.images.load(os.path.join(SRC_TEX, fn), check_existing=True)
        w, h = img.size
        # GPU estimate with block compression and a full mip chain: BC5 normal 1 byte/px, BC1 colour/ORM 0.5, BC3 mask 1
        bpp = 1.0 if key in ('normal', 'mask') else 0.5
        mb = w * h * bpp * 4.0 / 3.0 / (1024 * 1024)
        mem += mb
        tex_files.append(dict(file=fn, slot=m['slot'], kind=key, width=w, height=h, uncompressed_rgba8_mib=round(w * h * 4 / 1048576.0, 2),
                              gpu_compressed_estimate_mib=round(mb, 2)))
report = dict(schema='morphrig.material_and_lod_report/1',
              lods=lod_rep,
              lod_method='LOD1/LOD2: collapse decimation of everything except the head skin, which keeps its topology so all morph targets '
                         'exist on every LOD; skin weights limited to 8 influences',
              material_slots=[dict(index=i, name=s.name, shading=texgen.SHADING.get(s.name)) for i, s in enumerate(lods[0].material_slots)],
              textures=tex_files, texture_max_dimension=max(t['width'] for t in tex_files),
              texture_memory=dict(gpu_compressed_estimate_mib=round(mem, 1),
                                  uncompressed_rgba8_mib=round(sum(t['uncompressed_rgba8_mib'] for t in tex_files), 1),
                                  note='estimate for BC1 (base colour, ORM), BC5 (normal), BC3 (mask) with full mip chains; '
                                       'the Unreal import report lists the formats that were actually cooked'),
              deform_bone_count=len(sk.data.bones), control_rig_bone_count=len(rg.data.bones),
              morph_target_count=len(facedefs.MORPHS), height_m=round(float(max(v.co.z for v in lods[0].data.vertices)), 4),
              uv=dict(sets=1, stats=info['uv_stats']),
              team_variants=tex_doc['team_variants'])
docsgen.write_json(os.path.join(DOCS, 'material_and_lod_report.json'), report)
log('documents written; texture memory estimate %.1f MiB' % mem)

# ------------------------------------------------------------------------------------------------ prop static meshes
# prop static meshes: geometry rigid to a prop bone, stored upright in the prop's own frame (bone Y -> +Z, bone X -> +X)
me0 = lods[0].data


def prop_mesh(name, bone):
    gi = lods[0].vertex_groups[bone].index
    vmask = np.zeros(len(me0.vertices), dtype=bool)
    for v in me0.vertices:
        for g in v.groups:
            if g.group == gi and g.weight > 0.99:
                vmask[v.index] = True
    d = lods[0].copy()
    d.data = me0.copy()
    d.name = name
    d.data.name = name
    C_PROPS.objects.link(d)
    d.animation_data_clear()
    bpy.ops.object.select_all(action='DESELECT')
    d.select_set(True)
    bpy.context.view_layer.objects.active = d
    if d.data.shape_keys:
        d.data.shape_keys.animation_data_clear()
        d.shape_key_clear()
    for mod in list(d.modifiers):
        d.modifiers.remove(mod)
    d.parent = None
    d.vertex_groups.clear()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    d.data.vertices.foreach_set('select', ~vmask)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')
    bpy.ops.object.mode_set(mode='OBJECT')
    Mb = Matrix(np.array(skel.bone_matrix(bone)).tolist())
    up = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))     # bone (x, y, z) -> object (x, -z, y)
    d.data.transform(up @ Mb.inverted())
    d.matrix_world = Matrix.Identity(4)
    return d


props = [prop_mesh('SM_Beacon', 'prop_beacon'), prop_mesh('SM_PowerCell', 'prop_cell')]
for p in props:
    p.hide_render = True
    p.hide_viewport = True
log('props', [(p.name, len(p.data.vertices)) for p in props])


# ------------------------------------------------------------------------------------------------ neutral stage (lights, camera)
C_STAGE = collection('Stage')


def stage_sun(name, direction, strength, color=(1.0, 1.0, 1.0), angle=0.25):
    d = bpy.data.lights.new(name, 'SUN')
    d.energy, d.color, d.angle = strength, color, angle
    o = bpy.data.objects.new(name, d)
    C_STAGE.objects.link(o)
    o.rotation_euler = Vector(direction).normalized().to_track_quat('-Z', 'Y').to_euler()
    return o


stage_sun('Key', (-0.5, 0.8, -0.75), 2.6, (1.0, 0.97, 0.94))
stage_sun('Fill', (0.9, 0.5, -0.3), 0.9, (0.85, 0.92, 1.0), 0.6)
stage_sun('Rim', (0.3, -0.9, -0.5), 1.8, (0.8, 0.9, 1.0))
cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
C_STAGE.objects.link(cam)
cam.location = (2.6, -4.6, 1.45)
cam.rotation_euler = (Vector((0.0, 0.0, 0.92)) - Vector(cam.location)).normalized().to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 70
sc.camera = cam
world = sc.world or bpy.data.worlds.new('World')
sc.world = world
world.use_nodes = True
bgn = world.node_tree.nodes.get('Background')
if bgn is not None:
    bgn.inputs[0].default_value = (0.20, 0.22, 0.26, 1.0)
    bgn.inputs[1].default_value = 0.9
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        pass
sc.render.resolution_x, sc.render.resolution_y = 1080, 1350
try:
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].shading.type = 'MATERIAL'
except Exception:
    pass

# ------------------------------------------------------------------------------------------------ save the editable file
rigmod.reset_pose(rg)
if 'idle_relaxed' in bpy.data.actions:
    animio.assign(rg, bpy.data.actions['idle_relaxed'])
sc.frame_start, sc.frame_end = 0, 120
sc.frame_set(0)
bpy.context.view_layer.objects.active = rg
for o in sc.objects:
    o.select_set(False)
rg.select_set(True)
sk.hide_viewport = False
sk.hide_set(True)
proxy.hide_set(True)
if not opt('--no-blend'):
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, relative_remap=True)
    materials.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    log('saved', BLEND, '%.1f MiB' % (os.path.getsize(BLEND) / 1048576.0))
if opt('--no-export'):
    log('done (no export)')
    sys.exit(0)

# ------------------------------------------------------------------------------------------------ export (in-memory centimetre copy)
rigmod.set_follow(sk, False)
if rg.animation_data:
    rg.animation_data.action = None
rigmod.reset_pose(rg)
acts = [a for (a, s, k) in baked.values()]
mrexport.to_centimetres(sk, lods + [proxy], acts)
for p in props:
    p.hide_viewport = False
    p.hide_set(False)
    p.data.transform(Matrix.Scale(100.0, 4))
armature.reset_pose(sk)
sk.animation_data_create()
sk.animation_data.action = None
for m in lods:
    m.hide_viewport = False
    m.hide_set(False)
    if m.data.shape_keys and m.data.shape_keys.animation_data:
        for fc in list(m.data.shape_keys.animation_data.drivers):
            m.data.shape_keys.animation_data.drivers.remove(fc)
    for kb in m.data.shape_keys.key_blocks:
        kb.value = 0.0
if not only:
    for m, fn in zip(lods, ('Operative.fbx', 'Operative_LOD1.fbx', 'Operative_LOD2.fbx')):
        mrexport.export_fbx(os.path.join(EXP, fn), sk, [m], False)
    for p in props:
        bpy.ops.object.select_all(action='DESELECT')
        p.select_set(True)
        bpy.context.view_layer.objects.active = p
        bpy.ops.export_scene.fbx(filepath=os.path.join(EXP, 'props', p.name + '.fbx'), use_selection=True, global_scale=1.0,
                                 apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', object_types={'MESH'},
                                 mesh_smooth_type='FACE', use_tspace=False, bake_anim=False, axis_forward='-Z', axis_up='Y')
    log('meshes exported')
scene_name = sc.name
for k, cid in enumerate(ids):
    act, slot, kact = baked[cid]
    armature.reset_pose(sk)
    animio.assign(sk, act, slot)
    kd = proxy.data.shape_keys
    for kb in kd.key_blocks:
        kb.value = 0.0
    if kact is not None:
        animio.assign(kd, kact)
    elif kd.animation_data:
        kd.animation_data.action = None
    sc.frame_start = 0
    sc.frame_end = 1 if clips.BY_ID[cid]['form'] == 'pose' else clip_infos[cid]['frames']
    sc.name = cid
    mrexport.export_fbx(os.path.join(EXP, 'animations', cid + '.fbx'), sk, [proxy], True)
sc.name = scene_name
log('animations exported', len(ids))
log('DONE')

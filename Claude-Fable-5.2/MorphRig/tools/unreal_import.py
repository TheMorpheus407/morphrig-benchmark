"""MORPHRIG -> Unreal import (headless, idempotent).

Run through tools/ue_import.sh (which wipes the generated content folders first), or directly:

    UnrealEditor-Cmd <MorphRig.uproject> -run=pythonscript -script=<this file> -unattended -nosplash -nullrhi

Imports export/Operative.fbx (+LOD1/LOD2), the 96 clips, textures, audio and optional props, builds the
materials/instances, sockets and notifies from the delivery JSON files, copies those JSON files into
Content/MorphRigData for the runtime, and verifies the result against the manifests. Any mismatch makes
the script raise (non-zero commandlet exit code). A machine readable report is written to
unreal/Saved/MorphRigImportReport.json.
"""
import json
import os
import shutil
import struct
import zlib

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
EXPORT = os.path.join(ROOT, 'export')
DOCS = os.path.join(ROOT, 'docs')
AUDIO = os.path.join(ROOT, 'source', 'audio')
PROJECT_CONTENT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
PROJECT_SAVED = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
DATA_DIR = os.path.join(PROJECT_CONTENT, 'MorphRigData')

GAME = '/Game/Operative'
MESH_DIR = GAME + '/Mesh'
ANIM_DIR = GAME + '/Animations'
TEX_DIR = GAME + '/Textures'
MAT_DIR = GAME + '/Materials'
AUDIO_DIR = GAME + '/Audio'
PROP_DIR = GAME + '/Props'
SHOW_DIR = '/Game/Showcase'
MAP_PATH = '/Game/Maps/Showcase'

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AL = unreal.AnimationLibrary
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.MorphRigEditorLibrary

problems = []
report = {}


def log(*a):
    unreal.log('MORPHRIG_IMPORT ' + ' '.join(str(x) for x in a))


def fail(msg):
    problems.append(msg)
    unreal.log_error('MORPHRIG_IMPORT PROBLEM ' + msg)


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def sp(obj, **kw):
    for k, v in kw.items():
        obj.set_editor_property(k, v)
    return obj


def run_task(filename, dest, name, options=None, replace=True):
    t = unreal.AssetImportTask()
    sp(t, filename=filename, destination_path=dest, destination_name=name, replace_existing=replace,
       automated=True, save=True)
    if options is not None:
        t.set_editor_property('options', options)
    TOOLS.import_asset_tasks([t])
    return [unreal.load_asset(p) for p in t.get_editor_property('imported_object_paths')]


# ------------------------------------------------------------------------------------------ inputs
manifest = load_json(os.path.join(DOCS, 'animation_manifest.json'))
skeleton_doc = load_json(os.path.join(DOCS, 'skeleton_and_sockets.json'))
face_doc = load_json(os.path.join(DOCS, 'face_controls.json'))
tex_manifest_path = os.path.join(EXPORT, 'textures', 'texture_manifest.json')
tex_manifest = load_json(tex_manifest_path)
placeholder = bool(manifest.get('placeholder')) or bool(skeleton_doc.get('placeholder')) or bool(tex_manifest.get('placeholder'))
report['placeholder_inputs'] = placeholder
if placeholder:
    unreal.log_warning('MORPHRIG_IMPORT inputs are flagged placeholder=true')

for d in (GAME, SHOW_DIR):
    if EAL.does_directory_exist(d) and EAL.list_assets(d, True, False):
        log('removing existing', d)
        EAL.delete_directory(d)
        if EAL.does_directory_exist(d) and EAL.list_assets(d, True, False):
            raise RuntimeError('Stale assets remain in %s. Delete the folder on disk (tools/ue_import.sh does this) and re-run.' % d)

# ------------------------------------------------------------------------------------------ runtime data copies
os.makedirs(DATA_DIR, exist_ok=True)
for src in (os.path.join(DOCS, 'animation_manifest.json'), os.path.join(DOCS, 'skeleton_and_sockets.json'),
            os.path.join(DOCS, 'face_controls.json'), os.path.join(AUDIO, 'dialogue_alignment.json'),
            os.path.join(AUDIO, 'dialogue.txt'), tex_manifest_path):
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(DATA_DIR, os.path.basename(src)))
    else:
        fail('missing input file ' + src)


# ------------------------------------------------------------------------------------------ skeletal mesh
def mesh_options():
    o = unreal.FbxImportUI()
    sp(o, import_mesh=True, import_as_skeletal=True, import_animations=False, import_materials=False,
       import_textures=False, create_physics_asset=False, mesh_type_to_import=unreal.FBXImportType.FBXIT_SKELETAL_MESH,
       automated_import_should_detect_type=False)
    d = o.get_editor_property('skeletal_mesh_import_data')
    sp(d, import_morph_targets=True, convert_scene=True, convert_scene_unit=True, force_front_x_axis=False,
       use_t0_as_ref_pose=False, preserve_smoothing_groups=True, import_meshes_in_bone_hierarchy=False,
       import_mesh_lods=False, normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
       normal_generation_method=unreal.FBXNormalGenerationMethod.MIKK_T_SPACE)
    return o


objs = run_task(os.path.join(EXPORT, 'Operative.fbx'), MESH_DIR, 'SK_Operative', mesh_options())
sk = next((o for o in objs if isinstance(o, unreal.SkeletalMesh)), None)
if sk is None:
    raise RuntimeError('Operative.fbx did not produce a skeletal mesh: %s' % objs)
skel = sk.get_editor_property('skeleton')
log('mesh', sk.get_path_name(), 'skeleton', skel.get_path_name())

SMES = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
for li, fn in ((1, 'Operative_LOD1.fbx'), (2, 'Operative_LOD2.fbx')):
    p = os.path.join(EXPORT, fn)
    if not os.path.isfile(p):
        fail('missing LOD file ' + fn)
        continue
    res = SMES.import_lod(sk, li, p)
    log('import_lod', li, fn, '->', res)
    if res != li:
        fail('LOD %d import failed (%s)' % (li, res))
LIB.set_lod_screen_sizes(sk, [1.0, 0.35, 0.14])

# --- verification of the skeleton against the JSON
bone_names = [str(n) for n in LIB.get_ref_bone_names(sk)]
bone_pos = LIB.get_ref_bone_component_positions(sk)
doc_bones = skeleton_doc['bones']
if not bone_names or bone_names[0] != 'root':
    fail('root bone is %r, expected "root"' % (bone_names[:1],))
if len(bone_names) != skeleton_doc['bone_count']:
    fail('bone count %d != skeleton_and_sockets.json %d' % (len(bone_names), skeleton_doc['bone_count']))
missing = [b['name'] for b in doc_bones if b['name'] not in bone_names]
extra = [b for b in bone_names if b not in [d['name'] for d in doc_bones]]
if missing or extra:
    fail('bone name mismatch: missing %s extra %s' % (missing, extra))
max_err = 0.0
for b in doc_bones:
    if b['name'] in bone_names:
        p = bone_pos[bone_names.index(b['name'])]
        e = ((p.x - b['unreal_ref_position_cm'][0]) ** 2 + (p.y - b['unreal_ref_position_cm'][1]) ** 2 +
             (p.z - b['unreal_ref_position_cm'][2]) ** 2) ** 0.5
        max_err = max(max_err, e)
if max_err > 0.05:
    fail('ref pose differs from skeleton_and_sockets.json by up to %.3f cm' % max_err)
bounds = sk.get_bounds()
top = bounds.origin.z + bounds.box_extent.z
bottom = bounds.origin.z - bounds.box_extent.z
head_z = bone_pos[bone_names.index('head')].z if 'head' in bone_names else 0.0
report['mesh'] = dict(bounds_bottom_cm=round(bottom, 2), bounds_top_cm=round(top, 2), head_joint_z_cm=round(head_z, 2),
                      bone_count=len(bone_names), ref_pose_max_error_cm=round(max_err, 4))
if not placeholder:
    # 180 cm standing height (protruding accessories may add a little); no import-scale repair is applied anywhere
    if not (175.0 <= top <= 195.0):
        fail('mesh top is at %.1f cm, expected about 180 cm' % top)
    elif abs(top - 180.0) > 3.0:
        unreal.log_warning('MORPHRIG_IMPORT mesh top is at %.1f cm (180 cm nominal; accessories may protrude)' % top)
    if abs(bottom) > 1.5:
        fail('mesh bottom is at %.2f cm, expected 0' % bottom)
elif not (150.0 < top < 190.0):
    fail('placeholder mesh top %.1f cm is implausible' % top)

# --- morph targets
morphs = sorted(str(n) for n in sk.get_all_morph_target_names())
want = sorted(face_doc['morph_targets'])
miss_m = [m for m in want if m not in morphs]
if miss_m:
    fail('missing morph targets: %s' % miss_m)
report['morph_targets'] = dict(count=len(morphs), names=morphs, missing=miss_m, extra=[m for m in morphs if m not in want])
LIB.mark_morph_curves(sk, [unreal.Name(m) for m in morphs])
# sanity of the morph data itself: a facial morph that moves a vertex by more than MORPH_MAX_DELTA_CM is a broken export
MORPH_MAX_DELTA_CM = 12.0
morph_stats = []
bad_morphs = []
disabled_morphs = []     # runtime does not drive these (only ever non-empty for placeholder data, final data fails instead)
for m in morphs:
    d = LIB.get_morph_target_max_delta(sk, m, 0)
    n = LIB.get_morph_target_vertex_count(sk, m, 0)
    morph_stats.append(dict(name=m, max_delta_cm=round(d, 4), vertices=n))
    if n <= 0 or d <= 1e-4:
        bad_morphs.append('%s is empty' % m)
    elif d > MORPH_MAX_DELTA_CM:
        bad_morphs.append('%s moves vertices by %.1f cm' % (m, d))
        disabled_morphs.append(m)
report['morph_targets']['stats'] = morph_stats
report['morph_targets']['disabled'] = disabled_morphs
# how many morph targets carry data in each LOD (0 for a LOD means the face cannot animate there)
morphs_per_lod = []
for li in range(SMES.get_lod_count(sk)):
    morphs_per_lod.append(sum(1 for m in morphs if LIB.get_morph_target_vertex_count(sk, m, li) > 0))
report['morph_targets']['with_data_per_lod'] = morphs_per_lod
if not placeholder and len(morphs_per_lod) > 1 and morphs_per_lod[1] < len(want):
    unreal.log_warning('MORPHRIG_IMPORT LOD1 carries only %d of %d morph targets' % (morphs_per_lod[1], len(want)))
report['morph_targets']['implausible'] = bad_morphs
if bad_morphs:
    msg = 'implausible morph targets (limit %.0f cm): %s' % (MORPH_MAX_DELTA_CM, '; '.join(bad_morphs[:8]) + (' ...' if len(bad_morphs) > 8 else ''))
    if placeholder:
        unreal.log_warning('MORPHRIG_IMPORT (placeholder data, not fatal) ' + msg)
    else:
        fail(msg)

# --- sockets
LIB.remove_all_sockets(sk)
sock_err = 0.0
for s in skeleton_doc['sockets']:
    e = LIB.add_or_update_socket(sk, s['name'], s['bone'], unreal.Vector(*s['unreal_position_cm']),
                                 unreal.Vector(*s['unreal_forward']), unreal.Vector(*s['unreal_up']))
    if e < 0:
        fail('socket %s could not be created on bone %s' % (s['name'], s['bone']))
    sock_err = max(sock_err, e)
if sock_err > 0.01:
    fail('socket placement error %.4f cm' % sock_err)
report['sockets'] = dict(count=len(skeleton_doc['sockets']), max_error_cm=round(sock_err, 5),
                         names=[s['name'] for s in skeleton_doc['sockets']])

# --- LOD statistics
lods = []
for li in range(SMES.get_lod_count(sk)):
    lods.append(dict(lod=li, triangles=LIB.get_lod_triangle_count(sk, li), vertices=SMES.get_num_verts(sk, li),
                     sections=SMES.get_num_sections(sk, li), max_bone_influences=LIB.get_lod_max_bone_influences(sk, li)))
report['lods'] = lods
limits = [80000, 40000, 20000]
if len(lods) != 3:
    fail('expected 3 LODs, found %d' % len(lods))
for l, lim in zip(lods, limits):
    if l['triangles'] > lim:
        fail('LOD%d has %d triangles (limit %d)' % (l['lod'], l['triangles'], lim))
    if l['max_bone_influences'] > 8:
        fail('LOD%d uses %d bone influences (limit 8)' % (l['lod'], l['max_bone_influences']))
if len(lods) == 3 and not (lods[0]['triangles'] > lods[1]['triangles'] > lods[2]['triangles']):
    fail('LOD triangle counts are not strictly decreasing: %s' % [l['triangles'] for l in lods])


# ------------------------------------------------------------------------------------------ animations
def anim_options():
    o = unreal.FbxImportUI()
    sp(o, import_mesh=False, import_as_skeletal=False, import_animations=True, import_materials=False,
       import_textures=False, skeleton=skel, mesh_type_to_import=unreal.FBXImportType.FBXIT_ANIMATION,
       automated_import_should_detect_type=False)
    d = o.get_editor_property('anim_sequence_import_data')
    sp(d, import_bone_tracks=True, import_custom_attribute=True,
       animation_length=unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, remove_redundant_keys=False,
       convert_scene=True, convert_scene_unit=True, use_default_sample_rate=False, custom_sample_rate=30,
       snap_to_closest_frame_boundary=True, do_not_import_curve_with_zero=True, delete_existing_morph_target_curves=True)
    return o


anim_report = []
unknown_curves = {}
fps = float(manifest['fps'])
for c in manifest['clips']:
    cid = c['id']
    src = os.path.join(ROOT, c['export_file'])
    if not os.path.isfile(src):
        fail('missing clip file ' + c['export_file'])
        continue
    objs = run_task(src, ANIM_DIR, cid, anim_options())
    anim = next((o for o in objs if isinstance(o, unreal.AnimSequence)), None)
    if anim is None:
        anim = unreal.load_asset('%s/%s' % (ANIM_DIR, cid))
    if anim is None or not isinstance(anim, unreal.AnimSequence):
        fail('clip %s did not import as an AnimSequence' % cid)
        continue
    length = AL.get_sequence_length(anim)
    if abs(length - c['duration']) > 1.5e-3:
        fail('clip %s length %.5f != manifest %.5f' % (cid, length, c['duration']))
    sp(anim, enable_root_motion=(c['root_movement'] == 'root_motion'),
       root_motion_root_lock=unreal.RootMotionRootLock.REF_POSE, interpolation=unreal.AnimInterpolationType.LINEAR)
    try:
        anim.set_editor_property('loop', bool(c['loop']))
    except Exception:
        pass
    # markers -> notifies
    AL.remove_all_animation_notify_tracks(anim)
    if c['events']:
        AL.add_animation_notify_track(anim, 'MorphRig')
        for e in c['events']:
            t = min(max(float(e['time']), 0.0), max(0.0, length - 1e-4))
            n = AL.add_animation_notify_event(anim, 'MorphRig', t, unreal.MorphEventNotify)
            if n is None:
                fail('could not add notify %s to %s' % (e['name'], cid))
            else:
                n.set_editor_property('event_name', e['name'])
    curves = [str(x) for x in AL.get_animation_curve_names(anim, unreal.RawCurveTrackTypes.RCT_FLOAT)]
    stray = [x for x in curves if x not in want]
    if stray:
        unknown_curves.setdefault(cid, stray)
    notifies = [str(x) for x in LIB.describe_notifies(anim)]
    if len(notifies) != len(c['events']):
        fail('clip %s has %d notifies, manifest lists %d' % (cid, len(notifies), len(c['events'])))
    EAL.save_loaded_asset(anim, False)
    anim_report.append(dict(id=cid, length=round(length, 6), frames=AL.get_num_frames(anim), curves=len(curves), notifies=len(notifies),
                            root_motion=bool(anim.get_editor_property('enable_root_motion'))))
report['animations'] = dict(count=len(anim_report), clips=anim_report, curves_not_matching_a_morph_target=unknown_curves)
if unknown_curves:
    unreal.log_warning('MORPHRIG_IMPORT clips with curves that match no morph target: %s' % json.dumps(unknown_curves)[:600])
if len(anim_report) != 96:
    fail('imported %d clips, expected 96' % len(anim_report))
# root motion displacement check
opt = unreal.AnimPoseEvaluationOptions()
for c in manifest['clips']:
    if c['root_movement'] != 'root_motion':
        continue
    anim = unreal.load_asset('%s/%s' % (ANIM_DIR, c['id']))
    if anim is None:
        continue
    anim.set_editor_property('enable_root_motion', False)
    p0 = unreal.AnimPoseExtensions.get_bone_pose(unreal.AnimPoseExtensions.get_anim_pose_at_time(anim, 0.0, opt), 'root', unreal.AnimPoseSpaces.WORLD).translation
    p1 = unreal.AnimPoseExtensions.get_bone_pose(unreal.AnimPoseExtensions.get_anim_pose_at_time(anim, c['duration'], opt), 'root', unreal.AnimPoseSpaces.WORLD).translation
    anim.set_editor_property('enable_root_motion', True)
    EAL.save_loaded_asset(anim, False)
    d = [p1.x - p0.x, p1.y - p0.y, p1.z - p0.z]
    w = c['root_motion']['displacement_cm']
    if max(abs(a - b) for a, b in zip(d, w)) > 0.5:
        fail('clip %s root displacement %s != manifest %s' % (c['id'], [round(x, 2) for x in d], w))
    log('root motion', c['id'], [round(x, 2) for x in d])


# ------------------------------------------------------------------------------------------ textures
def write_png(path, w, h, rgba):
    raw = b''.join(b'\x00' + bytes(rgba) * w for _ in range(h))

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
                chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def import_texture(path, name, kind):
    objs = run_task(path, TEX_DIR, name)
    tex = next((o for o in objs if isinstance(o, unreal.Texture2D)), None) or unreal.load_asset('%s/%s' % (TEX_DIR, name))
    if tex is None:
        fail('texture %s did not import' % path)
        return None
    if kind == 'normal':
        sp(tex, compression_settings=unreal.TextureCompressionSettings.TC_NORMALMAP, srgb=False, flip_green_channel=True)
    elif kind == 'linear':
        sp(tex, compression_settings=unreal.TextureCompressionSettings.TC_MASKS, srgb=False)
    else:
        sp(tex, compression_settings=unreal.TextureCompressionSettings.TC_DEFAULT, srgb=True)
    EAL.save_loaded_asset(tex, False)
    return tex


tmp_dir = os.path.join(PROJECT_SAVED, 'MorphRigImportTmp')
os.makedirs(tmp_dir, exist_ok=True)
write_png(os.path.join(tmp_dir, 'T_MR_Black.png'), 4, 4, (0, 0, 0, 0))
write_png(os.path.join(tmp_dir, 'T_MR_White.png'), 4, 4, (255, 255, 255, 255))
write_png(os.path.join(tmp_dir, 'T_MR_FlatNormal.png'), 4, 4, (128, 128, 255, 255))
write_png(os.path.join(tmp_dir, 'T_MR_ORM.png'), 4, 4, (255, 160, 0, 255))
T_BLACK = import_texture(os.path.join(tmp_dir, 'T_MR_Black.png'), 'T_MR_Black', 'linear')
T_WHITE = import_texture(os.path.join(tmp_dir, 'T_MR_White.png'), 'T_MR_White', 'color')
T_FLATN = import_texture(os.path.join(tmp_dir, 'T_MR_FlatNormal.png'), 'T_MR_FlatNormal', 'normal')
T_ORM = import_texture(os.path.join(tmp_dir, 'T_MR_ORM.png'), 'T_MR_ORM', 'linear')

tex_report = []
slot_textures = {}
for m in tex_manifest['materials']:
    entry = {}
    for key, kind in (('base_color', 'color'), ('normal', 'normal'), ('orm', 'linear'), ('mask', 'linear'), ('emissive', 'color')):
        fn = m.get(key)
        if not fn:
            continue
        p = os.path.join(EXPORT, 'textures', fn)
        if not os.path.isfile(p):
            fail('texture file missing: ' + fn)
            continue
        tex = import_texture(p, os.path.splitext(fn)[0], kind)
        if tex is not None:
            entry[key] = tex
            w, h = tex.blueprint_get_size_x(), tex.blueprint_get_size_y()
            if max(w, h) > 4096:
                fail('texture %s is %dx%d (> 4096)' % (fn, w, h))
            # GPU memory estimate for the desktop formats these settings cook to, full mip chain (x 4/3):
            # normal map -> BC5 (1 byte/pixel); colour / packed masks -> BC1 (0.5 byte/pixel) without alpha, BC3 (1 byte/pixel) with alpha
            try:
                alpha = bool(tex.has_alpha_channel())
            except Exception:
                alpha = (key == 'mask')
            bpp = 1.0 if (kind == 'normal' or alpha) else 0.5
            fmt = 'BC5' if kind == 'normal' else ('BC3' if alpha else 'BC1')
            tex_report.append(dict(file=fn, slot=m['slot'], kind=key, width=w, height=h, gpu_format_estimate=fmt,
                                   gpu_bytes_estimate=int(round(w * h * bpp * 4.0 / 3.0))))
    slot_textures[m['slot']] = (m, entry)
report['textures'] = tex_report
report['texture_memory_estimate_mb'] = round(sum(t['gpu_bytes_estimate'] for t in tex_report) / (1024.0 * 1024.0), 2)


# ------------------------------------------------------------------------------------------ materials
def new_material(name, folder=MAT_DIR):
    path = '%s/%s' % (folder, name)
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    return TOOLS.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def E(mat, cls, x, y, **props):
    e = MEL.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def P_tex(mat, name, tex, sampler, x, y):
    return E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=tex, sampler_type=sampler)


def P_scalar(mat, name, value, x, y):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)


def P_vector(mat, name, rgba, x, y):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba))


def custom(mat, code, out_type, inputs, x, y, desc=''):
    c = E(mat, unreal.MaterialExpressionCustom, x, y, code=code, output_type=out_type, description=desc or 'MR')
    ins = []
    for name, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property('input_name', name)
        ins.append(ci)
    c.set_editor_property('inputs', ins)
    for name, (src, out) in inputs:
        if not MEL.connect_material_expressions(src, out, c, name):
            fail('material %s: could not connect custom input %s' % (mat.get_name(), name))
    return c


def finish(mat, skeletal=False):
    if skeletal:
        for usage in (unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS):
            if hasattr(MEL, 'set_base_material_usage'):
                MEL.set_base_material_usage(mat, usage)
            else:
                MEL.set_material_usage(mat, usage)
    MEL.layout_material_expressions(mat)
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat, False)
    return mat


CM = unreal.CustomMaterialOutputType
MP = unreal.MaterialProperty
ST = unreal.MaterialSamplerType


def build_character_master(name, skin=False):
    mat = new_material(name)
    sp(mat, blend_mode=unreal.BlendMode.BLEND_MASKED, two_sided=False)
    # skin: Default Lit like everything else. (A subsurface shading model with a red scatter colour washed the painted
    # detail out - brows, stubble, lips, lash line - and brightened the shadow side; the base colour has to read as authored.)
    base = P_tex(mat, 'BaseColorTex', T_WHITE, ST.SAMPLERTYPE_COLOR, -1200, -400)
    nrm = P_tex(mat, 'NormalTex', T_FLATN, ST.SAMPLERTYPE_NORMAL, -1200, -150)
    orm = P_tex(mat, 'ORMTex', T_ORM, ST.SAMPLERTYPE_MASKS, -1200, 100)
    msk = P_tex(mat, 'MaskTex', T_BLACK, ST.SAMPLERTYPE_MASKS, -1200, 350)
    team = P_vector(mat, 'TeamColor', (0.0, 0.62, 1.0, 1.0), -1200, 600)
    icon = P_scalar(mat, 'IconSelect', 0.0, -1200, 780)
    acc_e = P_scalar(mat, 'AccentEmissive', 3.0, -1200, 860)
    icon_e = P_scalar(mat, 'IconEmissive', 1.5, -1200, 940)
    flash = P_scalar(mat, 'HitFlash', 0.0, -1200, 1020)
    dissolve = P_scalar(mat, 'Dissolve', 0.0, -1200, 1100)
    rough_scale = P_scalar(mat, 'RoughnessScale', 1.0, -1200, 1180)
    uv = E(mat, unreal.MaterialExpressionTextureCoordinate, -1200, 1260)
    c_base = custom(mat, 'float icon = lerp(Mask.g, Mask.b, saturate(IconSelect));\nfloat a = saturate(Mask.r + icon);\nreturn lerp(Base, TeamColor, a);',
                    CM.CMOT_FLOAT3, [('Base', (base, 'RGB')), ('Mask', (msk, 'RGBA')), ('TeamColor', (team, '')), ('IconSelect', (icon, ''))], -700, -400, 'BaseColor')
    c_noise = custom(mat, 'float2 p = floor(UV * 240.0);\nreturn frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);',
                     CM.CMOT_FLOAT1, [('UV', (uv, ''))], -700, 1200, 'DissolveNoise')
    c_emis = custom(mat, 'float icon = lerp(Mask.g, Mask.b, saturate(IconSelect));\n'
                         'float edge = saturate(1.0 - abs(Noise - Dissolve) * 12.0) * step(0.001, Dissolve) * step(Dissolve, 0.999);\n'
                         'return TeamColor * (Mask.a * AccentEmissive + icon * IconEmissive + edge * 12.0) + HitFlash * float3(1.0, 0.85, 0.7);',
                    CM.CMOT_FLOAT3, [('Mask', (msk, 'RGBA')), ('TeamColor', (team, '')), ('IconSelect', (icon, '')), ('AccentEmissive', (acc_e, '')),
                                     ('IconEmissive', (icon_e, '')), ('HitFlash', (flash, '')), ('Noise', (c_noise, '')), ('Dissolve', (dissolve, ''))],
                    -700, 300, 'Emissive')
    c_mask = custom(mat, 'return (Noise >= Dissolve) ? 1.0 : 0.0;', CM.CMOT_FLOAT1,
                    [('Noise', (c_noise, '')), ('Dissolve', (dissolve, ''))], -400, 1200, 'OpacityMask')
    c_rough = custom(mat, 'return saturate(R * Scale);', CM.CMOT_FLOAT1, [('R', (orm, 'G')), ('Scale', (rough_scale, ''))], -700, 100, 'Roughness')
    MEL.connect_material_property(c_base, '', MP.MP_BASE_COLOR)
    MEL.connect_material_property(nrm, 'RGB', MP.MP_NORMAL)
    MEL.connect_material_property(orm, 'R', MP.MP_AMBIENT_OCCLUSION)
    MEL.connect_material_property(c_rough, '', MP.MP_ROUGHNESS)
    MEL.connect_material_property(orm, 'B', MP.MP_METALLIC)
    MEL.connect_material_property(c_emis, '', MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(c_mask, '', MP.MP_OPACITY_MASK)
    return finish(mat, skeletal=True)


def build_unlit(name, code, out_inputs_builder, skeletal=False, **matprops):
    mat = new_material(name)
    sp(mat, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, **matprops)
    out_inputs_builder(mat)
    return finish(mat, skeletal=skeletal)


def build_debug_materials():
    # wireframe
    m = new_material('M_Debug_Wireframe')
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, wireframe=True, two_sided=True)
    c = P_vector(m, 'Color', (0.05, 0.9, 0.55, 1.0), -400, 0)
    MEL.connect_material_property(c, '', MP.MP_EMISSIVE_COLOR)
    finish(m, True)
    # world normal visualisation (uses the character normal map of the slot it replaces when instanced)
    m = new_material('M_Debug_Normals')
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT)
    nrm = P_tex(m, 'NormalTex', T_FLATN, ST.SAMPLERTYPE_NORMAL, -900, 0)
    tw = E(m, unreal.MaterialExpressionTransform, -600, 0, transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
           transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    MEL.connect_material_expressions(nrm, 'RGB', tw, '')
    c = custom(m, 'return N * 0.5 + 0.5;', CM.CMOT_FLOAT3, [('N', (tw, ''))], -300, 0, 'NormalColor')
    MEL.connect_material_property(c, '', MP.MP_EMISSIVE_COLOR)
    finish(m, True)
    # clay (untextured lit)
    m = new_material('M_Debug_Clay')
    c = P_vector(m, 'Color', (0.52, 0.52, 0.5, 1.0), -400, 0)
    r = P_scalar(m, 'Roughness', 0.62, -400, 200)
    MEL.connect_material_property(c, '', MP.MP_BASE_COLOR)
    MEL.connect_material_property(r, '', MP.MP_ROUGHNESS)
    finish(m, True)
    # inverted hull outline (overlay material)
    m = new_material('M_Outline')
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True, blend_mode=unreal.BlendMode.BLEND_MASKED)
    col = P_vector(m, 'OutlineColor', (0.0, 0.62, 1.0, 1.0), -900, 0)
    thick = P_scalar(m, 'Thickness', 0.9, -900, 200)
    dash = P_scalar(m, 'Dashed', 0.0, -900, 300)
    emis = P_scalar(m, 'Brightness', 4.0, -900, 400)
    vn = E(m, unreal.MaterialExpressionVertexNormalWS, -900, 500)
    wp = E(m, unreal.MaterialExpressionWorldPosition, -900, 600)
    ts = E(m, unreal.MaterialExpressionTwoSidedSign, -900, 700)
    wpo = custom(m, 'return N * T;', CM.CMOT_FLOAT3, [('N', (vn, '')), ('T', (thick, ''))], -500, 500, 'WPO')
    msk = custom(m, 'float back = (Sign < 0.0) ? 1.0 : 0.0;\nfloat d = (Dashed < 0.5) ? 1.0 : step(0.45, frac(WP.z * 0.11));\nreturn back * d;',
                 CM.CMOT_FLOAT1, [('Sign', (ts, '')), ('Dashed', (dash, '')), ('WP', (wp, ''))], -500, 700, 'Mask')
    em = custom(m, 'return C * B;', CM.CMOT_FLOAT3, [('C', (col, '')), ('B', (emis, ''))], -500, 0, 'Emissive')
    MEL.connect_material_property(em, '', MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(wpo, '', MP.MP_WORLD_POSITION_OFFSET)
    MEL.connect_material_property(msk, '', MP.MP_OPACITY_MASK)
    finish(m, True)


def build_showcase_materials():
    # generic lit colour
    m = new_material('M_Solid', SHOW_DIR)
    c = P_vector(m, 'Color', (0.5, 0.5, 0.5, 1.0), -400, 0)
    r = P_scalar(m, 'Roughness', 0.7, -400, 200)
    me = P_scalar(m, 'Metallic', 0.0, -400, 300)
    ev = P_vector(m, 'Emissive', (0.0, 0.0, 0.0, 1.0), -400, 400)
    MEL.connect_material_property(c, '', MP.MP_BASE_COLOR)
    MEL.connect_material_property(r, '', MP.MP_ROUGHNESS)
    MEL.connect_material_property(me, '', MP.MP_METALLIC)
    MEL.connect_material_property(ev, '', MP.MP_EMISSIVE_COLOR)
    finish(m, True)
    # metre grid floor
    m = new_material('M_Grid', SHOW_DIR)
    a = P_vector(m, 'ColorA', (0.21, 0.215, 0.225, 1.0), -900, 0)
    ln = P_vector(m, 'LineColor', (0.36, 0.37, 0.39, 1.0), -900, 200)
    wp = E(m, unreal.MaterialExpressionWorldPosition, -900, 400)
    r = P_scalar(m, 'Roughness', 0.82, -900, 600)
    g = custom(m, 'float2 p = WP.xy / 100.0;\nfloat2 g1 = abs(frac(p - 0.5) - 0.5) / max(fwidth(p), 1e-5);\nfloat l1 = 1.0 - saturate(min(g1.x, g1.y) - 0.5);\n'
                  'float2 q = p / 5.0;\nfloat2 g5 = abs(frac(q - 0.5) - 0.5) / max(fwidth(q), 1e-5);\nfloat l5 = 1.0 - saturate(min(g5.x, g5.y) - 1.2);\n'
                  'return lerp(A, L, saturate(l1 * 0.45 + l5 * 0.9));',
               CM.CMOT_FLOAT3, [('WP', (wp, '')), ('A', (a, '')), ('L', (ln, ''))], -500, 0, 'Grid')
    MEL.connect_material_property(g, '', MP.MP_BASE_COLOR)
    MEL.connect_material_property(r, '', MP.MP_ROUGHNESS)
    finish(m)
    # backdrop dome: unlit vertical gradient, visible from inside
    m = new_material('M_Backdrop', SHOW_DIR)
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    lo = P_vector(m, 'Horizon', (0.035, 0.038, 0.045, 1.0), -900, 0)
    hi = P_vector(m, 'Zenith', (0.012, 0.013, 0.016, 1.0), -900, 200)
    wp = E(m, unreal.MaterialExpressionWorldPosition, -900, 400)
    g = custom(m, 'float t = saturate(WP.z / 6000.0);\nreturn lerp(A, B, sqrt(t));', CM.CMOT_FLOAT3, [('WP', (wp, '')), ('A', (lo, '')), ('B', (hi, ''))], -500, 0, 'Gradient')
    MEL.connect_material_property(g, '', MP.MP_EMISSIVE_COLOR)
    finish(m)
    # unlit translucent effect colour
    m = new_material('M_FX', SHOW_DIR)
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)
    c = P_vector(m, 'Color', (0.2, 0.8, 1.0, 1.0), -600, 0)
    i = P_scalar(m, 'Intensity', 6.0, -600, 200)
    o = P_scalar(m, 'Opacity', 0.6, -600, 300)
    em = custom(m, 'return C * I;', CM.CMOT_FLOAT3, [('C', (c, '')), ('I', (i, ''))], -300, 0, 'Emissive')
    MEL.connect_material_property(em, '', MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(o, '', MP.MP_OPACITY)
    finish(m, True)
    # team marker ring under the character: A = solid ring + chevron, B = segmented ring + bar
    m = new_material('M_TeamRing', SHOW_DIR)
    sp(m, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)
    c = P_vector(m, 'Color', (0.0, 0.62, 1.0, 1.0), -900, 0)
    st = P_scalar(m, 'Style', 0.0, -900, 200)
    i = P_scalar(m, 'Intensity', 3.0, -900, 300)
    uv = E(m, unreal.MaterialExpressionTextureCoordinate, -900, 400)
    sh = custom(m, 'float2 c = UV - 0.5;\nfloat r = length(c) * 2.0;\nfloat ang = atan2(c.y, c.x);\n'
                   'float ring = smoothstep(0.80, 0.83, r) * (1.0 - smoothstep(0.93, 0.96, r));\n'
                   'float seg = step(0.42, frac(ang / 6.2831853 * 10.0));\n'
                   'float chev = step(abs(c.x) * 1.6 + 0.31, c.y + 0.05) * step(c.y, 0.47) * step(0.335, c.y + abs(c.x) * 0.0) ;\n'
                   'float bar = step(abs(c.x), 0.13) * step(0.36, c.y) * step(c.y, 0.40);\n'
                   'float a = (Style < 0.5) ? max(ring, chev * step(r, 0.99)) : max(ring * seg, bar);\nreturn saturate(a);',
                CM.CMOT_FLOAT1, [('UV', (uv, '')), ('Style', (st, ''))], -500, 300, 'Shape')
    em = custom(m, 'return C * I;', CM.CMOT_FLOAT3, [('C', (c, '')), ('I', (i, ''))], -500, 0, 'Emissive')
    MEL.connect_material_property(em, '', MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(sh, '', MP.MP_OPACITY)
    finish(m)


M_CHAR = build_character_master('M_Operative', skin=False)
M_SKIN = build_character_master('M_OperativeSkin', skin=True)
build_debug_materials()
build_showcase_materials()


def new_instance(name, parent):
    path = '%s/%s' % (MAT_DIR, name)
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    mi = TOOLS.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    return mi


teams = tex_manifest.get('team_variants', {})
mat_report = []
slot_instances = {}
for slot, (m, texs) in slot_textures.items():
    short = slot[2:] if slot.startswith('M_') else slot
    parent = M_SKIN if m.get('shading') == 'skin' else M_CHAR
    mi = new_instance('MI_Operative_' + short, parent)
    for key, pname in (('base_color', 'BaseColorTex'), ('normal', 'NormalTex'), ('orm', 'ORMTex'), ('mask', 'MaskTex')):
        if key in texs:
            MEL.set_material_instance_texture_parameter_value(mi, pname, texs[key])
    if m.get('shading') == 'wet':
        MEL.set_material_instance_scalar_parameter_value(mi, 'RoughnessScale', 0.55)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi, False)
    variants = {}
    for tkey in ('A', 'B'):
        tv = teams.get(tkey, {})
        col = tv.get('color_linear', [0.0, 0.62, 1.0] if tkey == 'A' else [1.0, 0.36, 0.02])
        v = new_instance('MI_Operative_%s_Team%s' % (short, tkey), mi)
        MEL.set_material_instance_vector_parameter_value(v, 'TeamColor', unreal.LinearColor(col[0], col[1], col[2], 1.0))
        MEL.set_material_instance_scalar_parameter_value(v, 'IconSelect', 0.0 if tv.get('icon_channel', 'G' if tkey == 'A' else 'B') == 'G' else 1.0)
        MEL.update_material_instance(v)
        EAL.save_loaded_asset(v, False)
        variants[tkey] = v
    slot_instances[slot] = variants
    mat_report.append(dict(slot=slot, shading=m.get('shading'), instance=mi.get_path_name(),
                           team_a=variants['A'].get_path_name(), team_b=variants['B'].get_path_name(),
                           textures={k: t.get_name() for k, t in texs.items()}))

# assign by slot name (tolerant to missing / extra slots)
mats = list(sk.get_editor_property('materials'))
mesh_slots = []
for sm in mats:
    sname = str(sm.get_editor_property('material_slot_name'))
    mesh_slots.append(sname)
    key = next((k for k in slot_instances if k == sname or sname.startswith(k)), None)
    if key is None:
        unreal.log_warning('MORPHRIG_IMPORT mesh slot %s has no entry in texture_manifest.json; using M_Operative' % sname)
        sm.set_editor_property('material_interface', M_CHAR)
    else:
        sm.set_editor_property('material_interface', slot_instances[key]['A'])
sk.set_editor_property('materials', mats)
report['materials'] = dict(mesh_slots=mesh_slots, slot_count=len(mesh_slots), instances=mat_report)
if len(mesh_slots) > 8:
    fail('mesh has %d material slots (limit 8)' % len(mesh_slots))
if not placeholder:
    for want_slot in ('M_Skin', 'M_EyesMouth', 'M_Hair', 'M_Suit', 'M_Armor', 'M_Cyber'):
        if want_slot not in mesh_slots:
            fail('mesh is missing material slot ' + want_slot)
EAL.save_loaded_asset(sk, False)
EAL.save_loaded_asset(skel, False)

# ------------------------------------------------------------------------------------------ audio
wav = os.path.join(AUDIO, 'dialogue.wav')
if os.path.isfile(wav):
    objs = run_task(wav, AUDIO_DIR, 'dialogue')
    snd = next((o for o in objs if isinstance(o, unreal.SoundWave)), None)
    if snd is None:
        fail('dialogue.wav did not import as a SoundWave')
    else:
        report['audio'] = dict(asset=snd.get_path_name(), duration=round(snd.get_editor_property('duration'), 4))
        EAL.save_loaded_asset(snd, False)
else:
    fail('missing source/audio/dialogue.wav')

# ------------------------------------------------------------------------------------------ optional props
props = []
prop_dir = os.path.join(EXPORT, 'props')
if os.path.isdir(prop_dir):
    for fn in sorted(os.listdir(prop_dir)):
        if not fn.lower().endswith('.fbx'):
            continue
        o = unreal.FbxImportUI()
        sp(o, import_mesh=True, import_as_skeletal=False, import_animations=False, import_materials=False, import_textures=False,
           mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH, automated_import_should_detect_type=False)
        d = o.get_editor_property('static_mesh_import_data')
        sp(d, combine_meshes=True, convert_scene=True, convert_scene_unit=True, auto_generate_collision=True)
        objs = run_task(os.path.join(prop_dir, fn), PROP_DIR, os.path.splitext(fn)[0], o)
        sm = next((x for x in objs if isinstance(x, unreal.StaticMesh)), None)
        if sm is None:
            fail('prop %s did not import as a static mesh' % fn)
            continue
        smats = list(sm.get_editor_property('static_materials'))
        for stm in smats:
            sname = str(stm.get_editor_property('material_slot_name'))
            key = next((k for k in slot_instances if k == sname or sname.startswith(k)), None)
            stm.set_editor_property('material_interface', slot_instances[key]['A'] if key else M_CHAR)
        sm.set_editor_property('static_materials', smats)
        EAL.save_loaded_asset(sm, False)
        props.append(sm.get_path_name())
report['props'] = props

# ------------------------------------------------------------------------------------------ map
if not EAL.does_asset_exist(MAP_PATH):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.new_level(MAP_PATH)
    les.save_current_level()
    log('created map', MAP_PATH)

# ------------------------------------------------------------------------------------------ report
EAL.save_directory(GAME, False, True)
EAL.save_directory(SHOW_DIR, False, True)
report['problems'] = problems
os.makedirs(PROJECT_SAVED, exist_ok=True)
with open(os.path.join(PROJECT_SAVED, 'MorphRigImportReport.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=1)
shutil.copy2(os.path.join(PROJECT_SAVED, 'MorphRigImportReport.json'), os.path.join(DATA_DIR, 'import_report.json'))

log('================ SUMMARY ================')
log('placeholder inputs:', placeholder)
log('root bone:', bone_names[0] if bone_names else None, '| bones:', len(bone_names), '| ref pose max error cm:', round(max_err, 4))
log('mesh bounds z: %.2f .. %.2f cm' % (bottom, top))
log('LODs:', [(l['lod'], l['triangles'], l['vertices'], l['max_bone_influences']) for l in lods], '(lod, tris, verts, max influences)')
log('material slots:', mesh_slots)
log('morph targets:', len(morphs), 'missing:', miss_m, 'implausible:', len(bad_morphs), 'with data per LOD:', morphs_per_lod)
log('sockets:', len(skeleton_doc['sockets']), 'max error cm:', round(sock_err, 5))
log('animations:', len(anim_report), 'with curves:', sum(1 for a in anim_report if a['curves']), 'notifies total:', sum(a['notifies'] for a in anim_report))
log('textures:', len(tex_report), '| largest:', max([max(t['width'], t['height']) for t in tex_report] or [0]),
    '| GPU memory estimate MB (block compressed, with mips):', report['texture_memory_estimate_mb'], '| props:', len(props))
log('problems:', len(problems))
for p in problems:
    log('  PROBLEM', p)
if problems:
    raise RuntimeError('MORPHRIG import finished with %d problem(s)' % len(problems))
log('IMPORT OK')

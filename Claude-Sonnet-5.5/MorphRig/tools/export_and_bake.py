"""Bake the control-rig actions to the deformation skeleton and export everything for Unreal (reproducible, headless).

usage (from the MorphRig folder):
  blender -b source/Operative.blend -P tools/export_and_bake.py -- --out . [--only walk_f,idle_relaxed] [--no-clips] [--no-mesh]

Writes:  export/Operative.fbx (LOD0 + skeleton), export/Operative_LOD1.fbx, export/Operative_LOD2.fbx,
         export/props/*.fbx, export/animations/<id>.fbx (one baked clip per file, bones + morph curves),
         docs/animation_manifest.json, docs/skeleton_and_sockets.json
Conventions: Blender metres -> FBX centimetres (baked, unit scale 1), single 'root', 30 fps, Blender frame = 1 + clip frame.
"""
import json
import math
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'source', 'generators'))
import bpy
import numpy as np
from mathutils import Vector
import skeleton_def as S
import anim_lib as AL
import export_lib as EX
import clip_table as CT


def arg(name, default=None):
    if '--' in sys.argv:
        a = sys.argv[sys.argv.index('--') + 1:]
        if name in a:
            i = a.index(name)
            return a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return default


class FrameClip:
    def __init__(self, frames):
        self.frames = frames


def mesh_objects(names=('Operative_Body', 'Operative_Head', 'Operative_Eyes', 'Operative_Mouth', 'Operative_Hand_R', 'Operative_CyberArm_L',
                        'Operative_Boots', 'Operative_Gear', 'Operative_Braid', 'Operative_Cable', 'Operative_Hair')):
    return [bpy.data.objects[n] for n in names if n in bpy.data.objects]


def decimated(objs, arm_cm, name, ratio):
    ob = EX.assemble_mesh(objs, name, arm_cm, shape_key_from=None)
    md = ob.modifiers.new('Decimate', 'DECIMATE')
    md.decimate_type = 'COLLAPSE'
    md.ratio = ratio
    md.use_collapse_triangulate = False
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    # keep the armature modifier first: apply decimate only
    bpy.ops.object.modifier_apply(modifier='Decimate')
    return ob


def export_meshes(out_dir, arm_cm, report):
    objs = mesh_objects()
    head = bpy.data.objects['Operative_Head']
    lod0 = EX.assemble_mesh(objs, 'Operative_LOD0', arm_cm, shape_key_from=head)
    EX.fbx_export(os.path.join(out_dir, 'export', 'Operative.fbx'), [arm_cm, lod0], frame_range=(1, 2))
    tri = lambda o: sum(len(p.vertices) - 2 for p in o.data.polygons)
    report['lods'] = {'LOD0': {'triangles': tri(lod0), 'vertices': len(lod0.data.vertices), 'morph_targets': len(lod0.data.shape_keys.key_blocks) - 1 if lod0.data.shape_keys else 0}}
    for lod, ratio in (('LOD1', 0.5), ('LOD2', 0.22)):
        o = decimated(objs, arm_cm, f'Operative_{lod}', ratio)
        EX.fbx_export(os.path.join(out_dir, 'export', f'Operative_{lod}.fbx'), [arm_cm, o], frame_range=(1, 2))
        report['lods'][lod] = {'triangles': tri(o), 'vertices': len(o.data.vertices), 'decimate_ratio': ratio, 'morph_targets': 0}
        bpy.data.objects.remove(o)
    # skin statistics on LOD0
    mx = 0
    used = set()
    for v in lod0.data.vertices:
        ws = [g for g in v.groups if g.weight > 1e-4]
        mx = max(mx, len(ws))
        used.update(lod0.vertex_groups[g.group].name for g in ws)
    report['skin'] = {'max_influences_per_vertex': mx, 'deformation_bones_with_weights': len(used), 'total_bones': len(arm_cm.data.bones)}
    report['material_slots'] = [m.name for m in lod0.data.materials]
    per_mat = {}
    for p in lod0.data.polygons:
        nm = lod0.data.materials[p.material_index].name
        per_mat[nm] = per_mat.get(nm, 0) + len(p.vertices) - 2
    report['triangles_per_material'] = per_mat
    return lod0


def export_props(out_dir):
    props = {}
    for pname, fname in (('Operative_Prop_PowerCell', 'Operative_PowerCell'), ('Operative_Prop_Beacon', 'Operative_Beacon')):
        ob = bpy.data.objects.get(pname)
        if ob is None:
            continue
        me = ob.data.copy()
        me.transform(__import__('mathutils').Matrix.Scale(EX.SC, 4))
        cp = bpy.data.objects.new(fname, me)
        bpy.context.scene.collection.objects.link(cp)
        EX.fbx_export(os.path.join(out_dir, 'export', 'props', fname + '.fbx'), [cp], frame_range=(1, 2), object_types={'MESH'}, bake_anim=False)
        props[fname] = {'triangles': sum(len(p.vertices) - 2 for p in me.polygons), 'materials': [m.name for m in me.materials]}
        bpy.data.objects.remove(cp)
    return props


def read_face_curves(ctl, frames, morph_names):
    """Sample the ctl_face morph properties over the clip (after frame_set evaluation)."""
    pb = ctl.pose.bones['ctl_face']
    vals = {n: np.zeros(frames + 1) for n in morph_names}
    return vals


def export_clips(out_dir, ctl, skel, arm_cm, proxy, only=None, manifest=None):
    sc = bpy.context.scene
    table = {e['id']: e for e in CT.build_table()}
    outp = os.path.join(out_dir, 'export', 'animations')
    os.makedirs(outp, exist_ok=True)
    root_idx = [b.name for b in skel.data.bones].index('root')
    for cid, e in table.items():
        if only and cid not in only:
            continue
        act = bpy.data.actions.get('A_' + cid)
        if act is None:
            print('[export] missing action', cid)
            continue
        t0 = time.time()
        frames = int(act['mr_frames'])
        AL.assign_action(ctl, act)
        baked = AL.bake_clip(ctl, skel, FrameClip(frames), None)
        # morph curves: sample ctl_face props per frame
        morph_names = list(S.MORPH_TARGETS)
        pbf = ctl.pose.bones['ctl_face']
        curves = {n: np.zeros(frames + 1) for n in morph_names}
        for f in range(frames + 1):
            sc.frame_set(f + 1)
            for n in morph_names:
                curves[n][f] = pbf[n]
        curves = {n: a for n, a in curves.items() if np.abs(a).max() > 1e-4}
        EX.write_export_action(arm_cm, cid, baked)
        EX.write_morph_action(proxy, cid + '_morph', frames + 1, curves)
        keyd = proxy.data.shape_keys
        if not curves:
            keyd.animation_data.action = None
        EX.fbx_export(os.path.join(outp, cid + '.fbx'), [arm_cm, proxy], frame_range=(1, 1 + frames))
        loc = baked['loc'][:, root_idx]
        d = (loc[-1] - loc[0]) * 100.0
        events = json.loads(act.get('mr_events', '[]'))
        for ev in events:
            ev['time_s'] = ev['frame'] / 30.0
        ent = {
            'id': cid, 'form': e['form'], 'root_motion': e['root'], 'behavior': e['behavior'],
            'duration_s': frames / 30.0, 'frames': frames, 'keys': frames + 1, 'sample_rate': 30,
            'loop': bool(act.get('mr_loop', False)), 'static_pose': e['form'] == 'pose' or e['layer'] == 'pose',
            'layer': e['layer'], 'additive': cid in CT.ADDITIVE, 'nominal_speed_cm_s': float(act.get('mr_speed_cm_s', 0.0)),
            'root_motion_cm': {'x': round(float(d[0]), 3), 'y': round(float(-d[1]), 3), 'z': round(float(d[2]), 3), 'note': 'Unreal axes (forward +X, left -Y)'},
            'blender_frame_range': [1, 1 + frames], 'source_action': 'A_' + cid, 'baked_action': cid,
            'export_file': f'export/animations/{cid}.fbx', 'unreal_asset': f'/Game/Operative/Anims/{cid}',
            'events': events, 'foot_contacts': json.loads(act.get('mr_contacts', '[]')),
            'entry_states': e['entry'], 'exit_states': e['exit'],
            'morph_curves': sorted(curves), 'procedural_components': json.loads(act.get('mr_meta', '{}')),
            'note': act.get('mr_note', ''),
        }
        manifest.append(ent)
        print(f'[export] {cid:18s} frames {frames:4d} morphs {len(curves):2d}  {time.time() - t0:.1f}s')
    return manifest


def write_docs(out_dir, manifest, report):
    docs = os.path.join(out_dir, 'docs')
    os.makedirs(docs, exist_ok=True)
    # skeleton and sockets (Blender axes in metres and Unreal axes in centimetres)
    bones = []
    for b in S.BONES:
        x, y, z = S.bone_frame(b)
        bones.append({
            'name': b.name, 'parent': b.parent, 'group': b.group, 'deform': b.deform,
            'rest_head_m_blender': [round(c, 5) for c in b.head], 'rest_tail_m_blender': [round(c, 5) for c in b.tail],
            'rest_head_cm_unreal': [round(b.head[0] * 100, 3), round(-b.head[1] * 100, 3), round(b.head[2] * 100, 3)],
            'local_axes_blender': {'x': [round(c, 4) for c in x], 'y': [round(c, 4) for c in y], 'z': [round(c, 4) for c in z]},
            'note': b.note})
    socks = []
    for name, (bone, pos, fwd, up, purpose) in S.SOCKETS.items():
        socks.append({'name': name, 'bone': bone, 'position_m_blender': [round(c, 5) for c in pos],
                      'position_cm_unreal': [round(pos[0] * 100, 3), round(-pos[1] * 100, 3), round(pos[2] * 100, 3)],
                      'forward_hint_blender': [round(c, 4) for c in fwd], 'up_hint_blender': [round(c, 4) for c in up],
                      'forward_hint_unreal': [round(fwd[0], 4), round(-fwd[1], 4), round(fwd[2], 4)],
                      'up_hint_unreal': [round(up[0], 4), round(-up[1], 4), round(up[2], 4)], 'purpose': purpose})
    doc = {
        'schema': 'morphrig.skeleton_and_sockets/1',
        'units': {'blender_source': 'metres', 'fbx_and_unreal': 'centimetres', 'export_scale': 'baked x100 in a temporary export scene; FBX unit scale 1; no import scale needed'},
        'axes': {'blender': 'Z up, character faces +X, character left = +Y, ground origin between the feet',
                 'unreal': 'Z up, character faces +X, character left = -Y (Unreal receives Blender (x, y, z) as (x, -y, z))'},
        'bone_frame': 'local Y runs head->tail; local Z is the flexion-direction hint; local X = Y x Z. +X rotation is forward flexion for spine, limbs and head; right-side bones are exact X-mirrors of the left side.',
        'root': 'single root bone `root`, identity-oriented, independent of pelvis; carries root motion (dash clips)',
        'bone_count': len(bones), 'bones': bones, 'sockets': socks,
        'morph_targets': S.MORPH_TARGETS, 'visemes': S.VISEMES,
        'face_bones': {'jaw': 'open = negative local X rotation (up to about 24 degrees)', 'eye_l/eye_r': 'rot X = pitch up, rot Z = yaw left', 'lid_up_*': 'closes with negative local X rotation about the eyeball centre', 'lid_lo_*': 'closes with positive local X rotation', 'tongue_01..03': 'negative local X lifts the tongue'},
        'skin': report.get('skin', {}),
    }
    json.dump(doc, open(os.path.join(docs, 'skeleton_and_sockets.json'), 'w'), indent=1)
    if manifest:
        mf = {
            'schema': 'morphrig.animation_manifest/1', 'fps': 30, 'clip_count': len(manifest),
            'motion_entries': sum(1 for m in manifest if not m['static_pose']), 'static_pose_entries': sum(1 for m in manifest if m['static_pose']),
            'conventions': {'frames': 'frames = number of 30 fps intervals; keys = frames + 1; Blender frame = 1 + clip frame',
                            'loops': 'loop clips repeat keys 0..N with pose(N) equal to pose(0); Unreal loops over length = frames/30',
                            'root_motion': 'root bone translation baked in centimetres in Unreal axes (forward +X); in_place clips keep root at the origin',
                            'additive': 'hit_* are authored as offsets from their first frame; Unreal derives the additive pose from frame 0',
                            'layers': {'full': 'full body', 'upper': 'upper-body layer from spine_01 upward over the locomotion base', 'additive': 'additive over any base', 'pose': 'static pose entry'}},
            'clips': manifest}
        json.dump(mf, open(os.path.join(docs, 'animation_manifest.json'), 'w'), indent=1)
    json.dump(report, open(os.path.join(docs, 'export_report.json'), 'w'), indent=1)


def write_material_report(out_dir, report):
    """docs/material_and_lod_report.json: per-LOD triangles, material slots, texture inventory and memory estimate, skeleton statistics."""
    tex_dir = os.path.join(ROOT, 'source', 'textures')
    mpath = os.path.join(tex_dir, 'texture_manifest.json')
    mats = {}
    total_bc = total_raw = 0.0
    if os.path.exists(mpath):
        man = json.load(open(mpath, encoding='utf-8'))['materials']
        # Unreal default compression: colour BC1 (0.5 B/px), masks BC1, normal maps BC5 (1 B/px), team mask with alpha BC7 (1 B/px)
        bpp = {'bc': 0.5, 'n': 1.0, 'orm': 0.5, 'e': 0.5, 'tm': 1.0}
        for m, info in man.items():
            size = info['size']
            files = []
            for kind, fname in info['files'].items():
                px = size * size
                comp = px * bpp[kind] * 4.0 / 3.0 / 1048576.0
                raw = px * 4 * 4.0 / 3.0 / 1048576.0
                total_bc += comp
                total_raw += raw
                files.append({'file': fname, 'kind': {'bc': 'base colour (sRGB)', 'n': 'normal (DirectX)', 'orm': 'AO/roughness/metallic', 'e': 'emission intensity', 'tm': 'team mask'}[kind],
                              'width': size, 'height': size, 'unreal_compression_estimate': {'bc': 'BC1', 'n': 'BC5', 'orm': 'BC1 (masks)', 'e': 'BC1 (masks)', 'tm': 'BC7'}[kind],
                              'memory_mib_with_mips_compressed': round(comp, 3), 'memory_mib_with_mips_rgba8': round(raw, 3)})
            mats['MI_' + m] = {'atlas_size': size, 'textures': files, 'objects_using_it': info['objects'], 'island_coverage': info.get('island_coverage'),
                                'triangles_lod0': report.get('triangles_per_material', {}).get('MI_' + m)}
    lods = report.get('lods', {})
    budget = {'LOD0': 80000, 'LOD1': 40000, 'LOD2': 20000}

    def top_z(name):
        o = bpy.data.objects[name]
        return max((o.matrix_world @ v.co).z for v in o.data.vertices)
    heights = {'skull_top_cm': round(top_z('Operative_Head') * 100.0, 2), 'hair_top_cm': round(top_z('Operative_Hair') * 100.0, 2)}
    doc = {
        'schema': 'morphrig.material_and_lod_report/1',
        'lods': {k: dict(v, budget_triangles=budget[k], within_budget=v['triangles'] <= budget[k]) for k, v in lods.items()},
        'material_slots': {'character': report.get('material_slots', []), 'props': report.get('props', {}), 'total_unique_slots': len(set(report.get('material_slots', []))), 'limit': 8},
        'materials': mats,
        'texture_limits': {'max_dimension': 4096, 'largest_dimension_used': max([t['width'] for m in mats.values() for t in m['textures']] or [0])},
        'texture_memory_mib': {'unreal_compressed_estimate_with_mips': round(total_bc, 2), 'uncompressed_rgba8_with_mips': round(total_raw, 2),
                               'note': 'estimate from pixel counts (BC1/BC5/BC7 sizes, +1/3 for mips); the packaged build reports the real numbers in the showcase overlay'},
        'skeleton': {'bones_total': len(S.BONES), 'deformation_bones': sum(1 for b in S.BONES if b.deform), 'roots': sum(1 for b in S.BONES if b.parent is None),
                     'deformation_bones_with_weights': report.get('skin', {}).get('deformation_bones_with_weights'),
                     'max_influences_per_vertex': report.get('skin', {}).get('max_influences_per_vertex'), 'influence_limit': 8},
        'morph_targets_lod0': lods.get('LOD0', {}).get('morph_targets'),
        'team_variants': {'A': 'cyan, circle icon', 'B': 'magenta, diamond icon', 'mechanism': 'TeamIndex parameter selects the colour (Blender: scene["mr_team"]); icons live in the team mask G/B channels; the rim outline is a material parameter (Blender: scene["mr_outline"])'},
        'height_cm': heights['skull_top_cm'],
        'height_cm_with_hair': heights['hair_top_cm'],
        'height_note': 'rest pose, measured on the meshes: the ground to the top of the skull is the standing height; the hair cap adds a few millimetres on top',
    }
    json.dump(doc, open(os.path.join(out_dir, 'docs', 'material_and_lod_report.json'), 'w'), indent=1)


def main():
    out = os.path.abspath(arg('--out', ROOT))
    only = set(arg('--only', '').split(',')) - {''}
    t0 = time.time()
    ctl = bpy.data.objects['Operative_Control']
    skel = bpy.data.objects['Operative_Skeleton']
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 30, 1.0
    arm_cm = EX.cm_armature(skel)
    report = {}
    if not arg('--no-mesh', False):
        os.makedirs(os.path.join(out, 'export', 'props'), exist_ok=True)
        export_meshes(out, arm_cm, report)
        report['props'] = export_props(out)
        print(f'[export] meshes done {time.time() - t0:.1f}s', json.dumps(report.get('lods')))
    manifest = []
    if not arg('--no-clips', False):
        proxy = EX.make_morph_proxy('MorphProxy', S.MORPH_TARGETS, arm_cm)
        export_clips(out, ctl, skel, arm_cm, proxy, only or None, manifest)
        order = [e['id'] for e in CT.build_table()]
        manifest.sort(key=lambda m: order.index(m['id']))
    write_docs(out, manifest, report)
    if report.get('lods'):
        write_material_report(out, report)
    print(f'[export] done in {time.time() - t0:.1f}s')


main()

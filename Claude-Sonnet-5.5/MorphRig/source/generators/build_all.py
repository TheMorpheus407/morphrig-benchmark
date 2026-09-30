"""Build the complete Operative.blend from scratch (procedural generators, no interactive edits).

usage: blender -b --factory-startup -P source/generators/build_all.py -- [--blend OUT.blend] [--no-clips] [--bake-textures] [--no-textures]
Steps: deformation skeleton -> meshes and skin weights -> UV atlases -> textures and materials -> control rig -> face shape keys -> clip actions
       -> collections -> save. Textures are baked into source/textures/ when missing, stale (UV layout changed) or --bake-textures is given.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy
import numpy as np
import skeleton_def as S
import rig_skeleton as RS
import build_character as BC
import build_rig as BR
import face_shapes as FS
import anim_lib as AL
import anim_registry as AR
import pose_lib as PL
import uvtex as UT
import mr_tools as MT
import pose_tests as PT
import face_lib as FL


def arg(name, default=None):
    if '--' in sys.argv:
        a = sys.argv[sys.argv.index('--') + 1:]
        if name in a:
            i = a.index(name)
            return a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else True
    return default


def organise(skel, ctl, objs):
    sc = bpy.context.scene
    def coll(name, parent=None):
        c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if c.name not in [x.name for x in (parent or sc.collection).children]:
            (parent or sc.collection).children.link(c)
        return c
    c_rig, c_mesh, c_props = coll('Operative_Rig'), coll('Operative_Mesh'), coll('Operative_Props')
    for o in (skel, ctl):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        c_rig.objects.link(o)
    for o in objs.values():
        for c in list(o.users_collection):
            c.objects.unlink(o)
        c_mesh.objects.link(o)
    skel.hide_viewport = False
    ctl.show_in_front = True


TEX_DIR = os.path.abspath(os.path.join(HERE, '..', 'textures'))


def textures_and_materials(bake=False, enabled=True, log=print):
    """UV layout (always) + texture bake (when needed) + material node trees."""
    objs_m = UT.mesh_objects()
    UT.layout_uvs(objs_m)
    if not enabled:
        return None
    uvh = UT.uv_hash(objs_m)
    man_path = os.path.join(TEX_DIR, 'texture_manifest.json')
    stale = True
    if os.path.exists(man_path):
        try:
            with open(man_path, encoding='utf-8') as fh:
                cur = json.load(fh)
            stale = cur.get('uv_layout_sha1') != uvh
        except (OSError, ValueError):
            stale = True
    if bake or stale:
        log(f'[build_all] baking textures ({"forced" if bake else "missing or UV layout changed"})')
        manifest = UT.bake_textures(objs_m, TEX_DIR, log=log)
        UT.save_manifest(TEX_DIR, manifest, uvh)
    else:
        manifest = cur['materials']
    UT.build_materials(TEX_DIR, manifest)
    return manifest


def build(out_blend, with_clips=True, bake_textures=False, textures=False):
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 30
    sc.render.fps_base = 1.0
    sc.render.filepath = '//render_'
    sc.frame_start, sc.frame_end = 1, 31
    skel = RS.create_skeleton()
    objs, info = BC.build_all(skel)
    textures_and_materials(bake_textures, textures)
    rb = BR.build_rig(skel)
    ctl = rb.ob
    FS.add_shape_keys(objs['head'], info['head_info'])
    FS.add_face_props_and_drivers(ctl, objs['head'])
    AL.setup_defaults(ctl)
    organise(skel, ctl, objs)
    MT.install_into_blend(FL, S, source_path=os.path.join(HERE, 'mr_tools.py'))
    print(f'[build_all] rig+meshes {time.time() - t0:.1f}s, control bones {len(ctl.data.bones)}')
    clips = {}
    if with_clips:
        PL.bind(ctl, skel)
        AR.load_real_clips()
        clips = AR.make_all()
        for cid, c in clips.items():
            PL.finalize_clip(c, ctl, skel, getattr(c, 'prop_states', None))
        PT.build(ctl, skel)
        print(f'[build_all] {len(clips)} clips and {len(PT.POSES)} skinning test poses written {time.time() - t0:.1f}s')
    ctl.animation_data_create()
    if with_clips:
        AL.assign_action(ctl, bpy.data.actions['A_idle_relaxed'])
    if out_blend:
        os.makedirs(os.path.dirname(out_blend), exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0          # no .blend1 backup next to the deliverable
        bpy.ops.wm.save_as_mainfile(filepath=out_blend)
        bpy.ops.file.make_paths_relative()          # texture paths relative to the .blend (source/textures)
        bpy.ops.wm.save_mainfile()
        print('[build_all] saved', out_blend)
    return skel, ctl, objs, info, clips


if __name__ == '__main__':
    out = arg('--blend', None)
    build(out, with_clips=not arg('--no-clips', False), bake_textures=bool(arg('--bake-textures', False)), textures=not arg('--no-textures', False))

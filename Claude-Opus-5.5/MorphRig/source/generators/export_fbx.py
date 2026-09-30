"""Stage D: export the skeletal mesh (LOD0/1/2) and every baked clip to FBX, plus face curves.

Usage:
  blender -b --factory-startup -P export_fbx.py -- --in Operative.blend --outdir <MorphRig/export> [--only ids]

Outputs (in --outdir):
  Operative.fbx, Operative_LOD1.fbx, Operative_LOD2.fbx   skeletal mesh + morph targets, bind pose
  animations/<clip>.fbx                                    skeleton-only baked take per clip
  animations/face_curves.json                              per clip, per frame shape-key weights
                                                           (evaluated from the rig's face drivers)
Conventions: the production file is in Blender metres.  For export the in-memory copy is converted
to centimetres (scene unit scale 0.01, bones / meshes / shape keys / location keys x100), so the FBX
is written 1:1 in centimetres and every bone - including 'root' - has scale 1 in Unreal (a unit
scale carried on the root would also scale extracted root motion).  Blender -Y forward / +Z up ->
Unreal +Y forward (mesh space) / +Z up.
The armature object is exported under the node name 'Armature' so Unreal does not add
an extra root bone; the first bone is 'root'.
"""
import sys
import os
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
import numpy as np


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-mesh", action="store_true")
    ap.add_argument("--no-anims", action="store_true")
    return ap.parse_args(argv)


FBX_COMMON = dict(
    use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
    axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y',
    secondary_bone_axis='X', armature_nodetype='NULL', use_armature_deform_only=False,
    mesh_smooth_type='FACE', use_tspace=True, use_mesh_modifiers=False, use_triangles=False,
    embed_textures=False, path_mode='STRIP')


CM = 100.0


def _fcurves(act):
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


def to_centimetres(skel, meshes, extra_meshes=()):
    """Convert the export copy from metres to centimetres (scene unit 0.01, data x100)."""
    bpy.context.scene.unit_settings.scale_length = 1.0 / CM
    # armature: rest bones
    select_only([skel])
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in skel.data.edit_bones:
        eb.head = eb.head * CM
        eb.tail = eb.tail * CM
    bpy.ops.object.mode_set(mode='OBJECT')
    skel.location = skel.location * CM
    # meshes: vertices and every shape key
    for ob in list(meshes) + list(extra_meshes):
        me = ob.data
        n = len(me.vertices)
        co = np.empty(n * 3)
        me.vertices.foreach_get("co", co)
        me.vertices.foreach_set("co", co * CM)
        if me.shape_keys:
            for kb in me.shape_keys.key_blocks:
                kb.data.foreach_get("co", co)
                kb.data.foreach_set("co", co * CM)
        me.update()
        ob.location = ob.location * CM
        M = ob.matrix_parent_inverse.copy()
        M.translation = M.translation * CM
        ob.matrix_parent_inverse = M
    # baked skeleton actions: bone translations
    for act in bpy.data.actions:
        if not act.name.startswith("SK_"):
            continue
        for fc in _fcurves(act):
            if fc.data_path.endswith(".location") or fc.data_path == "location":
                for kp in fc.keyframe_points:
                    kp.co.y *= CM
                    kp.handle_left.y *= CM
                    kp.handle_right.y *= CM
    bpy.context.view_layer.update()


def select_only(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        for c in o.users_collection:
            c.hide_viewport = False
        o.hide_set(False)
        o.hide_viewport = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def mute_skeleton_constraints(skel, mute=True):
    for pb in skel.pose.bones:
        for c in pb.constraints:
            c.mute = mute


def lod_of(ob):
    for lv in (1, 2):
        if ob.name.endswith(f"_LOD{lv}"):
            return lv
    return 0


def export_static_beacon(out):
    """Static copy of the beacon for the deployed prop (upright, base at z = 0, centred)."""
    src = bpy.data.objects.get("MR_PropBeacon")
    if src is None:
        return
    me = src.data.copy()
    co = np.array([v.co for v in me.vertices])
    # holster orientation: beacon 'up' is +Y -> rotate +90 deg about X so it points +Z
    co = np.stack([co[:, 0], -co[:, 2], co[:, 1]], 1)      # (already centimetres: converted with the other children)
    co[:, 0] -= 0.5 * (co[:, 0].min() + co[:, 0].max())
    co[:, 1] -= 0.5 * (co[:, 1].min() + co[:, 1].max())
    co[:, 2] -= co[:, 2].min()
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    ob = bpy.data.objects.new("SM_Beacon", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.vertex_groups.clear()
    select_only([ob])
    os.makedirs(os.path.join(out, "props"), exist_ok=True)
    fp = os.path.join(out, "props", "SM_Beacon.fbx")
    bpy.ops.export_scene.fbx(filepath=fp, object_types={'MESH'}, bake_anim=False, **FBX_COMMON)
    bpy.data.objects.remove(ob)
    print("EXPORTED", fp)


def write_reports(out, skel, meshes):
    """Facts for docs/skeleton_and_sockets.json and docs/material_and_lod_report.json."""
    import mr_skeleton
    bones = []
    for b in skel.data.bones:
        M = b.matrix_local
        bones.append({
            "name": b.name, "parent": b.parent.name if b.parent else None, "deform": bool(b.use_deform),
            "head_m": [round(x, 5) for x in b.head_local], "tail_m": [round(x, 5) for x in b.tail_local],
            "axis_y": [round(M[i][1], 4) for i in range(3)], "axis_z": [round(M[i][2], 4) for i in range(3)]})
    sockets = [{"socket": n, "bone": "sock_" + n, "parent_bone": bone, "rest_location_m": [round(float(x), 5) for x in pos],
                "description": desc} for n, bone, pos, desc in mr_skeleton.socket_list()]
    lods = {}
    for m in meshes:
        lv = lod_of(m)
        tris = sum(len(p.vertices) - 2 for p in m.data.polygons)
        maxinf = max((len([g for g in v.groups if g.weight > 1e-4]) for v in m.data.vertices), default=0)
        d = lods.setdefault(f"LOD{lv}", {"objects": {}, "tris": 0, "verts": 0, "materials": set(), "max_influences": 0})
        d["objects"][m.name] = tris
        d["tris"] += tris
        d["verts"] += len(m.data.vertices)
        d["materials"] |= {ms.name for ms in m.data.materials if ms}
        d["max_influences"] = max(d["max_influences"], maxinf)
    for d in lods.values():
        d["materials"] = sorted(d["materials"])
    textures = []
    for img in bpy.data.images:
        if img.source != 'FILE' or not img.filepath:
            continue
        w, h = img.size
        name = os.path.basename(img.filepath)
        # BC7 / BC5 style 1 byte per texel, BC1 0.5; plus a full mip chain (x 4/3)
        bpt = 1.0
        textures.append({"file": name, "width": w, "height": h,
                         "est_gpu_mb": round(w * h * bpt * 4 / 3 / 2 ** 20, 2)})
    head = bpy.data.objects.get("MR_Head")
    report = {
        "units": "Blender metres (+Z up, character faces -Y, character left = +X); FBX / Unreal centimetres "
                 "(export copy converted, all bone scales 1), imported character height 180 cm",
        "bones": bones, "bone_count": len(bones), "deform_bone_count": sum(1 for b in bones if b["deform"]),
        "sockets": sockets, "lods": lods, "textures": textures,
        "texture_memory_mb": round(sum(t["est_gpu_mb"] for t in textures), 1),
        "shape_keys": [k.name for k in head.data.shape_keys.key_blocks[1:]] if head and head.data.shape_keys else [],
        "height_m": round(max(v.co.z for m in meshes if lod_of(m) == 0 and m.name.startswith("MR_Hair") is False
                              for v in m.data.vertices), 4),
    }
    with open(os.path.join(out, "reports.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    print("REPORT", report["bone_count"], "bones", {k: v["tris"] for k, v in lods.items()})


def main():
    args = parse()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.inp))
    out = os.path.abspath(args.outdir)
    os.makedirs(os.path.join(out, "animations"), exist_ok=True)
    skel = bpy.data.objects["MR_Skeleton"]
    rig = bpy.data.objects["MR_Rig"]
    head = bpy.data.objects["MR_Head"]
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == skel and o.get("mr_export", 1)]
    orig_name = skel.name
    skel.name = "Armature"
    skel.data.name = "Armature"
    if rig.animation_data:
        rig.animation_data.action = None
    mute_skeleton_constraints(skel, True)
    if skel.animation_data:
        skel.animation_data.action = None
    for pb in skel.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    if not args.no_mesh:
        write_reports(out, skel, meshes)          # metric facts, before the unit conversion
    extra = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == skel and o not in meshes]
    to_centimetres(skel, meshes, extra)
    if not args.no_mesh:
        for lv in (0, 1, 2):
            objs = [m for m in meshes if lod_of(m) == lv]
            if not objs:
                continue
            # LOD copies are exported under their LOD0 names (material slots / morph names match)
            renamed = []
            if lv:
                for o in objs:
                    base = o.name[:-5]
                    src = bpy.data.objects.get(base)
                    if src is not None:
                        src.name = base + "__tmp"
                    renamed.append((o, o.name, src))
                    o.name = base
            select_only([skel] + objs)
            fp = os.path.join(out, "Operative.fbx" if lv == 0 else f"Operative_LOD{lv}.fbx")
            bpy.ops.export_scene.fbx(filepath=fp, bake_anim=False, object_types={'ARMATURE', 'MESH'}, **FBX_COMMON)
            print("EXPORTED", fp, "meshes", [m.name for m in objs])
            for o, nm, src in renamed:
                base = o.name
                o.name = nm
                if src is not None:
                    src.name = base
    if not args.no_mesh:
        export_static_beacon(out)
    if args.no_anims:
        skel.name = orig_name
        skel.data.name = orig_name
        return
    only = [x for x in args.only.split(",") if x]
    clips = sorted([a for a in bpy.data.actions if a.name.startswith("SK_")], key=lambda a: a.name)
    sc = bpy.context.scene
    keys = [kb.name for kb in head.data.shape_keys.key_blocks[1:]]
    face_path = os.path.join(out, "animations", "face_curves.json")
    meta_path = os.path.join(out, "animations", "clips_meta.json")
    face, metas = {}, {}
    if only and os.path.exists(face_path):
        with open(face_path) as fh:
            face = json.load(fh)
    if only and os.path.exists(meta_path):
        with open(meta_path) as fh:
            metas = json.load(fh)
    for act in clips:
        cid = act.name[3:]
        if only and cid not in only:
            continue
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        sc.frame_start, sc.frame_end = f0, f1
        meta = json.loads(act.get("mr_meta", "{}"))
        meta["frame_range"] = [f0, f1]
        meta["blender_action"] = act.name
        meta["rig_action"] = "RIG_" + cid
        metas[cid] = meta
        # face: evaluate the rig's face drivers frame by frame
        ract = bpy.data.actions.get("RIG_" + cid)
        curves = {k: [] for k in keys}
        if ract is not None:
            rig.animation_data.action = ract
            rig.animation_data.action_slot = ract.slots[0]
            kbs = head.data.shape_keys.key_blocks
            for f in range(f0, f1 + 1):
                sc.frame_set(f)
                for k in keys:
                    curves[k].append(round(float(kbs[k].value), 4))
            rig.animation_data.action = None
        face[cid] = {"fps": 30, "first_frame": f0, "frames": f1 - f0 + 1,
                     "curves": {k: v for k, v in curves.items() if v and max(v) > 1e-3}}
        # skeleton take
        if skel.animation_data is None:
            skel.animation_data_create()
        skel.animation_data.action = act
        skel.animation_data.action_slot = act.slots[0]
        select_only([skel])
        fp = os.path.join(out, "animations", f"{cid}.fbx")
        bpy.ops.export_scene.fbx(filepath=fp, bake_anim=True, bake_anim_use_all_bones=True,
                                 bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
                                 bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                                 bake_anim_simplify_factor=0.0, object_types={'ARMATURE'}, **FBX_COMMON)
        skel.animation_data.action = None
        print("EXPORTED", fp, f0, f1, "face curves", len(face[cid]["curves"]))
    with open(face_path, "w") as fh:
        json.dump(face, fh, separators=(",", ":"))
    with open(meta_path, "w") as fh:
        json.dump(metas, fh, indent=1, default=str)
    skel.name = orig_name
    skel.data.name = orig_name


if __name__ == "__main__":
    main()

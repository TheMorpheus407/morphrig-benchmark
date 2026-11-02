"""Export the MorphRig production assets to FBX.

    blender -b --factory-startup -P source/generators/export_fbx.py

Produces
    export/Operative.fbx              skeleton + LOD0 body + every action
    export/animations/<clip>.fbx      one file per required clip
    export/LOD/Operative_LOD1.fbx     lower LODs
    export/textures/*.png             the eight material sets

The FBX is written in the Unreal friendly orientation: Blender Y-up with
-Z forward is converted on import, and the scene is scaled so the 1.80 m
character lands at 180 cm in Unreal without an import scale repair.
"""

import json
import math
import os
import shutil
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# Blender is metres, Unreal is centimetres.  The exporter bakes this factor
# into the geometry so a default Unreal import is already 180 cm tall.
# The scene is metric with a scale length of one, so the character is 1.8
# Blender units tall.  The FBX exporter writes the data in centimetres and
# marks the file as centimetres, so one Blender unit arrives in Unreal as
# one hundred centimetres.  The global scale therefore stays at one: a
# hundred would push the character to 180 metres in Unreal.
FBX_SCALE = 1.0

# Blender's FBX exporter scales the mesh and the bone rest hierarchy into
# centimetres but writes the bone animation curves in Blender units (metres).
# Unreal imports the file as centimetres, so every animated translation would
# arrive a hundred times too small - the two metres of dash displacement would
# become two centimetres and the secondary motion of the hips, spine and
# shoulders would disappear.  The location curves are therefore multiplied by
# the same factor while the files are written.  The master blend keeps the
# original metre based values, so the Blender source and the rendered videos
# are unaffected.
FBX_UNIT_FIX = 100.0

# The Blender character faces -Y, which is the convention of the source
# project.  Unreal expects the character of an actor to face the +X axis of
# the actor, and the axis conversion of the FBX importer keeps the Blender
# front on the Y axis of the component.  The armature is therefore turned by
# -90 degrees around Z while the files are written, so the Operative faces +X
# in Unreal with the right hand on +Y, exactly like every other Unreal
# character.  The master blend keeps the original orientation, so the Blender
# source and the rendered videos are unaffected.
FBX_YAW = 90.0

# Unreal asset paths used by the project
UE_ANIM_DIR = "/Game/MorphRig/Animations"
UE_MESH_DIR = "/Game/MorphRig/Meshes"
UE_TEX_DIR = "/Game/MorphRig/Textures"


def action_fcurves(action):
    """Blender 5 keeps the animation curves in slotted action channel bags."""
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


def scale_translation_curves(factor):
    """Scale every pose bone location curve of every action.

    Returns a callable that restores the original values.  The key values and
    the bezier handles are scaled together so the interpolation is unchanged.
    The original values are remembered by index: the keyframe structs
    themselves must not be kept, the exporter rebuilds the animation data and
    the references would dangle.
    """
    restore = []
    for action in bpy.data.actions:
        for curve in action_fcurves(action):
            if ".location" not in curve.data_path:
                continue
            for index, key in enumerate(curve.keyframe_points):
                restore.append((action.name, curve.data_path, curve.array_index,
                                index, key.co[1], key.handle_left[1],
                                key.handle_right[1]))
                key.co[1] = key.co[1] * factor
                key.handle_left[1] = key.handle_left[1] * factor
                key.handle_right[1] = key.handle_right[1] * factor
            curve.update()

    def undo():
        by_action = {}
        for action_name, data_path, array_index, index, co_y, left_y, right_y in restore:
            by_action.setdefault(action_name, []).append(
                (data_path, array_index, index, co_y, left_y, right_y))
        for action_name, entries in by_action.items():
            action = bpy.data.actions.get(action_name)
            if action is None:
                continue
            curves = {}
            for curve in action_fcurves(action):
                curves[(curve.data_path, curve.array_index)] = curve
            for data_path, array_index, index, co_y, left_y, right_y in entries:
                curve = curves.get((data_path, array_index))
                if curve is None or index >= len(curve.keyframe_points):
                    continue
                key = curve.keyframe_points[index]
                key.co[1] = co_y
                key.handle_left[1] = left_y
                key.handle_right[1] = right_y
            for curve in curves.values():
                curve.update()

    return undo


def export_fbx(path, objects, actions=None, all_actions=False):
    kw = dict(
        filepath=path,
        use_selection=False,
        use_visible=True,
        object_types={'ARMATURE', 'MESH'},
        use_mesh_modifiers=True,
        mesh_smooth_type='FACE',
        add_leaf_bones=False,
        primary_bone_axis='Y',
        secondary_bone_axis='X',
        use_armature_deform_only=True,
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=all_actions,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        axis_forward='-Z',
        axis_up='Y',
        global_scale=FBX_SCALE,
        apply_unit_scale=True,
        use_custom_props=False,
        path_mode='COPY',
        embed_textures=False,
    )
    if actions is not None:
        kw["bake_anim_use_all_actions"] = False
    bpy.ops.export_scene.fbx(**kw)
    return path


def export_everything(arm, body, actions, outdir, animdir, loddir, texdir):
    """Write every FBX file and return the list of (clip, path) pairs."""
    # The animation curves are written in centimetres so Unreal sees the
    # authored distances (see FBX_UNIT_FIX).
    restore_curves = scale_translation_curves(FBX_UNIT_FIX)

    # The armature is turned so the character faces +X in Unreal (FBX_YAW).
    # The body and the LOD copies are parented to the armature and follow.
    arm.rotation_euler = (0.0, 0.0, math.radians(FBX_YAW))
    bpy.context.view_layer.update()

    # --- the master file: skeleton, LOD0 mesh and every action as a take
    master = os.path.join(outdir, "Operative.fbx")
    export_fbx(master, [arm, body], all_actions=True)
    print("EXPORT_MASTER %s (%.1f MB)"
          % (master, os.path.getsize(master) / 1048576.0))

    # --- one file per clip
    manifest_clips = []
    scene = bpy.context.scene
    scene_range = (scene.frame_start, scene.frame_end)
    for act in actions:
        clip = act.name[4:]
        arm.animation_data.action = act
        # The FBX exporter bakes over the scene frame range, so the range
        # has to follow the action, otherwise every clip would be exported
        # with the length of the whole scene.
        start, end = act.frame_range
        scene.frame_start = int(round(start))
        scene.frame_end = int(round(end))
        # A one frame range produces an FBX take that Unreal's importer
        # rejects as empty, so a static pose is always written twice.
        if scene.frame_end <= scene.frame_start:
            scene.frame_end = scene.frame_start + 1
        p = os.path.join(animdir, "%s.fbx" % clip)
        export_fbx(p, [arm, body], actions=[act])
        manifest_clips.append((clip, p))
    scene.frame_start, scene.frame_end = scene_range
    print("EXPORT_CLIPS %d" % len(manifest_clips))

    # --- LOD files
    for lod in ("LOD1", "LOD2"):
        ob = bpy.data.objects.get("Operative_Body_%s" % lod)
        if ob is None:
            continue
        ob.hide_viewport = False
        ob.hide_render = False
        arm.animation_data.action = bpy.data.actions.get("ACT_idle_combat")
        p = os.path.join(loddir, "Operative_%s.fbx" % lod)
        export_fbx(p, [arm, ob], actions=[arm.animation_data.action])
        ob.hide_viewport = True
        ob.hide_render = True
        print("EXPORT_LOD %s" % p)

    # the master blend keeps the metre based curves and the original heading
    restore_curves()
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    # --- textures
    src_tex = os.path.join(ROOT, "source", "textures")
    for fn in sorted(os.listdir(src_tex)):
        if fn.lower().endswith(".png"):
            shutil.copy2(os.path.join(src_tex, fn), os.path.join(texdir, fn))
    print("EXPORT_TEXTURES %d" % len(os.listdir(texdir)))
    return manifest_clips


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = os.path.join(ROOT, "source", "Operative.blend")
    if "--blend" in argv:
        blend = argv[argv.index("--blend") + 1]
    # --manifest-only rewrites the manifest and the skeleton document from the
    # blend without touching the FBX files.  It is used when a documentation
    # field changes and the exported files themselves stay the same.
    manifest_only = "--manifest-only" in argv
    outdir = os.path.join(ROOT, "export")
    animdir = os.path.join(outdir, "animations")
    loddir = os.path.join(outdir, "LOD")
    texdir = os.path.join(outdir, "textures")
    for d in (outdir, animdir, loddir, texdir):
        os.makedirs(d, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    arm = bpy.data.objects.get("Operative_Rig")
    body = bpy.data.objects.get("Operative_Body")
    if arm is None or body is None:
        raise SystemExit("rig or body missing")

    # hide the LOD copies so only LOD0 is in the main file
    for ob in bpy.data.objects:
        if ob.name.startswith("Operative_Body_LOD"):
            ob.hide_viewport = True
            ob.hide_render = True

    actions = sorted([a for a in bpy.data.actions
                      if a.name.startswith("ACT_")
                      and not a.name.endswith("_face")
                      and "." not in a.name],
                     key=lambda a: a.name)
    print("EXPORT_ACTIONS %d" % len(actions))

    manifest_clips = []
    if manifest_only:
        # the files are already on disk, only the documentation is refreshed
        for act in actions:
            clip = act.name[4:]
            p = os.path.join(animdir, "%s.fbx" % clip)
            if os.path.exists(p):
                manifest_clips.append((clip, p))
        print("EXPORT_MANIFEST_ONLY %d clips on disk" % len(manifest_clips))
    else:
        manifest_clips = export_everything(arm, body, actions, outdir,
                                           animdir, loddir, texdir)

    # --- enrich the animation manifest
    manifest_path = os.path.join(ROOT, "docs", "animation_manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    # --- enrich the animation manifest
    manifest_path = os.path.join(ROOT, "docs", "animation_manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    exported = dict(manifest_clips)
    for c in manifest["clips"]:
        name = c["name"]
        c["exported_fbx"] = "export/animations/%s.fbx" % name
        c["master_fbx"] = "export/Operative.fbx"
        c["take"] = "ACT_%s" % name
        c["unreal_asset"] = "%s/A_%s" % (UE_ANIM_DIR, name)
        c["unreal_mesh"] = "%s/SK_Operative" % UE_MESH_DIR
        c["sample_rate"] = manifest["fps"]
        c["frame_start"] = 1
        # the exported range carries the closing key, so it is one frame
        # longer than the authored frame count
        c["frame_end"] = c["frames"] + 1
        c["authored_frames"] = c["frames"]
        c["closing_key"] = True
        c["start_time"] = 0.0
        c["end_time"] = round(c["duration"], 4)
        c["unreal_sequence_length"] = round(c["duration"], 4)
        c["layer"] = layer_for(c)
        c["entry_state"] = "Ground"
        c["exit_state"] = "Ground"
        c["exported"] = name in exported
    manifest["master_fbx"] = "export/Operative.fbx"
    manifest["unreal_animation_dir"] = UE_ANIM_DIR
    manifest["unreal_mesh_dir"] = UE_MESH_DIR
    manifest["unreal_texture_dir"] = UE_TEX_DIR
    manifest["fbx_scale_factor"] = FBX_SCALE
    manifest["fbx_export_corrections"] = {
        "fbx_scale_factor": FBX_SCALE,
        "fbx_unit_fix": FBX_UNIT_FIX,
        "fbx_unit_fix_note": (
            "Blender's FBX exporter writes the mesh and the bone rest hierarchy "
            "in centimetres but writes the bone animation curves in metres.  "
            "The location curves of every pose bone are multiplied by this "
            "factor while the files are written, so Unreal reads the animated "
            "translations in centimetres.  The master blend is not touched."),
        "fbx_yaw_degrees": FBX_YAW,
        "fbx_yaw_note": (
            "The armature is turned by this angle around Z while the files are "
            "written, so the Operative faces +X in Unreal (Blender faces -Y).  "
            "The master blend keeps the original orientation."),
        "applies_to": "export time only, the master blend keeps metres and -Y",
    }
    manifest["total_clips"] = len(manifest["clips"])
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print("EXPORT_MANIFEST %s" % manifest_path)

    # --- skeleton + sockets documentation
    write_skeleton_doc(arm, body)
    print("EXPORT_DONE")


def layer_for(clip):
    """The Unreal animation layer a clip belongs to."""
    name = clip["name"]
    if name.startswith("hit_"):
        return "Additive.HitReaction"
    if name.startswith("aim_"):
        return "UpperBody.Aim"
    if name.startswith("dash_"):
        return "FullBody.RootMotion"
    if name in ("blink_out", "blink_in"):
        return "FullBody.Teleport"
    if name.startswith(("melee", "ranged", "reload", "cast", "channel",
                        "charge", "deploy", "uplink")):
        return "FullBody.Action"
    if name.startswith(("walk", "run", "sprint", "start_", "stop_", "turn_",
                        "pivot_", "jump", "fall", "land")):
        return "FullBody.Locomotion"
    if name.startswith(("death", "dead", "respawn", "knock", "prone",
                        "getup", "stun", "sleep")):
        return "FullBody.State"
    if name == "dialogue":
        return "FullBody.Performance"
    return "FullBody.Idle"


def write_skeleton_doc(arm, body):
    """docs/skeleton_and_sockets.json"""
    import mathutils

    def v(t):
        return [round(c, 5) for c in t]

    bones = []
    for b in arm.data.bones:
        bones.append({
            "name": b.name,
            "parent": b.parent.name if b.parent else None,
            "head": v(b.head_local),
            "tail": v(b.tail_local),
            "deform": bool(b.use_deform),
            "connected": bool(b.use_connect),
        })
    sockets = []
    for name, desc, loc, rot in SOCKETS:
        sockets.append({"name": name, "description": desc,
                        "location": loc, "rotation": rot,
                        "space": "character"})

    doc = {
        "character": "Operative",
        "source_file": "source/Operative.blend",
        "exported_file": "export/Operative.fbx",
        "units": {"blender": "metre", "unreal": "centimetre",
                  "fbx_scale_factor": FBX_SCALE,
                  "fbx_unit_fix": FBX_UNIT_FIX,
                  "fbx_yaw_degrees": FBX_YAW,
                  "note": ("the exporter writes the mesh and the bone rest "
                           "hierarchy in centimetres but the bone animation "
                           "curves in metres, so the location curves are "
                           "multiplied by fbx_unit_fix while the files are "
                           "written; the armature is turned by fbx_yaw_degrees "
                           "around Z so the Operative faces +X in Unreal; "
                           "neither change touches the master blend")},
        "axes": {
            "blender_forward": "-Y", "blender_up": "+Z", "blender_right": "+X",
            "unreal_forward": "+X", "unreal_up": "+Z", "unreal_right": "+Y",
            "note": ("the FBX is written with axis_forward=-Z / axis_up=Y so "
                     "the Unreal importer converts the scene; the character "
                     "faces +X in Unreal and stands on Z=0"),
        },
        "root": {
            "name": "root",
            "note": ("exactly one root bone, independent from the pelvis; "
                     "root motion is extracted from it"),
        },
        "bone_count": len(bones),
        "deform_bone_count": len([b for b in bones if b["deform"]]),
        "bones": bones,
        "sockets": sockets,
        "material_slots": [s.material.name if s.material else None
                           for s in body.material_slots],
    }
    path = os.path.join(ROOT, "docs", "skeleton_and_sockets.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
    print("EXPORT_SKELETON %s" % path)


SOCKETS = [
    ("hand_r", "right hand attachment point", [0, 0, 0], [0, 0, 0]),
    ("hand_l", "left hand attachment point", [0, 0, 0], [0, 0, 0]),
    ("emitter_muzzle_r", "wrist emitter muzzle", [0, 0, 0], [0, 0, 0]),
    ("blade_base_r", "forearm blade root", [0, 0, 0], [0, 0, 0]),
    ("blade_tip_r", "forearm blade tip", [0, 0, 0], [0, 0, 0]),
    ("effect_anchor_r", "generic right hand effect anchor", [0, 0, 0],
     [0, 0, 0]),
    ("effect_anchor_l", "generic left hand effect anchor", [0, 0, 0],
     [0, 0, 0]),
    ("foot_l", "left foot contact point", [0, 0, 0], [0, 0, 0]),
    ("foot_r", "right foot contact point", [0, 0, 0], [0, 0, 0]),
    ("head_face", "face / look at anchor", [0, 0, 0], [0, 0, 0]),
]


main()

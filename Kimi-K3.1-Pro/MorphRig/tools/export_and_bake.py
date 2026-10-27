"""Bake/export the authoritative Blender asset. Run inside Blender after opening source/Operative.blend.
Example: blender -b source/Operative.blend -P tools/export_and_bake.py
Use -- --mesh-only or -- --animations-only for an explicit partial export.
"""
from pathlib import Path
import json
import math
import sys
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "export"
DOCS = ROOT / "docs"
FPS = 30


def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def fbx(path, objects, animation=False):
    select_only(objects)
    options = {
        "filepath": str(path), "use_selection": True, "object_types": {'ARMATURE', 'MESH'},
        "use_mesh_modifiers": True, "use_armature_deform_only": True, "add_leaf_bones": False,
        "primary_bone_axis": 'Y', "secondary_bone_axis": 'X', "armature_nodetype": 'NULL',
        "mesh_smooth_type": 'FACE', "use_tspace": True, "use_triangles": True,
        "axis_forward": '-Z', "axis_up": 'Y', "global_scale": 1.0,
        "apply_unit_scale": False, "apply_scale_options": 'FBX_SCALE_UNITS',
        "bake_space_transform": False,
        "path_mode": 'RELATIVE', "embed_textures": True,
        "bake_anim": animation, "bake_anim_use_all_bones": True,
        "bake_anim_use_nla_strips": False, "bake_anim_use_all_actions": False,
        "bake_anim_force_startend_keying": True, "bake_anim_step": 1.0,
        "bake_anim_simplify_factor": 0.0,
    }
    supported = set(bpy.ops.export_scene.fbx.get_rna_type().properties.keys())
    missing = [key for key in options if key not in supported]
    if missing:
        raise RuntimeError("Installed Blender FBX exporter lacks required options: " + repr(missing))
    bpy.ops.export_scene.fbx(**options)
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError("FBX export failed: " + str(path))


def reset_bones(rig, face):
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    for key in face.data.shape_keys.key_blocks:
        key.value = 0


def scaled_action(source, hold_pose=False):
    duplicate = source.copy()
    duplicate.use_fake_user = True
    for layer in duplicate.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    if hold_pose and len(curve.keyframe_points) == 1:
                        key = curve.keyframe_points[0]
                        curve.keyframe_points.insert(key.co.x + 1.0, key.co.y, options={'FAST'})
                    if not curve.data_path.endswith(".location"):
                        continue
                    for key in curve.keyframe_points:
                        key.co.y *= 100.0
                        key.handle_left.y *= 100.0
                        key.handle_right.y *= 100.0
    return duplicate


def prepare_export_skeleton(rig, face, props, bodies):
    for obj in (face, props, *bodies):
        obj.scale = (100.0, 100.0, 100.0)
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    rest = {bone.name: bone.matrix.copy() for bone in rig.data.edit_bones}
    for bone in rig.data.edit_bones:
        bone.use_connect = False
    for bone in rig.data.edit_bones:
        bone.matrix = Matrix.Scale(100.0, 4) @ rest[bone.name]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()


def export_mesh(rig, face, props, bodies):
    rig.animation_data.action = None
    face.data.shape_keys.animation_data.action = None
    reset_bones(rig, face)
    bpy.context.scene.frame_set(0)
    lod_objects = []
    for index, body in enumerate(bodies):
        collection = bpy.data.collections.new("EXPORT_JOIN_" + str(index))
        bpy.context.scene.collection.children.link(collection)
        duplicates = []
        for original in (face, body, props):
            duplicate = original.copy()
            duplicate.data = original.data.copy()
            duplicate.name = "ExportPart_" + original.name
            collection.objects.link(duplicate)
            duplicates.append(duplicate)
        select_only(duplicates)
        bpy.context.view_layer.objects.active = duplicates[0]
        bpy.ops.object.join()
        joined = bpy.context.object
        joined.name = "Operative_LOD" + str(index)
        if not joined.data.shape_keys or len(joined.data.shape_keys.key_blocks) != 27:
            raise RuntimeError("The export join did not preserve all 26 facial shapes plus Basis")
        lod_objects.append(joined)
        print("MESH_LOD_PREPARED", joined.name, flush=True)
    for index, lod in enumerate(lod_objects):
        fbx(EXPORT / f"Operative_LOD{index}.fbx", [rig, lod], False)
    fbx(EXPORT / "Operative.fbx", [rig, lod_objects[0]], False)
    print("MESH_EXPORTED Operative.fbx as LOD0; Operative_LOD0/1/2.fbx are the explicit LOD import files", flush=True)


def export_animations(rig, face, manifest):
    folder = EXPORT / "animations"
    folder.mkdir(parents=True, exist_ok=True)
    for entry in manifest["entries"]:
        name = entry["id"]
        if not bpy.data.actions.get(name) or not bpy.data.actions.get(name + "_FACE"):
            raise RuntimeError("Missing authored action or facial action: " + name)
        reset_bones(rig, face)
        hold_pose = entry["form"] == "pose"
        rig.animation_data.action = scaled_action(bpy.data.actions[name], hold_pose)
        rig.animation_data.action_slot = rig.animation_data.action.slots[0]
        face.data.shape_keys.animation_data.action = scaled_action(bpy.data.actions[name + "_FACE"], hold_pose)
        face.data.shape_keys.animation_data.action_slot = face.data.shape_keys.animation_data.action.slots[0]
        scene = bpy.context.scene
        scene.frame_start, scene.frame_end = entry["frame_range"]
        if hold_pose:
            scene.frame_end += 1
        scene.frame_set(entry["frame_range"][0])
        fbx(folder / (name + ".fbx"), [rig, face], True)
        print("ANIMATION_EXPORTED", name, entry["frame_count"], flush=True)


def skeleton_document(rig, manifest):
    points = {item["id"]: item for item in json.loads((ROOT / "source" / "animation_inventory.json").read_text())}
    bones = []
    for bone in rig.data.bones:
        bones.append({
            "name": bone.name, "parent": bone.parent.name if bone.parent else None,
            "source_head_m": list(bone.head_local), "source_tail_m": list(bone.tail_local),
            "source_rest_matrix": [list(row) for row in bone.matrix_local],
            "use_deform": bone.use_deform,
        })
    elbow, wrist = Vector((-.277, -.016, 1.183)), Vector((-.305, -.036, .962))
    direction = (wrist - elbow).normalized()
    center = elbow.lerp(wrist, .64) + Vector((0, -.037, 0))
    blade_start = elbow.lerp(wrist, .40) + Vector((-.037, -.006, 0))
    socket_world = {
        "hand_right": ("hand.R", wrist), "hand_left": ("hand.L", Vector((.305, -.036, .962))),
        "emitter_muzzle": ("forearm.R", center + direction * .108),
        "blade_base": ("blade_slide", blade_start), "blade_tip": ("blade_slide", blade_start + direction * .305),
        "power_cell": ("cell", elbow.lerp(wrist, .69) + Vector((0, -.084, 0))),
        "beacon": ("beacon", Vector((.17, .075, 1.023))),
        "fx_chest": ("spine_03", Vector((0, -.13, 1.34))),
        "fx_head": ("head", Vector((0, -.10, 1.73))),
        "look_at": ("head", Vector((0, -.70, 1.67))),
    }
    sockets = []
    for name, (bone_name, world) in socket_world.items():
        bone = rig.data.bones[bone_name]
        local = bone.matrix_local.inverted() @ world
        sockets.append({
            "name": name, "bone": bone_name,
            "source_world_m": list(world), "source_bone_local_m": list(local),
            "unreal_bone_local_offset_cm": [value * 100 for value in local],
            "rotation": "Identity in source bone space; validate imported socket basis in Unreal before attaching effects",
        })
    data = {
        "schema": "MorphRig.skeleton_and_sockets/1.2",
        "source_units": "meters, scale_length=1; one Blender unit is one meter",
        "unreal_units": "centimeters; the temporary export skeleton and bone-location channels are explicitly converted from source meters once. Connected flags are detached only during that temporary uniform rest-transform conversion. Mesh-object export scale is 100. Unreal convert_scene_unit=False consumes these explicit centimeter transforms without a second conversion; import_uniform_scale remains 1. The editable .blend is never rescaled or overwritten by the exporter",
        "source_axes": "Z up, forward -Y, anatomical left +X, ground-origin root",
        "unreal_axes": "Z up, centimeters; imported facing is audited in unreal_import_audit.json; showcase actor convention is +X forward",
        "bone_axes": "Blender local +Y follows each bone; X/Z roll is zero at authoring; actual Unreal reference transforms are audited after FBX import",
        "root": "root at (0,0,0), independent of pelvis, exactly one root; every other bone is connected through named parents",
        "deformation_bone_count": len(bones), "bones": bones, "sockets": sockets,
        "fbx": {"global_scale": 1.0, "apply_unit_scale": False, "apply_scale_options": "FBX_SCALE_UNITS", "bake_space_transform": False, "axis_forward": "-Z", "axis_up": "Y", "leaf_bones": False, "deform_only": True, "unreal_convert_scene_unit": False, "export_skeleton_units": "centimeters", "mesh_object_scale": 100},
        "source_height_m": 1.80, "target_unreal_height_cm": 180,
        "animation_names": list(points),
    }
    (DOCS / "skeleton_and_sockets.json").write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')


def main():
    EXPORT.mkdir(exist_ok=True)
    rig = bpy.data.objects["Operative_DEF"]
    rig.name = "armature"
    face = bpy.data.objects["Operative_Face"]
    props = bpy.data.objects["Operative_Props"]
    bodies = [bpy.data.objects[f"Operative_Body_LOD{i}"] for i in range(3)]
    ctrl = bpy.data.objects["Operative_CTRL"]
    ctrl.animation_data.action = None
    for collection in bpy.data.collections:
        if collection.name.startswith(("02_CHARACTER", "03_CHARACTER")):
            collection.hide_viewport = False
    for bone in rig.pose.bones:
        for constraint in bone.constraints:
            constraint.influence = 0
    manifest = json.loads((DOCS / "animation_manifest.json").read_text())
    skeleton_document(rig, manifest)
    prepare_export_skeleton(rig, face, props, bodies)
    if "--animations-only" not in sys.argv:
        export_mesh(rig, face, props, bodies)
    if "--mesh-only" not in sys.argv:
        export_animations(rig, face, manifest)
    result = {"mesh": "export/Operative.fbx", "lods": ["export/Operative_LOD0.fbx", "export/Operative_LOD1.fbx", "export/Operative_LOD2.fbx"], "animations": len(manifest["entries"]), "fps": 30, "status": "exported; Unreal import audit is separate"}
    (DOCS / "validation" / "blender_export.json").write_text(json.dumps(result, indent=2) + "\n", encoding='utf-8')
    print("BLENDER_EXPORT_COMPLETE", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()

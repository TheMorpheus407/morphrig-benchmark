"""Headless, reproducible Unreal import and persisted-asset audit.
Run through the supplied ue-exec wrapper with UnrealEditor-Cmd and -run=pythonscript.
All paths are derived from this file; the game does not depend on this editor script.
"""
from pathlib import Path
import json
import shutil
import sys
import traceback
import unreal

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "unreal" / "MorphRig"
DOCS = ROOT / "docs"
EXPORT = ROOT / "export"
AT = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.AnimationLibrary
MESH_EDITOR = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
MANIFEST = json.loads((DOCS / "animation_manifest.json").read_text())
ENTRIES = MANIFEST["entries"]
ASSET_ROOT = "/Game/Operative"
SAVE = []


def log(message, *args):
    unreal.log_warning("MORPH_IMPORT " + str(message) + " " + " ".join(str(value) for value in args))


def props(obj, values):
    for name, value in values.items():
        obj.set_editor_property(name, value)


def run_task(source, destination, name, options, factory):
    task = unreal.AssetImportTask()
    task.filename = str(source)
    task.destination_path = destination
    task.destination_name = name
    task.replace_existing = True
    task.replace_existing_settings = True
    task.automated = True
    task.save = True
    task.async_ = False
    task.factory = factory
    task.options = options
    AT.import_asset_tasks([task])
    objects = list(task.get_objects())
    if not objects:
        raise RuntimeError(f"No assets imported from {source}")
    log("imported", source.name, [obj.get_path_name() for obj in objects])
    SAVE.extend(objects)
    return objects


def create_or_load_asset(name, package_path, asset_class, factory):
    existing = unreal.load_asset(package_path + "/" + name)
    if existing:
        return existing, False
    created = AT.create_asset(name, package_path, asset_class, factory)
    if created is None:
        raise RuntimeError("Could not create asset " + package_path + "/" + name)
    return created, True


def shared_transform(data):
    props(data, {
        "import_translation": unreal.Vector(0, 0, 0),
        "import_rotation": unreal.Rotator(0, 0, 0),
        "import_uniform_scale": 1.0,
        "convert_scene": True,
        "convert_scene_unit": False,
        "force_front_x_axis": True,
        "coordinate_system_policy": unreal.CoordinateSystemPolicy.MATCH_UP_FORWARD_AXES,
    })


def skeletal_options():
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.original_import_type = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.import_as_skeletal = True
    options.import_mesh = True
    options.import_animations = False
    options.import_materials = True
    options.import_textures = True
    options.create_physics_asset = False
    options.override_full_name = True
    props(options.skeletal_mesh_import_data, {
        "import_morph_targets": True, "import_mesh_lods": True,
        "import_meshes_in_bone_hierarchy": True,
        "update_skeleton_reference_pose": True, "use_t0_as_ref_pose": False,
        "normal_import_method": unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS,
    })
    shared_transform(options.skeletal_mesh_import_data)
    props(options.anim_sequence_import_data, {"add_curve_metadata_to_skeleton": True})
    return options


def animation_options(skeleton):
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_ANIMATION
    options.original_import_type = unreal.FBXImportType.FBXIT_ANIMATION
    options.import_mesh = False
    options.import_animations = True
    options.import_materials = False
    options.import_textures = False
    options.skeleton = skeleton
    options.override_full_name = True
    props(options.anim_sequence_import_data, {
        "animation_length": unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME,
        "use_default_sample_rate": False, "custom_sample_rate": 30,
        "snap_to_closest_frame_boundary": False, "import_bone_tracks": True,
        "import_custom_attribute": True, "add_curve_metadata_to_skeleton": True,
        "do_not_import_curve_with_zero": False, "delete_existing_morph_target_curves": True,
        "delete_existing_custom_attribute_curves": True,
        "delete_existing_non_curve_custom_attributes": True,
        "remove_redundant_keys": False, "preserve_local_transform": False,
        "import_meshes_in_bone_hierarchy": True,
    })
    shared_transform(options.anim_sequence_import_data)
    return options


def import_mesh():
    import math
    editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    staging_path = ASSET_ROOT + "/Diagnostics/BasisSource"
    for name in ("dash_l_basis_source", "idle_relaxed_basis_source", "SK_Operative_BasisSource", "SK_Operative_BasisSource_Skeleton", "Operative_LOD0_Skeleton", "SK_AnimationSource", "AnimationSource_Skeleton"):
        asset = staging_path + "/" + name
        if unreal.load_asset(asset) and not editor.delete_asset(asset):
            raise RuntimeError("Could not reset isolated staging asset " + asset)
    unreal.SystemLibrary.collect_garbage()
    staging_options = skeletal_options()
    staging_options.skeletal_mesh_import_data.import_mesh_lods = False
    staging_objects = run_task(EXPORT / "Operative_LOD0.fbx", staging_path, "SK_Operative_BasisSource", staging_options, unreal.FbxFactory())
    staging_mesh = next(obj for obj in staging_objects if isinstance(obj, unreal.SkeletalMesh))
    staging_skeleton = staging_mesh.skeleton
    if not staging_skeleton or not staging_skeleton.get_path_name().startswith(staging_path + "/") or len(staging_skeleton.get_reference_pose().get_bone_names()) != 70:
        raise RuntimeError("Isolated FBX skeleton mismatch: " + (staging_skeleton.get_path_name() + " bones=" + str(len(staging_skeleton.get_reference_pose().get_bone_names())) if staging_skeleton else "None"))
    if not editor.save_asset(staging_skeleton.get_path_name().split(".")[0], only_if_is_dirty=False):
        raise RuntimeError("The isolated deformation skeleton must be persisted before importing animation")
    source_evidence = infer_import_rotation(staging_mesh)
    if source_evidence["source_to_unreal_matrix"] != [[0, -1, 0], [-1, 0, 0], [0, 0, 1]]:
        raise RuntimeError("Isolated source skeleton did not recover the documented original matrix: " + repr(source_evidence))
    source_root_error = math.degrees(staging_skeleton.get_reference_pose().get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL).rotation.angular_distance(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(staging_mesh, "root").rotation))
    if source_root_error > .001:
        raise RuntimeError("The isolated skeleton and mesh have different root bases: " + str(source_root_error))
    SAVE.extend([staging_mesh, staging_skeleton])
    if not editor.save_asset(staging_mesh.get_path_name().split(".")[0], only_if_is_dirty=False):
        raise RuntimeError("Could not persist the source-correct isolated mesh")

    if unreal.load_asset(ASSET_ROOT + "/SK_Operative"):
        previous_mesh = ASSET_ROOT + "/Diagnostics/SK_Operative_PreviousMesh"
        suffix = 2
        while unreal.EditorAssetLibrary.does_asset_exist(previous_mesh):
            previous_mesh = ASSET_ROOT + "/Diagnostics/SK_Operative_PreviousMesh" + str(suffix)
            suffix += 1
        if not editor.rename_asset(ASSET_ROOT + "/SK_Operative", previous_mesh):
            raise RuntimeError("Could not preserve the previous generated mesh")
        unreal.SystemLibrary.collect_garbage()
    skeleton_path = ASSET_ROOT + "/SK_Operative_Skeleton"
    existing_skeleton = unreal.load_asset(skeleton_path)
    if existing_skeleton:
        if len(existing_skeleton.get_reference_pose().get_bone_names()) != 70:
            raise RuntimeError("Refusing to replace a skeleton that is not the authored 70-bone hierarchy")
        legacy = ASSET_ROOT + "/Diagnostics/SK_Operative_LegacySkeleton"
        suffix = 2
        while unreal.EditorAssetLibrary.does_asset_exist(legacy):
            legacy = ASSET_ROOT + "/Diagnostics/SK_Operative_LegacySkeleton" + str(suffix)
            suffix += 1
        if not editor.rename_asset(skeleton_path, legacy):
            raise RuntimeError("Could not preserve the previous generated skeleton before rebuilding its basis")
        if unreal.EditorAssetLibrary.does_asset_exist(skeleton_path):
            raise RuntimeError("The old skeleton did not vacate the required asset path")
    production_skeleton = unreal.EditorAssetLibrary.duplicate_asset(staging_skeleton.get_path_name().split(".")[0], skeleton_path)
    if not production_skeleton:
        raise RuntimeError("Could not copy the validated source skeleton to the production path")
    final_staging_path = staging_path + "/SK_Operative_Final"
    if unreal.load_asset(final_staging_path) and not editor.delete_asset(final_staging_path):
        raise RuntimeError("Could not reset the final mesh staging asset")
    options = skeletal_options()
    options.skeletal_mesh_import_data.import_mesh_lods = False
    options.skeleton = production_skeleton
    objects = run_task(EXPORT / "Operative_LOD0.fbx", staging_path, "SK_Operative_Final", options, unreal.FbxFactory())
    meshes = [obj for obj in objects if isinstance(obj, unreal.SkeletalMesh)]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one combined skeletal mesh, got {[m.get_name() for m in meshes]}")
    mesh = meshes[0]
    actual_skeleton = mesh.skeleton.get_path_name().split(".")[0] if mesh.skeleton else "None"
    if actual_skeleton != skeleton_path or len(mesh.skeleton.get_reference_pose().get_bone_names()) != 70:
        raise RuntimeError(f"Production skeleton mismatch: actual={actual_skeleton}, expected={skeleton_path}")
    if not editor.rename_asset(final_staging_path, ASSET_ROOT + "/SK_Operative"):
        raise RuntimeError("Could not move the freshly imported final mesh into the production path")
    if not editor.save_asset(mesh.skeleton.get_path_name().split(".")[0], only_if_is_dirty=False):
        raise RuntimeError("The deformation skeleton must be persisted before importing animation")
    SAVE.extend([mesh, mesh.skeleton])
    for lod in (1, 2):
        imported = MESH_EDITOR.import_lod(mesh, lod, str(EXPORT / f"Operative_LOD{lod}.fbx"))
        triangles = unreal.MorphAuditLibrary.get_lod_triangle_count(mesh, lod)
        log("native_lod_import", lod, imported, triangles)
        if imported != lod or triangles <= 0:
            raise RuntimeError(f"Native import_lod failed for LOD{lod}: {imported}, triangles={triangles}")
    log("fresh_mesh_validation", mesh.get_bounds().box_extent.z * 2, len(mesh.get_all_morph_target_names()), MESH_EDITOR.get_lod_count(mesh))
    if not 179 <= mesh.get_bounds().box_extent.z * 2 <= 181 or len(mesh.get_all_morph_target_names()) != 26:
        raise RuntimeError("Fresh mesh did not satisfy the 180cm and 26-morph requirements")
    if MESH_EDITOR.get_lod_count(mesh) != 3:
        raise RuntimeError("Expected three imported LODs")
    models = list(mesh.get_editor_property("source_models"))
    for index, screen_size in enumerate((1.0, .30, .12)):
        model = models[index]
        screen = model.get_editor_property("screen_size")
        screen.set_editor_property("default", screen_size)
        model.set_editor_property("screen_size", screen)
        models[index] = model
    mesh.set_editor_property("source_models", models)
    log("mesh and 3 LODs ready", mesh.get_path_name())
    return mesh


def import_textures_and_materials(mesh):
    specs = {
        "M_Skin": ("skin", .0, False), "M_Suit": ("suit", .0, False),
        "M_Armor": ("armor", .68, False), "M_Metal": ("metal", .90, False),
        "M_Accent": ("accent", .35, False), "M_Emissive": ("emissive", .25, True),
        "M_Eye": ("eye", .0, False), "M_Hair": ("hair", .05, False),
    }
    materials = {}
    for material_name, (token, metal, emissive) in specs.items():
        maps = {}
        for kind in ("BaseColor", "Roughness", "Normal"):
            filename = EXPORT / "textures" / f"{token}_{kind}.png"
            obj = run_task(filename, ASSET_ROOT + "/Textures", f"{token}_{kind}", None, unreal.TextureFactory())[0]
            obj.set_editor_property("srgb", kind == "BaseColor")
            if kind == "Normal":
                obj.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            maps[kind] = obj
        material, created = create_or_load_asset(material_name, ASSET_ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
        material.set_editor_property("used_with_skeletal_mesh", True)
        material.set_editor_property("used_with_morph_targets", True)
        if not created:
            materials[material_name] = material
            SAVE.append(material)
            continue
        nodes = {}
        for index, (kind, texture) in enumerate(maps.items()):
            expression = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionTextureSample, -700, index * 230)
            expression.set_editor_property("texture", texture)
            nodes[kind] = expression
        mel = unreal.MaterialEditingLibrary
        if material_name == "M_Accent":
            tint = mel.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -700, 730)
            tint.set_editor_property("parameter_name", "TeamAccent")
            tint.set_editor_property("default_value", unreal.LinearColor(.035, .48, .68, 1))
            multiply = mel.create_material_expression(material, unreal.MaterialExpressionMultiply, -350, 250)
            mel.connect_material_expressions(nodes["BaseColor"], "RGB", multiply, "A")
            mel.connect_material_expressions(tint, "", multiply, "B")
            mel.connect_material_property(multiply, "", unreal.MaterialProperty.MP_BASE_COLOR)
        else:
            mel.connect_material_property(nodes["BaseColor"], "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        mel.connect_material_property(nodes["Roughness"], "RGB", unreal.MaterialProperty.MP_ROUGHNESS)
        mel.connect_material_property(nodes["Normal"], "RGB", unreal.MaterialProperty.MP_NORMAL)
        scalar = mel.create_material_expression(material, unreal.MaterialExpressionConstant, -300, -250)
        scalar.set_editor_property("r", metal)
        mel.connect_material_property(scalar, "", unreal.MaterialProperty.MP_METALLIC)
        if emissive:
            strength = mel.create_material_expression(material, unreal.MaterialExpressionConstant, -300, 700)
            strength.set_editor_property("r", 3.0)
            multiply = mel.create_material_expression(material, unreal.MaterialExpressionMultiply, -100, 550)
            mel.connect_material_expressions(nodes["BaseColor"], "RGB", multiply, "A")
            mel.connect_material_expressions(strength, "", multiply, "B")
            mel.connect_material_property(multiply, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        materials[material_name] = material
        SAVE.append(material)
    slots = list(mesh.get_editor_property("materials"))
    if len(slots) > 8:
        raise RuntimeError(f"Too many material slots: {len(slots)}")
    for slot in slots:
        name = str(slot.material_slot_name)
        if name not in materials:
            raise RuntimeError("Unexpected character material slot " + name)
    if not unreal.MorphAuditLibrary.set_material_slots(mesh, [materials[str(slot.material_slot_name)] for slot in slots]):
        raise RuntimeError("Native material slot assignment did not retain the authored material pointers")
    accent = materials["M_Accent"]
    for team, color in (("Cyan", unreal.LinearColor(.035, .48, .68, 1)), ("Amber", unreal.LinearColor(.90, .31, .055, 1))):
        instance, _ = create_or_load_asset("MI_Team_" + team, ASSET_ROOT + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance, accent)
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, "TeamAccent", color)
        unreal.MaterialEditingLibrary.update_material_instance(instance)
        SAVE.append(instance)
    log("authored textures, materials and team variants ready")


def import_audio():
    run_task(ROOT / "source" / "audio" / "dialogue.wav", ASSET_ROOT + "/Audio", "Dialogue", None, unreal.SoundFactory())
    (PROJECT / "Content" / "Operative").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS / "animation_manifest.json", PROJECT / "Content" / "Operative" / "animation_manifest.json")
    (PROJECT / "Content" / "Operative" / "Audio").mkdir(parents=True, exist_ok=True)
    for filename in ("dialogue.txt", "dialogue_alignment.json"):
        shutil.copy2(ROOT / "source" / "audio" / filename, PROJECT / "Content" / "Operative" / "Audio" / filename)
    log("dialogue audio, transcript and alignment ready")


def vec(value):
    return [value.x, value.y, value.z]


def unreal_bone_name(name):
    return name.replace(".", "_")


def infer_import_rotation(mesh):
    import itertools
    import math
    expected = {
        "eye.L": (3.7, -5.8, 169.7), "hand.L": (30.5, -3.6, 96.2),
        "hand.R": (-30.5, -3.6, 96.2), "pelvis": (0.0, 0.0, 99.5),
        "head": (0.0, 0.0, 155.5),
    }
    actual = {name: vec(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, unreal_bone_name(name)).translation) for name in expected}
    candidates = []
    for x_axis, y_axis, z_axis in itertools.permutations(range(3)):
        for signs in itertools.product((-1, 1), repeat=3):
            matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            matrix[0][x_axis], matrix[1][y_axis], matrix[2][z_axis] = signs
            error = 0.0
            for name, source in expected.items():
                transformed = [sum(matrix[row][column] * source[column] for column in range(3)) for row in range(3)]
                error += sum((transformed[index] - actual[name][index]) ** 2 for index in range(3))
            candidates.append((error, matrix))
    _, matrix = min(candidates, key=lambda item: item[0])
    determinant = matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1]) - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0]) + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    forward = [-matrix[0][1], -matrix[1][1], -matrix[2][1]]
    yaw = math.degrees(math.atan2(forward[1], forward[0]))
    samples, maximum = [], 0.0
    for name, source in expected.items():
        transformed = [sum(matrix[row][column] * source[column] for column in range(3)) for row in range(3)]
        maximum = max(maximum, math.sqrt(sum((transformed[index] - actual[name][index]) ** 2 for index in range(3))))
        samples.append({"bone": name, "source_cm": source, "native_cm": actual[name], "converted_source_cm": transformed})
    return {
        "source_to_unreal_matrix": matrix, "determinant": determinant,
        "native_forward": forward, "max_reference_error_cm": maximum,
        "reference_samples": samples, "mesh_reference_forward_yaw": yaw,
        "source_to_unreal_yaw_degrees": None,
    }


def rotate_source_cm(source, evidence):
    matrix = evidence["source_to_unreal_matrix"]
    source = [value * 100 for value in source]
    return tuple(sum(matrix[row][column] * source[column] for column in range(3)) for row in range(3))


def create_sockets(mesh):
    document = json.loads((DOCS / "skeleton_and_sockets.json").read_text())
    reference = mesh.skeleton.get_reference_pose()
    actual_bones = {str(name) for name in reference.get_bone_names()}
    evidence = infer_import_rotation(mesh)
    previous_evidence = document.get("axis_evidence", {})
    evidence["evaluated_body_forward"] = evidence["native_forward"]
    evidence["showcase_mesh_yaw"] = evidence["mesh_reference_forward_yaw"]
    evidence["root_motion_mesh_yaw"] = previous_evidence.get("root_motion_mesh_yaw", 0.0)
    for key in ("root_reference_alignment", "root_motion_basis_evidence"):
        if key in previous_evidence:
            evidence[key] = previous_evidence[key]
    document["axis_evidence"] = evidence
    log("imported bone names", sorted(actual_bones))
    for bone in document["bones"]:
        bone["unreal_name"] = unreal_bone_name(bone["name"])
    for item in document["sockets"]:
        bone_name = unreal_bone_name(item["bone"])
        item["unreal_bone"] = bone_name
        existing = mesh.find_socket(item["name"])
        if existing is None:
            socket = unreal.new_object(unreal.SkeletalMeshSocket, outer=mesh)
            socket.set_socket_parent(mesh, bone_name)
            mesh.modify()
            mesh.add_socket(socket, False)
            if not MESH_EDITOR.rename_socket(mesh, str(socket.socket_name), item["name"]):
                raise RuntimeError("Could not name socket " + item["name"])
            socket = mesh.find_socket(item["name"])
        else:
            socket = existing
            socket.set_socket_parent(mesh, bone_name)
        source_world = item["source_world_m"]
        native_world = rotate_source_cm(source_world, evidence)
        target = unreal.Transform(location=unreal.Vector(*native_world))
        bone = unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, bone_name)
        local = target.make_relative(bone)
        socket.set_socket_local_transform(local)
        item["unreal_local_transform"] = {
            "translation_cm": vec(local.translation),
            "rotation_quaternion": [local.rotation.x, local.rotation.y, local.rotation.z, local.rotation.w],
            "scale": vec(local.scale3d),
        }
        item["unreal_component_rest_cm"] = native_world
    document["bone_name_mapping"] = "The FBX importer replaces '.' with '_' in bone and morph names. unreal_name/unreal_bone records the exact one-to-one native mapping."
    document["unreal_facing"] = f"Measured source-to-Unreal basis {evidence['source_to_unreal_matrix']}; source forward -Y maps to {evidence['native_forward']}. Mesh-relative yaw is {evidence['showcase_mesh_yaw']:g} degrees to face actor +X. Baked local transforms are preserved; measured animation-to-mesh yaw is {evidence['root_motion_mesh_yaw']:g} degrees before CharacterMovement sweeps the capsule. Scale remains one."
    (DOCS / "skeleton_and_sockets.json").write_text(json.dumps(document, indent=2) + "\n")
    log("sockets created from actual imported reference transforms", len(document["sockets"]))


def import_animations(mesh):
    source_skeleton = mesh.skeleton
    if not source_skeleton or len(source_skeleton.get_reference_pose().get_bone_names()) != 70:
        raise RuntimeError("The original 70-bone production skeleton must be persisted before clip import")
    unreal.log_warning(f"MORPH_SOURCE_SKELETON {source_skeleton.get_path_name()} bones={len(source_skeleton.get_reference_pose().get_bone_names())}")
    missing_sources = [entry["id"] for entry in ENTRIES if not (EXPORT / "animations" / (entry["id"] + ".fbx")).is_file()]
    if missing_sources:
        raise RuntimeError("Refusing to retire native clips with missing FBX sources: " + repr(missing_sources))
    editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    for entry in reversed(ENTRIES):
        asset = entry["unreal_asset"]
        if unreal.load_asset(asset) and not editor.delete_asset(asset):
            raise RuntimeError("Could not retire generated animation before rebinding: " + asset)
    sequences = {}
    for index, entry in enumerate(ENTRIES):
        name = entry["id"]
        objects = run_task(EXPORT / "animations" / (name + ".fbx"), ASSET_ROOT + "/Diagnostics/BasisSource", name, animation_options(source_skeleton), unreal.FbxFactory())
        sequence = next((obj for obj in objects if isinstance(obj, unreal.AnimSequence)), None)
        if sequence is None:
            raise RuntimeError("Animation import did not produce an AnimSequence: " + name)
        if sequence.get_editor_property("skeleton").get_path_name() != source_skeleton.get_path_name():
            raise RuntimeError(f"Clip {name} retained the wrong skeleton: {sequence.get_editor_property('skeleton').get_path_name()} != {source_skeleton.get_path_name()}")
        sequence.set_editor_property("enable_root_motion", entry["root_motion_policy"] == "root_motion")
        if entry["form"] == "additive":
            sequence.set_editor_property("additive_anim_type", unreal.AdditiveAnimationType.AAT_ROTATION_OFFSET_MESH_SPACE)
            sequence.set_editor_property("ref_pose_type", unreal.AdditiveBasePoseType.ABPT_ANIM_FRAME)
            sequence.set_editor_property("ref_frame_index", 0)
            sequence.set_editor_property("ref_pose_seq", unreal.load_asset(ASSET_ROOT + "/Diagnostics/BasisSource/idle_relaxed"))
        sequences[name] = sequence
        if index % 8 == 0:
            log("animation progress", index + 1, len(ENTRIES))
    if not unreal.MorphAuditLibrary.align_animation_root_to_reference(mesh, mesh, list(sequences.values())):
        raise RuntimeError("Root-reference alignment failed while preserving the authored local tracks")
    for entry in ENTRIES:
        if not editor.rename_asset(ASSET_ROOT + "/Diagnostics/BasisSource/" + entry["id"], entry["unreal_asset"]):
            raise RuntimeError("Could not move the aligned clip into its required asset path: " + entry["id"])
    for entry in ENTRIES:
        sequence = unreal.load_asset(entry["unreal_asset"])
        if not sequence or sequence.get_editor_property("skeleton").get_path_name() != mesh.skeleton.get_path_name():
            raise RuntimeError("Final clip did not persist with the original target skeleton: " + entry["id"])
        sequences[entry["id"]] = sequence
        sequence.set_editor_property("enable_root_motion", entry["root_motion_policy"] == "root_motion")
        if entry["form"] == "additive":
            sequence.set_editor_property("ref_pose_seq", sequences["idle_relaxed"])
    SAVE.extend(sequences.values())
    SAVE.append(source_skeleton)
    log("Imported all 96 authored clips onto the original reference skeleton")
    return sequences


def align_reference_basis(mesh, sequences):
    import math
    document = json.loads((DOCS / "skeleton_and_sockets.json").read_text())
    bones = [str(name) for name in mesh.skeleton.get_reference_pose().get_bone_names()]

    def local_reference():
        transforms = {}
        parents = {}
        for name in bones:
            transform = unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, name)
            parent = str(MESH_EDITOR.get_bone_parent(mesh, name))
            if parent != "None":
                transform = transform.make_relative(unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, parent))
            transforms[name] = transform
            parents[name] = parent
        return transforms, parents

    before, parents_before = local_reference()
    idle_root = LIB.get_bone_pose_for_frame(sequences["idle_relaxed"], "root", 0, False)
    alignment_error = math.degrees(before["root"].rotation.angular_distance(idle_root.rotation))
    if alignment_error > .001 and not unreal.MorphAuditLibrary.align_root_reference_to_animation(mesh, sequences["idle_relaxed"]):
        raise RuntimeError("Could not align the root reference with the actual imported idle root")
    log("final root alignment check", alignment_error, "degrees")
    corrected_evidence = infer_import_rotation(mesh)
    if corrected_evidence["source_to_unreal_matrix"] != [[0, -1, 0], [-1, 0, 0], [0, 0, 1]]:
        raise RuntimeError("Root alignment changed the documented original mesh-reference matrix: " + repr(corrected_evidence))
    after, parents_after = local_reference()
    non_root_changes = []
    for name in bones:
        if name == "root":
            continue
        position_error = math.dist(vec(before[name].translation), vec(after[name].translation))
        angle_error = math.degrees(before[name].rotation.angular_distance(after[name].rotation))
        scale_error = max(abs(value - other) for value, other in zip(vec(before[name].scale3d), vec(after[name].scale3d)))
        if position_error > .001 or angle_error > .001 or scale_error > .00001:
            non_root_changes.append({"bone": name, "position_error_cm": position_error, "angle_error_degrees": angle_error, "scale_error": scale_error})
    idle_root = LIB.get_bone_pose_for_frame(sequences["idle_relaxed"], "root", 0, False)
    root_rotation_error = math.degrees(after["root"].rotation.angular_distance(idle_root.rotation))
    root_location_error = math.dist(vec(before["root"].translation), vec(after["root"].translation))
    root_scale_error = max(abs(value - other) for value, other in zip(vec(before["root"].scale3d), vec(after["root"].scale3d)))
    hierarchy_unchanged = parents_before == parents_after
    record = {
        "method": "Direct import onto the original reference skeleton; measured root-frame correction aligns orientation and translation through the public animation-data-model API, preserving every other local bone channel and nominal displacement",
        "final_mesh_root_update_performed": alignment_error > .001,
        "non_root_bones": 69, "non_root_local_changes": non_root_changes,
        "hierarchy_unchanged": hierarchy_unchanged,
        "root_location_error_cm": root_location_error, "root_scale_error": root_scale_error,
        "root_rotation_error_degrees": root_rotation_error,
    }
    source_evidence = infer_import_rotation(mesh)
    raw_left = vec(unreal.MorphAuditLibrary.get_root_motion_delta(sequences["dash_l"], 0.0, sequences["dash_l"].get_play_length()))
    expected_left = rotate_source_cm([2, 0, 0], source_evidence)
    basis_yaw = math.degrees(math.atan2(raw_left[0] * expected_left[1] - raw_left[1] * expected_left[0], raw_left[0] * expected_left[0] + raw_left[1] * expected_left[1]))
    if abs(basis_yaw) > .01 or abs(math.sqrt(sum(value * value for value in raw_left)) - 200) > .5:
        raise RuntimeError(f"Unexpected native root-motion basis: raw_left={raw_left}, expected_left={expected_left}, yaw={basis_yaw}")
    document["axis_evidence"]["root_reference_alignment"] = record
    document["axis_evidence"]["root_motion_mesh_yaw"] = basis_yaw
    document["axis_evidence"]["root_motion_basis_evidence"] = {
        "raw_left_track_cm": raw_left, "expected_actor_left_cm": expected_left,
        "track_to_mesh_yaw_degrees": basis_yaw,
        "description": "Baked local bone transforms are preserved at import. The measured animation-to-mesh yaw is zero, so no additional dash rotation or scale repair is applied.",
    }
    (DOCS / "skeleton_and_sockets.json").write_text(json.dumps(document, indent=2) + "\n")
    if non_root_changes or not hierarchy_unchanged or root_location_error > .001 or root_scale_error > .00001 or root_rotation_error > .001:
        raise RuntimeError("Reference-basis correction violated the hierarchy, root placement or animation basis: " + repr(record))
    SAVE.extend([mesh, mesh.skeleton, sequences["idle_relaxed"]])
    log("root reference aligned with imported idle; all 69 non-root locals unchanged")


def import_events(sequences):
    notify_class = getattr(unreal, "MorphEventNotify", None)
    if notify_class is None:
        raise RuntimeError("The compiled MorphEventNotify class is required for named native event assets; run the native build before event import")
    for entry in ENTRIES:
        sequence = sequences[entry["id"]]
        sequence.modify()
        for track in LIB.get_animation_notify_track_names(sequence):
            LIB.remove_animation_notify_events_by_track(sequence, track)
        if not LIB.is_valid_anim_notify_track_name(sequence, "MorphEvents"):
            LIB.add_animation_notify_track(sequence, "MorphEvents")
        for marker in entry["events"]:
            notify = LIB.add_animation_notify_event(sequence, "MorphEvents", float(marker["time"]), notify_class)
            if notify is None:
                raise RuntimeError("Could not create event " + marker["name"])
            notify.set_editor_property("event_name", marker["name"])
            notify.set_editor_property("event_type", marker["type"])
            notify.set_editor_property("value", float(marker["value"]))
        for event in LIB.get_animation_notify_events(sequence):
            notify = event.get_editor_property("notify")
            if isinstance(notify, notify_class):
                if not unreal.MorphAuditLibrary.set_notify_name(sequence, notify, notify.get_editor_property("event_name")):
                    raise RuntimeError("Could not set native notify name on " + entry["id"])
    log("named native event markers ready")


def audit(mesh, sequences, require_events=False):
    import math
    reference = mesh.skeleton.get_reference_pose()
    bones = [str(name) for name in reference.get_bone_names()]
    roots = [name for name in bones if str(MESH_EDITOR.get_bone_parent(mesh, name)) == "None"]
    bounds = mesh.get_bounds()
    morph_names = [str(name) for name in mesh.get_all_morph_target_names()]
    source_geometry = json.loads((DOCS / "source_geometry_report.json").read_text())
    failures = []
    lods = []
    for index in range(MESH_EDITOR.get_lod_count(mesh)):
        lods.append({
            "lod": index,
            "expected_source_triangles": source_geometry["triangles"]["LOD" + str(index)],
            "render_triangles": unreal.MorphAuditLibrary.get_lod_triangle_count(mesh, index),
            "vertices": MESH_EDITOR.get_num_verts(mesh, index),
            "sections": MESH_EDITOR.get_num_sections(mesh, index),
            "material_slot_indices": [MESH_EDITOR.get_lod_material_slot(mesh, index, section) for section in range(MESH_EDITOR.get_num_sections(mesh, index))],
            "morph_target_count": unreal.MorphAuditLibrary.get_lod_morph_target_count(mesh, index),
        })
    if len(lods) != 3:
        failures.append("Expected three imported LODs")
    for lod in lods:
        if lod["render_triangles"] != lod["expected_source_triangles"]:
            failures.append(f"LOD{lod['lod']} triangles do not match source")
        if lod["morph_target_count"] != 26:
            failures.append(f"LOD{lod['lod']} has {lod['morph_target_count']} morphs instead of 26")
        if lod["sections"] != 8 or set(lod["material_slot_indices"]) != set(range(8)):
            failures.append(f"LOD{lod['lod']} material assignments are incomplete")

    material_records = []
    for slot in mesh.get_editor_property("materials"):
        material = slot.material_interface
        name = str(slot.material_slot_name)
        record = {"slot": name, "asset": material.get_path_name() if material else None}
        if not material:
            failures.append("Unassigned material slot " + name)
        else:
            if material.get_path_name() != ASSET_ROOT + "/Materials/" + name + "." + name:
                failures.append("Unexpected material asset in slot " + name)
            if isinstance(material, unreal.Material):
                record["expressions"] = unreal.MaterialEditingLibrary.get_num_material_expressions(material)
                if record["expressions"] < 3:
                    failures.append("Incomplete material graph in slot " + name)
        material_records.append(record)
    if len(material_records) != 8:
        failures.append("Expected eight assigned material slots")

    texture_records = []
    for file in sorted((EXPORT / "textures").glob("*.png")):
        texture = unreal.load_asset(ASSET_ROOT + "/Textures/" + file.stem)
        if texture is None:
            failures.append("Missing imported texture " + file.stem)
            continue
        texture_records.append({"name": file.stem, "size_x": texture.blueprint_get_size_x(), "size_y": texture.blueprint_get_size_y()})
        if max(texture_records[-1]["size_x"], texture_records[-1]["size_y"]) > 4096:
            failures.append("Oversized imported texture " + file.stem)

    socket_records = []
    socket_document = json.loads((DOCS / "skeleton_and_sockets.json").read_text())
    socket_evidence = infer_import_rotation(mesh)
    for key in ("root_reference_alignment", "root_motion_basis_evidence"):
        if key in socket_document.get("axis_evidence", {}):
            socket_evidence[key] = socket_document["axis_evidence"][key]
    socket_evidence["evaluated_body_forward"] = socket_evidence["native_forward"]
    socket_evidence["showcase_mesh_yaw"] = socket_evidence["mesh_reference_forward_yaw"]
    socket_evidence["root_motion_mesh_yaw"] = socket_document.get("axis_evidence", {}).get("root_motion_mesh_yaw", 0.0)
    for bone in socket_document["bones"]:
        bone["unreal_name"] = unreal_bone_name(bone["name"])
    for item in socket_document["sockets"]:
        socket = mesh.find_socket(item["name"])
        if socket is None:
            failures.append("Missing native socket " + item["name"])
            continue
        item["unreal_bone"] = str(socket.bone_name)
        if "unreal_component_rest_cm" not in item:
            item["unreal_component_rest_cm"] = list(rotate_source_cm(item["source_world_m"], socket_evidence))
        local = socket.get_socket_local_transform()
        item["unreal_local_transform"] = {
            "translation_cm": vec(local.translation),
            "rotation_quaternion": [local.rotation.x, local.rotation.y, local.rotation.z, local.rotation.w],
            "scale": vec(local.scale3d),
        }
        world = local * unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, item["unreal_bone"])
        error = math.dist(vec(world.translation), item["unreal_component_rest_cm"])
        socket_records.append({"name": item["name"], "bone": str(socket.bone_name), "world_cm": vec(world.translation), "local_scale": vec(local.scale3d), "position_error_cm": error})
        if str(socket.bone_name) != unreal_bone_name(item["bone"]) or error > .5:
            failures.append("Socket transform mismatch " + item["name"])
    socket_document["axis_evidence"] = socket_evidence
    socket_document["unreal_facing"] = f"Measured source-to-Unreal basis {socket_evidence['source_to_unreal_matrix']}; source forward -Y maps to {socket_evidence['native_forward']}. Mesh-relative yaw is {socket_evidence['showcase_mesh_yaw']:g} degrees to face actor +X. Baked local transforms are preserved; measured animation-to-mesh yaw is {socket_evidence['root_motion_mesh_yaw']:g} degrees before CharacterMovement sweeps the capsule. Scale remains one."
    socket_document["bone_name_mapping"] = "The FBX importer replaces '.' with '_' in bone and morph names. unreal_name/unreal_bone records the exact one-to-one native mapping."
    (DOCS / "skeleton_and_sockets.json").write_text(json.dumps(socket_document, indent=2) + "\n")

    alignment = json.loads((ROOT / "source" / "audio" / "dialogue_alignment.json").read_text())
    audio = unreal.load_asset(ASSET_ROOT + "/Audio/Dialogue")
    audio_record = None
    if audio is None:
        failures.append("Dialogue SoundWave did not import")
    else:
        duration = audio.get_editor_property("duration")
        audio_record = {"asset": audio.get_path_name(), "duration_seconds": duration, "source_duration_seconds": alignment["duration_seconds"]}
        if abs(duration - alignment["duration_seconds"]) > .01:
            failures.append("Dialogue audio duration mismatch")

    axis_evidence = infer_import_rotation(mesh)
    if "axis_evidence" in socket_document:
        axis_evidence.update({key: value for key, value in socket_document["axis_evidence"].items() if key in ("evaluated_body_forward", "showcase_mesh_yaw", "root_motion_mesh_yaw", "root_reference_alignment", "root_motion_basis_evidence")})
    original_matrix = [[0, -1, 0], [-1, 0, 0], [0, 0, 1]]
    axis_evidence["documented_original_matrix"] = original_matrix
    axis_evidence["matches_documented_original_matrix"] = axis_evidence["source_to_unreal_matrix"] == original_matrix
    if not axis_evidence["matches_documented_original_matrix"]:
        failures.append("Measured source-to-Unreal basis does not match the documented original matrix")
    clips = []
    for entry in ENTRIES:
        if not sequences.get(entry["id"]):
            continue
        sequence = sequences[entry["id"]]
        model = sequence.get_editor_property("data_model_interface")
        rate = model.get_frame_rate()
        curves = [str(name) for name in LIB.get_animation_curve_names(sequence, unreal.RawCurveTrackTypes.RCT_FLOAT)]
        event_records = []
        for event in LIB.get_animation_notify_events(sequence):
            notify = event.get_editor_property("notify")
            event_records.append({
                "name": str(event.get_editor_property("notify_name")),
                "time": LIB.get_anim_notify_event_trigger_time(event),
                "class": notify.get_class().get_name() if notify else "MissingNotify",
                "payload_name": str(notify.get_editor_property("event_name")) if notify else None,
                "event_type": str(notify.get_editor_property("event_type")) if notify else None,
                "value": float(notify.get_editor_property("value")) if notify else None,
            })
        root_start = LIB.get_bone_pose_for_frame(sequence, "root", 0, False)
        root_end = LIB.get_bone_pose_for_frame(sequence, "root", entry["frame_range"][1], False)
        source_displacement = entry["nominal_root_displacement_m"]
        additive_reference = sequence.get_editor_property("ref_pose_seq") if entry["form"] == "additive" else None
        mesh_delta = vec(unreal.MorphAuditLibrary.get_root_motion_delta(sequence, 0.0, sequence.get_play_length()))
        yaw = math.radians(socket_document["axis_evidence"]["root_motion_mesh_yaw"])
        actor_delta = [mesh_delta[0] * math.cos(yaw) - mesh_delta[1] * math.sin(yaw), mesh_delta[0] * math.sin(yaw) + mesh_delta[1] * math.cos(yaw), mesh_delta[2]]
        raw_local = [root_end.translation.x - root_start.translation.x, root_end.translation.y - root_start.translation.y, root_end.translation.z - root_start.translation.z]
        source_actor = rotate_source_cm(source_displacement, axis_evidence)
        expected_mesh = [source_actor[0] * math.cos(yaw) + source_actor[1] * math.sin(yaw), -source_actor[0] * math.sin(yaw) + source_actor[1] * math.cos(yaw), source_actor[2]]
        expected_actor = list(source_actor)
        clips.append({
            "id": entry["id"], "asset": sequence.get_path_name(), "length": sequence.get_play_length(),
            "skeleton": sequence.get_editor_property("skeleton").get_path_name(),
            "expected_length": entry["duration_seconds"], "fps": rate.numerator / rate.denominator,
            "bone_tracks": model.get_num_bone_tracks(), "float_curves": curves,
            "missing_facial_curves": sorted({name.replace(".", "_") for name in source_geometry["shape_keys"]} - set(curves)),
            "enable_root_motion": sequence.get_editor_property("enable_root_motion"),
            "additive_type": str(sequence.get_editor_property("additive_anim_type")),
            "additive_reference": additive_reference.get_path_name() if additive_reference else None,
            "root_local_displacement_cm": raw_local,
            "root_motion_mesh_delta_cm": mesh_delta,
            "root_motion_actor_delta_cm": actor_delta,
            "expected_mesh_delta_cm": expected_mesh,
            "expected_actor_delta_cm": expected_actor,
            "root_motion_track_error_cm": math.dist(raw_local, mesh_delta),
            "root_scale_error": max(abs(value - 1.0) for value in vec(root_end.scale3d)),
            "event_count": len(event_records), "events": event_records,
        })

    axis_evidence["handedness"] = "The measured source-to-Unreal basis is a right-handed to left-handed coordinate conversion; determinant -1 is intentional."
    if sequences and len(clips) != len(ENTRIES):
        failures.append("Missing imported clip assets: " + str(len(clips)) + "/96")
    if axis_evidence["max_reference_error_cm"] > .1:
        failures.append("Reference-pose axis/scale mismatch: " + str(axis_evidence["max_reference_error_cm"]))
    reference_position_error = 0.0
    reference_angle_error = 0.0
    for name in bones:
        mesh_pose = unreal.MorphAuditLibrary.get_mesh_bone_rest_transform(mesh, name)
        skeleton_pose = reference.get_ref_bone_pose(name, unreal.AnimPoseSpaces.WORLD)
        reference_position_error = max(reference_position_error, math.dist(vec(mesh_pose.translation), vec(skeleton_pose.translation)))
        reference_angle_error = max(reference_angle_error, math.degrees(mesh_pose.rotation.angular_distance(skeleton_pose.rotation)))
    axis_evidence["skeleton_mesh_reference_max_position_error_cm"] = reference_position_error
    axis_evidence["skeleton_mesh_reference_max_angle_degrees"] = reference_angle_error
    if reference_position_error > .1 or reference_angle_error > .1:
        failures.append(f"Skeleton and mesh reference poses disagree: position={reference_position_error}cm angle={reference_angle_error}deg")
    if roots != ["root"]:
        failures.append("Expected exactly one root named root: " + repr(roots))
    if len(bones) != 70:
        failures.append("Expected 70 deformation bones, got " + str(len(bones)))
    scale_error = max(abs(value - 1.0) for name in bones for value in vec(reference.get_ref_bone_pose(name, unreal.AnimPoseSpaces.LOCAL).scale3d))
    axis_evidence["root_local_scale"] = vec(reference.get_ref_bone_pose("root", unreal.AnimPoseSpaces.LOCAL).scale3d)
    axis_evidence["max_bone_scale_error"] = scale_error
    if scale_error > .001:
        failures.append("Bone reference scale is not one: " + str(scale_error))
    height = bounds.box_extent.z * 2
    if not 179.0 <= height <= 181.0:
        failures.append("Imported height outside tolerance: " + str(height))
    if set(morph_names) != {name.replace(".", "_") for name in source_geometry["shape_keys"]}:
        failures.append("Imported morph names do not match the 26 source controls")

    for clip in clips:
        entry = next(entry for entry in ENTRIES if entry["id"] == clip["id"])
        if entry["form"] == "pose":
            if not 0.0 <= clip["length"] <= 1.0 / 30.0 + .001:
                failures.append(clip["id"] + ": static pose is not a held frame")
        elif abs(clip["length"] - clip["expected_length"]) > .04:
            failures.append(clip["id"] + ": wrong imported duration")
        if clip["bone_tracks"] != 70:
            failures.append(clip["id"] + ": incomplete skeletal tracks")
        if clip["skeleton"] != mesh.skeleton.get_path_name():
            failures.append(clip["id"] + ": bound to a different skeleton")
        if clip["fps"] != 30:
            failures.append(clip["id"] + ": not 30fps")
        if clip["missing_facial_curves"]:
            failures.append(clip["id"] + ": facial curves missing")
        if clip["root_scale_error"] > .001:
            failures.append(clip["id"] + ": root scale is not one")
        if clip["root_motion_track_error_cm"] > .5:
            failures.append(clip["id"] + ": root-track translation sampling mismatch")
        if math.dist(clip["root_motion_mesh_delta_cm"], clip["expected_mesh_delta_cm"]) > .5:
            failures.append(clip["id"] + ": mesh-space root displacement mismatch")
        if math.dist(clip["root_motion_actor_delta_cm"], clip["expected_actor_delta_cm"]) > .5:
            failures.append(clip["id"] + ": actor-space root displacement mismatch")
        if clip["enable_root_motion"] != (entry["root_motion_policy"] == "root_motion"):
            failures.append(clip["id"] + ": root-motion flag mismatch")
        if entry["form"] == "additive" and (clip["additive_type"] != str(unreal.AdditiveAnimationType.AAT_ROTATION_OFFSET_MESH_SPACE) or clip["additive_reference"] != "/Game/Operative/Animations/idle_relaxed.idle_relaxed"):
            failures.append(clip["id"] + ": wrong rotation-offset additive setup")
        if require_events:
            expected = sorted(entry["events"], key=lambda marker: (marker["time"], marker["name"]))
            actual = sorted(clip["events"], key=lambda event: (event["time"], event["name"]))
            if len(actual) != len(expected):
                failures.append(clip["id"] + ": event count mismatch")
                continue
            for event, marker in zip(actual, expected):
                if event["name"] != marker["name"] or abs(event["time"] - marker["time"]) > .001 or event["payload_name"] != marker["name"] or event["event_type"] != marker["type"] or abs(event["value"] - marker["value"]) > .0001 or event["class"] != "MorphEventNotify":
                    failures.append(clip["id"] + ": event identity/time/payload mismatch")
                    break
    result = {
        "status": "PASS" if not failures else "FAIL", "failures": failures,
        "mesh": mesh.get_path_name(), "skeleton": mesh.skeleton.get_path_name(),
        "height_cm": height, "bounds_origin_cm": vec(bounds.origin), "bounds_extent_cm": vec(bounds.box_extent),
        "bone_count": len(bones), "bone_names": bones, "roots": roots, "morph_names": morph_names,
        "axis_evidence": axis_evidence,
        "material_slots": [str(slot.material_slot_name) for slot in mesh.get_editor_property("materials")],
        "material_interfaces": material_records,
        "textures": texture_records, "sockets": socket_records, "audio": audio_record,
        "lods": lods, "clips": clips, "event_audit_required": require_events,
        "notify_time_tolerance_seconds": .001,
        "texture_memory_note": "Measured decoded source texture bytes are reported in material_and_lod_report.json; runtime GPU memory is benchmarked separately.",
    }
    (DOCS / "unreal_import_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    log("audit", result["status"], failures)
    return result


def save_assets():
    options_path = PROJECT / "Saved" / "ImportOptions.json"
    if options_path.exists() and "--audit-only" in json.loads(options_path.read_text()).get("arguments", []):
        log("read-only audit complete; no asset packages rewritten")
        return
    editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    records = []
    for asset in dict.fromkeys(SAVE):
        package = asset.get_path_name().split(".")[0]
        log("save candidate", package, asset.get_class().get_name(), asset.get_outer().get_name())
        saved = editor.save_asset(package, only_if_is_dirty=False)
        file = PROJECT / "Content" / (package.split("/Game/", 1)[1] + ".uasset")
        exists = file.is_file() and unreal.load_asset(package) is not None
        records.append({"asset": package, "saved": bool(saved), "persisted": exists, "class": asset.get_class().get_name()})
    (DOCS / "validation" / "unreal_save_report.json").write_text(json.dumps({"assets": records}, indent=2) + "\n")
    failed = [record["asset"] for record in records if not record["saved"] or not record["persisted"]]
    if failed:
        raise RuntimeError("Assets were not persisted: " + repr(failed))
    log("persisted assets verified", len(records))


def main():
    options_path = PROJECT / "Saved" / "ImportOptions.json"
    args = set(json.loads(options_path.read_text()).get("arguments", [])) if options_path.exists() else set()
    log("import mode", sorted(args))
    reuse_mesh = bool(args.intersection({"--audit-only", "--events-only", "--animations-only"}))
    mesh = unreal.load_asset(ASSET_ROOT + "/SK_Operative") if reuse_mesh else import_mesh()
    if not args.intersection({"--audit-only", "--events-only", "--animations-only"}):
        import_textures_and_materials(mesh)
        import_audio()
    if "--mesh-only" in args:
        create_sockets(mesh)
        result = audit(mesh, {})
        save_assets()
        if result["status"] != "PASS": raise RuntimeError("Mesh import audit failed")
        log("SUCCESS mesh-only")
        return
    sequences = {entry["id"]: unreal.load_asset(entry["unreal_asset"]) for entry in ENTRIES} if args.intersection({"--audit-only", "--events-only"}) else import_animations(mesh)
    SAVE.extend(sequence for sequence in sequences.values() if sequence is not None)
    if any(sequence is None for sequence in sequences.values()) and not args.intersection({"--audit-only"}):
        raise RuntimeError("Missing required clip assets; import all animations before adding events")
    if "--audit-only" not in args:
        align_reference_basis(mesh, sequences)
        create_sockets(mesh)
    if not args.intersection({"--audit-only", "--skip-events"}):
        import_events(sequences)
    result = audit(mesh, sequences, require_events=not args.intersection({"--skip-events", "--mesh-only"}))
    save_assets()
    if result["status"] != "PASS":
        raise RuntimeError("Import audit failed; see unreal_import_audit.json")
    log("SUCCESS")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print("MORPH_IMPORT FAILED", flush=True)
        raise

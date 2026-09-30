"""Import authored FBX assets into the native MorphRig project.

Run inside Unreal with tools/build_linux.sh import. -MorphMeshOnly permits an
early mesh/LOD/material smoke import while authored motion export is running.
Full import rejects missing named assets and records measured import evidence.
"""
from pathlib import Path
import csv
import json
import shutil
import traceback
import unreal

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "unreal" / "Content"
REPORT = ROOT / "verification" / "unreal_import_report.json"
COMMAND_LINE = unreal.SystemLibrary.get_command_line()
MESH_ONLY = "-MorphMeshOnly" in COMMAND_LINE
INSPECT_ONLY = "-MorphInspectOnly" in COMMAND_LINE
ONLY_CLIP = next((word.split("=", 1)[1] for word in COMMAND_LINE.split() if word.startswith("-MorphReimportClip=")), None)
ONLY_CLIPS = set(ONLY_CLIP.split(",")) if ONLY_CLIP else set()
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.EditorAssetLibrary
MAT = unreal.MaterialEditingLibrary
SKELETAL = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
EACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ELEVE = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
RESULT = {"engine_version": unreal.SystemLibrary.get_engine_version(),
          "mesh_only": MESH_ONLY, "source_units": "meters", "runtime_units": "centimeters",
          "import_scale": 1.0, "animations": [], "missing": [], "errors": []}


def log(message):
    unreal.log("MORPHRIG_IMPORT " + message)


def save_report():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(RESULT, indent=2))


def import_file(filename, destination, name, options=None, factory=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(filename))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)
    if options:
        task.set_editor_property("options", options)
    if factory:
        task.set_editor_property("factory", factory)
    ASSETS.import_asset_tasks([task])
    paths = list(task.get_editor_property("imported_object_paths"))
    if not paths:
        raise RuntimeError(f"No assets imported from {filename}")
    log(f"{filename.name} -> {paths}")
    return [LIB.load_asset(p) for p in paths]


def rename_to(asset, desired):
    current = asset.get_path_name().split(".")[0]
    if current != desired:
        if LIB.does_asset_exist(desired):
            # Reimports normally already retain their destination names.
            existing = LIB.load_asset(desired)
            if isinstance(existing, type(asset)):
                raise RuntimeError(f"Unexpected import naming collision {current} -> {desired}")
        if not LIB.rename_asset(current, desired):
            raise RuntimeError(f"Could not rename {current} -> {desired}")
    return LIB.load_asset(desired)


def fbx_options(mesh=False, skeleton=None):
    options = unreal.FbxImportUI()
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_mesh", mesh)
    options.set_editor_property("import_animations", not mesh)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("create_physics_asset", mesh)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH if mesh else unreal.FBXImportType.FBXIT_ANIMATION)
    if skeleton:
        options.set_editor_property("skeleton", skeleton)
    data = options.get_editor_property("skeletal_mesh_import_data" if mesh else "anim_sequence_import_data")
    data.set_editor_property("convert_scene", True)
    data.set_editor_property("convert_scene_unit", True)
    data.set_editor_property("force_front_x_axis", True)
    data.set_editor_property("coordinate_system_policy", unreal.CoordinateSystemPolicy.MATCH_UP_FORWARD_AXES)
    data.set_editor_property("import_uniform_scale", 1.0)
    if mesh:
        data.set_editor_property("import_morph_targets", True)
        data.set_editor_property("use_t0_as_ref_pose", False)
        data.set_editor_property("update_skeleton_reference_pose", False)
        data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
        data.set_editor_property("preserve_smoothing_groups", True)
    else:
        data.set_editor_property("use_default_sample_rate", False)
        data.set_editor_property("custom_sample_rate", 30)
        data.set_editor_property("import_custom_attribute", True)
        data.set_editor_property("remove_redundant_keys", False)
        data.set_editor_property("animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    return options


def material(name, folder="/Game/Operative/Materials"):
    path = folder + "/" + name
    if LIB.does_asset_exist(path):
        asset = LIB.load_asset(path)
        MAT.delete_all_material_expressions(asset)
    else:
        asset = ASSETS.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    MAT.set_base_material_usage(asset, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    MAT.set_base_material_usage(asset, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    return asset


def expr(m, cls, x, y):
    return MAT.create_material_expression(m, cls, x, y)


def scalar(m, value, x=0, y=0):
    e = expr(m, unreal.MaterialExpressionConstant, x, y)
    e.set_editor_property("r", value)
    return e


def color(m, value, x=0, y=0):
    e = expr(m, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property("constant", unreal.LinearColor(*value, 1))
    return e


def link(source, output, destination, pin):
    if not MAT.connect_material_expressions(source, output, destination, pin):
        raise RuntimeError(f"Material link failed: {source.get_class().get_name()}:{output} -> {destination.get_class().get_name()}:{pin}; inputs={list(MAT.get_material_expression_input_names(destination))}")


def property_link(source, output, prop):
    if not MAT.connect_material_property(source, output, prop):
        raise RuntimeError(f"Material property link failed: {source.get_class().get_name()}:{output} -> {prop}")


def build_materials(mesh):
    report = json.loads((ROOT / "docs" / "material_and_lod_report.json").read_text())
    materials = {}
    for item in report["materials"]:
        name = item["name"]
        texture = next((a for a in import_file(ROOT / "export" / "textures" / (name + "_BaseColor.png"), "/Game/Operative/Textures", name + "_BaseColor") if isinstance(a, unreal.Texture2D)), None)
        if texture is None:
            raise RuntimeError("Missing imported texture " + name)
        texture.set_editor_property("srgb", True)
        m = material("M_" + name)
        sample = expr(m, unreal.MaterialExpressionTextureSample, -500, -200)
        sample.set_editor_property("texture", texture)
        sample.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        output = sample
        if name == "Accent":
            grey = expr(m, unreal.MaterialExpressionDesaturation, -330, -200)
            link(sample, "", grey, "")
            link(scalar(m, 1), "", grey, "Fraction")
            parameter = expr(m, unreal.MaterialExpressionVectorParameter, -330, -60)
            parameter.set_editor_property("parameter_name", "TeamAccent")
            parameter.set_editor_property("default_value", unreal.LinearColor(.02, .65, 1, 1))
            output = expr(m, unreal.MaterialExpressionMultiply, -100, -150)
            link(grey, "", output, "A")
            link(parameter, "", output, "B")
        property_link(output, "RGB" if output is sample else "", unreal.MaterialProperty.MP_BASE_COLOR)
        property_link(scalar(m, item["metallic"], -180, 100), "", unreal.MaterialProperty.MP_METALLIC)
        property_link(scalar(m, item["roughness"], -180, 180), "", unreal.MaterialProperty.MP_ROUGHNESS)
        normal_name = item.get("normal_texture")
        if normal_name:
            normal_file = ROOT / "export" / "textures" / Path(normal_name).name
            normal = next(a for a in import_file(normal_file, "/Game/Operative/Textures", normal_file.stem) if isinstance(a, unreal.Texture2D))
            normal.set_editor_property("srgb", False)
            normal.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            # Source normal textures encode tangent +Y (OpenGL). Unreal's
            # tangent normal input uses -Y (DirectX), so convert on import.
            normal.set_editor_property("flip_green_channel", True)
            normal_sample = expr(m, unreal.MaterialExpressionTextureSample, -500, 260)
            normal_sample.set_editor_property("texture", normal)
            normal_sample.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            mix = expr(m, unreal.MaterialExpressionLinearInterpolate, -250, 270)
            link(color(m, (0, 0, 1), -450, 350), "", mix, "A")
            link(normal_sample, "", mix, "B")
            link(scalar(m, .55, -450, 430), "", mix, "Alpha")
            normalized = expr(m, unreal.MaterialExpressionNormalize, -80, 270)
            link(mix, "", normalized, "")
            property_link(normalized, "", unreal.MaterialProperty.MP_NORMAL)
            LIB.save_loaded_asset(normal)
        MAT.recompile_material(m)
        LIB.save_loaded_asset(m)
        LIB.save_loaded_asset(texture)
        materials[name] = m
    slots = list(mesh.get_editor_property("materials"))
    for slot in slots:
        slot_name = str(slot.get_editor_property("imported_material_slot_name"))
        matches = [name for name in materials if name.lower() == slot_name.lower() or name.lower() in slot_name.lower()]
        if not matches:
            raise RuntimeError("Unmapped imported material slot " + slot_name)
        slot.set_editor_property("material_interface", materials[matches[0]])
    mesh.set_editor_property("materials", slots)
    LIB.save_loaded_asset(mesh)
    RESULT["materials"] = [{"slot": str(s.get_editor_property("imported_material_slot_name")), "asset": s.get_editor_property("material_interface").get_path_name()} for s in slots]
    RESULT["normal_import"] = {"source_convention": "OpenGL tangent +Y", "flip_green_channel": True,
                               "srgb": False, "compression": "TC_NORMALMAP", "strength": .55}
    return materials


def assign_beacon_materials(materials):
    beacon = LIB.load_asset("/Game/Operative/SM_Beacon")
    if not beacon:
        return
    slots = list(beacon.get_editor_property("static_materials"))
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("imported_material_slot_name"))
        matches = [key for key in materials if key.lower() == name.lower() or key.lower() in name.lower()]
        if not matches:
            raise RuntimeError("Unmapped beacon material slot " + name)
        beacon.set_material(index, materials[matches[0]])
    LIB.save_loaded_asset(beacon)
    RESULT["beacon_materials"] = [{"slot": str(s.get_editor_property("imported_material_slot_name")),
                                   "asset": beacon.get_material(i).get_path_name()} for i, s in enumerate(slots)]


def stage_boot_surface(mesh):
    bindings = json.loads(unreal.MorphAssetLibrary.inspect_boot_surface(mesh))
    if len(bindings.get("vertices", [])) < 100:
        raise RuntimeError("Imported boot surface binding inspection was incomplete")
    data = CONTENT / "Data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "boot_surface_bindings.json").write_text(json.dumps(bindings, separators=(",", ":")) + "\n")
    RESULT["boot_surface_bindings"] = {"vertices": len(bindings["vertices"]), "lod": bindings["lod"],
                                       "source": "Measured imported LOD0 vertex positions and skin weights"}


def showcase_materials():
    backdrop = material("M_Backdrop", "/Game/Showcase")
    backdrop.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    backdrop.set_editor_property("two_sided", True)
    property_link(color(backdrop, (.5, .55, .6)), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MAT.recompile_material(backdrop)
    LIB.save_loaded_asset(backdrop)
    for name, base, rough in [("M_Room", (.09, .11, .13), .8), ("M_Clay", (.42, .42, .42), .65)]:
        m = material(name, "/Game/Showcase")
        property_link(color(m, base), "", unreal.MaterialProperty.MP_BASE_COLOR)
        property_link(scalar(m, rough, 0, 130), "", unreal.MaterialProperty.MP_ROUGHNESS)
        MAT.recompile_material(m)
        LIB.save_loaded_asset(m)
    m = material("M_Normals", "/Game/Showcase")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    normal = expr(m, unreal.MaterialExpressionVertexNormalWS, -400, 0)
    multiply = expr(m, unreal.MaterialExpressionMultiply, -240, 0)
    link(normal, "", multiply, "A")
    link(scalar(m, .5, -400, 100), "", multiply, "B")
    add = expr(m, unreal.MaterialExpressionAdd, -80, 0)
    link(multiply, "", add, "A")
    link(scalar(m, .5, -240, 170), "", add, "B")
    property_link(add, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MAT.recompile_material(m)
    LIB.save_loaded_asset(m)


def setup_sockets(mesh, skeleton):
    definitions = json.loads((ROOT / "docs" / "skeleton_and_sockets.json").read_text())["sockets"]
    for item in definitions:
        name, bone = item["name"], item.get("unreal_bone", item["bone"].replace(".", "_"))
        if "position_m" in item:
            x, y, z = item["position_m"]
            # Verified legacy FBX basis: source (x,y,z) -> UE (-y,-x,z).
            unreal.MorphAssetLibrary.add_asset_socket_at_component_position(mesh, name, bone, unreal.Vector(-y*100, -x*100, z*100))
        else:
            offset = item.get("offset_m", [0, 0, 0])
            unreal.MorphAssetLibrary.add_asset_socket(mesh, name, bone, unreal.Vector(*(float(v)*100 for v in offset)))
    for name, bone in [("hand_left", "hand_L"), ("hand_right", "hand_R"), ("effect_head", "head"), ("cell_grip", "cell"), ("beacon_grip", "beacon")]:
        unreal.MorphAssetLibrary.add_asset_socket(mesh, name, bone, unreal.Vector())
    LIB.save_loaded_asset(skeleton)
    LIB.save_loaded_asset(mesh)
    RESULT["sockets"] = definitions


def setup_map(mesh):
    path = "/Game/Showcase/Showcase"
    if not LIB.does_asset_exist(path):
        ELEVE.new_level(path)
    else:
        ELEVE.load_level(path)
    # The room, targets, lighting, camera and operative are spawned by the
    # native game mode in editor play and in the standalone client alike.
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    start = next((a for a in EACTORS.get_all_level_actors() if isinstance(a, unreal.PlayerStart)), None)
    if start is None:
        start = EACTORS.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 90))
    start.set_actor_rotation(unreal.Rotator(0, 0, 0), False)
    settings = world.get_world_settings()
    settings.set_editor_property("default_game_mode", unreal.MorphShowcaseMode)
    ELEVE.save_current_level()
    inspection = json.loads(unreal.MorphAssetLibrary.inspect_skeletal_asset(mesh))
    roots = inspection["root_bones"]
    RESULT["mesh_bounds_cm"] = {"height": inspection["height_cm"]}
    RESULT["bone_count"] = inspection["bone_count"]
    RESULT["root_bones"] = roots
    RESULT["bone_hierarchy"] = inspection["bones"]
    RESULT["morph_targets"] = inspection["morph_targets"]
    RESULT["reference_bone_locations_cm"] = {b["name"]: b["position_cm"] for b in inspection["bones"]}
    if roots != ["root"]:
        raise RuntimeError(f"Expected one ground root bone, imported roots {roots}")
    if not 177 <= inspection["height_cm"] <= 185:
        raise RuntimeError(f"Unexpected imported 180 cm body height: {inspection['height_cm']}")


def import_animations(skeleton):
    manifest_path = ROOT / "docs" / "animation_manifest.json"
    if not manifest_path.exists():
        if MESH_ONLY:
            return
        raise RuntimeError("Animation manifest is not exported")
    manifest = json.loads(manifest_path.read_text())
    data = CONTENT / "Data"
    data.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_path, data / "animation_manifest.json")
    alignment = ROOT / "source" / "audio" / "dialogue_alignment.json"
    if alignment.exists():
        shutil.copyfile(alignment, data / "dialogue_alignment.json")
    if MESH_ONLY:
        return
    required = [r["id"] for r in csv.DictReader((ROOT / "required_animations.csv").open())]
    rows = {row["id"]: row for row in manifest["animations"]}
    if sorted(rows) != sorted(required):
        raise RuntimeError("Manifest does not match the closed 96-entry inventory")
    animations = getattr(unreal, "AnimationLibrary", None) or unreal.AnimationBlueprintLibrary
    for identifier in required:
        if ONLY_CLIPS and identifier not in ONLY_CLIPS:
            continue
        row = rows[identifier]
        filename = ROOT / row["export_file"]
        if not filename.exists():
            RESULT["missing"].append(identifier)
            continue
        objects = import_file(filename, "/Game/Operative/Animations", identifier, fbx_options(False, skeleton), unreal.FbxFactory())
        sequences = [a for a in objects if isinstance(a, unreal.AnimSequence)]
        if len(sequences) != 1:
            raise RuntimeError(f"Expected one reusable animation in {filename}, got {[a.get_path_name() for a in sequences]}")
        sequence = rename_to(sequences[0], "/Game/Operative/Animations/" + identifier)
        root_motion = row["root_motion_policy"] == "root_motion"
        sequence.set_editor_property("enable_root_motion", root_motion)
        sequence.set_editor_property("force_root_lock", not root_motion)
        sequence.set_editor_property("root_motion_root_lock", unreal.RootMotionRootLock.REF_POSE)
        LIB.set_metadata_tag(sequence, "MorphRigLoop", "true" if row["loop"] else "false")
        animations.remove_all_animation_notify_tracks(sequence)
        animations.add_animation_notify_track(sequence, "MorphRigMarkers", unreal.LinearColor(.2, .8, 1, 1))
        duration = sequence.get_play_length()
        for event in row.get("events", []):
            time = float(event.get("time", event.get("frame", 0) / 30))
            notify = animations.add_animation_notify_event(sequence, "MorphRigMarkers", min(time, max(0, duration - .001)), unreal.MorphMarkerNotify)
            notify.set_editor_property("event_name", event.get("name", event.get("event", "marker")))
        LIB.save_loaded_asset(sequence)
        measured = {"id": identifier, "asset": sequence.get_path_name(), "duration": duration, "root_motion": root_motion, "markers": len(row.get("events", []))}
        if root_motion:
            start = animations.get_bone_pose_for_time(sequence, "root", 0, False)
            end = animations.get_bone_pose_for_time(sequence, "root", duration, False)
            a, b = start.translation, end.translation
            measured["root_delta_cm"] = [b.x-a.x, b.y-a.y, b.z-a.z]
            measured["native_extraction"] = json.loads(unreal.MorphAssetLibrary.inspect_animation_asset(sequence))
        RESULT["animations"].append(measured)
        save_report()
    if RESULT["missing"]:
        raise RuntimeError("Missing required FBX clips: " + ", ".join(RESULT["missing"]))
    audio = ROOT / "source" / "audio" / "dialogue.wav"
    if not audio.exists():
        raise RuntimeError("Required dialogue WAV missing")
    if not ONLY_CLIP:
        import_file(audio, "/Game/Operative", "dialogue")


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, "Interchange.FeatureFlags.Import.FBX 0")
    if unreal.SystemLibrary.get_console_variable_int_value("Interchange.FeatureFlags.Import.FBX") != 0:
        raise RuntimeError("Legacy FBX backend was not selected")
    if INSPECT_ONLY or ONLY_CLIP:
        if REPORT.exists():
            RESULT.update(json.loads(REPORT.read_text()))
        RESULT["errors"] = []
        mesh = LIB.load_asset("/Game/Operative/SK_Operative")
        skeleton = mesh.get_editor_property("skeleton")
        materials = build_materials(mesh)
        assign_beacon_materials(materials)
        showcase_materials()
        for path in LIB.list_assets("/Game/Operative/Materials", recursive=True) + ["/Game/Showcase/M_Clay", "/Game/Showcase/M_Normals"]:
            asset = LIB.load_asset(path)
            if isinstance(asset, unreal.Material):
                MAT.set_base_material_usage(asset, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
                MAT.set_base_material_usage(asset, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
                MAT.recompile_material(asset)
                LIB.save_loaded_asset(asset)
        setup_sockets(mesh, skeleton)
        if ONLY_CLIP:
            required = {row["id"] for row in json.loads((ROOT / "docs" / "animation_manifest.json").read_text())["animations"]}
            if not ONLY_CLIPS <= required:
                raise RuntimeError("Unknown selective clips " + ", ".join(sorted(ONLY_CLIPS-required)))
            RESULT["animations"] = [row for row in RESULT["animations"] if row["id"] not in ONLY_CLIPS]
            import_animations(skeleton)
            RESULT["animations"].sort(key=lambda row: row["id"])
        for row in RESULT["animations"]:
            if row["root_motion"]:
                sequence = LIB.load_asset(row["asset"])
                row["native_extraction"] = json.loads(unreal.MorphAssetLibrary.inspect_animation_asset(sequence))
        RESULT["native_asset_inspection"] = json.loads(unreal.MorphAssetLibrary.inspect_skeletal_asset(mesh))
        stage_boot_surface(mesh)
        RESULT["complete"] = len(RESULT["animations"]) == 96
        save_report()
        log(f"SUCCESS inspect/selective animations={len(RESULT['animations'])}")
        return
    existing = LIB.load_asset("/Game/Operative/SK_Operative") if LIB.does_asset_exist("/Game/Operative/SK_Operative") else None
    if existing and "Interchange" in existing.get_editor_property("asset_import_data").get_class().get_name():
        for path in ("/Game/Operative/SK_Operative", "/Game/Operative/SK_Operative_PhysicsAsset", "/Game/Operative/Operative_Skeleton"):
            if LIB.does_asset_exist(path) and not LIB.delete_asset(path):
                raise RuntimeError("Could not replace provisional Interchange asset " + path)
    for folder in ("/Game/Operative", "/Game/Operative/Animations", "/Game/Operative/Materials", "/Game/Operative/Textures", "/Game/Showcase"):
        LIB.make_directory(folder)
    objects = import_file(ROOT / "export" / "Operative.fbx", "/Game/Operative", "SK_Operative", fbx_options(True), unreal.FbxFactory())
    meshes = [a for a in objects if isinstance(a, unreal.SkeletalMesh)]
    if len(meshes) != 1:
        raise RuntimeError("Mesh export must import as one skinned character")
    mesh = rename_to(meshes[0], "/Game/Operative/SK_Operative")
    imported_settings = mesh.get_editor_property("asset_import_data")
    RESULT["import_settings"] = {key: str(imported_settings.get_editor_property(key)) for key in ("convert_scene", "force_front_x_axis", "convert_scene_unit", "import_rotation", "import_uniform_scale", "coordinate_system_policy")}
    skeleton = rename_to(mesh.get_editor_property("skeleton"), "/Game/Operative/Operative_Skeleton")
    materials = build_materials(mesh)
    RESULT["lods"] = []
    for index in (1, 2):
        imported = SKELETAL.import_lod(mesh, index, str(ROOT / "export" / f"Operative_LOD{index}.fbx"))
        if imported != index:
            raise RuntimeError(f"Authored LOD{index} import returned {imported}")
    for index in (0, 1, 2):
        RESULT["lods"].append({"lod": index, "vertices": SKELETAL.get_num_verts(mesh, index), "sections": SKELETAL.get_num_sections(mesh, index)})
    mesh.set_editor_property("enable_per_poly_collision", False)
    LIB.save_loaded_asset(mesh)
    beacon_options = unreal.FbxImportUI()
    beacon_options.set_editor_property("automated_import_should_detect_type", False)
    beacon_options.set_editor_property("import_as_skeletal", False)
    beacon_options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    beacon_options.set_editor_property("import_materials", False)
    beacon_options.set_editor_property("import_textures", False)
    for prop in ("convert_scene", "convert_scene_unit", "force_front_x_axis"):
        beacon_options.static_mesh_import_data.set_editor_property(prop, True)
    beacon_options.static_mesh_import_data.set_editor_property("combine_meshes", True)
    beacon_objects = import_file(ROOT / "export" / "Beacon.fbx", "/Game/Operative", "SM_Beacon", beacon_options, unreal.FbxFactory())
    beacon = rename_to(next(a for a in beacon_objects if isinstance(a, unreal.StaticMesh)), "/Game/Operative/SM_Beacon")
    assign_beacon_materials(materials)
    setup_sockets(mesh, skeleton)
    showcase_materials()
    setup_map(mesh)
    RESULT["native_asset_inspection"] = json.loads(unreal.MorphAssetLibrary.inspect_skeletal_asset(mesh))
    stage_boot_surface(mesh)
    import_animations(skeleton)
    LIB.save_directory("/Game", only_if_is_dirty=True, recursive=True)
    RESULT["complete"] = not MESH_ONLY and len(RESULT["animations"]) == 96
    save_report()
    log(f"SUCCESS mesh={mesh.get_path_name()} animations={len(RESULT['animations'])} lods=3")


try:
    main()
except Exception as error:
    RESULT["errors"].append(str(error))
    RESULT["complete"] = False
    save_report()
    unreal.log_error(traceback.format_exc())
    raise

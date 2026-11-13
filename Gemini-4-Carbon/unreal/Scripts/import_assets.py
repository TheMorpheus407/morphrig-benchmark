"""
Headless Unreal Engine 5.8.3 Asset Import & Setup Script for MORPHRIG.
Run via:
  TMPDIR="$PWD/.tmp_work" "${UE_EXEC:-$HOME/UnrealEngine/bin/ue-exec}" \
    '$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd' \
    "$PWD/unreal/MorphRig.uproject" \
    -run=pythonscript -script="$PWD/unreal/Scripts/import_assets.py" \
    -nullrhi -unattended -nopause -nosplash
"""

import json
import os
import sys
from pathlib import Path
import unreal


ROOT_DIR = Path(__file__).resolve().parents[2]
EXPORT_DIR = ROOT_DIR / "export"
TEXTURES_DIR = EXPORT_DIR / "textures"
ANIMS_DIR = EXPORT_DIR / "animations"
AUDIO_WAV = ROOT_DIR / "source" / "audio" / "dialogue.wav"
MANIFEST_JSON = ROOT_DIR / "docs" / "animation_manifest.json"
MORPH_CURVES_JSON = ANIMS_DIR / "morph_curves.json"


def log(msg: str) -> None:
    unreal.log(f"[MorphRigImport] {msg}")
    print(f"[MorphRigImport] {msg}", flush=True)


def disable_interchange_fbx() -> None:
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX.ToLevel 0")


def import_textures() -> dict:
    dest_dir = "/Game/MorphRig/Textures"
    png_files = sorted(TEXTURES_DIR.glob("*.png"))
    if not png_files:
        raise RuntimeError(f"No PNG textures found in {TEXTURES_DIR}")

    tasks = []
    for png in png_files:
        task = unreal.AssetImportTask()
        task.filename = str(png)
        task.destination_path = dest_dir
        task.destination_name = png.stem
        task.replace_existing = True
        task.replace_existing_settings = True
        task.automated = True
        task.save = False
        tasks.append(task)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    textures = {}
    for png in png_files:
        asset_path = f"{dest_dir}/{png.stem}"
        tex = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not tex:
            raise RuntimeError(f"Failed to import texture: {asset_path}")

        stem = png.stem
        if stem.endswith("_Normal"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        elif stem.endswith("_ORM") or stem.endswith("_TeamMask"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        else:
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)

        unreal.EditorAssetLibrary.save_loaded_asset(tex, False)
        textures[stem] = tex

    log(f"Imported and configured {len(textures)} PBR textures in {dest_dir}")
    return textures


def create_pbr_material(
    mat_name: str,
    base_tex: unreal.Texture2D,
    norm_tex: unreal.Texture2D,
    orm_tex: unreal.Texture2D,
    emis_tex: unreal.Texture2D = None,
    with_team_rim: bool = False,
) -> unreal.Material:
    dest_dir = "/Game/MorphRig/Materials"
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat_factory = unreal.MaterialFactoryNew()
    mat = asset_tools.create_asset(mat_name, dest_dir, unreal.Material, mat_factory)
    if not mat:
        raise RuntimeError(f"Failed to create material {dest_dir}/{mat_name}")

    mel = unreal.MaterialEditingLibrary
    mel.delete_all_material_expressions(mat)

    # Mandatory shader permutations for standalone packaged builds!
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS, True)

    # 1. BaseColor Texture Parameter (supports runtime Team A / Team B texture swap)
    base_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -520, -240)
    base_node.set_editor_property("parameter_name", "BaseColorTex")
    base_node.set_editor_property("texture", base_tex)
    base_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    mel.connect_material_property(base_node, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    # 2. Tangent-Space Normal Map
    norm_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -520, 40)
    norm_node.set_editor_property("texture", norm_tex)
    norm_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    mel.connect_material_property(norm_node, "RGB", unreal.MaterialProperty.MP_NORMAL)

    # 3. Packed ORM Map (R = Ambient Occlusion, G = Roughness, B = Metallic)
    orm_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -520, 300)
    orm_node.set_editor_property("texture", orm_tex)
    orm_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    mel.connect_material_property(orm_node, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(orm_node, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(orm_node, "B", unreal.MaterialProperty.MP_METALLIC)

    # 4. Emissive + Optional Team Rim/Outline Parameterization
    if emis_tex is not None:
        emis_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -520, 560)
        emis_node.set_editor_property("parameter_name", "EmissiveTex")
        emis_node.set_editor_property("texture", emis_tex)
        emis_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)

        emis_boost = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -320, 660)
        emis_boost.set_editor_property("r", 2.4)

        emis_mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -200, 580)
        mel.connect_material_expressions(emis_node, "RGB", emis_mul, "A")
        mel.connect_material_expressions(emis_boost, "", emis_mul, "B")

        if with_team_rim:
            fresnel = mel.create_material_expression(mat, unreal.MaterialExpressionFresnel, -520, 820)
            exp_const = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -680, 820)
            exp_const.set_editor_property("r", 3.5)
            mel.connect_material_expressions(exp_const, "", fresnel, "ExponentIn")

            outline_str = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -520, 960)
            outline_str.set_editor_property("parameter_name", "OutlineStrength")
            outline_str.set_editor_property("default_value", 0.0)

            rim_mask = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -320, 860)
            mel.connect_material_expressions(fresnel, "", rim_mask, "A")
            mel.connect_material_expressions(outline_str, "", rim_mask, "B")

            rim_col = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -520, 1080)
            rim_col.set_editor_property("parameter_name", "TeamRimColor")
            rim_col.set_editor_property("default_value", unreal.LinearColor(0.0, 0.82, 1.0, 1.0))

            rim_rgb = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -180, 920)
            mel.connect_material_expressions(rim_mask, "", rim_rgb, "A")
            mel.connect_material_expressions(rim_col, "", rim_rgb, "B")

            emis_sum = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, -40, 680)
            mel.connect_material_expressions(emis_mul, "", emis_sum, "A")
            mel.connect_material_expressions(rim_rgb, "", emis_sum, "B")
            mel.connect_material_property(emis_sum, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        else:
            mel.connect_material_property(emis_mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    errors = mel.recompile_material(mat)
    if errors:
        log(f"WARNING compiling {mat_name}: {errors}")
    unreal.EditorAssetLibrary.save_loaded_asset(mat, False)
    return mat


def build_all_materials(tex: dict) -> dict:
    mats = {
        "M_Skin_FaceBody": create_pbr_material(
            "M_Skin_FaceBody",
            tex["Skin_BaseColor"],
            tex["Skin_Normal"],
            tex["Skin_ORM"],
        ),
        "M_Eyes_Mouth": create_pbr_material(
            "M_Eyes_Mouth",
            tex["EyesMouth_BaseColor"],
            tex["EyesMouth_Normal"],
            tex["EyesMouth_ORM"],
        ),
        "M_Hair": create_pbr_material(
            "M_Hair",
            tex["Hair_BaseColor"],
            tex["Hair_Normal"],
            tex["Hair_ORM"],
        ),
        "M_Suit_Fabric": create_pbr_material(
            "M_Suit_Fabric",
            tex["SuitFabric_BaseColor"],
            tex["SuitFabric_Normal"],
            tex["SuitFabric_ORM"],
        ),
        "M_CyberArmor": create_pbr_material(
            "M_CyberArmor",
            tex["CyberArmor_BaseColor"],
            tex["CyberArmor_Normal"],
            tex["CyberArmor_ORM"],
            emis_tex=tex["CyberArmor_Emissive"],
            with_team_rim=True,
        ),
        "M_Props_Tech": create_pbr_material(
            "M_Props_Tech",
            tex["PropsTech_BaseColor"],
            tex["PropsTech_Normal"],
            tex["PropsTech_ORM"],
            emis_tex=tex["PropsTech_Emissive"],
            with_team_rim=True,
        ),
    }
    log(f"Created and compiled {len(mats)} master materials in /Game/MorphRig/Materials")
    return mats


def import_character_mesh_and_lods(mats: dict) -> unreal.SkeletalMesh:
    char_dir = "/Game/MorphRig/Character"
    fbx_lod0 = EXPORT_DIR / "Operative.fbx"
    fbx_lod1 = EXPORT_DIR / "Operative_LOD1.fbx"
    fbx_lod2 = EXPORT_DIR / "Operative_LOD2.fbx"

    options = unreal.FbxImportUI()
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    options.set_editor_property("import_animations", False)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("create_physics_asset", True)

    sm_data = options.skeletal_mesh_import_data
    sm_data.set_editor_property("import_morph_targets", True)
    sm_data.set_editor_property("import_uniform_scale", 1.0)
    sm_data.set_editor_property("convert_scene", True)
    sm_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)

    factory = unreal.FbxFactory()
    task = unreal.AssetImportTask()
    task.filename = str(fbx_lod0)
    task.destination_path = char_dir
    task.destination_name = "Operative"
    task.replace_existing = True
    task.replace_existing_settings = True
    task.automated = True
    task.save = False
    task.factory = factory
    task.options = options

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    skel_mesh = unreal.EditorAssetLibrary.load_asset(f"{char_dir}/Operative")
    if not skel_mesh:
        raise RuntimeError("Failed to import Operative SkeletalMesh!")

    # Import authored LOD1 and LOD2 into Operative SkeletalMesh
    lod1_idx = unreal.SkeletalMeshEditorSubsystem.import_lod(skel_mesh, 1, str(fbx_lod1))
    lod2_idx = unreal.SkeletalMeshEditorSubsystem.import_lod(skel_mesh, 2, str(fbx_lod2))
    log(f"Imported custom SkeletalMesh LODs -> LOD1 index={lod1_idx}, LOD2 index={lod2_idx}")

    # Assign our 6 PBR materials preserving exact imported slot order
    ordered_names = [
        "M_Skin_FaceBody",
        "M_Eyes_Mouth",
        "M_Hair",
        "M_Suit_Fabric",
        "M_CyberArmor",
        "M_Props_Tech",
    ]
    existing_slots = list(skel_mesh.materials)
    new_slots = []
    if existing_slots:
        for idx, slot in enumerate(existing_slots):
            slot_name_str = str(slot.material_slot_name)
            matched_mat = None
            for mname in ordered_names:
                if mname.lower() in slot_name_str.lower() or slot_name_str.lower() in mname.lower():
                    matched_mat = mats[mname]
                    break
            if matched_mat is None and idx < len(ordered_names):
                matched_mat = mats[ordered_names[idx]]
            if matched_mat is not None:
                slot.material_interface = matched_mat
            new_slots.append(slot)
    else:
        for mname in ordered_names:
            sm = unreal.SkeletalMaterial()
            sm.material_interface = mats[mname]
            sm.material_slot_name = mname
            new_slots.append(sm)

    skel_mesh.materials = new_slots
    unreal.EditorAssetLibrary.save_loaded_asset(skel_mesh, False)
    return skel_mesh


def import_dialogue_audio() -> unreal.SoundWave:
    audio_dir = "/Game/MorphRig/Audio"
    task = unreal.AssetImportTask()
    task.filename = str(AUDIO_WAV)
    task.destination_path = audio_dir
    task.destination_name = "SW_Dialogue"
    task.replace_existing = True
    task.replace_existing_settings = True
    task.automated = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    sw = unreal.EditorAssetLibrary.load_asset(f"{audio_dir}/SW_Dialogue")
    if not sw:
        raise RuntimeError("Failed to import SW_Dialogue SoundWave!")
    log(f"Imported dialogue audio -> {audio_dir}/SW_Dialogue")
    return sw


def import_all_animations(skel_mesh: unreal.SkeletalMesh) -> dict:
    with open(MANIFEST_JSON, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(MORPH_CURVES_JSON, "r", encoding="utf-8") as f:
        morph_curves_db = json.load(f)

    skeleton = skel_mesh.skeleton
    # Ensure all 46 morph curve metadata names exist on the USkeleton
    all_curve_names = set()
    for clip_entry in morph_curves_db.values():
        all_curve_names.update(clip_entry.get("curves", {}).keys())
    for cname in sorted(all_curve_names):
        unreal.AnimationLibrary.add_curve_meta_data(skeleton, cname, False)

    anim_dest = "/Game/MorphRig/Animations"
    tasks = []
    entries = manifest["animations"]

    for entry in entries:
        cid = entry["id"]
        fbx_path = ANIMS_DIR / f"{cid}.fbx"
        if not fbx_path.exists():
            raise RuntimeError(f"Missing animation FBX: {fbx_path}")

        opts = unreal.FbxImportUI()
        opts.set_editor_property("import_mesh", False)
        opts.set_editor_property("import_as_skeletal", False)
        opts.set_editor_property("import_animations", True)
        opts.set_editor_property("skeleton", skeleton)
        opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
        opts.set_editor_property("import_materials", False)
        opts.set_editor_property("import_textures", False)

        adata = opts.anim_sequence_import_data
        adata.set_editor_property("import_bone_tracks", True)
        adata.set_editor_property("import_custom_attribute", True)
        adata.set_editor_property("import_meshes_in_bone_hierarchy", True)
        adata.set_editor_property("use_default_sample_rate", False)
        adata.set_editor_property("custom_sample_rate", 30)
        adata.set_editor_property("convert_scene", True)

        t = unreal.AssetImportTask()
        t.filename = str(fbx_path)
        t.destination_path = anim_dest
        t.destination_name = f"Anim_{cid}"
        t.replace_existing = True
        t.replace_existing_settings = True
        t.automated = True
        t.save = False
        t.factory = unreal.FbxFactory()
        t.options = opts
        tasks.append(t)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    seqs = {}
    curves_injected = 0
    markers_injected = 0

    for entry in entries:
        cid = entry["id"]
        asset_path = f"{anim_dest}/Anim_{cid}"
        seq = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not seq:
            raise RuntimeError(f"Failed to load imported AnimSequence: {asset_path}")

        # Root motion policy
        if entry["root_movement_policy"] == "root_motion":
            unreal.AnimationLibrary.set_root_motion_enabled(seq, True)
        else:
            unreal.AnimationLibrary.set_root_motion_enabled(seq, False)

        # Populate sync/event markers on notify track
        markers = entry.get("event_markers", [])
        if markers:
            if not unreal.AnimationLibrary.is_valid_anim_notify_track_name(seq, "MorphRigEvents"):
                unreal.AnimationLibrary.add_animation_notify_track(
                    seq, "MorphRigEvents", unreal.LinearColor(0.0, 0.85, 1.0, 1.0)
                )
            for mk in markers:
                unreal.AnimationLibrary.add_animation_sync_marker(
                    seq, mk["name"], float(mk["time_sec"]), "MorphRigEvents"
                )
                markers_injected += 1

        # Ensure Morph Target float curves exist on UAnimSequence
        existing_curves = unreal.AnimationLibrary.get_animation_curve_names(
            seq, unreal.RawCurveTrackTypes.RCT_FLOAT
        )
        existing_set = {str(n) for n in existing_curves}
        clip_curves = morph_curves_db.get(cid, {}).get("curves", {})
        fps = float(morph_curves_db.get(cid, {}).get("fps", 30))

        for cname, samples in clip_curves.items():
            if cname not in existing_set and samples:
                unreal.AnimationLibrary.add_curve(seq, cname, unreal.RawCurveTrackTypes.RCT_FLOAT, False)
                times = [float(i) / fps for i in range(len(samples))]
                vals = [float(v) for v in samples]
                unreal.AnimationLibrary.add_float_curve_keys(seq, cname, times, vals)
                curves_injected += 1

        seqs[cid] = seq

    log(
        f"Imported all {len(seqs)} AnimSequences into {anim_dest} "
        f"(markers={markers_injected}, fallback_curves_injected={curves_injected})"
    )
    return seqs


def create_anim_blueprint_and_showcase_map(skel_mesh: unreal.SkeletalMesh) -> None:
    # 1. Create ABP_Operative inheriting from UMorphRigAnimInstance
    abp_factory = unreal.AnimBlueprintFactory()
    abp_factory.set_editor_property("parent_class", unreal.MorphRigAnimInstance.static_class())
    abp_factory.set_editor_property("target_skeleton", skel_mesh.skeleton)
    abp_factory.set_editor_property("preview_skeletal_mesh", skel_mesh)

    abp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "ABP_Operative", "/Game/MorphRig/Character", unreal.AnimBlueprint, abp_factory
    )
    if not abp:
        raise RuntimeError("Failed to create /Game/MorphRig/Character/ABP_Operative")
    unreal.EditorAssetLibrary.save_loaded_asset(abp, False)
    log("Created /Game/MorphRig/Character/ABP_Operative (parent=UMorphRigAnimInstance)")

    # 2. Create /Game/MorphRig/Maps/ShowcaseMap with DefaultGameMode = AMorphRigGameMode
    map_path = "/Game/MorphRig/Maps/ShowcaseMap"
    lvl_sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    lvl_sub.new_level(map_path)
    editor_sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor_sub.get_editor_world()
    if world:
        ws = world.get_world_settings()
        ws.set_editor_property("default_game_mode", unreal.MorphRigGameMode.static_class())
    lvl_sub.save_current_level()
    log(f"Created and saved {map_path} with AMorphRigGameMode")


def main() -> None:
    log("=== Starting Headless MORPHRIG Asset Import Pipeline ===")
    disable_interchange_fbx()

    if unreal.EditorAssetLibrary.does_directory_exist("/Game/MorphRig"):
        log("Cleaning previous /Game/MorphRig directory...")
        unreal.EditorAssetLibrary.delete_directory("/Game/MorphRig")

    textures = import_textures()
    materials = build_all_materials(textures)
    skel_mesh = import_character_mesh_and_lods(materials)
    import_dialogue_audio()
    seqs = import_all_animations(skel_mesh)

    hit_seqs = [seqs["hit_f"], seqs["hit_b"], seqs["hit_l"], seqs["hit_r"]]
    summary_json = unreal.MorphRigEditorHelpers.finalize_operative_assets(
        skel_mesh, seqs["idle_combat"], hit_seqs
    )
    log(f"C++ Asset Finalization Summary: {summary_json}")
    summary = json.loads(summary_json)

    # Enforce strict SPEC.md invariants!
    height_cm = float(summary["standing_height_cm"])
    if not (178.0 <= height_cm <= 182.0):
        raise RuntimeError(f"Standing height {height_cm:.2f} cm outside 180 +/- 2 cm spec!")
    if summary["root_bone"] != "root":
        raise RuntimeError(f"Root bone #0 is '{summary['root_bone']}', expected 'root'!")
    if int(summary["num_bones"]) != 92:
        raise RuntimeError(f"Expected 92 deformation bones, got {summary['num_bones']}!")
    if int(summary["num_morph_targets"]) < 44:
        raise RuntimeError(f"Expected >= 44 non-zero morph targets, got {summary['num_morph_targets']}!")
    if int(summary["num_lods"]) != 3:
        raise RuntimeError(f"Expected 3 LODs, got {summary['num_lods']}!")
    if int(summary["num_sockets"]) < 10:
        raise RuntimeError(f"Expected 10 sockets, got {summary['num_sockets']}!")

    create_anim_blueprint_and_showcase_map(skel_mesh)

    unreal.EditorAssetLibrary.save_directory("/Game/MorphRig", only_if_is_dirty=False, recursive=True)
    log("=== MORPHRIG Asset Import & Verification Completed Successfully! ===")


if __name__ == "__main__":
    main()

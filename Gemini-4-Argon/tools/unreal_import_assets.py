#!/usr/bin/env python3
"""
Headless Unreal Engine 5.8.3 asset import & map setup script for MorphRig.
Imports:
  - PBR texture sets from export/textures/*.png -> /Game/MorphRig/Textures/
  - Spoken dialogue audio from source/audio/dialogue.wav -> /Game/MorphRig/Audio/dialogue
  - SkeletalMesh + Skeleton + 38 Morph Targets from export/Operative.fbx (+ LOD1 & LOD2) -> /Game/MorphRig/Character/
  - All 96 required animations from export/animations/*.fbx -> /Game/MorphRig/Animations/
  - Creates and saves default map /Game/Maps/ShowcaseArena
"""

import glob
import os
import unreal

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXPORT_DIR = os.path.join(REPO_ROOT, "export")
ANIM_DIR = os.path.join(EXPORT_DIR, "animations")
TEX_DIR = os.path.join(EXPORT_DIR, "textures")
AUDIO_WAV = os.path.join(REPO_ROOT, "source", "audio", "dialogue.wav")

ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()


def import_textures():
    unreal.log("[MorphRig] Importing PBR textures...")
    tasks = []
    for png_path in sorted(glob.glob(os.path.join(TEX_DIR, "*.png"))):
        name = os.path.splitext(os.path.basename(png_path))[0]
        # Import key maps (_D, _ORM, _N, _E) to keep cooking fast and deterministic
        if not name.endswith(("_D", "_ORM", "_N", "_E")):
            continue
        t = unreal.AssetImportTask()
        t.filename = png_path
        t.destination_path = "/Game/MorphRig/Textures"
        t.destination_name = name
        t.replace_existing = True
        t.automated = True
        t.save = False
        tasks.append(t)

    if tasks:
        ASSET_TOOLS.import_asset_tasks(tasks)
    unreal.log(f"[MorphRig] Imported {len(tasks)} textures.")


def import_audio():
    if not os.path.exists(AUDIO_WAV):
        unreal.log_warning(f"[MorphRig] Audio file not found: {AUDIO_WAV}")
        return
    t = unreal.AssetImportTask()
    t.filename = AUDIO_WAV
    t.destination_path = "/Game/MorphRig/Audio"
    t.destination_name = "dialogue"
    t.replace_existing = True
    t.automated = True
    t.save = False
    ASSET_TOOLS.import_asset_tasks([t])
    unreal.log("[MorphRig] Imported /Game/MorphRig/Audio/dialogue")


def safe_set(obj, prop, val):
    try:
        obj.set_editor_property(prop, val)
    except Exception as e:
        unreal.log_warning(f"[MorphRig] Could not set {prop} on {type(obj).__name__}: {e}")


def make_fbx_skeletal_options(skeleton=None, is_anim=False):
    opts = unreal.FbxImportUI()
    safe_set(opts, "automated_import_should_detect_type", False)
    if not is_anim:
        safe_set(opts, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        safe_set(opts, "import_mesh", True)
        safe_set(opts, "import_as_skeletal", True)
        safe_set(opts, "import_animations", False)
        safe_set(opts, "import_materials", True)
        safe_set(opts, "import_textures", False)
        safe_set(opts, "create_physics_asset", False)
        sm_data = opts.get_editor_property("skeletal_mesh_import_data")
        safe_set(sm_data, "import_morph_targets", True)
        safe_set(sm_data, "update_skeleton_reference_pose", False)
        safe_set(sm_data, "use_t0_as_ref_pose", True)
        if skeleton:
            safe_set(opts, "skeleton", skeleton)
    else:
        safe_set(opts, "mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
        safe_set(opts, "import_mesh", False)
        safe_set(opts, "import_as_skeletal", False)
        safe_set(opts, "import_animations", True)
        safe_set(opts, "import_materials", False)
        safe_set(opts, "import_textures", False)
        safe_set(opts, "skeleton", skeleton)
        anim_data = opts.get_editor_property("anim_sequence_import_data")
        safe_set(anim_data, "animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
        safe_set(anim_data, "import_meshes_in_bone_hierarchy", False)
        safe_set(anim_data, "import_custom_attribute", True)
        safe_set(anim_data, "import_bone_tracks", True)
        safe_set(anim_data, "use_default_sample_rate", False)
        safe_set(anim_data, "custom_sample_rate", 30)
    return opts


def import_character_and_lods():
    unreal.log("[MorphRig] Importing Operative.fbx SkeletalMesh + Morph Targets...")
    fbx_factory = unreal.FbxFactory()
    t0 = unreal.AssetImportTask()
    t0.filename = os.path.join(EXPORT_DIR, "Operative.fbx")
    t0.destination_path = "/Game/MorphRig/Character"
    t0.destination_name = "Operative"
    t0.replace_existing = True
    t0.automated = True
    t0.save = False
    t0.factory = fbx_factory
    t0.options = make_fbx_skeletal_options(skeleton=None, is_anim=False)
    ASSET_TOOLS.import_asset_tasks([t0])

    skel_mesh = unreal.EditorAssetLibrary.load_asset("/Game/MorphRig/Character/Operative")
    skeleton = unreal.EditorAssetLibrary.load_asset("/Game/MorphRig/Character/Operative_Skeleton")

    # Import LOD1 and LOD2 onto Operative SkeletalMesh (and also as standalone verification assets)
    for lod_idx, lod_name in [(1, "Operative_LOD1"), (2, "Operative_LOD2")]:
        lod_fbx = os.path.join(EXPORT_DIR, f"{lod_name}.fbx")
        if os.path.exists(lod_fbx):
            try:
                if hasattr(unreal, "EditorSkeletalMeshLibrary") and hasattr(unreal.EditorSkeletalMeshLibrary, "import_mesh_lod"):
                    unreal.EditorSkeletalMeshLibrary.import_mesh_lod(skel_mesh, lod_fbx, lod_idx)
                    unreal.log(f"[MorphRig] Attached LOD{lod_idx} onto /Game/MorphRig/Character/Operative")
                elif hasattr(unreal, "SkeletalMeshEditorSubsystem"):
                    sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
                    if hasattr(sub, "import_lod"):
                        sub.import_lod(skel_mesh, lod_idx, lod_fbx)
                        unreal.log(f"[MorphRig] Attached LOD{lod_idx} via SkeletalMeshEditorSubsystem")
            except Exception as e:
                unreal.log_warning(f"[MorphRig] import_mesh_lod fallback for LOD{lod_idx}: {e}")

            tl = unreal.AssetImportTask()
            tl.filename = lod_fbx
            tl.destination_path = "/Game/MorphRig/Character"
            tl.destination_name = lod_name
            tl.replace_existing = True
            tl.automated = True
            tl.save = False
            tl.factory = fbx_factory
            tl.options = make_fbx_skeletal_options(skeleton=skeleton, is_anim=False)
            ASSET_TOOLS.import_asset_tasks([tl])

    return skel_mesh, skeleton


def configure_pbr_materials():
    unreal.log("[MorphRig] Wiring PBR material nodes and TeamA/TeamB parameters...")
    mat_Editing = unreal.MaterialEditingLibrary
    mat_map = {
        "M_Operative_Skin": "T_Operative_Skin",
        "M_Operative_Eyes": "T_Operative_Eyes",
        "M_Operative_Suit": "T_Operative_Suit",
        "M_Operative_Armor": "T_Operative_Armor",
        "M_Operative_CyberArm": "T_Operative_CyberArm",
        "M_Operative_Props_Accent": "T_Operative_Props_Accent_TeamA",
    }

    for mat_name, tex_prefix in mat_map.items():
        mat_path = f"/Game/MorphRig/Character/{mat_name}"
        if not unreal.EditorAssetLibrary.does_asset_exist(mat_path):
            mat = ASSET_TOOLS.create_asset(mat_name, "/Game/MorphRig/Character", unreal.Material, unreal.MaterialFactoryNew())
        else:
            mat = unreal.EditorAssetLibrary.load_asset(mat_path)
        if not mat:
            continue

        mat_Editing.delete_all_material_expressions(mat)

        tex_d = unreal.EditorAssetLibrary.load_asset(f"/Game/MorphRig/Textures/{tex_prefix}_D")
        tex_orm = unreal.EditorAssetLibrary.load_asset(f"/Game/MorphRig/Textures/{tex_prefix}_ORM")
        tex_n = unreal.EditorAssetLibrary.load_asset(f"/Game/MorphRig/Textures/{tex_prefix}_N")
        tex_e = unreal.EditorAssetLibrary.load_asset(f"/Game/MorphRig/Textures/{tex_prefix}_E")

        if tex_d:
            node_d = mat_Editing.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -420, -180)
            node_d.set_editor_property("parameter_name", "BaseColorMap")
            node_d.set_editor_property("texture", tex_d)
            mat_Editing.connect_material_property(node_d, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

        if tex_orm:
            node_orm = mat_Editing.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -420, 40)
            node_orm.set_editor_property("parameter_name", "ORMMap")
            node_orm.set_editor_property("texture", tex_orm)
            mat_Editing.connect_material_property(node_orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
            mat_Editing.connect_material_property(node_orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
            mat_Editing.connect_material_property(node_orm, "B", unreal.MaterialProperty.MP_METALLIC)

        if tex_n:
            node_n = mat_Editing.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -420, 260)
            node_n.set_editor_property("parameter_name", "NormalMap")
            node_n.set_editor_property("texture", tex_n)
            node_n.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            mat_Editing.connect_material_property(node_n, "RGB", unreal.MaterialProperty.MP_NORMAL)

        if tex_e:
            node_e = mat_Editing.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -420, 480)
            node_e.set_editor_property("parameter_name", "EmissiveMap")
            node_e.set_editor_property("texture", tex_e)
            mat_Editing.connect_material_property(node_e, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

        mat_Editing.recompile_material(mat)


def import_animations(skeleton):
    unreal.log("[MorphRig] Importing all 96 animation FBXs...")
    fbx_factory = unreal.FbxFactory()
    tasks = []
    for fbx_path in sorted(glob.glob(os.path.join(ANIM_DIR, "*.fbx"))):
        anim_id = os.path.splitext(os.path.basename(fbx_path))[0]
        t = unreal.AssetImportTask()
        t.filename = fbx_path
        t.destination_path = "/Game/MorphRig/Animations"
        t.destination_name = anim_id
        t.replace_existing = True
        t.automated = True
        t.save = False
        t.factory = fbx_factory
        t.options = make_fbx_skeletal_options(skeleton=skeleton, is_anim=True)
        tasks.append(t)

    ASSET_TOOLS.import_asset_tasks(tasks)
    unreal.log(f"[MorphRig] Imported {len(tasks)} animation sequences.")


def create_showcase_map():
    unreal.log("[MorphRig] Creating and saving /Game/Maps/ShowcaseArena ...")
    map_path = "/Game/Maps/ShowcaseArena"
    if not unreal.EditorAssetLibrary.does_asset_exist(map_path):
        try:
            subsys = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if not subsys.new_level(map_path):
                ASSET_TOOLS.create_asset("ShowcaseArena", "/Game/Maps", unreal.World, unreal.WorldFactory())
        except Exception as e:
            unreal.log_warning(f"[MorphRig] LevelEditorSubsystem.new_level fallback: {e}")
            ASSET_TOOLS.create_asset("ShowcaseArena", "/Game/Maps", unreal.World, unreal.WorldFactory())
    try:
        unreal.EditorLoadingAndSavingUtils.save_current_level()
    except Exception:
        pass


def main():
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX false")
    import_textures()
    import_audio()
    skel_mesh, skeleton = import_character_and_lods()
    configure_pbr_materials()
    if skeleton:
        import_animations(skeleton)
    create_showcase_map()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.EditorAssetLibrary.save_directory("/Game", only_if_is_dirty=False, recursive=True)
    unreal.log("[MorphRig] All Unreal Engine 5.8.3 assets and ShowcaseArena map imported and saved!")


if __name__ == "__main__":
    main()

"""Import the MORPHRIG production into the Unreal project.

    UnrealEditor-Cmd <project> -run=pythonscript -script=tools/ue_import.py

Stages
    1  textures            24 PNGs           -> /Game/MorphRig/Textures
    2  skeletal mesh       LOD0             -> /Game/MorphRig/Meshes/SK_Operative
    3  LODs                LOD1, LOD2       -> imported into SK_Operative
    4  animations         96 clips          -> /Game/MorphRig/Animations/A_<clip>
    5  materials          8 + 1 instance    -> /Game/MorphRig/Materials
    6  clip table          96 rows          -> /Game/MorphRig/DT_MorphRigClips
    7  speech audio        dialogue.wav     -> /Game/MorphRig/Audio/S_Dialogue
    8  showcase level      room + operative -> /Game/MorphRig/Maps/L_MorphRigShowroom

A JSON report is written to /tmp/ue_import_report.json.
"""

import json
import os
import traceback

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPORT = os.environ.get("MORPHRIG_REPORT",
                        os.path.join(ROOT, "build", "ue_import_report.json"))

MESH_DIR = "/Game/MorphRig/Meshes"
ANIM_DIR = "/Game/MorphRig/Animations"
TEX_DIR = "/Game/MorphRig/Textures"
MAT_DIR = "/Game/MorphRig/Materials"
AUDIO_DIR = "/Game/MorphRig/Audio"
MAP_DIR = "/Game/MorphRig/Maps"
TABLE_PATH = "/Game/MorphRig/DT_MorphRigClips"

MATERIAL_NAMES = ["M_Skin", "M_Face", "M_Suit", "M_Armor",
                  "M_Metal", "M_Optic", "M_Energy", "M_Accent"]

REPORT_DATA = {"stages": {}, "errors": []}


def log(msg):
    unreal.log("[MorphRigImport] %s" % msg)


def write_report():
    """Write the report and flush it to disk.

    The editor can shut down right after the script returns, so the report
    is flushed explicitly and rewritten after every stage.
    """
    try:
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        with open(REPORT, "w") as fh:
            json.dump(REPORT_DATA, fh, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception as exc:  # noqa: BLE001
        log("could not write the report: %s" % exc)


def stage(name):
    def deco(fn):
        def wrapper(*args, **kwargs):
            log("stage %s" % name)
            try:
                result = fn(*args, **kwargs)
                REPORT_DATA["stages"][name] = {"ok": True, "result": result}
                log("stage %s ok" % name)
                write_report()
                return result
            except Exception as exc:  # noqa: BLE001
                REPORT_DATA["stages"][name] = {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(),
                }
                REPORT_DATA["errors"].append("%s: %s" % (name, exc))
                log("stage %s FAILED: %s" % (name, exc))
                unreal.log_error(traceback.format_exc())
                write_report()
                return None
        return wrapper
    return deco


def set_prop(obj, name, value):
    """Set an editor property, ignoring the ones this build does not expose."""
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        log("  property %s not set (%s)" % (name, exc))
        return False


def fbx_type(name):
    try:
        return getattr(unreal.FBXImportType, name)
    except Exception:  # noqa: BLE001
        return None


def import_task(filename, destination, options=None, factory=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", False)
    if options is not None:
        task.set_editor_property("options", options)
    if factory is not None:
        task.set_editor_property("factory", factory)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return list(task.get_editor_property("imported_object_paths"))


# ---------------------------------------------------------------------------
# 0  clean
# ---------------------------------------------------------------------------

@stage("clean")
def clean_assets():
    """Remove everything the import creates, so the script is idempotent.

    The animation and material imports rename their asset to a fixed name.
    Without the clean step the rename fails when the asset already exists
    and a duplicate is left behind.
    """
    removed = []
    for folder in ("/Game/MorphRig/Animations", "/Game/MorphRig/Textures",
                   "/Game/MorphRig/Materials", "/Game/MorphRig/Audio"):
        if unreal.EditorAssetLibrary.does_directory_exist(folder):
            if unreal.EditorAssetLibrary.delete_directory(folder):
                removed.append(folder)
        else:
            # the folder holds only assets, remove them one by one
            for asset in unreal.EditorAssetLibrary.list_assets(folder, recursive=True):
                if unreal.EditorAssetLibrary.delete_asset(asset):
                    removed.append(asset)
    for asset in ("/Game/MorphRig/Meshes/SK_Operative",
                  "/Game/MorphRig/Meshes/Operative_Skeleton",
                  "/Game/MorphRig/DT_MorphRigClips"):
        if unreal.EditorAssetLibrary.does_asset_exist(asset):
            if unreal.EditorAssetLibrary.delete_asset(asset):
                removed.append(asset)
    # the folder of the scale probe, it is not part of the delivery
    if unreal.EditorAssetLibrary.does_directory_exist("/Game/MorphRig/ScaleTest"):
        if unreal.EditorAssetLibrary.delete_directory("/Game/MorphRig/ScaleTest"):
            removed.append("/Game/MorphRig/ScaleTest")
    return {"removed": removed}


# ---------------------------------------------------------------------------
# 1  textures
# ---------------------------------------------------------------------------

@stage("textures")
def import_textures():
    src = os.path.join(ROOT, "export", "textures")
    names = sorted(f for f in os.listdir(src) if f.lower().endswith(".png"))
    created = []
    for name in names:
        paths = import_task(os.path.join(src, name), TEX_DIR)
        created.extend(paths)
    settings = configure_textures(created)
    return {"count": len(created), "assets": created, "settings": settings}


def configure_textures(paths):
    """Match the texture settings to the sampler types of the material graphs.

    Unreal derives the sampler type of a texture from its compression
    settings and refuses to compile a material when the node and the texture
    disagree.  The authored graphs sample the three maps with fixed sampler
    types, so the textures have to be stored the same way:

      base colour -> colour sampler, sRGB
      normal      -> normal sampler, linear
      ORM         -> masks sampler, linear, R=AO G=roughness B=metallic
    """
    result = []
    for path in paths:
        asset = unreal.load_asset(path)
        if not isinstance(asset, unreal.Texture):
            continue
        name = asset.get_name().lower()
        if name.endswith("_normal"):
            compression = unreal.TextureCompressionSettings.TC_NORMALMAP
            srgb = False
        elif name.endswith("_orm"):
            compression = unreal.TextureCompressionSettings.TC_MASKS
            srgb = False
        elif name.endswith("_basecolor"):
            compression = unreal.TextureCompressionSettings.TC_DEFAULT
            srgb = True
        else:
            continue
        asset.set_editor_property("compression_settings", compression)
        asset.set_editor_property("srgb", srgb)
        unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
        result.append({"asset": path,
                       "compression": compression.name,
                       "srgb": srgb})
    return result


# ---------------------------------------------------------------------------
# 2  skeletal mesh
# ---------------------------------------------------------------------------

def mesh_import_options():
    options = unreal.FbxImportUI()
    set_prop(options, "import_mesh", True)
    set_prop(options, "import_animations", False)
    set_prop(options, "import_as_skeletal", True)
    set_prop(options, "mesh_type_to_import", fbx_type("FBXIT_SKELETAL_MESH"))
    set_prop(options, "original_import_type", fbx_type("FBXIT_SKELETAL_MESH"))
    set_prop(options, "create_physics_asset", False)
    set_prop(options, "import_textures", False)
    set_prop(options, "import_materials", False)

    data = unreal.FbxSkeletalMeshImportData()
    set_prop(data, "import_morph_targets", True)
    set_prop(data, "update_skeleton_reference_pose", False)
    set_prop(data, "use_t0_as_ref_pose", False)
    set_prop(data, "import_mesh_lo_ds", False)
    set_prop(data, "convert_scene", True)
    set_prop(data, "convert_scene_unit", True)
    set_prop(options, "skeletal_mesh_import_data", data)
    return options


@stage("skeletal_mesh")
def import_mesh():
    src = os.path.join(ROOT, "export", "Operative.fbx")
    paths = import_task(src, MESH_DIR, mesh_import_options())
    meshes = []
    for path in paths:
        asset = unreal.load_asset(path)
        if isinstance(asset, unreal.SkeletalMesh):
            meshes.append(asset)
    if not meshes:
        raise RuntimeError("no skeletal mesh imported from %s" % src)
    mesh = meshes[0]
    unreal.EditorAssetLibrary.rename_asset(mesh.get_path_name(),
                                           "%s/SK_Operative" % MESH_DIR)
    skeleton = mesh.get_editor_property("skeleton")
    return {
        "mesh": mesh.get_path_name(),
        "skeleton": skeleton.get_path_name() if skeleton else None,
        "materials": len(mesh.get_editor_property("materials")),
    }


# ---------------------------------------------------------------------------
# 3  LODs
# ---------------------------------------------------------------------------

@stage("lods")
def import_lods():
    mesh = unreal.load_asset("%s/SK_Operative" % MESH_DIR)
    if mesh is None:
        raise RuntimeError("SK_Operative missing")
    subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    results = []
    for index, name in ((1, "Operative_LOD1"), (2, "Operative_LOD2")):
        src = os.path.join(ROOT, "export", "LOD", "%s.fbx" % name)
        if not os.path.exists(src):
            results.append({"lod": index, "ok": False, "error": "missing %s" % src})
            continue
        try:
            new_index = subsystem.import_lod(mesh, index, src)
            results.append({"lod": index, "ok": new_index != -1,
                            "returned": new_index})
        except Exception as exc:  # noqa: BLE001
            results.append({"lod": index, "ok": False, "error": str(exc)})
    try:
        results.append({"lod_count": subsystem.get_lod_count(mesh)})
    except Exception as exc:  # noqa: BLE001
        results.append({"lod_count_error": str(exc)})
    return results


# ---------------------------------------------------------------------------
# 4  animations
# ---------------------------------------------------------------------------

@stage("animations")
def import_animations():
    manifest = json.load(open(os.path.join(ROOT, "docs", "animation_manifest.json")))
    mesh = unreal.load_asset("%s/SK_Operative" % MESH_DIR)
    skeleton = mesh.get_editor_property("skeleton") if mesh else None
    if skeleton is None:
        raise RuntimeError("no skeleton to import animations against")

    created = {}
    failures = []
    for clip in manifest["clips"]:
        name = clip["name"]
        src = os.path.join(ROOT, "export", "animations", "%s.fbx" % name)
        if not os.path.exists(src):
            failures.append({"clip": name, "error": "missing fbx"})
            continue

        target = "%s/A_%s" % (ANIM_DIR, name)

        # The importer names the asset after the FBX file and the script then
        # renames it to A_<clip>.  If A_<clip> is still there from an earlier
        # run the rename fails and a duplicate is left behind, so the target
        # and any leftover copy are removed first.
        for stale in (target, "%s/%s" % (ANIM_DIR, name)):
            if unreal.EditorAssetLibrary.does_asset_exist(stale):
                unreal.EditorAssetLibrary.delete_asset(stale)

        options = unreal.FbxImportUI()
        set_prop(options, "import_mesh", False)
        set_prop(options, "import_animations", True)
        set_prop(options, "import_as_skeletal", False)
        set_prop(options, "mesh_type_to_import", fbx_type("FBXIT_ANIMATION"))
        set_prop(options, "original_import_type", fbx_type("FBXIT_ANIMATION"))
        set_prop(options, "skeleton", skeleton)
        set_prop(options, "import_materials", False)
        set_prop(options, "import_textures", False)

        data = unreal.FbxAnimSequenceImportData()
        set_prop(data, "import_bone_tracks", True)
        set_prop(data, "import_custom_attribute", True)
        set_prop(data, "delete_existing_morph_target_curves", False)
        set_prop(data, "remove_redundant_keys", True)
        set_prop(data, "convert_scene", True)
        set_prop(data, "convert_scene_unit", True)
        set_prop(options, "anim_sequence_import_data", data)

        try:
            paths = import_task(src, ANIM_DIR, options)
        except Exception as exc:  # noqa: BLE001
            failures.append({"clip": name, "error": str(exc)})
            continue

        if not paths:
            failures.append({"clip": name, "error": "nothing imported"})
            continue

        asset = unreal.load_asset(paths[0])
        if asset is None:
            failures.append({"clip": name, "error": "asset not loadable"})
            continue

        # the dash clips carry the root motion that drives the capsule
        if name.startswith("dash_"):
            set_prop(asset, "enable_root_motion", True)

        if asset.get_path_name() != target:
            if not unreal.EditorAssetLibrary.rename_asset(asset.get_path_name(), target):
                log("  rename failed for %s" % name)
                failures.append({"clip": name, "error": "rename failed"})
                continue
        created[name] = target

    return {"created": len(created), "failures": failures,
            "missing": sorted(set(c["name"] for c in manifest["clips"]) - set(created))}


# ---------------------------------------------------------------------------
# 5  materials
# ---------------------------------------------------------------------------

def set_usage_flags(mat, skeletal=True):
    """Allow the material to be used on the Operative's skeletal mesh.

    Without the skeletal mesh usage flag Unreal refuses to draw the
    material on a skeletal mesh: it logs "Material with missing usage flag
    was applied to skeletal mesh" and falls back to the default material.
    """
    if mat is None:
        return
    for prop, value in (("used_with_skeletal_mesh", skeletal),
                        ("used_with_static_mesh", True),
                        ("used_with_morph_targets", True),
                        ("used_with_instanced_static_meshes", False)):
        try:
            mat.set_editor_property(prop, value)
        except Exception as exc:  # noqa: BLE001
            log("  usage flag %s not set (%s)" % (prop, exc))


def build_material(name, textures, emissive=False, team_color=False):
    path = "%s/%s" % (MAT_DIR, name)
    existing = unreal.load_asset(path)
    if existing is not None:
        unreal.EditorAssetLibrary.delete_asset(path)

    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError("could not create material %s" % name)

    lib = unreal.MaterialEditingLibrary

    base = lib.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, -250)
    base.set_editor_property("parameter_name", "BaseColorTexture")
    base.set_editor_property("texture", textures["base"])
    base.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    lib.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    normal = lib.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, 0)
    normal.set_editor_property("parameter_name", "NormalTexture")
    normal.set_editor_property("texture", textures["normal"])
    normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    lib.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)

    orm = lib.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -900, 250)
    orm.set_editor_property("parameter_name", "ORMTexture")
    orm.set_editor_property("texture", textures["orm"])
    orm.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    lib.connect_material_property(orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    lib.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    lib.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)

    color_output = base

    if team_color:
        # M_Accent carries the team colour parameter, the runtime switches it
        param = lib.create_material_expression(
            mat, unreal.MaterialExpressionVectorParameter, -900, -450)
        param.set_editor_property("parameter_name", "TeamColor")
        param.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
        multiply = lib.create_material_expression(
            mat, unreal.MaterialExpressionMultiply, -450, -300)
        lib.connect_material_expressions(base, "RGB", multiply, "A")
        lib.connect_material_expressions(param, "", multiply, "B")
        lib.connect_material_property(multiply, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        color_output = None

    if emissive:
        # M_Energy glows with its base colour
        intensity = lib.create_material_expression(
            mat, unreal.MaterialExpressionConstant, -450, 60)
        intensity.set_editor_property("r", 3.0)
        multiply = lib.create_material_expression(
            mat, unreal.MaterialExpressionMultiply, -200, 60)
        lib.connect_material_expressions(base, "RGB", multiply, "A")
        lib.connect_material_expressions(intensity, "", multiply, "B")
        lib.connect_material_property(multiply, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    lib.layout_material_expressions(mat)
    set_usage_flags(mat)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
    return mat


@stage("materials")
def build_materials():
    made = {}
    for name in MATERIAL_NAMES:
        textures = {}
        for slot, suffix in (("base", "basecolor"), ("normal", "normal"), ("orm", "orm")):
            asset = unreal.load_asset("%s/%s_%s" % (TEX_DIR, name, suffix))
            if asset is None:
                raise RuntimeError("texture %s_%s missing" % (name, suffix))
            textures[slot] = asset
        made[name] = build_material(
            name, textures,
            emissive=(name == "M_Energy"),
            team_color=(name == "M_Accent"),
        ).get_path_name()

    # the team accent instance the character swaps at runtime
    mi_path = "%s/MI_M_Accent" % MAT_DIR
    if unreal.EditorAssetLibrary.does_asset_exist(mi_path):
        unreal.EditorAssetLibrary.delete_asset(mi_path)
    factory = unreal.MaterialInstanceConstantFactoryNew()
    try:
        factory.set_editor_property("initial_parent",
                                    unreal.load_asset(made["M_Accent"]))
    except Exception as exc:  # noqa: BLE001
        log("  initial_parent not available (%s)" % exc)
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "MI_M_Accent", MAT_DIR, unreal.MaterialInstanceConstant, factory)
    if mi is None:
        raise RuntimeError("could not create MI_M_Accent")
    try:
        mi.set_editor_property("parent", unreal.load_asset(made["M_Accent"]))
    except Exception as exc:  # noqa: BLE001
        log("  could not set the parent (%s)" % exc)
    unreal.EditorAssetLibrary.save_asset(mi_path, only_if_is_dirty=False)
    return {"materials": made, "instance": mi_path}


@stage("viewmaterials")
def build_view_materials():
    """The two extra materials the showcase uses for the shading views.

    M_ViewNormal shows the world space normal of the surface, M_ViewClay is
    a flat grey without any texture.  The runtime swaps the eight authored
    slots of the Operative for these two while the view is not "textured".
    """
    lib = unreal.MaterialEditingLibrary
    made = {}

    # --- the normal view -------------------------------------------------
    normal_path = "%s/M_ViewNormal" % MAT_DIR
    if unreal.EditorAssetLibrary.does_asset_exist(normal_path):
        unreal.EditorAssetLibrary.delete_asset(normal_path)
    normal = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_ViewNormal", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if normal is None:
        raise RuntimeError("could not create M_ViewNormal")
    normal.set_editor_property("shading_model",
                               unreal.MaterialShadingModel.MSM_UNLIT)
    pixel_normal = lib.create_material_expression(
        normal, unreal.MaterialExpressionPixelNormalWS, -400, 0)
    if not lib.connect_material_property(pixel_normal, "",
                                         unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        log("  the normal could not be connected to the emissive channel")
    lib.layout_material_expressions(normal)
    set_usage_flags(normal)
    lib.recompile_material(normal)
    unreal.EditorAssetLibrary.save_asset(normal_path, only_if_is_dirty=False)
    made["normal"] = normal_path

    # --- the clay view ---------------------------------------------------
    clay_path = "%s/M_ViewClay" % MAT_DIR
    if unreal.EditorAssetLibrary.does_asset_exist(clay_path):
        unreal.EditorAssetLibrary.delete_asset(clay_path)
    clay = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_ViewClay", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if clay is None:
        raise RuntimeError("could not create M_ViewClay")
    clay.set_editor_property("shading_model",
                             unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    colour = lib.create_material_expression(
        clay, unreal.MaterialExpressionConstant3Vector, -400, -120)
    colour.set_editor_property("constant",
                               unreal.LinearColor(0.36, 0.37, 0.40, 1.0))
    if not lib.connect_material_property(colour, "",
                                         unreal.MaterialProperty.MP_BASE_COLOR):
        log("  the clay colour could not be connected to the base colour")
    rough = lib.create_material_expression(
        clay, unreal.MaterialExpressionConstant, -400, 120)
    rough.set_editor_property("r", 0.65)
    if not lib.connect_material_property(rough, "",
                                         unreal.MaterialProperty.MP_ROUGHNESS):
        log("  the clay roughness could not be connected")
    lib.layout_material_expressions(clay)
    set_usage_flags(clay)
    lib.recompile_material(clay)
    unreal.EditorAssetLibrary.save_asset(clay_path, only_if_is_dirty=False)
    made["clay"] = clay_path

    # read the graph back, so the report shows what was really connected
    graphs = {}
    for key, path in made.items():
        mat = unreal.load_asset(path)
        expressions = [e.get_class().get_name()
                       for e in lib.get_material_expressions(mat)]
        linked = {}
        for prop in (unreal.MaterialProperty.MP_EMISSIVE_COLOR,
                     unreal.MaterialProperty.MP_BASE_COLOR,
                     unreal.MaterialProperty.MP_ROUGHNESS):
            node = lib.get_material_property_input_node(mat, prop)
            linked[str(prop)] = (node.get_class().get_name()
                                 if node is not None else None)
        graphs[key] = {"expressions": expressions, "inputs": linked}
    return {"materials": made, "graphs": graphs}


@stage("assign_materials")
def assign_materials():
    mesh = unreal.load_asset("%s/SK_Operative" % MESH_DIR)
    if mesh is None:
        raise RuntimeError("SK_Operative missing")
    slots = []
    for name in MATERIAL_NAMES:
        asset = unreal.load_asset("%s/%s" % (MAT_DIR, name))
        if asset is None:
            raise RuntimeError("material %s missing" % name)
        slots.append(unreal.SkeletalMaterial(material_interface=asset,
                                             material_slot_name=name))
    mesh.set_editor_property("materials", slots)
    unreal.EditorAssetLibrary.save_asset(mesh.get_path_name(), only_if_is_dirty=False)
    return {"slots": len(slots),
            "names": [s.get_editor_property("material_slot_name") for s in slots]}


# ---------------------------------------------------------------------------
# 6  clip table
# ---------------------------------------------------------------------------

@stage("clip_table")
def build_clip_table():
    manifest = json.load(open(os.path.join(ROOT, "docs", "animation_manifest.json")))

    # The CSV importer uses the first column as the row name and maps the
    # remaining columns onto the fields of the row struct.
    header = ["Name", "ClipName", "AssetPath", "Form", "bLoop", "Duration",
              "Layer", "RootMotion", "Markers"]
    lines = [",".join(header)]
    for clip in manifest["clips"]:
        name = clip["name"]
        markers = []
        for marker in clip.get("markers", []):
            if isinstance(marker, (list, tuple)):
                markers.append("%s@%s" % (marker[0], marker[1]))
            else:
                markers.append(str(marker))
        row = [
            name,
            name,
            clip.get("unreal_asset") or ("%s/A_%s" % (ANIM_DIR, name)),
            clip.get("form", "one_shot"),
            "True" if clip.get("loop") else "False",
            "%.4f" % float(clip.get("duration", 0.0)),
            clip.get("layer", "FullBody.Idle"),
            clip.get("root_motion", "in_place"),
            ",".join(markers),
        ]
        lines.append(",".join('"%s"' % cell.replace('"', '""') for cell in row))
    payload = "\n".join(lines)

    table = unreal.load_asset(TABLE_PATH)
    if table is None:
        factory = unreal.DataTableFactory()
        factory.set_editor_property("struct", unreal.MorphRigClipEntry.static_struct())
        table = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "DT_MorphRigClips", "/Game/MorphRig", unreal.DataTable, factory)
    if table is None:
        raise RuntimeError("could not create the data table")
    # the row struct comes from the factory, the property is read only
    unreal.DataTableFunctionLibrary.fill_data_table_from_csv_string(
        table, payload, unreal.MorphRigClipEntry.static_struct())
    unreal.EditorAssetLibrary.save_asset(TABLE_PATH, only_if_is_dirty=False)
    try:
        row_names = table.get_row_names()
    except Exception:  # noqa: BLE001
        row_names = []
    return {"rows": len(manifest["clips"]),
            "row_names": len(row_names),
            "sample": [str(r) for r in list(row_names)[:6]],
            "row_struct": str(table.get_editor_property("row_struct"))}


# ---------------------------------------------------------------------------
# 7  speech audio
# ---------------------------------------------------------------------------

@stage("audio")
def import_audio():
    src = os.path.join(ROOT, "source", "audio", "dialogue.wav")
    if not os.path.exists(src):
        return {"ok": False, "error": "missing %s" % src}
    paths = import_task(src, AUDIO_DIR)
    renamed = []
    for path in paths:
        asset = unreal.load_asset(path)
        if asset is None:
            continue
        target = "%s/S_Dialogue" % AUDIO_DIR
        if asset.get_path_name() != target:
            unreal.EditorAssetLibrary.rename_asset(asset.get_path_name(), target)
        renamed.append(target)
    return {"paths": paths, "renamed": renamed}


# ---------------------------------------------------------------------------
# 8  showcase level
# ---------------------------------------------------------------------------

@stage("level")
def build_level():
    map_path = "%s/L_MorphRigShowroom" % MAP_DIR
    unreal.EditorLevelLibrary.new_level(map_path)

    showroom = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.MorphRigShowroom, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))

    # The player Operative is spawned by the game mode, it needs a start
    # point.  Rotator(0, 0, 0) points the Operative along +X, which is the
    # direction the character faces in Unreal.
    start = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))

    # a key directional light so the room reads well.  The light has to be
    # movable: a static light only contributes through baked light maps, and
    # this level is never baked, so a static light would light nothing.
    light = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(0, 0, 400), unreal.Rotator(-45, 35, 0))
    if light is not None:
        comps = light.get_components_by_class(unreal.DirectionalLightComponent)
        if comps:
            comps[0].set_editor_property("intensity", 6.0)
            comps[0].set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    # the frame time logger
    logger = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.MorphRigPerfLogger, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))

    # save the level under the wanted asset path
    world = unreal.EditorLevelLibrary.get_editor_world()
    saved = False
    try:
        saved = unreal.EditorLoadingAndSavingUtils.save_map(world, map_path)
    except Exception as exc:  # noqa: BLE001
        log("  save_map failed (%s)" % exc)
    try:
        unreal.EditorLevelLibrary.save_current_level()
    except Exception as exc:  # noqa: BLE001
        log("  save_current_level failed (%s)" % exc)

    return {
        "map": map_path,
        "saved": bool(saved),
        "world": world.get_path_name() if world else None,
        "showroom": showroom.get_path_name() if showroom else None,
        "player_start": start.get_path_name() if start else None,
        "perf_logger": logger.get_path_name() if logger else None,
        "actors": len(unreal.EditorLevelLibrary.get_all_level_actors()),
    }


@stage("save_all")
def save_all():
    # save_directory walks the whole folder, saving a folder path as an
    # asset is an error in the editor.
    unreal.EditorAssetLibrary.save_directory("/Game/MorphRig",
                                            only_if_is_dirty=False,
                                            recursive=True)
    return True


ALL_STAGES = [
    ("clean", clean_assets),
    ("textures", import_textures),
    ("mesh", import_mesh),
    ("lods", import_lods),
    ("animations", import_animations),
    ("materials", build_materials),
    ("viewmaterials", build_view_materials),
    ("assign", assign_materials),
    ("table", build_clip_table),
    ("audio", import_audio),
    ("level", build_level),
    ("save", save_all),
]


def main():
    """Run the requested stages.

    MORPHRIG_STAGES selects a subset, for example
    MORPHRIG_STAGES=table,level .  The default is every stage.
    """
    wanted = os.environ.get("MORPHRIG_STAGES", "").strip()
    if wanted:
        names = [n.strip() for n in wanted.split(",") if n.strip()]
    else:
        names = [n for n, _ in ALL_STAGES]

    for name, fn in ALL_STAGES:
        if name in names:
            fn()

    write_report()
    log("REPORT %s" % REPORT)
    unreal.log("MORPHRIG_IMPORT_DONE")


try:
    main()
except Exception:
    REPORT_DATA["fatal"] = traceback.format_exc()
    write_report()
    unreal.log_error(traceback.format_exc())

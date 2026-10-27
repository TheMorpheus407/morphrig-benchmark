from pathlib import Path
import hashlib
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "docs" / "validation" / "beacon_import.json"
source = json.loads((ROOT / "docs" / "validation" / "beacon_export.json").read_text())
asset_path = "/Game/Operative/ST_Beacon"
file = ROOT / "export" / "Beacon.fbx"
digest = hashlib.sha256(file.read_bytes()).hexdigest()
axis_matrix = json.loads((ROOT / "docs" / "skeleton_and_sockets.json").read_text())["axis_evidence"]["source_to_unreal_matrix"]
if REPORT.exists():
    previous = json.loads(REPORT.read_text())
    if previous.get("status") == "PASS" and previous.get("fbx_sha256") == digest and previous.get("axis_mapping") == axis_matrix and unreal.load_asset(asset_path):
        previous["reused"] = True
        previous["bounds_extent_convention"] = "Unreal half-extents in centimeters; the source-axis full spans are halved for comparison"
        REPORT.write_text(json.dumps(previous, indent=2) + "\n")
        print("Reusing persisted authored beacon", flush=True)
    else:
        previous = None
else:
    previous = None
if previous is None:
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.import_mesh = True
    options.import_animations = False
    options.import_materials = False
    options.import_textures = False
    props = options.static_mesh_import_data
    props.import_translation = unreal.Vector(0, 0, 0)
    props.import_rotation = unreal.Rotator(0, 0, 0)
    props.import_uniform_scale = 1.0
    props.convert_scene = True
    props.convert_scene_unit = False
    props.force_front_x_axis = True
    props.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
    task = unreal.AssetImportTask()
    task.filename = str(file)
    task.destination_path = "/Game/Operative"
    task.destination_name = "ST_Beacon"
    task.replace_existing = True
    task.replace_existing_settings = True
    task.automated = True
    task.save = True
    task.async_ = False
    task.factory = unreal.FbxFactory()
    task.options = options
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    tools.import_asset_tasks([task])
    meshes = [obj for obj in task.get_objects() if isinstance(obj, unreal.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError("Expected one authored static beacon")
    mesh = meshes[0]
    expected_materials = {"M_Armor", "M_Emissive", "M_Metal"}
    slots = list(mesh.get_editor_property("static_materials"))
    for index, slot in enumerate(slots):
        name = str(slot.material_slot_name)
        if name not in expected_materials:
            raise RuntimeError("Unexpected beacon material slot " + name)
        slot.material_interface = unreal.load_asset("/Game/Operative/Materials/" + name)
        slots[index] = slot
    mesh.set_editor_property("static_materials", slots)
    mesh.modify()
    if not unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).save_asset(asset_path, only_if_is_dirty=False):
        raise RuntimeError("Could not persist authored beacon")
    bounds = mesh.get_bounds().box_extent
    extent = [bounds.x, bounds.y, bounds.z]
    axis_matrix = json.loads((ROOT / "docs" / "skeleton_and_sockets.json").read_text())["axis_evidence"]["source_to_unreal_matrix"]
    expected_extent = [
        .5 * (max(axis_matrix[row][column] * endpoint for endpoint in source["bounds_cm"][column])
        - min(axis_matrix[row][column] * endpoint for endpoint in source["bounds_cm"][column]))
        for row in range(3) for column in range(3) if abs(axis_matrix[row][column]) > .5
    ]
    if any(abs(actual - expected) > .15 for actual, expected in zip(extent, expected_extent)):
        raise RuntimeError(f"Beacon bounds mismatch: {extent} != {expected_extent}")
    triangles = mesh.get_num_triangles(0)
    if triangles != source["triangles"]:
        raise RuntimeError(f"Beacon triangle mismatch: {triangles} != {source['triangles']}")
    if mesh.get_num_vertices(0) <= 0 or mesh.get_num_sections(0) <= 0:
        raise RuntimeError("Beacon has no renderable geometry")
    report = {
        "status": "PASS", "asset": asset_path, "reused": False,
        "vertices": mesh.get_num_vertices(0), "triangles": triangles,
        "sections": mesh.get_num_sections(0), "bounds_extent_cm": extent,
        "material_slots": [str(slot.material_slot_name) for slot in slots],
        "uv_channels": source["uv_layers"], "source": source["file"],
        "fbx_sha256": digest,
        "axis_mapping": axis_matrix,
        "persisted": (ROOT / "unreal" / "MorphRig" / "Content" / "Operative" / "ST_Beacon.uasset").is_file(),
        "scale": "Source-object scale 100; import_uniform_scale=1 and convert_scene_unit=False",
    }
    if not report["persisted"]:
        raise RuntimeError("Authored beacon package was not persisted")
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)

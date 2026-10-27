from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
mesh = unreal.load_asset("/Game/Operative/SK_Operative")
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
lod_editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
if not mesh:
    raise RuntimeError("Production mesh is missing")
records = []

def snapshot(label):
    record = {
        "stage": label,
        "lod_count": lod_editor.get_lod_count(mesh),
        "source_model_count": len(mesh.get_editor_property("source_models")),
        "triangles": [unreal.MorphAuditLibrary.get_lod_triangle_count(mesh, index) for index in range(3)],
        "morphs": [unreal.MorphAuditLibrary.get_lod_morph_target_count(mesh, index) for index in range(3)],
    }
    records.append(record)
    unreal.log_warning("MORPH_LOD_STAGE " + json.dumps(record))

snapshot("loaded")
for lod in (1, 2):
    imported = lod_editor.import_lod(mesh, lod, str(ROOT / "export" / f"Operative_LOD{lod}.fbx"))
    if imported != lod:
        raise RuntimeError("Native LOD import failed at " + str(lod))
    snapshot("imported_" + str(lod))
models = list(mesh.get_editor_property("source_models"))
for index, size in enumerate((1.0, .30, .12)):
    model = models[index]
    screen = model.get_editor_property("screen_size")
    screen.set_editor_property("default", size)
    model.set_editor_property("screen_size", screen)
    models[index] = model
mesh.set_editor_property("source_models", models)
snapshot("screen_size_updated")
report = {"records": records, "persisted": False}
if records[-1]["lod_count"] != 3 or records[-1]["morphs"] != [26, 26, 26]:
    (ROOT / "docs" / "validation" / "lod_restore.json").write_text(json.dumps(report, indent=2) + "\n")
    raise RuntimeError("LOD persistence preflight failed; mesh not saved")
import sys
sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
import import_operative as ops
ops.import_textures_and_materials(mesh)
ops.SAVE.append(mesh)
for asset in ops.SAVE:
    if not editor.save_asset(asset.get_path_name().split(".")[0], only_if_is_dirty=False):
        raise RuntimeError("Could not save restored material asset " + asset.get_path_name())
snapshot("material_slots_restored")
report["material_slots"] = [slot.material_interface.get_path_name() if slot.material_interface else None for slot in mesh.get_editor_property("materials")]
if any(path is None for path in report["material_slots"]):
    raise RuntimeError("LOD restoration left an unassigned material slot")
report["persisted"] = editor.save_asset("/Game/Operative/SK_Operative", only_if_is_dirty=False)
(ROOT / "docs" / "validation" / "lod_restore.json").write_text(json.dumps(report, indent=2) + "\n")
if not report["persisted"]:
    raise RuntimeError("Could not save restored LODs")

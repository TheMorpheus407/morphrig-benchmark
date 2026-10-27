from pathlib import Path
import json
import sys
import unreal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
import import_operative as ops

mesh = unreal.load_asset("/Game/Operative/SK_Operative")
if not mesh:
    raise RuntimeError("Production mesh is missing")
ops.import_textures_and_materials(mesh)
ops.SAVE.append(mesh)
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
for asset in ops.SAVE:
    if not editor.save_asset(asset.get_path_name().split(".")[0], only_if_is_dirty=False):
        raise RuntimeError("Could not save material assignment " + asset.get_path_name())
records = []
for slot in mesh.get_editor_property("materials"):
    material = slot.material_interface
    records.append({
        "slot": str(slot.material_slot_name),
        "asset": material.get_path_name() if material else None,
        "expressions": unreal.MaterialEditingLibrary.get_num_material_expressions(material) if isinstance(material, unreal.Material) else None,
    })
report = {"status": "PASS" if len(records) == 8 and all(item["asset"] for item in records) else "FAIL", "slots": records}
print(json.dumps(report, indent=2), flush=True)
(ROOT / "docs" / "validation" / "material_assignment.json").write_text(json.dumps(report, indent=2) + "\n")
if report["status"] != "PASS":
    raise RuntimeError("Material assignment did not persist")

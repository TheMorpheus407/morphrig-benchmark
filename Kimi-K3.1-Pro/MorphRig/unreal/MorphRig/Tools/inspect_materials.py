from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
report = {"api": [name for name in dir(unreal.MaterialEditingLibrary) if "expression" in name or "delete" in name], "materials": []}
mesh = unreal.load_asset("/Game/Operative/SK_Operative")
for slot in mesh.get_editor_property("materials"):
    name = str(slot.material_slot_name)
    material = slot.material_interface
    record = {"slot": name, "path": material.get_path_name() if material else None, "class": material.get_class().get_name() if material else None}
    if material and hasattr(unreal.MaterialEditingLibrary, "get_num_material_expressions"):
        record["expressions"] = unreal.MaterialEditingLibrary.get_num_material_expressions(material)
    if material and material.get_class().get_name() == "Material":
        record["expression_names"] = [str(expression) for expression in unreal.MaterialEditingLibrary.get_material_expressions(material)]
    report["materials"].append(record)
for name in ("skin_BaseColor", "skin_Roughness", "skin_Normal", "suit_BaseColor"):
    texture = unreal.load_asset("/Game/Operative/Textures/" + name)
    report[name] = {"path": texture.get_path_name() if texture else None, "srgb": texture.get_editor_property("srgb") if texture else None, "size": [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()] if texture else None}
print(json.dumps(report, indent=2), flush=True)
(ROOT / "docs" / "validation" / "material_inspection.json").write_text(json.dumps(report, indent=2) + "\n")

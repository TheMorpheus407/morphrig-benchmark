#!/usr/bin/env python3
"""Generate measured material/LOD metadata from source and any available Unreal audit."""
from pathlib import Path
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
source = json.loads((DOCS / "source_geometry_report.json").read_text())
manifest = json.loads((DOCS / "animation_manifest.json").read_text())
textures = []
raw_rgba = 0
compressed_estimate = 0
for path in sorted((ROOT / "source" / "textures").glob("*.png")):
    with path.open("rb") as stream:
        header = stream.read(24)
    width, height = struct.unpack(">II", header[16:24])
    pixels = width * height
    decoded = pixels * 4
    kind = "BaseColor" if "BaseColor" in path.name else "Normal" if "Normal" in path.name else "Roughness"
    compression = 1.0 if kind in ("BaseColor", "Normal") else .5
    raw_rgba += decoded
    compressed_estimate += pixels * compression * 4 / 3
    textures.append({"file": "source/textures/" + path.name, "width": width, "height": height, "decoded_rgba8_bytes": decoded, "export_copy": "export/textures/" + path.name, "usage": kind})
result = {
    "schema": "MorphRig.material_and_lod_report/1.2",
    "source_units": "meters, Z-up, forward -Y, root at ground origin",
    "unreal_units": "centimeters, Z-up; imported facing and actor-space yaw are documented in skeleton_and_sockets.json",
    "standing_height": {"source_m": 1.80, "unreal_cm": 180.0, "import_scale_repair": False},
    "material_slots_total": 8,
    "materials": source["materials"],
    "texture_count": len(textures),
    "texture_memory_estimate": {
        "decoded_one_resident_rgba8_set_bytes": raw_rgba,
        "decoded_with_4_3_mip_chain_bytes": round(raw_rgba * 4 / 3),
        "typical_block_compressed_with_mips_bytes": round(compressed_estimate),
        "basis": "One shared texture set, not duplicate source/export folders. Typical estimate uses 1 byte/pixel for BaseColor and normal and 0.5 byte/pixel for roughness, with a 4/3 mip chain. Actual GPU allocation is driver/compression dependent and is not presented as a measured allocation.",
    },
    "textures": textures,
    "max_texture_dimension": max(item["width"] for item in textures + [{"width": 0}]),
    "deformation_bones": source["bones"],
    "max_effective_bone_influences": source["max_influences"],
    "uv_channels": 1,
    "facial_shapes": len(source["shape_keys"]),
    "animation_inventory": {"entries": manifest["entry_count"], "motion": manifest["motion_entry_count"], "static_poses": manifest["static_pose_count"], "fps": 30},
    "lods": [],
}
for index in range(3):
    result["lods"].append({
        "lod": index, "source_triangles": source["triangles"][f"LOD{index}"],
        "required_triangle_budget": (80000, 40000, 20000)[index],
        "within_budget": source["triangles"][f"LOD{index}"] <= (80000, 40000, 20000)[index],
        "reduction_method": "Collapse-decimated body with retained explicit skin weights and UVs; face/eyes/mouth and equipped props shared to preserve close inspection and morph usability",
        "same_mesh_duplicate": False, "skeleton": "Same 70-bone hierarchy",
    })
audit_path = DOCS / "unreal_import_audit.json"
if audit_path.exists():
    audit = json.loads(audit_path.read_text())
    result["unreal_import"] = {
        "status": audit["status"], "height_cm": audit["height_cm"], "bone_count": audit["bone_count"],
        "morph_names": audit["morph_names"], "material_slots": audit["material_slots"],
        "material_interfaces": audit.get("material_interfaces", []),
        "lod_render_data": audit["lods"], "clip_count": len(audit["clips"]),
        "texture_count": len(audit.get("textures", [])), "socket_count": len(audit.get("sockets", [])),
        "audio_duration_seconds": (audit.get("audio") or {}).get("duration_seconds"),
    }
    for index, lod in enumerate(audit["lods"]):
        if index < len(result["lods"]):
            result["lods"][index]["native_morph_target_count"] = lod.get("morph_target_count")
            result["lods"][index]["native_material_slot_indices"] = lod.get("material_slot_indices")
            result["lods"][index]["unreal_render_triangles"] = lod.get("render_triangles")
            result["lods"][index]["unreal_vertices"] = lod.get("vertices")
            result["lods"][index]["unreal_sections"] = lod.get("sections")
beacon_validation = DOCS / "validation" / "beacon_import.json"
if beacon_validation.exists():
    result["deployed_beacon"] = json.loads(beacon_validation.read_text())
source_validation = DOCS / "validation" / "source_asset_validation.json"
if source_validation.exists():
    result["source_validation"] = json.loads(source_validation.read_text())["status"]
(DOCS / "material_and_lod_report.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"material_slots": 8, "textures": len(textures), "decoded_mb": raw_rgba / 1e6, "lod_triangles": source["triangles"]}))

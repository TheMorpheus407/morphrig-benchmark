#!/usr/bin/env python3
"""
Master Blender 5.1 Production Asset Builder for MorphRig Operative ("Vex").

Builds source/Operative.blend from scratch using:
  - character_mesh_builder.py (LOD0, LOD1, LOD2 meshes, UVs, 6 PBR materials, 38 Shape Keys)
  - rig_and_skin_builder.py (93-bone deformation skeleton + animator CTRL/MCH rig + skin weights)
  - animation_suite_builder.py (all 96 required animations/poses + 7 deformation demo poses)

Also outputs:
  - docs/skeleton_and_sockets.json
  - docs/animation_manifest.json
  - docs/material_and_lod_report.json
"""

import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector

# Ensure generators directory is on sys.path
GEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = GEN_DIR.parent.parent
if str(GEN_DIR) not in sys.path:
    sys.path.insert(0, str(GEN_DIR))

from character_mesh_builder import (
    MATERIAL_NAMES,
    build_operative_lod_mesh,
    create_materials,
)
from rig_and_skin_builder import (
    assign_smooth_skin_weights,
    build_armature_and_controls,
    write_skeleton_and_sockets_manifest,
)
from animation_suite_builder import build_all_animations


def count_mesh_triangles_and_influences(obj: bpy.types.Object) -> dict:
    mesh = obj.data
    mesh.calc_loop_triangles()
    tri_count = len(mesh.loop_triangles)
    vert_count = len(mesh.vertices)
    max_inf = 0
    ungrouped = 0
    for v in mesh.vertices:
        n_g = sum(1 for g in v.groups if g.weight > 1e-4)
        if n_g == 0:
            ungrouped += 1
        if n_g > max_inf:
            max_inf = n_g

    zs = [v.co.z for v in mesh.vertices]
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    return {
        "name": obj.name,
        "vertices": vert_count,
        "triangles": tri_count,
        "polygons": len(mesh.polygons),
        "material_slots": len(mesh.materials),
        "shape_keys": len(mesh.shape_keys.key_blocks) if mesh.shape_keys else 0,
        "max_bone_influences_per_vertex": max_inf,
        "ungrouped_vertices": ungrouped,
        "bounds_min_m": [round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)],
        "bounds_max_m": [round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)],
        "standing_height_m": round(max(zs) - min(zs), 4),
    }


def setup_scene_lighting_and_camera():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps = 30
    scene.frame_start = 0
    scene.frame_end = 90

    # Key, Fill, Rim lights for clean presentation
    light_specs = [
        ("KeyLight", "AREA", (1.8, -2.4, 2.3), (math.radians(55.0), 0.0, math.radians(35.0)), 220.0, (1.0, 0.97, 0.93)),
        ("FillLight", "AREA", (-2.0, -1.8, 1.6), (math.radians(65.0), 0.0, math.radians(-42.0)), 95.0, (0.78, 0.88, 1.0)),
        ("RimLight", "AREA", (0.2, 2.2, 2.2), (math.radians(-55.0), 0.0, math.radians(5.0)), 180.0, (0.4, 0.92, 1.0)),
    ]
    for lname, ltype, loc, rot, energy, col in light_specs:
        ldata = bpy.data.lights.new(name=lname, type=ltype)
        ldata.energy = energy
        ldata.color = col
        if hasattr(ldata, "size"):
            ldata.size = 1.8
        lobj = bpy.data.objects.new(lname, ldata)
        lobj.location = loc
        lobj.rotation_euler = rot
        scene.collection.objects.link(lobj)

    cam_data = bpy.data.cameras.new("InspectionCamera")
    cam_data.lens = 50.0
    cam_obj = bpy.data.objects.new("InspectionCamera", cam_data)
    cam_obj.location = (0.0, -3.15, 1.05)
    cam_obj.rotation_euler = (math.radians(88.0), 0.0, 0.0)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Dark studio world background
    if not scene.world:
        scene.world = bpy.data.worlds.new("MorphRigWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.035, 0.042, 0.055, 1.0)
        bg.inputs["Strength"].default_value = 0.85


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_scene_lighting_and_camera()

    tex_dir = REPO_ROOT / "source" / "textures"
    materials = create_materials(tex_dir)

    print("Building Operative Rig & Control Hierarchy...")
    arm_obj = build_armature_and_controls()

    print("Building Operative_LOD0, Operative_LOD1, Operative_LOD2 meshes...")
    lod0_obj, lod0_tags = build_operative_lod_mesh(
        "Operative_LOD0", radial_seg=64, height_sub=5, materials=materials, with_shape_keys=True
    )
    lod1_obj, lod1_tags = build_operative_lod_mesh(
        "Operative_LOD1", radial_seg=40, height_sub=3, materials=materials, with_shape_keys=True
    )
    lod2_obj, lod2_tags = build_operative_lod_mesh(
        "Operative_LOD2", radial_seg=24, height_sub=1, materials=materials, with_shape_keys=True
    )

    print("Assigning smooth normalized skin weights across all 3 LODs...")
    assign_smooth_skin_weights(lod0_obj, arm_obj, lod0_tags)
    assign_smooth_skin_weights(lod1_obj, arm_obj, lod1_tags)
    assign_smooth_skin_weights(lod2_obj, arm_obj, lod2_tags)

    # Parent LOD meshes under OperativeRig for clean outliner organization
    for m_obj in (lod0_obj, lod1_obj, lod2_obj):
        m_obj.parent = arm_obj

    # Put LOD1 and LOD2 in a dedicated LOD_Variants sub-collection (hidden in viewport by default so LOD0 shows cleanly)
    lod_coll = bpy.data.collections.new("LOD_Variants")
    bpy.context.scene.collection.children.link(lod_coll)
    for m_obj in (lod1_obj, lod2_obj):
        bpy.context.scene.collection.objects.unlink(m_obj)
        lod_coll.objects.link(m_obj)
        m_obj.hide_render = True
        m_obj.hide_viewport = True

    skel_path = REPO_ROOT / "docs" / "skeleton_and_sockets.json"
    n_def_bones = write_skeleton_and_sockets_manifest(skel_path)

    print("Generating all 96 required animations/poses + 7 deformation demo poses...")
    csv_path = REPO_ROOT / "required_animations.csv"
    dialogue_align_path = REPO_ROOT / "source" / "audio" / "dialogue_alignment.json"
    anim_manifest_path = REPO_ROOT / "docs" / "animation_manifest.json"
    build_all_animations(arm_obj, lod0_obj, csv_path, dialogue_align_path, anim_manifest_path)

    lod0_stats = count_mesh_triangles_and_influences(lod0_obj)
    lod1_stats = count_mesh_triangles_and_influences(lod1_obj)
    lod2_stats = count_mesh_triangles_and_influences(lod2_obj)

    print(f"LOD0 stats: {lod0_stats['triangles']} tris (limit <= 80000), height = {lod0_stats['standing_height_m']} m")
    print(f"LOD1 stats: {lod1_stats['triangles']} tris (limit <= 40000), height = {lod1_stats['standing_height_m']} m")
    print(f"LOD2 stats: {lod2_stats['triangles']} tris (limit <= 20000), height = {lod2_stats['standing_height_m']} m")

    assert lod0_stats["triangles"] <= 80000, f"LOD0 exceeded 80k: {lod0_stats['triangles']}"
    assert lod1_stats["triangles"] <= 40000, f"LOD1 exceeded 40k: {lod1_stats['triangles']}"
    assert lod2_stats["triangles"] <= 20000, f"LOD2 exceeded 20k: {lod2_stats['triangles']}"
    assert lod0_stats["triangles"] > lod1_stats["triangles"] > lod2_stats["triangles"], "LODs must decrease in triangle count"
    assert lod0_stats["max_bone_influences_per_vertex"] <= 8
    assert lod0_stats["ungrouped_vertices"] == 0

    # Compute texture memory report
    tex_files = sorted(tex_dir.glob("*.png"))
    total_disk_bytes = sum(p.stat().st_size for p in tex_files)
    # 7 texture sets * 6 maps * 1024x1024:
    # In GPU VRAM (BC1/BC3/BC5/BC7 compressed with mipmaps ~ 1.33 MB per 1024x1024 map; uncompressed RGBA8 ~ 4 MB per map)
    num_maps = len(tex_files)
    uncompressed_mib = round(num_maps * (1024 * 1024 * 4) / (1024.0 * 1024.0), 2)
    bc_compressed_mib = round(num_maps * (1024 * 1024 * 1.0 * 1.333) / (1024.0 * 1024.0), 2)

    mat_lod_report = {
        "character_name": "Operative (Vex)",
        "standing_height_m": lod0_stats["standing_height_m"],
        "standing_height_cm_unreal": round(lod0_stats["standing_height_m"] * 100.0, 2),
        "deformation_bone_count": n_def_bones,
        "max_effective_bone_influences_per_vertex": lod0_stats["max_bone_influences_per_vertex"],
        "spec_max_bone_influences_limit": 8,
        "material_slots_count": len(MATERIAL_NAMES),
        "spec_max_material_slots_limit": 8,
        "material_slots": [
            {
                "slot_index": i,
                "material_name": mname,
                "pbr_maps": ["BaseColor (_D)", "Roughness (_R)", "Metallic (_M)", "Packed ORM (_ORM)", "Normal (_N)", "Emissive (_E)"],
                "max_dimension_px": 1024,
            }
            for i, mname in enumerate(MATERIAL_NAMES)
        ],
        "team_accent_variants": {
            "Team_A": {
                "material_instance": "MI_Operative_Props_Accent_TeamA",
                "primary_color": "Electric Cyan (#00E5FF)",
                "secondary_icon_and_outline": "Hexagonal Triple-Chevron shoulder crest badge + continuous double-ring border",
            },
            "Team_B": {
                "material_instance": "MI_Operative_Props_Accent_TeamB",
                "primary_color": "Solar Amber/Crimson (#FF5810)",
                "secondary_icon_and_outline": "Crossed-Diamond Strike shoulder crest badge + segmented notch border",
            },
        },
        "lods": {
            "LOD0": {**lod0_stats, "spec_triangle_limit": 80000},
            "LOD1": {**lod1_stats, "spec_triangle_limit": 40000},
            "LOD2": {**lod2_stats, "spec_triangle_limit": 20000},
        },
        "texture_memory_estimate": {
            "texture_file_count": num_maps,
            "max_resolution": "1024x1024 (limit <= 4096x4096)",
            "total_png_disk_size_mib": round(total_disk_bytes / (1024.0 * 1024.0), 2),
            "estimated_uncompressed_rgba8_mib": uncompressed_mib,
            "estimated_gpu_bc_compressed_with_mips_mib": bc_compressed_mib,
        },
    }

    report_path = REPO_ROOT / "docs" / "material_and_lod_report.json"
    report_path.write_text(json.dumps(mat_lod_report, indent=2), encoding="utf-8")

    blend_path = REPO_ROOT / "source" / "Operative.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), relative_remap=True)
    try:
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_mainfile()
    except Exception:
        pass
    print(f"Saved authoritative Blender production file: {blend_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MORPHRIG Authoritative Build, DEF Action Baker & FBX Export Pipeline (Blender 5.1+).

Usage:
  1) Full clean build from procedural source generators:
       blender -b --factory-startup --python tools/export_and_bake.py

  2) Rebake & re-export after editing CTRL_<id> or SK_CTRL_<id> in source/Operative.blend:
       blender -b source/Operative.blend --python tools/export_and_bake.py -- --rebake
       blender -b source/Operative.blend --python tools/export_and_bake.py -- --rebake --clip melee_1

Outputs:
  - source/Operative.blend (editable control rig, 3 LODs, 6 PBR materials, 46 shape keys, 96 CTRL + 96 baked actions)
  - export/Operative.fbx, export/Operative_LOD1.fbx, export/Operative_LOD2.fbx
  - export/animations/<id>.fbx (all 96 clips/poses at 30 FPS) + export/animations/morph_curves.json
  - export/textures/*.png
  - docs/skeleton_and_sockets.json
  - docs/animation_manifest.json
  - docs/material_and_lod_report.json
"""

import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path
import bpy

ROOT_DIR = Path(__file__).resolve().parents[1]
GEN_DIR = ROOT_DIR / "source" / "generators"
sys.path.insert(0, str(GEN_DIR))

from build_character_mesh import build_operative_meshes, generate_lods, MATERIAL_NAMES
from build_rig_and_skin import (
    build_armature,
    assign_skin_weights,
    build_facial_and_corrective_shapekeys,
    export_skeleton_and_sockets_doc,
)
from motion_library import MotionLibrary, FPS
from build_animations import (
    author_ctrl_actions,
    bake_ctrl_to_def_actions,
    reset_rig_pose,
    set_def_constraints_muted,
)


def parse_cli_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="MorphRig Blender Build, Bake & FBX Exporter")
    parser.add_argument("--rebake", action="store_true", help="Rebake existing CTRL_<id> actions in loaded Operative.blend without regenerating meshes")
    parser.add_argument("--clip", type=str, default=None, help="Optional single clip ID to rebake/re-export")
    return parser.parse_args(argv)


def select_only(objs: list[bpy.types.Object], active: bpy.types.Object) -> None:
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.data.objects:
        o.select_set(False)
    for o in objs:
        o.hide_viewport = False
        o.hide_render = False
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def sync_export_textures() -> list[str]:
    src_tex = ROOT_DIR / "source" / "textures"
    dst_tex = ROOT_DIR / "export" / "textures"
    dst_tex.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in sorted(src_tex.glob("*.png")):
        shutil.copy2(p, dst_tex / p.name)
        copied.append(p.name)
    return copied


def export_skeletal_meshes(arm_obj: bpy.types.Object, lod0: bpy.types.Object, lod1: bpy.types.Object, lod2: bpy.types.Object) -> None:
    export_dir = ROOT_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    # Neutral rest bind pose for mesh export
    arm_obj.animation_data.action = None
    if lod0.data.shape_keys and lod0.data.shape_keys.animation_data:
        lod0.data.shape_keys.animation_data.action = None
    reset_rig_pose(arm_obj, lod0)
    set_def_constraints_muted(arm_obj, True)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()

    targets = [
        (lod0, export_dir / "Operative.fbx"),
        (lod1, export_dir / "Operative_LOD1.fbx"),
        (lod2, export_dir / "Operative_LOD2.fbx"),
    ]
    for m_obj, fpath in targets:
        select_only([arm_obj, m_obj], arm_obj)
        bpy.ops.export_scene.fbx(
            filepath=str(fpath),
            use_selection=True,
            object_types={"ARMATURE", "MESH"},
            use_mesh_modifiers=False,  # Preserves all 46 Shape Keys on Operative.fbx!
            mesh_smooth_type="FACE",
            use_armature_deform_only=True,
            add_leaf_bones=False,
            bake_anim=False,
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE",
            axis_forward="-Y",
            axis_up="Z",
            path_mode="RELATIVE",
        )
        print(f"[Exporter] Wrote {fpath.relative_to(ROOT_DIR)}")

    # Hide LOD1 & LOD2 in viewport and Cycles render so Operative_LOD0 is cleanly displayed when opening Operative.blend
    lod1.hide_set(True)
    lod1.hide_render = True
    lod2.hide_set(True)
    lod2.hide_render = True


def export_animation_fbxs(arm_obj: bpy.types.Object, ml: MotionLibrary, target_clips: list[str] | None = None) -> None:
    anim_dir = ROOT_DIR / "export" / "animations"
    anim_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0

    # Mute live DEF constraints so Armature plays the exact baked DEF action <id>
    set_def_constraints_muted(arm_obj, True)
    select_only([arm_obj], arm_obj)

    clips = [c for c in ml.catalog if (target_clips is None or c.clip_id in target_clips)]
    for clip in clips:
        cid = clip.clip_id
        baked_act = bpy.data.actions.get(cid)
        assert baked_act is not None, f"Missing baked action {cid}"
        n_frames = max(1, clip.frames)

        arm_obj.animation_data.action = baked_act
        scene.frame_start = 0
        scene.frame_end = n_frames
        scene.frame_set(0)
        bpy.context.view_layer.update()

        out_fbx = anim_dir / f"{cid}.fbx"
        bpy.ops.export_scene.fbx(
            filepath=str(out_fbx),
            use_selection=True,
            object_types={"ARMATURE"},
            use_armature_deform_only=True,
            add_leaf_bones=False,
            use_custom_props=True,
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE",
            axis_forward="-Y",
            axis_up="Z",
        )
    print(f"[Exporter] Exported {len(clips)} animation FBX files to export/animations/")


def write_manifests_and_reports(
    lod0: bpy.types.Object,
    lod1: bpy.types.Object,
    lod2: bpy.types.Object,
    ml: MotionLibrary,
    telemetry: dict[str, dict],
    tex_files: list[str],
) -> None:
    docs_dir = ROOT_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Load CSV descriptions so animation_manifest.json includes full spec verification metadata
    csv_rows = {}
    with (ROOT_DIR / "required_animations.csv").open("r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            csv_rows[r["id"]] = r

    manifest_path = docs_dir / "animation_manifest.json"
    existing_by_id = {}
    if manifest_path.exists():
        try:
            old_m = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing_by_id = {e["id"]: e for e in old_m.get("animations", [])}
        except Exception:
            pass

    morph_curves_bundle = {}
    curves_path = ROOT_DIR / "export" / "animations" / "morph_curves.json"
    if curves_path.exists():
        try:
            morph_curves_bundle = json.loads(curves_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    anim_entries = []
    for clip in ml.catalog:
        cid = clip.clip_id
        n_frames = max(1, clip.frames)
        tel = telemetry.get(cid)
        if tel is None and cid in existing_by_id:
            anim_entries.append(existing_by_id[cid])
            continue
        tel = tel or {"root_displacement_m": [0.0, 0.0, 0.0], "root_displacement_length_m": 0.0, "active_morph_curves": {}, "markers": []}
        morph_curves_bundle[cid] = {
            "fps": FPS,
            "frames": n_frames,
            "curves": tel["active_morph_curves"],
            "markers": tel["markers"],
        }
        entry = {
            "id": cid,
            "form": clip.form,
            "is_loop": clip.form == "loop",
            "is_additive": clip.form == "additive",
            "is_static_pose": clip.form == "pose",
            "root_movement_policy": clip.root_movement,
            "source_editable_action": f"CTRL_{cid}",
            "source_editable_shapekey_action": f"SK_CTRL_{cid}",
            "source_baked_action": cid,
            "source_baked_shapekey_action": f"SK_{cid}",
            "exported_fbx": f"export/animations/{cid}.fbx",
            "exported_take": f"Armature|{cid}",
            "unreal_asset_path": f"/Game/MorphRig/Animations/Anim_{cid}",
            "sample_rate_fps": FPS,
            "frame_range": [0, n_frames],
            "authored_duration_seconds": 0.0 if clip.form == "pose" else round(clip.frames / float(FPS), 4),
            "exported_duration_seconds": round(n_frames / float(FPS), 4),
            "spec_duration_window": csv_rows[cid]["duration_seconds"],
            "nominal_speed_cms": clip.nominal_speed_cms,
            "intended_layer": clip.intended_layer,
            "additive_base_reference": "idle_combat (frame 0)" if clip.form == "additive" else None,
            "entry_state": clip.entry_state,
            "exit_state": clip.exit_state,
            "root_displacement_m": tel["root_displacement_m"],
            "event_markers": tel["markers"],
            "active_morph_curve_names": sorted(tel["active_morph_curves"].keys()),
            "required_behavior": csv_rows[cid]["required_behavior"],
        }
        anim_entries.append(entry)

    curves_path.write_text(json.dumps(morph_curves_bundle, indent=2) + "\n", encoding="utf-8")

    manifest_doc = {
        "project": "MorphRig",
        "asset": "Operative",
        "sample_rate_fps": FPS,
        "total_required_entries": len(anim_entries),
        "counts_by_form": {
            "loop": sum(1 for e in anim_entries if e["form"] == "loop"),
            "one_shot": sum(1 for e in anim_entries if e["form"] == "one_shot"),
            "additive": sum(1 for e in anim_entries if e["form"] == "additive"),
            "pose": sum(1 for e in anim_entries if e["form"] == "pose"),
        },
        "aim_grid_convention": {
            "yaw_degrees": [-60.0, 0.0, 60.0],
            "yaw_sign": "-60 = Left, 0 = Center, +60 = Right",
            "pitch_degrees": [-35.0, 0.0, 35.0],
            "pitch_sign": "-35 = Down, 0 = Level, +35 = Up",
        },
        "procedural_runtime_components": [
            "Analytical 2-bone Foot & Pelvis Ground-Adaptation IK (up to 20 deg slope / 20 cm step)",
            "Head & Stereo Eye Look-At Damped Tracking",
            "Damped Spring Secondary Settle Overlay (cable_01..03, strap_01..03)",
            "Pose-Snapshot Interrupt Crossfade on Channel, Charge, Uplink & Death",
        ],
        "animations": anim_entries,
    }
    manifest_path.write_text(json.dumps(manifest_doc, indent=2) + "\n", encoding="utf-8")
    print(f"[Exporter] Wrote {manifest_path.relative_to(ROOT_DIR)} ({len(anim_entries)} entries)")

    # Write docs/material_and_lod_report.json
    def mesh_stats(obj: bpy.types.Object, limit_tris: int, screen_size: float, fbx_rel: str):
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        sk_count = (len(obj.data.shape_keys.key_blocks) - 1) if obj.data.shape_keys else 0
        # Verify max bone influences per vertex <= 8
        max_inf = max((len(v.groups) for v in obj.data.vertices), default=0)
        zs = [v.co.z for v in obj.data.vertices]
        return {
            "name": obj.name,
            "exported_fbx": fbx_rel,
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons),
            "triangles": tris,
            "triangle_budget_limit": limit_tris,
            "within_budget": tris <= limit_tris,
            "material_slots": len(obj.data.materials),
            "shape_key_count": sk_count,
            "max_bone_influences_per_vertex": max_inf,
            "standing_z_bounds_m": [round(min(zs), 4), round(max(zs), 4)],
            "unreal_lod_screen_size": screen_size,
        }

    tex_disk_bytes = sum((ROOT_DIR / "export" / "textures" / fn).stat().st_size for fn in tex_files if (ROOT_DIR / "export" / "textures" / fn).exists())
    # 2048x2048 mipmapped BC7/BC5/BC1 GPU VRAM: ~5.33 MiB per 2K BC7/BC5 texture; uncompressed RGBA8 w/ mips: ~21.33 MiB per 2K texture
    n_tex = len(tex_files)
    def_bone_count = sum(1 for b in bpy.data.objects["Armature"].data.bones if b.use_deform)

    mat_report = {
        "asset": "Operative",
        "standing_height_m": 1.80,
        "standing_height_unreal_cm": 180.0,
        "deformation_bone_count": def_bone_count,
        "material_slot_budget_limit": 8,
        "material_slot_count": len(MATERIAL_NAMES),
        "texture_resolution_max": "2048x2048",
        "texture_count_total": n_tex,
        "texture_memory_estimate": {
            "png_disk_total_mib": round(tex_disk_bytes / (1024.0 * 1024.0), 2),
            "active_single_team_textures": 20,
            "gpu_vram_bc7_bc5_mipmapped_single_team_mib": round(20 * (2048 * 2048 * 1.3333) / (1024.0 * 1024.0), 2),
            "gpu_vram_bc7_bc5_mipmapped_all_25_maps_mib": round(n_tex * (2048 * 2048 * 1.3333) / (1024.0 * 1024.0), 2),
            "uncompressed_rgba8_mipmapped_single_team_mib": round(20 * (2048 * 2048 * 4 * 1.3333) / (1024.0 * 1024.0), 2),
        },
        "team_accent_variants": {
            "Team_A_Vanguard_Cyan": {
                "primary_accent_srgb": "#00D8FF",
                "secondary_cue": "Single Diamond Crest on Left Pauldron & Dorsal Mantle + Optional Floating Diamond Beacon / Fresnel Outline",
                "armor_basecolor": "CyberArmor_BaseColor.png",
                "armor_emissive": "CyberArmor_Emissive.png",
                "props_basecolor": "PropsTech_BaseColor.png",
                "props_emissive": "PropsTech_Emissive.png",
            },
            "Team_B_Helix_CrimsonAmber": {
                "primary_accent_srgb": "#FF4A1C",
                "secondary_cue": "Double-Chevron Crest on Left Pauldron & Dorsal Mantle + Optional Floating Chevron Beacon / Fresnel Outline",
                "armor_basecolor": "CyberArmor_TeamB_BaseColor.png",
                "armor_emissive": "CyberArmor_TeamB_Emissive.png",
                "props_basecolor": "PropsTech_TeamB_BaseColor.png",
                "props_emissive": "PropsTech_TeamB_Emissive.png",
            },
        },
        "materials": [
            {"slot": 0, "name": "M_Skin_FaceBody", "maps": ["Skin_BaseColor.png", "Skin_Normal.png", "Skin_ORM.png"], "unreal_path": "/Game/MorphRig/Materials/M_Skin_FaceBody"},
            {"slot": 1, "name": "M_Eyes_Mouth",    "maps": ["EyesMouth_BaseColor.png", "EyesMouth_Normal.png", "EyesMouth_ORM.png"], "unreal_path": "/Game/MorphRig/Materials/M_Eyes_Mouth"},
            {"slot": 2, "name": "M_Hair",          "maps": ["Hair_BaseColor.png", "Hair_Normal.png", "Hair_ORM.png"], "unreal_path": "/Game/MorphRig/Materials/M_Hair"},
            {"slot": 3, "name": "M_Suit_Fabric",   "maps": ["SuitFabric_BaseColor.png", "SuitFabric_Normal.png", "SuitFabric_ORM.png"], "unreal_path": "/Game/MorphRig/Materials/M_Suit_Fabric"},
            {"slot": 4, "name": "M_CyberArmor",    "maps": ["CyberArmor_BaseColor.png", "CyberArmor_Normal.png", "CyberArmor_ORM.png", "CyberArmor_Emissive.png", "CyberArmor_TeamMask.png"], "unreal_path": "/Game/MorphRig/Materials/M_CyberArmor"},
            {"slot": 5, "name": "M_Props_Tech",    "maps": ["PropsTech_BaseColor.png", "PropsTech_Normal.png", "PropsTech_ORM.png", "PropsTech_Emissive.png"], "unreal_path": "/Game/MorphRig/Materials/M_Props_Tech"},
        ],
        "textures_exported": tex_files,
        "lods": [
            mesh_stats(lod0, 80000, 1.0,  "export/Operative.fbx"),
            mesh_stats(lod1, 40000, 0.45, "export/Operative_LOD1.fbx"),
            mesh_stats(lod2, 20000, 0.20, "export/Operative_LOD2.fbx"),
        ],
        "facial_shape_keys": [kb.name for kb in lod0.data.shape_keys.key_blocks if kb.name != "Basis"] if lod0.data.shape_keys else [],
    }
    mat_report_path = docs_dir / "material_and_lod_report.json"
    mat_report_path.write_text(json.dumps(mat_report, indent=2) + "\n", encoding="utf-8")
    print(f"[Exporter] Wrote {mat_report_path.relative_to(ROOT_DIR)}")


def main() -> None:
    t0 = time.time()
    args = parse_cli_args()
    blend_path = ROOT_DIR / "source" / "Operative.blend"
    ml = MotionLibrary()

    if args.rebake:
        if bpy.data.filepath != str(blend_path) and blend_path.exists():
            bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        arm_obj = bpy.data.objects["Armature"]
        lod0 = bpy.data.objects["Operative_LOD0"]
        lod1 = bpy.data.objects["Operative_LOD1"]
        lod2 = bpy.data.objects["Operative_LOD2"]
        target_clips = [args.clip] if args.clip else None
        telemetry = bake_ctrl_to_def_actions(arm_obj, lod0, ml, target_clips=target_clips)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        scene.render.fps = FPS
        scene.render.fps_base = 1.0

        lod0, part_names = build_operative_meshes()
        arm_obj = build_armature()
        assign_skin_weights(lod0, arm_obj, part_names)
        lod1, lod2 = generate_lods(lod0)
        build_facial_and_corrective_shapekeys(lod0, arm_obj, part_names)
        export_skeleton_and_sockets_doc(arm_obj, ROOT_DIR / "docs" / "skeleton_and_sockets.json")

        author_ctrl_actions(arm_obj, lod0, ml)
        telemetry = bake_ctrl_to_def_actions(arm_obj, lod0, ml)
        target_clips = None

    tex_files = sync_export_textures()

    # Save initial Operative.blend so relative paths (//textures/*.png) resolve cleanly against source/
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    bpy.ops.file.make_paths_relative()

    if not args.clip:
        export_skeletal_meshes(arm_obj, lod0, lod1, lod2)
    export_animation_fbxs(arm_obj, ml, target_clips=target_clips)
    write_manifests_and_reports(lod0, lod1, lod2, ml, telemetry, tex_files)

    # Restore live editable CTRL rig state and save clean authoritative source/Operative.blend!
    arm_obj.animation_data.action = None
    if lod0.data.shape_keys and lod0.data.shape_keys.animation_data:
        lod0.data.shape_keys.animation_data.action = None
    set_def_constraints_muted(arm_obj, False)
    reset_rig_pose(arm_obj, lod0)
    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = 120
    bpy.context.scene.frame_set(0)
    select_only([arm_obj], arm_obj)
    lod1.hide_set(True)
    lod1.hide_render = True
    lod2.hide_set(True)
    lod2.hide_render = True
    bpy.context.view_layer.update()
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True, check_existing=False)

    dt = time.time() - t0
    print(f"[MorphRig] Pipeline completed cleanly in {dt:.2f}s -> {blend_path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()

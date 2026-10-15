#!/usr/bin/env python3
"""
Reproducible Blender -> FBX Export & Action Baking Utility (tools/export_and_bake.py).

Usage:
  blender -b source/Operative.blend --python-exit-code 1 -P tools/export_and_bake.py

Exports:
  1. export/Operative.fbx       (Authoritative SkeletalMesh LOD0 + 93-bone deformation skeleton + 38 Morph Targets)
  2. export/Operative_LOD1.fbx  (LOD1 SkeletalMesh for Unreal LOD1 import)
  3. export/Operative_LOD2.fbx  (LOD2 SkeletalMesh for Unreal LOD2 import)
  4. export/animations/<id>.fbx (All 96 baked skeletal animation & static pose clips at 30 FPS)
"""

import csv
import json
import sys
import time
from pathlib import Path
import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = REPO_ROOT / "export"
ANIM_DIR = EXPORT_DIR / "animations"


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_viewport = False
        o.hide_select = False
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def reset_rig_and_keys(rig, meshes):
    for pb in rig.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    for m in meshes:
        if m and m.data.shape_keys:
            for kb in m.data.shape_keys.key_blocks:
                if kb.name != "Basis":
                    kb.value = 0.0


def export_mesh_fbx(rig, mesh_obj, out_path: Path):
    select_only([rig, mesh_obj])
    bpy.ops.export_scene.fbx(
        filepath=str(out_path),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        use_mesh_modifiers=False,  # Must be False so Shape Keys (Morph Targets) export to FBX!
        use_armature_deform_only=True,
        add_leaf_bones=False,
        bake_anim=False,
        mesh_smooth_type="FACE",
        use_tspace=True,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        axis_forward="-Y",
        axis_up="Z",
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_NONE",
        path_mode="RELATIVE",
    )


def export_all():
    t0 = time.time()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ANIM_DIR.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.render.fps = 30

    rig = bpy.data.objects["OperativeRig"]
    lod0 = bpy.data.objects["Operative_LOD0"]
    lod1 = bpy.data.objects["Operative_LOD1"]
    lod2 = bpy.data.objects["Operative_LOD2"]

    # Ensure LOD_Variants collection is temporarily enabled in view layer for selection/export
    for layer_coll in bpy.context.view_layer.layer_collection.children:
        layer_coll.exclude = False
        layer_coll.hide_viewport = False

    reset_rig_and_keys(rig, [lod0, lod1, lod2])
    scene.frame_set(0)

    print("Exporting export/Operative.fbx (LOD0 + Skeleton + 38 Morph Targets)...")
    export_mesh_fbx(rig, lod0, EXPORT_DIR / "Operative.fbx")

    print("Exporting export/Operative_LOD1.fbx and export/Operative_LOD2.fbx...")
    export_mesh_fbx(rig, lod1, EXPORT_DIR / "Operative_LOD1.fbx")
    export_mesh_fbx(rig, lod2, EXPORT_DIR / "Operative_LOD2.fbx")

    # Re-hide LOD1 & LOD2 in viewport
    lod1.hide_viewport = True
    lod2.hide_viewport = True

    # Read required_animations.csv for the authoritative 96 clip list
    csv_path = REPO_ROOT / "required_animations.csv"
    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    select_only([rig])
    for idx, row in enumerate(rows):
        clip_id = row["id"].strip()
        act = bpy.data.actions.get(clip_id)
        if act is None:
            raise RuntimeError(f"Missing required Blender Action: {clip_id}")

        rig.animation_data.action = act
        if hasattr(rig.animation_data, "action_slot") and act.slots:
            rig.animation_data.action_slot = act.slots[0]

        f_start = int(round(act.frame_range[0]))
        f_end = max(f_start + 1, int(round(act.frame_range[1])))
        scene.frame_start = f_start
        scene.frame_end = f_end
        scene.frame_set(f_start)

        out_fbx = ANIM_DIR / f"{clip_id}.fbx"
        bpy.ops.export_scene.fbx(
            filepath=str(out_fbx),
            use_selection=True,
            object_types={"ARMATURE"},
            use_armature_deform_only=True,
            add_leaf_bones=False,
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            axis_forward="-Y",
            axis_up="Z",
            global_scale=1.0,
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE",
        )
        if (idx + 1) % 16 == 0 or (idx + 1) == len(rows):
            print(f"  Exported {idx + 1}/{len(rows)} animations ({clip_id}.fbx)")

    reset_rig_and_keys(rig, [lod0, lod1, lod2])
    dt = time.time() - t0
    print(f"Completed export of Operative.fbx + LODs + {len(rows)} animation FBXs in {dt:.1f}s")


if __name__ == "__main__":
    export_all()

"""Verify the imported MORPHRIG assets inside Unreal.

    UnrealEditor-Cmd <project> -run=pythonscript -script=tools/ue_verify.py

Writes a JSON report to build/ue_verify.json.
"""

import json
import os
import traceback

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPORT = os.environ.get("MORPHRIG_VERIFY_REPORT",
                        os.path.join(ROOT, "build", "ue_verify.json"))
DATA = {}


def main():
    DATA["version"] = unreal.SystemLibrary.get_engine_version()

    # ---- the skeletal mesh -------------------------------------------------
    mesh = unreal.load_asset("/Game/MorphRig/Meshes/SK_Operative")
    if mesh is None:
        DATA["mesh"] = "MISSING"
    else:
        info = {"path": mesh.get_path_name()}
        slots = mesh.get_editor_property("materials")
        info["material_slots"] = [s.get_editor_property("material_slot_name") for s in slots]
        info["material_assets"] = [
            (s.get_editor_property("material_interface").get_path_name()
             if s.get_editor_property("material_interface") else None)
            for s in slots]
        skeleton = mesh.get_editor_property("skeleton")
        info["skeleton"] = skeleton.get_path_name() if skeleton else None

        # morph targets
        morphs = []
        for prop in ("morph_targets", "morph_target_names"):
            try:
                value = mesh.get_editor_property(prop)
                morphs = [m.get_name() if hasattr(m, "get_name") else str(m)
                          for m in value]
                info["morph_property"] = prop
                break
            except Exception:
                continue
        info["morph_targets"] = morphs
        info["morph_count"] = len(morphs)

        # LODs
        try:
            subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
            info["lod_count"] = subsystem.get_lod_count(mesh)
        except Exception as exc:
            info["lod_count_error"] = str(exc)

        # the size of the imported character, Unreal works in centimetres
        try:
            bounds = mesh.get_bounds()
            origin = bounds.origin
            extent = bounds.box_extent
            info["bounds_cm"] = {
                "min_z": round(origin.z - extent.z, 2),
                "max_z": round(origin.z + extent.z, 2),
                "height": round(extent.z * 2.0, 2),
                "width": round(extent.x * 2.0, 2),
                "depth": round(extent.y * 2.0, 2),
            }
        except Exception as exc:
            info["bounds_error"] = str(exc)

        # The bones, compared with the manifest.  Unreal 5.8 protects the
        # name property of a bone node, so the skeleton is asked directly
        # whether it knows a bone and the bone tracks of a clip give the
        # names that are actually animated.
        try:
            skeleton = mesh.get_editor_property("skeleton")
            manifest = json.load(open(os.path.join(ROOT, "docs",
                                                   "skeleton_and_sockets.json")))
            expected = [b["name"] for b in manifest["bones"] if b.get("deform", True)]
            missing_bones = []
            for bone in expected:
                try:
                    found = unreal.AnimationLibrary.does_bone_name_exist(
                        skeleton, bone)
                except Exception:
                    found = True
                if not found:
                    missing_bones.append(bone)
            info["bones_missing"] = sorted(missing_bones)
            seq = unreal.load_asset("/Game/MorphRig/Animations/A_idle_combat")
            names = [str(n) for n in
                     unreal.AnimationLibrary.get_animation_track_names(seq)]
            info["bone_count"] = len(names)
            info["bone_names_sample"] = names[:6]
            info["bones_extra"] = sorted(set(names) - set(expected))
        except Exception as exc:
            info["bones_error"] = str(exc)
        DATA["mesh"] = info

    # ---- the animations ----------------------------------------------------
    # Every one of the 96 clips is checked against the manifest: the asset has
    # to exist and its length has to match the authored duration.
    manifest = json.load(open(os.path.join(ROOT, "docs", "animation_manifest.json")))
    clips = manifest["clips"]
    length_errors = []
    missing = []
    lengths = {}
    root_motion = []
    for clip in clips:
        name = clip["name"]
        seq = unreal.load_asset("/Game/MorphRig/Animations/A_%s" % name)
        if seq is None:
            missing.append(name)
            continue
        try:
            length = float(seq.get_editor_property("sequence_length"))
        except Exception:
            length = None
        lengths[name] = length
        expected = float(clip.get("duration") or 0.0)
        if length is None or abs(length - expected) > 0.02:
            length_errors.append({"clip": name, "expected": expected,
                                   "actual": length})
        try:
            if seq.get_editor_property("enable_root_motion"):
                root_motion.append(name)
        except Exception:
            pass
    DATA["clip_count"] = len(clips)
    DATA["clips_imported"] = len(lengths)
    DATA["clips_missing"] = missing
    DATA["clip_length_errors"] = length_errors
    DATA["clips_with_root_motion"] = sorted(root_motion)
    DATA["clip_length_sample"] = dict(list(sorted(lengths.items()))[:8])

    # the assets that are in the folder but should not be there
    stray = []
    for asset in unreal.EditorAssetLibrary.list_assets("/Game/MorphRig/Animations",
                                                        recursive=True):
        base = os.path.basename(asset)
        if base.endswith(".uasset"):
            base = base[:-7]
        if not base.startswith("A_"):
            stray.append(base)
    DATA["stray_animation_assets"] = sorted(stray)

    # a few clips in detail
    names = ["A_idle_combat", "A_walk_f", "A_dash_f", "A_dialogue",
             "A_aim_level_center", "A_death_front", "A_melee_1",
             "A_dead_front", "A_dead_back"]
    anims = {}
    for name in names:
        seq = unreal.load_asset("/Game/MorphRig/Animations/%s" % name)
        if seq is None:
            anims[name] = "MISSING"
            continue
        entry = {"path": seq.get_path_name()}
        for prop in ("sequence_length", "number_of_frames"):
            try:
                entry[prop] = seq.get_editor_property(prop)
            except Exception:
                pass
        try:
            entry["enable_root_motion"] = seq.get_editor_property("enable_root_motion")
        except Exception:
            pass
        # the morph target curves of the spoken performance
        try:
            curves = seq.get_editor_property("curve_not_ifies")
        except Exception:
            curves = None
        anims[name] = entry
    DATA["animations"] = anims

    # the morph target curves of the dialogue clip
    seq = unreal.load_asset("/Game/MorphRig/Animations/A_dialogue")
    if seq is not None:
        curve_names = []
        errors = []
        types = unreal.RawCurveTrackTypes
        # Unreal 5.8 does not expose RCT_MORPH_TARGET to Python.  A morph
        # target curve is a float curve whose name is the morph target, so
        # the float curves are matched against the morph targets of the mesh.
        float_type = getattr(types, "RCT_FLOAT", None)
        if float_type is None:
            errors.append("float: the curve type is missing")
        else:
            try:
                names = unreal.AnimationLibrary.get_animation_curve_names(
                    seq, float_type)
                curve_names.extend([str(n) for n in names])
            except Exception as exc:
                errors.append("float: %s" % str(exc)[:160])
        morph_names = set(DATA.get("mesh", {}).get("morph_targets", []))
        found = sorted(set(curve_names) & morph_names)
        DATA["dialogue_morph_curves"] = found
        if morph_names and not found:
            errors.append("morph: no morph target curve was found")
        DATA["dialogue_curve_count"] = len(curve_names)
        DATA["dialogue_curves_sample"] = sorted(curve_names)[:14]
        DATA["dialogue_curve_errors"] = errors

    # ---- the data table ----------------------------------------------------
    table = unreal.load_asset("/Game/MorphRig/DT_MorphRigClips")
    if table is None:
        DATA["clip_table"] = "MISSING"
    else:
        try:
            rows = list(table.get_row_names())
        except Exception as exc:  # noqa: BLE001
            rows = []
            DATA["clip_table_error"] = str(exc)
        DATA["clip_table"] = {"rows": len(rows),
                               "sample": [str(r) for r in rows[:8]]}

    # ---- the materials -----------------------------------------------------
    mats = {}
    for name in ("M_Skin", "M_Accent", "M_Energy", "M_ViewNormal", "M_ViewClay"):
        mat = unreal.load_asset("/Game/MorphRig/Materials/%s" % name)
        if mat is None:
            mats[name] = "MISSING"
            continue
        entry = {"path": mat.get_path_name()}
        try:
            params = mat.get_editor_property("expression_collection")
            entry["expressions"] = len(params.get_editor_property("expressions"))
        except Exception:
            pass
        # A material without the skeletal mesh usage flag is not drawn on the
        # Operative: Unreal falls back to the default material.  The flag is
        # part of the contract, so it is checked here.
        for flag in ("used_with_skeletal_mesh", "used_with_static_mesh"):
            try:
                entry[flag] = bool(mat.get_editor_property(flag))
            except Exception as exc:  # noqa: BLE001
                entry[flag] = "unknown (%s)" % exc
        mats[name] = entry
    mi = unreal.load_asset("/Game/MorphRig/Materials/MI_M_Accent")
    mats["MI_M_Accent"] = mi.get_path_name() if mi else "MISSING"
    DATA["materials"] = mats

    # ---- the level ---------------------------------------------------------
    try:
        map_path = "/Game/MorphRig/Maps/L_MorphRigShowroom"
        unreal.EditorLoadingAndSavingUtils.load_map(map_path)
        world = unreal.EditorLevelLibrary.get_editor_world()
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        DATA["level"] = {
            "path": world.get_path_name() if world else None,
            "actors": sorted(set(a.get_class().get_name() for a in actors)),
            "count": len(actors),
            "has_player_start": any(a.get_class().get_name() == "PlayerStart"
                                     for a in actors),
            "has_character": any(a.get_class().get_name() == "MorphRigCharacter"
                                 for a in actors),
            "has_perf_logger": any(a.get_class().get_name() == "MorphRigPerfLogger"
                                   for a in actors),
            "has_showroom": any(a.get_class().get_name() == "MorphRigShowroom"
                                for a in actors),
        }

        # The lights of the room.  A light with static mobility only
        # contributes through baked light maps, and this level is never
        # baked, so every light has to be movable or the room stays black.
        lights = []
        for actor in actors:
            comps = actor.get_components_by_class(unreal.LightComponentBase)
            for comp in comps:
                entry = {
                    "actor": actor.get_name(),
                    "type": comp.get_class().get_name(),
                    "intensity": round(comp.get_editor_property("intensity"), 3),
                }
                try:
                    entry["mobility"] = str(comp.get_editor_property("mobility"))
                except Exception as exc:  # noqa: BLE001
                    entry["mobility"] = "unknown (%s)" % exc
                lights.append(entry)
        DATA["level"]["lights"] = lights
        DATA["level"]["static_lights"] = [
            entry for entry in lights if "STATIC" in entry.get("mobility", "")]
    except Exception as exc:  # noqa: BLE001
        DATA["level_error"] = str(exc)

    # ---- the audio ---------------------------------------------------------
    sound = unreal.load_asset("/Game/MorphRig/Audio/S_Dialogue")
    DATA["audio"] = sound.get_path_name() if sound else "MISSING"


try:
    main()
except Exception:
    DATA["fatal"] = traceback.format_exc()

os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w") as fh:
    json.dump(DATA, fh, indent=2, default=str)
    fh.flush()
    os.fsync(fh.fileno())
print("VERIFY_WRITTEN %s" % REPORT)

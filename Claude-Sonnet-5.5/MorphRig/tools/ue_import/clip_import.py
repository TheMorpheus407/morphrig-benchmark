"""Import the 96 clip FBX files listed in docs/animation_manifest.json as AnimSequences named exactly like the clip ids.

Per clip settings come from the manifest:
  root_motion clips (dash_*): root motion enabled, root lock at the reference pose (the capsule is driven by the extracted motion)
  additive clips (hit_*):     local space additive relative to frame 0 of the clip itself
  events:                     one UOperativeEventNotify per manifest event on the track "Events"
  morph curves:               only the curves listed in the manifest are kept (the exporter writes 44 constant channels for clips
                              without face animation, see docs/known_issues.md)
"""
import os
import math
import unreal
import common as C


def anim_options(skeleton):
    o = unreal.FbxImportUI()
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("import_mesh", False)
    o.set_editor_property("import_as_skeletal", True)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    o.set_editor_property("skeleton", skeleton)
    o.set_editor_property("import_animations", True)
    return o


def _params_string(params):
    return ",".join("%s=%s" % (k, params[k]) for k in sorted(params)) if params else ""


def post_process(entry, anim):
    lib = unreal.AnimationLibrary
    cid = entry["id"]
    stats = {"removed_curves": 0, "events": 0}

    # ---- morph curves: keep only what the manifest lists
    keep = set(entry.get("morph_curves", []))
    names = [str(n) for n in lib.get_animation_curve_names(anim, unreal.RawCurveTrackTypes.RCT_FLOAT)]
    for n in names:
        if n not in keep:
            lib.remove_curve(anim, n)
            stats["removed_curves"] += 1
    missing = [n for n in keep if n not in names]
    if missing:
        C.warn(cid, "manifest morph curves missing in the FBX:", missing)

    # ---- root motion
    if entry.get("root_motion") == "root_motion":
        lib.set_root_motion_enabled(anim, True)
        lib.set_root_motion_lock_type(anim, unreal.RootMotionRootLock.REF_POSE)
        lib.set_is_root_motion_lock_forced(anim, False)
    else:
        lib.set_root_motion_enabled(anim, False)

    # ---- additive (hit_*): offsets from the first frame of the clip
    if entry.get("additive"):
        lib.set_additive_animation_type(anim, unreal.AdditiveAnimationType.AAT_LOCAL_SPACE_BASE)
        lib.set_additive_base_pose_type(anim, unreal.AdditiveBasePoseType.ABPT_ANIM_FRAME)
        anim.set_editor_property("ref_frame_index", 0)
    else:
        lib.set_additive_animation_type(anim, unreal.AdditiveAnimationType.AAT_NONE)
        lib.set_additive_base_pose_type(anim, unreal.AdditiveBasePoseType.ABPT_NONE)

    # ---- event notifies
    lib.remove_all_animation_notify_tracks(anim)
    events = entry.get("events", [])
    if events:
        lib.add_animation_notify_track(anim, "Events")
        length = anim.get_editor_property("sequence_length")
        for ev in events:
            t = float(ev.get("time_s", ev.get("frame", 0) / 30.0))
            t = max(0.0, min(t, length - 1e-4))
            n = lib.add_animation_notify_event(anim, "Events", t, unreal.OperativeEventNotify)
            n.set_editor_property("event_name", ev["name"])
            n.set_editor_property("params", _params_string(ev.get("params", {})))
            stats["events"] += 1
    return stats


def run(ctx):
    C.ensure_dir(C.ANIM_DIR)
    skel = ctx.state.get("skeleton") or C.load(C.SKELETON_PATH)
    clips = ctx.manifest["clips"]
    opts = anim_options(skel)
    batch = []
    imported = []
    for entry in clips:
        fbx = os.path.join(ctx.root, entry["export_file"])
        if not os.path.exists(fbx):
            C.warn("missing clip FBX", fbx)
            continue
        dest = entry["unreal_asset"].rsplit("/", 1)[0]
        batch.append(C.import_task(fbx, dest, entry["id"], opts, save=False))
        imported.append(entry)
        if len(batch) >= 16:
            C.run_tasks(batch)
            batch = []
    if batch:
        C.run_tasks(batch)
    total_removed = total_events = bad = 0
    lengths = {}
    for entry in imported:
        anim = unreal.load_asset(entry["unreal_asset"])
        if not isinstance(anim, unreal.AnimSequence):
            C.warn("clip did not import", entry["id"])
            bad += 1
            continue
        st = post_process(entry, anim)
        total_removed += st["removed_curves"]
        total_events += st["events"]
        length = anim.get_editor_property("sequence_length")
        lengths[entry["id"]] = length
        expect = entry["frames"] / 30.0
        if abs(length - expect) > 1.5 / 30.0:
            C.warn("length mismatch", entry["id"], "unreal %.3f manifest %.3f" % (length, expect))
        C.save(anim)
    C.log("clips imported %d/%d removed_curves=%d events=%d bad=%d" % (len(lengths), len(clips), total_removed, total_events, bad))
    ctx.state["anim_count"] = len(lengths)

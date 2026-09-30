#!/usr/bin/env python3
"""Generate the machine-readable documentation from the exported asset.

    python3 MorphRig/tools/make_docs.py

Inputs : export/reports.json, export/animations/clips_meta.json, export/animations/face_curves.json,
         docs/required_animations.csv, docs/qa/motion_qa.json (optional)
Outputs: docs/animation_manifest.json, docs/skeleton_and_sockets.json, docs/material_and_lod_report.json
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 30
UE_ANIM = "/Game/MorphRig/Animations/A_{}"
LIMITS = {"LOD0": 80000, "LOD1": 40000, "LOD2": 20000}


def load(rel, default=None):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return default
    with open(p) as fh:
        return json.load(fh)


def duration_ok(rng, secs, form):
    if rng.strip() == "pose":
        return form == "pose"
    lo, hi = [float(x) for x in rng.replace("–", "-").split("-")]
    return lo - 1e-6 <= secs <= hi + 1e-6


def manifest():
    metas = load("export/animations/clips_meta.json", {})
    faces = load("export/animations/face_curves.json", {})
    qa = load("docs/qa/motion_qa.json", {})
    req = {}
    with open(os.path.join(ROOT, "docs", "required_animations.csv")) as fh:
        for r in csv.DictReader(fh):
            req[r["id"]] = r
    clips, extras, missing = [], [], []
    for cid in list(req) + sorted(set(metas) - set(req)):
        m = metas.get(cid)
        if m is None:
            missing.append(cid)
            continue
        n = int(m["frames"])
        secs = n / FPS
        r = req.get(cid)
        entry = {
            "id": cid,
            "required": r is not None,
            "form": m["form"],
            "loop": bool(m["loop"]),
            "root_motion_policy": m["root"],
            "intended_layer": m["layer"],
            "sample_rate_fps": FPS,
            "frame_range": [0, n],
            "frame_count": n + 1,
            "duration_s": round(secs, 4),
            "nominal_speed_cms": m.get("speed_cms", 0.0),
            "entry_states": m.get("entry", ""),
            "exit_states": m.get("exit", ""),
            "event_markers": [{"frame": int(f), "time_s": round(int(f) / FPS, 4), "name": nm} for f, nm in m.get("markers", [])],
            "source_blend": "source/Operative.blend",
            "source_action_editable": f"RIG_{cid}",
            "source_action_baked": f"SK_{cid}",
            "export_file": f"export/animations/{cid}.fbx",
            "export_take": f"SK_{cid}",
            "unreal_asset": UE_ANIM.format(cid),
            "face_curves": sorted(faces.get(cid, {}).get("curves", {}).keys()),
            "notes": m.get("notes", ""),
        }
        if r:
            entry["required_form"] = r["form"]
            entry["required_root_movement"] = r["root_movement"]
            entry["required_duration"] = r["duration_seconds"]
            entry["duration_in_range"] = duration_ok(r["duration_seconds"], secs, m["form"])
            entry["required_behavior"] = r["required_behavior"]
        if cid in qa:
            q = qa[cid]
            entry["qa"] = {k: q[k] for k in ("loop_seam", "foot_slide_cm", "min_body_z_cm", "body_clear_cm",
                                             "pelvis_drift_cm") if k in q}
        (clips if r else extras).append(entry)
    out = {
        "character": "MorphRig Operative",
        "sample_rate_fps": FPS,
        "frame_convention": "frames 0..N inclusive at 30 fps, duration = N / 30 s; loops repeat frame 0 at N",
        "units": "Blender metres / Unreal centimetres; root motion only on dash_* (2 m nominal)",
        "required_count": len(req),
        "delivered_required": len(clips),
        "missing_required": missing,
        "clips": clips,
        "extra_clips": extras,
    }
    with open(os.path.join(ROOT, "docs", "animation_manifest.json"), "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    bad = [c["id"] for c in clips if not c.get("duration_in_range", True)]
    print("manifest:", len(clips), "required +", len(extras), "extra; missing", missing, "; out of range", bad)


def skeleton():
    rep = load("export/reports.json", {})
    bones = []
    for b in rep.get("bones", []):
        bones.append({
            "name": b["name"], "parent": b["parent"], "deform": b["deform"],
            "head_blender_m": b["head_m"], "tail_blender_m": b["tail_m"],
            "head_unreal_cm": [round(b["head_m"][0] * 100, 3), round(-b["head_m"][1] * 100, 3), round(b["head_m"][2] * 100, 3)],
            "bone_axis_y_blender": b["axis_y"], "bone_axis_z_blender": b["axis_z"],
        })
    out = {
        "skeleton": "SKEL_Operative (Unreal asset created with /Game/MorphRig/Character/SK_Operative)",
        "root_bone": "root (single stable root at the ground origin, independent of pelvis)",
        "conventions": {
            "blender": "metres, +Z up, character faces -Y, character left = +X, bone Y along the bone",
            "unreal": "centimetres, +Z up, mesh faces +Y in component space (component yaw -90 on the "
                      "character so the actor faces +X); FBX written in centimetres (export copy converted, every bone scale 1), no import-scale repair",
            "unit_conversion": "Unreal = Blender x 100 with Y flipped (x, -y, z) for mesh-space positions",
        },
        "bone_count": len(bones),
        "deform_bone_count": sum(1 for b in bones if b["deform"]),
        "bones": bones,
        "sockets": [dict(s, unreal_socket=s["socket"]) for s in rep.get("sockets", [])],
        "morph_targets": rep.get("shape_keys", []),
        "face_control_poses": [f"ctl_{n}" for n in ("blink_l", "blink_r", "wide_l", "wide_r", "squint_l", "squint_r",
                                                   "jaw_open", "jaw_left", "jaw_right", "look_left", "look_right",
                                                   "look_up", "look_down", "tongue_up", "tongue_down")],
    }
    with open(os.path.join(ROOT, "docs", "skeleton_and_sockets.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("skeleton:", out["bone_count"], "bones,", len(out["sockets"]), "sockets")


def materials_lods():
    rep = load("export/reports.json", {})
    lods = rep.get("lods", {})
    out = {
        "lods": {k: {"triangles": v["tris"], "limit": LIMITS.get(k), "within_limit": v["tris"] <= LIMITS.get(k, 1e9),
                     "vertices": v["verts"], "material_slots": v["materials"], "max_bone_influences": v["max_influences"],
                     "per_object_triangles": v["objects"]} for k, v in sorted(lods.items())},
        "material_slots_total": len(set(sum((v["materials"] for v in lods.values()), []))),
        "material_slot_limit": 8,
        "textures": rep.get("textures", []),
        "texture_max_dimension": max((max(t["width"], t["height"]) for t in rep.get("textures", [])), default=0),
        "texture_memory_estimate_mb": rep.get("texture_memory_mb"),
        "texture_memory_note": "estimate: BC7 / BC5 1 byte per texel, full mip chain (x 4/3); 28 PBR maps + icon",
        "deform_bone_count": rep.get("deform_bone_count"),
        "bone_count_including_sockets": rep.get("bone_count"),
        "bone_influence_limit_export": 8,
        "bone_influences_authored": 4,
        "height_m": rep.get("height_m"),
        "units": rep.get("units"),
    }
    with open(os.path.join(ROOT, "docs", "material_and_lod_report.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print("lods:", {k: v["triangles"] for k, v in out["lods"].items()}, "materials", out["material_slots_total"])


if __name__ == "__main__":
    manifest()
    skeleton()
    materials_lods()

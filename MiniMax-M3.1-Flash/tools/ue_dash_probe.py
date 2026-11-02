"""Probe the imported dash clips in Unreal.

Reports for every clip of interest whether root motion is enabled and what the
root bone track looks like at the first and the last frame.  This proves where
the 2 m of dash displacement lives inside Unreal.
"""
import json
import os

import unreal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "dash_probe.json")

CLIPS = ["dash_f", "dash_b", "dash_l", "dash_r", "walk_f", "idle_combat"]
ANIM_DIR = "/Game/MorphRig/Animations"

report = {"clips": {}}

for name in CLIPS:
    path = "%s/A_%s" % (ANIM_DIR, name)
    seq = unreal.load_asset(path)
    if seq is None:
        report["clips"][name] = {"error": "not found"}
        continue

    entry = {
        "enable_root_motion": bool(seq.get_editor_property("enable_root_motion")),
        "play_length": float(seq.get_editor_property("sequence_length")),
        "number_of_frames": int(seq.get_editor_property("number_of_sampled_keys")),
        
        "has_root_motion": bool(unreal.AnimationBlueprintLibrary.is_root_motion_enabled(seq)),
    }

    length = entry["play_length"]
    samples = []
    for t in (0.0, length * 0.25, length * 0.5, length * 0.75, length):
        for extract in (False, True):
            ok, xform = unreal.AnimationBlueprintLibrary.get_bone_pose_for_time(
                seq, "root", t, extract)
            if not ok:
                samples.append({"t": round(t, 4), "extract": extract, "error": "no pose"})
                continue
            loc = xform.translation
            samples.append({
                "t": round(t, 4),
                "extract": extract,
                "loc": [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)],
            })
    entry["root_samples"] = samples
    report["clips"][name] = entry

with open(OUT, "w") as handle:
    json.dump(report, handle, indent=2)

for name, entry in report["clips"].items():
    unreal.log("DASHPROBE %s root_motion=%s length=%.3f frames=%d" %
               (name, entry.get("enable_root_motion"), entry.get("play_length", 0.0),
                entry.get("number_of_frames", 0)))
    for s in entry.get("root_samples", []):
        unreal.log("DASHPROBE   %s t=%.3f extract=%s loc=%s" %
                   (name, s["t"], s["extract"], s.get("loc", s.get("error"))))

unreal.log("DASHPROBE written %s" % OUT)

#!/usr/bin/env python3
"""Cross-check the final task deliverables without changing them."""
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
checks = []


def check(name, condition, detail=""):
    checks.append({"check": name, "passed": bool(condition), "detail": str(detail)})


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


required_files = [
    "README.md", "source/Operative.blend", "source/audio/dialogue.wav", "source/audio/dialogue.txt",
    "source/audio/dialogue_alignment.json", "export/Operative.fbx", "unreal/MorphRig/MorphRig.uproject",
    "docs/rig_usage.md", "docs/skeleton_and_sockets.json", "docs/animation_manifest.json",
    "docs/animation_state_contract.md", "docs/material_and_lod_report.json", "docs/THIRD_PARTY_ASSETS.csv",
    "docs/build_and_import_instructions.md", "docs/known_issues.md", "tools/export_and_bake.py",
    "tools/build_linux.sh", "presentation/turntable.mp4", "presentation/motion_showcase.mp4",
    "presentation/face_performance.mp4",
]
for filename in required_files:
    path = ROOT / filename
    check("exists:" + filename, path.is_file() and path.stat().st_size > 0, path.stat().st_size if path.exists() else "missing")

manifest = read_json(DOCS / "animation_manifest.json")
with (ROOT / "source" / "required_animations.csv").open(newline='', encoding='utf-8') as stream:
    csv_rows = list(csv.DictReader(stream))
entries = manifest["entries"]
check("inventory:96", len(entries) == 96 and len({entry["id"] for entry in entries}) == 96)
check("inventory:85motion11pose", sum(entry["form"] != "pose" for entry in entries) == 85 and sum(entry["form"] == "pose" for entry in entries) == 11)
check("inventory:csv_order", [row["id"] for row in csv_rows] == [entry["id"] for entry in entries])
for row, entry in zip(csv_rows, entries):
    check("metadata:" + entry["id"], (entry["form"], entry["root_motion_policy"], entry["required_behavior"]) == (row["form"], row["root_movement"], row["required_behavior"]))
    if row["duration_seconds"] == "pose":
        check("pose_duration:" + entry["id"], entry["duration_seconds"] == 0 and entry["frame_count"] == 1)
    else:
        low, high = [float(value) for value in row["duration_seconds"].replace("–", "-").split("-")]
        check("duration:" + entry["id"], low <= entry["duration_seconds"] <= high and abs(entry["duration_seconds"] - (entry["frame_range"][1] / 30)) < 1e-6)
    check("action_names:" + entry["id"], entry["source_action"] == entry["id"] and entry["editable_control_action"] == "SOURCE_" + entry["id"])
    check("unreal_path:" + entry["id"], entry["unreal_asset"] == "/Game/Operative/Animations/" + entry["id"])
    fbx = ROOT / "export" / entry["exported_file"]
    check("fbx:" + entry["id"], fbx.is_file() and fbx.stat().st_size > 1024)
    check("fps:" + entry["id"], entry["sample_rate"] == 30)
    if entry["root_motion_policy"] == "in_place":
        check("in_place:" + entry["id"], entry["nominal_root_displacement_m"] == [0, 0, 0])
    for event in entry["events"]:
        check("event_time:" + entry["id"] + ":" + event["name"], 0 <= event["time"] <= entry["duration_seconds"] + 1e-6)
        check("event_frame:" + entry["id"] + ":" + event["name"], round(event["time"] * 30) == event["frame"])

skeleton = read_json(DOCS / "skeleton_and_sockets.json")
check("skeleton:70", skeleton["deformation_bone_count"] == 70 and len(skeleton["bones"]) == 70)
check("skeleton:single_root", [bone["name"] for bone in skeleton["bones"] if bone["parent"] is None] == ["root"])
check("skeleton:connected", all(bone["parent"] in {item["name"] for item in skeleton["bones"]} for bone in skeleton["bones"] if bone["parent"]))
for socket in ("hand_left", "hand_right", "emitter_muzzle", "blade_base", "blade_tip", "power_cell", "beacon", "fx_chest"):
    check("socket:" + socket, any(item["name"] == socket for item in skeleton["sockets"]))

report = read_json(DOCS / "material_and_lod_report.json")
check("materials:8", report["material_slots_total"] == 8 and len(report["materials"]) == 8)
check("influences:8", report["max_effective_bone_influences"] <= 8)
check("textures:4096", report["max_texture_dimension"] <= 4096)
for lod in report["lods"]:
    check("lod_budget:" + str(lod["lod"]), lod["within_budget"] and lod["source_triangles"] <= lod["required_triangle_budget"])
check("lod_distinct", len({lod["source_triangles"] for lod in report["lods"]}) == 3)
check("source_validation", read_json(DOCS / "validation" / "source_asset_validation.json")["status"] == "PASS")
check("analytic_motion", read_json(DOCS / "validation" / "analytic_motion.json")["status"] == "PASS")

import_audit_path = DOCS / "unreal_import_audit.json"
check("unreal_audit_exists", import_audit_path.exists())
if import_audit_path.exists():
    audit = read_json(import_audit_path)
    check("unreal_audit_pass", audit["status"] == "PASS", audit.get("failures", []))
    check("unreal_height", abs(audit["height_cm"] - 180) <= 1, audit["height_cm"])
    check("unreal_bones", audit["bone_count"] == 70 and audit["roots"] == ["root"])
    check("unreal_lods", len(audit["lods"]) == 3)
    check("unreal_morphs", len(audit["morph_names"]) == 26)
    check("unreal_clips", len(audit["clips"]) == 96)
    check("unreal_event_audit", audit.get("event_audit_required") is True)
    for clip in audit["clips"]:
        entry = next(item for item in entries if item["id"] == clip["id"])
        check("unreal_duration:" + clip["id"], abs(clip["length"] - entry["duration_seconds"]) <= .04)
        check("unreal_events:" + clip["id"], clip["event_count"] == len(entry["events"]))
    dialogue = next((clip for clip in audit["clips"] if clip["id"] == "dialogue"), None)
    check("unreal_dialogue_curves", dialogue and len(dialogue["float_curves"]) >= 12)

launchers = sorted((ROOT / "build" / "Linux").glob("MorphRig.sh")) + sorted((ROOT / "build" / "Linux").glob("*/MorphRig.sh"))
check("linux_launcher", any(path.stat().st_size > 0 for path in launchers), [str(path.relative_to(ROOT)) for path in launchers])
for path in launchers:
    binary = path.parent / "MorphRig" / "Binaries" / "Linux" / "MorphRig"
    check("linux_binary:" + str(path.relative_to(ROOT)), binary.is_file() and binary.stat().st_size > 1000000)

for filename, minimum_duration in (("turntable.mp4", 5), ("motion_showcase.mp4", 15), ("face_performance.mp4", 12)):
    path = ROOT / "presentation" / filename
    if path.exists():
        try:
            data = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], text=True))
            duration = float(data["format"]["duration"])
            check("video_duration:" + filename, duration >= minimum_duration, duration)
        except Exception as error:
            check("video_probe:" + filename, False, error)

for path in (ROOT / "unreal" / "MorphRig" / "Source").rglob("*"):
    if path.suffix in (".h", ".cpp", ".cs") and "Intermediate" not in path.parts:
        text = path.read_text(encoding="utf-8")
        check("no_private_source_path:" + str(path.relative_to(ROOT)), "/home/morpheus" not in text)

for entry in entries:
    native_clip = ROOT / "unreal" / "MorphRig" / "Content" / "Operative" / "Animations" / (entry["id"] + ".uasset")
    check("native_clip_asset:" + entry["id"], native_clip.is_file() and native_clip.stat().st_size > 0)
check("native_mesh_persisted", (ROOT / "unreal" / "MorphRig" / "Content" / "Operative" / "SK_Operative.uasset").is_file())
check("native_audio_persisted", (ROOT / "unreal" / "MorphRig" / "Content" / "Operative" / "Audio" / "Dialogue.uasset").is_file())
check("native_sockets", len(skeleton["sockets"]) == 10 and all(item.get("unreal_bone") for item in skeleton["sockets"]))
check("source_controls", read_json(DOCS / "validation" / "blender_controls.json")["status"] == "PASS")
beacon_report_path = DOCS / "validation" / "beacon_import.json"
check("beacon_import_report", beacon_report_path.is_file() and read_json(beacon_report_path).get("status") == "PASS")
if beacon_report_path.exists():
    native_beacon = read_json(beacon_report_path)
    source_beacon = read_json(DOCS / "validation" / "beacon_export.json")
    beacon_file = ROOT / "export" / "Beacon.fbx"
    check("native_beacon_geometry", native_beacon.get("triangles") == source_beacon["triangles"] and native_beacon.get("uv_channels") == source_beacon["uv_layers"] and len(native_beacon.get("material_slots", [])) == 3)
    check("native_beacon_persisted", native_beacon.get("persisted") is True and beacon_file.is_file() and (ROOT / "unreal" / "MorphRig" / "Content" / "Operative" / "ST_Beacon.uasset").is_file())
    check("native_beacon_current_export", native_beacon.get("fbx_sha256") == hashlib.sha256(beacon_file.read_bytes()).hexdigest())
check("texture_set", report.get("texture_count") == 24, report.get("texture_count"))
with wave.open(str(ROOT / "source" / "audio" / "dialogue.wav"), "rb") as audio:
    duration = audio.getnframes() / audio.getframerate()
    check("dialogue_duration_12_to_18_seconds", 12.0 <= duration <= 18.0, duration)

if import_audit_path.exists():
    audit = read_json(import_audit_path)
    check("native_unit_scale", audit.get("axis_evidence", {}).get("max_bone_scale_error", 100) <= .001)
    check("native_materials", len(audit["material_slots"]) == 8)
    check("native_lod_distinct_and_matching", sorted(lod["render_triangles"] for lod in audit["lods"]) == sorted(lod["source_triangles"] for lod in report["lods"]))
    expected_morphs = {name.replace(".", "_") for name in read_json(DOCS / "source_geometry_report.json")["shape_keys"]}
    check("native_morph_names", set(audit["morph_names"]) == expected_morphs)
    for clip in audit["clips"]:
        entry = next(item for item in entries if item["id"] == clip["id"])
        check("native_fps_tracks:" + clip["id"], clip["fps"] == 30 and clip["bone_tracks"] == 70)
        expected_events = sorted((event["time"], event["name"]) for event in entry["events"])
        actual_events = sorted((event["time"], event["name"]) for event in clip["events"])
        check("native_event_identity:" + clip["id"], len(expected_events) == len(actual_events) and all(abs(a[0] - e[0]) <= .001 and a[1] == e[1] for a, e in zip(actual_events, expected_events)))
        check("native_event_classes:" + clip["id"], all(event["class"] == "MorphEventNotify" for event in clip["events"]))

runtime_path = DOCS / "validation" / "runtime_verification.json"
check("runtime_evidence_exists", runtime_path.is_file())
if runtime_path.is_file():
    runtime = read_json(runtime_path)
    check("runtime_success", runtime.get("success") is True, runtime.get("failures", []))
    check("runtime_manifest", runtime.get("manifest_loaded") is True)
    check("runtime_96_clips", runtime.get("loaded_clips") == 96 and len(runtime.get("clip_results", [])) == 96)
    check("runtime_all_sampled", all(clip.get("loaded") and clip.get("requested") and clip.get("sampled") for clip in runtime.get("clip_results", [])))
    check("runtime_checks", bool(runtime.get("checks")) and all(item.get("passed") for item in runtime["checks"]))
state_path = DOCS / "validation" / "states_trace.txt"
check("state_demo_trace", state_path.is_file() and "MR_STATE" in state_path.read_text() and "MR_EVENT" in state_path.read_text())
performance_path = DOCS / "validation" / "performance.json"
check("performance_evidence_exists", performance_path.is_file())
if performance_path.is_file():
    performance = read_json(performance_path)
    check("performance_resolution", performance.get("resolution") == "1920x1080" and performance.get("frame_generation") is False)
    for group in ("one", "ten"):
        sample = performance.get("samples", {}).get(group, {})
        check("performance_sample:" + group, sample.get("frame_count", 0) > 60 and sample.get("median_ms", 0) > 0 and sample.get("warmup_seconds", 0) >= 3 and len(sample.get("frames", [])) == sample.get("frame_count"))
    check("performance_hardware", bool(performance.get("cpu")) and bool(performance.get("gpu")) and bool(performance.get("rhi")))
rendered_path = DOCS / "validation" / "rendered_inspection.json"
check("rendered_inspection", rendered_path.is_file() and read_json(rendered_path).get("status") == "PASS" and len(read_json(rendered_path).get("inspected", [])) >= 3)

result = {"status": "PASS" if all(item["passed"] for item in checks) else "FAIL", "checks": len(checks), "failures": [item for item in checks if not item["passed"]], "results": checks}
(DOCS / "validation" / "delivery_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "checks": len(checks), "failure_count": len(result["failures"])}))
for failure in result["failures"]:
    print("FAIL", failure["check"], failure["detail"])
raise SystemExit(0 if result["status"] == "PASS" else 1)

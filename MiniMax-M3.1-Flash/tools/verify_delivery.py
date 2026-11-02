"""Check the MORPHRIG delivery against the specification budgets.

    python3 tools/verify_delivery.py

This runs outside of Blender and outside of Unreal, it only reads the
reports, the manifests and the files of the delivery.  It prints one line
per check and exits with a non zero code when a check fails.
"""

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print("%-4s %-42s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def path(*parts):
    return os.path.join(ROOT, *parts)


def load_json(*parts):
    with open(path(*parts)) as fh:
        return json.load(fh)


def probe_video(name):
    """The duration and the frame count of a delivered video."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration:stream=width,height,nb_frames",
         "-of", "json", path("presentation", name)],
        capture_output=True, text=True)
    if out.returncode != 0:
        return None
    data = json.loads(out.stdout)
    stream = data.get("streams", [{}])[0]
    return {
        "duration": float(data.get("format", {}).get("duration", 0.0)),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frames": int(stream.get("nb_frames", 0)),
    }


def main():
    print("MORPHRIG delivery check")
    print("-" * 72)

    # ---- the layout --------------------------------------------------------
    layout = [
        "README.md",
        "source/Operative.blend",
        "source/generators",
        "source/textures",
        "source/audio/dialogue.wav",
        "source/audio/dialogue.txt",
        "source/audio/dialogue_alignment.json",
        "export/Operative.fbx",
        "export/animations",
        "export/textures",
        "unreal/MorphRig.uproject",
        "unreal/Source/MorphRig",
        "unreal/Config",
        "unreal/Content/MorphRig",
        "build/Linux",
        "docs/rig_usage.md",
        "docs/skeleton_and_sockets.json",
        "docs/animation_manifest.json",
        "docs/animation_state_contract.md",
        "docs/material_and_lod_report.json",
        "docs/THIRD_PARTY_ASSETS.csv",
        "docs/build_and_import_instructions.md",
        "docs/known_issues.md",
        "docs/performance_report.md",
        "tools/build_linux.sh",
        "presentation/turntable.mp4",
        "presentation/motion_showcase.mp4",
        "presentation/face_performance.mp4",
    ]
    missing = [name for name in layout if not os.path.exists(path(*name.split("/")))]
    check("the delivery layout is complete", not missing,
          "missing: %s" % ", ".join(missing) if missing else
          "%d entries" % len(layout))

    # ---- the motion inventory ----------------------------------------------
    with open(path("required_animations.csv")) as fh:
        required = [row["id"] for row in csv.DictReader(fh)]
    manifest = load_json("docs", "animation_manifest.json")
    clips = manifest["clips"]
    names = [c["name"] for c in clips]
    check("every required clip is delivered",
          set(required) == set(names),
          "%d required, %d delivered" % (len(required), len(names)))
    check("no clip is delivered twice", len(names) == len(set(names)),
          "%d entries" % len(names))
    check("the manifest carries the frame range, the sample rate and the "
          "duration",
          all(c.get("frame_start") and c.get("frame_end") and
              c.get("sample_rate") and c.get("duration") and
              c.get("loop") is not None and c.get("layer") and
              c.get("root_motion") and c.get("entry_state") and
              c.get("exit_state") for c in clips),
          "%d clips" % len(clips))
    check("every clip has an event marker list",
          all(isinstance(c.get("markers"), list) for c in clips))
    check("every clip is exported as FBX",
          all(c.get("exported") for c in clips))
    root = [c["name"] for c in clips if c.get("root_motion") != "in_place"]
    check("at most four root motion clips", len(root) <= 4, ", ".join(root))

    # ---- the geometry budgets ---------------------------------------------
    lod = load_json("docs", "material_and_lod_report.json")
    limits = {"LOD0": 80000, "LOD1": 40000, "LOD2": 20000}
    for entry in lod.get("lods", []):
        name = entry.get("lod", "?")
        limit = limits.get(name)
        if limit is None:
            continue
        tris = entry.get("triangles", 0)
        check("the %s triangle budget" % name, tris <= limit,
              "%d of %d" % (tris, limit))
    slots = max((e.get("material_slot_count", 0) for e in lod.get("lods", [])),
                default=0)
    check("at most eight material slots", slots <= 8, "%d slots" % slots)
    check("the texture count", lod.get("texture_count", 0) == 24,
          "%s textures" % lod.get("texture_count"))
    maxsize = lod.get("max_texture_size", 0)
    check("no texture is larger than 4096", maxsize <= 4096, "max %s" % maxsize)
    check("the unit is the metre and the forward axis is -Y",
          lod.get("unit") == "metre" and lod.get("forward") == "-Y",
          "%s / %s" % (lod.get("unit"), lod.get("forward")))

    # ---- the rig ------------------------------------------------------------
    rig = load_json("docs", "skeleton_and_sockets.json")
    bones = rig.get("bones", [])
    # the control rig lives in the same file but it is not the deform skeleton
    deform = [b for b in bones if b.get("deform", True)]
    root_bones = [b for b in deform if not b.get("parent")]
    check("exactly one independent root bone in the deform skeleton",
          len(root_bones) == 1 and root_bones[0].get("name") == "root",
          "%s" % ", ".join(b.get("name", "?") for b in root_bones))
    pelvis = next((b for b in bones if b.get("name") == "pelvis"), None)
    check("the root bone is independent from the pelvis",
          pelvis is not None and pelvis.get("parent") == "root")
    check("the deform skeleton carries 71 bones",
          rig.get("deform_bone_count", 0) == 71,
          "%s" % rig.get("deform_bone_count"))
    socket_names = [s.get("name") for s in rig.get("sockets", [])]
    wanted = ["hand_r", "hand_l", "emitter_muzzle_r", "blade_base_r",
              "blade_tip_r"]
    check("the sockets document the hands, the emitter and the blade",
          all(name in socket_names for name in wanted),
          "%s" % ", ".join(socket_names))
    check("the axes map to +X forward in Unreal",
          rig.get("axes", {}).get("unreal_forward") == "+X")

    # ---- the skin ----------------------------------------------------------
    skin_path = path("docs", "skin_report.json")
    if os.path.exists(skin_path):
        skin = load_json("docs", "skin_report.json")
        check("no unbound vertex", skin.get("unbound_count", 1) == 0,
              "%s" % skin.get("unbound_count"))
        ratios = skin.get("edge_ratio", {})
        worst = max(ratios.values()) if ratios else 0.0
        check("the mesh never stretches", worst <= 1.6, "worst ratio %.3f" % worst)
    else:
        check("the skin report exists", False, "docs/skin_report.json missing")

    # ---- the videos --------------------------------------------------------
    for name, low, high in (("turntable.mp4", 4.0, 12.0),
                            ("motion_showcase.mp4", 10.0, 20.0),
                            ("face_performance.mp4", 10.0, 20.0)):
        info = probe_video(name)
        if info is None:
            check("the video %s is readable" % name, False)
            continue
        check("the video %s has the right length" % name,
              low <= info["duration"] <= high,
              "%.1f s, %dx%d, %d frames" % (info["duration"], info["width"],
                                            info["height"], info["frames"]))

    # ---- the packaged client ----------------------------------------------
    # The archive root is build/Linux.  The launcher sits next to the staged
    # project folder, the binary inside it.
    launchers = [path("build", "Linux", "MorphRig.sh"),
                 path("build", "Linux", "MorphRig", "MorphRig.sh")]
    launcher = next((p for p in launchers if os.path.exists(p)), None)
    binary = path("build", "Linux", "MorphRig", "Binaries", "Linux", "MorphRig")
    check("the packaged client exists",
          launcher is not None and os.path.exists(binary),
          "%s + %s" % (os.path.relpath(launcher, ROOT) if launcher else "no launcher",
                       os.path.relpath(binary, ROOT)))
    perf = path("build", "perf")
    runs = []
    if os.path.isdir(perf):
        runs = [n for n in os.listdir(perf)
                if n.startswith("MorphRigPerf_instances") and n.endswith(".csv")]
    check("the performance logs are captured", len(runs) >= 2,
          ", ".join(sorted(runs)))

    # ---- the third party manifest -----------------------------------------
    with open(path("docs", "THIRD_PARTY_ASSETS.csv")) as fh:
        rows = list(csv.DictReader(fh))
    check("the third party manifest lists a source and a licence",
          bool(rows) and all(r.get("source") and r.get("license") for r in rows),
          "%d entries" % len(rows))

    print("-" * 72)
    failed = [name for name, ok, _ in CHECKS if not ok]
    print("%d checks, %d failed" % (len(CHECKS), len(failed)))
    for name in failed:
        print("  FAILED: %s" % name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

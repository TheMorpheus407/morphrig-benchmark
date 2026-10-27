#!/usr/bin/env python3
"""Capture the packaged real-time character and encode the required presentations."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "build" / "Linux"
VALIDATION = ROOT / "docs" / "validation"
PRESENTATION = ROOT / "presentation"
ENVIRONMENT = json.loads((ROOT.parent / "environment.json").read_text(encoding="utf-8"))
WRAPPER = ENVIRONMENT["unreal_engine"]["runtime_wrapper"].split()[0]
EXPECTED = {"turntable": 180, "motion": 1260, "face": 480}
FILENAMES = {"turntable": "turntable.mp4", "motion": "motion_showcase.mp4", "face": "face_performance.mp4"}


def launcher():
    sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
    from verify_runtime import executable_from_archive
    return executable_from_archive()


def capture(kind, executable):
    started = time.time_ns()
    VALIDATION.mkdir(parents=True, exist_ok=True)
    with (VALIDATION / f"capture_{kind}.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [WRAPPER, str(executable), f"-MorphCapture={kind}", "-windowed", "-ResX=1920", "-ResY=1080"],
            cwd=executable.parent, stdout=log, stderr=subprocess.STDOUT, timeout=600,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"Packaged {kind} capture exited {completed.returncode}; see docs/validation/capture_{kind}.log")
    candidates = [path for path in ARCHIVE.rglob("capture.json") if path.match(f"*/Saved/MorphRig/MorphCapture/{kind}/capture.json")]
    if not candidates:
        raise RuntimeError(f"No capture report for {kind}")
    report_path = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    if report_path.stat().st_mtime_ns < started:
        raise RuntimeError(f"Stale {kind} capture report: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("kind") != kind or not report.get("mesh_loaded") or report.get("fps") != 30 or report.get("frames") != EXPECTED[kind]:
        raise RuntimeError(f"Unexpected {kind} capture metadata: {report}")
    directory = (executable.parent / report["directory"]).resolve()
    if not directory.is_relative_to(ROOT):
        raise RuntimeError(f"Capture directory is outside the task folder: {directory}")
    frames = [directory / f"frame_{index:04d}.png" for index in range(EXPECTED[kind])]
    missing = [path.name for path in frames if not path.is_file() or path.stat().st_size < 1024 or path.stat().st_mtime_ns < started]
    if missing:
        raise RuntimeError(f"Missing, stale, or empty rendered {kind} frames: {missing[:12]}")
    return directory, frames, report


def encode(kind, directory, frames, report):
    destination = PRESENTATION / FILENAMES[kind]
    PRESENTATION.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-framerate", "30", "-start_number", "0", "-i", str(directory / "frame_%04d.png")]
    if kind == "face":
        command.extend(["-i", str(ROOT / "source" / "audio" / "dialogue.wav")])
    command.extend(["-map", "0:v:0"])
    if kind == "face":
        command.extend(["-map", "1:a:0"])
    command.extend(["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30", "-frames:v", str(len(frames))])
    if kind == "face":
        command.extend(["-c:a", "aac", "-b:a", "160k", "-af", "apad"])
    command.extend(["-t", f"{len(frames) / 30:.9f}", "-movflags", "+faststart", str(destination)])
    with (VALIDATION / f"encode_{kind}.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames,duration:format=duration", "-of", "json", str(destination),
    ], text=True))
    video = probe["streams"][0]
    if video["codec_name"] != "h264" or video["r_frame_rate"] != "30/1" or int(video["nb_frames"]) != len(frames):
        raise RuntimeError(f"Encoded video failed frame/rate validation: {probe}")
    if kind == "face" and (len(probe["streams"]) < 2 or probe["streams"][1]["codec_name"] != "aac"):
        raise RuntimeError(f"Speech video is missing its original WAV audio stream: {probe}")
    report["capture_step_seconds"] = 1.0 / 30.0
    if kind == "face":
        report["audio_source"] = "source/audio/dialogue.wav"
        report["audio_mux"] = "Original 15.2-second WAV with a silent 0.8-second settle; no pitch or playback-rate change"
    report["video"] = str(destination.relative_to(ROOT))
    report["directory"] = str(directory.relative_to(ROOT))
    report["verified_frame_count"] = len(frames)
    report["video_probe"] = probe
    (VALIDATION / f"capture_{kind}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{destination.relative_to(ROOT)}: {len(frames)} rendered frames at 30 FPS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=list(EXPECTED), action="append", help="Capture only this presentation; may be repeated")
    parser.add_argument("--encode-only", action="store_true", help="Encode a previously completed native capture instead of launching the client")
    args = parser.parse_args()
    for executable in (WRAPPER, "ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            raise RuntimeError(f"Required tool is unavailable: {executable}")
    executable = launcher()
    for kind in args.kind or EXPECTED:
        if args.encode_only:
            candidates = [path for path in ARCHIVE.rglob("capture.json") if path.match(f"*/Saved/MorphRig/MorphCapture/{kind}/capture.json")]
            if not candidates:
                raise RuntimeError(f"No completed {kind} capture to encode")
            report = json.loads(max(candidates, key=lambda path: path.stat().st_mtime_ns).read_text(encoding="utf-8"))
            directory = (executable.parent / report["directory"]).resolve()
            frames = [directory / f"frame_{index:04d}.png" for index in range(EXPECTED[kind])]
            if not directory.is_relative_to(ROOT) or any(not path.is_file() for path in frames):
                raise RuntimeError(f"Incomplete {kind} frame sequence in {directory}")
        else:
            directory, frames, report = capture(kind, executable)
        encode(kind, directory, frames, report)


if __name__ == "__main__":
    main()

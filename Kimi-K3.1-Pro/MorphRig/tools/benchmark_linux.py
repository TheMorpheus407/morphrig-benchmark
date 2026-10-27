#!/usr/bin/env python3
"""Measure the packaged one/ten-instance showcase with an isolated GPU."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "docs" / "validation"
sys.path.insert(0, str(ROOT / "unreal" / "MorphRig" / "Tools"))
from verify_runtime import executable_from_archive


def main():
    environment = json.loads((ROOT.parent / "environment.json").read_text(encoding="utf-8"))
    wrapper = environment["unreal_engine"]["runtime_wrapper"].split()[0]
    executable = executable_from_archive()
    for tool in (wrapper, "nvidia-smi"):
        if not shutil.which(tool):
            raise RuntimeError(f"Required measurement tool is unavailable: {tool}")
    query = ["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"]
    processes = subprocess.check_output(query, text=True).strip()
    if processes and os.environ.get("MORPH_BENCH_ALLOW_SHARED_GPU") != "1":
        raise RuntimeError("Other GPU work is active. Stop it before measuring, or explicitly set MORPH_BENCH_ALLOW_SHARED_GPU=1:\n" + processes)
    command = [wrapper, str(executable), "-MorphBenchmark", "-windowed", "-ResX=1920", "-ResY=1080"]
    started = time.time_ns()
    process = subprocess.Popen(command, cwd=executable.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    status = 0
    try:
        output, _ = process.communicate(timeout=180)
        status = process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        status = 124
    VALIDATION.mkdir(parents=True, exist_ok=True)
    (VALIDATION / "performance.log").write_text(output or "", encoding="utf-8")
    if status:
        raise RuntimeError(f"Benchmark client exited {status}; see docs/validation/performance.log")
    reports = [path for path in (ROOT / "build" / "Linux").rglob("frame_times.json") if path.match("*/Saved/MorphRig/MorphBenchmark/frame_times.json")]
    if not reports:
        raise RuntimeError("The benchmark did not produce frame_times.json")
    source = max(reports, key=lambda path: path.stat().st_mtime_ns)
    if source.stat().st_mtime_ns < started:
        raise RuntimeError("The benchmark report is stale")
    report = json.loads(source.read_text(encoding="utf-8"))
    if report.get("resolution") != "1920x1080" or report.get("frame_generation") is not False:
        raise RuntimeError("Benchmark settings are not the required 1920x1080 without frame generation")
    for group in ("one", "ten"):
        sample = report.get("samples", {}).get(group, {})
        count = sample.get("frame_count", 0)
        if sample.get("warmup_seconds", 0) < 3 or sample.get("sample_seconds", 0) < 8 or count <= 60:
            raise RuntimeError(f"Incomplete warmed benchmark group: {group}")
        if len(sample.get("frames", [])) != count or sample.get("median_ms", 0) <= 0 or sample.get("average_ms", 0) <= 0:
            raise RuntimeError(f"Missing measured frame-time data: {group}")
        sample["median_fps"] = 1000.0 / sample["median_ms"]
        sample["p95_fps"] = 1000.0 / sample["p95_ms"]
        sample["peak_used_ram_gib"] = max(frame[4] for frame in sample["frames"]) / (1024 ** 3)
        sample["peak_reported_gpu_memory_gib"] = max(frame[5] for frame in sample["frames"]) / (1024 ** 3)
    for field in ("cpu", "gpu", "rhi", "ram_total_gib"):
        if not report.get(field):
            raise RuntimeError(f"Missing measured hardware field: {field}")
    report["measured_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["command"] = command
    report["process_exit_status"] = status
    report["gpu_isolation"] = {"query": query, "processes": processes, "isolated": not processes}
    report["host_environment"] = environment["host"]
    report["frame_columns"] = ["wall_frame_ms", "game_thread_ms", "render_thread_ms", "gpu_ms", "used_physical_bytes", "reported_gpu_memory_bytes"]
    report["frame_rate_limit"] = 0
    report["vsync"] = False
    (VALIDATION / "performance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(source), **{group: report["samples"][group] | {"frames": "preserved in performance.json"} for group in ("one", "ten")}}, indent=2))


if __name__ == "__main__":
    main()

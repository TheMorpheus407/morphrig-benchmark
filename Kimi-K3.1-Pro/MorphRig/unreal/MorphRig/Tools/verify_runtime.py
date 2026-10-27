#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT = ROOT.parent / "environment.json"
ARCHIVE = ROOT / "build" / "Linux"


def executable_from_archive() -> Path:
    candidates = [
        ARCHIVE / "Linux" / "MorphRig" / "Binaries" / "Linux" / "MorphRig",
        ARCHIVE / "MorphRig" / "Binaries" / "Linux" / "MorphRig",
        ARCHIVE / "Linux" / "MorphRig.sh",
        ARCHIVE / "MorphRig.sh",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if ARCHIVE.is_dir():
        for candidate in ARCHIVE.rglob("MorphRig"):
            if candidate.is_file() and candidate.parent.name == "Linux" and candidate.parent.parent.name == "Binaries":
                return candidate
    raise FileNotFoundError(f"No packaged MorphRig executable under {ARCHIVE}")


def report_from_archive() -> Path:
    if ARCHIVE.is_dir():
        reports = [p for p in ARCHIVE.rglob("results.json") if p.match("*/Saved/MorphRig/MorphVerify/results.json")]
        if reports:
            return max(reports, key=lambda p: p.stat().st_mtime_ns)
    raise FileNotFoundError("No Saved/MorphRig/MorphVerify/results.json report found")


def validate(path: Path) -> list[str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    clips = report.get("clip_results", [])
    ids = [entry.get("id") for entry in clips]
    if len(clips) != 96 or len(set(ids)) != 96:
        errors.append(f"Expected 96 unique sampled clips, found {len(clips)} entries/{len(set(ids))} IDs")
    for entry in clips:
        if not entry.get("loaded") or not entry.get("requested") or not entry.get("sampled"):
            errors.append(f"Clip failed load/request/sample: {entry.get('id')}")
    for check in report.get("checks", []):
        if not check.get("passed"):
            errors.append(f"Check failed: {check.get('name')} ({check.get('details', '')})")
    if not report.get("success"):
        errors.append("Native verification reported success=false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and validate the native MorphRig 96-clip verification")
    parser.add_argument("--executable", type=Path, help="Packaged executable to launch with -MorphVerify")
    parser.add_argument("--report", type=Path, help="Existing native results.json to validate")
    parser.add_argument("--no-launch", action="store_true", help="Only validate an existing report")
    args = parser.parse_args()

    report = args.report
    process_status = 0
    started_ns = time.time_ns()
    if not args.no_launch:
        executable = args.executable or executable_from_archive()
        environment = json.loads(ENVIRONMENT.read_text(encoding="utf-8"))
        wrapper = environment["unreal_engine"]["runtime_wrapper"].split()[0]
        process = subprocess.Popen([wrapper, str(executable), "-MorphVerify"], cwd=executable.parent, start_new_session=True)
        try:
            process_status = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process_status = 124
        if process_status != 0:
            print(f"Native verification process exited {process_status}", file=sys.stderr)
        if report is None:
            report = report_from_archive()
    if report is None:
        report = report_from_archive()

    errors = validate(report)
    if process_status != 0:
        errors.append(f"Native client exit status was {process_status}")
    if not args.no_launch and report.stat().st_mtime_ns < started_ns:
        errors.append("Native client did not produce a fresh results.json")
    if not json.loads(report.read_text(encoding="utf-8")).get("manifest_loaded"):
        errors.append("Runtime manifest did not load")
    print(f"Native report: {report}")
    if errors:
        for error in errors:
            print("FAIL:", error, file=sys.stderr)
        return 1
    print("PASS: 96 clips loaded/requested/sampled; all native checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

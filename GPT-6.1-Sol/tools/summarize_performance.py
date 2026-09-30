#!/usr/bin/env python3
"""Audit retained real one/ten-client samples and stamp their file identities."""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_MS = 1000 / 60


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    binary_hash = digest(ROOT / "build/Linux/MorphRig/Binaries/Linux/MorphRig")
    report = {
        "binary_sha256": binary_hash,
        "target_frame_ms": TARGET_MS,
        "evaluated_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "method": "Every measured native frame delta and game/render/GPU timing is retained. Percentiles use sorted index floor(N*p), matching the client. File identities refer to the delivered executable and retained CSVs.",
        "runs": {},
    }
    for count in (1, 10):
        stem = ROOT / "verification" / f"performance_{count}_instances"
        csv_path, json_path = stem.with_suffix(".csv"), stem.with_suffix(".json")
        sample = json.loads(json_path.read_text())
        rows = list(csv.DictReader(csv_path.open()))
        assert len(rows) == sample["frames"] > 100, f"Frame count mismatch: {csv_path}"
        assert sample["instances"] == count
        assert sample["width"] == 1920 and sample["height"] == 1080
        assert sample["warmup_seconds"] >= 5 and sample["sample_seconds"] >= 30
        assert sample["generated_frames"] is False and sample["vsync"] is False
        assert all(int(row["instances"]) == count for row in rows)
        metrics = {}
        for name in ("frame_ms", "game_ms", "render_ms", "gpu_ms"):
            values = sorted(float(row[name]) for row in rows)
            assert all(math.isfinite(v) and v > 0 for v in values), name
            metrics[name] = {
                "mean_ms": sum(values) / len(values),
                "p95_ms": values[min(len(values)-1, math.floor(len(values)*.95))],
                "p99_ms": values[min(len(values)-1, math.floor(len(values)*.99))],
                "max_ms": values[-1],
            }
        duration = sum(float(row["frame_ms"]) for row in rows) / 1000
        assert duration >= 30, f"Incomplete measured duration: {duration}"
        assert abs(sample["mean_ms"]-metrics["frame_ms"]["mean_ms"]) < .0001
        sample.update({
            "client_binary_sha256": binary_hash,
            "csv_sha256": digest(csv_path),
            "metrics": metrics,
            "frames_over_16_667_ms": sum(float(row["frame_ms"]) > TARGET_MS for row in rows),
            "sample_duration_seconds_from_frame_deltas": duration,
        })
        json_path.write_text(json.dumps(sample, indent=2)+"\n")
        report["runs"][str(count)] = sample
    report["summary"] = {"pass": all(
        run["metrics"]["frame_ms"]["mean_ms"] <= TARGET_MS
        and run["metrics"]["frame_ms"]["p99_ms"] <= TARGET_MS
        for run in report["runs"].values())}
    (ROOT / "verification/performance_validation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"binary_sha256": binary_hash, "summary": report["summary"],
                      "frame_mean_ms": {k: v["metrics"]["frame_ms"]["mean_ms"]
                                        for k, v in report["runs"].items()}}))
    if not report["summary"]["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

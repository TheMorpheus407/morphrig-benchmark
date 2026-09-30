# Standalone performance report

Both measured runs met the 60 FPS / 16.667 ms target at 1920×1080. The final
packaged Linux client averaged 1.858 ms with one animated Operative and
1.994 ms with ten. Their 99th-percentile frame times were
3.074 and 3.514 ms. No recorded frame exceeded 16.667 ms.

These are actual application measurements from 2026-09-30 Europe/Berlin,
using `build/Linux/MorphRig.sh` outside the editor. The measured executable's
SHA256 is
`8479393c16e8a6fe6dd3ffabca4a58ffaedf953967aba95c7eee395ec5a547e8`.
This is the same executable used for the final packaged terrain replays and
presentation recordings. Both individual summaries retain its identity and
the SHA256 of their per-frame CSV.

## Host and settings

The supplied NixOS reference host has an AMD Ryzen 9 9950X, 16 cores / 32
threads, and NVIDIA GeForce RTX 5090 with 32 GiB VRAM, driver 595.71.05.
Unreal's physical-memory API reports 92 GiB rounded upward; `environment.json`
records approximately 91 GiB. Runtime process memory was 1792 MiB for the
one-instance run and 1969 MiB for the ten-instance run.

Unreal Engine 5.8.3 used Vulkan SM6, native 1920×1080 and 100% screen
percentage. VSync, frame smoothing, the FPS cap and generated frames were
disabled. The neutral room uses ordinary raster lights/shadows, temporal AA,
and the authored materials, textures and LODs; Lumen GI/reflections and motion
blur are disabled. HUD, team identifiers and normal animation/event updates
were active. No other Unreal client, Blender render or presentation recording
ran during either measurement.

Each fresh client warmed for five seconds, then recorded at least 30 seconds.
The one-instance run retained 16,145 frames covering
30.0014 seconds; the ten-instance run retained
15,049 frames covering 30.0012 seconds. Inspection
screenshots were taken during warmup, before measured frames began.

The ten-instance toggle shares imported assets and displays idle, channel and
walk clips on nine additional independently ticking Operatives. The showcase
camera widens to include all ten and authored LOD selection remains automatic.
Consequently, these runs assess the delivered default inspection views; they
are not a fixed-camera scaling experiment with ten full-screen LOD0 meshes.

## Recorded times

All values below are milliseconds. Game, render and GPU timing overlap, so
their durations should not be added together.

| Instances | Metric | Mean | p95 | p99 |
|---|---|---:|---:|---:|
| 1 | Frame | 1.858 | 2.247 | 3.074 |
| 1 | Game thread | 0.653 | 0.881 | 1.158 |
| 1 | Render thread | 1.420 | 1.786 | 2.374 |
| 1 | GPU | 1.634 | 1.793 | 1.822 |
| 10 | Frame | 1.994 | 2.509 | 3.514 |
| 10 | Game thread | 0.975 | 1.278 | 1.568 |
| 10 | Render thread | 1.682 | 2.092 | 3.249 |
| 10 | GPU | 1.695 | 1.857 | 1.896 |

Maximum frame times were 10.606 ms and
12.686 ms respectively. Both means, p99 values and
these measured maxima met the target. This is a warmed sample on the supplied
host rather than a guarantee for every user interaction or different hardware.

Frame duration is the controller's actual frame delta. Game/render durations
come from `GGameThreadTime` / `GRenderThreadTime`; GPU duration comes from
`RHIGetGPUFrameCycles()`. CSV retains every recorded value. Percentiles use
the sorted sample at index `floor(N * percentile)`, matching the native
summary implementation. `tools/summarize_performance.py` independently checks
frame counts, duration and settings, recomputes the statistics and stamps
binary/CSV identities.

## Evidence and reproduction

The primary records are:

- `verification/performance_1_instances.csv` and `.json`
- `verification/performance_10_instances.csv` and `.json`
- `verification/performance_validation.json` with independently summarized
  per-metric statistics, sample durations, file identities and target comparison
- `verification/logs/performance_1_instances.log` and
  `verification/logs/performance_10_instances.log`
- `verification/performance_1_instances.png` and
  `verification/performance_10_instances.png`, showing the measured views

From this delivery folder, with other heavy workloads stopped:

```bash
./tools/build_linux.sh run -MorphPerf -MorphAutoExit
./tools/build_linux.sh run -MorphPerf10 -MorphPerf -MorphAutoExit
```

The runtime writes each run to
`unreal/Saved/User/Saved/Verification/performance_<count>_instances.csv`
and its JSON summary. These commands use the same installed-engine FHS
wrapper as the delivery launcher. Retain both pairs in `verification/`, then
run `python3 -B tools/summarize_performance.py` to reproduce the audit and
identity fields. F10 toggles one/ten characters interactively; F11 records
the same five-second warmup and 30-second sample at the current instance count.

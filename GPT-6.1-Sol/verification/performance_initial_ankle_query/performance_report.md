# Standalone performance report

Both measured runs met the 60 FPS / 16.667 ms target at 1920×1080. The final
packaged Linux client averaged 4.294 ms with one animated Operative and
4.047 ms with ten. Their 99th-percentile frame times were 8.413 and 10.850 ms.

These are actual application measurements from 2026-09-30 Europe/Berlin,
using `build/Linux/MorphRig.sh` outside the editor. The measured executable's
SHA256 is
`85f61c48e21e244ac0a4e92bd179fdb1efa481d1d7228c03232857e9333e3263`.

## Host and settings

The supplied NixOS reference host has an AMD Ryzen 9 9950X, 16 cores / 32
threads, and NVIDIA GeForce RTX 5090 with 32 GiB VRAM, driver 595.71.05.
Unreal's physical-memory API reports 92 GiB rounded upward; `environment.json`
records approximately 91 GiB. Runtime process memory was 1,727 MiB for the
one-instance run and 1,700 MiB for the ten-instance run.

Unreal Engine 5.8.3 used Vulkan SM6, native 1920×1080 and 100% screen
percentage. VSync, frame smoothing, the FPS cap and generated frames were
disabled. The neutral room uses ordinary raster lights/shadows, temporal AA,
and the authored materials, textures and LODs; Lumen GI/reflections and motion
blur are disabled. HUD, team identifiers and normal animation/event updates
were active. No other Unreal client, Blender render or presentation recording
ran during either measurement.

Each fresh client warmed for five seconds, then recorded at least 30 seconds.
The one-instance run retained 6,987 frames covering 30.003 seconds; the
ten-instance run retained 7,415 frames covering 30.006 seconds. Inspection
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
| 1 | Frame | 4.294 | 6.686 | 8.413 |
| 1 | Game thread | 1.758 | 3.159 | 4.388 |
| 1 | Render thread | 3.979 | 6.088 | 7.721 |
| 1 | GPU | 1.672 | 1.831 | 1.902 |
| 10 | Frame | 4.047 | 7.568 | 10.850 |
| 10 | Game thread | 2.036 | 4.028 | 6.097 |
| 10 | Render thread | 3.799 | 7.009 | 9.920 |
| 10 | GPU | 1.733 | 1.892 | 1.937 |

Each sample contained five frames above 16.667 ms. Maximum frame times were
26.240 ms and 32.696 ms respectively. Both means and p99 values meet the
target; the logs retain these occasional longer frames.

Frame duration is the controller's actual frame delta. Game/render durations
come from `GGameThreadTime` / `GRenderThreadTime`; GPU duration comes from
`RHIGetGPUFrameCycles()`. CSV retains every recorded value. Percentiles use
the sorted sample at index `floor(N * percentile)`, matching the native
summary implementation.

## Evidence and reproduction

The primary records are:

- `verification/performance_1_instances.csv` and `.json`
- `verification/performance_10_instances.csv` and `.json`
- `verification/performance_validation.json` with independently summarized
  per-metric statistics, sample durations and target comparison
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
wrapper as the delivery launcher. F10 toggles one/ten characters interactively;
F11 records the same five-second warmup and 30-second sample at the current
instance count.

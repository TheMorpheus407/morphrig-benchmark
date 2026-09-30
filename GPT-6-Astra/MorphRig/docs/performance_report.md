# Measured packaged-client performance

The standalone Linux client runs for 45 seconds per view; the first 10 seconds are discarded. These are actual wall-clock frame deltas, without screenshot capture, a fixed time step or generated frames. This project’s render, import and build workers are idle during measurement. Other desktop processes are recorded in the GPU snapshots.

Host: AMD Ryzen 9 9950X (16 cores / 32 threads), 91 GiB RAM, NVIDIA RTX 5090 (32 GiB), driver 595.71.05, NixOS x86-64.

Settings: windowed 1920×1080, Vulkan SM6, native 100% resolution, TAA, visible UI, automatic LOD, VSync off and no FPS cap. Default showcase lighting; Lumen, Nanite and virtual shadow maps disabled. Full renderer and scalability settings are retained in the [configuration snapshots](validation/performance/).

| Instances | Resolution | Samples | Mean ms | p95 ms | p99 ms | Effective FPS |
|---|---|---:|---:|---:|---:|---:|
| 1 | 1920x1080 | 21971 | 1.593 | 3.447 | 4.564 | 627.7 |
| 10 | 1920x1080 | 20255 | 1.728 | 2.749 | 4.028 | 578.7 |

The ten-actor view uses a wider camera and automatic lower LODs. The comparison includes the effects of screen coverage and LOD selection. These results measure the delivered views rather than a controlled same-LOD scaling benchmark.

1 actor(s): hero rendered LOD [0]; 100.000% of warmed frames meet the 16.67 ms / 60 FPS target; slowest recorded frame 14.635 ms. [Raw CSV](validation/performance/1_actors/frames_1_actors.csv).

10 actor(s): hero rendered LOD [1]; 100.000% of warmed frames meet the 16.67 ms / 60 FPS target; slowest recorded frame 12.374 ms. [Raw CSV](validation/performance/10_actors/frames_10_actors.csv).

[Machine-readable report](performance_report.json) includes all percentiles and evidence paths. Results apply to this reference host and recorded configuration.

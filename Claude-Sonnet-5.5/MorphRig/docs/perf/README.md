# Frame time logs

Two logs of the packaged Linux client (`build/Linux`, Development configuration) at 1920 x 1080, windowed, VSync off, no frame generation, temporal super resolution at 100 percent:

| Log | Scene | Command |
|---|---|---|
| `perf_1_instance.csv` (+ `.summary.txt`) | one animated Operative | `tools/ue_run_packaged.sh -PerfLog=docs/perf/perf_1_instance.csv -Instances=1 -ExitAfterPerf` |
| `perf_10_instances.csv` (+ `.summary.txt`) | ten animated Operatives | `tools/ue_run_packaged.sh -PerfLog=docs/perf/perf_10_instances.csv -Instances=10 -ExitAfterPerf` |

Every instance runs the autopilot loop (`OperativeAutopilot.cpp`: walking at 150 cm/s, running at 400 cm/s, single shot, burst, melee, ground cast, self cast, channel, hit reaction, dash, jump, reload, greeting), the camera is the third person view, materials are textured, LOD is automatic, overlays are off. The room is the showcase room with one directional key light with virtual shadow maps, two unshadowed directional lights and a sky light, no Lumen and no ray tracing. The sample starts after 240 frames and 5 s of warm-up and lasts 20 s of wall clock time.

## Result

| | 1 Operative | 10 Operatives |
|---|---|---|
| frames sampled | 10,034 | 7,669 |
| frame time average / p50 / p95 / p99 / max (ms) | 1.99 / 1.91 / 2.54 / 3.52 / 11.39 | 2.61 / 2.46 / 3.00 / 10.74 / 11.65 |
| average frame rate | 502 FPS | 383 FPS |
| 1 percent low (from the p99 frame time) | 284 FPS | 93 FPS |
| game thread average / p99 (ms) | 0.99 / 1.75 | 1.26 / 2.07 |
| render thread average / p99 (ms) | 1.33 / 2.58 | 1.56 / 10.29 |
| GPU average / p99 (ms) | 1.76 / 1.97 | 2.29 / 2.60 |

The target of 60 FPS (16.67 ms per frame) is met with a wide margin in both scenes: the slowest frame of either log takes 11.7 ms. The GPU needs 2.3 ms for ten characters and makes up about 88 percent of the average frame time; the game thread and the render thread each need less than 1.6 ms on average.

About 1 percent of the frames in the ten instance log (0.2 percent with one instance) take 10 to 12 ms although the game thread and the GPU need less than 3 ms in the same frames; the render thread column shows the same 10 to 12 ms in those frames. The cause was not investigated (virtual shadow map page updates and the present under the desktop compositor are candidates). All of them stay below the frame budget.

## Hardware, settings and host state

The hardware, the console variables and the host load average at the start and at the end of the sample are written into each `.summary.txt`. Reference host: AMD Ryzen 9 9950X (16 cores, 32 threads), 91.9 GiB RAM, NVIDIA GeForce RTX 5090 (driver 595.71), Vulkan, NixOS 26.05. The host is shared with other jobs. A load average above the 32 hardware threads adds waiting time to the game and render thread columns: an earlier run of the ten instance scene at a load average of about 30 needed 7.1 ms on the game thread instead of 1.3 ms, while the GPU column moved by only 10 percent (2.5 ms instead of 2.3 ms). The logs in this folder were taken at a load average between 4.5 and 5.0.

## Columns of the CSV

`frame`, `wall_s` (seconds since the start of the sample), `frame_ms` (wall clock time between two frames), `game_thread_ms`, `render_thread_ms`, `gpu_ms` (the engine's own timers, which lag the frame by one or two frames), `draw_calls`, `primitives`.

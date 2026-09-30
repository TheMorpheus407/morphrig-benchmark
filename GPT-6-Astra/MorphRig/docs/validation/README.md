# Validation evidence

The authoritative deliverables are mapped in [the project README](../../README.md). Reports below state their individual scope; a file-inventory pass is not a visual-quality test.

| Evidence | What it checks |
|---|---|
| [Source review](source_final_summary.md) | Actual Blender mesh, rig, action inventory, contacts and edit/rebake proof |
| [Independent acceptance review](acceptance_review.md) | Rendered deformation, hands, face, LODs and remaining limitations |
| [Unreal import](../unreal_import_validation.json) | Actual native assets for all 96 required entries |
| [Source/native pose comparison](../unreal_source_pose_comparison.json) | Compressed native bone transforms against Blender |
| [Native mesh report](../unreal_native_mesh_report.json) | Imported bones, LODs, sections and morph delta buffers |
| [Interactive stasis/death test](scroll_stasis_escape/state_event_trace.log) | Real mouse/keyboard input, death priority and clean Escape shutdown |
| [Presentation inspection](media_review.json) | Decoded media format and visual review |
| [Speech audio alignment](face_audio_sync_validation.json) | Decoded video audio compared with original WAV |
| [Final native motion and terrain review](runtime_motion_visual_review.md) | Corrected packaged mesh, manipulation, recovery, ramp and stair samples |
| [Final inspection controls](runtime_final_controls/input_record.json) | Final focused keyboard checks for skeleton, cameras, team accents, LODs and the ten-instance toggle; input record states the exact scope |
| [Beacon transfer](beacon_release_fixed/report.json) | Explicit centimeter/bone-local transfer, two materials, visible release and persistence |
| [Final demonstration trace](runtime_delivery_demo/trace_audit.json) | Combined states and once-only event crossings from the final packaged capture |
| [Measured runtime performance](../performance_report.md) | Normal wall-clock 1080p samples after a 10-second warmup, one and ten actors |
| [Final artifact record](final_delivery.json) | Hashes for final sources, mesh/prop exports, packaged executable and all three videos |
| [Delivery inventory](delivery_audit.json) | Required paths, 96 exported FBXs, speech metadata and playable videos |

`acceptance_before_contact_fix`, the initial `runtime_motion` frames, `runtime_final_demo`, `runtime_uinput`, `runtime_controls`, and the earlier `native_terrain_*` folders retain diagnostic evidence from development. `linear_skin` records the source-side correction that preceded the final native import. Some contain the defects that prompted later corrections; use the revision descriptions in the acceptance review to identify current results. A capture run uses a fixed 30 FPS clock and must never be used as a performance measurement. Normal wall-clock samples live under `performance/`.

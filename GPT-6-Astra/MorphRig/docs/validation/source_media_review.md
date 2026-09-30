Both presentation videos were regenerated from the final source SHA-256 `643750f8d297ed65586bc3be82bdc244b9cd3cd80aa84f69edacd04e1a43f980`, including the corrected linear skinning, shoulder cuffs, wrist weights, squint clearance and cell casing. The renderer read the saved source without modifying it. Every expected input frame existed and was newer than the source before encoding. [Encoding and stream validation](source_media_final.json) passes.

| Video | Verified delivery | Visual evidence |
|---|---|---|
| [Turntable](../../presentation/turntable.mp4) | 1920×1080, 30 FPS, 240 frames, 8.0 seconds; H.264 CRF18 | [Four angles from encoded video](turntable_video_contact_sheet.png) |
| [Face performance](../../presentation/face_performance.mp4) | 1920×1080, 30 FPS, 420 frames, 14.0 seconds; H.264 CRF18 and AAC audio, padded to 14.0 seconds | [Vowels, closure and emotional transition from encoded video](face_video_contact_sheet.png) |

The sampled turntable angles retain the whole character and show continuous shoulders, mechanical elbow and wrists. The face samples show an open vowel, closed bilabial lips, a focused glance and a confident open expression; no exposed iris crescents or crossing lips are visible in these samples. These checks inspect actual decoded MP4 frames rather than relying only on the source render directory.

The encoded dialogue audio also matches the supplied WAV at 0 measured sample lag after AAC decoding (normalized correlation 0.99995576; [audio check](face_audio_sync_validation.json)).

This is a sampled visual check plus complete frame-count/stream validation. The source numerical contact and deformation checks are recorded in [source_final_summary.md](source_final_summary.md). Native state transitions, camera coverage and runtime deformation require the separate final-package review in [runtime_motion_visual_review.md](runtime_motion_visual_review.md).

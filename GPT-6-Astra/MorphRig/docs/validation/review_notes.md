# Independent review log

This file tracks intermediate findings. Acceptance is established by the final reports and captures, not by a generator's completion message.

## First source and motion pass

- Initial source opened in Blender 5.1.1, with packed/relative textures and no linked libraries. All character vertices had weights, with at most two influences. Three genuinely reduced LOD meshes were present, each with eight material slots.
- The first character preview failed facial inspection: all shape targets had accumulated active values. A later neutral preview corrected the protruding mouth, with further eye/lip topology seam cleanup requested.
- First action library contained all 96 named entries and editable source variants. Sampled loop endpoints matched. Independent evaluated matrices detected incorrectly oriented root translations for dashes and a duplicate knockdown/death trajectory. Both were sent for correction.
- Rendered run/walk/reload frames exposed detached foot/hand chains. The animation author traced this to stale parent transforms while setting child matrices, and replaced the solver with explicit parent-relative basis transforms. The corrected library requires a fresh independent all-frame continuity audit.
- Source audit scripts are `tools/inspect_source.py` and `tools/measure_motion_contacts.py`. The latter compares every sampled parent tail to child head across all eight limb connections and measures selected actual skinned sole heights.
- Runtime source review found and requested fixes for double blink teleport, death-to-held-pose transitions, respawn priority, exit-pose fading, stasis audio pause, aim during upper-body attacks and mismatched expression morph names. Actual packaged execution is required to verify those fixes.
- Audio WAV: 13.932789 s, mono 22050 Hz signed PCM16, no clipped samples. All native phoneme events fall within the waveform. Seven speech viseme groups are present.

Intermediate images in this directory may depict superseded defects. Final presentation files and final validation reports must be generated from the corrected source/project.

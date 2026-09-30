# Production record

All character geometry, rigs, animation curves, materials and showcase code are authored for this assignment using the exposed GPT-6-Astra session and same-model delegated workers. No stock character, downloaded skeletal animation, remote generative service or purchased asset is used. Character, animation and Unreal tasks run in parallel with distinct file ownership.

The latest task explicitly assigns this benchmark to the exposed system, superseding older general video-production routing suggestions. All authored work, render output and delivery files reside below the supplied task folder. Installed applications and their prepared NixOS wrappers are reused.

Blender is the authoritative editable source. Its chosen coordinate convention is meters, Z up, negative Y forward; the left side is positive X. The intended standing height is 1.80 m. Unreal uses centimeters. Scale, hierarchy and actual imported dimensions are checked in validation output.

Dialogue uses eSpeak NG 1.52.0.1 with the built-in en-us+f3 formant voice at 140 words/minute. Original text and synthesis audio are delivered. Timing comes from the same synthesis callback that emits the PCM audio, including a common 0.300 s lead. The waveform lasts 13.933 seconds. Speech implementation follows the [official eSpeak NG callback API](https://github.com/espeak-ng/espeak-ng/blob/master/src/include/espeak-ng/speak_lib.h). The generator and its observations are preserved.

Completion is assessed from real exported files, actual Unreal imports, runtime output and visual review. Intermediate files and named entries alone do not establish animation quality or acceptance.

# MORPHRIG — Known Engineering Trade-Offs & Limitations

Per `SPEC.md` §§2, 9, and 12, this document records honest engineering trade-offs and known boundaries in the delivered asset and showcase controller:

1. **Zero-Delta Neutral Shape Key Stripping on FBX Import (`46` Blender Keys → `45` Unreal Morph Targets)**:
   - `Operative_LOD0` in `source/Operative.blend` defines 46 named shape keys (plus `Basis`), including the neutral silent rest key `V_SIL` (`0.0` vertex displacement everywhere so speech alignment curves can explicitly keyframe rest intervals).
   - Unreal Engine 5.8's `UFbxFactory` strips morph targets whose maximum vertex delta is `0.0`, resulting in **45** active `UMorphTarget`s on `/Game/MorphRig/Character/Operative`. All 12 non-silent visemes (`V_MBP`..`V_ER`), all 21 asymmetric/oral facial controls, all 6 emotional presets, and all 6 joint correctives import and evaluate identically; `V_SIL` naturally corresponds to zero weight across active speech morphs.
2. **LOD1 & LOD2 Morph Target Policy**:
   - Full 45-target facial morph evaluation runs on `LOD0` (close-up and mid-range gameplay). `LOD1` (`0.45` screen size, `15,218` tris) and `LOD2` (`0.20` screen size, `7,608` tris) rely on the 92-bone skeletal deformation (including jaw, head, neck, and eye bones) without per-vertex facial morph deltas, saving vertex-shader bandwidth in 10-operative and top-down views where facial pore/lip detail subtends only a few pixels.
3. **Offline Deterministic Voice Synthesis (`eSpeak NG` + Formant Filtering)**:
   - Spoken audio (`source/audio/dialogue.wav`, `16.48s`, 48 kHz 16-bit mono) is synthesized locally via `libespeak-ng` (`en-us+f3`) with studio EQ/compression so that exact synchronous phoneme-to-sample timestamps (`dialogue_alignment.json`) are generated deterministically offline without cloud APIs or restricted commercial voice clones. Timbre has a crisp synthetic cybernetic-operative character rather than a studio human actor recording.
4. **Action Play-Rate Envelope (`0.5x – 1.5x`)**:
   - The animation state machine, phase-synced 8-direction gait blender, and bitmask-deduplicated event tracker are verified across the specified `0.5x` to `1.5x` play-rate range. Extreme unbounded play rates (`< 0.1x` or `> 4.0x`) are clamped to `[0.5, 1.5]` in interactive controls so capsule physics and analytical foot IK remain stable.
5. **Runtime Analytical IK & Spring Scope**:
   - Ground adaptation uses deterministic two-bone analytical leg IK + pelvis height adaptation tuned for slopes up to `20°` and step deltas up to `20 cm`. Extreme vertical cliff overhangs (`> 45 cm` split-leg drop) clamp cleanly to maximum leg reach rather than stretching limb bone lengths.
   - Neural dorsal cable (`cable_01..03`) and hip utility strap (`strap_01..03`) secondary motion uses bounded critically-damped angular springs (`±0.32 rad`) rather than full cloth/rigid-body collision chains, preventing jitter or runaway simulation during teleports (`blink_out`/`blink_in`) and 10-instance crowd spawns.

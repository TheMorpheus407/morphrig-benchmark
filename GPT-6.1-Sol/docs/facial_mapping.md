# Facial controls and speech mapping

The editable controls are properties on `Operative_Rig` → `CTRL_face`.
The source uses a dot before an anatomical side (`blink.L`); exported morph
names and the Unreal control panel use an underscore (`blink_L`). `L` is the
Operative's own left. Anatomical sliders and viseme sliders range from 0 to 1.
Eye angles in Blender are radians: positive yaw looks to character right
(+X), positive pitch looks up (+Z), from forward −Y. The runtime panel
normalizes its eye slider range; its implementation maps that range to eye
angles. Left and right eyes and eyelids remain individually controllable.

| Controls | Function and exported deformation |
|---|---|
| `eye_yaw.L/R`, `eye_pitch.L/R` | Separate eye-bone yaw and pitch; eyelid pitch follows gaze. |
| `blink.L/R`, `squint.L/R` | Independent upper/lower lid closure and tightening. |
| `brow_raise.L/R`, `brow_lower.L/R` | Independent vertical eyebrow response. |
| `cheek.L/R` | Separate cheek lift/forward response. |
| `jaw` | Skeletal jaw hinge; lower teeth and tongue follow the jaw. |
| `lip_close` | Upper/lower lip seal, including compensation for jaw motion. |
| `smile.L/R`, `frown.L/R` | Independent mouth-corner rise and fall. |
| `width` | Lateral mouth widening. |
| `pucker`, `funnel` | Lip protrusion/narrowing and rounded opening. |
| `tongue` | Tongue lift/forward placement toward teeth. |

Neutral and six presets are authored in `motions.expression_presets`:
`joy_confidence`, `anger`, `concern_sadness`, `surprise`, `pain`, and `focus`.
The presets use asymmetric brow, cheek and mouth-corner values. Neutral is
all sliders zero and closed lips. Their control values can be edited or
combined with the phoneme shapes.

| Viseme control | Relevant eSpeak phonemes | Anatomical intent |
|---|---|---|
| `viseme_closure` | p, b, m | Both lips seal; jaw opening is suppressed. |
| `viseme_labiodental` | f, v | Lower lip approaches upper teeth with a small jaw opening. |
| `viseme_open` | a, A, V, @, 3 and their stressed/long variants | Open vowel with jaw drop and relaxed width. |
| `viseme_wide` | i, I, e, E, eI, aI, j and variants | Widened mouth with moderate jaw opening. |
| `viseme_round` | w, u, U, o, O, oU, aU, OI and variants | Rounded lips, protrusion and a moderate aperture. |
| `viseme_tongue` | T, D, l, n, t, d, N | Tongue-to-teeth/alveolar response. |
| `viseme_consonant` | s, z, h, r, k, g and remaining consonants | Small articulated aperture between vowel shapes. |

Stress marks and separators are removed before classification; `_`, `_:`,
and equivalent native pauses produce silence. `speech.classify()` is the
complete mapping, including eSpeak's `@2`, `@L`, `I#`, and `O2` variants.
Viseme controls also drive the anatomical bones directly, so an isolated
viseme in the control panel works independently. The spoken action keys
both viseme values and anatomical values; rig composition uses maximum
contributions to avoid doubling the jaw opening.

`source/audio/dialogue.wav` contains the original 13.566667-second English
performance, mono 16-bit PCM at 22,050 Hz. The accompanying transcript and
`dialogue_alignment.json` contain the actual audio SHA-256, native word and
phoneme spans, and performance cues. Alignment comes from eSpeak NG's
`espeakEVENT_WORD` and `espeakEVENT_PHONEME` `audio_position` callbacks during
the exact synchronous synthesis that creates this WAV. The voice is the
built-in generic English synthetic voice. No voice model or person's
recording is used.

Speech is authored at 30 FPS with 408 inclusive samples. A 45 ms anticipatory
and 35 ms release envelope blends adjacent phonemes. Bilabial seals include
the adjacent source sample when a /b/ or /p/ stop is shorter than one frame.
The actual mouth closes on /p b m/; lip width, lip rounding, labiodental
contact and tongue shapes remain distinct from jaw motion.

The performance begins concerned, scans left, inspects the cybernetic wrist
at the spoken “relay,” points toward the crossing with the organic hand,
re-centers on “Breathe,” and changes to a confident asymmetric smile on
“signal” at 8.621 seconds. An open hand invites forward movement on
“together” at 10.454 seconds. Left/right blink offsets and gaze convergence
are authored independently. Native audio spans drive lips; the longer hand
gestures and emotional shift follow the same word timestamps.

Regenerate the audio and alignment with the installed local dependency:

```bash
nix-shell -p espeak-ng --run 'python3 source/generators/speech.py'
python3 -B source/generators/motions.py
```

Rebuild the editable actions and baked exports after changing dialogue or
facial curves, following `build_and_import_instructions.md`. The audio
generator discovers the active eSpeak installation dynamically. The
delivered character does not require speech synthesis at runtime.

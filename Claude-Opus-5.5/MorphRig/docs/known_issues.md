# Known issues and limits

Everything below was observed in the delivered files (Blender motion QA `docs/qa/motion_qa.json`, renders of
the flagged frames, Unreal runs of the editor and the packaged client). Values are the worst frame per clip.

## Motion / contacts
| Clip | Frame | Issue | Size |
|---|---|---|---|
| `deploy` | 8 | left hand closes on the beacon at the back of the belt; the fingers pass into the beacon clip / pouch geometry while gripping | up to 5.0 cm |
| `knockdown_back` | 18 | mid-fall, the left hand grazes the left hip | 1.8 cm |
| `death_front` | 36 | mid-fall, the left hand grazes the hip | 1.7 cm |
| idle / locomotion / `dialogue` / face-control poses | various | left forearm or bracer touches the belt charger (front left) | ≤ 0.45 cm |
| `knockdown_back`, `prone_back`, `getup_back` | lying frames | boot heel slightly below the floor while lying on the back | ≤ 1.3 cm |
| `death_front` / `dead_front`, `respawn`, `jump_start` | contact frames | boot heel / toe slightly below the floor | ≤ 0.9 cm |
| `sleep_start`, `getup_front` | 46 / 6 | belt pouch touches the floor while kneeling / pushing up | ≤ 1.3 cm |

No clip has foot sliding above 0.5 cm on planted feet (`start_f` was fixed: its steps now land at the walk
width, so the hand-over to `walk_f` needs no foot shift). The largest loop seam (first vs last frame, max over bones of
rotation in degrees or translation in cm) is 0.15 (`run_br`).

## Deformation
* Extreme wrist flexion (beyond the gameplay range; visible in `demo_deformation`) makes the sleeve cuff flare
  slightly at the wrist.
* Teeth read somewhat grey in the close-up because the lips shadow the mouth interior; the texture itself is
  off-white.

## Unreal runtime
* Performance: averages are far above the 60 FPS target (255 FPS with 1, 144 FPS with 10 operatives at
  1920×1080), but 0.4–1.0 % of frames exceed 16.7 ms. They come as short render-thread stalls in ~10 ms
  steps every few seconds (game thread and GPU stay normal). Removing Lumen reduced but did not reliably
  remove them, and they also appear in fullscreen mode. The source is not identified; run-to-run variance on
  the (not isolated) desktop host was large (one run had none in 11,579 frames).
* Lighting deliberately uses no dynamic GI (Lumen off): key light with shadows and a shadowless fill that
  follow the view direction, plus a sky light. This is a neutral inspection setup, not a final-game lighting
  setup; shadows therefore change direction when the camera cuts.
* Knockback travel is driven by the controller (capsule launch), not baked into the clip; dash is the only
  root-motion clip.
* The hair tail's secondary motion is simulated in Blender and baked per clip; there is no runtime physics.
  The skeletal mesh has no physics asset (no ragdoll; capsule collision only).
* The pose markers are Unreal notifies that the controller dispatches itself; the engine's own notify
  dispatch is not used.

## Pipeline
* `tools/export_and_bake.py --only <ids> --from anims` rebuilds only those clips inside the existing
  `source/Operative.blend`; a run from `rig` or earlier rebuilds every clip.
* The dialogue voice is local Piper TTS (synthetic prosody); the lip sync follows the phoneme timing that
  Piper/eSpeak report.

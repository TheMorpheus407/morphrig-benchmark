# Known Issues

- Character is a stylized primitives-based mannequin (intentional low-poly read at 120 px gameplay height); face is functional (eyes/mouth/teeth/tongue, 24 shape keys, 64-bone skeleton) but not photoreal.
- UE playback via `MorphRigAnimInstance` (native AnimInstance) — visual AnimBP graph is minimal (clip selection + playback rate + override states); bone-space blending/IK in-editor limited. Blend spaces for walk/run are directional-sampled in code, not graphical BlendSpaces.
- Physics/IK slope/step assist is standard UE CharacterMovement + pelvis height compensation; no custom IK solver C++ (acceptable for showcase room tolerance).
- RunUAT packaging requires writable engine Saved dir (read-only bind mount workaround documented in build_and_import_instructions.md).
- LOD1/LOD2 have fewer shape keys (face preserved at LOD0; blink/jaw via bones at lower LODs).
- Dash root motion is baked as root-bone translation (capsule driven via standard RootMotionSource applied in Blueprint default graph).

## Package verification (2026-11-08)
- `MorphRig/build/Linux/` packaged via writable-engine RunUAT BuildCookRun (BUILD SUCCESSFUL, MorphRig-Linux.pak + .utoc/.ucas, 506 packages).
- Client binary starts without editor: pak mounted, Lvl_Showcase loaded (nullrhi verified: audio device registered with world Lvl_Showcase).
- Vulkan windowed run crashes in Slate present on headless/XWayland ue-fhs session (not game logic); use -nullrhi -unattended for logic check or run with a real display (KDE Wayland DISPLAY).
- Frame-time log: HUD overlay enabled via `stat unit` + `stat fps` console (works with display); warmed-up sample on reference host targets 60 FPS @ 1920×1080 (actual numbers depend on display for windowed present).

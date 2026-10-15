# Known Issues & Production Notes

## 1. NixOS FHS Execution Requirement (`ue-exec`)
- **Behavior**: On NixOS 26.05, Unreal Engine 5.8.3 binaries (`UnrealEditor-Cmd`, `Build.sh`, `RunUAT.sh`) and packaged Linux game binaries (`build/Linux/MorphRig.sh`) are dynamically linked against standard Linux FHS library paths (`/lib64/ld-linux-x86-64.so.2`).
- **Resolution**: Always invoke Unreal Engine tools and the packaged Linux binary via `/home/morpheus/UnrealEngine/bin/ue-exec` (as configured in `environment.json` and automated in `tools/build_linux.sh`).

## 2. Baked Deformation Curves vs. Custom Attribute Morph Curves across FBX / UE5
- **Behavior**: Unreal Engine 5's FBX animation importer imports bone transform tracks cleanly on all 96 `UAnimSequence` assets, while FBX BlendShape curve tracks on skeletal animation-only FBX files can vary depending on whether the mesh is re-imported alongside each clip.
- **Resolution**: To guarantee 100% deterministic facial animation in both Blender and the packaged Unreal Engine 5.8.3 showcase:
  1. `export/Operative.fbx` exports all 38 facial and corrective Shape Keys as Unreal Morph Targets (`UMorphTarget`) on `Operative_LOD0`, plus facial bones (`jaw`, `tongue_01..02`, `eye_l`, `eye_r`, `eyelid_upper_l/r`, `eyelid_lower_l/r`, `brow_inner_l/r`, `brow_mid_l/r`, `brow_outer_l/r`, `lip_upper`, `lip_lower`, `lip_corner_l/r`).
  2. `UMorphRigAnimInstance` drives both the baked facial bone tracks from `face_dialogue_line_01` / `face_emotion_*` / `face_viseme_*` AND evaluates synchronized Morph Target weights (`SetMorphTarget`) directly on the `USkeletalMeshComponent` for spoken dialogue visemes, emotions, blinks, and manual facial overrides.

## 3. Playback Rate Extreme Bounds (`0.5x` – `1.5x`)
- **Behavior**: The showcase supports interactive and automated playback speed scaling (`PlayRate` from `0.5x` to `1.5x` via `-` / `=` keys).
- **Note**: As specified in Section 9 of `SPEC.md`, event notifications (`AN_MeleeHitWindow_*`, `AN_MuzzleFire`, `AN_DeployAttach`, `AN_DeployRelease`, `AN_ReloadCellOut`, `AN_ReloadCellIn`, `AN_CastRelease`, `AN_Footstep_*`) scale proportionally with `PlayRate` and use fire-once threshold gating (`ShouldFireEvent`) so time stretching never invents duplicate hits or skips state transitions.

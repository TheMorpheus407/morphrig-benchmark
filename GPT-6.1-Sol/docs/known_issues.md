# Known issues and integration limits

The Operative is an original stylized character made from editable procedural
mesh data and authored control curves. The face, hands and organic limb
surfaces retain visible stylization in close inspection.

The spoken performance uses the generic local eSpeak NG voice. Its original
WAV and native phoneme alignment are delivered; the synthetic voice quality
is separate from the authored facial and body performance.

The Unreal facial slider panel selects LOD0, which carries the complete set
of anatomical morph targets. LOD1 and LOD2 retain the facial deformation
bones and play the baked speech performance. Use the full-body views to
inspect those reduced LODs.

Blender disables embedded Python when opening an untrusted file. Run the
delivered `Operative_Animator_Panel.py` text once to enable the reset and
matched IK/FK sidebar. Geometry, packed textures, existing source actions and
baked actions are available immediately without running that panel.

Floor-contact validation allows up to 1 cm of pressure at a contact surface.
The corrected source inventory's largest measured contact penetration is
6.34 mm at the deploy fingertips; the corrected landing and lying poses stay
within 2.61 mm. Exact values and sampled frames are retained in
`verification/qa_motion_floor_validation.json`.

The final packaged ramp and step replays sample all 1,938 imported LOD0
boot vertices after bone evaluation. Both tested paths retain at least 1 mm
of surface clearance, with no sampled solid-step pressure. Maximum planted
clearance is 9.43 mm and maximum measured horizontal support drift is
5.20 mm. These measurements cover the documented straight traversal and
stop/recovery tests; the raw samples, contact phases and acceptance criteria
are retained in `verification/terrain_validation.json` and the two independent
`verification/qa_runtime_*_validation.json` reports.

The delivered standalone target is Linux x86-64. The character assets and
native Engine-based controller are portable; a Windows executable has not
been built or tested. The NixOS wrapper is a host build/run dependency and
is documented in `environment.json`.

Motion editing remains in the Blender controls. After changing a source
action, rebake that ID, reimport its FBX, and cook a new package. An existing
Linux package contains the assets from its recorded build, rather than live
links to the editable `.blend`.

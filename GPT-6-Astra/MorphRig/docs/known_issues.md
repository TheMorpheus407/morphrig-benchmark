# Remaining limitations and verification scope

The final acceptance status and measured runtime results are recorded in the validation index and performance report. Earlier diagnostic screenshots and reports are retained with their revision context; they include defects that were subsequently corrected.

The spoken line uses a local eSpeak formant voice and intentionally sounds synthetic. No recorded or cloned voice is included.

The source and runtime use the same authored meshes, textures, skeletal actions and facial targets. Source presentation videos use Blender EEVEE; the motion overview uses the packaged Unreal renderer. Lighting differs between these renderers. The final Blender skinning setup uses linear deformation to match Unreal.

The motion inventory is checked across all 96 source actions and actual imported assets. Every-frame source probes check skeletal continuity; dense whole-mesh floor/contact scans cover the 14 affected floor and prop clips. Runtime visual review and event tests cover the documented demonstrations and interactive controls. These checks do not exhaust every possible combination of controls or every custom edit to the rig.

Performance results apply to the supplied Ryzen 9950X / RTX 5090 reference host and the recorded 1920×1080 showcase settings. Video-capture frame timing is excluded from performance evidence.

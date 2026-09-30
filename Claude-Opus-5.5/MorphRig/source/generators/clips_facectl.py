"""Extra (non-inventory) single-frame control poses for the bone-driven face controls.

Frame 0 is the neutral pose, frame 1 applies one control at full strength.  Unreal imports them
as additive (base = frame 0) and blends them with the face-panel / look-at weights, so eyelids,
jaw, tongue and gaze behave exactly like the Blender rig drivers (lids follow gaze pitch, etc.).
Shape-key controls are morph targets and are driven directly in Unreal."""
from mr_clip import Clip
from mr_anim import merge
import mr_poses as P
from clips_common import clip

CONTROLS = {
    "ctl_blink_l": {"face": {"blink_L": 1.0}},
    "ctl_blink_r": {"face": {"blink_R": 1.0}},
    "ctl_wide_l": {"face": {"wide_L": 1.0}},
    "ctl_wide_r": {"face": {"wide_R": 1.0}},
    "ctl_squint_l": {"face": {"squint_L": 1.0}},
    "ctl_squint_r": {"face": {"squint_R": 1.0}},
    "ctl_jaw_open": {"jaw": 18.0},
    "ctl_jaw_left": {"jaw_side": 6.0},
    "ctl_jaw_right": {"jaw_side": -6.0},
    "ctl_look_left": {"look": (30.0, 0.0)},
    "ctl_look_right": {"look": (-30.0, 0.0)},
    "ctl_look_up": {"look": (0.0, 25.0)},
    "ctl_look_down": {"look": (0.0, -25.0)},
    "ctl_tongue_up": {"tongue": (10.0, 22.0, 34.0)},
    "ctl_tongue_down": {"tongue": (-8.0, -10.0, -12.0)},
}
EXTRA_CLIPS = list(CONTROLS)


def _make(cid, delta):
    def build(R):
        c = Clip(cid, 1, form="pose", layer="additive_face", entry="any", exit="any",
                 notes="extra: face control pose (frame 1 = full control)")
        base = merge(P.RELAXED, {"look": (0.0, 0.0), "face": {}})
        c.key(0, base, "LINEAR")
        c.key(1, merge(base, delta), "LINEAR")
        c.extra["no_floor_fix"] = True
        c.extra["no_contact_fix"] = True
        c.extra["no_tail_sim"] = True
        return c
    return build


for _cid, _delta in CONTROLS.items():
    clip(_cid)(_make(_cid, _delta))

"""Quick probe: what animation helpers are exposed and is root motion enabled?"""
import os

import unreal

ANIM_DIR = "/Game/MorphRig/Animations"

names = sorted(n for n in dir(unreal) if "Anim" in n or "anim" in n)
unreal.log("ANIMHELPERS %s" % ", ".join(names))

for name in ("dash_f", "dash_b", "dash_l", "dash_r", "walk_f"):
    seq = unreal.load_asset("%s/A_%s" % (ANIM_DIR, name))
    if seq is None:
        unreal.log("ROOTMOTION %s missing" % name)
        continue
    try:
        enabled = seq.get_editor_property("enable_root_motion")
    except Exception as exc:  # noqa: BLE001
        enabled = "err:%s" % exc
    try:
        lock = seq.get_editor_property("root_motion_root_lock")
    except Exception as exc:  # noqa: BLE001
        lock = "err:%s" % exc
    try:
        force = seq.get_editor_property("force_root_lock")
    except Exception as exc:  # noqa: BLE001
        force = "err:%s" % exc
    unreal.log("ROOTMOTION %s enable=%s lock=%s force=%s len=%.4f" %
               (name, enabled, lock, force,
                float(seq.get_editor_property("sequence_length"))))

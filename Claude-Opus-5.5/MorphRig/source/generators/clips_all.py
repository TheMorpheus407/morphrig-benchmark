"""MorphRig clip registry: every required animation id maps to a builder function."""
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, DEG
import mr_poses as P
import mr_locomotion as LOC

from clips_common import REGISTRY, clip, breathing, blinks, sway_noise, tremble, expr


# ---------------------------------------------------------------- idles
@clip("idle_relaxed")
def idle_relaxed(R):
    c = Clip("idle_relaxed", 120, loop=True, form="loop", entry="any", exit="any",
             notes="relaxed breathing, weight shifts left/right, glances")
    base = P.RELAXED
    left = merge(base, {"cog": (0.012, 0.0, -0.014), "hips": (0, 2, -2.5), "spine": (1.5, -1.5, 1.5),
                        "head": (1, 6, 0), "look": (10, 0)})
    right = merge(base, {"cog": (-0.012, 0.004, -0.013), "hips": (0, -2, 2.5), "spine": (1.0, 1.5, -1.5),
                         "head": (2, -4, 1), "look": (-8, -3)})
    c.key(0, base).key(28, left).key(58, base).key(88, right).key(120, base)
    c.layers += [breathing(1.0), blinks([40, 97]), sway_noise(1, 0.5)]
    return c


# ---------------------------------------------------------------- locomotion
DIRS = {"f": 0.0, "fl": 45.0, "l": 90.0, "bl": 135.0, "b": 180.0, "br": -135.0, "r": -90.0, "fr": -45.0}

for _kind in ("walk", "run"):
    for _d, _psi in DIRS.items():
        def _mk(R, kind=_kind, d=_d, psi=_psi):
            return LOC.gait_clip(f"{kind}_{d}", kind, psi)
        REGISTRY[f"{_kind}_{_d}"] = _mk


@clip("sprint_f")
def sprint_f(R):
    return LOC.gait_clip("sprint_f", "sprint", 0.0)


import clips_actions  # noqa: F401  (registers clips)
import clips_reactions  # noqa: F401
import clips_transitions  # noqa: F401
import clips_misc  # noqa: F401
import clip_dialogue  # noqa: F401
import clips_demo  # noqa: F401  (extra, not an inventory entry)
import clips_facectl  # noqa: F401  (extra: face control poses for Unreal)


def build_all(R, only=()):
    out = []
    for cid, fn in REGISTRY.items():
        if only and cid not in only:
            continue
        out.append(fn(R))
    return out

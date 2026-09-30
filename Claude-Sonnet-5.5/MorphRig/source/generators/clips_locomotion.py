"""Locomotion clips: eight-direction walk and run, forward sprint (gait.py), plus start/stop/turn/pivot (below)."""
import math
import clip_table as CT
from anim_registry import clip
import gait

DIRS = {'f': 0.0, 'fl': 45.0, 'l': 90.0, 'bl': 135.0, 'b': 180.0, 'br': -135.0, 'r': -90.0, 'fr': -45.0}


def _make(kind):
    def gen(entry):
        cid = entry['id']
        d = DIRS[cid.split('_')[1]]
        return gait.gait_clip(cid, entry, kind, d, entry['speed'])
    return gen


for k in DIRS:
    clip(f'walk_{k}')(_make('walk'))
    clip(f'run_{k}')(_make('run'))


@clip('sprint_f')
def sprint(entry):
    return gait.gait_clip('sprint_f', entry, 'sprint', 0.0, entry['speed'])

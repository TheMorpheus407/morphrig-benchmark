"""Replace selected original control actions without recreating the character.

Run: blender -b source/Operative.blend -P tools/reauthor_clip.py -- --clips reload
Then bake: blender -b source/Operative.blend -P tools/export_and_bake.py -- --clips reload --no-mesh
Use export_and_bake directly when editing existing curves interactively.
"""
from pathlib import Path
import argparse
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'source/generators'))
import build_character
import motions

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--clips', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
manifest = json.loads((ROOT / 'docs/animation_manifest.json').read_text())
lookup = {entry['id']: entry for entry in manifest['animations']}
names = args.clips.split(',')
if any(name not in lookup for name in names):
    raise ValueError('Only required IDs from the delivered manifest can be regenerated.')
rig = bpy.data.objects['Operative_Rig']
mesh = bpy.data.objects['Operative_LOD0']
rig.animation_data_create()
for name in names:
    entry = lookup[name]
    rig.animation_data.action = None
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data.action = action
    for frame in range(entry['frame_start'], entry['frame_end'] + 1):
        build_character.frame_pose(
            rig, mesh, motions.pose_at(name, (frame - entry['frame_start']) / 30,
                                      entry['duration']), frame)
    action['source'] = 'Original authored control motion'
    action['fps'] = 30
    action['duration'] = entry['duration']
    action['root_policy'] = entry['root_motion_policy']
    action['loop'] = entry['loop']
    print('REAUTHORED', name, entry['frame_count'], flush=True)
rig.animation_data.action = bpy.data.actions['idle_relaxed']
bpy.context.scene.frame_set(1)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'source/Operative.blend'))
print('SELECTED_SOURCE_UPDATE_COMPLETE')

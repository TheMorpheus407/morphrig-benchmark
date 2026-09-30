import bpy,sys,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import create_animations,action_curves
ids=['deploy','knockdown_front','knockdown_back','prone_front','prone_back','death_front','death_back','dead_front','dead_back','getup_front','getup_back','sleep_start','sleep_loop','sleep_end']
def signature(action):
 return hashlib.sha256(str([(f.data_path,f.array_index,[(float(k.co.x),float(k.co.y)) for k in f.keyframe_points]) for f in action_curves(action)]).encode()).hexdigest()
protected={n:signature(bpy.data.actions[n]) for n in ('dialogue','FACE__dialogue','idle_relaxed','aim_up_left','EDIT__ranged_fire')}
create_animations(bpy.data.objects['Operative_Rig'],bpy.data.objects['Operative_LOD0'],root,ids)
assert protected=={n:signature(bpy.data.actions[n]) for n in protected}
(root/'docs/contact_fix_preservation.json').write_text(json.dumps({'changed_clips':ids,'protected_action_hashes':protected,'protected_unchanged':True},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/Operative.blend'))

import bpy,json,math,csv
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[1]
rig=bpy.data.objects['Operative_Rig']
manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations']
rows=list(csv.DictReader((root/'source/required_animations.csv').open()))
assert {x['id'] for x in manifest}=={x['id'] for x in rows}
report={'inventory':len(manifest),'loops':{},'static_poses':{},'dash_displacement_m':{},'deaths':{},'in_place_max_root_drift_m':0.,'distinct_gait_signatures':{},'errors':[]}
def assign(id,f):
 a=bpy.data.actions[id];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 bpy.context.scene.frame_set(f);bpy.context.view_layer.update()
 return {p.name:p.matrix.copy() for p in rig.pose.bones if p.bone.use_deform}
def delta(a,b):return max((max(abs(a[k][i][j]-b[k][i][j]) for i in range(4) for j in range(4)) for k in a),default=0)
for m in manifest:
 id=m['id'];a=assign(id,1);b=assign(id,m['frame_end']);d=delta(a,b)
 if m['loop']:report['loops'][id]=d
 if m['static_pose']:report['static_poses'][id]=d
 if id.startswith('dash_'):report['dash_displacement_m'][id]=(b['root'].translation-a['root'].translation).length
 else:report['in_place_max_root_drift_m']=max(report['in_place_max_root_drift_m'],(b['root'].translation-a['root'].translation).length)
 if id.startswith(('walk_','run_')):
  mats=assign(id,1+round((m['frame_end']-1)*.2));report['distinct_gait_signatures'][id]=[round(x,5) for bone in ('foot.L','foot.R','hand.L','hand.R') for x in mats[bone].translation]
for suffix in ('front','back'):
 death=next(x for x in manifest if x['id']=='death_'+suffix);a=assign('death_'+suffix,death['frame_end']);b=assign('dead_'+suffix,1);report['deaths'][suffix]=delta(a,b)
if max(report['loops'].values())>1e-4:report['errors'].append('Loop endpoint differs')
if max(report['static_poses'].values())>1e-6:report['errors'].append('Static pose changes')
if any(abs(x-2)>1e-5 for x in report['dash_displacement_m'].values()):report['errors'].append('Dash displacement differs from2m')
if max(report['deaths'].values())>1e-4:report['errors'].append('Death endpoints differ')
(root/'docs/animation_curve_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2));assert not report['errors'],report['errors']

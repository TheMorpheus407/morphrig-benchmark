import sys,bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'source/generators'))
from animations import *
rig=bpy.data.objects['Operative_Rig'];rig.animation_data.action=None
for p in rig.pose.bones:
 for c in p.constraints:c.mute=True
report={}
for id,t in [('idle_relaxed',0),('run_f',7/21),('walk_f',6/24),('reload',34/69),('knockdown_back',1)]:
 p=motion(id,t,DURATIONS.get(id,.7));apply_pose(rig,p,id,t)
 report[id]={}
 for side in ('L','R'):
  report[id][side]={'target':p['foot'+side],'ankle':list(rig.pose.bones['foot.'+side].head),'shin_end':list(rig.pose.bones['shin.'+side].tail),'residual':(rig.pose.bones['foot.'+side].head-rig.pose.bones['shin.'+side].tail).length}
  report[id]['hand'+side]={'target':p['hand'+side],'wrist':list(rig.pose.bones['hand.'+side].head),'forearm_end':list(rig.pose.bones['forearm.'+side].tail),'residual':(rig.pose.bones['hand.'+side].head-rig.pose.bones['forearm.'+side].tail).length}
print(json.dumps(report,indent=2));(root/'docs/solver_validation.json').write_text(json.dumps(report,indent=2))

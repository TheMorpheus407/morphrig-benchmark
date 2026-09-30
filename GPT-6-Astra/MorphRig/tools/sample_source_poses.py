import bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];rig=bpy.data.objects['Operative_Rig'];manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations'];bones=['root','pelvis','head','hand.L','hand.R','cell','beacon','foot.L','foot.R']
report={'units':'meters','coordinates':'Blender +X anatomical left, -Y forward, +Z up','clips':{}}
for id in ('idle_relaxed','run_f','prone_back','reload','deploy','dash_f'):
 m=next(x for x in manifest if x['id']==id);a=bpy.data.actions[id];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 samples=[]
 for phase in (0,.5,1):
  frame=1+(m['frame_end']-1)*phase;bpy.context.scene.frame_set(int(frame),subframe=frame%1);bpy.context.view_layer.update();samples.append({'time':phase*m['duration'],'frame':frame,'bones':{n:{'head_m':list(rig.pose.bones[n].head),'world_matrix':[[v for v in row] for row in rig.pose.bones[n].matrix]} for n in bones}})
 report['clips'][id]=samples
(root/'docs/blender_pose_samples.json').write_text(json.dumps(report,indent=2))
print('WROTE SOURCE SAMPLES')

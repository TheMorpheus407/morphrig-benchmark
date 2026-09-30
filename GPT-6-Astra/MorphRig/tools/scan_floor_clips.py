import bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];rig=bpy.data.objects['Operative_Rig'];obj=bpy.data.objects['Operative_LOD0'];groups={g.index:g.name for g in obj.vertex_groups};manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations'];ids=set(json.loads((root/'docs/contact_fix_preservation.json').read_text())['changed_clips']);report={}
for m in manifest:
 if m['id'] not in ids:continue
 a=bpy.data.actions[m['id']];rig.animation_data.action=a
 if a.slots:rig.animation_data.action_slot=a.slots[0]
 key=obj.data.shape_keys;fa=bpy.data.actions['FACE__'+m['id']];key.animation_data.action=fa
 if fa.slots:key.animation_data.action_slot=fa.slots[0]
 worst={'minZ':100,'frame':None,'groups':[]};bad=[]
 for f in range(1,m['frame_end']+1):
  bpy.context.scene.frame_set(f);bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();v=min(mesh.vertices,key=lambda v:v.co.z)
  if v.co.z<worst['minZ']:worst={'minZ':v.co.z,'frame':f,'groups':[groups[g.group] for g in obj.data.vertices[v.index].groups]}
  if v.co.z<-.01:bad.append(f)
  ev.to_mesh_clear()
 worst['frames_below_minus_1cm']=bad;report[m['id']]=worst;print(m['id'],worst,flush=True)
(root/'docs/floor_clip_scan.json').write_text(json.dumps(report,indent=2))

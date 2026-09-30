"""Check the weights-only wrist correction against every floor-action frame."""
import bpy,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=Path(sys.argv[sys.argv.index('--')+1]).resolve() if '--' in sys.argv else root/'docs/validation/Operative_Wrist_Preview.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
rig=bpy.data.objects['Operative_Rig'];obj=bpy.data.objects['Operative_LOD0'];groups={g.index:g.name for g in obj.vertex_groups}
manifest=json.loads((root/'docs/animation_manifest.json').read_text())['animations'];ids=set(json.loads((root/'docs/contact_fix_preservation.json').read_text())['changed_clips']);report={'source':str(source.relative_to(root)),'clips':{}}
for m in manifest:
 if m['id'] not in ids:continue
 a=bpy.data.actions[m['id']];rig.animation_data.action=a;rig.animation_data.action_slot=a.slots[0]
 key=obj.data.shape_keys;fa=bpy.data.actions['FACE__'+m['id']];key.animation_data.action=fa;key.animation_data.action_slot=fa.slots[0]
 worst={'minZ':100,'frame':None,'groups':[]}
 for frame in range(1,m['frame_end']+1):
  bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();v=min(mesh.vertices,key=lambda v:v.co.z)
  if v.co.z<worst['minZ']:worst={'minZ':v.co.z,'frame':frame,'groups':[groups[g.group] for g in obj.data.vertices[v.index].groups]}
  ev.to_mesh_clear()
 report['clips'][m['id']]=worst
print(json.dumps(report,indent=2));(root/'docs/validation/wrist_floor_scan.json').write_text(json.dumps(report,indent=2))

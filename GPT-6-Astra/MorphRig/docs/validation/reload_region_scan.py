import bpy,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
root=Path(__file__).resolve().parents[2];bpy.ops.wm.open_mainfile(filepath=str(root/'source/Operative.blend'));r=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];groups={g.index:g.name for g in o.vertex_groups};h={v.index for v in o.data.vertices if any(g.weight>.15 and (groups[g.group]=='hand.L' or (groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ['thumb','index','middle','ring','pinky'])) for g in v.groups)};p={v.index for v in o.data.vertices if any(g.weight>.15 and groups[g.group]=='cell' for g in v.groups)};r.animation_data.action=bpy.data.actions['reload'];r.animation_data.action_slot=r.animation_data.action.slots[0]
report=[]
for f in range(1,71):
 bpy.context.scene.frame_set(f);bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());vs=[v.co.copy() for v in ev.data.vertices];body=BVHTree.FromPolygons(vs,[tuple(poly.vertices) for poly in ev.data.polygons if poly.material_index==3 and all(i in p for i in poly.vertices)],all_triangles=False);mat=r.pose.bones['cell'].matrix.inverted();inside=[]
 for i in h:
  hit,n,face,d=body.find_nearest(vs[i])
  if (vs[i]-hit).dot(n)<-1e-7:inside.append({'index':i,'depth_m':d,'local':list(mat@vs[i])})
 report.append({'frame':f,'inside':inside})
(root/'docs/validation/reload_classification/dense_before.json').write_text(json.dumps(report,indent=2))
print([(x['frame'],len(x['inside']),min(v['local'][1] for v in x['inside']),max(v['depth_m'] for v in x['inside'])) for x in report if x['inside']])

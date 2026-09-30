import bpy,json,sys
from pathlib import Path
from hashlib import file_digest
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path(__file__).resolve().parents[2]
source=Path(sys.argv[sys.argv.index('--source')+1]).resolve() if '--source' in sys.argv else root/'source/Operative.blend'
out=root/'docs/validation/native_skin_contact' if '--preview' in sys.argv else root/'docs/validation/acceptance'
lod=int(sys.argv[sys.argv.index('--lod')+1]) if '--lod' in sys.argv else 0
if lod:out=out/('LOD'+str(lod))
out.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
r=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD'+str(lod)];groups={g.index:g.name for g in o.vertex_groups}
def ids(kind):
 if kind=='hand':return {v.index for v in o.data.vertices if any(g.weight>.15 and (groups[g.group]=='hand.L' or (groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ['thumb','index','middle','ring','pinky'])) for g in v.groups)}
 return {v.index for v in o.data.vertices if any(g.weight>.15 and groups[g.group]==kind for g in v.groups)}
h=ids('hand');report=[]
deploy_frames=list(range(1,56)) if '--all-deploy' in sys.argv else [20,30,35]
for clip,prop,frames in [('reload','cell',list(range(1,71)) if '--all-reload' in sys.argv else [20,28,35,45,51]),('deploy','beacon',deploy_frames)]:
 p=ids(prop)
 for f in frames:
  r.animation_data.action=bpy.data.actions[clip];r.animation_data.action_slot=r.animation_data.action.slots[0];bpy.context.scene.frame_set(f);bpy.context.view_layer.update();ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());vs=[v.co.copy() for v in ev.data.vertices]
  pt=BVHTree.FromPolygons(vs,[tuple(poly.vertices) for poly in ev.data.polygons if all(i in p for i in poly.vertices)],all_triangles=False)
  ht=BVHTree.FromPolygons(vs,[tuple(poly.vertices) for poly in ev.data.polygons if all(i in h for i in poly.vertices)],all_triangles=False)
  distances=[pt.find_nearest(vs[i])[3] for i in h]+[ht.find_nearest(vs[i])[3] for i in p]
  # The rigid alloy body is closed with outward cube normals. Test its interior
  # separately from the lens/window, whose nested surfaces would bias signs.
  body=BVHTree.FromPolygons(vs,[tuple(poly.vertices) for poly in ev.data.polygons if poly.material_index==3 and all(i in p for i in poly.vertices)],all_triangles=False)
  bounds=[(min(vs[i][axis] for i in p),max(vs[i][axis] for i in p)) for axis in range(3)]
  depths=[];penetration_by_joint={}
  for i in h:
   # A signed nearest-face normal alone can falsely label remote outside points
   # against a narrow bevel. Every interior point must first lie within the body AABB.
   if any(vs[i][axis]<lo-1e-7 or vs[i][axis]>hi+1e-7 for axis,(lo,hi) in enumerate(bounds)):continue
   hit,normal,face,distance=body.find_nearest(vs[i])
   if (vs[i]-hit).dot(normal)<-1e-7:
    depths.append(distance)
    for g in o.data.vertices[i].groups:
     if g.weight>.15:penetration_by_joint[groups[g.group]]=max(penetration_by_joint.get(groups[g.group],0),distance)
  report.append({'clip':clip,'frame':f,'minimum_vertex_to_surface_distance_m':min(distances),'triangle_overlap_pairs':len(pt.overlap(ht)),'hand_vertices_inside_rigid_body':len(depths),'max_hand_vertex_penetration_m':max(depths,default=0),'penetration_by_joint_m':penetration_by_joint})
print(json.dumps(report));(out/'contact_surfaces.json').write_text(json.dumps(report,indent=2))
with source.open('rb') as f:sha=file_digest(f,'sha256').hexdigest()
(out/'contact_revision.json').write_text(json.dumps({'source':str(source.relative_to(root)),'lod':lod,'source_mtime':source.stat().st_mtime,'source_sha256':sha,'deploy_frames_tested':len(deploy_frames),'reload_frames_tested':70 if '--all-reload' in sys.argv else 5,'skinning':'linear blend; Preserve Volume disabled','method':'Nearest rigid-body surface, hand/prop triangle intersection and AABB-bounded signed inside test on closed outward-normal alloy body; lens/window excluded from inside test.'},indent=2))

import bpy,sys,json
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path(__file__).resolve().parents[2]
src=Path(sys.argv[sys.argv.index('--')+1]).resolve() if '--' in sys.argv else root/'source/Operative.blend'
bpy.ops.wm.open_mainfile(filepath=str(src));r=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];scene=bpy.context.scene
r.animation_data.action=bpy.data.actions['reload'];r.animation_data.action_slot=r.animation_data.action.slots[0]
o.data.shape_keys.animation_data.action=None
for k in o.data.shape_keys.key_blocks:k.value=0
scene.frame_set(28);bpy.context.view_layer.update()
groups={g.index:g.name for g in o.vertex_groups};ev=o.evaluated_get(bpy.context.evaluated_depsgraph_get());vs=[v.co.copy() for v in ev.data.vertices]
h={v.index for v in o.data.vertices if any(g.weight>.15 and (groups[g.group]=='hand.L' or (groups[g.group].endswith('.L') and groups[g.group].split('.')[0] in ['thumb','index','middle','ring','pinky'])) for g in v.groups)}
p={v.index for v in o.data.vertices if any(g.weight>.15 and groups[g.group]=='cell' for g in v.groups)}
body=BVHTree.FromPolygons(vs,[tuple(poly.vertices) for poly in ev.data.polygons if poly.material_index==3 and all(i in p for i in poly.vertices)],all_triangles=False)
inside=[]
for i in h:
 hit,n,face,d=body.find_nearest(vs[i])
 if (vs[i]-hit).dot(n)<-1e-7:inside.append({'index':i,'depth_m':d,'rest_coordinate':list(o.data.shape_keys.key_blocks['Basis'].data[i].co),'evaluated_coordinate':list(vs[i]),'groups':{groups[g.group]:g.weight for g in o.data.vertices[i].groups}})
out=root/'docs/validation/reload_cell_after';out.mkdir(exist_ok=True);(out/'frame28.json').write_text(json.dumps(inside,indent=2))
target=sum((vs[i] for i in p),Vector())/len(p)
scene.render.resolution_x=800;scene.render.resolution_y=800;scene.render.resolution_percentage=100;scene.cycles.samples=20
for name,offset in [('front',(.6,-1,.45)),('side',(-1,-.2,.3)),('back',(.2,1,.5)),('under',(.2,-.4,-.5))]:
 cam=scene.camera;cam.data.type='ORTHO';cam.data.ortho_scale=.27;cam.location=target+Vector(offset);cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)

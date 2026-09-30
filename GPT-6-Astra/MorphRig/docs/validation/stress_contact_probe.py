import bpy,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
bpy.ops.wm.open_mainfile(filepath=str(root/'source/Operative.blend'))
r=bpy.data.objects['Operative_Rig'];o=bpy.data.objects['Operative_LOD0'];groups={g.index:g.name for g in o.vertex_groups};report={}
for n in ['TEST__planted_hand_support','TEST__kneeling','TEST__deep_squat']:
 r.animation_data.action=bpy.data.actions[n];r.animation_data.action_slot=r.animation_data.action.slots[0];bpy.context.scene.frame_set(1);bpy.context.view_layer.update();vs=o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices
 def zmin(names):return min(vs[v.index].co.z for v in o.data.vertices if any(g.weight>.15 and names(groups[g.group]) for g in v.groups))
 report[n]={'whole_min_z':min(v.co.z for v in vs),'palmL_min_z':zmin(lambda x:x=='hand.L'),'palmR_min_z':zmin(lambda x:x=='hand.R'),'allhandL_min_z':zmin(lambda x:x=='hand.L' or (x.endswith('.L') and x.split('.')[0] in ['thumb','index','middle','ring','pinky'])),'allhandR_min_z':zmin(lambda x:x=='hand.R' or (x.endswith('.R') and x.split('.')[0] in ['thumb','index','middle','ring','pinky']))}
print(json.dumps(report));(root/'docs/validation/acceptance/stress_contacts.json').write_text(json.dumps(report,indent=2))
from mathutils import Vector
scene=bpy.context.scene
r.animation_data.action=bpy.data.actions['TEST__planted_hand_support'];r.animation_data.action_slot=r.animation_data.action.slots[0]
for ob in bpy.data.objects:
 if ob.type=='MESH' and ob.data.shape_keys:
  if ob.data.shape_keys.animation_data:ob.data.shape_keys.animation_data.action=None
  for k in ob.data.shape_keys.key_blocks:
   if k.name!='Basis':k.value=0
scene.frame_set(1);bpy.context.view_layer.update()
scene.render.resolution_x=900;scene.render.resolution_y=700;scene.render.resolution_percentage=100
scene.cycles.samples=24
scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=1.72
scene.camera.location=(2.8,-4,1.55)
scene.camera.rotation_euler=(Vector((0,-.10,.46))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(root/'docs/validation/acceptance/planted_hand_support.png')
bpy.ops.render.render(write_still=True)

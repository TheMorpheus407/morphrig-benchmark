"""Targeted pauldron clearance and cyber-elbow linear-skin compatibility patch.
Preserves vertex order, shape keys and actions; removes four intersecting cap faces per LOD. INPUT.blend [OUTPUT.blend]
"""
import bpy,bmesh,sys,json
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent));import character
args=sys.argv[sys.argv.index('--')+1:];src=Path(args[0]).resolve();dst=Path(args[1]).resolve() if len(args)>1 else src
bpy.ops.wm.open_mainfile(filepath=str(src));report=[]
for lod,detail in [(0,1.),(1,.62),(2,.38)]:
 obj=bpy.data.objects['Operative_LOD'+str(lod)];auth=character.MeshBuilder(detail);character.build_body(auth)
 basis=obj.data.shape_keys.key_blocks['Basis'];moved=[i for i,t in enumerate(auth.tags) if t.startswith(('shoulder_shell.','shoulder_inlay.'))]
 delta={i:Vector(auth.v[i])-basis.data[i].co for i in moved}
 for key in obj.data.shape_keys.key_blocks:
  for i,d in delta.items():key.data[i].co+=d
 weighted=[i for i,t in enumerate(auth.tags) if t in ['sleeve.R','cyber_armature.R']]
 for group in obj.vertex_groups:group.remove(weighted)
 for i in weighted:
  for name,weight in auth.weights[i].items():
   if weight>1e-8:obj.vertex_groups[name].add([i],weight,'REPLACE')
 # Remove only the solid end caps. All their vertices remain on side walls;
 # the intentional open cuffs replace a solid surface cutting across cloth.
 before_keys={key.name:[tuple(v.co) for v in key.data] for key in obj.data.shape_keys.key_blocks}
 caps=[p.index for p in obj.data.polygons if len(p.vertices)>4 and all(i<len(auth.tags) and auth.tags[i].startswith('shoulder_shell.') for i in p.vertices)]
 for i,co in enumerate(before_keys['Basis']):obj.data.vertices[i].co=co
 bm=bmesh.new();bm.from_mesh(obj.data);bm.faces.ensure_lookup_table();bmesh.ops.delete(bm,geom=[bm.faces[i] for i in caps],context='FACES_ONLY');bm.to_mesh(obj.data);bm.free()
 assert len(obj.data.vertices)==len(before_keys['Basis'])
 for key in obj.data.shape_keys.key_blocks:
  for i,co in enumerate(before_keys[key.name]):key.data[i].co=co
  assert [tuple(v.co) for v in key.data]==before_keys[key.name],key.name
 for mod in obj.modifiers:
  if mod.type=='ARMATURE':mod.use_deform_preserve_volume=False;mod.name='Native-compatible linear skin'
 obj.data.update();report.append({'mesh':obj.name,'pauldron_vertices':len(moved),'maximum_position_delta_m':max(d.length for d in delta.values()),'cyber_joint_vertices_reweighted':len(weighted),'caps_removed':len(caps),'triangles':sum(len(p.vertices)-2 for p in obj.data.polygons)})
text=bpy.data.texts.get('character.py')
if text:text.clear();text.write(Path(character.__file__).read_text())
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(dst));print('NATIVE_SKIN_PATCH',json.dumps(report))

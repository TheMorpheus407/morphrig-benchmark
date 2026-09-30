"""Match organic forearm/palm endpoint weights without changing topology/actions.

blender -b --factory-startup -P patch_wrist_weights.py -- INPUT.blend [OUTPUT.blend]
Only the last three forearm rings change; mesh/key coordinates are untouched.
"""
import bpy,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import character
args=sys.argv[sys.argv.index('--')+1:]
src=Path(args[0]).resolve();dst=Path(args[1]).resolve() if len(args)>1 else src
bpy.ops.wm.open_mainfile(filepath=str(src));report=[]
for lod,detail in [(0,1.),(1,.62),(2,.38)]:
    obj=bpy.data.objects['Operative_LOD'+str(lod)]
    authored=character.MeshBuilder(detail);character.build_body(authored)
    indices=[i for i,tag in enumerate(authored.tags) if tag=='organic_forearm.L' and 'hand.L' in authored.weights[i]]
    assert len(indices)==3*max(8,int(24*detail)),(obj.name,len(indices))
    before={i:{obj.vertex_groups[g.group].name:g.weight for g in obj.data.vertices[i].groups} for i in indices}
    for group in obj.vertex_groups:group.remove(indices)
    for i in indices:
        weights=authored.weights[i]
        assert abs(sum(weights.values())-1)<1e-6 and len(weights)<=2
        for name,value in weights.items():obj.vertex_groups[name].add([i],value,'REPLACE')
    obj.data.update()
    report.append({'mesh':obj.name,'vertices_updated':len(indices),'ring_endpoint_weights':authored.weights[indices[-1]],'maximum_weight_delta':max(abs(before[i].get(n,0)-w) for i in indices for n,w in authored.weights[i].items())})
text=bpy.data.texts.get('character.py')
if text:text.clear();text.write(Path(character.__file__).read_text())
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(dst))
print('WRIST_WEIGHT_PATCH',json.dumps(report))

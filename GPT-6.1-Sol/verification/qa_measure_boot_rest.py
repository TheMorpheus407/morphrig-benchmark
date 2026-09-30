"""Read actual delivered boot vertices and foot/toe reference matrices.

blender -b source/Operative.blend --python-exit-code 1 -P verification/qa_measure_boot_rest.py
Never modifies or saves the source file; all numbers are Blender metres.
"""
import bpy
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
mesh = bpy.data.objects['Operative_LOD0']
arm = bpy.data.objects['Operative_Rig']
groups = {g.index: g.name for g in mesh.vertex_groups}
report = {'source_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
          'units': 'Blender metres', 'native_mapping': 'cm=(-100*sourceY,-100*sourceX,100*sourceZ)', 'sides': {}}
for side in ['L', 'R']:
    names = {'foot.'+side, 'toe.'+side}
    vertices = [v for v in mesh.data.vertices
                if sum(g.weight for g in v.groups if groups[g.group] in names) >= .5]
    foot = arm.data.bones['foot.'+side]
    local = [foot.matrix_local.inverted() @ v.co for v in vertices]
    relative = [v.co-foot.head_local for v in vertices]
    bounds = lambda points: {'min': [min(p[i] for p in points) for i in range(3)],
                             'max': [max(p[i] for p in points) for i in range(3)]}
    report['sides'][side] = {
        'selected_vertices': len(vertices),
        'selection': 'sum foot and toe bone weights >=0.5; includes mixed cuff vertices',
        'foot_head_mesh': list(foot.head_local),
        'foot_tail_mesh': list(foot.tail_local),
        'foot_rest_matrix_mesh': [list(row) for row in foot.matrix_local],
        'foot_relative_mesh_bounds': bounds(relative),
        'foot_local_bounds': bounds(local),
        'mesh_bounds': bounds([v.co for v in vertices]),
        'sole_vertices': [
            {'vertex': v.index, 'mesh': list(v.co),
             'foot_local': list(foot.matrix_local.inverted() @ v.co)}
            for v in vertices if v.co.z < .001],
    }
out = root/'verification/qa_boot_rest.json'
out.write_text(json.dumps(report, indent=2)+'\n')
print('BOOT_REST_MEASURED', out)

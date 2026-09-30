"""Render representative actual action frames for independent visual review."""
import bpy
import json
import runpy
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.argv=[__file__,'--','--mode','still','--action','idle_relaxed','--frame','1','--width','800','--height','800']
ctx=runpy.run_path(str(ROOT/'tools/render_presentation.py'),run_name='__main__')
checks=[('walk_f',7,'side'),('walk_l',10,'front'),('run_f',8,'side'),
    ('melee_3',15,'front'),('reload',35,'front'),('deploy',30,'side'),
    ('knockdown_front',34,'side'),('knockdown_back',37,'side'),
    ('getup_front',35,'side'),('getup_back',40,'side'),
    ('dialogue',75,'face'),('dialogue',325,'face')]
for clip,frame,view in checks:
    ctx['assign_action'](clip,frame)
    ctx['camera'](view)
    bpy.context.scene.render.filepath=str(ROOT/'docs/validation'/f'{clip}_{frame}_{view}.png')
    bpy.ops.render.render(write_still=True)
    print('VALIDATION_RENDER',clip,frame,view,flush=True)
(ROOT/'docs/validation/render_checks.json').write_text(json.dumps({'source':'source/Operative.blend','checks':[{'clip':c,'frame':f,'view':v,'file':f'{c}_{f}_{v}.png'} for c,f,v in checks]},indent=2)+'\n')

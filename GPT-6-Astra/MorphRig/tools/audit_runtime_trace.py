#!/usr/bin/env python3
"""Check observed packaged-client state and marker execution, not simulated code."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def audit(path, demo=False):
    text=path.read_text()
    checks=[]
    def check(name, passed, evidence):
        checks.append(dict(check=name,pass_=bool(passed),evidence=evidence))
    loaded=re.search(r'loaded=(\d+)/96',text)
    check('all required animations loaded',loaded and int(loaded[1])==96,loaded[0] if loaded else 'not logged')
    events=[]
    for line in text.splitlines():
        if 'event generation=' not in line:continue
        pairs=dict(re.findall(r'(generation|loop|clip|t|marker)=([^\s]+)',line))
        pairs['elapsed_s']=float(line.split()[0])
        events.append(pairs)
    keys=[(e.get('generation'),e.get('loop'),e.get('clip'),e.get('marker')) for e in events]
    duplicates=[{'key':key,'count':count} for key,count in Counter(keys).items() if count>1]
    check('event loop identity recorded',events and all('loop' in e for e in events),len(events))
    check('no duplicate marker execution per generation and loop',not duplicates,duplicates)
    transitions=[]
    for line in text.splitlines():
        m=re.search(r'state generation=(\d+) (.*?) -> (\S+) priority=(\d+) browser=(\d+)',line)
        if m:transitions.append(dict(generation=int(m[1]),previous=m[2],state=m[3],priority=int(m[4]),browser=bool(int(m[5])),elapsed_s=float(line.split()[0])))
    if demo:
        check('deterministic sequence completed','deterministic sequence complete' in text,'sequence completion trace')
        expected={'ranged_burst','cast_directional','channel_start','channel_loop','channel_interrupt','charge_start','charge_hold','charge_release','uplink_start','uplink_loop','uplink_cancel','reload','deploy','dash_f','jump_start','death_front','dead_front','respawn','knockdown_back','prone_back','getup_back','blink_out','blink_in','melee_1','melee_2','stun_start','stun_loop','stun_end'}
        observed={s['state'] for s in transitions}
        check('combined-state sequence reached required demonstration states',expected<=observed,{'missing':sorted(expected-observed),'observed':sorted(observed)})
        for clip,markers in [('ranged_burst',{'muzzle_fire_1','muzzle_fire_2','muzzle_fire_3'}),('deploy',{'beacon_grip','beacon_release','beacon_activate'}),('reload',{'cell_grip','cell_extract','cell_insert','cell_release','reload_complete'})]:
            seen=[e['marker'] for e in events if e.get('clip')==clip]
            check(clip+' executes each interaction marker once',all(seen.count(k)==1 for k in markers),seen)
        death=[s for s in transitions if s['state']=='death_front']
        check('death plays once in demonstration',len(death)==1,len(death))
        teleports=[e for e in events if e.get('marker')=='blink_teleport']
        check('blink teleport marker executes once',len(teleports)==1,len(teleports))
    return {'trace':str(path.resolve().relative_to(ROOT)),'scope':'Observed state/marker execution; visual contact, capsule displacement, UI input and frame performance require separate evidence.',
            'passed':sum(c['pass_'] for c in checks),'total':len(checks),'checks':checks,'transitions':transitions,'events':events}

def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('--demo',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
    result=audit(args.trace,args.demo)
    out=args.output or args.trace.with_name('trace_audit.json');out.write_text(json.dumps(result,indent=2)+'\n')
    print(f"{result['passed']}/{result['total']} runtime trace checks passed")
    for c in result['checks']:
        if not c['pass_']:print('FAIL',c['check'],c['evidence'])
    if result['passed']!=result['total']:raise SystemExit(1)

if __name__=='__main__':main()

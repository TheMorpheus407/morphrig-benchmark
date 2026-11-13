#!/usr/bin/env python3
"""Checks a MORPHRIG showcase trace (MorphRigTrace.log / presentation/*_trace.log) against the event rules of
docs/animation_state_contract.md section 6:

  A  a marker fires at most once per pass of a clip activation (once per cycle for loops)
  B  a clip that was replaced on its layer fires nothing afterwards (no late hits from interrupted clips)
  C  markers of one pass arrive in clip-time order
  D  markers before the entry time of an activation are skipped, not replayed
  E  death happens once per life (further death requests are refused)
  F  ranged_fire dispatches one muzzle marker, ranged_burst three distinct ones (unless the clip was cut short)
  G  every activation uses a clip of the manifest and markers that the manifest lists for it
  I  (traces of scripts/ui_selftest.txt) the injected mouse / keyboard steps had their effect
  J  (traces of scripts/browse_all.txt) every inventory entry was selected in the motion viewer and started
  H  (traces of the deterministic sequence only) the combined states really happened: shots, burst, directional cast
     and reload started while the controller was moving, hits arrived while moving, the channel was interrupted and
     completed, the charge was released at two levels and cancelled, the uplink was cancelled and completed, death
     interrupted a cast and a jump, both knock-down sides, both turns and pivots, all four dashes, both action rates

Usage: tools/verify_trace.py <trace.log> [docs/animation_manifest.json]
Exit code 0 when no rule is violated.
"""
import json
import os
import re
import sys

LINE = re.compile(r'^\[\s*([0-9.]+)\]\s+(.*)$')
CLIP = re.compile(r'^CLIP (base|upper) (\S+) #(\d+)(?: t=([0-9.]+))?(?: blend=([0-9.]+))?(.*)$')
EVENT = re.compile(r'^EVENT (\S+) @([0-9.]+) clip=(\S+) #(\d+)$')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    trace_path = sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    manifest_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, '..', 'docs', 'animation_manifest.json')
    manifest = {c['id']: c for c in json.load(open(manifest_path, encoding='utf-8'))['clips']}

    blended = set()    # clips used through blends / layers (gait set, idles, aim grid, additive hits)
    acts = {}          # id -> dict
    order = []         # (layer, id) in start order
    violations = []
    deaths_in_life = 0
    death_refusals = 0
    lives = 1
    n_events = 0
    gait_events = 0
    with open(trace_path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    current = {'base': None, 'upper': None}
    for ln, raw in enumerate(lines, 1):
        m = LINE.match(raw.rstrip('\n'))
        if not m:
            continue
        t, body = float(m.group(1)), m.group(2)
        mc = CLIP.match(body)
        if mc and ('finished' not in mc.group(6)) and ('ended' not in mc.group(6)):
            layer, clip, aid = mc.group(1), mc.group(2), int(mc.group(3))
            start = float(mc.group(4)) if mc.group(4) else 0.0
            if clip not in manifest:
                violations.append('G line %d: activation #%d uses unknown clip %s' % (ln, aid, clip))
            acts[aid] = dict(layer=layer, clip=clip, start_time=t, entry=start, events=[], line=ln, replaced_at=None)
            prev = current[layer]
            if prev is not None and prev in acts:
                acts[prev]['replaced_at'] = ln
            current[layer] = aid
            order.append((layer, aid))
            continue
        if mc and ('ended' in mc.group(6)) and mc.group(1) == 'upper':
            aid = int(mc.group(3))
            if aid in acts:
                acts[aid]['replaced_at'] = ln
            if current['upper'] == aid:
                current['upper'] = None
            continue
        me = EVENT.match(body)
        if me:
            name, ct, clip, aid = me.group(1), float(me.group(2)), me.group(3), int(me.group(4))
            n_events += 1
            if aid == 0:
                gait_events += 1      # foot contacts of the gait blend (dominant clip, shared phase)
                if clip in manifest and name not in [e['name'] for e in manifest[clip]['events']]:
                    violations.append('G line %d: gait marker %s is not listed for %s' % (ln, name, clip))
                continue
            a = acts.get(aid)
            if a is None:
                violations.append('B line %d: marker %s for unknown activation #%d' % (ln, name, aid))
                continue
            if a['clip'] != clip:
                violations.append('G line %d: marker %s reports clip %s but #%d is %s' % (ln, name, clip, aid, a['clip']))
            if clip in manifest and name not in [e['name'] for e in manifest[clip]['events']]:
                violations.append('G line %d: marker %s is not listed for %s' % (ln, name, clip))
            if a['replaced_at'] is not None and ln > a['replaced_at']:
                violations.append('B line %d: marker %s fired by #%d (%s) after it was replaced at line %d'
                                  % (ln, name, aid, clip, a['replaced_at']))
            if ct < a['entry'] - 1e-3:
                violations.append('D line %d: marker %s @%.3f is before the entry time %.3f of #%d' % (ln, name, ct, a['entry'], aid))
            a['events'].append((t, name, ct, ln))
            continue
        mb = re.match(r'^(GAIT|IDLE) (\S+)', body) or re.match(r'^AIM pose (\S+)()', body)
        if mb:
            blended.add(mb.group(2) if mb.group(1) in ('GAIT', 'IDLE') else mb.group(1))
            if body.startswith('AIM pose'):
                blended.add('aim_level_center')      # reference pose of the aim layer
            continue
        mv = re.match(r'^VIEW additive (\S+)', body)
        if mv:
            blended.add(mv.group(1))
            continue
        if body.startswith('HIT from'):
            for name in re.findall(r'(hit_[fblr])=', body):
                blended.add(name)
        if body.startswith('STATE ') and '-> Dead' in body:
            deaths_in_life += 1
            if deaths_in_life > 1:
                violations.append('E line %d: second death in the same life' % ln)
        elif body.startswith('RESPAWN') or body.startswith('RESET'):
            if deaths_in_life:
                lives += 1
            deaths_in_life = 0
        elif body.startswith('REFUSED death'):
            death_refusals += 1

    loops = 0
    for aid, a in acts.items():
        info = manifest.get(a['clip'])
        if not info:
            continue
        ev = a['events']
        if info['loop']:
            loops += 1
            # once per cycle: the same marker may only repeat one cycle later. The shortest possible cycle is the clip
            # duration at the maximum action rate (1.5x); anything closer than 45 % of that is a duplicate.
            min_gap = 0.45 * float(info['duration']) / 1.5
            last_fired = {}
            for (t, name, ct, ln) in ev:
                key = (name, round(ct, 4))
                if key in last_fired and t - last_fired[key] < min_gap:
                    violations.append('A line %d: loop marker %s @%.3f fired twice in one cycle of #%d (%s)' % (ln, name, ct, aid, a['clip']))
                last_fired[key] = t
        else:
            seen = set()
            last_ct = -1.0
            for (t, name, ct, ln) in ev:
                key = (name, round(ct, 4))
                if key in seen:
                    violations.append('A line %d: marker %s @%.3f fired twice by #%d (%s)' % (ln, name, ct, aid, a['clip']))
                seen.add(key)
                if ct < last_ct - 1e-4:
                    violations.append('C line %d: marker %s @%.3f out of order in #%d (%s)' % (ln, name, ct, aid, a['clip']))
                last_ct = ct
            if a['clip'] in ('ranged_fire', 'ranged_burst'):
                muzzles = [n for (_, n, _, _) in ev if n.startswith('muzzle_')]
                want = 1 if a['clip'] == 'ranged_fire' else 3
                complete = any(n == 'recovery' for (_, n, _, _) in ev)
                if len(muzzles) != len(set(muzzles)):
                    violations.append('F activation #%d (%s): duplicate muzzle markers %s' % (aid, a['clip'], muzzles))
                if complete and len(muzzles) != want:
                    violations.append('F activation #%d (%s): %d muzzle markers, expected %d' % (aid, a['clip'], len(muzzles), want))

    # ---- H: combined states of the deterministic sequence
    bodies = []
    for raw in lines:
        m = LINE.match(raw.rstrip('\n'))
        if m:
            bodies.append(m.group(2))
    seq_checks = []
    if any(b.startswith('SEQUENCE begin') for b in bodies):
        def upper_speed(clip):
            best = -1.0
            for b in bodies:
                mm = re.match(r'^CLIP upper %s #\d+ blend=[0-9.]+ speed=([0-9.]+)' % re.escape(clip), b)
                if mm:
                    best = max(best, float(mm.group(1)))
            return best
        hit_speeds = [float(x) for b in bodies for x in re.findall(r'^HIT from .*speed=([0-9.]+)', b)]
        charge_levels = sorted(set(re.findall(r'^CHARGE release requested at level ([0-9.]+)', '\n'.join(bodies), re.M)))
        dashes = {a['clip'] for a in acts.values() if a['clip'].startswith('dash_') and any(n == 'dash_end' for (_, n, _, _) in a['events'])}
        has = lambda text: any(text in b for b in bodies)
        seq_checks = [
            ('ranged_fire started while moving (>= 100 cm/s)', upper_speed('ranged_fire') >= 100.0),
            ('ranged_burst started while moving (>= 100 cm/s)', upper_speed('ranged_burst') >= 100.0),
            ('cast_directional started while moving (>= 100 cm/s)', upper_speed('cast_directional') >= 100.0),
            ('reload started while walking (>= 50 cm/s)', upper_speed('reload') >= 50.0),
            ('four hits while moving (>= 100 cm/s)', sum(1 for v in hit_speeds if v >= 100.0) >= 4),
            ('channel interrupted midway', has('CHANNEL interrupted')),
            ('channel completed normally', has('CHANNEL released normally')),
            ('charge released at two different levels', len(charge_levels) >= 2),
            ('charge cancelled', has('CHARGE cancelled')),
            ('uplink cancelled by damage', has('UPLINK cancelled')),
            ('uplink completed', any(b.startswith('EVENT uplink_complete') for b in bodies)),
            ('death during a cast', has('DEATH requested during Action:cast')),
            ('death during a jump', has('DEATH requested during Air')),
            ('second death refused', death_refusals >= 1),
            ('knock-down from the front and from behind', has('KNOCKDOWN hit from front') and has('KNOCKDOWN hit from behind')),
            ('turn in place to both sides', {a['clip'] for a in acts.values()} >= {'turn_l90', 'turn_r90'}),
            ('pivot to both sides', {a['clip'] for a in acts.values()} >= {'pivot_l180', 'pivot_r180'}),
            ('four root-motion dashes completed', len(dashes) == 4),
            ('action rate 0.5x and 1.5x', has('CMD rate 0.5') and has('CMD rate 1.5')),
            ('silenced cast and disarmed attack refused', has('REFUSED cast (silenced)') and has('REFUSED melee (disarmed)')),
            ('reload cancelled before reload_insert', has('RELOAD cancelled')),
            ('sequence ran to its end', any(b.startswith('SEQUENCE end') for b in bodies)),
        ]
        for text, ok in seq_checks:
            if not ok:
                violations.append('H sequence expectation not met: %s' % text)

    # ---- I: traces of tools/scripts/ui_selftest.txt (every step was injected through Slate as mouse / keyboard input)
    ui_checks = []
    if any(b.startswith('UITEST') for b in bodies):
        has = lambda text: any(text in b for b in bodies)
        started = {a['clip'] for a in acts.values()}
        fire_speed = max([float(x) for b in bodies for x in re.findall(r'^CLIP upper ranged_fire #\d+ blend=[0-9.]+ speed=([0-9.]+)', b)] or [-1.0])
        ui_checks = [
            ('panel tab click + typed filter + list click selected melee_3', has('CMD view melee_3')),
            ('Backspace reset after the focus click', has('RESET character returned')),
            ('shot fired with the mouse while W was held (>= 100 cm/s)', fire_speed >= 100.0),
            ('channel started with C and interrupted with X', has('CHANNEL interrupted (interrupt command)')),
            ('charge held and released with G', has('CHARGE release requested')),
            ('jump, dash and the three-step melee combo from the keyboard', started >= {'jump_start', 'melee_1', 'melee_2', 'melee_3'} and any(c.startswith('dash_') for c in started)),
            ('hit, stun, death and respawn from the keyboard', has('HIT from') and has('-> Stun') and has('DEATH requested') and has('RESPAWN')),
            ('speech sample started with Enter', 'dialogue' in started),
            ('script ran to its end', has('UITEST done')),
        ]
        for text, ok in ui_checks:
            if not ok:
                violations.append('I interaction expectation not met: %s' % text)

    # ---- J: traces of tools/scripts/browse_all.txt (motion viewer over the whole inventory)
    viewed = [b.split()[2] for b in bodies if b.startswith('CMD view ') and len(b.split()) > 2]
    browse = len(set(viewed)) >= 90
    if browse:
        shown = {a['clip'] for a in acts.values()} | set(re.findall(r'^VIEW additive (\S+)', '\n'.join(bodies), re.M))
        for cid in manifest:
            if cid not in viewed:
                violations.append('J browser: %s was never selected' % cid)
            elif cid not in shown:
                violations.append('J browser: %s was selected but no clip started' % cid)
    for ln, b in enumerate(bodies, 1):
        if b.startswith('ERROR') or b.startswith('DATA ERROR'):
            violations.append('trace reports: %s' % b[:160])

    clips_used = sorted({a['clip'] for a in acts.values()} | {b for b in blended if b in manifest})
    trace_label = trace_path
    try:                                           # reports are kept in the delivery: no machine-specific prefix
        root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        rel = os.path.relpath(os.path.abspath(trace_path), root)
        if not rel.startswith('..'):
            trace_label = rel
    except ValueError:
        pass
    print('trace: %s' % trace_label)
    print('activations: %d (%d loops)   markers dispatched: %d (+%d gait foot contacts)   clips used: %d of %d'
          % (len(acts), loops, n_events - gait_events, gait_events, len(clips_used), len(manifest)))
    print('lives: %d   refused extra deaths: %d' % (lives, death_refusals))
    missing = sorted(set(manifest) - set(clips_used))
    if missing:
        print('clips not exercised in this trace (%d): %s' % (len(missing), ' '.join(missing)))
    if not missing:
        print('coverage: all %d inventory entries were exercised (single clips, gait/idle blends, aim grid, additive hits)' % len(manifest))
    if seq_checks:
        print('sequence expectations: %d of %d met' % (sum(1 for _, ok in seq_checks if ok), len(seq_checks)))
    if ui_checks:
        print('interaction expectations: %d of %d met' % (sum(1 for _, ok in ui_checks if ok), len(ui_checks)))
    if browse:
        print('motion viewer: %d of %d inventory entries selected and started' % (len([c for c in manifest if c in viewed and c in shown]), len(manifest)))
    if violations:
        print('VIOLATIONS: %d' % len(violations))
        for v in violations[:60]:
            print('  ' + v)
        return 1
    print('RESULT: no rule violated (A once per pass, B nothing after replacement, C ordered, D entry offset, E single death, F muzzle counts, G manifest names%s)'
          % ((', H combined states' if seq_checks else '') + (', I interaction' if ui_checks else '') + (', J motion viewer' if browse else '')))
    return 0


if __name__ == '__main__':
    sys.exit(main())

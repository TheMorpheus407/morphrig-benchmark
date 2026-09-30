"""Single table of the 96 required clips: final frame counts (30 fps intervals), loop flags, root policy, layer, nominal speed
and gameplay entry/exit states. Validated against required_animations.csv (duration ranges)."""
import csv
import json
import os

FPS = 30

# id: (seconds, layer, nominal_cm_s, entry_states, exit_states)
LOC = ['idle', 'locomotion']
_T = {}


def T(cid, seconds, layer='full', speed=0.0, entry=(), exit_=()):
    _T[cid] = dict(frames=int(round(seconds * FPS)), layer=layer, speed=float(speed), entry=list(entry), exit=list(exit_))


T('idle_relaxed', 4.0, entry=['any_grounded_free'], exit_=['any'])
T('idle_combat', 3.2, entry=['any_grounded_free'], exit_=['any'])
T('idle_wounded', 3.6, entry=['any_grounded_free'], exit_=['any'])
# walk (nominal per-direction speeds, cm/s)
for cid, sec, spd in (('walk_f', 0.9, 150), ('walk_fl', 0.9, 140), ('walk_l', 0.8, 100), ('walk_bl', 1.0, 110), ('walk_b', 1.0, 105),
                      ('walk_br', 1.0, 110), ('walk_r', 0.8, 100), ('walk_fr', 0.9, 140)):
    T(cid, sec, speed=spd, entry=['locomotion'], exit_=['locomotion'])
for cid, sec, spd in (('run_f', 0.6, 400), ('run_fl', 0.6, 370), ('run_l', 0.6, 260), ('run_bl', 0.7, 250), ('run_b', 0.7, 240),
                      ('run_br', 0.7, 250), ('run_r', 0.6, 260), ('run_fr', 0.6, 370)):
    T(cid, sec, speed=spd, entry=['locomotion'], exit_=['locomotion'])
T('sprint_f', 0.5, speed=650, entry=['locomotion'], exit_=['locomotion'])
T('start_f', 0.6, entry=['idle'], exit_=['locomotion'])
T('stop_f', 0.55, entry=['locomotion'], exit_=['idle'])
T('turn_l90', 0.7, entry=['idle'], exit_=['idle'])
T('turn_r90', 0.7, entry=['idle'], exit_=['idle'])
T('pivot_l180', 0.75, entry=['locomotion'], exit_=['locomotion'])
T('pivot_r180', 0.75, entry=['locomotion'], exit_=['locomotion'])
T('jump_start', 0.45, entry=['grounded'], exit_=['jump_air'])
T('jump_air', 0.6, entry=['jump_start', 'walk_off_ledge'], exit_=['jump_land', 'fall'])
T('jump_land', 0.5, entry=['jump_air'], exit_=['idle', 'locomotion'])
T('fall', 0.6, entry=['airborne_long'], exit_=['land_heavy', 'jump_land'])
T('land_heavy', 0.8, entry=['fall'], exit_=['idle'])
for cid, spd in (('dash_f', 500), ('dash_b', 500), ('dash_l', 500), ('dash_r', 500)):
    T(cid, 0.4, speed=spd, entry=['grounded_free'], exit_=['idle', 'locomotion'])
T('blink_out', 0.3, entry=['grounded_free'], exit_=['blink_teleport'])
T('blink_in', 0.35, entry=['blink_teleport'], exit_=['idle'])
for cid in ('melee_1', 'melee_2', 'melee_3'):
    T(cid, 0.8, entry=['grounded_free', 'melee_chain'], exit_=['idle', 'melee_chain'])
T('ranged_fire', 0.3, 'upper', entry=['grounded_free', 'locomotion'], exit_=['any'])
T('ranged_burst', 0.6, 'upper', entry=['grounded_free', 'locomotion'], exit_=['any'])
T('reload', 1.9, entry=['grounded_free'], exit_=['idle'])
T('cast_directional', 0.8, 'upper', entry=['grounded_free', 'locomotion'], exit_=['any'])
T('cast_ground', 1.1, entry=['grounded_free'], exit_=['idle'])
T('cast_self', 0.8, entry=['grounded_free'], exit_=['idle'])
T('channel_start', 0.5, entry=['grounded_free'], exit_=['channel_loop', 'channel_interrupt', 'channel_end'])
T('channel_loop', 1.2, entry=['channel_start'], exit_=['channel_end', 'channel_interrupt'])
T('channel_end', 0.5, entry=['channel_loop'], exit_=['idle'])
T('channel_interrupt', 0.4, entry=['channel_start', 'channel_loop'], exit_=['idle'])
T('charge_start', 0.7, entry=['grounded_free'], exit_=['charge_hold', 'charge_release', 'charge_cancel'])
T('charge_hold', 1.0, entry=['charge_start'], exit_=['charge_release', 'charge_cancel'])
T('charge_release', 0.6, entry=['charge_start', 'charge_hold'], exit_=['idle'])
T('charge_cancel', 0.45, entry=['charge_start', 'charge_hold'], exit_=['idle'])
T('deploy', 1.2, entry=['grounded_free'], exit_=['idle'])
T('uplink_start', 0.7, entry=['grounded_free'], exit_=['uplink_loop', 'uplink_cancel', 'uplink_end'])
T('uplink_loop', 1.5, entry=['uplink_start'], exit_=['uplink_end', 'uplink_cancel'])
T('uplink_end', 0.5, entry=['uplink_loop'], exit_=['idle'])
T('uplink_cancel', 0.45, entry=['uplink_start', 'uplink_loop'], exit_=['idle'])
for cid in ('hit_f', 'hit_b', 'hit_l', 'hit_r'):
    T(cid, 0.35, 'additive', entry=['any_alive'], exit_=['any'])
T('stun_start', 0.6, entry=['any_alive'], exit_=['stun_loop'])
T('stun_loop', 1.6, entry=['stun_start'], exit_=['stun_end'])
T('stun_end', 0.8, entry=['stun_loop'], exit_=['idle'])
T('knockback', 0.9, entry=['any_alive'], exit_=['idle', 'knockdown'])
T('knockup_start', 0.6, entry=['any_alive'], exit_=['knockup_air'])
T('knockup_air', 0.9, entry=['knockup_start'], exit_=['knockdown_front', 'knockdown_back'])
T('knockdown_front', 1.4, entry=['knockup_air', 'knockback', 'any_alive'], exit_=['prone_front'])
T('knockdown_back', 1.4, entry=['knockup_air', 'knockback', 'any_alive'], exit_=['prone_back'])
T('prone_front', 2.0, entry=['knockdown_front'], exit_=['getup_front'])
T('prone_back', 2.0, entry=['knockdown_back'], exit_=['getup_back'])
T('getup_front', 2.2, entry=['prone_front'], exit_=['idle'])
T('getup_back', 2.2, entry=['prone_back'], exit_=['idle'])
T('sleep_start', 1.8, entry=['grounded_free'], exit_=['sleep_loop'])
T('sleep_loop', 3.0, entry=['sleep_start'], exit_=['sleep_end'])
T('sleep_end', 1.6, entry=['sleep_loop'], exit_=['idle'])
T('death_front', 2.4, entry=['any_alive'], exit_=['dead_front'])
T('death_back', 2.4, entry=['any_alive'], exit_=['dead_back'])
T('dead_front', 1.0 / FPS, 'pose', entry=['death_front'], exit_=['respawn'])
T('dead_back', 1.0 / FPS, 'pose', entry=['death_back'], exit_=['respawn'])
T('respawn', 2.6, entry=['dead_front', 'dead_back'], exit_=['idle'])
T('greet', 2.2, entry=['grounded_free'], exit_=['idle'])
T('victory', 3.0, entry=['grounded_free'], exit_=['idle'])
T('defeat', 3.0, entry=['grounded_free'], exit_=['idle'])
def _dialogue_seconds(default=15.0):
    """Length of the spoken performance = length of the synthesised audio (source/audio/dialogue_alignment.json)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audio', 'dialogue_alignment.json'), encoding='utf-8') as fh:
            return json.load(fh)['clip']['frames'] / FPS
    except (OSError, KeyError, ValueError):
        return default


T('dialogue', _dialogue_seconds(), entry=['grounded_free'], exit_=['idle'])
for pitch in ('down', 'level', 'up'):
    for yaw in ('left', 'center', 'right'):
        T(f'aim_{pitch}_{yaw}', 1.0 / FPS, 'pose', entry=['aim_layer'], exit_=['aim_layer'])

LOOPS = {'idle_relaxed', 'idle_combat', 'idle_wounded', 'walk_f', 'walk_fl', 'walk_l', 'walk_bl', 'walk_b', 'walk_br', 'walk_r', 'walk_fr',
         'run_f', 'run_fl', 'run_l', 'run_bl', 'run_b', 'run_br', 'run_r', 'run_fr', 'sprint_f', 'jump_air', 'fall', 'channel_loop',
         'charge_hold', 'uplink_loop', 'stun_loop', 'knockup_air', 'prone_front', 'prone_back', 'sleep_loop'}
ROOT_MOTION = {'dash_f', 'dash_b', 'dash_l', 'dash_r'}
ADDITIVE = {'hit_f', 'hit_b', 'hit_l', 'hit_r'}
POSES = {'dead_front', 'dead_back'} | {f'aim_{p}_{y}' for p in ('down', 'level', 'up') for y in ('left', 'center', 'right')}


def load_csv(path):
    rows = {}
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows[r['id']] = r
    return rows


def parse_range(s):
    s = s.strip()
    if s == 'pose':
        return None
    a, b = s.replace('–', '-').split('-')
    return float(a), float(b)


def build_table(csv_path=None):
    """Return ordered list of clip dicts merged with the CSV spec; asserts durations lie in the required ranges."""
    # the task's inventory table is shipped next to the generators so the folder builds on its own
    csv_path = csv_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'required_animations.csv')
    rows = load_csv(csv_path)
    out = []
    for cid, r in rows.items():
        t = dict(_T[cid])
        t['id'] = cid
        t['form'] = r['form']
        t['root'] = r['root_movement']
        t['behavior'] = r['required_behavior']
        t['loop'] = cid in LOOPS
        t['duration_s'] = t['frames'] / FPS
        rng = parse_range(r['duration_seconds'])
        if rng is not None:
            assert rng[0] - 1e-6 <= t['duration_s'] <= rng[1] + 1e-6, f"{cid}: {t['duration_s']} not in {rng}"
        else:
            t['duration_s'] = None
        t['range'] = rng
        out.append(t)
    assert len(out) == 96, len(out)
    assert set(_T) == set(rows), (set(_T) ^ set(rows))
    return out


if __name__ == '__main__':
    tab = build_table()
    print(len(tab), 'clips OK; total frames', sum(t['frames'] for t in tab))

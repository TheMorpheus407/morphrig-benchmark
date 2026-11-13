"""Closed animation inventory: the 96 required entries with authoring metadata.

This table is the single source for clip names, forms, layers, planned lengths, event markers and state
links. Animation authoring code may adjust frame counts / marker frames; the exported
animation_manifest.json always reflects the values that were actually baked.
"""
import csv
import os

FPS = 30

WALK_SPEED = 150.0    # cm/s nominal
RUN_SPEED = 400.0
SPRINT_SPEED = 650.0
WALK_FRAMES = 32
RUN_FRAMES = 22
SPRINT_FRAMES = 16
DASH_DISTANCE = 200.0  # cm

# direction suffix -> travel direction in degrees, 0 = forward, +90 = character's left (counter-clockwise from above)
DIRS = {'f': 0.0, 'fl': 45.0, 'l': 90.0, 'bl': 135.0, 'b': 180.0, 'br': -135.0, 'r': -90.0, 'fr': -45.0}

CLIPS = []
BY_ID = {}


def clip(cid, form, frames, layer, root='in_place', events=(), entry=(), exit=(), **kw):
    d = dict(id=cid, form=form, frames=frames, layer=layer, root_movement=root,
             events=[dict(name=n, frame=f) for (n, f) in events],
             entry_states=list(entry), exit_states=list(exit))
    d.update(kw)
    d['loop'] = (form == 'loop')
    CLIPS.append(d)
    BY_ID[cid] = d
    return d


# ------------------------------------------------------------------------------------ idles
clip('idle_relaxed', 'loop', 120, 'base', entry=['locomotion', 'any_recovery'], exit=['locomotion', 'action', 'disable', 'death'])
clip('idle_combat', 'loop', 90, 'base', entry=['locomotion', 'action_end'], exit=['locomotion', 'action', 'disable', 'death'])
clip('idle_wounded', 'loop', 96, 'base', entry=['locomotion'], exit=['locomotion', 'action', 'disable', 'death'])

# ------------------------------------------------------------------------------------ locomotion
for d, ang in DIRS.items():
    clip('walk_' + d, 'loop', WALK_FRAMES, 'locomotion',
         events=[('foot_l_contact', 0), ('foot_r_contact', WALK_FRAMES // 2)],
         entry=['idle', 'locomotion'], exit=['idle', 'locomotion', 'action', 'disable', 'death'],
         nominal_speed=WALK_SPEED, travel_dir_deg=ang, gait='walk', phase_sync='foot_l_contact@0')
for d, ang in DIRS.items():
    clip('run_' + d, 'loop', RUN_FRAMES, 'locomotion',
         events=[('foot_l_contact', 0), ('foot_r_contact', RUN_FRAMES // 2)],
         entry=['idle', 'locomotion'], exit=['idle', 'locomotion', 'action', 'disable', 'death'],
         nominal_speed=RUN_SPEED, travel_dir_deg=ang, gait='run', phase_sync='foot_l_contact@0')
clip('sprint_f', 'loop', SPRINT_FRAMES, 'locomotion',
     events=[('foot_l_contact', 0), ('foot_r_contact', SPRINT_FRAMES // 2)],
     entry=['locomotion'], exit=['locomotion', 'action', 'disable', 'death'],
     nominal_speed=SPRINT_SPEED, travel_dir_deg=0.0, gait='sprint', phase_sync='foot_l_contact@0')
clip('start_f', 'one_shot', 12, 'base', events=[('foot_r_contact', 5), ('foot_l_contact', 11)],
     entry=['idle'], exit=['locomotion'], nominal_speed=RUN_SPEED, travel_dir_deg=0.0)
clip('stop_f', 'one_shot', 14, 'base', events=[('foot_r_contact', 3), ('foot_l_contact', 9)],
     entry=['locomotion'], exit=['idle'], nominal_speed=RUN_SPEED, travel_dir_deg=0.0)
clip('turn_l90', 'one_shot', 18, 'base', events=[('foot_l_contact', 8), ('foot_r_contact', 14)],
     entry=['idle'], exit=['idle'], turn_yaw_deg=90.0)
clip('turn_r90', 'one_shot', 18, 'base', events=[('foot_r_contact', 8), ('foot_l_contact', 14)],
     entry=['idle'], exit=['idle'], turn_yaw_deg=-90.0)
clip('pivot_l180', 'one_shot', 16, 'base', events=[('foot_r_contact', 4), ('foot_l_contact', 11)],
     entry=['locomotion'], exit=['locomotion'], turn_yaw_deg=180.0, nominal_speed=RUN_SPEED)
clip('pivot_r180', 'one_shot', 16, 'base', events=[('foot_l_contact', 4), ('foot_r_contact', 11)],
     entry=['locomotion'], exit=['locomotion'], turn_yaw_deg=-180.0, nominal_speed=RUN_SPEED)

# ------------------------------------------------------------------------------------ air
clip('jump_start', 'one_shot', 9, 'base', events=[('jump_takeoff', 6)], entry=['idle', 'locomotion'], exit=['jump_air'])
clip('jump_air', 'loop', 20, 'base', entry=['jump_start'], exit=['fall', 'jump_land', 'land_heavy'])
clip('jump_land', 'one_shot', 14, 'base', events=[('land_impact', 0), ('foot_l_contact', 0), ('foot_r_contact', 0)],
     entry=['jump_air', 'fall'], exit=['idle', 'locomotion'])
clip('fall', 'loop', 16, 'base', entry=['jump_air', 'locomotion'], exit=['jump_land', 'land_heavy'])
clip('land_heavy', 'one_shot', 26, 'base', events=[('land_impact', 0), ('foot_l_contact', 0), ('foot_r_contact', 0)],
     entry=['fall', 'knockup_air'], exit=['idle', 'locomotion'])

# ------------------------------------------------------------------------------------ dash / blink
for d, ang in (('f', 0.0), ('b', 180.0), ('l', 90.0), ('r', -90.0)):
    clip('dash_' + d, 'one_shot', 12, 'fullbody', root='root_motion',
         events=[('dash_start', 2), ('dash_end', 10)], entry=['idle', 'locomotion'], exit=['idle', 'locomotion'],
         root_displacement_cm=DASH_DISTANCE, travel_dir_deg=ang)
clip('blink_out', 'one_shot', 9, 'fullbody', events=[('blink_vanish', 8)], entry=['idle', 'locomotion'], exit=['blink_in'])
clip('blink_in', 'one_shot', 12, 'fullbody', events=[('blink_appear', 0), ('foot_l_contact', 3), ('foot_r_contact', 3)],
     entry=['blink_out'], exit=['idle', 'locomotion'])

# ------------------------------------------------------------------------------------ combat
clip('melee_1', 'one_shot', 24, 'fullbody', events=[('blade_extend', 2), ('hit_begin', 8), ('hit_end', 12), ('combo_window', 13), ('recovery', 16)],
     entry=['idle', 'locomotion'], exit=['melee_2', 'idle', 'locomotion'])
clip('melee_2', 'one_shot', 24, 'fullbody', events=[('hit_begin', 8), ('hit_end', 12), ('combo_window', 13), ('recovery', 16)],
     entry=['melee_1', 'idle', 'locomotion'], exit=['melee_3', 'idle', 'locomotion'])
clip('melee_3', 'one_shot', 33, 'fullbody', events=[('hit_begin', 12), ('hit_end', 17), ('recovery', 22), ('blade_retract', 27)],
     entry=['melee_2', 'idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('ranged_fire', 'one_shot', 10, 'upperbody', events=[('muzzle_1', 2), ('recovery', 5)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('ranged_burst', 'one_shot', 18, 'upperbody', events=[('muzzle_1', 2), ('muzzle_2', 6), ('muzzle_3', 10), ('recovery', 13)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('reload', 'one_shot', 60, 'upperbody',
     events=[('reload_eject', 14), ('reload_stow', 26), ('reload_grab_new', 31), ('reload_insert', 45), ('reload_done', 52)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('cast_directional', 'one_shot', 24, 'upperbody', events=[('cast_release', 11), ('recovery', 16)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('cast_ground', 'one_shot', 36, 'fullbody', events=[('cast_release', 18), ('recovery', 26)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('cast_self', 'one_shot', 30, 'fullbody', events=[('cast_release', 13), ('recovery', 21)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('channel_start', 'one_shot', 12, 'fullbody', events=[('channel_begin', 10)], entry=['idle', 'locomotion'], exit=['channel_loop', 'channel_interrupt', 'channel_end'])
clip('channel_loop', 'loop', 40, 'fullbody', events=[('channel_tick', 0), ('channel_tick', 20)], entry=['channel_start'], exit=['channel_end', 'channel_interrupt'])
clip('channel_end', 'one_shot', 15, 'fullbody', events=[('channel_complete', 3)], entry=['channel_loop', 'channel_start'], exit=['idle', 'locomotion'])
clip('channel_interrupt', 'one_shot', 12, 'fullbody', events=[('channel_interrupted', 0)], entry=['channel_loop', 'channel_start'], exit=['idle', 'locomotion'])
clip('charge_start', 'one_shot', 18, 'upperbody', events=[('charge_begin', 3), ('charge_ready', 17)], entry=['idle', 'locomotion'], exit=['charge_hold', 'charge_release', 'charge_cancel'])
clip('charge_hold', 'loop', 30, 'upperbody', events=[('charge_pulse', 0)], entry=['charge_start'], exit=['charge_release', 'charge_cancel'])
clip('charge_release', 'one_shot', 20, 'upperbody', events=[('charge_released', 4), ('recovery', 12)], entry=['charge_hold', 'charge_start'], exit=['idle', 'locomotion'])
clip('charge_cancel', 'one_shot', 14, 'upperbody', events=[('charge_cancelled', 2)], entry=['charge_hold', 'charge_start'], exit=['idle', 'locomotion'])
clip('deploy', 'one_shot', 45, 'fullbody', events=[('deploy_grab', 9), ('deploy_release', 27), ('recovery', 34)],
     entry=['idle', 'locomotion'], exit=['idle', 'locomotion'])
clip('uplink_start', 'one_shot', 20, 'fullbody', events=[('uplink_begin', 16)], entry=['idle', 'locomotion'], exit=['uplink_loop', 'uplink_cancel'])
clip('uplink_loop', 'loop', 45, 'fullbody', events=[('uplink_pulse', 0)], entry=['uplink_start'], exit=['uplink_end', 'uplink_cancel'])
clip('uplink_end', 'one_shot', 16, 'fullbody', events=[('uplink_complete', 5)], entry=['uplink_loop'], exit=['blink_out', 'idle'])
clip('uplink_cancel', 'one_shot', 13, 'fullbody', events=[('uplink_cancelled', 0)], entry=['uplink_loop', 'uplink_start'], exit=['idle', 'locomotion'])

# ------------------------------------------------------------------------------------ reactions / disables
for d, ang in (('f', 0.0), ('b', 180.0), ('l', 90.0), ('r', -90.0)):
    clip('hit_' + d, 'additive', 10, 'additive', events=[('hit_peak', 2)], entry=['any_alive'], exit=['any_alive'],
         additive=dict(space='local', base='frame_0'), hit_from_deg=ang)
clip('stun_start', 'one_shot', 15, 'fullbody', events=[('stun_begin', 0)], entry=['any_alive'], exit=['stun_loop'])
clip('stun_loop', 'loop', 60, 'fullbody', entry=['stun_start'], exit=['stun_end', 'death'])
clip('stun_end', 'one_shot', 18, 'fullbody', events=[('control_regained', 14)], entry=['stun_loop'], exit=['idle', 'locomotion'])
clip('knockback', 'one_shot', 24, 'fullbody', events=[('knockback_begin', 0), ('foot_l_contact', 14), ('foot_r_contact', 18), ('control_regained', 20)],
     entry=['any_alive'], exit=['idle', 'locomotion'])
clip('knockup_start', 'one_shot', 12, 'fullbody', events=[('knockup_launch', 2)], entry=['any_alive'], exit=['knockup_air'])
clip('knockup_air', 'loop', 30, 'fullbody', entry=['knockup_start'], exit=['knockdown_back', 'knockdown_front', 'land_heavy'])
clip('knockdown_front', 'one_shot', 36, 'fullbody', events=[('ground_impact', 20), ('settled', 32)], entry=['any_alive', 'knockup_air'], exit=['prone_front'])
clip('knockdown_back', 'one_shot', 36, 'fullbody', events=[('ground_impact', 20), ('settled', 32)], entry=['any_alive', 'knockup_air'], exit=['prone_back'])
clip('prone_front', 'loop', 75, 'fullbody', entry=['knockdown_front'], exit=['getup_front', 'death'])
clip('prone_back', 'loop', 75, 'fullbody', entry=['knockdown_back'], exit=['getup_back', 'death'])
clip('getup_front', 'one_shot', 54, 'fullbody', events=[('hand_plant', 10), ('foot_r_contact', 30), ('foot_l_contact', 40), ('control_regained', 48)],
     entry=['prone_front'], exit=['idle', 'locomotion'])
clip('getup_back', 'one_shot', 60, 'fullbody', events=[('hand_plant', 12), ('foot_l_contact', 34), ('foot_r_contact', 44), ('control_regained', 54)],
     entry=['prone_back'], exit=['idle', 'locomotion'])
clip('sleep_start', 'one_shot', 45, 'fullbody', events=[('sleep_begin', 0), ('settled', 40)], entry=['any_alive'], exit=['sleep_loop'])
clip('sleep_loop', 'loop', 90, 'fullbody', entry=['sleep_start'], exit=['sleep_end', 'death'])
clip('sleep_end', 'one_shot', 36, 'fullbody', events=[('control_regained', 30)], entry=['sleep_loop'], exit=['idle', 'locomotion'])

# ------------------------------------------------------------------------------------ death / respawn
clip('death_front', 'one_shot', 60, 'fullbody', events=[('death_begin', 0), ('ground_impact', 30), ('death_settled', 54)],
     entry=['any_alive'], exit=['dead_front'], final_pose='dead_front')
clip('death_back', 'one_shot', 66, 'fullbody', events=[('death_begin', 0), ('ground_impact', 36), ('death_settled', 60)],
     entry=['any_alive'], exit=['dead_back'], final_pose='dead_back')
clip('dead_front', 'pose', 1, 'fullbody', entry=['death_front'], exit=['respawn'], pose_of=('death_front', 'last'))
clip('dead_back', 'pose', 1, 'fullbody', entry=['death_back'], exit=['respawn'], pose_of=('death_back', 'last'))
clip('respawn', 'one_shot', 75, 'fullbody', events=[('respawn_materialize', 0), ('respawn_active', 40), ('control_regained', 68)],
     entry=['dead_front', 'dead_back'], exit=['idle'])

# ------------------------------------------------------------------------------------ social / speech
clip('greet', 'one_shot', 60, 'fullbody', entry=['idle'], exit=['idle'])
clip('victory', 'one_shot', 90, 'fullbody', entry=['idle'], exit=['idle'])
clip('defeat', 'one_shot', 84, 'fullbody', entry=['idle'], exit=['idle'])
def dialogue_timing():
    """Frame count and markers of the dialogue clip follow the alignment of the actual audio."""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'audio', 'dialogue_alignment.json')
    try:
        with open(path, encoding='utf-8') as fh:
            d = json.load(fh)
        if d.get('placeholder'):
            raise ValueError('placeholder alignment')
        f0 = int(d['clip']['audio_start_frame'])
        mk = d['markers']
        return int(d['clip']['frames']), [('line_start', f0), ('emotion_shift', f0 + int(round(mk['emotion_shift'] * FPS))),
                                         ('line_end', f0 + int(round(mk['line_end'] * FPS)))]
    except (OSError, ValueError, KeyError):
        return 450, [('line_start', 9), ('emotion_shift', 220), ('line_end', 420)]


_DLG_FRAMES, _DLG_EVENTS = dialogue_timing()
clip('dialogue', 'one_shot', _DLG_FRAMES, 'fullbody', events=_DLG_EVENTS,
     entry=['idle'], exit=['idle'], audio='source/audio/dialogue.wav', alignment='source/audio/dialogue_alignment.json')

# ------------------------------------------------------------------------------------ aim grid
AIM_YAW = {'left': 60.0, 'center': 0.0, 'right': -60.0}     # +yaw = towards the character's left
AIM_PITCH = {'down': -35.0, 'level': 0.0, 'up': 35.0}       # +pitch = up
for pn, pv in AIM_PITCH.items():
    for yn, yv in AIM_YAW.items():
        clip('aim_%s_%s' % (pn, yn), 'pose', 1, 'aim', entry=['aim_layer'], exit=['aim_layer'],
             aim_yaw_deg=yv, aim_pitch_deg=pv, additive=dict(space='mesh', base='aim_level_center'))

# prop handling metadata (which bone carries which prop during which frames); filled by animation authoring
PROP_BONES = ['prop_cell', 'prop_cell_spare', 'prop_beacon', 'blade_l']


def duration(c):
    return c['frames'] / float(FPS)


def check_against_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    ids = [r['id'] for r in rows]
    assert len(ids) == 96, len(ids)
    mine = [c['id'] for c in CLIPS]
    assert mine == ids, ('order/content mismatch', [a for a in ids if a not in mine], [a for a in mine if a not in ids],
                         [(a, b) for a, b in zip(ids, mine) if a != b][:3])
    problems = []
    for r, c in zip(rows, CLIPS):
        if r['form'] != c['form'] or r['root_movement'] != c['root_movement']:
            problems.append((r['id'], 'form/root'))
        ds = r['duration_seconds']
        if ds != 'pose':
            lo, hi = [float(x) for x in ds.replace('–', '-').split('-')]
            d = duration(c)
            if not (lo - 1e-6 <= d <= hi + 1e-6):
                problems.append((r['id'], 'duration %.3f not in [%s, %s]' % (d, lo, hi)))
    return problems

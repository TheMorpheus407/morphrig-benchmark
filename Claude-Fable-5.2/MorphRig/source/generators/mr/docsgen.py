"""Writers for the machine readable delivery documents (skeleton, sockets, manifest, face mapping)."""
import json
import math
import os
import numpy as np
from . import skel, clips, facedefs


def _r(v, nd=6):
    return [round(float(x), nd) for x in v]


def _uvec(v):
    """Blender direction -> Unreal direction (y flipped)."""
    return [round(float(v[0]), 6), round(float(-v[1]), 6), round(float(v[2]), 6)]


def skeleton_doc(placeholder=False):
    bones = []
    for i, b in enumerate(skel.BONES):
        fr = skel.bone_frame(b['name'])
        flags = b['flags']
        role = 'deform'
        if 'T' in flags:
            role = 'twist (procedural, baked + recomputed at runtime)'
        elif 'H' in flags:
            role = 'half-rotation corrective helper (procedural, baked + recomputed at runtime)'
        elif 'P' in flags:
            role = 'prop carrier'
        elif 'F' in flags:
            role = 'face'
        elif 'S' in flags:
            role = 'secondary motion chain'
        bones.append(dict(
            index=i, name=b['name'], parent=b['parent'], role=role,
            blender_head_m=_r(b['head']), blender_tail_m=_r(b['tail']),
            blender_axes=dict(x=_r(fr[:, 0]), y=_r(fr[:, 1]), z=_r(fr[:, 2])),
            unreal_ref_position_cm=_r(skel.to_unreal_pos(b['head']), 4),
            unreal_axes=dict(x=_uvec(fr[:, 0]), y=_uvec(-fr[:, 1]), z=_uvec(fr[:, 2])),
            length_cm=round(float(np.linalg.norm(b['tail'] - b['head'])) * 100.0, 4)))
    socks = []
    for s in skel.SOCKETS.values():
        socks.append(dict(name=s['name'], bone=s['bone'], blender_position_m=_r(s['pos']),
                          blender_forward=_r(s['fwd']), blender_up=_r(s['up']),
                          unreal_position_cm=_r(skel.to_unreal_pos(s['pos']), 4),
                          unreal_forward=_uvec(s['fwd']), unreal_up=_uvec(s['up'])))
    from .armature import HELPER_RULES
    return dict(
        schema='morphrig.skeleton_and_sockets/1',
        placeholder=placeholder,
        units=dict(blender='metres, scene unit scale 1.0', unreal='centimetres, import uniform scale 1.0',
                   export_conversion='export_and_bake converts joint/mesh/translation data x100 in memory and writes '
                                     'the FBX in centimetres with unit scale factors of 1 (see docs/build_and_import_instructions.md)'),
        conventions=dict(
            blender='right handed, +Z up, character faces -Y, character left = +X, ground z = 0, origin between the feet',
            unreal='left handed, +Z up, mesh faces +Y, character left = +X (component space = Blender (x, -y, z) * 100); '
                   'the character actor rotates the mesh component by yaw -90 so the actor faces +X',
            bone_local_blender='Y along the bone (head->tail), Z towards the listed z axis, X = Y x Z',
            bone_local_unreal='Unreal bone local axes are the Blender axes mapped by (x, -y, z): the bone runs along local -Y',
            rotation_signs='Blender bone-local rotation (axis a, angle t) equals Unreal bone-local rotation (axis (ax,-ay,az), angle -t); '
                           'quaternion (w,x,y,z)_blender -> (w,-x,y,-z)_unreal',
            root='single root bone "root" at the origin with identity rest orientation; pelvis is its child',
            height_cm=180.0),
        bone_count=len(bones), bones=bones,
        procedural_bones={k: dict(kind=v[0], driver=v[1], amount=v[2]) for k, v in HELPER_RULES.items()},
        procedural_rules=dict(
            half='local rotation = slerp(identity, driver local rotation relative to its rest pose, amount)',
            untwist='child of driver: local rotation = inverse(twist of driver local rotation about the bone axis) * amount',
            twist='sibling of driver under the same parent chain: local rotation = twist of driver local rotation about the bone axis * amount'),
        sockets=socks)


def face_doc():
    def conv_bone_controls():
        out = {}
        for ctl, items in facedefs.BONE_CONTROLS.items():
            lst = []
            for (bone, kind, axis, amount) in items:
                ax = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[axis]
                if kind == 'rot':
                    h = math.radians(amount) / 2.0
                    qb = (math.cos(h), ax[0] * math.sin(h), ax[1] * math.sin(h), ax[2] * math.sin(h))
                    qu = (qb[0], -qb[1], qb[2], -qb[3])
                    lst.append(dict(bone=bone, kind='rot', blender_axis=axis, degrees=amount,
                                    blender_quat_wxyz=_r(qb, 8), unreal_quat_xyzw=_r((qu[1], qu[2], qu[3], qu[0]), 8)))
                else:
                    vb = [ax[0] * amount, ax[1] * amount, ax[2] * amount]
                    lst.append(dict(bone=bone, kind='loc', blender_axis=axis, metres=amount,
                                    blender_loc_m=_r(vb, 6), unreal_loc_cm=_r((vb[0] * 100, -vb[1] * 100, vb[2] * 100), 5)))
            out[ctl] = lst
        return out

    return dict(
        schema='morphrig.face_controls/1',
        description='Face control vocabulary. Controls are 0..1 channels; morph controls drive the morph target of the same '
                    'name, bone controls add the listed bone-local offsets (scaled linearly; rotations by slerp from identity). '
                    'Visemes and expressions are linear combinations of controls. '
                    'final(control) = clamp01(direct + sum(viseme*w) + sum(expression*w)).',
        morph_targets=list(facedefs.MORPHS),
        controls=list(facedefs.CONTROLS),
        bone_controls=conv_bone_controls(),
        eye_look=dict(facedefs.EYE_LOOK, bones=['eye_l', 'eye_r'],
                      note='eye bones aim along their local Y (Blender) / -Y (Unreal); lids add follow * eye pitch about their local X'),
        visemes={k: dict(phonemes=v[0], controls=v[1]) for k, v in facedefs.VISEMES.items()},
        expressions=dict(facedefs.EXPRESSIONS))


def manifest_doc(clip_infos, placeholder=False):
    """clip_infos: {id: dict(frames=..., events=[...], extra...)} measured at bake time."""
    out = []
    for c in clips.CLIPS:
        info = clip_infos.get(c['id'], {})
        frames = int(info.get('frames', c['frames']))
        is_pose = c['form'] == 'pose'
        n_samples = 2 if is_pose else frames + 1
        dur = (1.0 if is_pose else frames) / clips.FPS
        events = info.get('events', c['events'])
        ev = [dict(name=e['name'], frame=int(e['frame']), time=round(e['frame'] / clips.FPS, 6),
                   normalized=round(e['frame'] / float(max(1, frames)), 6)) for e in events]
        d = dict(
            id=c['id'], form=c['form'], root_movement=c['root_movement'],
            source_action=info.get('source_action', c['id']), baked_action=info.get('baked_action', 'BAKED_' + c['id']),
            export_file='export/animations/%s.fbx' % c['id'], take=c['id'],
            unreal_asset='/Game/Operative/Animations/%s.%s' % (c['id'], c['id']),
            frame_start=0, frame_end=(1 if is_pose else frames), sample_count=n_samples, sample_rate=clips.FPS,
            duration=round(dur, 6), loop=bool(c['loop']), is_pose=is_pose,
            root_motion=dict(policy=c['root_movement'],
                             displacement_cm=info.get('root_displacement_cm', [0.0, 0.0, 0.0]),
                             note='Unreal component space (x = character left, y = forward, z = up)'),
            layer=c['layer'], events=ev, entry_states=c['entry_states'], exit_states=c['exit_states'])
        for k in ('nominal_speed', 'travel_dir_deg', 'gait', 'phase_sync', 'turn_yaw_deg', 'aim_yaw_deg', 'aim_pitch_deg',
                  'additive', 'hit_from_deg', 'final_pose', 'pose_of', 'audio'):
            if k in c:
                d[k if k != 'nominal_speed' else 'nominal_speed_cm_s'] = c[k]
        if info.get('prop_tracks'):
            d['prop_tracks'] = info['prop_tracks']
        if 'procedural' in info:
            d['procedural_components'] = info['procedural']
        notes = info.get('notes') or {}
        if 'speed_profile' in notes:
            d['speed_profile'] = [round(float(v), 4) for v in notes['speed_profile']]
            d['speed_profile_cm_s'] = [round(float(v) * 100.0, 2) for v in notes['speed_profile']]
            d['speed_profile_note'] = 'ground speed along the facing at clip start, one value per frame (m/s and cm/s); the clip is authored in place'
        for k in ('exit_phase', 'entry_phase', 'entry_loop', 'exit_loop', 'turn_yaw_deg', 'prop_swap', 'cycle_frames'):
            if k in notes:
                d[k] = notes[k]
        if 'root_travel' in notes:
            d['root_motion']['travel_m'] = [round(float(v), 4) for v in notes['root_travel']]
        if info.get('floor_contact'):
            d['floor_contact'] = True
        if 'source_keys' in info:
            d['source_keys'] = info['source_keys']
        if 'qa' in info:
            d['qa'] = info['qa']
        out.append(d)
    return dict(
        schema='morphrig.animation_manifest/1', placeholder=placeholder, fps=clips.FPS,
        counts=dict(total=len(out), motions=sum(1 for c in out if not c['is_pose']), poses=sum(1 for c in out if c['is_pose'])),
        conventions=dict(
            frames='frame_start..frame_end inclusive at 30 fps; duration = (frame_end - frame_start) / 30; loops repeat their first pose on the last frame',
            poses='static entries are exported as two identical frames (duration 1/30 s) so they import as ordinary pose clips',
            travel_dir_deg='0 = forward, +90 = character left, measured counter-clockwise seen from above',
            aim='yaw + = towards the character left, pitch + = up; grid yaw -60/0/+60, pitch -35/0/+35',
            events='event frames are clip-local; Unreal notifies are created from this list at import',
            prop_tracks='frames during which a prop bone is carried by another bone than its rest parent (holder = bone name, or "world" = stays where it was released, in root space)',
            floor_contact='clips whose hands / knees / torso rest on the floor: play them without foot IK or additive layers',
            source_keys='sparse = hand keyed poses on the control rig; dense = one key per frame on the control rig (floor-constrained or simulated channels)',
            qa='measured on the baked skeleton: loop_error (max joint channel difference between first and last frame), slide_max_cm_s (planted foot speed relative to the ground speed), min_sole_height_cm, body_clear_cm',
            nominal_speeds_cm_s=dict(walk=clips.WALK_SPEED, run=clips.RUN_SPEED, sprint=clips.SPRINT_SPEED)),
        clips=out)


def write_json(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
        f.write('\n')

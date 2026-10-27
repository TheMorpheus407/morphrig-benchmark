#!/usr/bin/env python3
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parents[2]
DURATIONS = {
    "idle_relaxed": 90, "idle_combat": 90, "idle_wounded": 90,
    "sprint_f": 18, "start_f": 18, "stop_f": 18,
    "turn_l90": 24, "turn_r90": 24, "pivot_l180": 24, "pivot_r180": 24,
    "jump_start": 18, "jump_air": 24, "jump_land": 24, "fall": 30, "land_heavy": 30,
    "blink_out": 12, "blink_in": 12,
    "melee_1": 30, "melee_2": 30, "melee_3": 36,
    "ranged_fire": 12, "ranged_burst": 18, "reload": 60,
    "cast_directional": 30, "cast_ground": 36, "cast_self": 30,
    "channel_start": 15, "channel_loop": 36, "channel_end": 18, "channel_interrupt": 12,
    "charge_start": 24, "charge_hold": 36, "charge_release": 24, "charge_cancel": 15,
    "deploy": 48, "uplink_start": 24, "uplink_loop": 48, "uplink_end": 18, "uplink_cancel": 15,
    "stun_start": 24, "stun_loop": 48, "stun_end": 24,
    "knockback": 24, "knockup_start": 18, "knockup_air": 36,
    "knockdown_front": 66, "knockdown_back": 66, "prone_front": 60, "prone_back": 60,
    "getup_front": 90, "getup_back": 90,
    "sleep_start": 72, "sleep_loop": 90, "sleep_end": 72,
    "death_front": 96, "death_back": 99, "respawn": 84,
    "greet": 66, "victory": 90, "defeat": 72, "dialogue": 456,
}
for direction in ("f", "fl", "l", "bl", "b", "br", "r", "fr"):
    DURATIONS["walk_" + direction] = 36
    DURATIONS["run_" + direction] = 24
for direction in ("f", "b", "l", "r"):
    DURATIONS["dash_" + direction] = 18
for direction in ("f", "b", "l", "r"):
    DURATIONS["hit_" + direction] = 9


def layer_for(name, form):
    if name.startswith("aim_") or name in ("ranged_fire", "ranged_burst", "cast_directional"):
        return "upper_body"
    if form == "additive":
        return "additive_upper_body"
    if name.startswith("dash_"):
        return "full_body_root_motion"
    if name.startswith("walk_") or name.startswith("run_") or name in ("idle_relaxed", "idle_combat", "idle_wounded", "sprint_f", "start_f", "stop_f"):
        return "locomotion_full_body"
    if name == "dialogue":
        return "full_body_face_audio"
    return "full_body_action"


def state_for(name, form):
    if name.startswith("aim_"): return "Aim"
    if name.startswith(("dead", "death")): return "Dead"
    if name.startswith(("knock", "prone", "getup", "stun", "sleep")): return "Incapacitated"
    if name.startswith("channel_"): return "Channel"
    if name.startswith("charge_"): return "Charge"
    if name.startswith("uplink_"): return "Uplink"
    if name.startswith(("walk", "run")) or name == "sprint_f": return "Travel"
    if form == "loop": return "Idle"
    if form == "additive": return "HitAdditive"
    return "Action"


def exit_state_for(name, form):
    if name.startswith(("death", "dead")): return "Dead"
    if name in ("channel_start", "channel_loop"): return "Channel"
    if name in ("charge_start", "charge_hold"): return "Charge"
    if name in ("uplink_start", "uplink_loop"): return "Uplink"
    if name in ("stun_start", "stun_loop"): return "Stun"
    if name in ("sleep_start", "sleep_loop"): return "Sleep"
    if name in ("knockup_start", "knockup_air", "knockdown_front", "knockdown_back", "prone_front", "prone_back"): return "Incapacitated"
    if name.startswith("aim_"): return "Aim"
    if form == "additive": return "Previous"
    if name == "start_f" or name.startswith("turn_") or name.startswith("pivot_"): return "Travel"
    if name.startswith(("walk", "run")) or name == "sprint_f": return "Travel"
    return "Idle"


def markers_for(name, frames, form):
    def event(event_name, fraction, kind="gameplay", value=0):
        frame = min(frames, max(0, round(fraction * frames)))
        return {"name": event_name, "frame": frame, "time": round(frame / 30, 6), "type": kind, "value": value}
    events = [event("LoopStart" if form == "loop" else "PoseSample" if form == "pose" else "ActionStart", 0, "state")]
    if name.startswith(("walk_", "run_")) or name == "sprint_f":
        events += [event("FootPlant.L", 0, "contact"), event("FootPlant.R", .5, "contact"), event("FootRelease.L", .60, "contact"), event("FootRelease.R", .10, "contact")]
    elif name.startswith("melee_"):
        events += [event("MeleeWindowBegin", .32, "hit_window"), event("MeleeWindowEnd", .56, "hit_window"), event("Recovery", .66, "state")]
    elif name == "ranged_fire":
        events += [event("MuzzleFire", .28, "muzzle"), event("Recovery", .64, "state")]
    elif name == "ranged_burst":
        events += [event("MuzzleFire", .16, "muzzle", 1), event("MuzzleFire", .45, "muzzle", 2), event("MuzzleFire", .73, "muzzle", 3), event("Recovery", .88, "state")]
    elif name == "reload":
        events += [event("CellGrip", .25, "attachment"), event("CellDetach", .43, "attachment"), event("CellSeat", .76, "attachment"), event("CellRelease", .88, "attachment"), event("Recovery", .94, "state")]
    elif name.startswith("cast_"):
        events += [event("CastRelease", .53, "effect"), event("Recovery", .75, "state")]
    elif name.startswith("channel_"):
        events += [event("Channel" + name.split("_")[1].title(), .85 if name.endswith("start") else .48, "state")]
    elif name.startswith("charge_"):
        events += [event("Charge" + name.split("_")[1].title(), .80 if name.endswith("start") else .48, "state")]
    elif name == "deploy":
        events += [event("DeployGrip", .17, "attachment"), event("DeployContact", .63, "attachment"), event("DeployRelease", .73, "attachment"), event("Recovery", .92, "state")]
    elif name.startswith("uplink_"):
        events += [event("Uplink" + name.split("_")[1].title(), .84 if name.endswith("start") else .5, "state")]
    elif name.startswith("hit_"):
        events += [event("HitPeak", .35, "reaction")]
    elif name == "blink_out":
        events += [event("TeleportOut", .65, "teleport")]
    elif name == "blink_in":
        events += [event("TeleportIn", .05, "teleport"), event("LandingContact", .35, "contact")]
    elif name == "jump_start":
        events += [event("Takeoff", .70, "movement")]
    elif name in ("jump_land", "land_heavy"):
        events += [event("LandingContact", .20, "contact"), event("Recovery", .66, "state")]
    elif name.startswith("turn_") or name.startswith("pivot_"):
        events += [event("FootPivot", .43, "contact"), event("FacingCommit", .90, "movement", 90 if "l90" in name else -90 if "r90" in name else 180 if "l180" in name else -180)]
    elif name.startswith("dash_"):
        events += [event("CapsuleDrive", 0, "root_motion", 200), event("DashEnd", 1, "root_motion")]
    elif name.startswith("death_"):
        events += [event("DeathImpact", .12, "priority"), event("DeathSettled", .94, "state")]
    elif name == "respawn":
        events += [event("Reconstruct", .2, "effect"), event("RespawnLiving", .86, "state")]
    elif name == "dialogue":
        events += [event("SpeechStart", 0, "audio"), event("GestureLane", .14, "acting"), event("GestureNetwork", .32, "acting"), event("LookLeft", .43, "acting"), event("EmotionConcern", .47, "face"), event("GestureStabilize", .66, "acting"), event("EmotionConfidence", .79, "face"), event("SpeechEnd", .982, "audio")]
    if form not in ("loop", "pose"):
        events.append(event("ActionEnd", 1, "state"))
    unique = {}
    for item in events:
        unique[(item["name"], item["frame"], item["value"])] = item
    return list(unique.values())


def prepare():
    source = ROOT / "source" / "required_animations.csv"
    if not source.exists():
        source = ROOT.parent / "required_animations.csv"
    with source.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    inventory = []
    for row in rows:
        name = row["id"]
        form = row["form"]
        frames = DURATIONS.get(name, 0 if form == "pose" else None)
        if frames is None:
            raise KeyError("No authored frame count for " + name)
        if name.startswith("walk_"): speed = 150
        elif name.startswith("run_"): speed = 400
        elif name == "sprint_f": speed = 650
        elif name.startswith("dash_"): speed = 200 / (frames / 30)
        else: speed = 0
        aim = None
        if name.startswith("aim_"):
            _, pitch, yaw = name.split("_")
            aim = {"yaw_left_degrees": {"left": 60, "center": 0, "right": -60}[yaw], "pitch_up_degrees": {"down": -35, "level": 0, "up": 35}[pitch]}
        inventory.append({
            "id": name, "form": form, "root_motion_policy": row["root_movement"],
            "duration_seconds": frames / 30 if form != "pose" else 0,
            "duration_range_seconds": row["duration_seconds"], "required_behavior": row["required_behavior"],
            "frame_range": [0, frames], "frame_count": frames + 1, "sample_rate": 30,
            "loop": form == "loop", "nominal_speed_cm_s": round(speed, 4),
            "nominal_root_displacement_m": [0, -2, 0] if name == "dash_f" else [0, 2, 0] if name == "dash_b" else [-2, 0, 0] if name == "dash_r" else [2, 0, 0] if name == "dash_l" else [0, 0, 0],
            "layer": layer_for(name, form), "entry_state": state_for(name, form), "exit_state": exit_state_for(name, form),
            "source_action": name, "editable_control_action": "SOURCE_" + name,
            "exported_file": "animations/" + name + ".fbx", "exported_take": name,
            "unreal_asset": "/Game/Operative/Animations/" + name,
            "events": markers_for(name, frames, form), "aim": aim,
            "additive_reference": "idle_relaxed" if form == "additive" else None,
        })
    assert len(inventory) == 96 and len({entry["id"] for entry in inventory}) == 96
    assert sum(entry["form"] == "pose" for entry in inventory) == 11
    (ROOT / "source" / "animation_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')
    print("Prepared", len(inventory), "required animation entries")


if __name__ == "__main__":
    prepare()

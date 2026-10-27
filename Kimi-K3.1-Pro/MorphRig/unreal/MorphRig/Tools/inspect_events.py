from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
mesh = unreal.load_asset("/Game/Operative/SK_Operative")
sequence = unreal.EditorAssetLibrary.duplicate_asset("/Game/Operative/Animations/dash_f", "/Game/Operative/Diagnostics/EventProbe")
lib = unreal.AnimationLibrary
result = {"steps": [], "controller_notify_api": {name: getattr(unreal.AnimationDataController, name).__doc__ for name in dir(unreal.AnimationDataController) if "notify" in name}}
result["initial_tracks"] = [str(name) for name in lib.get_animation_notify_track_names(sequence)]
result["remove_result"] = lib.remove_animation_notify_events_by_track(sequence, "MorphEvents")
result["remaining_tracks"] = [str(name) for name in lib.get_animation_notify_track_names(sequence)]
def snapshot(label, returned=None):
    stored = lib.get_animation_notify_events(sequence)
    result["steps"].append({"step": label, "returned": {"path": returned.get_path_name(), "event": str(returned.get_editor_property("event_name"))} if returned else None, "stored": [{"path": event.get_editor_property("notify").get_path_name(), "event": str(event.get_editor_property("notify").get_editor_property("event_name")), "timeline": str(event.get_editor_property("notify_name"))} for event in stored]})
first = lib.add_animation_notify_event(sequence, "MorphEvents", 0.0, unreal.MorphEventNotify)
snapshot("created first", first)
first.set_editor_property("event_name", "ActionStart")
snapshot("set returned", first)
stored_first = lib.get_animation_notify_events(sequence)[0].get_editor_property("notify")
stored_first.set_editor_property("event_name", "ActionStart")
snapshot("set stored", first)
default = unreal.MorphEventNotify.get_default_object()
default.set_editor_property("event_name", "DashEnd")
result["default_after_set"] = str(default.get_editor_property("event_name"))
second = lib.add_animation_notify_event(sequence, "MorphEvents", 0.6, unreal.MorphEventNotify)
snapshot("created second", second)
for event in lib.get_animation_notify_events(sequence):
    notify = event.get_editor_property("notify")
    unreal.MorphAuditLibrary.set_notify_name(sequence, notify, notify.get_editor_property("event_name"))
snapshot("set timeline names", first)
path = ROOT / "docs" / "validation" / "native_event_probe.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2), flush=True)

from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
source = (ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py").read_text()
namespace = {"__file__": str(ROOT / "unreal" / "MorphRig" / "Tools" / "import_operative.py")}
exec(source[:source.index("\ntry:\n    main()")], namespace)
mesh = unreal.load_asset("/Game/Operative/SK_Operative")
if mesh is None:
    raise RuntimeError("Run the production mesh import before the pose probe")
result = {"candidates": []}
for label, mode, end in (("exported_time", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, 1), ("one_frame_range", unreal.FBXAnimationLengthImportType.FBXALIT_SET_RANGE, 1)):
    try:
        options = namespace["animation_options"](mesh.skeleton)
        options.anim_sequence_import_data.set_editor_property("animation_length", mode)
        options.anim_sequence_import_data.set_editor_property("frame_import_range", unreal.Int32Interval(min=0, max=end))
        objects = namespace["run_task"](ROOT / "export" / "animations" / "dead_front.fbx", "/Game/Operative/Diagnostics", "Pose_" + label, options, unreal.FbxFactory())
        sequence = next((obj for obj in objects if isinstance(obj, unreal.AnimSequence)), None)
        if sequence is None:
            result["candidates"].append({"mode": label, "asset": None})
            continue
        model = sequence.get_editor_property("data_model_interface")
        get_frames = getattr(model, "get_num_frames", None)
        result["candidates"].append({"mode": label, "asset": sequence.get_path_name(), "duration": sequence.get_play_length(), "tracks": model.get_num_bone_tracks(), "frames": get_frames() if callable(get_frames) else None, "root": str(unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, "root", 0, False))})
    except Exception as error:
        result["candidates"].append({"mode": label, "error": str(error)})
path = ROOT / "docs" / "validation" / "native_pose_options.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print("POSE_CANDIDATES", json.dumps(result), flush=True)

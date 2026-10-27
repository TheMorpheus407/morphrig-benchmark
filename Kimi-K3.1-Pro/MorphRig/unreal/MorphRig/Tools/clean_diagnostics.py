from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[3]
library = unreal.EditorAssetLibrary
editor = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
path = "/Game/Operative/Diagnostics"
assets = library.list_assets(path, recursive=True, include_folder=False) if library.does_directory_exist(path) else []
clip_ids = tuple(entry["id"] for entry in json.loads((ROOT / "docs" / "animation_manifest.json").read_text())["entries"])
allowed = ("Pose_", "UnitProbe", "DashProbe", "EventProbe", "SK_AxesUp_", "idle_axes_up_", "Operative_LOD0_", "SK_Operative_LegacySkeleton", "SK_Operative_BasisSource", "idle_relaxed_basis_source", "dash_l_basis_source", "AnimationSource", "SK_AnimationSource", "SK_Operative_PreviousMesh", "SourceProbe", "original_idle", "diagonal_idle") + clip_ids
retained = set()
unexpected = []
deleted = []
animation_assets = sorted(asset for asset in assets if unreal.load_asset(asset).get_class().get_name() == "AnimSequence")
other_assets = sorted(asset for asset in assets if unreal.load_asset(asset).get_class().get_name() != "AnimSequence")
for index, asset in enumerate(animation_assets + other_assets):
    if index == len(animation_assets):
        unreal.SystemLibrary.collect_garbage()
    if asset in retained:
        continue
    if not asset.rsplit("/", 1)[-1].startswith(allowed):
        unexpected.append(asset)
        continue
    if unreal.load_asset(asset).get_class().get_name() in ("AnimSequence", "SkeletalMesh"):
        item = unreal.load_asset(asset)
        skeleton = item.get_editor_property("skeleton")
        if skeleton is None or not library.does_asset_exist(skeleton.get_path_name().split(".")[0]):
            production_skeleton = unreal.load_asset("/Game/Operative/SK_Operative_Skeleton")
            if not production_skeleton:
                raise RuntimeError("Cannot restore a diagnostic skeleton reference before deletion")
            if not unreal.MorphAuditLibrary.rebind_skeleton_for_cleanup(item, production_skeleton):
                raise RuntimeError("Could not rebind a diagnostic skeleton before deletion")
    if not editor.delete_asset(asset):
        raise RuntimeError("Could not delete diagnostic asset " + asset)
    deleted.append(asset)
if unexpected:
    raise RuntimeError("Unexpected assets left for explicit review: " + repr(unexpected))
if library.does_directory_exist(path) and not library.list_assets(path, recursive=True, include_folder=False):
    library.delete_directory(path)
report = {"deleted_assets": deleted, "retained_assets": sorted(retained), "unexpected_assets": unexpected}
(ROOT / "docs" / "validation" / "native_diagnostics_cleanup.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)

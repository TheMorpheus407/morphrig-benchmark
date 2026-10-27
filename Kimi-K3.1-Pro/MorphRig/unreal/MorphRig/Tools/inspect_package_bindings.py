import json
import unreal

result = {}
for name in ("load_package", "new_object", "create_package", "load_asset"):
    value = getattr(unreal, name, None)
    result[name] = {"present": value is not None, "doc": getattr(value, "__doc__", None)}
result["package_members"] = [name for name in dir(unreal) if "package" in name]
for name in ("duplicate_asset", "rename_asset", "delete_asset"):
    value = getattr(unreal.EditorAssetLibrary, name, None)
    result[name] = getattr(value, "__doc__", None)
result["factory_properties"] = [name for name in dir(unreal.SkeletonFactory()) if "target" in name or "mesh" in name]
package = unreal.load_package("/Game/Operative/Diagnostics/PackageProbe")
if not package:
    raise RuntimeError("load_package could not create a new package")
skeleton = unreal.new_object(unreal.Skeleton, outer=package, name="PackageProbe")
result["unsaved_skeleton"] = skeleton.get_path_name() if skeleton else None
result["unsaved_bone_count"] = len(skeleton.get_reference_pose().get_bone_names()) if skeleton else -1
unreal.log_warning(json.dumps(result, indent=2))

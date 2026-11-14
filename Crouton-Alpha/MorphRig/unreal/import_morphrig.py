import unreal, os, json
PROJ = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(os.path.dirname(PROJ), "export")
LOG = "/tmp/import_out.txt"
def log(s):
    with open(LOG, "a") as fh: fh.write(s + "\n")
log("import starting")
SKEL_PATH = "/Game/MorphRig/Meshes/Operative_Deform_Skeleton"

def save(p):
    try: unreal.EditorAssetLibrary.save_asset(p, False)
    except: pass

# 1) base mesh (only if skeleton missing)
skel = None
try: skel = unreal.EditorAssetLibrary.load_asset(SKEL_PATH)
except: pass
base = os.path.join(EXPORT, "Operative.fbx")
if skel is None and os.path.exists(base):
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_animations", True)
    opts.set_editor_property("import_as_skeletal", True)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    opts.set_editor_property("import_materials", True)
    opts.set_editor_property("import_textures", True)
    opts.set_editor_property("create_physics_asset", False)
    opts.set_editor_property("automated_import_should_detect_type", False)
    task = unreal.AssetImportTask()
    task.filename = base; task.destination_path = "/Game/MorphRig/Meshes"; task.options = opts; task.replace_existing = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    log("base -> " + str(task.imported_object_paths))
    for p in task.imported_object_paths: save(p)
    skel = unreal.EditorAssetLibrary.load_asset(SKEL_PATH)
log("skel ready: " + str(skel is not None))

manifest = json.load(open(os.path.join(os.path.dirname(PROJ), "docs", "animation_manifest.json")))
for i, entry in enumerate(manifest["animations"]):
    src = os.path.join(EXPORT, "animations", entry["id"] + ".fbx")
    if not os.path.exists(src):
        log("missing " + src); continue
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", False)
    opts.set_editor_property("import_animations", True)
    opts.set_editor_property("import_as_skeletal", True)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    opts.set_editor_property("skeleton", skel)
    opts.set_editor_property("import_materials", False)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("create_physics_asset", False)
    opts.set_editor_property("automated_import_should_detect_type", False)
    task = unreal.AssetImportTask()
    task.filename = src; task.destination_path = "/Game/MorphRig/Animations"; task.options = opts; task.replace_existing = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    for p in task.imported_object_paths: save(p)
    if i % 16 == 0 or i == len(manifest["animations"])-1:
        types = []
        for p in task.imported_object_paths:
            a = unreal.EditorAssetLibrary.load_asset(p)
            types.append(type(a).__name__ if a else "None")
        log("progress %d/%d %s -> %s %s" % (i, len(manifest["animations"]), os.path.basename(src), str(task.imported_object_paths)[:80], str(types)))
log("animations done")
aud = os.path.join(os.path.dirname(PROJ), "source", "audio", "dialogue.wav")
if os.path.exists(aud):
    task = unreal.AssetImportTask()
    task.filename = aud; task.destination_path = "/Game/MorphRig/Audio"; task.replace_existing = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    log("audio " + str(task.imported_object_paths))
    for p in task.imported_object_paths: save(p)
try:
    unreal.EditorAssetLibrary.save_directory("/Game/MorphRig", True, False); log("saved dir")
except Exception as e: log("save dir err " + str(e))
log("IMPORT DONE")

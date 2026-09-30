"""Shared helpers for the Unreal import scripts."""
import os
import json
import unreal

GAME = "/Game/Operative"
MESH_DIR = GAME + "/Mesh"
ANIM_DIR = GAME + "/Anims"
PROP_DIR = GAME + "/Props"
MAT_DIR = GAME + "/Materials"
TEX_DIR = GAME + "/Textures"
AUDIO_DIR = GAME + "/Audio"
SHOWCASE_DIR = "/Game/Showcase"
MESH_NAME = "SK_Operative"
SKELETON_PATH = MESH_DIR + "/" + MESH_NAME + "_Skeleton"
MESH_PATH = MESH_DIR + "/" + MESH_NAME
DATA_ASSET = GAME + "/DA_OperativeAssets"


def log(*a):
    unreal.log("MRIMPORT " + " ".join(str(x) for x in a))


def warn(*a):
    unreal.log_warning("MRIMPORT " + " ".join(str(x) for x in a))


class Context(object):
    def __init__(self, root):
        self.root = root
        self.export = os.path.join(root, "export")
        self.docs = os.path.join(root, "docs")
        self.source = os.path.join(root, "source")
        self.manifest = json.load(open(os.path.join(self.docs, "animation_manifest.json")))
        self.skeleton_doc = json.load(open(os.path.join(self.docs, "skeleton_and_sockets.json")))
        self.state = {}


def asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def eal():
    return unreal.EditorAssetLibrary


def import_task(filename, dest_path, dest_name, options=None, save=True):
    t = unreal.AssetImportTask()
    t.filename = filename
    t.destination_path = dest_path
    t.destination_name = dest_name
    t.automated = True
    t.replace_existing = True
    t.replace_existing_settings = True
    t.save = save
    if options is not None:
        t.options = options
    return t


def run_tasks(tasks):
    asset_tools().import_asset_tasks(tasks)
    return [[str(p) for p in t.imported_object_paths] for t in tasks]


def load(path):
    a = unreal.load_asset(path)
    if a is None:
        warn("asset missing", path)
    return a


def save(asset_or_path):
    if isinstance(asset_or_path, str):
        eal().save_asset(asset_or_path, only_if_is_dirty=False)
    else:
        eal().save_loaded_asset(asset_or_path, only_if_is_dirty=False)


def ensure_dir(path):
    if not eal().does_directory_exist(path):
        eal().make_directory(path)

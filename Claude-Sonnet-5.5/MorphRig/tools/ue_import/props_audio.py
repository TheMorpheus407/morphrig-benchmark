"""Static prop meshes (power cell, beacon) and the dialogue audio."""
import os
import unreal
import common as C


def static_options():
    o = unreal.FbxImportUI()
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", False)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("import_animations", False)
    return o


def run_props(ctx):
    C.ensure_dir(C.PROP_DIR)
    for src, name in (("Operative_PowerCell.fbx", "SM_PowerCell"), ("Operative_Beacon.fbx", "SM_Beacon")):
        path = os.path.join(ctx.export, "props", src)
        if not os.path.exists(path):
            C.warn("missing prop", path)
            continue
        C.run_tasks([C.import_task(path, C.PROP_DIR, name, static_options())])
        sm = C.load(C.PROP_DIR + "/" + name)
        if sm:
            b = sm.get_bounds()
            C.log("prop", name, "extent cm (%.1f %.1f %.1f)" % (b.box_extent.x * 2, b.box_extent.y * 2, b.box_extent.z * 2),
                  "slots", [str(m.material_slot_name) for m in sm.static_materials])
            C.save(sm)


def run_audio(ctx):
    wav = os.path.join(ctx.source, "audio", "dialogue.wav")
    if not os.path.exists(wav):
        C.warn("dialogue.wav not delivered yet, audio import skipped")
        return
    C.ensure_dir(C.AUDIO_DIR)
    t = C.import_task(wav, C.AUDIO_DIR, "dialogue", None)
    C.run_tasks([t])
    snd = C.load(C.AUDIO_DIR + "/dialogue")
    if snd:
        C.log("dialogue sound", snd.get_path_name(), "duration %.2f s" % snd.get_editor_property("duration"))
        C.save(snd)

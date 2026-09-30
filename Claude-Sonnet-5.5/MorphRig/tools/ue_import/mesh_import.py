"""Skeletal mesh, LOD1/LOD2, sockets and physics asset."""
import os
import unreal
import common as C


def mesh_options():
    o = unreal.FbxImportUI()
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("import_animations", False)
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", True)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    o.skeletal_mesh_import_data.set_editor_property("import_morph_targets", True)
    # use the normals and tangents written by Blender (the textures were baked with the same tangent basis)
    o.skeletal_mesh_import_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_COMPUTE_NORMALS)
    return o


def make_sockets(ctx, mesh, skel):
    """Create the sockets of docs/skeleton_and_sockets.json on the skeletal mesh.

    position_cm_unreal is a component space rest position, forward_hint_unreal / up_hint_unreal give socket +X and +Z;
    the stored transform is relative to the parent bone as Unreal expects.
    """
    ref = skel.get_reference_pose()
    sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    created = 0
    for s in ctx.skeleton_doc["sockets"]:
        name, bone = s["name"], s["bone"]
        bone_world = ref.get_bone_pose(bone, unreal.AnimPoseSpaces.WORLD)
        pos = unreal.Vector(*s["position_cm_unreal"])
        if bone in ("prop_cell", "prop_beacon"):
            # the prop sockets are the origin of the prop bones (their clips carry the world motion of the prop).
            # A rest position that differs from the bone origin (see docs/known_issues.md) would offset the attached mesh.
            d = (pos - bone_world.translation).length()
            if d > 1.0:
                C.warn("socket %s: JSON position is %.1f cm away from the rest position of bone %s; the socket is placed at the bone origin" % (name, d, bone))
                pos = bone_world.translation
        fwd = unreal.Vector(*s["forward_hint_unreal"])
        up = unreal.Vector(*s["up_hint_unreal"])
        rot = unreal.MathLibrary.make_rot_from_xz(fwd, up)
        sock_world = unreal.Transform(location=pos, rotation=rot, scale=unreal.Vector(1, 1, 1))
        rel = sock_world.make_relative(bone_world)
        if unreal.OperativeImportLibrary.add_or_replace_socket(mesh, name, bone, rel):
            created += 1
        else:
            C.warn("socket failed", name, bone)
    C.log("sockets created:", created)


def run(ctx):
    C.ensure_dir(C.MESH_DIR)
    fbx = os.path.join(ctx.export, "Operative.fbx")
    # a reimport onto an existing skeleton keeps the bone transforms of the old skeleton (a prop bone that moved in Blender stays at its old
    # rest position in the reference pose), so the skeleton, mesh and physics asset are always created from scratch (the clips step
    # follows in a full import and rebuilds every animation on the new skeleton)
    for path in (C.MESH_DIR + "/" + C.MESH_NAME + "_PhysicsAsset", C.MESH_PATH, C.SKELETON_PATH):
        if C.eal().does_asset_exist(path):
            C.eal().delete_asset(path)
    r = C.run_tasks([C.import_task(fbx, C.MESH_DIR, C.MESH_NAME, mesh_options())])
    C.log("mesh import", r)
    mesh = C.load(C.MESH_PATH)
    skel = C.load(C.SKELETON_PATH)
    sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)

    # LODs (the reimport of LOD0 removes them, so import them every time)
    for lod, fname in ((1, "Operative_LOD1.fbx"), (2, "Operative_LOD2.fbx")):
        path = os.path.join(ctx.export, fname)
        if os.path.exists(path):
            idx = sub.import_lod(mesh, lod, path)
            C.log("LOD import", lod, "->", idx)
        else:
            C.warn("missing", path)
    C.log("LOD count", sub.get_lod_count(mesh), "verts",
          [sub.get_num_verts(mesh, i) for i in range(sub.get_lod_count(mesh))])

    make_sockets(ctx, mesh, skel)

    # simple physics asset (one capsule/sphere per bone group produced by the engine)
    pa_path = C.MESH_DIR + "/" + C.MESH_NAME + "_PhysicsAsset"
    if C.eal().does_asset_exist(pa_path):
        C.eal().delete_asset(pa_path)
    pa = sub.create_physics_asset(mesh, True, 0)
    C.log("physics asset", pa.get_path_name() if pa else None)
    if pa:
        C.save(pa)

    # report
    b = mesh.get_bounds()
    C.log("mesh height cm = %.2f  origin z = %.2f" % (b.box_extent.z * 2.0, b.origin.z - b.box_extent.z))
    C.log("mesh slots", [str(m.material_slot_name) for m in mesh.materials], "morphs", len(mesh.get_editor_property("morph_targets")))
    C.save(mesh)
    C.save(skel)
    ctx.state["mesh"] = mesh
    ctx.state["skeleton"] = skel

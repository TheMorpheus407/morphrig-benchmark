"""Reimport a comma-separated MORPH_IMPORT_IDS subset after initial full import."""
from pathlib import Path
import os,json,runpy,shutil
import unreal as u
ROOT=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(ROOT/'tools/import_unreal.py'),run_name='import_helpers')
ids=set(os.environ.get('MORPH_IMPORT_IDS','deploy').split(','))
api['material']('M_Normals',normals=True)
manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())
if os.environ.get('MORPH_IMPORT_MESH')=='1':
    api['task'](ROOT/'export/Operative.fbx','/Game/Operative','SK_Operative',api['options']())
    mesh=u.load_asset('/Game/Operative/SK_Operative')
    materials=list(mesh.get_editor_property('materials'))
    contract=json.loads((ROOT/'docs/rig_contract.json').read_text())
    for index,slot in enumerate(materials):
        name=str(slot.get_editor_property('material_slot_name'))
        if name not in contract['material_slots']:name=contract['material_slots'][index]
        slot.set_editor_property('material_interface',u.load_asset('/Game/Operative/'+name))
    mesh.set_editor_property('materials',materials)
    editor=u.get_editor_subsystem(u.SkeletalMeshEditorSubsystem)
    for lod in [1,2]:assert editor.import_lod(mesh,lod,str(ROOT/f'export/Operative_LOD{lod}.fbx'))==lod
    u.EditorAssetLibrary.save_loaded_asset(mesh)
    u.EditorAssetLibrary.save_loaded_asset(mesh.get_editor_property('skeleton'))
skel=u.load_asset('/Game/Operative/SK_Operative_Skeleton')
marker=u.load_class(None,'/Script/MorphRig.MorphMarker')
completed=[]
for clip in manifest['animations']:
    name=clip['id']
    if name not in ids:continue
    path='/Game/Operative/Animations/'+name
    anim=u.load_asset(path)
    settings=anim.get_editor_property('asset_import_data')
    settings.set_editor_property('force_front_x_axis',True)
    settings.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
    u.EditorAssetLibrary.save_loaded_asset(anim)
    api['task'](ROOT/clip['exported_file'],'/Game/Operative/Animations',name,api['options'](skel,True))
    anim=u.load_asset(path)
    anim.set_editor_property('enable_root_motion',clip['root_motion_policy']=='root_motion')
    anim.set_editor_property('force_root_lock',False)
    u.AnimationLibrary.remove_all_animation_notify_tracks(anim)
    u.AnimationLibrary.add_animation_notify_track(anim,'MorphRig',u.LinearColor(.1,.8,.8,1))
    for event in clip['events']:
        notify=u.AnimationLibrary.add_animation_notify_event(anim,'MorphRig',min(event['time'],anim.get_play_length()),marker)
        notify.set_editor_property('marker_name',event['name'])
    u.EditorAssetLibrary.save_loaded_asset(anim)
    completed.append(name)
assert set(completed)==ids,(ids,completed)
for file in ['animation_manifest.json','facial_animation_curves.json']:
    shutil.copyfile(ROOT/'docs'/file,ROOT/'unreal/Content/Data'/file)
runpy.run_path(str(ROOT/'tools/verify_unreal.py'),run_name='__main__')
(ROOT/'docs/unreal_last_clip_update.json').write_text(json.dumps({'updated_clips':completed},indent=2))

from pathlib import Path
import runpy
import unreal as u
ROOT=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(ROOT/'tools/import_unreal.py'))
skel=u.load_asset('/Game/Operative/SK_Operative_Skeleton')
a=u.load_asset('/Game/Operative/Animations/dash_f')
data=a.get_editor_property('asset_import_data')
u.log('PRIOR_OPTIONS '+str(data.get_editor_property('force_front_x_axis'))+' '+str(data.get_editor_property('import_rotation')))
data.set_editor_property('force_front_x_axis',True)
data.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
u.EditorAssetLibrary.save_loaded_asset(a)
o=api['options'](skel,True)
o.get_editor_property('skeletal_mesh_import_data').set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
o.get_editor_property('anim_sequence_import_data').set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
api['task'](ROOT/'export/animations/dash_f.fbx','/Game/Operative/Animations','dash_f',o)
a=u.load_asset('/Game/Operative/Animations/dash_f')
data=a.get_editor_property('asset_import_data')
u.log('AFTER_OPTIONS '+str(data.get_editor_property('force_front_x_axis'))+' '+str(data.get_editor_property('import_rotation')))
a.set_editor_property('enable_root_motion',True)
u.EditorAssetLibrary.save_loaded_asset(a)
runpy.run_path(str(ROOT/'tools/verify_unreal.py'))

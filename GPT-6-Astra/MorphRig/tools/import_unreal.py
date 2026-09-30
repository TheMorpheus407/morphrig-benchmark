"""Reproducible UE editor import. Run via tools/import_unreal.sh, after Blender export."""
from pathlib import Path
import json
import shutil
import os
import unreal as u
u.load_module('AnimationBlueprintLibrary')

ROOT = Path(__file__).resolve().parents[1]
CONTENT = '/Game/Operative'
AT = u.AssetToolsHelpers.get_asset_tools()
LIB = u.EditorAssetLibrary
ML = u.MaterialEditingLibrary
u.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')

def task(file, destination, name, options=None):
    t = u.AssetImportTask()
    t.filename = str(file)
    t.destination_path = destination
    t.destination_name = name
    t.automated = True
    t.replace_existing = True
    t.replace_existing_settings = True
    t.save = True
    if options:
        t.options = options
    AT.import_asset_tasks([t])
    return [u.load_asset(p) for p in t.imported_object_paths]

def expression(mat, cls, x=-500, y=0):
    return ML.create_material_expression(mat, cls, x, y)

def material(name, base=None, normal=None, color=None, rough=.5, metal=0, team=False, normals=False):
    mat = u.load_asset(f'{CONTENT}/{name}')
    if mat is None:
        mat = AT.create_asset(name, CONTENT, u.Material, u.MaterialFactoryNew())
    ML.delete_all_material_expressions(mat)
    mat.set_editor_property('two_sided', False)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    mat.set_editor_property('used_with_morph_targets', True)
    if normals:
        mat.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
        n = expression(mat, u.MaterialExpressionVertexNormalWS)
        scale=expression(mat,u.MaterialExpressionMultiply,-320,0)
        scale.set_editor_property('const_b',.5)
        ML.connect_material_expressions(n,'',scale,'A')
        bias=expression(mat,u.MaterialExpressionAdd,-150,0)
        bias.set_editor_property('const_b',.5)
        ML.connect_material_expressions(scale,'',bias,'A')
        ML.connect_material_property(bias, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
    elif team or color is not None:
        c = expression(mat, u.MaterialExpressionVectorParameter)
        c.set_editor_property('parameter_name','TeamColor' if team else 'Color')
        c.set_editor_property('default_value',u.LinearColor(*(color or (.01,.68,.67)), 1))
        ML.connect_material_property(c, '', u.MaterialProperty.MP_BASE_COLOR)
        if team:
            multiply=expression(mat,u.MaterialExpressionMultiply,-240,120)
            multiply.set_editor_property('const_b',.35)
            ML.connect_material_expressions(c,'',multiply,'A')
            ML.connect_material_property(multiply,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
    elif base:
        t = expression(mat,u.MaterialExpressionTextureSample)
        t.texture = base
        ML.connect_material_property(t, 'RGB', u.MaterialProperty.MP_BASE_COLOR)
    if normal:
        t = expression(mat,u.MaterialExpressionTextureSample,-500,250)
        t.texture=normal
        t.sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL
        ML.connect_material_property(t,'RGB',u.MaterialProperty.MP_NORMAL)
    for offset,(prop,val) in enumerate([(u.MaterialProperty.MP_ROUGHNESS,rough),(u.MaterialProperty.MP_METALLIC,metal)]):
        e=expression(mat,u.MaterialExpressionConstant,-240,330+offset*90)
        e.r=val
        ML.connect_material_property(e,'',prop)
    ML.recompile_material(mat)
    LIB.save_loaded_asset(mat)
    return mat

def options(skeleton=None, animations=False):
    o=u.FbxImportUI()
    o.set_editor_property('automated_import_should_detect_type',False)
    o.set_editor_property('mesh_type_to_import',u.FBXImportType.FBXIT_ANIMATION if animations else u.FBXImportType.FBXIT_SKELETAL_MESH)
    o.set_editor_property('import_as_skeletal',True)
    o.set_editor_property('import_mesh',not animations)
    o.set_editor_property('import_animations',animations)
    o.set_editor_property('import_materials',False)
    o.set_editor_property('import_textures',False)
    o.set_editor_property('create_physics_asset',False)
    if skeleton:o.set_editor_property('skeleton',skeleton)
    data=o.get_editor_property('skeletal_mesh_import_data')
    data.set_editor_property('import_morph_targets',True)
    data.set_editor_property('update_skeleton_reference_pose',True)
    data.set_editor_property('normal_import_method',u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    data.set_editor_property('convert_scene',True)
    data.set_editor_property('convert_scene_unit',True)
    data.set_editor_property('force_front_x_axis',True)
    data.set_editor_property('import_uniform_scale',1.0)
    if animations:data.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
    a=o.get_editor_property('anim_sequence_import_data')
    a.set_editor_property('animation_length',u.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    a.set_editor_property('use_default_sample_rate',False)
    a.set_editor_property('custom_sample_rate',30)
    a.set_editor_property('import_custom_attribute',True)
    a.set_editor_property('import_bone_tracks',True)
    a.set_editor_property('remove_redundant_keys',False)
    a.set_editor_property('convert_scene',True)
    a.set_editor_property('convert_scene_unit',True)
    a.set_editor_property('force_front_x_axis',True)
    if animations:a.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
    return o

def import_beacon():
    """Import the explicit-centimeter, two-section socket-local prop."""
    beacon=ROOT/'export/Beacon.fbx'
    assert beacon.is_file(), 'Export authored static beacon first'
    path=CONTENT+'/SM_Beacon'
    # Rebuild this derived asset so old section-remapping data cannot collapse
    # the compact alloy/accent slots on reimport.
    if LIB.does_asset_exist(path):LIB.delete_asset(path)
    opt=u.FbxImportUI()
    opt.set_editor_property('automated_import_should_detect_type',False)
    opt.set_editor_property('mesh_type_to_import',u.FBXImportType.FBXIT_STATIC_MESH)
    opt.set_editor_property('import_as_skeletal',False)
    opt.set_editor_property('import_materials',False)
    opt.set_editor_property('import_textures',False)
    data=opt.get_editor_property('static_mesh_import_data')
    data.set_editor_property('force_front_x_axis',True)
    data.set_editor_property('convert_scene',True)
    data.set_editor_property('convert_scene_unit',True)
    data.set_editor_property('combine_meshes',True)
    data.set_editor_property('import_uniform_scale',1.)
    task(beacon,CONTENT,'SM_Beacon',opt)
    prop=u.load_asset(path)
    slots=list(prop.get_editor_property('static_materials'))
    assert len(slots)==2, [(str(s.material_slot_name),str(s.material_interface)) for s in slots]
    for i,entry in enumerate(slots):
        name=str(entry.get_editor_property('material_slot_name'))
        assert name in ('M_Alloy','M_TeamAccent'),name
        prop.set_material(i,u.load_asset(CONTENT+'/'+name))
    LIB.save_loaded_asset(prop)
    return prop

def main():
    centimeter_pilot=os.environ.get('MORPH_IMPORT_CM')=='1'
    pilot=os.environ.get('MORPH_IMPORT_PILOT')=='1' or centimeter_pilot
    pilot_folder='pilot_cm' if centimeter_pilot else 'pilot'
    pilot_ids=['dash_f','prone_back','reload','deploy','run_f','idle_relaxed'] if centimeter_pilot else ['idle_combat','dash_f']
    if os.environ.get('MORPH_IMPORT_CLEAN')=='1':
        for asset in LIB.list_assets(CONTENT+'/Animations',recursive=True):LIB.delete_asset(asset)
        for asset in [CONTENT+'/SK_Operative',CONTENT+'/SK_Operative_Skeleton']:
            if LIB.does_asset_exist(asset):LIB.delete_asset(asset)
    manifest=json.loads((ROOT/'docs/animation_manifest.json').read_text())
    contract=json.loads((ROOT/'docs/rig_contract.json').read_text())
    mesh_file=ROOT/(f'export/{pilot_folder}/Operative.fbx' if pilot else 'export/Operative.fbx')
    assert mesh_file.is_file(), 'Bake/export source first'
    meshes=task(mesh_file,CONTENT,'SK_Operative',options())
    mesh=u.load_asset(CONTENT+'/SK_Operative')
    assert isinstance(mesh,u.SkeletalMesh), [(str(x),type(x)) for x in meshes]
    skeleton=mesh.get_editor_property('skeleton')
    assert skeleton is not None,'Mesh skeleton was not created'
    LIB.save_loaded_asset(skeleton,only_if_is_dirty=False)
    textures={}
    for p in sorted((ROOT/'source/textures').glob('*.png')):
        assets=task(p,CONTENT+'/Textures',p.stem)
        tex=u.load_asset(CONTENT+'/Textures/'+p.stem)
        if p.stem.endswith('_Normal'):
            tex.set_editor_property('compression_settings',u.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property('srgb',False)
        tex.set_editor_property('max_texture_size',4096)
        LIB.save_loaded_asset(tex)
        textures[p.stem]=tex
    roughness={'M_Skin':.48,'M_Weave':.78,'M_Ceramic':.36,'M_Alloy':.28,'M_TeamAccent':.35,'M_Hair':.6,'M_EyeWhite':.2,'M_Iris':.23}
    mats={}
    for n in contract['material_slots']:
        mats[n]=material(n,base=textures[n+'_BaseColor'],normal=textures[n+'_Normal'],rough=roughness[n],metal=.85 if n=='M_Alloy' else .08 if n=='M_Ceramic' else 0,team=n=='M_TeamAccent')
    skeletal_mats=list(mesh.get_editor_property('materials'))
    for i,sm in enumerate(skeletal_mats):
        name=str(sm.get_editor_property('material_slot_name'))
        if name not in mats:
            name=contract['material_slots'][i]
        sm.set_editor_property('material_interface',mats[name])
    mesh.set_editor_property('materials',skeletal_mats)
    sme=u.get_editor_subsystem(u.SkeletalMeshEditorSubsystem)
    for lod in ([] if pilot else [1,2]):
        filename=ROOT/f'export/Operative_LOD{lod}.fbx'
        assert filename.exists(),f'Missing required LOD: {filename}'
        result=sme.import_lod(mesh,lod,str(filename))
        assert result==lod,(lod,result)
    LIB.save_loaded_asset(mesh)
    marker_class=u.load_class(None,'/Script/MorphRig.MorphMarker')
    imported=[]
    for clip in manifest['animations']:
        name=clip['id']
        if pilot and name not in pilot_ids:continue
        clip_file=ROOT/f'export/{pilot_folder}/{name}.fbx' if pilot else ROOT/clip['exported_file']
        existing=u.load_asset(CONTENT+'/Animations/'+name)
        if existing:
            previous=existing.get_editor_property('asset_import_data')
            previous.set_editor_property('force_front_x_axis',True)
            previous.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
            LIB.save_loaded_asset(existing)
        assets=task(clip_file,CONTENT+'/Animations',name,options(skeleton,True))
        anim=u.load_asset(CONTENT+'/Animations/'+name)
        if anim is None:
            candidates=[a for a in assets if isinstance(a,u.AnimSequence)]
            assert len(candidates)==1,(name,assets)
            LIB.rename_asset(candidates[0].get_path_name(),CONTENT+'/Animations/'+name)
            anim=u.load_asset(CONTENT+'/Animations/'+name)
        assert isinstance(anim,u.AnimSequence),name
        imported_options=anim.get_editor_property('asset_import_data')
        if abs(imported_options.get_editor_property('import_rotation').yaw+90)>.01:
            imported_options.set_editor_property('force_front_x_axis',True)
            imported_options.set_editor_property('import_rotation',u.Rotator(pitch=0,yaw=-90,roll=0))
            LIB.save_loaded_asset(anim)
            task(clip_file,CONTENT+'/Animations',name,options(skeleton,True))
            anim=u.load_asset(CONTENT+'/Animations/'+name)
        anim.set_editor_property('enable_root_motion',clip['root_motion_policy']=='root_motion')
        anim.set_editor_property('force_root_lock',False)
        abl=u.AnimationLibrary
        abl.remove_all_animation_notify_tracks(anim)
        abl.add_animation_notify_track(anim,'MorphRig',u.LinearColor(.1,.8,.8,1))
        for event in clip['events']:
            notify=abl.add_animation_notify_event(anim,'MorphRig',min(event['time'],anim.get_play_length()),marker_class)
            notify.set_editor_property('marker_name',event['name'])
        LIB.save_loaded_asset(anim)
        imported.append({'id':name,'path':anim.get_path_name(),'duration':anim.get_play_length(),'markers':len(clip['events'])})
        u.log(f'MorphRig imported {name}: {anim.get_play_length():.3f}s')
    task(ROOT/'source/audio/dialogue.wav',CONTENT,'Dialogue')
    import_beacon()
    material('M_Stage',color=(.16,.19,.22),rough=.75)
    material('M_Normals',normals=True)
    level=u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not LIB.does_asset_exist('/Game/Showcase'):
        assert level.new_level('/Game/Showcase')
        level.save_current_level()
    data=ROOT/'unreal/Content/Data';data.mkdir(exist_ok=True)
    for source in ['docs/animation_manifest.json','docs/facial_animation_curves.json','source/audio/dialogue_alignment.json']:
        shutil.copyfile(ROOT/source,data/Path(source).name)
    ref=u.AnimPoseExtensions.get_reference_pose(skeleton)
    names=[str(n) for n in u.AnimPoseExtensions.get_bone_names(ref)]
    assert names[0]=='root',f'Export introduces an unwanted root: {names[:5]}'
    report={'engine':u.SystemLibrary.get_engine_version(),'pilot':pilot,'mesh':mesh.get_path_name(),'bones':names,'bone_count':len(names),'animation_count':len(imported),'animations':imported,'lods':[{'lod':i,'vertices':sme.get_num_verts(mesh,i),'sections':sme.get_num_sections(mesh,i)}for i in range(1 if pilot else 3)],'materials':len(skeletal_mats),'morphs':[str(m.get_name())for m in mesh.get_editor_property('morph_targets')]}
    (ROOT/('docs/unreal_pilot_validation.json' if pilot else 'docs/unreal_import_validation.json')).write_text(json.dumps(report,indent=2))
    LIB.save_directory('/Game',only_if_is_dirty=True,recursive=True)
    assert len(imported)==(len(pilot_ids) if pilot else 96)
    u.log(f'MORPHRIG_IMPORT_COMPLETE: {len(imported)} authored clips, skeleton, morphs, audio and map saved. Pilot={pilot}')

if __name__=='__main__':main()

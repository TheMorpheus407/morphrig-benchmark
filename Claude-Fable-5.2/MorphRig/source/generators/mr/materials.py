"""Blender materials for the Operative: image based PBR with the team accent variants.

The same mask logic is used in the Unreal master material:
    icon      = mix(mask.G, mask.B, team_icon)          (0 = chevron + solid trim, 1 = ring + dashed trim)
    accent    = clamp(mask.R + icon)
    base      = mix(base colour, team colour, accent)
    emission  = team colour * (mask.A * 3.0 + icon * 1.5)
`team_color` (RGB) and `team_icon` (0 / 1) are custom properties of the mesh object; set_team() switches the variant.
"""
import os
import bpy

TEAMS = {'A': dict(color=(0.0, 0.62, 1.0), icon=0.0, label='Team A - cyan, chevron icon, solid trim'),
         'B': dict(color=(1.0, 0.36, 0.02), icon=1.0, label='Team B - amber, ring icon, dashed trim')}
SSS = {'M_Skin': 0.06}


def _img(path, colorspace):
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.load(path)
    else:
        img.filepath = path
        img.reload()
    img.colorspace_settings.name = colorspace
    return img


def build_materials(ob, tex_dir, manifest, relative=False):
    """(Re)create the node trees of all material slots from the texture manifest."""
    by_slot = {m['slot']: m for m in manifest['materials']}
    for slot in ob.material_slots:
        mat = slot.material
        info = by_slot.get(mat.name)
        if info is None:
            continue
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        N = nt.nodes.new
        L = nt.links.new
        out = N('ShaderNodeOutputMaterial')
        out.location = (900, 0)
        bsdf = N('ShaderNodeBsdfPrincipled')
        bsdf.location = (560, 0)
        L(bsdf.outputs['BSDF'], out.inputs['Surface'])

        def tex(key, cs, x, y):
            n = N('ShaderNodeTexImage')
            n.location = (x, y)
            n.image = _img(os.path.join(tex_dir, info[key]), cs)
            n.label = key
            return n
        tb = tex('base_color', 'sRGB', -900, 300)
        tn = tex('normal', 'Non-Color', -900, -500)
        to = tex('orm', 'Non-Color', -900, -100)
        sep = N('ShaderNodeSeparateColor')
        sep.location = (-600, -100)
        L(to.outputs['Color'], sep.inputs['Color'])
        L(sep.outputs['Green'], bsdf.inputs['Roughness'])
        L(sep.outputs['Blue'], bsdf.inputs['Metallic'])
        nm = N('ShaderNodeNormalMap')
        nm.location = (-600, -500)
        L(tn.outputs['Color'], nm.inputs['Color'])
        L(nm.outputs['Normal'], bsdf.inputs['Normal'])
        # ambient occlusion darkens the albedo a little in Blender (Unreal uses the AO channel directly)
        aom = N('ShaderNodeMix')
        aom.data_type = 'RGBA'
        aom.blend_type = 'MULTIPLY'
        aom.location = (-300, 300)
        aom.inputs['Factor'].default_value = 0.5
        L(tb.outputs['Color'], aom.inputs['A'])
        L(sep.outputs['Red'], aom.inputs['B'])
        base_out = aom.outputs['Result']
        if info.get('mask'):
            tm = tex('mask', 'Non-Color', -900, 700)
            ms = N('ShaderNodeSeparateColor')
            ms.location = (-600, 700)
            L(tm.outputs['Color'], ms.inputs['Color'])
            tc = N('ShaderNodeAttribute')
            tc.attribute_type = 'OBJECT'
            tc.attribute_name = 'team_color'
            tc.location = (-600, 1000)
            ti = N('ShaderNodeAttribute')
            ti.attribute_type = 'OBJECT'
            ti.attribute_name = 'team_icon'
            ti.location = (-600, 1200)
            icon = N('ShaderNodeMix')
            icon.data_type = 'FLOAT'
            icon.location = (-300, 900)
            L(ti.outputs['Fac'], icon.inputs['Factor'])
            L(ms.outputs['Green'], icon.inputs['A'])
            L(ms.outputs['Blue'], icon.inputs['B'])
            add = N('ShaderNodeMath')
            add.operation = 'ADD'
            add.use_clamp = True
            add.location = (-100, 800)
            L(ms.outputs['Red'], add.inputs[0])
            L(icon.outputs['Result'], add.inputs[1])
            mixc = N('ShaderNodeMix')
            mixc.data_type = 'RGBA'
            mixc.location = (150, 450)
            L(add.outputs['Value'], mixc.inputs['Factor'])
            L(base_out, mixc.inputs['A'])
            L(tc.outputs['Color'], mixc.inputs['B'])
            base_out = mixc.outputs['Result']
            # emission strength = mask.A * 3 + icon * 1.5
            m1 = N('ShaderNodeMath')
            m1.operation = 'MULTIPLY'
            m1.inputs[1].default_value = 3.0
            m1.location = (-100, 1100)
            L(tm.outputs['Alpha'], m1.inputs[0])
            m2 = N('ShaderNodeMath')
            m2.operation = 'MULTIPLY_ADD'
            m2.inputs[1].default_value = 1.5
            m2.location = (100, 1100)
            L(icon.outputs['Result'], m2.inputs[0])
            L(m1.outputs['Value'], m2.inputs[2])
            L(tc.outputs['Color'], bsdf.inputs['Emission Color'])
            L(m2.outputs['Value'], bsdf.inputs['Emission Strength'])
        L(base_out, bsdf.inputs['Base Color'])
        if mat.name in SSS:
            bsdf.inputs['Subsurface Weight'].default_value = 1.0
            bsdf.inputs['Subsurface Scale'].default_value = SSS[mat.name] * 0.1
            bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.35, 0.2)
        if mat.name == 'M_EyesMouth':
            bsdf.inputs['Specular IOR Level'].default_value = 0.8
        mat.diffuse_color = {'M_Skin': (0.72, 0.52, 0.42, 1), 'M_EyesMouth': (0.92, 0.9, 0.88, 1), 'M_Hair': (0.82, 0.82, 0.86, 1),
                             'M_Suit': (0.10, 0.115, 0.15, 1), 'M_Armor': (0.62, 0.61, 0.58, 1), 'M_Cyber': (0.30, 0.32, 0.36, 1)}.get(mat.name, (0.8, 0.8, 0.8, 1))
    set_team(ob, 'A')


def set_team(ob, team):
    t = TEAMS[team]
    ob['team_color'] = t['color']
    ob['team_icon'] = t['icon']
    ob['team'] = team
    ob.update_tag()


def make_paths_relative():
    for img in bpy.data.images:
        if img.filepath and not img.filepath.startswith('//'):
            try:
                img.filepath = bpy.path.relpath(img.filepath)
            except ValueError:
                pass

"""Build all Operative mesh objects (LOD0 source), vertex groups from procedural skinning, placeholder materials.
Run inside Blender after rig_skeleton.create_skeleton(). Returns a dict name -> object."""
import numpy as np
import bpy
import skeleton_def as S
import mr_geo as G
import hs
import body_base as B
import head as H
import hands as HD
import cyber_arm as CA
import accessories as AC
import skinning as SK
import hair as HR

A = np.array
MAT_NAMES = ['skin', 'eye', 'mouth', 'hair', 'suit', 'armor', 'cyber']


def get_materials():
    mats = {}
    for n in MAT_NAMES:
        m = bpy.data.materials.get('MI_' + n)
        if m is None:
            m = bpy.data.materials.new('MI_' + n)
            m.diffuse_color = {'skin': (0.55, 0.40, 0.33, 1), 'eye': (0.9, 0.9, 0.92, 1), 'mouth': (0.85, 0.8, 0.75, 1),
                               'hair': (0.05, 0.04, 0.04, 1), 'suit': (0.05, 0.06, 0.08, 1), 'armor': (0.3, 0.32, 0.36, 1),
                               'cyber': (0.55, 0.6, 0.66, 1)}[n]
        mats[n] = m
    return mats


def add_object(name, V, F, skel, mats, face_mat=None, W=None, masks=None, collection=None, skin_to_armature=True, smooth=True):
    """face_mat: list of material names per face (or a single name)."""
    V = np.asarray(V, dtype=np.float64)
    ob = G.make_object(name, V, F, collection=collection, smooth=smooth)
    names = []
    if face_mat is None:
        face_mat = 'armor'
    if isinstance(face_mat, str):
        face_mat = [face_mat] * len(F)
    for n in face_mat:
        if n not in names:
            names.append(n)
    for n in names:
        ob.data.materials.append(mats[n])
    idx = {n: i for i, n in enumerate(names)}
    mi = np.array([idx[n] for n in face_mat], dtype=np.int32)
    ob.data.polygons.foreach_set('material_index', mi)
    if masks:
        attr = ob.data.color_attributes.new('MR_MASKS', 'FLOAT_COLOR', 'POINT')
        cols = np.zeros((len(V), 4), dtype=np.float32)
        cols[:, 0] = masks.get('emit', 0)
        cols[:, 1] = masks.get('accent', 0)
        cols[:, 2] = masks.get('extra', 0)
        cols[:, 3] = 1.0
        attr.data.foreach_set('color', cols.ravel())
    if W is not None:
        Wp = SK.prune(W, max_inf=6)
        for bi, b in enumerate(S.BONES):
            col = Wp[:, bi]
            nz = np.nonzero(col > 0)[0]
            if len(nz) == 0:
                continue
            vg = ob.vertex_groups.new(name=b.name)
            for vi in nz:
                vg.add([int(vi)], float(col[vi]), 'REPLACE')
    if skel is not None and skin_to_armature:
        md = ob.modifiers.new('Armature', 'ARMATURE')
        md.object = skel
        ob.parent = skel
    return ob


def parts_to_object(name, parts, skel, mats, body_data=None):
    v, f, pidx, emit, accent = hs.merge_parts(parts)
    face_mat = []
    offs = 0
    for p in parts:
        face_mat += [p.mat] * len(p.faces)
    W = np.zeros((len(v), SK.NB))
    o = 0
    for p in parts:
        n = len(p.verts)
        sl = slice(o, o + n)
        if p.bone:
            W[sl] = SK.rigid(n, p.bone)
        elif p.flex == 'upperarm':
            s, d = SK.project_polyline(p.verts, SK.arm_poly(1.0))
            W[sl] = SK.hat(s, SK.arm_anchors('l'))
        elif p.flex == 'boot':
            W[sl] = SK.boot_weights(p.verts, 'l' if p.verts[:, 1].mean() > 0 else 'r')
        elif p.flex == 'braid':
            pts = [S.BONE_BY_NAME['hair_01'].head] + [S.BONE_BY_NAME[f'hair_{i:02d}'].tail for i in range(1, 6)]
            W[sl] = SK.chain_hat_weights(p.verts, [f'hair_{i:02d}' for i in range(1, 6)] + ['hair_05'], pts)
        elif p.flex == 'cable':
            pts = [S.BONE_BY_NAME['cable_01'].head] + [S.BONE_BY_NAME[f'cable_{i:02d}'].tail for i in range(1, 6)]
            W[sl] = SK.chain_hat_weights(p.verts, [f'cable_{i:02d}' for i in range(1, 6)] + ['cable_05'], pts)
        elif body_data is not None:
            W[sl] = SK.transfer(p.verts, body_data['P'], body_data['W'], k=4)
        else:
            W[sl] = SK.rigid(n, 'pelvis')
        o += n
    return add_object(name, v, f, skel, mats, face_mat, W, {'emit': emit, 'accent': accent})


def shape_body(P, faces):
    """Athletic female-presenting anatomy bumps on the body base."""
    n = G.normals(P, faces)
    d = np.zeros_like(P)
    bumps = [
        # name, centre, radii, amount
        ('bust', (0.090, 0.084, 1.318), (0.060, 0.060, 0.052), 0.020),
        ('glute', (-0.095, 0.078, 0.955), (0.065, 0.070, 0.070), 0.022),
        ('quad', (0.030, 0.095, 0.780), (0.060, 0.062, 0.170), 0.010),
        ('hamstring', (-0.040, 0.092, 0.760), (0.055, 0.062, 0.150), 0.007),
        ('calf', (-0.030, 0.098, 0.340), (0.050, 0.050, 0.100), 0.011),
        ('deltoid', (-0.008, 0.205, 1.442), (0.055, 0.050, 0.055), 0.009),
        ('trap', (-0.030, 0.070, 1.492), (0.070, 0.070, 0.035), 0.008),
        ('lats', (-0.060, 0.135, 1.290), (0.050, 0.030, 0.100), 0.006),
        ('abs', (0.085, 0.0, 1.170), (0.040, 0.050, 0.070), 0.004),
        ('bicep', (0.020, 0.300, 1.300), (0.050, 0.040, 0.070), 0.005),
        ('forearm', (0.030, 0.430, 1.075), (0.050, 0.040, 0.085), 0.006),
    ]
    for name, c, r, amt in bumps:
        for sy in (1, -1):
            cc = (c[0], c[1] * sy, c[2])
            d += G.gauss_bump(P, cc, r, 'normal', amt, n)
    return P + d


def add_props(skel, mats):
    """Power cell and beacon as static meshes (mesh space = character axes at rest, pivot at the prop bone head).
    In Blender they follow their prop bones through a Child-Of constraint with a rest inverse."""
    out = {}
    for name, parts, bone, rest_loc in (('Operative_Prop_PowerCell', AC.prop_power_cell(), 'prop_cell', S.BONE_BY_NAME['prop_cell'].head),
                                       ('Operative_Prop_Beacon', AC.prop_beacon(), 'prop_beacon', S.BONE_BY_NAME['prop_beacon'].head)):
        v, f, pidx, emit, accent = hs.merge_parts(parts)
        if name.endswith('PowerCell'):
            # cell authored along local Y; stand it up along the forearm axis direction at rest (slot orientation)
            R = hs.frame(CA.FA, CA.FRONT)      # columns X,Y,Z with Y along the forearm axis
            v = v @ R.T
        face_mat = []
        for p in parts:
            face_mat += [p.mat] * len(p.faces)
        ob = add_object(name, v, f, None, mats, face_mat, None, {'emit': emit, 'accent': accent})
        ob.location = tuple(rest_loc)
        bpy.context.view_layer.update()
        con = ob.constraints.new('CHILD_OF')
        con.target = skel
        con.subtarget = bone
        con.inverse_matrix = (skel.matrix_world @ skel.data.bones[bone].matrix_local).inverted()
        out[name] = ob
    return out


def build_all(skel):
    mats = get_materials()
    objs = {}
    # ---- body base
    Pb, Fb, rings, info = B.build_body_base()
    Pb, _ = B.trunk_warp(Pb, Fb, info)
    Pb = shape_body(Pb, Fb)
    lab, kinds = B.part_labels(Pb, info)
    Wb = SK.body_weights(Pb, Fb, lab, kinds)
    cent = np.array([Pb[list(f)].mean(axis=0) for f in Fb])
    # skin on the arms beyond the shoulder cap, suit elsewhere
    face_mat = []
    for sy in (1.0, -1.0):
        pass
    s_r, _ = SK.project_polyline(cent, SK.arm_poly(-1.0))
    s_l, _ = SK.project_polyline(cent, SK.arm_poly(1.0))
    dl = np.linalg.norm(cent - A(S.SHOULDER), axis=1)
    dr = np.linalg.norm(cent - A([S.SHOULDER[0], -S.SHOULDER[1], S.SHOULDER[2]]), axis=1)
    skin_face = ((cent[:, 1] < -0.19) & (cent[:, 2] < 1.48) & (dr > 0.085) & (cent[:, 2] > 0.93)) | ((cent[:, 1] > 0.19) & (cent[:, 2] < 1.48) & (dl > 0.085) & (cent[:, 2] > 1.10))
    face_mat = ['skin' if s else 'suit' for s in skin_face]
    objs['body'] = add_object('Operative_Body', Pb, Fb, skel, mats, face_mat, Wb)
    body_data = {'P': Pb, 'W': Wb}
    # ---- head, eyes, ears, mouth parts
    Vh, Fh, hinfo = H.build_head()
    ears = [H.ear_mesh(1.0), H.ear_mesh(-1.0)]
    Vh2, Fh2, offs = G.merge([(Vh, Fh)] + ears)
    Wh = np.zeros((len(Vh2), SK.NB))
    Wh[: len(Vh)] = SK.head_weights(Vh, Fh, hinfo)
    Wh[len(Vh):] = SK.rigid(len(Vh2) - len(Vh), 'head')
    # region tags for texturing (MR_MASKS.B): ears 0.25, eye sockets 0.5, mouth cavity 1.0
    extra_h = np.zeros(len(Vh2))
    extra_h[len(Vh):] = 0.25
    for nm in ('eye_l', 'eye_r'):
        for ring in hinfo[nm][3:]:                       # pocket rings behind the lids
            extra_h[list(ring)] = 0.5
    for ring in hinfo['mouth']['rings'][1:]:             # cavity rings; the slit ring on the lip edge stays skin
        extra_h[list(ring)] = 1.0
    objs['head'] = add_object('Operative_Head', Vh2, Fh2, skel, mats, 'skin', Wh, {'extra': extra_h})
    Vc, Fc, hair_info = HR.hair_cap(Vh, Fh)
    objs['hair'] = add_object('Operative_Hair', Vc, Fc, skel, mats, 'hair', SK.rigid(len(Vc), 'head'))
    ev, ef = [], []
    eyes = []
    for nm in ('l', 'r'):
        v, f, _ = H.eyeball(hinfo['eye_' + nm + '_centre'])
        eyes.append((v, f))
    Ve, Fe, offs = G.merge(eyes)
    We = np.zeros((len(Ve), SK.NB))
    n1 = len(eyes[0][0])
    We[:n1] = SK.rigid(n1, 'eye_l')
    We[n1:] = SK.rigid(len(Ve) - n1, 'eye_r')
    objs['eyes'] = add_object('Operative_Eyes', Ve, Fe, skel, mats, 'eye', We)
    teeth = H.teeth_meshes()
    tv, tf = H.tongue_mesh()
    Vm, Fm, offs = G.merge([teeth['upper'], teeth['lower'], (tv, tf)])
    Wm = np.zeros((len(Vm), SK.NB))
    n_u, n_l = len(teeth['upper'][0]), len(teeth['lower'][0])
    Wm[:n_u] = SK.rigid(n_u, 'head')
    Wm[n_u:n_u + n_l] = SK.rigid(n_l, 'jaw')
    tp = [S.BONE_BY_NAME['tongue_01'].head, S.BONE_BY_NAME['tongue_02'].head, S.BONE_BY_NAME['tongue_03'].head, S.BONE_BY_NAME['tongue_03'].tail]
    Wm[n_u + n_l:] = SK.chain_hat_weights(tv, ['tongue_01', 'tongue_02', 'tongue_03', 'tongue_03'], tp)
    extra_m = np.zeros(len(Vm))
    extra_m[:n_u] = 0.25            # upper teeth
    extra_m[n_u:n_u + n_l] = 0.5    # lower teeth
    extra_m[n_u + n_l:] = 1.0       # tongue
    objs['mouth'] = add_object('Operative_Mouth', Vm, Fm, skel, mats, 'mouth', Wm, {'extra': extra_m})
    # ---- right hand (organic)
    Vr, Fr = HD.build_hand(-1.0)
    Wr = SK.hand_weights(Vr, Fr, 'r', -1.0)
    objs['hand_r'] = add_object('Operative_Hand_R', Vr, Fr, skel, mats, 'skin', Wr)
    # ---- hard-surface groups
    objs['cyber_arm'] = parts_to_object('Operative_CyberArm_L', CA.build_cyber_arm(), skel, mats, body_data)
    objs['boots'] = parts_to_object('Operative_Boots', AC.boots(), skel, mats, body_data)
    objs['gear'] = parts_to_object('Operative_Gear', AC.torso_parts() + AC.limb_armor(), skel, mats, body_data)
    objs['braid'] = parts_to_object('Operative_Braid', AC.braid(), skel, mats, body_data)
    objs['cable'] = parts_to_object('Operative_Cable', AC.cable(), skel, mats, body_data)
    objs_props = add_props(skel, mats)
    return objs, {'head_info': hinfo, 'rings': rings, 'body_info': info, 'props': objs_props}

"""Organic hand (right) from a small Skin-modifier graph: palm hub, four finger chains, thumb chain, hidden wrist stub.
The palm is flattened along the palm normal afterwards. Finger tips stay closed (rounded). Blender + numpy."""
import numpy as np
import bpy
import skeleton_def as S
import mr_geo as G

A = np.array


def build_hand(side_sign=-1.0, level=2):
    sy = side_sign
    m = lambda p: A([p[0], sy * p[1], p[2]], float)
    W = A(S.WRIST)
    HD = A(S.HAND_DIR)
    PN = A(S.PALM_NORMAL)
    PS = A(S.PALM_SIDE)
    verts, edges, rad = [], [], []

    def V(p, r):
        verts.append(tuple(p))
        rad.append(r)
        return len(verts) - 1

    back = V(m(W - HD * 0.030), 0.0205)
    wrist = V(m(W + HD * 0.004), 0.0225)
    edges.append((back, wrist))
    palm = V(m(W + HD * 0.052 + PN * 0.002), 0.0300)
    edges.append((wrist, palm))
    mcp_c = W + HD * S.PALM_LEN
    fr = {'index': (0.0102, 0.0090, 0.0080, 0.0068), 'middle': (0.0105, 0.0092, 0.0082, 0.0070),
          'ring': (0.0100, 0.0088, 0.0079, 0.0067), 'pinky': (0.0088, 0.0076, 0.0068, 0.0058)}
    for fname in ('index', 'middle', 'ring', 'pinky'):
        bm1 = S.BONE_BY_NAME[f'{fname}_01_l']
        mcp = V(m(bm1.head), fr[fname][0])
        edges.append((palm, mcp))
        prev = mcp
        for i, rr in zip((1, 2, 3), fr[fname][1:]):
            b = S.BONE_BY_NAME[f'{fname}_{i:02d}_l']
            nxt = V(m(b.tail), rr)
            edges.append((prev, nxt))
            prev = nxt
    # thumb
    t1 = S.BONE_BY_NAME['thumb_01_l']
    tb = V(m(t1.head), 0.0150)
    edges.append((wrist, tb))
    prev = tb
    for i, rr in zip((1, 2, 3), (0.0125, 0.0108, 0.0092)):
        b = S.BONE_BY_NAME[f'thumb_{i:02d}_l']
        nxt = V(m(b.tail), rr)
        edges.append((prev, nxt))
        prev = nxt
    me = bpy.data.meshes.new('hand_tmp')
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new('hand_tmp', me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    sk = ob.modifiers.new('Skin', 'SKIN')
    sk.branch_smoothing = 0.55
    sk.use_smooth_shade = True
    sub = ob.modifiers.new('Sub', 'SUBSURF')
    sub.levels = level
    sub.render_levels = level
    layer = me.skin_vertices[0]
    for i, r in enumerate(rad):
        layer.data[i].radius = (r, r)
    layer.data[wrist].use_root = True
    bpy.context.view_layer.update()
    v, f = G.eval_mesh(ob)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    # flatten: scale the thickness along the palm normal about the plane through the wrist, strongest at the palm
    pn = A([PN[0], sy * PN[1], PN[2]])
    w0 = m(W)
    palm_c = m(W + HD * 0.055)
    d = np.linalg.norm(v - palm_c, axis=1)
    strength = 0.42 * G.smoothstep((0.070 - d) / 0.040)
    strength += 0.16 * G.smoothstep((0.150 - d) / 0.08)
    off = (v - palm_c) @ pn
    v = v - np.outer(off * strength, pn)
    return v, f

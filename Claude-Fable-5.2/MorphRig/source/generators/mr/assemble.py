"""Builds all character geometry and returns MeshData parts (single place that defines the part list)."""
from . import body, head, hair, outfit, cyber, skel


def build_parts():
    parts = {}
    info = {}
    parts['Body'], info['body'] = body.build_body()
    hp, hinfo = head.build_head()
    info['head'] = hinfo
    parts['Head'] = hp['skin']
    parts['Lashes'] = hp['lashes']
    parts['Eyes'] = hp['eyes']
    parts['Teeth'] = hp['teeth']
    parts['Tongue'] = hp['tongue']
    parts['Hair'], info['hair'] = hair.build_hair(hinfo['shape'])
    parts['Outfit'], oinfo = outfit.build_outfit()
    info['outfit'] = oinfo
    cp, cinfo = cyber.build_cyber(oinfo, hinfo['shape'])
    parts['Cyber'] = cp['cyber']
    info['cyber'] = cinfo
    # construction helper vertices that no face uses (e.g. body grid points inside the arm holes) are removed.
    # The head keeps its vertex order: the face shape keys are defined on it.
    assert parts['Head'].unused_count() == 0, 'head mesh has unused vertices'
    info['removed_unused_vertices'] = {k: md.remove_unused() for k, md in parts.items() if k != 'Head'}
    return parts, info

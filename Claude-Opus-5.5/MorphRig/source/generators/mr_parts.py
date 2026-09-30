"""Registry of named mesh parts.  Faces carry an integer 'part' attribute (and costume shells a
'shell' attribute: 1 outer, 2 inner, 3 rim) so the texture stage can style each piece; the name
list is stored on the scene as JSON (scene['mr_part_names'])."""
NAMES = ["none"]


def pid(name):
    if name not in NAMES:
        NAMES.append(name)
    return NAMES.index(name)


def tag(m, name):
    """Set the part id of every face of Mesh m."""
    m.face_attrs["part"] = [pid(name)] * len(m.f)
    return m

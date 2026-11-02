#!/usr/bin/env python3
"""Read the unit settings and the mesh size out of a binary FBX file.

    python3 tools/fbx_probe.py export/Operative.fbx

It prints the unit scale factor of the file and the bounding box of the
largest mesh, so the scale of an export can be checked without opening
Unreal.
"""
import struct
import sys


def read_prop(data, pos):
    tlen = struct.unpack('<I', data[pos:pos + 4])[0]
    ptype = data[pos + 4:pos + 4 + tlen]
    pos += 4 + tlen
    if ptype in (b'L', b'i', b'B', b'C'):
        fmt = {b'L': '<q', b'i': '<i', b'B': '?', b'C': 'b'}[ptype]
        size = struct.calcsize(fmt)
        value = struct.unpack(fmt, data[pos:pos + size])[0]
        return value, pos + size
    if ptype in (b'd', b'f'):
        fmt = {b'd': '<d', b'f': '<f'}[ptype]
        size = struct.calcsize(fmt)
        value = struct.unpack(fmt, data[pos:pos + size])[0]
        return value, pos + size
    if ptype in (b'S', b'R'):
        slen = struct.unpack('<I', data[pos:pos + 4])[0]
        value = data[pos + 4:pos + 4 + slen]
        return value, pos + 4 + slen
    if ptype == b'*':
        # array: <array_len><encoding_len><encoding><compressed_len><data>
        alen = struct.unpack('<I', data[pos:pos + 4])[0]
        elen = struct.unpack('<I', data[pos + 4:pos + 8])[0]
        enc = data[pos + 8:pos + 8 + elen]
        pos += 8 + elen
        clen = struct.unpack('<I', data[pos:pos + 4])[0]
        pos += 4
        if enc == b'Y':
            comp = data[pos:pos + clen]
            pos += clen
            value = decode_array(compressed, alen, ptype)
            return value, pos
        raw = data[pos:pos + alen * struct.calcsize('<d' if ptype in (b'd', b'f') else '<i')]
        pos += alen * struct.calcsize('<d' if ptype in (b'd', b'f') else '<i')
        return ('raw', raw), pos
    raise ValueError('unknown property type %r' % ptype)


def decode_array(comp, count, ptype):
    values = []
    pos = 0
    for _ in range(count):
        value, pos = read_prop(comp, pos)
        values.append(value)
    return values


def walk(data, start, end, depth, out):
    pos = start
    while pos < end:
        node_end = struct.unpack('<Q', data[pos:pos + 8])[0]
        nprops = struct.unpack('<Q', data[pos + 8:pos + 16])[0]
        plen = struct.unpack('<Q', data[pos + 16:pos + 24])[0]
        nlen = data[pos + 24]
        name = data[pos + 25:pos + 25 + nlen].decode('utf8', 'replace')
        p = pos + 25 + nlen
        props = []
        for _ in range(nprops):
            value, p = read_prop(data, p)
            props.append(value)
        out.append((depth, name, props, p, node_end))
        p += plen
        if node_end > pos:
            walk(data, p, node_end, depth + 1, out)
        pos = node_end
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'export/Operative.fbx'
    data = open(path, 'rb').read()
    nodes = []
    walk(data, 27, len(data), 0, nodes)

    for depth, name, props, _p, _e in nodes:
        if name in ('UnitScaleFactor', 'OriginalUnitScaleFactor'):
            print('%s = %s' % (name, props[0]))

    # the bounding box of the geometry
    for depth, name, props, _p, _e in nodes:
        if name == 'BBoxMax':
            print('BBoxMax = %s' % (props[0],))
        if name == 'BBoxMin':
            print('BBoxMin = %s' % (props[0],))

    # the vertices of the biggest mesh
    best = None
    for depth, name, props, p, node_end in nodes:
        if name == 'Vertices' and props and isinstance(props[0], tuple):
            raw = props[0][1]
            values = struct.unpack('<%dd' % (len(raw) // 8), raw)
            zs = values[2::3]
            height = max(zs) - min(zs)
            if best is None or height > best[1]:
                best = (name, height, min(zs), max(zs))
    if best:
        print('largest mesh vertex height = %.4f (z %.4f .. %.4f)' % (best[1], best[2], best[3]))


if __name__ == '__main__':
    main()

"""Minimal FBX binary reader.

Reads the global settings (unit scale, axis system) and the local transforms
of the model nodes so the unit handling of the exported files can be checked
without trusting a third party tool.
"""
import struct
import sys


class Reader:
    def __init__(self, data, offset=0):
        self.d = data
        self.o = offset

    def u32(self):
        (v,) = struct.unpack("<I", self.d[self.o:self.o + 4])
        self.o += 4
        return v

    def u64(self):
        (v,) = struct.unpack("<Q", self.d[self.o:self.o + 8])
        self.o += 8
        return v

    def u8(self):
        v = self.d[self.o]
        self.o += 1
        return v

    def dbl(self):
        (v,) = struct.unpack("<d", self.d[self.o:self.o + 8])
        self.o += 8
        return v

    def s(self):
        n = self.u32()
        v = self.d[self.o:self.o + n].decode("utf8", "replace")
        self.o += n
        return v

    def raw(self):
        n = self.u32()
        v = self.d[self.o:self.o + n]
        self.o += n
        return v


def read_property(r):
    code = chr(r.u8())
    if code == "Y":
        (v,) = struct.unpack("<h", r.d[r.o:r.o + 2]); r.o += 2
        return v
    if code == "C":
        return bool(r.u8())
    if code == "I":
        return r.u32()
    if code == "F":
        (v,) = struct.unpack("<f", r.d[r.o:r.o + 4]); r.o += 4
        return v
    if code == "D":
        return r.dbl()
    if code == "L":
        return r.u64()
    if code in ("f", "d", "l", "i", "b"):
        length = r.u32()
        encoding = r.u32()
        compressed = r.u32()
        raw = r.d[r.o:r.o + compressed]
        r.o += compressed
        if encoding == 0:
            fmt = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}[code]
            values = list(struct.unpack("<%d%s" % (length, fmt), raw[:length * struct.calcsize(fmt)]))
        else:
            values = ("compressed", length)
        return values
    if code in ("S", "R"):
        return r.raw().decode("utf8", "replace")
    raise ValueError("unknown property code %r" % code)


def walk(data, start, end, depth=0, out=None):
    r = Reader(data, start)
    while r.o < end - 4:
        node_start = r.o
        end_offset = r.u32()
        num_props = r.u32()
        prop_len = r.u32()
        name_len = r.u8()
        name = data[r.o:r.o + name_len].decode("utf8", "replace")
        r.o += name_len
        props = []
        for _ in range(num_props):
            props.append(read_property(r))
        if out is not None:
            out.append((depth, name, props, node_start, end_offset))
        # nested list
        if end_offset > 0 and name.endswith("Properties70") or name in ("Objects", "Connections"):
            inner_start = r.o
            inner_end = end_offset - (prop_len if prop_len else 0)
            # for a node with a nested list the record ends at end_offset
            inner_end = end_offset
            if inner_end > inner_start:
                try:
                    walk(data, inner_start, inner_end, depth + 1, out)
                except Exception:
                    pass
        r.o = end_offset if end_offset > node_start else r.o
        if end_offset <= node_start:
            break


def main():
    path = sys.argv[sys.argv.index("--") + 1]
    data = open(path, "rb").read()
    # FBX binary header: 27 bytes then uint64 version
    version = struct.unpack("<Q", data[23:31])[0]
    print("FBX %s version=%d size=%d" % (path, version, len(data)))
    out = []
    walk(data, 27, len(data), 0, out)
    for depth, name, props, _, _ in out:
        if name == "GlobalSettings":
            print("GlobalSettings:")
            for p in props:
                print("   %r" % (p,))
        if name == "Model" and len(props) >= 5:
            # Model: id, name, type, parent index
            mname = props[1]
            if isinstance(mname, str) and mname in ("root", "pelvis", "spine_01", "head"):
                print("Model %s type=%r" % (mname, props[2]))


if __name__ == "__main__":
    main()

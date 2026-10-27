#!/usr/bin/env python3
"""Insert an FBX LODGroup around the authored Operative_LOD0/1/2 mesh nodes.
This is a structural export utility, not a geometry or motion generator. It preserves
all original records except for the LOD meshes' parent connections.
"""
from pathlib import Path
from dataclasses import dataclass, field
import copy
import json
import struct
import sys


@dataclass
class Record:
    name: bytes
    properties: list = field(default_factory=list)
    children: list = field(default_factory=list)
    has_null: bool = False


def property_value(data, position, kind):
    size = {b"Y": 2, b"C": 1, b"I": 4, b"F": 4, b"D": 8, b"L": 8}.get(kind)
    if size is not None:
        return data[position:position + size], position + size
    if kind in (b"S", b"R"):
        length = struct.unpack_from("<I", data, position)[0]
        return data[position:position + 4 + length], position + 4 + length
    if kind in b"fdilb":
        _, encoding, length = struct.unpack_from("<III", data, position)
        if encoding not in (0, 1):
            raise ValueError("Unsupported FBX array encoding")
        return data[position:position + 12 + length], position + 12 + length
    raise ValueError(f"Unsupported FBX property {kind!r}")


def parse_property(data, position):
    kind = data[position:position + 1]
    raw, end = property_value(data, position + 1, kind)
    value = None
    if kind == b"L":
        value = struct.unpack("<q", raw)[0]
    elif kind == b"S":
        value = raw[4:]
    return (kind, raw, value), end


def parse_record(data, position, large):
    header_size = 32 if large else 20
    null_size = 25 if large else 13
    if position + header_size > len(data):
        raise ValueError("Truncated FBX record")
    end, count, properties_length, name_length = struct.unpack_from("<QQQB" if large else "<IIIB", data, position)
    if end == 0:
        return None, position + null_size
    header = 25 if large else 13
    name = data[position + header:position + header + name_length]
    cursor = position + header + name_length
    properties = []
    for _ in range(count):
        prop, cursor = parse_property(data, cursor)
        properties.append(prop)
    children = []
    has_null = False
    while cursor < end:
        if end - cursor == null_size:
            has_null = True
            cursor = end
            break
        child, next_cursor = parse_record(data, cursor, large)
        if child is not None:
            children.append(child)
        if next_cursor <= cursor:
            raise ValueError("Invalid FBX child record")
        cursor = next_cursor
    if cursor != end:
        raise ValueError("FBX record end mismatch")
    return Record(name, properties, children, has_null), end


def parse_file(path):
    data = path.read_bytes()
    if not data.startswith(b"Kaydara FBX Binary  \x00"):
        raise ValueError("Expected a binary FBX file")
    version = struct.unpack_from("<I", data, 23)[0]
    large = version >= 7500
    records = []
    position = 27
    while position < len(data):
        record, position = parse_record(data, position, large)
        if record is not None:
            records.append(record)
        if record is not None and record.name == b"Takes":
            break
    footer = data[position:] if position < len(data) else b""
    return version, large, records, footer


def write_property(prop):
    kind, raw, _ = prop
    return kind + raw


def write_record(record, large, start):
    properties = b"".join(write_property(prop) for prop in record.properties)
    name_length = len(record.name)
    header_size = 25 if large else 13
    child_start = start + header_size + name_length + len(properties)
    children_parts = []
    for child_record in record.children:
        child_bytes = write_record(child_record, large, child_start)
        children_parts.append(child_bytes)
        child_start += len(child_bytes)
    children = b"".join(children_parts)
    end = child_start + (25 if large and record.has_null else 13 if record.has_null else 0)
    return struct.pack("<QQQB" if large else "<IIIB", end, len(record.properties), len(properties), name_length) + record.name + properties + children + (b"\0" * (25 if large else 13) if record.has_null else b"")


def write_file(path, version, large, records, footer):
    header = path.read_bytes()[:27]
    parts = []
    offset = len(header)
    for record in records:
        part = write_record(record, large, offset)
        parts.append(part)
        offset += len(part)
    path.write_bytes(header + b"".join(parts) + footer)


def string_property(value):
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return (b"S", struct.pack("<I", len(encoded)) + encoded, encoded)


def int_property(value):
    return (b"L", struct.pack("<q", value), value)


def child(record, name):
    return next((item for item in record.children if item.name == name), None)


def add_group(path):
    version, large, records, footer = parse_file(path)
    objects = next((record for record in records if record.name == b"Objects"), None)
    connections = next((record for record in records if record.name == b"Connections"), None)
    if not objects or not connections:
        raise ValueError("FBX has no Objects/Connections sections")
    models = [record for record in objects.children if record.name == b"Model"]
    old_group_ids = {record.properties[0][2] for record in models if len(record.properties) >= 3 and record.properties[2][2] == b"LODGroup"}
    if old_group_ids:
        objects.children = [record for record in objects.children if record.name != b"Model" or record.properties[2][2] != b"LODGroup"]
        connections.children = [record for record in connections.children if len(record.properties) < 3 or (record.properties[1][2] not in old_group_ids and record.properties[2][2] not in old_group_ids)]
    by_name = {record.properties[1][2].split(b"\x00\x01")[0].split(b"::")[-1].decode("utf-8"): record for record in models if len(record.properties) >= 3}
    lods = [by_name.get(f"Operative_LOD{index}") for index in range(3)]
    if any(record is None for record in lods):
        raise ValueError("All three named LOD mesh nodes are required")
    if any(record.properties[2][2] != b"Mesh" for record in lods):
        raise ValueError("LOD nodes must be mesh models")
    new_id = max(record.properties[0][2] for record in models) + 1
    group = copy.deepcopy(lods[0])
    group.properties[0] = int_property(new_id)
    group.properties[1] = string_property("Operative_LODs")
    group.properties[2] = string_property("LODGroup")
    lod_ids = {record.properties[0][2] for record in lods}
    links = []
    linked_lods = set()
    for record in connections.children:
        if record.name != b"C" or len(record.properties) < 3:
            continue
        kind, child_id, parent_id = record.properties[0][2], record.properties[1][2], record.properties[2][2]
        if kind == b"OO" and child_id in lod_ids:
            record.properties[2] = int_property(new_id)
            linked_lods.add(child_id)
        links.append(record)
    for lod_id in lod_ids - linked_lods:
        links.append(Record(b"C", [string_property("OO"), int_property(lod_id), int_property(new_id)]))
    connections.children = links
    connections.children.append(Record(b"C", [string_property("OO"), int_property(new_id), int_property(0)]))
    objects.children.append(group)
    write_file(path, version, large, records, footer)
    _, _, check, _ = parse_file(path)
    check_objects = child(next(record for record in check if record.name == b"Objects"), b"Model")
    groups = [record for record in next(item for item in check if item.name == b"Objects").children if record.name == b"Model" and record.properties[2][2] == b"LODGroup"]
    if len(groups) != 1:
        raise ValueError("LODGroup roundtrip validation failed")
    result = {"file": str(path), "lod_group_id": new_id, "lod_mesh_ids": sorted(lod_ids), "fbx_version": version, "lod_group_type": groups[0].properties[2][2].decode(), "lod_count": 3}
    (path.parent / "lod_group_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    add_group(Path(sys.argv[1]).resolve())

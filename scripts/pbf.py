"""Minimal read-only OSM PBF decoder (dense nodes and ways), standard library only."""
import struct
import zlib


def varint(buf, pos):
    value = 0
    shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
        shift += 7


def fields(buf):
    pos = 0
    while pos < len(buf):
        key, pos = varint(buf, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = varint(buf, pos)
        elif wire == 2:
            size, pos = varint(buf, pos)
            value = buf[pos:pos + size]
            pos += size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = buf[pos:pos + size]
            pos += size
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire}")
        yield number, value


def packed(buf, signed=False):
    pos = 0
    while pos < len(buf):
        value, pos = varint(buf, pos)
        yield (value >> 1) ^ -(value & 1) if signed else value


def blocks(path):
    with open(path, "rb") as stream:
        while header_len := stream.read(4):
            header = stream.read(struct.unpack(">I", header_len)[0])
            size = next(v for k, v in fields(header) if k == 3)
            blob = stream.read(size)
            parts = dict(fields(blob))
            if 1 in parts:
                data = parts[1]
            elif 3 in parts:
                data = zlib.decompress(parts[3])
            else:
                continue
            if b"OSMData" in header:
                yield data


def parse(path, bounds):
    """Return bbox nodes and driving ways, including their OSM tags and node refs."""
    west, south, east, north = bounds
    nodes, ways = {}, []
    for block in blocks(path):
        parts = dict(fields(block))
        strings = [v.decode("utf8", "replace") for _, v in fields(parts[1])]
        granularity = parts.get(17, 100)
        lat_offset = parts.get(19, 0)
        lon_offset = parts.get(20, 0)
        for group in (v for k, v in fields(block) if k == 2):
            for kind, item in fields(group):
                if kind == 2:  # DenseNodes
                    dense = dict(fields(item))
                    ids = packed(dense[1], True)
                    lats = packed(dense[8], True)
                    lons = packed(dense[9], True)
                    nid = lat = lon = 0
                    for di, dy, dx in zip(ids, lats, lons):
                        nid += di; lat += dy; lon += dx
                        x = (lon_offset + granularity * lon) * 1e-9
                        y = (lat_offset + granularity * lat) * 1e-9
                        if west <= x <= east and south <= y <= north:
                            nodes[str(nid)] = (round(x, 7), round(y, 7))
                elif kind == 1:  # Non-dense Node
                    d = dict(fields(item))
                    x = (lon_offset + granularity * ((d[9] >> 1) ^ -(d[9] & 1))) * 1e-9
                    y = (lat_offset + granularity * ((d[8] >> 1) ^ -(d[8] & 1))) * 1e-9
                    if west <= x <= east and south <= y <= north:
                        nodes[str(d[1])] = (round(x, 7), round(y, 7))
                elif kind == 3:  # Way
                    d = dict(fields(item))
                    keys = list(packed(d.get(2, b"")))
                    vals = list(packed(d.get(3, b"")))
                    tags = {strings[k]: strings[v] for k, v in zip(keys, vals)}
                    if "highway" not in tags:
                        continue
                    refs = []
                    ref = 0
                    for delta in packed(d.get(8, b""), True):
                        ref += delta
                        refs.append(str(ref))
                    ways.append((str(d[1]), refs, tags))
    return nodes, ways

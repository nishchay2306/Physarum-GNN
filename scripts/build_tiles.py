"""Convert cached OSM-based vector tiles to a compact directed road graph.

The tile schema preserves oneway tags, but tile generalization may omit minor roads
and cannot retain OSM turn restrictions. This is an offline demonstration extract.
"""
import json
import math
from pathlib import Path
from pbf import fields, packed

ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / "data/tiles"
OUT = ROOT / "data/guwahati_roads.json"
Z = 14
EXCLUDE = {"path", "pedestrian", "cycleway", "footway", "steps", "rail", "transit",
           "ferry", "aerialway", "horse", "track"}
SPEED = {"motorway": 65, "trunk": 55, "primary": 42, "secondary": 35,
         "tertiary": 30, "residential": 24, "street": 24, "minor": 24,
         "service": 16, "living_street": 15}


def zigzag(x):
    return (x >> 1) ^ -(x & 1)


def decode_value(buf):
    k, v = next(fields(buf))
    if k == 1: return v.decode("utf8", "replace")
    if k == 7: return bool(v)
    if k == 6: return zigzag(v)
    return v


def lines(buf):
    vals = list(packed(buf)); index = 0; x = y = 0; line = []
    while index < len(vals):
        command = vals[index] & 7; count = vals[index] >> 3; index += 1
        for _ in range(count):
            if command in (1, 2):
                x += zigzag(vals[index]); y += zigzag(vals[index + 1]); index += 2
                if command == 1 and line:
                    yield line
                    line = []
                line.append((x, y))
            elif command == 7:
                break
    if line: yield line


def ll(tile_x, tile_y, px, py, extent):
    x = (tile_x + px / extent) / (2 ** Z)
    y = (tile_y + py / extent) / (2 ** Z)
    return (round(x * 360 - 180, 7),
            round(math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y)))), 7))


def meters(a, b):
    x = math.radians(b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    y = math.radians(b[1] - a[1])
    return 6371000 * math.hypot(x, y)


def build():
    nodes, edges, seen = {}, [], set()
    for path in sorted(TILES.glob("*.pbf")):
        tile_x, tile_y = map(int, path.stem.split("_"))
        for _, layer in fields(path.read_bytes()):
            layer_fields = list(fields(layer))
            if next((v for k, v in layer_fields if k == 1), b"") != b"transportation":
                continue
            keys = [v.decode("utf8", "replace") for k, v in layer_fields if k == 3]
            values = [decode_value(v) for k, v in layer_fields if k == 4]
            extent = next((v for k, v in layer_fields if k == 5), 4096)
            for _, feature in ((k, v) for k, v in layer_fields if k == 2):
                f = dict(fields(feature))
                if f.get(3) != 2 or 4 not in f: continue  # LineString
                tags_idx = list(packed(f.get(2, b"")))
                tags = {keys[tags_idx[i]]: values[tags_idx[i + 1]]
                        for i in range(0, len(tags_idx), 2)}
                cls = str(tags.get("class", ""))
                subclass = str(tags.get("subclass", ""))
                if cls in EXCLUDE or subclass in EXCLUDE or tags.get("access") in ("no", "private"):
                    continue
                oneway = str(tags.get("oneway", "")).lower()
                direction = -1 if oneway in ("-1", "reverse") else 1 if oneway in ("1", "yes", "true") else 0
                speed = SPEED.get(subclass, SPEED.get(cls, 24))
                for line in lines(f[4]):
                    for a0, b0 in zip(line, line[1:]):
                        # Take the copy whose segment midpoint lies in its tile.
                        mx, my = (a0[0] + b0[0]) / 2, (a0[1] + b0[1]) / 2
                        if not (0 <= mx < extent and 0 <= my < extent): continue
                        a, b = ll(tile_x, tile_y, *a0, extent), ll(tile_x, tile_y, *b0, extent)
                        length = meters(a, b)
                        if length < 1: continue
                        if direction == -1: a, b = b, a
                        u, v = f"{a[0]},{a[1]}", f"{b[0]},{b[1]}"
                        identity = (u, v, cls, direction)
                        if identity in seen: continue
                        seen.add(identity)
                        nodes[u] = a; nodes[v] = b
                        edges.append({"id": len(edges), "u": u, "v": v,
                                      "oneway": direction != 0, "highway": subclass or cls,
                                      "bridge": tags.get("brunnel") == "bridge",
                                      "meters": round(length, 2), "speed_kmh": speed,
                                      "geometry": [a, b]})
    data = {"meta": {"source": "OpenStreetMap contributors via OpenFreeMap vector tiles",
                      "source_url": "https://tiles.openfreemap.org/planet/latest/{z}/{x}/{y}.pbf",
                      "zoom": Z, "bounds": [91.60, 26.045, 91.965, 26.255],
                      "license": "ODbL; © OpenStreetMap contributors",
                      "notes": "Tile-generalized OSM roads; one-way tags retained when present. Junctions reconstructed from shared vertices; turn restrictions and some minor roads are unavailable. Speeds are class defaults."},
            "nodes": nodes, "edges": edges}
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf8")
    print(f"Bundled {len(nodes)} road vertices and {len(edges)} segments to {OUT}")


if __name__ == "__main__": build()

"""One-time OSM PBF conversion. Runtime uses only the bundled JSON graph."""
import json
import math
from collections import Counter
from pathlib import Path

from pbf import parse

ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data/north-eastern-zone.osm.pbf"
OUT = ROOT / "data/guwahati_roads.json"
BOUNDS = (91.60, 26.045, 91.965, 26.255)  # west, south, east, north
DRIVE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
         "residential", "living_street", "service", "motorway_link", "trunk_link",
         "primary_link", "secondary_link", "tertiary_link"}
SPEED = {"motorway": 65, "trunk": 55, "primary": 42, "secondary": 35,
         "tertiary": 30, "residential": 24, "unclassified": 25,
         "service": 16, "living_street": 15}


def haversine(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371000 * math.hypot(x, y)


def build():
    raw_nodes, raw_ways = parse(PBF, BOUNDS)
    ways = []
    for wid, refs, tags in raw_ways:
        highway = tags.get("highway", "")
        if highway not in DRIVE or tags.get("motor_vehicle") in ("no", "private"):
            continue
        if tags.get("access") in ("no", "private") or tags.get("area") == "yes":
            continue
        # Clip each way to its contiguous runs inside the extraction rectangle.
        runs, current = [], []
        for ref in refs + [None]:
            if ref in raw_nodes:
                current.append((ref, *raw_nodes[ref]))
            elif len(current) >= 2:
                runs.append(current)
                current = []
            else:
                current = []
        tag = tags.get("oneway", "").lower()
        direction = -1 if tag == "-1" else 1 if tag in ("yes", "1", "true") or tags.get("junction") == "roundabout" or highway == "motorway" else 0
        for points in runs:
            ways.append((wid, points, highway, direction, tags.get("name", ""),
                         tags.get("bridge", "") == "yes"))
    counts = Counter(pid for _, points, *_ in ways for pid, *_ in points)
    nodes = {}
    edges = []
    for wid, points, highway, direction, name, bridge in ways:
        # Split at shared OSM nodes and at 600 m intervals, retaining all curve points.
        start = 0
        length = 0.0
        for i in range(1, len(points)):
            length += haversine(points[i - 1][1:], points[i][1:])
            if i != len(points) - 1 and counts[points[i][0]] < 2 and length < 600:
                continue
            segment = points[start:i + 1]
            start = i
            length = 0.0
            if not any(BOUNDS[0] <= x <= BOUNDS[2] and BOUNDS[1] <= y <= BOUNDS[3]
                       for _, x, y in segment):
                continue
            a, b = segment[0], segment[-1]
            if a[0] == b[0]:
                continue
            nodes[a[0]] = [a[1], a[2]]
            nodes[b[0]] = [b[1], b[2]]
            geom = [[x, y] for _, x, y in segment]
            meters = sum(haversine(geom[j - 1], geom[j]) for j in range(1, len(geom)))
            if meters < 1:
                continue
            if direction == -1:
                a, b = b, a
                geom.reverse()
            speed = SPEED.get(highway.replace("_link", ""), 25)
            edges.append({"id": len(edges), "u": a[0], "v": b[0], "osm_way": wid,
                          "oneway": direction != 0, "highway": highway, "name": name,
                          "bridge": bridge, "meters": round(meters, 2), "speed_kmh": speed,
                          "geometry": geom})
    data = {"meta": {"source": "OpenStreetMap contributors via BBBike North-Eastern Zone PBF",
                      "source_url": "https://download3.bbbike.org/osm/pbf/region/asia/india/north-eastern-zone.osm.pbf",
                      "bounds": BOUNDS, "license": "ODbL; © OpenStreetMap contributors",
                      "notes": "OSM geometry/direction; speeds are class defaults, not observed traffic. Turn restrictions are not modeled."},
            "nodes": nodes, "edges": edges}
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf8")
    print(f"Bundled {len(nodes)} OSM nodes, {len(edges)} road segments -> {OUT}")


if __name__ == "__main__":
    build()

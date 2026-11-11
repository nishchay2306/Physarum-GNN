import csv
import html
import time
from pathlib import Path
from .graph import RoadGraph
from .physarum import adapt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"


def svg(graph, original, recovered, blocked, source, target, title, path, route_label="Physarum detour"):
    coords = list(graph.nodes.values())
    west = min(x for x, _ in coords); east = max(x for x, _ in coords)
    south = min(y for _, y in coords); north = max(y for _, y in coords)
    width, height, pad = 1100, 610, 42
    def xy(p):
        return (pad + (p[0] - west) / (east - west) * (width - 2 * pad),
                pad + (north - p[1]) / (north - south) * (height - 2 * pad))
    def draw(eid, color, stroke, dash=""):
        e = graph.by_id[eid]
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(xy, e["geometry"]))
        return f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" {dash}/>'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#0b1525"/>',
             f'<text x="38" y="30" font-size="20" fill="white" font-family="sans-serif">{html.escape(title)}</text>']
    parts += [draw(e["id"], "#33465b", 1.25) for e in graph.edges]
    parts += [draw(i, "#eab85d", 4, 'stroke-dasharray="6 4"') for i in original]
    if recovered is not None:
        parts += [draw(i, "#27d0d1", 5) for i in recovered]
    parts += [draw(i, "#fa596b", 7) for i in blocked]
    for n, color, label in ((source, "#7feb95", "START"), (target, "#ffffff", "DESTINATION")):
        x, y = xy(graph.nodes[n])
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}" stroke="#111" stroke-width="2"/>',
                  f'<text x="{x+12:.1f}" y="{y-10:.1f}" fill="white" font-size="13" font-family="sans-serif">{label}</text>']
    parts += ['<rect x="28" y="552" width="1042" height="40" rx="8" fill="#152438"/>',
              f'<text x="43" y="578" fill="#e9f3ff" font-size="15" font-family="sans-serif">Orange dashed: original | Cyan: {html.escape(route_label)} | Red: simulated closure | (c) OpenStreetMap contributors</text>', '</svg>']
    path.write_text("\n".join(parts), encoding="utf8")


def demo():
    OUT.mkdir(exist_ok=True)
    graph = RoadGraph(bounds=(91.645, 26.135, 91.735, 26.185))
    parent = {n: n for n in graph.nodes}
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for e in graph.edges:
        parent[root(e["u"])] = root(e["v"])
    from collections import Counter
    largest = Counter(root(n) for n in graph.nodes).most_common(1)[0][0]
    connected = [n for n in graph.nodes if root(n) == largest]
    def pick(lon, lat):
        return min(connected, key=lambda n: ((graph.nodes[n][0] - lon) * .9) ** 2 +
                   (graph.nodes[n][1] - lat) ** 2)
    source = pick(91.665, 26.150)
    target = pick(91.715, 26.167)
    original = graph.dijkstra(source, target)
    if not original: raise RuntimeError("Bundled graph has no initial route")
    candidates = original[len(original)//3: 2*len(original)//3]
    alternatives = [(graph.drive_time(graph.dijkstra(source, target, {eid})) or float("inf"), eid)
                    for eid in candidates if graph.by_id[eid]["meters"] > 8]
    choices = [(minutes, eid) for minutes, eid in alternatives if minutes < float("inf")]
    if not choices: raise RuntimeError("No recoverable closure in this corridor")
    _, closure = max(choices)
    blocked = {closure}
    _, warm, pressure = adapt(graph, source, target, set(), rounds=5)
    before = OUT / "maligaon_before.svg"
    after = OUT / "maligaon_after.svg"
    svg(graph, original, None, set(), source, target,
        "BEFORE  |  Maligaon → Kamakhya  |  original emergency route", before)
    t0 = time.perf_counter_ns()
    dijkstra = graph.dijkstra(source, target, blocked)
    dijkstra_ms = (time.perf_counter_ns() - t0) / 1e6
    t0 = time.perf_counter_ns()
    phys, _, _ = adapt(graph, source, target, blocked, warm, prior_pressure=pressure)
    phys_ms = (time.perf_counter_ns() - t0) / 1e6
    svg(graph, original, phys, blocked, source, target,
        "AFTER  |  simulated road closure  |  Physarum self-healing detour", after)
    rows = []
    for name, route, latency in (("Fixed pre-disaster", original, 0.),
                                 ("Dijkstra rerun", dijkstra, dijkstra_ms),
                                 ("Physarum warm-start", phys, phys_ms)):
        rows.append({"scenario": "Maligaon–Kamakhya simulated closure", "method": name,
                     "valid_route": graph.valid(route, source, target, blocked),
                     "estimated_drive_min": round(graph.drive_time(route), 3) if route else "",
                     "reroute_ms": round(latency, 3), "closed_edge": closure})
    with (OUT / "benchmark.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    print("Simulated Maligaon–Kamakhya road closure; OSM-derived road geometry, class-based speeds")
    for r in rows:
        print(f"{r['method']:24} valid={str(r['valid_route']):5}  "
              f"drive={str(r['estimated_drive_min']):>7} min  reroute={r['reroute_ms']:>9} ms")
    print(f"Maps: {before}, {after}\nCSV: {OUT / 'benchmark.csv'}")
    return rows

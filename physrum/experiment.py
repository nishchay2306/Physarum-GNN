"""Reproducible offline command-line scenarios and measured comparisons."""
import argparse
import csv
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

from .demo import OUT, ROOT, svg
from .graph import RoadGraph
from .model import MODEL, base_features, load, predict, save, train
from .physarum import adapt

SCENARIOS = {
    "maligaon": {"name": "Maligaon-Kamakhya closures", "kind": "simulated road closure",
                  "bounds": (91.645, 26.135, 91.735, 26.185),
                  "start": (91.685, 26.158), "end": (91.713, 26.168), "hazard": (91.698, 26.162)},
    "jorabat": {"name": "Jorabat landslide", "kind": "simulated landslide",
                 "bounds": (91.845, 26.09, 91.915, 26.14),
                 "start": (91.8820846, 26.1015011), "end": (91.8854535, 26.107513),
                 "hazard": (91.8795, 26.101)},
    "panikhaiti": {"name": "Panikhaiti-Chandrapur approach flooding", "kind": "simulated flood",
                    "bounds": (91.805, 26.145, 91.89, 26.195),
                    "start": (91.84, 26.17), "end": (91.86, 26.175), "hazard": (91.854, 26.174)},
}

# Distinct affected corridors for supervised simulation; none overlaps the three
# named held-out hazard centers. All labels come from simulated closures.
TRAINING = [
    ((91.745, 26.18, 91.805, 26.23), (91.755, 26.195), (91.785, 26.21)),
    ((91.765, 26.115, 91.825, 26.16), (91.775, 26.125), (91.81, 26.15)),
    ((91.62, 26.19, 91.675, 26.235), (91.63, 26.205), (91.665, 26.22)),
    ((91.725, 26.08, 91.775, 26.125), (91.737, 26.091), (91.765, 26.114)),
    ((91.91, 26.07, 91.96, 26.11), (91.92, 26.08), (91.95, 26.1)),
]


def endpoints(graph, start, end, hazard=None):
    parent = {n: n for n in graph.nodes}
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    for e in graph.edges: parent[root(e["u"])] = root(e["v"])
    groups = Counter(root(n) for n in graph.nodes)
    # Prefer the closest connected component that can demonstrate a detour.
    candidates = [n for n in graph.nodes if groups[root(n)] >= 70]
    ranked = sorted(set(root(n) for n in candidates), key=lambda r: -groups[r])[:30]
    options = []
    for r in ranked:
        pool = [n for n in candidates if root(n) == r]
        def pick(pos):
            return min(pool, key=lambda n: ((graph.nodes[n][0] - pos[0]) * .9)**2 +
                       (graph.nodes[n][1] - pos[1])**2)
        a, b = pick(start), pick(end)
        if a == b: continue
        distance = sum(((graph.nodes[n][0]-position[0])**2 * .9**2 +
                        (graph.nodes[n][1]-position[1])**2)
                       for n, position in ((a, start), (b, end)))
        options.append((distance, a, b))
    for _, a, b in sorted(options):
        route = graph.dijkstra(a, b)
        if route and (hazard is None or any(
                graph.dijkstra(a, b, {eid}) for eid in closure_on_route(graph, route, hazard))):
            return a, b
    raise RuntimeError("No directed route between scenario endpoints")


def closure_on_route(graph, route, hazard):
    middle = route
    def distance(eid):
        points = graph.by_id[eid]["geometry"]
        x = sum(p[0] for p in points) / len(points)
        y = sum(p[1] for p in points) / len(points)
        return ((x-hazard[0])*.9)**2 + (y-hazard[1])**2
    return sorted((e for e in middle if graph.by_id[e]["meters"] >= 6), key=distance)


def train_offline():
    examples, scenes = [], 0
    rng = random.Random(2306)
    for bounds, a, b in TRAINING:
        graph = RoadGraph(bounds=bounds)
        try: source, target = endpoints(graph, a, b)
        except RuntimeError: continue
        original = graph.dijkstra(source, target)
        if not original or len(original) < 12: continue
        candidates = original[len(original)//4:3*len(original)//4]
        for eid in rng.sample(candidates, min(5, len(candidates))):
            blocked = {eid}
            oracle = graph.dijkstra(source, target, blocked)
            if not oracle or oracle == original: continue
            feats = base_features(graph, blocked, original)
            positives = list(set(oracle) - set(original))
            if not positives: continue
            near = [i for i, x in feats.items() if x[6] > .04 and i not in oracle and i not in blocked]
            negatives = rng.sample(near, min(len(near), 4 * len(positives)))
            examples.extend((feats[i], 1) for i in positives)
            examples.extend((feats[i], 0) for i in negatives)
            scenes += 1
    if scenes < 3: raise RuntimeError("Insufficient distinct training disruptions")
    model = train(examples)
    model["training_scenarios"] = scenes
    model["training_examples"] = len(examples)
    model["training_bounds"] = [x[0] for x in TRAINING]
    save(model)
    print(f"Trained one-hop spatial GNN on {scenes} simulated closures, {len(examples)} edge examples; held-out corridors excluded")
    return model


def route_setup(key):
    config = SCENARIOS[key]
    graph = RoadGraph(bounds=config["bounds"])
    source, target = endpoints(graph, config["start"], config["end"], config["hazard"])
    original = graph.dijkstra(source, target)
    return graph, source, target, original


def describe_route(graph, source, route):
    """Return road IDs and continuous route coordinates in travel direction."""
    if route is None:
        return None
    node = source
    coordinates = [list(graph.nodes[node])]
    for eid in route:
        edge = graph.by_id[eid]
        if node == edge["u"]:
            node = edge["v"]
            segment = edge["geometry"]
        elif node == edge["v"] and not edge["oneway"]:
            node = edge["u"]
            segment = edge["geometry"][::-1]
        else:
            raise ValueError(f"Route is not continuous at edge {eid}")
        coordinates.extend(list(p) for p in segment[1:])
    return {"edge_ids": route, "coordinates_lon_lat": coordinates}


def print_original_route(key):
    graph, source, target, original = route_setup(key)
    print(f"Original route in {key}: {len(original)} road IDs; "
          f"start={graph.nodes[source]}, destination={graph.nodes[target]}")
    print("Choose an ID below, then run --scenario " + key + " --close-edge ID")
    for eid in original:
        edge = graph.by_id[eid]
        midpoint = tuple(round((a+b)/2, 6) for a, b in zip(*edge["geometry"]))
        print(f"{eid:>8}  lon,lat={midpoint}  one_way={edge['oneway']}")
    return original


def run_one(key, config, model, manual=None, close_at=None):
    graph, source, target, original = route_setup(key)
    if close_at is not None:
        def dist(e):
            p = e["geometry"][len(e["geometry"])//2]
            return ((p[0] - close_at[0]) * .9)**2 + (p[1] - close_at[1])**2
        blocked = {min(graph.edges, key=dist)["id"]}
    elif manual:
        blocked = set(manual)
        if blocked - graph.by_id.keys(): raise ValueError("Custom edge ID outside scenario road graph")
    else:
        blocked = None
        for eid in closure_on_route(graph, original, config["hazard"]):
            trial = {eid}
            if graph.dijkstra(source, target, trial):
                blocked = trial; break
        if blocked is None: raise RuntimeError(f"No recoverable closure in {key}")
    custom = manual is not None or close_at is not None
    tag = f"{key}_custom_{'_'.join(map(str, sorted(blocked)))}" if custom else key
    _, warm, pressure = adapt(graph, source, target, set(), rounds=4)
    before, after = OUT / f"{tag}_before.svg", OUT / f"{tag}_after.svg"
    svg(graph, original, None, set(), source, target,
        f"BEFORE | {config['name']} | original route", before)
    t = time.perf_counter_ns()
    dijkstra = graph.dijkstra(source, target, blocked)
    dij_ms = (time.perf_counter_ns() - t) / 1e6
    t = time.perf_counter_ns()
    phys, _, _ = adapt(graph, source, target, blocked, warm, prior_pressure=pressure)
    phys_ms = (time.perf_counter_ns() - t) / 1e6
    t = time.perf_counter_ns()
    scores = predict(graph, blocked, original, model)  # inference included in latency
    seeded = {i: max(.04, warm[i] * (.65 + 1.35 * scores[i])) for i in warm}
    gnn, _, _ = adapt(graph, source, target, blocked, seeded, prior_pressure=pressure)
    gnn_ms = (time.perf_counter_ns() - t) / 1e6
    svg(graph, original, phys, blocked, source, target,
        f"AFTER | {config['name']} | {config['kind']} | Physarum detour", after)
    method_maps = {"Physarum": after}
    for name, route, suffix in (("Dijkstra rerun", dijkstra, "dijkstra"),
                                ("Physarum-GNN", gnn, "gnn")):
        path = OUT / f"{tag}_after_{suffix}.svg"
        svg(graph, original, route, blocked, source, target,
            f"AFTER | {config['name']} | {name}", path, route_label=name)
        method_maps[name] = path
    bypass = set(dijkstra or []) - set(original)
    ranked = sorted((i for i in scores if i not in blocked), key=scores.get, reverse=True)
    top = set(ranked[:max(1, round(len(ranked) * .05))])
    recall = len(bypass & top) / len(bypass) if bypass else None
    rows = []
    paths = {"scenario": key, "closure_type": "simulated custom" if custom else config["kind"],
             "closed_edge_ids": sorted(blocked), "start_lon_lat": graph.nodes[source],
             "destination_lon_lat": graph.nodes[target], "maps": {"before": str(before.relative_to(ROOT))},
             "methods": {}}
    for name, route, latency in (("Fixed pre-disaster", original, 0.),
                                 ("Dijkstra rerun", dijkstra, dij_ms),
                                 ("Physarum", phys, phys_ms),
                                 ("Physarum-GNN", gnn, gnn_ms)):
        valid = graph.valid(route, source, target, blocked)
        paths["methods"][name] = {"valid_after_closure": valid,
            "estimated_drive_min": round(graph.drive_time(route), 3) if valid else None,
            "reroute_ms": round(latency, 3), "path": describe_route(graph, source, route)}
        if name in method_maps:
            paths["maps"][name] = str(method_maps[name].relative_to(ROOT))
        rows.append({"scenario": key, "hazard": config["kind"], "method": name,
                     "valid_route": valid, "estimated_drive_min": round(graph.drive_time(route), 3) if valid else "",
                     "reroute_ms": round(latency, 3),
                     "closed_edge_ids": ";".join(map(str, sorted(blocked))),
                     "route_edge_ids": ";".join(map(str, route)) if route is not None else "",
                     "route_edge_count": len(route) if route else 0,
                     "pre_disaster_drive_min": round(graph.drive_time(original), 3)})
    paths_file = OUT / f"{tag}_routes.json"
    paths_file.write_text(json.dumps(paths, indent=2), encoding="utf8")
    return rows, {"scenario": key, "held_out_bypass_edges": len(bypass),
                  "gnn_recall_at_top_5pct": round(recall, 3) if recall is not None else ""}, paths_file


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Guwahati emergency routing benchmark")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--list-route", action="store_true", help="Print original route road IDs to select a closure")
    parser.add_argument("--interactive", action="store_true", help="Show original road IDs and prompt for IDs to block")
    parser.add_argument("--close-edge", help="Comma-separated local edge IDs; requires one scenario")
    parser.add_argument("--close-at", help="Close nearest edge to LON,LAT; requires one scenario")
    parser.add_argument("--train", action="store_true", help="Retrain on seeded simulated corridors")
    args = parser.parse_args(argv)
    if (args.close_edge or args.close_at or args.list_route or args.interactive) and args.scenario == "all":
        parser.error("custom closures and route listing require --scenario")
    if sum(bool(x) for x in (args.close_edge, args.close_at, args.interactive)) > 1:
        parser.error("choose one custom closure mode")
    if args.list_route:
        print_original_route(args.scenario)
        return
    OUT.mkdir(exist_ok=True)
    model = train_offline() if args.train or not MODEL.exists() else load()
    if args.interactive:
        print_original_route(args.scenario)
        args.close_edge = input("Road ID(s) to block, separated by commas: ").strip()
    try:
        manual = {int(value.strip()) for value in args.close_edge.split(",")} if args.close_edge else None
        close_at = tuple(map(float, args.close_at.split(","))) if args.close_at else None
    except ValueError:
        parser.error("use integer road IDs for --close-edge, or LON,LAT for --close-at")
    if args.interactive and not manual: parser.error("enter at least one road ID")
    if close_at is not None and len(close_at) != 2: parser.error("--close-at expects LON,LAT")
    all_rows, evaluations = [], []
    for key in SCENARIOS if args.scenario == "all" else [args.scenario]:
        try:
            rows, evaluation, paths_file = run_one(key, SCENARIOS[key], model, manual, close_at)
        except ValueError as error:
            parser.error(str(error))
        all_rows.extend(rows)
        evaluations.append(evaluation)
        print(f"\n{SCENARIOS[key]['name']} ({SCENARIOS[key]['kind']})")
        for r in rows:
            print(f"{r['method']:20} valid={str(r['valid_route']):5}  drive={str(r['estimated_drive_min']):>7} min  reroute={r['reroute_ms']:>9} ms")
            ids = r["route_edge_ids"].split(";") if r["route_edge_ids"] else []
            preview = ";".join(ids[:12]) + (";..." if len(ids) > 12 else "") if ids else "UNREACHABLE"
            print(f"  path ({len(ids)} road IDs): {preview}")
        print(f"  blocked road IDs: {rows[0]['closed_edge_ids']}")
        print(f"  route coordinates and method maps: {paths_file}")
    csv_path = OUT / "benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0]); writer.writeheader(); writer.writerows(all_rows)
    with (OUT / "model_evaluation.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=evaluations[0]); writer.writeheader(); writer.writerows(evaluations)
    print(f"\nSaved {csv_path} and before/after SVG maps in {OUT}")


if __name__ == "__main__": main()

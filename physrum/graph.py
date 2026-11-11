import heapq
import json
import math
from pathlib import Path


class RoadGraph:
    def __init__(self, path=None, bounds=None):
        path = path or Path(__file__).resolve().parents[1] / "data/guwahati_roads.json"
        raw = json.loads(Path(path).read_text(encoding="utf8"))
        nodes = raw["nodes"]
        self.nodes = {k: tuple(v) for k, v in nodes.items()
                      if bounds is None or bounds[0] <= v[0] <= bounds[2] and bounds[1] <= v[1] <= bounds[3]}
        self.edges = [e for e in raw["edges"] if e["u"] in self.nodes and e["v"] in self.nodes]
        self.by_id = {e["id"]: e for e in self.edges}
        self.adj = {n: [] for n in self.nodes}
        for e in self.edges:
            self.adj[e["u"]].append((e["v"], e["id"]))
            if not e["oneway"]:
                self.adj[e["v"]].append((e["u"], e["id"]))

    def nearest(self, lon, lat):
        return min(self.nodes, key=lambda n: ((self.nodes[n][0] - lon) * .9) ** 2 +
                   (self.nodes[n][1] - lat) ** 2)

    def minutes(self, eid):
        e = self.by_id[eid]
        return e["meters"] / (e["speed_kmh"] * 1000 / 60)

    def dijkstra(self, source, target, blocked=frozenset(), weights=None):
        pq, best, previous = [(0., source)], {source: 0.}, {}
        while pq:
            cost, u = heapq.heappop(pq)
            if cost > best[u] + 1e-9: continue
            if u == target: break
            for v, eid in self.adj[u]:
                if eid in blocked: continue
                step = self.minutes(eid) if weights is None else weights[eid]
                new = cost + step
                if new + 1e-10 < best.get(v, float("inf")):
                    best[v] = new; previous[v] = (u, eid)
                    heapq.heappush(pq, (new, v))
        if target not in best: return None
        route, u = [], target
        while u != source:
            u, eid = previous[u]
            route.append(eid)
        return route[::-1]

    def drive_time(self, route):
        return None if route is None else sum(self.minutes(e) for e in route)

    def valid(self, route, source, target, blocked):
        if route is None: return False
        frontier = {source}
        for eid in route:
            if eid in blocked: return False
            e = self.by_id[eid]
            new = set()
            if e["u"] in frontier: new.add(e["v"])
            if not e["oneway"] and e["v"] in frontier: new.add(e["u"])
            if not new: return False
            frontier = new
        return target in frontier

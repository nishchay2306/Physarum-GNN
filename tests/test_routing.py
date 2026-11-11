"""Safety invariants for directed roads and disruptions."""
import json
import tempfile
import unittest
from pathlib import Path

from physrum.graph import RoadGraph
from physrum.physarum import adapt


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "roads.json"
        nodes = {"A": [0, 0], "B": [1, 0], "C": [2, 0], "D": [1, 1]}
        roads = [("A", "B", True), ("B", "C", True),
                 ("A", "D", False), ("D", "C", False)]
        edges = [{"id": i, "u": u, "v": v, "oneway": one,
                  "meters": 100, "speed_kmh": 30,
                  "geometry": [nodes[u], nodes[v]]}
                 for i, (u, v, one) in enumerate(roads)]
        path.write_text(json.dumps({"nodes": nodes, "edges": edges}))
        self.graph = RoadGraph(path)

    def test_oneway_and_detour(self):
        g = self.graph
        self.assertEqual(g.dijkstra("A", "C"), [0, 1])
        self.assertEqual(g.dijkstra("C", "A"), [3, 2])
        closed = {1}
        self.assertEqual(g.dijkstra("A", "C", closed), [2, 3])
        self.assertFalse(g.valid([0, 1], "A", "C", closed))
        route, _, _ = adapt(g, "A", "C", closed, rounds=3)
        self.assertTrue(g.valid(route, "A", "C", closed))

    def test_unreachable(self):
        route, _, _ = adapt(self.graph, "A", "C", {0, 2}, rounds=3)
        self.assertIsNone(route)


if __name__ == "__main__": unittest.main()

"""Export the existing fleet map and trained weights for the browser demo."""

import json
from pathlib import Path

from physrum.dynamic import DEFAULT_END, DEFAULT_START, DISPLAY_BOUNDS, GRAPH
from physrum.fleet import DEPOTS, ZONES
from physrum.graph import RoadGraph
from physrum.model import load


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "map.json"


def main():
    background = RoadGraph(bounds=DISPLAY_BOUNDS)
    background.edges.extend(edge for edge in GRAPH.edges if edge.get("simulated"))
    data = {
        "nodes": GRAPH.nodes,
        "edges": background.edges,
        "background_nodes": background.nodes,
        "default_start": DEFAULT_START,
        "default_end": DEFAULT_END,
        "depots": DEPOTS,
        "zones": ZONES,
        "model": load(),
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

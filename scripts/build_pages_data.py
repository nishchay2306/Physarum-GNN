"""Export the map, trained weights, and frontend for the GitHub Pages demo."""

import json
from pathlib import Path

from physrum.dynamic import DEFAULT_END, DEFAULT_START, DISPLAY_BOUNDS, GRAPH
from physrum.fleet import DEPOTS, ZONES, MAX_PAIRS, default_pairs
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
        "default_pairs": default_pairs(),
        "max_pairs": MAX_PAIRS,
        "model": load(),
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    frontend = (ROOT / "fleet.html").read_text(encoding="utf-8")
    if frontend.count("fetch('/api/") != 3 or frontend.count("<script>") != 1:
        raise ValueError("The Python frontend API calls changed; update the Pages adapter.")
    frontend = frontend.replace("fetch('/api/", "pagesApiFetch('/api/")
    frontend = frontend.replace("<script>", '<script src="pages-api.js"></script>\n<script>', 1)
    (OUTPUT.parent / "index.html").write_text(frontend, encoding="utf-8")
    print(f"Wrote {OUTPUT} and {OUTPUT.parent / 'index.html'}")


if __name__ == "__main__":
    main()

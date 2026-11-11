"""Small spatial edge GNN trained only on simulated closures outside test corridors."""
import json
import math
import random
from pathlib import Path

MODEL = Path(__file__).resolve().parents[1] / "data/gnn_weights.json"
HILLS = ((91.775, 26.115), (91.91, 26.095), (91.74, 26.12))


def base_features(graph, blocked, original):
    closed = [graph.by_id[i] for i in blocked]
    if closed:
        cx = sum((e["geometry"][0][0] + e["geometry"][-1][0]) / 2 for e in closed) / len(closed)
        cy = sum((e["geometry"][0][1] + e["geometry"][-1][1]) / 2 for e in closed) / len(closed)
    else:
        cx = cy = 0.
    original = set(original)
    raw, incident = {}, {n: [] for n in graph.nodes}
    for e in graph.edges:
        eid = e["id"]
        x = (graph.nodes[e["u"]][0] + graph.nodes[e["v"]][0]) / 2
        y = (graph.nodes[e["u"]][1] + graph.nodes[e["v"]][1]) / 2
        hill = max(math.exp(-((x - hx)**2 + (y - hy)**2) / (.025**2)) for hx, hy in HILLS)
        flood = math.exp(-((y - .19) / .03)**2) * min(1., max(0., (x - 91.7) / .2))
        proximity = math.exp(-(((x - cx) * .9)**2 + (y - cy)**2) / (.006**2))
        raw[eid] = [min(1., e["meters"] / 200), e["speed_kmh"] / 65,
                    float(e["oneway"]), float(e["bridge"]), hill, flood,
                    proximity, float(eid in original), float(eid in blocked)]
        incident[e["u"]].append(eid); incident[e["v"]].append(eid)
    # One-hop line-graph message passing: mean incident edge context.
    out = {}
    for e in graph.edges:
        eid = e["id"]
        neighbors = set(incident[e["u"]] + incident[e["v"]]) - {eid}
        mean = [sum(raw[j][k] for j in neighbors) / len(neighbors) if neighbors else 0.
                for k in (1, 6, 7)]
        out[eid] = raw[eid] + mean
    return out


def sigmoid(x):
    x = max(-30., min(30., x))
    return 1 / (1 + math.exp(-x))


def predict_one(model, x):
    h = [math.tanh(sum(w * a for w, a in zip(row, x)) + bias)
         for row, bias in zip(model["w1"], model["b1"])]
    return sigmoid(sum(w * a for w, a in zip(model["w2"], h)) + model["b2"])


def predict(graph, blocked, original, model):
    features = base_features(graph, blocked, original)
    return {eid: predict_one(model, feat) for eid, feat in features.items()}


def train(examples, seed=2306, epochs=32):
    """Train a learned hidden projection and readout over one-hop edge messages."""
    rng = random.Random(seed)
    dim, hidden = 12, 8
    model = {"w1": [[rng.uniform(-.2, .2) for _ in range(dim)] for _ in range(hidden)],
             "b1": [0.] * hidden, "w2": [rng.uniform(-.2, .2) for _ in range(hidden)],
             "b2": 0., "architecture": "one-hop edge mean + learned tanh(12x8) + sigmoid",
             "seed": seed, "training": "simulated closures on corridors distinct from three held-out scenes"}
    for epoch in range(epochs):
        rng.shuffle(examples)
        lr = .035 * (1 - .7 * epoch / epochs)
        for x, label in examples:
            h = [math.tanh(sum(w*a for w, a in zip(row, x)) + b)
                 for row, b in zip(model["w1"], model["b1"])]
            pred = sigmoid(sum(w*a for w, a in zip(model["w2"], h)) + model["b2"])
            error = pred - label
            dh = [error * model["w2"][j] * (1 - h[j]*h[j]) for j in range(hidden)]
            for j in range(hidden):
                model["w2"][j] -= lr * error * h[j]
                for k in range(dim): model["w1"][j][k] -= lr * dh[j] * x[k]
                model["b1"][j] -= lr * dh[j]
            model["b2"] -= lr * error
    return model


def save(model):
    MODEL.write_text(json.dumps(model, indent=2), encoding="utf8")


def load():
    return json.loads(MODEL.read_text(encoding="utf8"))

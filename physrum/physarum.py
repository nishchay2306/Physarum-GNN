"""Pressure/flux dynamics; directional restrictions apply to extracted routes."""
import math


def _pressures(graph, source, target, blocked, conductivity, guess=None, iterations=110):
    # Matrix-free conjugate gradient on the grounded, undirected road Laplacian.
    # Directed roads are enforced in path extraction; the pressure field is a
    # symmetric relaxation rather than a directed conservation law.
    active = [e for e in graph.edges if e["id"] not in blocked]
    nodes = list(graph.nodes)
    index = {n: i for i, n in enumerate(nodes)}
    grounded = index[target]
    terms, diagonal = [], [0.] * len(nodes)
    for e in active:
        a, b = index[e["u"]], index[e["v"]]
        g = max(.001, conductivity[e["id"]]) / max(.01, graph.minutes(e["id"]))
        terms.append((a, b, g))
        diagonal[a] += g; diagonal[b] += g
    rhs = [0.] * len(nodes); rhs[index[source]] = 1.
    rhs[grounded] = 0.
    x = [0.] * len(nodes) if guess is None else [guess.get(n, 0.) for n in nodes]
    x[grounded] = 0.

    def multiply(v):
        out = [0.] * len(nodes)
        for a, b, g in terms:
            q = g * (v[a] - v[b])
            out[a] += q; out[b] -= q
        out[grounded] = v[grounded]
        return out

    ax = multiply(x)
    r = [rhs[i] - ax[i] for i in range(len(nodes))]
    z = [r[i] / diagonal[i] if diagonal[i] else 0. for i in range(len(nodes))]
    z[grounded] = 0.
    p = z[:]; rz = sum(a * b for a, b in zip(r, z))
    for _ in range(iterations):
        if rz < 1e-14: break
        ap = multiply(p)
        denom = sum(a * b for a, b in zip(p, ap))
        if denom <= 0: break
        alpha = rz / denom
        for i in range(len(nodes)):
            x[i] += alpha * p[i]; r[i] -= alpha * ap[i]
        z = [r[i] / diagonal[i] if diagonal[i] else 0. for i in range(len(nodes))]
        z[grounded] = 0.
        new = sum(a * b for a, b in zip(r, z))
        beta = new / rz
        p = [z[i] + beta * p[i] for i in range(len(nodes))]
        rz = new
    x[grounded] = 0.
    return dict(zip(nodes, x))


def adapt(graph, source, target, blocked, initial=None, rounds=7, prior_pressure=None):
    conductivity = {e["id"]: 1. if initial is None else initial.get(e["id"], 1.)
                    for e in graph.edges}
    for eid in blocked: conductivity[eid] = 0.
    # A disconnected destination has no safe route; avoid a singular Laplacian.
    if graph.dijkstra(source, target, blocked) is None:
        return None, conductivity, None
    pressure = prior_pressure
    for _ in range(rounds):
        pressure = _pressures(graph, source, target, blocked, conductivity, pressure)
        for e in graph.edges:
            eid = e["id"]
            if eid in blocked: continue
            delta = pressure[e["u"]] - pressure[e["v"]]
            # One-way road only reinforces if flux points in its legal direction.
            flux = conductivity[eid] / max(.01, graph.minutes(eid)) * (
                max(0., delta) if e["oneway"] else abs(delta))
            conductivity[eid] = max(.04, min(3., .77 * conductivity[eid] +
                                         .23 * min(3., 2.2 * flux)))
    costs = {e["id"]: graph.minutes(e["id"]) / (.25 + .75 * conductivity[e["id"]])
             for e in graph.edges}
    return graph.dijkstra(source, target, blocked, costs), conductivity, pressure

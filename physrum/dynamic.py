"""Tick-driven, seeded disaster simulation on an OSM-derived Guwahati component."""
import copy
import queue
import random
import threading
import time
from collections import deque

from .experiment import route_setup
from .graph import RoadGraph
from .model import load, predict
from .physarum import adapt


def local_graph():
    graph, source, target, _ = route_setup('maligaon')
    original = connected_component(graph, source)
    xs = [p[0] for p in original.nodes.values()]
    ys = [p[1] for p in original.nodes.values()]
    cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    bounds = (cx-.75*(max(xs)-min(xs)), cy-.75*(max(ys)-min(ys)),
              cx+.75*(max(xs)-min(xs)), cy+.75*(max(ys)-min(ys)))
    return connected_component(RoadGraph(bounds=bounds), source), source, target, bounds


def connected_component(graph, source):
    neighbors = {n: [] for n in graph.nodes}
    for e in graph.edges:
        neighbors[e['u']].append(e['v']); neighbors[e['v']].append(e['u'])
    seen, pending = {source}, deque([source])
    while pending:
        for v in neighbors[pending.popleft()]:
            if v not in seen: seen.add(v); pending.append(v)
    graph.nodes = {n: p for n, p in graph.nodes.items() if n in seen}
    graph.edges = [e for e in graph.edges if e['u'] in seen and e['v'] in seen]
    graph.by_id = {e['id']: e for e in graph.edges}
    graph.adj = {n: [] for n in graph.nodes}
    for e in graph.edges:
        graph.adj[e['u']].append((e['v'], e['id']))
        if not e['oneway']: graph.adj[e['v']].append((e['u'], e['id']))
    return graph


GRAPH, DEFAULT_START, DEFAULT_END, DISPLAY_BOUNDS = local_graph()


class Session:
    def __init__(self, source, target, seed=2306, interval=3, max_ticks=200, tick_seconds=.08):
        if source not in GRAPH.nodes or target not in GRAPH.nodes or source == target:
            raise ValueError('Choose two different road intersections.')
        route = GRAPH.dijkstra(source, target)
        if not route: raise ValueError('No directed route connects these intersections.')
        self.source, self.target = source, target
        self.seed, self.interval = seed, interval
        self.max_ticks, self.tick_seconds = max_ticks, tick_seconds
        self.lock = threading.Lock()
        self.notifications = queue.Queue()
        self.tick_ready = threading.Condition()
        self.request_tick = 0
        self.done_tick = 0
        self.rng = random.Random(seed)
        self.blocked = set()
        self.initial = route
        self.snapshot = {'tick': 0, 'done': False, 'blocked': [], 'events': [],
            'original': route, 'agents': {'dijkstra': {'node': source, 'route': route},
                                         'physarum': {'node': source, 'route': route}}}

    def chaos(self):
        """Concurrent producer; publishes a disaster proposal once per interval."""
        while True:
            with self.tick_ready:
                self.tick_ready.wait_for(lambda: self.request_tick > self.done_tick or self.request_tick < 0)
                tick = self.request_tick
                if tick < 0: return
                if tick % self.interval == 0:
                    with self.lock:
                        remaining = list(self.snapshot['agents']['dijkstra']['route'] or [])
                    candidates = []
                    for eid in remaining[1:]:
                        e = GRAPH.by_id[eid]
                        candidates.extend((e['u'], e['v']))
                    candidates = list(dict.fromkeys(n for n in candidates if n != self.target))
                    self.rng.shuffle(candidates)
                    self.notifications.put((tick, candidates, remaining[1:]))
                self.done_tick = tick
                self.tick_ready.notify_all()

    def run(self):
        producer = threading.Thread(target=self.chaos, daemon=True)
        producer.start()
        positions = {'dijkstra': self.source, 'physarum': self.source}
        plans = {'dijkstra': list(self.initial), 'physarum': list(self.initial)}
        stats = {name: {'compute_ms': 0., 'recalculations': 0, 'route_updates': 0,
                        'edge_travel_min': 0., 'completed_tick': None, 'penalties_ms': []}
                 for name in positions}
        events, conductivity, pressure = [], None, None
        start_wall = time.perf_counter()
        try:
            # The trained edge-message model seeds conductivity once; subsequent
            # ticks keep the same conductivity and prior pressure state.
            scores = predict(GRAPH, set(), self.initial, load())
            conductivity = {e['id']: .65 + 1.35 * scores[e['id']] for e in GRAPH.edges}
            for tick in range(1, self.max_ticks + 1):
                with self.tick_ready:
                    self.request_tick = tick
                    self.tick_ready.notify_all()
                    self.tick_ready.wait_for(lambda: self.done_tick == tick)
                new_event = None
                while not self.notifications.empty():
                    _, candidates, remaining = self.notifications.get_nowait()
                    # Choose a seeded random epicenter that leaves a bypass if
                    # possible; otherwise report that no viable event was found.
                    for node in candidates:
                        incident = {e['id'] for e in GRAPH.edges if node in (e['u'], e['v'])}
                        proposed = self.blocked | incident
                        if any(node == p for p in positions.values()): continue
                        if all(p == self.target or GRAPH.dijkstra(p, self.target, proposed)
                               for p in positions.values()):
                            with self.lock:
                                self.blocked = proposed
                                conductivity.update({i: .0001 for i in incident})
                            new_event = {'tick': tick, 'epicenter': node, 'closed': sorted(incident),
                                         'kind': 'simulated disruption'}
                            events.append(new_event)
                            break
                    if new_event is None:
                        # Sparse tile-derived junctions often have no bypass
                        # around an entirely destroyed intersection. In that
                        # case use a one-segment landslide at the epicenter.
                        options = list(remaining)
                        self.rng.shuffle(options)
                        for eid in options:
                            proposed = self.blocked | {eid}
                            if all(p == self.target or GRAPH.dijkstra(p, self.target, proposed)
                                   for p in positions.values()):
                                with self.lock:
                                    self.blocked = proposed
                                    conductivity[eid] = .0001
                                new_event = {'tick': tick, 'epicenter': GRAPH.by_id[eid]['u'],
                                             'closed': [eid], 'kind': 'simulated single-road landslide'}
                                events.append(new_event)
                                break
                # Both agents read the same frozen blocked-edge snapshot for this tick.
                with self.lock: blocked = frozenset(self.blocked)
                if new_event and any(eid in blocked for eid in plans['dijkstra']):
                    t = time.perf_counter_ns()
                    plans['dijkstra'] = GRAPH.dijkstra(positions['dijkstra'], self.target, blocked)
                    ms = (time.perf_counter_ns()-t)/1e6
                    stats['dijkstra']['compute_ms'] += ms
                    stats['dijkstra']['recalculations'] += 1
                    stats['dijkstra']['penalties_ms'].append(round(ms, 4))
                if positions['physarum'] != self.target:
                    t = time.perf_counter_ns()
                    path, conductivity, pressure = adapt(GRAPH, positions['physarum'],
                        self.target, blocked, conductivity, rounds=1, prior_pressure=pressure)
                    stats['physarum']['compute_ms'] += (time.perf_counter_ns()-t)/1e6
                    plans['physarum'] = path
                    stats['physarum']['route_updates'] += 1
                for name in positions:
                    if positions[name] == self.target or not plans[name]: continue
                    eid = plans[name][0]
                    if eid in blocked: continue
                    e = GRAPH.by_id[eid]
                    here = positions[name]
                    nxt = e['v'] if e['u'] == here else e['u'] if not e['oneway'] and e['v'] == here else None
                    if nxt is None: continue
                    positions[name] = nxt
                    plans[name] = plans[name][1:]
                    stats[name]['edge_travel_min'] += GRAPH.minutes(eid)
                    if nxt == self.target: stats[name]['completed_tick'] = tick
                with self.lock:
                    self.snapshot = {'tick': tick, 'done': False, 'blocked': sorted(blocked),
                        'events': copy.deepcopy(events), 'original': self.initial,
                        'latest_event': new_event,
                        'agents': {name: {'node': positions[name], 'route': plans[name],
                            'arrived': positions[name] == self.target,
                            'metrics': {**stats[name], 'compute_ms': round(stats[name]['compute_ms'], 3),
                                'edge_travel_min': round(stats[name]['edge_travel_min'], 3)}} for name in positions},
                        'elapsed_wall_s': round(time.perf_counter()-start_wall, 3)}
                if all(p == self.target for p in positions.values()): break
                time.sleep(self.tick_seconds)
        finally:
            with self.tick_ready:
                self.request_tick = -1
                self.tick_ready.notify_all()
            with self.lock:
                self.snapshot['done'] = True
                self.snapshot['elapsed_wall_s'] = round(time.perf_counter()-start_wall, 3)

    def get(self):
        with self.lock: return copy.deepcopy(self.snapshot)

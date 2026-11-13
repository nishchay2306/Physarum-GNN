"""Seeded fleet comparison on an OSM-derived connected road extract."""
import copy
import math
import queue
import random
import statistics
import threading
import time

from .dynamic import GRAPH, DEFAULT_START, DEFAULT_END
from .model import load, predict

try:
    import numpy as np
except ImportError:
    np = None


def nearby(anchor, avoid, destination):
    x, y = GRAPH.nodes[anchor]
    choices = sorted(GRAPH.nodes, key=lambda n: (GRAPH.nodes[n][0]-x)**2+(GRAPH.nodes[n][1]-y)**2)
    result = next((n for n in choices if n != anchor and n != avoid
                   and GRAPH.dijkstra(n, destination)), None)
    if result is None:
        raise ValueError('No reachable second depot near the selected start node.')
    return result


DEPOTS = (DEFAULT_START, nearby(DEFAULT_START, DEFAULT_END, DEFAULT_END))
ZONES = (DEFAULT_END, nearby(DEFAULT_END, DEFAULT_START, DEFAULT_END))
MAX_PAIRS = 10


def default_pairs(limit=MAX_PAIRS):
    """Deterministic, reachable, well-spread start/end pairs for the page's defaults.

    Pair 1 is the original default route; the rest are seeded picks of moderate
    length whose endpoints keep clear of every endpoint already chosen, so the
    map pins do not pile on top of each other.
    """
    pairs = [(DEFAULT_START, DEFAULT_END)]
    rng = random.Random(7)
    ids = sorted(GRAPH.nodes)
    used = [DEFAULT_START, DEFAULT_END]

    def clear(n, extra=()):
        x, y = GRAPH.nodes[n]
        return all(math.hypot((x-GRAPH.nodes[u][0])*.9, y-GRAPH.nodes[u][1]) > .002
                   for u in used + list(extra))

    for _ in range(6000):
        if len(pairs) >= limit: break
        a, b = rng.choice(ids), rng.choice(ids)
        if a == b or not clear(a) or not clear(b, (a,)): continue
        route = GRAPH.dijkstra(a, b)
        if route and 10 <= len(route) <= 40:
            pairs.append((a, b)); used += [a, b]
    return pairs[:limit]


def bpr_multiplier(flow, capacity):
    """Same simulated traffic time multiplier for both routing policies."""
    return 1 + .30 * (flow / capacity) ** 4


class Fleet:
    def __init__(self, count=50, start=DEFAULT_START, target=DEFAULT_END,
                 seed=2306, tick_seconds=.02, max_ticks=None, pairs=None):
        if not 1 <= count <= 2500: raise ValueError('Fleet size must be between 1 and 2500.')
        if pairs is None:
            # Legacy mode: one selected start/end; a second depot and zone are
            # derived nearby and vehicles cycle through all four combinations.
            if start not in GRAPH.nodes or target not in GRAPH.nodes or start == target:
                raise ValueError('Select different connected road intersections for start and destination.')
            if not GRAPH.dijkstra(start, target):
                raise ValueError('No directed route connects the selected intersections.')
            second_start = nearby(start, target, target)
            x,y = GRAPH.nodes[target]
            choices = sorted(GRAPH.nodes, key=lambda n:(GRAPH.nodes[n][0]-x)**2+(GRAPH.nodes[n][1]-y)**2)
            second_target = next((n for n in choices if n not in (target,start,second_start)
                                  and GRAPH.dijkstra(start,n) and GRAPH.dijkstra(second_start,n)), None)
            if second_target is None: raise ValueError('No second reachable destination near the selected point.')
            self.depots, self.zones = (start,second_start),(target,second_target)
            self.pairs = [(self.depots[0],self.zones[0]),(self.depots[1],self.zones[0]),
                          (self.depots[0],self.zones[1]),(self.depots[1],self.zones[1])]
        else:
            # Explicit mode: N independent start/end paths chosen by the user.
            try: pairs = [(str(a), str(b)) for a, b in pairs]
            except (TypeError, ValueError):
                raise ValueError('Each path needs one start and one end intersection.')
            if not 1 <= len(pairs) <= MAX_PAIRS:
                raise ValueError(f'Choose between 1 and {MAX_PAIRS} start/end paths.')
            if count < len(pairs):
                raise ValueError(f'Fleet size ({count}) must be at least the number of paths ({len(pairs)}).')
            for n, (a, b) in enumerate(pairs, 1):
                if a not in GRAPH.nodes or b not in GRAPH.nodes or a == b:
                    raise ValueError(f'Path {n}: select two different road intersections.')
                if not GRAPH.dijkstra(a, b):
                    raise ValueError(f'Path {n}: no directed route connects the selected intersections.')
            self.pairs = pairs
            self.depots = tuple(a for a, _ in pairs)
            self.zones = tuple(b for _, b in pairs)
        self.count, self.seed = count, seed
        # Allow large fleets time to clear capacity-limited roads. An explicit
        # max_ticks argument still overrides the default for tests and demos.
        self.tick_seconds = tick_seconds
        self.max_ticks = max_ticks if max_ticks is not None else max(1000, math.ceil(count*1.3))
        self.lock, self.condition = threading.Lock(), threading.Condition()
        self.proposals = queue.Queue()
        self.request_tick = self.done_tick = 0
        self.rng = random.Random(seed)
        self.closed_until = {}
        self.initial = []
        self.trucks = {}
        initial_routes = {pair: GRAPH.dijkstra(*pair) for pair in self.pairs}
        for method in ('dijkstra', 'physarum'):
            team = []
            for i in range(count):
                pair_index = i % len(self.pairs)
                source, target = self.pairs[pair_index]
                route = initial_routes[(source, target)]
                if not route: raise ValueError('The bundled road extract cannot connect fleet depots and zones.')
                if method == 'dijkstra': self.initial.append(route)
                team.append({'node': source, 'target': target, 'pair': pair_index, 'plan': route,
                             'edge': None, 'remaining': 0, 'wait': 0, 'arrived': False,
                             'arrival_tick': None,
                             'traversed': []})
            self.trucks[method] = team
        # Incident locations are fixed before either policy starts moving;
        # event generation never examines one method's active route.
        self.hazard_pool = sorted({eid for path in self.initial for eid in path[2:22]})
        # One-time GNN inference; subsequent ticks reuse the scores.
        scores = predict(GRAPH, set(), self.initial[0], load())
        self.edge_ids = [e['id'] for e in GRAPH.edges]
        self.edge_idx = {eid: i for i, eid in enumerate(self.edge_ids)}
        self.seeds = [max(.05, .65 + 1.35*scores[eid]) for eid in self.edge_ids]
        self.capacity = {e['id']: 8 if e['highway'] in ('primary','trunk') else 4
                         for e in GRAPH.edges}
        self.snapshot = {'tick':0,'done':False,'events':[],'blocked':[],
                         'fleets':{},'density':{},'depot_nodes':self.depots,'zone_nodes':self.zones,
                         'pairs':[list(p) for p in self.pairs],
                         'numpy_acceleration':np is not None}

    def disasters(self):
        rng = random.Random(self.seed + 101)
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.request_tick > self.done_tick or self.request_tick < 0)
                tick = self.request_tick
                if tick < 0: return
                # Independent seeded micro-disruptions from the pre-event road
                # corridor. Neither policy's live routes influence locations.
                if tick >= 3 and rng.random() < .08:
                    candidates = list(self.hazard_pool)
                    rng.shuffle(candidates)
                    self.proposals.put((tick, candidates))
                self.done_tick = tick
                self.condition.notify_all()

    def get(self):
        with self.lock: return copy.deepcopy(self.snapshot)

    def run(self):
        producer = threading.Thread(target=self.disasters, daemon=True)
        producer.start()
        stats = {m:{'compute_ms':0.,'recalculations':0,'route_updates':0,
                     'congestion_wait_ticks':0,'travel_min':0.,
                     'congestion_extra_min':0.,'delivered':0,
                     'completed_tick':None,'penalties_ms':[]} for m in self.trucks}
        used_edges = {m:set() for m in self.trucks}
        arrival_ticks = {m:[] for m in self.trucks}
        arrival_series = {m:[[0, 0]] for m in self.trucks}
        npairs = len(self.pairs)
        pair_total = [sum(1 for i in range(self.count) if i % npairs == k) for k in range(npairs)]
        pstats = {m:[{'delivered':0,'wait':0,'extra':0.,'travel':0.,'completed':None,
                      'arrivals':[],'series':[[0,0]]} for _ in range(npairs)] for m in self.trucks}
        cond = list(self.seeds)
        events, wall_start = [], time.perf_counter()
        try:
            for tick in range(1,self.max_ticks+1):
                with self.condition:
                    self.request_tick=tick
                    self.condition.notify_all()
                    self.condition.wait_for(lambda:self.done_tick==tick)
                self.closed_until={eid:end for eid,end in self.closed_until.items() if end>tick}
                proposed=[]
                while not self.proposals.empty():
                    _,proposed=self.proposals.get_nowait()
                for eid in proposed:
                    if eid in self.closed_until: continue
                    candidate=set(self.closed_until)|{eid}
                    # Keep at least one route for each selected start/end path.
                    if all(GRAPH.dijkstra(s,t,candidate) for s,t in self.pairs):
                        self.closed_until[eid]=tick+8
                        events.append({'tick':tick,'edge':eid,'until':tick+8,
                                       'kind':'simulated micro-disruption'})
                        break
                blocked=frozenset(self.closed_until)
                occupancy={m:{eid:0 for eid in self.edge_ids} for m in self.trucks}
                route_cache = {}
                for method,team in self.trucks.items():
                    for truck in team:
                        if truck['edge'] is not None: occupancy[method][truck['edge']]+=1
                # Persistent conductivity reflects congestion: NumPy processes
                # all roads together when installed; Python follows same formula.
                loads=occupancy['physarum']
                if np is not None:
                    vec=np.asarray(cond); flow=np.asarray([loads[i]/self.capacity[i] for i in self.edge_ids])
                    cond=np.clip(.90*vec+.10*np.asarray(self.seeds)/(1+flow**2),.05,3.).tolist()
                else:
                    cond=[max(.05,min(3.,.90*cond[i]+.10*self.seeds[i]/
                           (1+(loads[eid]/self.capacity[eid])**2)))
                          for i,eid in enumerate(self.edge_ids)]
                for method,team in self.trucks.items():
                    for truck in team:
                        if truck['arrived']:continue
                        if truck['edge'] is not None:
                            truck['remaining']-=1
                            if truck['remaining']>0:continue
                            edge=GRAPH.by_id[truck['edge']]
                            truck['traversed'].append(truck['edge'])
                            truck['node']=edge['v'] if truck['node']==edge['u'] else edge['u']
                            occupancy[method][truck['edge']]-=1
                            truck['edge']=None
                            if truck['node']==truck['target']:
                                truck['arrived']=True;stats[method]['delivered']+=1
                                truck['arrival_tick']=tick
                                arrival_ticks[method].append(tick)
                                ps=pstats[method][truck['pair']]
                                ps['delivered']+=1;ps['arrivals'].append(tick)
                                if ps['delivered']==pair_total[truck['pair']]:ps['completed']=tick
                                if stats[method]['delivered']==self.count:stats[method]['completed_tick']=tick
                                continue
                        if method=='dijkstra':
                            if not truck['plan'] or any(eid in blocked for eid in truck['plan']):
                                t=time.perf_counter_ns()
                                truck['plan']=GRAPH.dijkstra(truck['node'],truck['target'],blocked)
                                ms=(time.perf_counter_ns()-t)/1e6
                                stats[method]['compute_ms']+=ms
                                stats[method]['recalculations']+=1
                                stats[method]['penalties_ms'].append(round(ms,4))
                        else:
                            t=time.perf_counter_ns()
                            # One-hop GNN seed + persistent capacity-aware C_ij.
                            # Route extraction still uses a shortest-path search.
                            # Reuse the same route for trucks at the same
                            # intersection while its outgoing load is unchanged.
                            # A departure changes that load, prompting a new
                            # capacity-aware route on the next decision.
                            nearby_load=tuple(occupancy[method][e] for _,e in GRAPH.adj[truck['node']])
                            cache_key=(truck['node'],truck['target'],nearby_load)
                            if cache_key not in route_cache:
                                costs={eid: GRAPH.minutes(eid)/(.25+.75*cond[self.edge_idx[eid]])*
                                       (1+.55*(occupancy[method][eid]/self.capacity[eid])**4)
                                       for eid in self.edge_ids}
                                route_cache[cache_key]=GRAPH.dijkstra(truck['node'],truck['target'],blocked,costs)
                                stats[method]['compute_ms']+=(time.perf_counter_ns()-t)/1e6
                                stats[method]['route_updates']+=1
                            truck['plan']=route_cache[cache_key]
                        if not truck['plan']:continue
                        eid=truck['plan'][0]
                        if eid in blocked:continue
                        edge=GRAPH.by_id[eid]
                        if truck['node'] not in (edge['u'],edge['v']):continue
                        # Same BPR alpha/beta for both fleets. Over-capacity
                        # flow increases time sharply; extra trucks wait at the
                        # intersection once occupancy reaches 2x capacity.
                        if occupancy[method][eid] >= 2*self.capacity[eid]:
                            truck['wait']+=1
                            stats[method]['congestion_wait_ticks']+=1
                            pstats[method][truck['pair']]['wait']+=1
                            continue
                        occupancy[method][eid]+=1
                        free=GRAPH.minutes(eid)
                        delay=bpr_multiplier(occupancy[method][eid], self.capacity[eid])
                        truck['remaining']=max(1,math.ceil(delay))
                        truck['edge']=eid
                        used_edges[method].add(eid)
                        truck['plan']=truck['plan'][1:]
                        stats[method]['travel_min']+=free*delay
                        stats[method]['congestion_extra_min']+=free*(delay-1)
                        stats[method]['congestion_wait_ticks']+=truck['remaining']-1
                        ps=pstats[method][truck['pair']]
                        ps['travel']+=free*delay;ps['extra']+=free*(delay-1)
                        ps['wait']+=truck['remaining']-1
                for method in self.trucks:
                    arrival_series[method].append([tick, stats[method]['delivered']])
                    for ps in pstats[method]:
                        ps['series'].append([tick, ps['delivered']])
                with self.lock:
                    self.snapshot={'tick':tick,'done':False,'events':events[:],
                        'blocked':sorted(blocked),'depot_nodes':self.depots,'zone_nodes':self.zones,
                        'pairs':[list(p) for p in self.pairs],
                        'numpy_acceleration':np is not None,
                        'density':{m:{str(i):n for i,n in loads.items() if n>0} for m,loads in occupancy.items()},
                        'fleets':{m:{'trucks':[{'node':t['node'],'edge':t['edge'],
                            'remaining':t['remaining'],'target':t['target'],'pair':t['pair'],
                            'arrival_tick':t['arrival_tick'],
                            'traversed':t['traversed'], 'route':(t['plan'] or [])[:18]}
                            for t in team], 'arrival_series':arrival_series[m][:],
                            'pairs':[{'index':k,'start':self.pairs[k][0],'target':self.pairs[k][1],
                                'vehicles':pair_total[k],'delivered':ps['delivered'],
                                'completed_tick':ps['completed'],
                                'median_arrival_tick':statistics.median(ps['arrivals']) if ps['arrivals'] and ps['delivered']==pair_total[k] else None,
                                'congestion_wait_ticks':ps['wait'],
                                'congestion_extra_min':round(ps['extra'],3),
                                'travel_min':round(ps['travel'],3),
                                'arrival_series':ps['series'][:]}
                                for k,ps in enumerate(pstats[m])],
                            'metrics':{**stats[m],
                                'unique_roads_used':len(used_edges[m]),
                                'compute_ms':round(stats[m]['compute_ms'],3),
                                'median_arrival_tick':statistics.median(arrival_ticks[m]) if len(arrival_ticks[m]) == self.count else None,
                                'congestion_extra_min':round(stats[m]['congestion_extra_min'],3),
                                'travel_min':round(stats[m]['travel_min'],3)}}
                            for m,team in self.trucks.items()},
                        'elapsed_wall_s':round(time.perf_counter()-wall_start,3)}
                if all(s['delivered']==self.count for s in stats.values()):break
                time.sleep(self.tick_seconds)
        finally:
            with self.condition:
                self.request_tick=-1;self.condition.notify_all()
            with self.lock:
                self.snapshot['done']=True
                self.snapshot['elapsed_wall_s']=round(time.perf_counter()-wall_start,3)

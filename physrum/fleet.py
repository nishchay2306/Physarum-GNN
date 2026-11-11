"""Seeded fleet comparison on an OSM-derived connected road extract."""
import copy
import math
import queue
import random
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


class Fleet:
    def __init__(self, count=50, start=DEFAULT_START, target=DEFAULT_END,
                 seed=2306, tick_seconds=.02, max_ticks=1000):
        if not 1 <= count <= 120: raise ValueError('Fleet size must be between 1 and 120.')
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
        self.count, self.seed = count, seed
        self.tick_seconds, self.max_ticks = tick_seconds, max_ticks
        self.lock, self.condition = threading.Lock(), threading.Condition()
        self.proposals = queue.Queue()
        self.request_tick = self.done_tick = 0
        self.rng = random.Random(seed)
        self.closed_until = {}
        self.initial = []
        self.trucks = {}
        for method in ('dijkstra', 'physarum'):
            team = []
            for i in range(count):
                source, target = self.depots[i % 2], self.zones[(i // 2) % 2]
                route = GRAPH.dijkstra(source, target)
                if not route: raise ValueError('The bundled road extract cannot connect fleet depots and zones.')
                if method == 'dijkstra': self.initial.append(route)
                team.append({'node': source, 'target': target, 'plan': route,
                             'edge': None, 'remaining': 0, 'wait': 0, 'arrived': False,
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
                     'congestion_wait_ticks':0,'travel_min':0.,'delivered':0,
                     'completed_tick':None,'penalties_ms':[]} for m in self.trucks}
        used_edges = {m:set() for m in self.trucks}
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
                    # Keep at least one route for each depot-zone pair.
                    if all(GRAPH.dijkstra(s,t,candidate) for s in self.depots for t in self.zones):
                        self.closed_until[eid]=tick+8
                        events.append({'tick':tick,'edge':eid,'until':tick+8,
                                       'kind':'simulated micro-disruption'})
                        break
                blocked=frozenset(self.closed_until)
                occupancy={m:{eid:0 for eid in self.edge_ids} for m in self.trucks}
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
                            costs={eid: GRAPH.minutes(eid)/(.25+.75*cond[self.edge_idx[eid]])*
                                   (1+.55*(occupancy[method][eid]/self.capacity[eid])**4)
                                   for eid in self.edge_ids}
                            truck['plan']=GRAPH.dijkstra(truck['node'],truck['target'],blocked,costs)
                            stats[method]['compute_ms']+=(time.perf_counter_ns()-t)/1e6
                            stats[method]['route_updates']+=1
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
                            continue
                        occupancy[method][eid]+=1
                        ratio=occupancy[method][eid]/self.capacity[eid]
                        free=GRAPH.minutes(eid)
                        delay=1+.15*ratio**4
                        truck['remaining']=max(1,math.ceil(delay))
                        truck['edge']=eid
                        used_edges[method].add(eid)
                        truck['plan']=truck['plan'][1:]
                        stats[method]['travel_min']+=free*delay
                        stats[method]['congestion_wait_ticks']+=truck['remaining']-1
                with self.lock:
                    self.snapshot={'tick':tick,'done':False,'events':events[:],
                        'blocked':sorted(blocked),'depot_nodes':self.depots,'zone_nodes':self.zones,
                        'numpy_acceleration':np is not None,
                        'density':{m:{str(i):n for i,n in loads.items() if n>0} for m,loads in occupancy.items()},
                        'fleets':{m:{'trucks':[{'node':t['node'],'edge':t['edge'],
                            'remaining':t['remaining'],'target':t['target'],
                            'traversed':t['traversed'], 'route':(t['plan'] or [])[:18]}
                            for t in team], 'metrics':{**stats[m],
                                'unique_roads_used':len(used_edges[m]),
                                'compute_ms':round(stats[m]['compute_ms'],3),
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

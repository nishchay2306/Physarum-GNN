"use strict";

class PythonRandom {
  constructor(seed) {
    this.values = new Uint32Array(624);
    this.values[0] = 19650218;
    for (let i = 1; i < 624; i++) {
      const previous = this.values[i - 1];
      this.values[i] = (Math.imul(1812433253, previous ^ (previous >>> 30)) + i) >>> 0;
    }

    let i = 1;
    let j = 0;
    for (let count = 624; count > 0; count--) {
      const previous = this.values[i - 1];
      this.values[i] = ((this.values[i] ^ Math.imul(previous ^ (previous >>> 30), 1664525)) + seed + j) >>> 0;
      i++;
      j++;
      if (i >= 624) {
        this.values[0] = this.values[623];
        i = 1;
      }
      if (j >= 1) j = 0;
    }
    for (let count = 623; count > 0; count--) {
      const previous = this.values[i - 1];
      this.values[i] = ((this.values[i] ^ Math.imul(previous ^ (previous >>> 30), 1566083941)) - i) >>> 0;
      i++;
      if (i >= 624) {
        this.values[0] = this.values[623];
        i = 1;
      }
    }
    this.values[0] = 0x80000000;
    this.index = 624;
  }

  nextUint32() {
    if (this.index >= 624) {
      for (let i = 0; i < 624; i++) {
        const mixed = (this.values[i] & 0x80000000) | (this.values[(i + 1) % 624] & 0x7fffffff);
        let value = this.values[(i + 397) % 624] ^ (mixed >>> 1);
        if (mixed & 1) value ^= 0x9908b0df;
        this.values[i] = value >>> 0;
      }
      this.index = 0;
    }
    let value = this.values[this.index++];
    value ^= value >>> 11;
    value ^= (value << 7) & 0x9d2c5680;
    value ^= (value << 15) & 0xefc60000;
    value ^= value >>> 18;
    return value >>> 0;
  }

  random() {
    const high = this.nextUint32() >>> 5;
    const low = this.nextUint32() >>> 6;
    return (high * 67108864 + low) / 9007199254740992;
  }

  below(n) {
    const bits = Math.floor(Math.log2(n)) + 1;
    let value;
    do {
      value = this.nextUint32() >>> (32 - bits);
    } while (value >= n);
    return value;
  }

  shuffle(values) {
    for (let i = values.length - 1; i > 0; i--) {
      const j = this.below(i + 1);
      [values[i], values[j]] = [values[j], values[i]];
    }
  }
}

class MinHeap {
  constructor() {
    this.items = [];
  }

  push(item) {
    const items = this.items;
    let index = items.length;
    items.push(item);
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (compareHeapItems(items[parent], item) <= 0) break;
      items[index] = items[parent];
      index = parent;
    }
    items[index] = item;
  }

  pop() {
    const items = this.items;
    const first = items[0];
    const last = items.pop();
    if (items.length) {
      let index = 0;
      while (index * 2 + 1 < items.length) {
        let child = index * 2 + 1;
        if (child + 1 < items.length && compareHeapItems(items[child + 1], items[child]) < 0) child++;
        if (compareHeapItems(last, items[child]) <= 0) break;
        items[index] = items[child];
        index = child;
      }
      items[index] = last;
    }
    return first;
  }

  get length() {
    return this.items.length;
  }
}

function compareHeapItems(left, right) {
  return left[0] - right[0] || (left[1] < right[1] ? -1 : left[1] > right[1] ? 1 : 0);
}

class RoadGraph {
  constructor(data) {
    this.nodes = data.nodes;
    this.edges = data.edges.filter(edge => edge.u in data.nodes && edge.v in data.nodes);
    this.byId = new Map(this.edges.map(edge => [edge.id, edge]));
    this.adj = new Map(Object.keys(this.nodes).map(node => [node, []]));
    this.minutesById = new Map();
    for (const edge of this.edges) {
      this.adj.get(edge.u).push([edge.v, edge.id]);
      if (!edge.oneway) this.adj.get(edge.v).push([edge.u, edge.id]);
      this.minutesById.set(edge.id, edge.meters / (edge.speed_kmh * 1000 / 60));
    }
  }

  dijkstra(source, target, blocked = new Set(), weights = null) {
    const heap = new MinHeap();
    heap.push([0, source]);
    const best = new Map([[source, 0]]);
    const previous = new Map();
    while (heap.length) {
      const [cost, node] = heap.pop();
      if (cost > best.get(node) + 1e-9) continue;
      if (node === target) break;
      for (const [next, edgeId] of this.adj.get(node)) {
        if (blocked.has(edgeId)) continue;
        const step = weights ? weights.get(edgeId) : this.minutesById.get(edgeId);
        const nextCost = cost + step;
        if (nextCost + 1e-10 < (best.get(next) ?? Infinity)) {
          best.set(next, nextCost);
          previous.set(next, [node, edgeId]);
          heap.push([nextCost, next]);
        }
      }
    }
    if (!best.has(target)) return null;
    const route = [];
    for (let node = target; node !== source;) {
      const [previousNode, edgeId] = previous.get(node);
      route.push(edgeId);
      node = previousNode;
    }
    return route.reverse();
  }
}

function nearby(graph, anchor, avoid, destination) {
  const [x, y] = graph.nodes[anchor];
  const choices = Object.keys(graph.nodes).sort((left, right) => {
    const a = graph.nodes[left];
    const b = graph.nodes[right];
    return ((a[0] - x) ** 2 + (a[1] - y) ** 2) - ((b[0] - x) ** 2 + (b[1] - y) ** 2);
  });
  const result = choices.find(node => node !== anchor && node !== avoid && graph.dijkstra(node, destination)?.length);
  if (!result) throw new Error("No reachable second depot near the selected start node.");
  return result;
}

function modelScores(graph, original, model) {
  const originalEdges = new Set(original);
  const incident = new Map(Object.keys(graph.nodes).map(node => [node, []]));
  const features = new Map();
  const hills = [[91.775, 26.115], [91.91, 26.095], [91.74, 26.12]];
  for (const edge of graph.edges) {
    const [x1, y1] = graph.nodes[edge.u];
    const [x2, y2] = graph.nodes[edge.v];
    const x = (x1 + x2) / 2;
    const y = (y1 + y2) / 2;
    const hill = Math.max(...hills.map(([hx, hy]) => Math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (.025 ** 2))));
    const flood = Math.exp(-(((y - .19) / .03) ** 2)) * Math.min(1, Math.max(0, (x - 91.7) / .2));
    const proximity = Math.exp(-(((x * .9) ** 2 + y ** 2) / (.006 ** 2)));
    features.set(edge.id, [Math.min(1, edge.meters / 200), edge.speed_kmh / 65,
      Number(edge.oneway), Number(edge.bridge), hill, flood, proximity,
      Number(originalEdges.has(edge.id)), 0]);
    incident.get(edge.u).push(edge.id);
    incident.get(edge.v).push(edge.id);
  }
  const scores = new Map();
  for (const edge of graph.edges) {
    const neighbors = new Set([...incident.get(edge.u), ...incident.get(edge.v)]);
    neighbors.delete(edge.id);
    const context = [1, 6, 7].map(index => neighbors.size
      ? [...neighbors].reduce((sum, id) => sum + features.get(id)[index], 0) / neighbors.size
      : 0);
    const input = [...features.get(edge.id), ...context];
    const hidden = model.w1.map((row, index) => Math.tanh(row.reduce((sum, weight, column) => sum + weight * input[column], model.b1[index])));
    const output = model.w2.reduce((sum, weight, index) => sum + weight * hidden[index], model.b2);
    scores.set(edge.id, 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, output)))));
  }
  return scores;
}

class Fleet {
  constructor(data, options = {}) {
    const { count = 50, start = data.default_start, target = data.default_end, seed = 2306, maxTicks = 1000 } = options;
    if (!Number.isInteger(count) || count < 1 || count > 1000) throw new Error("Fleet size must be between 1 and 1000.");
    this.graph = new RoadGraph(data);
    const graph = this.graph;
    if (!(start in graph.nodes) || !(target in graph.nodes) || start === target) {
      throw new Error("Select different connected road intersections for start and destination.");
    }
    if (!graph.dijkstra(start, target)?.length) throw new Error("No directed route connects the selected intersections.");
    const secondStart = nearby(graph, start, target, target);
    const [x, y] = graph.nodes[target];
    const choices = Object.keys(graph.nodes).sort((left, right) => {
      const a = graph.nodes[left];
      const b = graph.nodes[right];
      return ((a[0] - x) ** 2 + (a[1] - y) ** 2) - ((b[0] - x) ** 2 + (b[1] - y) ** 2);
    });
    const secondTarget = choices.find(node => ![target, start, secondStart].includes(node)
      && graph.dijkstra(start, node)?.length && graph.dijkstra(secondStart, node)?.length);
    if (!secondTarget) throw new Error("No second reachable destination near the selected point.");

    this.depots = [start, secondStart];
    this.zones = [target, secondTarget];
    this.count = count;
    this.maxTicks = maxTicks;
    this.tick = 0;
    this.startedAt = performance.now();
    this.random = new PythonRandom(seed + 101);
    this.closedUntil = new Map();
    this.events = [];
    this.done = false;
    this.edgeIds = graph.edges.map(edge => edge.id);
    this.initial = [];
    this.trucks = { dijkstra: [], physarum: [] };
    const initialRoutes = new Map();
    for (const depot of this.depots) {
      for (const zone of this.zones) initialRoutes.set(`${depot}|${zone}`, graph.dijkstra(depot, zone));
    }
    for (const method of ["dijkstra", "physarum"]) {
      for (let i = 0; i < count; i++) {
        const depot = this.depots[i % 2];
        const zone = this.zones[Math.floor(i / 2) % 2];
        const route = initialRoutes.get(`${depot}|${zone}`);
        if (!route?.length) throw new Error("The bundled road extract cannot connect fleet depots and zones.");
        if (method === "dijkstra") this.initial.push(route);
        this.trucks[method].push({ node: depot, target: zone, plan: route,
          edge: null, remaining: 0, wait: 0, arrived: false, arrival_tick: null, traversed: [] });
      }
    }
    this.hazardPool = [...new Set(this.initial.flatMap(path => path.slice(2, 22)))].sort((a, b) => a - b);
    const scores = modelScores(graph, this.initial[0], data.model);
    this.seeds = new Map(this.edgeIds.map(id => [id, Math.max(.05, .65 + 1.35 * scores.get(id))]));
    this.conductivity = new Map(this.seeds);
    this.capacity = new Map(graph.edges.map(edge => [edge.id, ["primary", "trunk"].includes(edge.highway) ? 8 : 4]));
    this.stats = Object.fromEntries(["dijkstra", "physarum"].map(method => [method, {
      compute_ms: 0, recalculations: 0, route_updates: 0, congestion_wait_ticks: 0,
      travel_min: 0, congestion_extra_min: 0, delivered: 0, completed_tick: null, penalties_ms: []
    }]));
    this.usedEdges = { dijkstra: new Set(), physarum: new Set() };
    this.arrivalTicks = { dijkstra: [], physarum: [] };
    this.arrivalSeries = { dijkstra: [[0, 0]], physarum: [[0, 0]] };
    this.occupancy = { dijkstra: new Map(), physarum: new Map() };
    this.blocked = new Set();
  }

  advance() {
    if (this.done) return;
    const graph = this.graph;
    const tick = ++this.tick;
    for (const [id, until] of this.closedUntil) if (until <= tick) this.closedUntil.delete(id);
    let proposed = [];
    if (tick >= 3 && this.random.random() < .08) {
      proposed = [...this.hazardPool];
      this.random.shuffle(proposed);
    }
    for (const id of proposed) {
      if (this.closedUntil.has(id)) continue;
      const candidate = new Set([...this.closedUntil.keys(), id]);
      if (this.depots.every(depot => this.zones.every(zone => graph.dijkstra(depot, zone, candidate)?.length))) {
        this.closedUntil.set(id, tick + 8);
        this.events.push({ tick, edge: id, until: tick + 8, kind: "simulated micro-disruption" });
        break;
      }
    }
    this.blocked = new Set(this.closedUntil.keys());
    const occupancy = Object.fromEntries(["dijkstra", "physarum"].map(method => [method,
      new Map(this.edgeIds.map(id => [id, 0]))]));
    for (const method of ["dijkstra", "physarum"]) {
      for (const truck of this.trucks[method]) {
        if (truck.edge !== null) occupancy[method].set(truck.edge, occupancy[method].get(truck.edge) + 1);
      }
    }
    const loads = occupancy.physarum;
    for (const id of this.edgeIds) {
      const ratio = loads.get(id) / this.capacity.get(id);
      const next = .90 * this.conductivity.get(id) + .10 * this.seeds.get(id) / (1 + ratio ** 2);
      this.conductivity.set(id, Math.max(.05, Math.min(3, next)));
    }

    const routeCache = new Map();
    for (const method of ["dijkstra", "physarum"]) {
      const stats = this.stats[method];
      for (const truck of this.trucks[method]) {
        if (truck.arrived) continue;
        if (truck.edge !== null) {
          truck.remaining--;
          if (truck.remaining > 0) continue;
          const edge = graph.byId.get(truck.edge);
          truck.traversed.push(truck.edge);
          truck.node = truck.node === edge.u ? edge.v : edge.u;
          occupancy[method].set(truck.edge, occupancy[method].get(truck.edge) - 1);
          truck.edge = null;
          if (truck.node === truck.target) {
            truck.arrived = true;
            stats.delivered++;
            truck.arrival_tick = tick;
            this.arrivalTicks[method].push(tick);
            if (stats.delivered === this.count) stats.completed_tick = tick;
            continue;
          }
        }
        if (method === "dijkstra") {
          if (!truck.plan || truck.plan.some(id => this.blocked.has(id))) {
            const started = performance.now();
            truck.plan = graph.dijkstra(truck.node, truck.target, this.blocked);
            const elapsed = performance.now() - started;
            stats.compute_ms += elapsed;
            stats.recalculations++;
            stats.penalties_ms.push(Math.round(elapsed * 10000) / 10000);
          }
        } else {
          const nearbyLoad = graph.adj.get(truck.node).map(([, id]) => occupancy[method].get(id));
          const cacheKey = `${truck.node}|${truck.target}|${nearbyLoad.join(",")}`;
          if (!routeCache.has(cacheKey)) {
            const started = performance.now();
            const costs = new Map(this.edgeIds.map(id => [id,
              graph.minutesById.get(id) / (.25 + .75 * this.conductivity.get(id))
              * (1 + .55 * (occupancy[method].get(id) / this.capacity.get(id)) ** 4)]));
            routeCache.set(cacheKey, graph.dijkstra(truck.node, truck.target, this.blocked, costs));
            stats.compute_ms += performance.now() - started;
            stats.route_updates++;
          }
          truck.plan = routeCache.get(cacheKey);
        }
        if (!truck.plan?.length) continue;
        const id = truck.plan[0];
        if (this.blocked.has(id)) continue;
        const edge = graph.byId.get(id);
        if (truck.node !== edge.u && truck.node !== edge.v) continue;
        if (occupancy[method].get(id) >= 2 * this.capacity.get(id)) {
          truck.wait++;
          stats.congestion_wait_ticks++;
          continue;
        }
        const flow = occupancy[method].get(id) + 1;
        occupancy[method].set(id, flow);
        const free = graph.minutesById.get(id);
        const delay = 1 + .30 * (flow / this.capacity.get(id)) ** 4;
        truck.remaining = Math.max(1, Math.ceil(delay));
        truck.edge = id;
        this.usedEdges[method].add(id);
        truck.plan = truck.plan.slice(1);
        stats.travel_min += free * delay;
        stats.congestion_extra_min += free * (delay - 1);
        stats.congestion_wait_ticks += truck.remaining - 1;
      }
      this.arrivalSeries[method].push([tick, stats.delivered]);
    }
    this.occupancy = occupancy;
    this.done = tick >= this.maxTicks || Object.values(this.stats).every(stats => stats.delivered === this.count);
  }

  snapshot() {
    const fleets = {};
    for (const method of ["dijkstra", "physarum"]) {
      const ticks = this.arrivalTicks[method];
      const sorted = ticks.length === this.count ? [...ticks].sort((a, b) => a - b) : null;
      const middle = sorted ? (sorted[(this.count - 1) >> 1] + sorted[this.count >> 1]) / 2 : null;
      const stats = this.stats[method];
      fleets[method] = {
        trucks: this.trucks[method].map(truck => ({
          node: truck.node, edge: truck.edge, remaining: truck.remaining,
          target: truck.target, arrival_tick: truck.arrival_tick,
          traversed: truck.traversed, route: (truck.plan || []).slice(0, 18)
        })),
        arrival_series: this.arrivalSeries[method],
        metrics: { ...stats, unique_roads_used: this.usedEdges[method].size,
          compute_ms: Math.round(stats.compute_ms * 1000) / 1000,
          median_arrival_tick: middle,
          congestion_extra_min: Math.round(stats.congestion_extra_min * 1000) / 1000,
          travel_min: Math.round(stats.travel_min * 1000) / 1000 }
      };
    }
    return {
      tick: this.tick, done: this.done, events: this.events, blocked: [...this.blocked].sort((a, b) => a - b),
      depot_nodes: this.depots, zone_nodes: this.zones, numpy_acceleration: false,
      density: Object.fromEntries(["dijkstra", "physarum"].map(method => [method,
        Object.fromEntries([...this.occupancy[method]].filter(([, count]) => count > 0))])),
      fleets, elapsed_wall_s: Math.round((performance.now() - this.startedAt) / 10) / 100
    };
  }
}

const PhysrumSimulator = { PythonRandom, RoadGraph, Fleet, modelScores };
if (typeof module !== "undefined" && module.exports) module.exports = PhysrumSimulator;
else self.PhysrumSimulator = PhysrumSimulator;

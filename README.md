# Physarum-GNN: Offline Guwahati Fleet Routing Simulation

An offline experiment that compares two routing policies, classic **Dijkstra** and a **Physarum-inspired GNN** policy, on a simulated fleet operating over an OSM-derived road network of Guwahati, India. Both policies face identical vehicles, road speeds, capacities, congestion math, and hazard events, so the comparison is like for like. Purple dashed connectors are synthetic simulation roads, never verified real streets.

> **Observed results:** on the denser map, neither routing policy wins every measure. The 50-vehicle run finished at tick 187 for Physarum and tick 191 for Dijkstra, but Dijkstra used much less routing CPU. At 1,000 vehicles, Physarum finished its last delivery sooner yet incurred more aggregate BPR drive delay. These are simulated outcomes, not a general superiority claim.

---

## Results at a glance

### Fleet dashboard (seed 2306; no visual tick delay)

| Vehicles per policy | Policy | Delivered | Median arrival tick | Last arrival tick | Fleet BPR delay |
| ---: | --- | ---: | ---: | ---: | ---: |
| 50 | Dijkstra | 50 / 50 | 122.5 | 191 | 62.2 min |
| 50 | Physarum-GNN | 50 / 50 | **114.5** | **187** | **34.1 min** |
| 1,000 | Dijkstra | 1,000 / 1,000 | 511 | 847 | **1,205.8 min** |
| 1,000 | Physarum-GNN | 1,000 / 1,000 | **473.5** | **808** | 3,361.9 min |

Median arrival tick and last-car tick are shown when all vehicles in the corresponding fleet have arrived. Median arrival is the middle per-vehicle arrival time on the simulation clock; for even fleet sizes, it averages the two middle arrival ticks. The live graph plots cumulative vehicles arrived against those same ticks for both policies. Ticks are simulated steps, not minutes or wall-clock seconds. BPR delay is summed across all vehicles and excludes intersection queue ticks. Wall time and routing CPU depend on the computer; a 1,000-vehicle run may take minutes. In this default A-to-B route, blocking each original route segment in turn yields 24 detours, 12 within 25% of the original drive time; without simulated joins, it yields 3 detours and none within 25%.

### Single-vehicle CLI benchmark (Maligaon–Kamakhya route, simulated blockade `14255`)

| Method | Valid after closure | Estimated drive | Rerouting latency |
| --- | --- | ---: | ---: |
| Fixed pre-disaster route | No | unavailable | 0 ms |
| Dijkstra rerun | Yes | 5.310 min | 1.072 ms |
| Physarum | Yes | 5.310 min | 5,467.157 ms |
| Physarum-GNN | Yes | 5.310 min | 5,649.875 ms |

**How to read these numbers**

- Every method that can reroute finds the same 5.310-minute detour. Dijkstra gets there thousands of times faster.
- The GNN did not improve route validity or drive time.
- The results do not support a claim that conventional shortest-path rerouting is static or inferior.
- Timings come from one run and vary by machine. The default seeded run is reproducible, but measured CPU time is not.
- The short purple links are simulated for this graph experiment; they are not verified travel corridors.

---

## Quick start

Requires **Python 3.10+**. No internet connection is needed.

```bash
python app.py
```

The app prints a fresh local address in the terminal. Open it in your browser and keep the terminal running. Press `Ctrl+C` to stop.

Optional: run the CLI benchmark instead.

```bash
python main.py
```

---

## Fleet dashboard

### The map

The main map is a **1.5× wider OSM-derived Guwahati close-up** with 722 mapped nodes and 834 visible links. It includes 694 bundled OSM segments and 140 short, simulated joins, marked purple and dashed. The connected routable area has 495 selectable intersections and 643 links. The joins add alternative paths for the simulation; they are not verified roads.

### Running a comparison

1. **Pick a start and destination** by clicking intersections on the map or by using the two node menus. These are the actual first depot and disaster zone.
2. **Set the fleet size.** The default is **50 vehicles per fleet**. Enter a whole number from 1 to 1000 in the number box, or use the synchronized slider.
3. Press **Dispatch both fleets**.

The simulator derives a second reachable depot and zone nearby so the fleets have more than one depot-zone pair. Each policy gets the same number of vehicles, the same selected depot-zone pairs, and the same road speeds, capacities, and hazard events.

While the simulation runs you can watch live traffic, road closures, vehicle locations, and delivery counts, plus a separate route map and report card for each policy. The graph below compares their cumulative arrivals at each simulation tick; the colored dashed lines mark each median arrival tick. Median arrival tick and last-car tick appear only when every vehicle in that fleet has arrived; if the tick cap ends first, final times are unavailable and the live arrival curve still shows progress. Larger fleets take longer to finish and may hit the configured tick cap.

### Report cards

Each policy's card shows:

- Fleet deliveries and the last arrival tick
- BPR added drive time in minutes, shown separately from aggregate congestion wait ticks
- Aggregate congestion wait ticks
- Median arrival tick and last-car tick, shown once every vehicle has arrived
- Measured routing CPU milliseconds
- Route update and recalculation counts
- Roads used

Moving time and queued or waiting ticks are separate metrics. A simulation tick is a visualization clock, not a real travel-time unit.

> **Depot caveat:** the bundled connected component does not include verified ISBT or GMCH sites, nor the named GS Road, VIP Road, or Zoo Road alternatives. The two depots and two zones shown are **simulated positions on the mapped roads**, and the app does not present them as those real facilities.

---

## How the simulation works

### Shared conditions for both policies

- **Road closures.** Both policies see the same temporary closures each tick. A concurrent producer thread proposes seeded micro-disruptions from a pre-event corridor, independently of either policy's current route. A lock and condition coordinate it with the master tick loop.
- **Closure rules.** Closures last eight ticks and are accepted only where depot-zone pairs still have a bypass.
- **Capacity.** Each road has a class-based capacity, and at most twice that number of vehicles may occupy it. Extra vehicles wait at the preceding intersection.
- **Congestion model.** For each admitted vehicle, travel duration follows the BPR formula below. The resulting simulated delay is rounded up to ticks. Both policies use identical congestion math. The backend retains the sum of free-flow and BPR road time across vehicles; the dashboard shows median arrival tick and the fleet-wide BPR penalty instead of that confusing aggregate drive-time sum. Vehicles also queue at full roads, and queue time is reported as wait ticks rather than conflated with drive minutes.

```text
travel time = free-flow time × (1 + 0.30 × (occupancy / capacity)^4)
```

### The two routing policies

| | Dijkstra | Physarum-GNN |
| --- | --- | --- |
| Initial routing | Shortest path per truck at dispatch | Capacity-aware route using conductivity and current occupancy |
| When it reroutes | Only when the remaining route is blocked, via a fresh search from the truck's current node | Chooses routes from current road occupancy and retained conductivity |
| Congestion handling | Reactive to blockages only; does not reroute solely because of congestion | Edge scores precomputed once per run; conductivity retained across ticks |
| Route extraction | Dijkstra | Weighted Dijkstra search internally |

Implementation notes:

- **NumPy is optional.** When installed, all conductivity values update in one vectorized operation. The standard-library fallback runs fully offline.
- The GUI does **not** run 100 pressure-solver iterations per frame.
- This is a routing *policy comparison*. It does not show that Physarum has lower algorithmic compute cost.

---

## CLI benchmark

`python main.py` blocks a simulated road on the original Maligaon–Kamakhya route and runs Dijkstra, warm-start Physarum, and Physarum-GNN on that same closure. It also runs the Jorabat and Panikhaiti scenarios.

### Outputs (in `output/`)

| File | Contents |
| --- | --- |
| `maligaon_before.svg` | Original route |
| `maligaon_after.svg` | Physarum detour |
| `maligaon_after_dijkstra.svg` | Dijkstra path |
| `maligaon_after_gnn.svg` | Physarum-GNN path |
| `*_routes.json` | Full paths and equivalent maps for each scenario |
| `benchmark.csv` | Benchmark results |
| `model_evaluation.csv` | GNN evaluation: recall of held-out bypass edges among the highest-scoring 5% of predictions |

### Block your own road

List the local road IDs along the original route:

```bash
python main.py --scenario maligaon --list-route
```

Then close one of them, which ensures the original route breaks:

```bash
python main.py --scenario maligaon --close-edge 14255
```

Other options:

- **Interactive mode:** `python main.py --scenario maligaon --interactive` lists IDs and lets you enter one or several comma-separated IDs at a prompt.
- **Multiple closures:** `--close-edge 14255,14256`
- **Other scenarios:** `--scenario jorabat` or `--scenario panikhaiti`
- **Close by location:** `--close-at 91.854,26.174` with `--scenario panikhaiti` blocks the nearest road to that longitude and latitude.

The IDs refer to segments in the bundled graph, not OSM way IDs.

**Reading the results**

- Each method reports whether its path remains valid, estimated drive minutes, rerouting milliseconds, and a route preview.
- Complete ordered road IDs are in the CSV. Complete route coordinates and map filenames are in `output/maligaon_custom_14255_routes.json` for the example above.
- Custom runs write distinct filenames (`*_before.svg`, `*_after.svg` for Physarum, `*_after_dijkstra.svg`, `*_after_gnn.svg`) and preserve the default maps.
- An unreachable destination produces an empty path and a blank estimated drive time.
- A closure off the original route can leave the fixed route valid.

### Measurement method

- The fixed pre-disaster route is computed before the closure and validated afterward. Zero rerouting time means it never reroutes.
- **Dijkstra** recomputes the shortest route with the closed road removed.
- **Physarum** starts from pre-event conductivity, solves nodal pressures, computes flux, and reinforces used edges while others decay. It then extracts a directed path.
- **Physarum-GNN** uses a lightweight one-hop GNN to modify the initial conductivity, with features and weights learned from simulated closures in separate corridors.
- Post-closure latency includes GNN inference, Physarum iterations, and path extraction. It excludes offline training and pre-event preparation.

---

## Data

`data/guwahati_roads.json` bundles **91,923 vertices** and **87,662 OSM-derived road segments**, of which 5,904 are marked one-way. Roads and geometries were extracted from bundled OpenFreeMap zoom-14 vector tiles. To rebuild the JSON from the cached tiles:

```bash
python scripts/build_tiles.py
```

## Limitations

- **Simulated, not real.** Speeds, capacities, destinations, congestion, and incident hazards are assumed for this demo. Closures are simulated, not observed events. Disasters and congestion are not live safety data.
- **Depots and zones are simulated positions**, not the real facilities named above (see the depot caveat).
- **Tile generalization.** Vector tiles can omit minor roads or misconnect junctions, and turn restrictions are unavailable.
- **Speeds** are assumed from road class, without traffic. Terrain and flood features are simulated proxies, not measured elevation or flood data.
- **Endpoint snapping** can move scenario endpoints away from the approximate corridor anchors. Check snapped coordinates in each `*_routes.json`.
- **Panikhaiti scenario** covers an eastbound approach toward Chandrapur, not Chandrapur itself.
- **Solver and one-way roads.** The pressure solver relaxes an undirected electrical network, while route extraction enforces one-way roads.
- **Not operational guidance.** This is an offline routing experiment and must not be used for emergency decisions.

---

## Development

```bash
python main.py --train                      # retrain the GNN
python -m unittest discover -s tests -v     # run tests
python -m pip install numpy                 # optional: vectorized conductivity updates
```

The project uses the **Python standard library only**; NumPy is an optional accelerator. The original single-vehicle dynamic experiment is kept in `physrum/dynamic.py` for reference.

## Credits

Road data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under ODbL, via [OpenFreeMap](https://openfreemap.org/) vector tiles.
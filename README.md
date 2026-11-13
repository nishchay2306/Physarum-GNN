# Physarum-GNN: Offline Guwahati Fleet Routing Simulation

An offline experiment that compares two routing policies, classic **Dijkstra** and a **Physarum-inspired GNN** policy, on a simulated fleet operating over an OSM-derived road network of Guwahati, India. Both policies face identical vehicles, road speeds, capacities, congestion math, and hazard events, so the comparison is like for like. Purple dashed connectors are synthetic simulation roads, never verified real streets.

> **How to interpret it:** Neither routing policy is guaranteed to win. Select paths and fleet size, then compare the live arrival curves, final median arrival tick, last-car tick, congestion and routing CPU for that particular simulation. Ticks are simulation steps, not wall-clock seconds or real travel minutes.

---

## Live fleet results

The dashboard derives per-path and combined results from each run. The maximum fleet size is 2,500 vehicles **per policy**. Runs at that limit can take several minutes, and the tick cap may leave some vehicles en route; final median and last-car figures remain unavailable until all vehicles arrive. Previously recorded figures from the narrower map are intentionally omitted because they do not describe this expanded map.

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

**[GitHub Pages demo](https://nishchay2306.github.io/Physarum-GNN/)** serves files from `docs/` on `main`. Publish this revision to the repository to make the updated interface live. It runs locally in the browser using a Web Worker and bundled map/model data. Choose 1–10 start/end paths, pick nodes on the map or in the selectors, enter up to 2,500 vehicles per policy, and dispatch both fleets. The map stays pale in either theme; the surrounding dashboard opens in black. The two full-width animated maps, combined arrival chart, and four-at-a-time path charts update as the run advances.

For the offline Python version, use **Python 3.10+**. No internet connection is needed.

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

The road close-up now covers about **1.65× the original connected extract**, displaying 768 mapped intersections and 875 visible links. The connected routable area has 518 selectable intersections and 667 links. The 140 purple dashed short joins are synthetic simulation roads, not verified real streets. The animated Physarum and Dijkstra maps fill the available page width and appear one after the other beneath the selection map. All three road maps retain the original pale map background, light road lines, white intersection dots, and readable map labels in either theme. The dashboard opens in a black theme; the theme toggle switches the surrounding interface to light mode if desired.

### Running a comparison

1. **Choose how many start → end paths to simulate** (1 to 10) with the *Number of start → end paths* box. Each path gets its own row in the sidebar.
2. **Set a start and an end for every path**, either from that row's two node menus or by clicking intersections on the map. Map clicks fill START 1, END 1, START 2, END 2 … in order; press **Pick on map** beside any slot to choose which one the next click sets. On the map, a filled pin is a start and a ringed pin is an end, with one colour per path. A start and end of the same path must differ and be connected by a directed route.
3. **Set the fleet size.** The default is **50 vehicles per fleet**. Enter a whole number from 1 to 2500 in the number box, or use the synchronized slider. The fleet is the total per policy and must be at least the number of paths.
4. Press **Dispatch both fleets**.

Vehicles are assigned to paths in turn (vehicle 1 to path 1, vehicle 2 to path 2, and so on), so every path receives an equal share, give or take one vehicle. Each policy gets the same number of vehicles per path, the same selected paths, and the same road speeds, capacities, and hazard events. A micro-disruption is only accepted if every selected path still has a bypass.

> **About earlier fleet screenshots and numbers:** they used the older four-combination layout, so they are not directly comparable with the current selected-path dashboard. Calling `Fleet(count=...)` without `pairs=` still uses that legacy layout for code compatibility.

The page opens with one path (the default Maligaon–Kamakhya route). Raising the path count fills new rows with deterministic, well-separated default paths, which you can change.

While the simulation runs you can watch live traffic, road closures, vehicle locations, and delivery counts, plus a separate route map and report card for each policy. The first graph below compares cumulative arrivals of all vehicles at each simulation tick; the colored dashed lines mark each median arrival tick. Under it, **Per-path timelines** display four paths in a 2×2 desktop grid. Fewer than four paths leave blank slots; ten paths produce three grids of four, with two blank slots in the last grid. Each graph shows only vehicles assigned to that path, with its own median, last-car tick and BPR delay for both policies. Median arrival tick and last-car tick appear only when every vehicle in that fleet has arrived; if the tick cap ends first, final times are unavailable and the live arrival curve still shows progress. Larger fleets take longer to finish and may hit the configured tick cap.

### Report cards

Each policy's card shows:

- Fleet deliveries and the last arrival tick (all paths combined; per-path figures are in the Per-path timelines section)
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

- **Road closures.** Both policies see the same temporary closures each tick. The Python app coordinates a concurrent producer thread with the master tick loop using a lock and condition. The hosted browser version runs the corresponding seeded hazard logic and simulation in a Web Worker.
- **Closure rules.** Closures last eight ticks and are accepted only where every selected start→end path still has a bypass.
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
python -m scripts.build_pages_data          # rebuild docs/map.json and docs/index.html
node tests/test_pages.js                    # test hosted browser simulator
```

GitHub Pages serves `docs/` from the `main` branch. The generator copies the current `fleet.html` into `docs/index.html`, adapts its API calls to the Web Worker, and rebuilds the bundled map and default paths. To preview locally, run `python -m http.server 8000 --directory docs` and open `http://localhost:8000/`. The hosted Web Worker uses JavaScript, so routing CPU times depend on the browser and device.

The project uses the **Python standard library only**; NumPy is an optional accelerator. The original single-vehicle dynamic experiment is kept in `physrum/dynamic.py` for reference.

## Credits

Road data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under ODbL, via [OpenFreeMap](https://openfreemap.org/) vector tiles.
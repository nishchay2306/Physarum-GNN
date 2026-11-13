"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { Fleet } = require("../docs/simulator.js");
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "../docs/map.json"), "utf8"));
assert.equal(data.max_pairs, 10);
assert.equal(data.default_pairs.length, 10);
for (const selected of [1, 4, 10]) {
  const fleet = new Fleet(data, { count: Math.max(50, selected), pairs: data.default_pairs.slice(0, selected) });
  fleet.advance();
  fleet.advance();
  const state = fleet.snapshot();
  assert.equal(state.pairs.length, selected);
  assert.equal(state.fleets.physarum.pairs.length, selected);
  assert.equal(state.fleets.dijkstra.pairs.length, selected);
  for (const method of ["physarum", "dijkstra"]) {
    assert.equal(state.fleets[method].pairs.reduce((total, p) => total + p.vehicles, 0), fleet.count);
    assert.equal(state.fleets[method].pairs[0].arrival_series.length, 3);
    assert.equal(state.fleets[method].trucks.length, fleet.count);
  }
}
const large = new Fleet(data, { count: 2500, pairs: data.default_pairs.slice(0, 4) });
assert.equal(large.maxTicks, 3250);
assert.equal(large.snapshot().fleets.dijkstra.pairs.reduce((n, pair) => n + pair.vehicles, 0), 2500);
assert.throws(() => new Fleet(data, { count: 2501, pairs: data.default_pairs.slice(0, 1) }), /2500/);
console.log("Browser fleet tests passed (1, 4, 10 paths and 2,500 vehicles).");

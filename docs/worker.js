"use strict";

importScripts("simulator.js");

let dataPromise;
let fleet;
let sessionId = 0;

function loadData() {
  if (!dataPromise) {
    dataPromise = fetch("map.json").then(response => {
      if (!response.ok) throw new Error("Could not load the bundled road map.");
      return response.json();
    });
  }
  return dataPromise;
}

function runTick(id) {
  if (id !== sessionId || !fleet || fleet.done) return;
  fleet.advance();
  if (!fleet.done) setTimeout(() => runTick(id), 20);
}

self.onmessage = async event => {
  const { requestId, type, body, session } = event.data;
  try {
    if (type === "start") {
      const data = await loadData();
      const next = new PhysrumSimulator.Fleet(data, {
        count: Number(body.count), start: body.start, target: body.target, seed: Number(body.seed)
      });
      fleet = next;
      const id = ++sessionId;
      self.postMessage({ requestId, value: {
        session: String(id), initial: next.initial, depots: next.depots, zones: next.zones
      } });
      setTimeout(() => runTick(id), 20);
    } else if (type === "state") {
      if (!fleet || session !== String(sessionId)) throw new Error("Simulation not found.");
      self.postMessage({ requestId, value: fleet.snapshot() });
    }
  } catch (error) {
    self.postMessage({ requestId, error: error.message });
  }
};

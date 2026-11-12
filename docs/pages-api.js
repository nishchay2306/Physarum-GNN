"use strict";

const pagesWorker = new Worker("worker.js");
const pagesRequests = new Map();
let pagesRequestId = 0;
let pagesMap;

pagesWorker.onmessage = event => {
  const { requestId, value, error } = event.data;
  const resolve = pagesRequests.get(requestId);
  if (!resolve) return;
  pagesRequests.delete(requestId);
  resolve({ ok: !error, json: async () => error ? { error } : value });
};

pagesWorker.onerror = event => {
  for (const resolve of pagesRequests.values()) {
    resolve({ ok: false, json: async () => ({ error: event.message || "Simulation worker failed." }) });
  }
  pagesRequests.clear();
};

function pagesRequest(type, body, session) {
  return new Promise(resolve => {
    const requestId = ++pagesRequestId;
    pagesRequests.set(requestId, resolve);
    pagesWorker.postMessage({ requestId, type, body, session });
  });
}

async function pagesApiFetch(path, options = {}) {
  if (path === "/api/map") {
    if (!pagesMap) pagesMap = fetch("map.json").then(response => {
      if (!response.ok) throw new Error("Could not load the bundled road map.");
      return response.json();
    });
    return { ok: true, json: async () => pagesMap };
  }
  if (path === "/api/start" && options.method === "POST") {
    return pagesRequest("start", JSON.parse(options.body));
  }
  if (path.startsWith("/api/state/")) {
    return pagesRequest("state", null, path.slice("/api/state/".length));
  }
  return { ok: false, json: async () => ({ error: "Unknown simulation request." }) };
}

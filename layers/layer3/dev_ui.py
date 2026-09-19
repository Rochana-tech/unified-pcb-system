#!/usr/bin/env python3
"""
Layer 3 - Simple Developer UI
================================
A minimal, dependency-free (Python stdlib only) local dashboard for
developers to inspect the live Digital Twin, see the bottleneck ranking,
and run what-if simulations while building against `digital_twin_layer3`.

This is a DEVELOPER TOOL, not a production dashboard - a full dashboard
is explicitly out of scope for Layer 3. No external packages are used
(no Flask/FastAPI/etc.) so it runs anywhere this package runs.

Run it:
    cd /path/to/folder/containing/digital_twin_layer3
    python3 -m digital_twin_layer3.dev_ui

Then open:  http://127.0.0.1:8765
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .config import ELECTRONICS_LINE, AUTOMOBILE_LINE, LineConfig
from .interfaces import ProductionLineService
from .models import (
    MachineState, MachineStatus,
    FaultEvent, FaultStatus,
    MachineHealthEvent, HealthStatus,
)

HOST = "127.0.0.1"
PORT = 8765

LINES = {"ELECTRONICS": ELECTRONICS_LINE, "AUTOMOBILE": AUTOMOBILE_LINE}


# ---------------------------------------------------------------------------
# Demo data seeding (so the dashboard has something to show on first load)
# ---------------------------------------------------------------------------

def seed_demo_data(service: ProductionLineService, line_config: LineConfig) -> None:
    """
    Feed a short synthetic Layer1/2A/2B history into `service` so the
    dashboard isn't empty on first load. 'M4' (Testing, on both sample
    lines) is seeded with an ANN fault + a degraded ML health score, and
    'M3's queue is made to climb, so both fault-driven and queue-growth-
    driven bottleneck signals are visible in the UI.
    """
    def ts(step: int, step_minutes: int = 5) -> datetime:
        return datetime.now(timezone.utc) - timedelta(minutes=(5 - step) * step_minutes)

    base_queue = {m.machine_id: i + 1 for i, m in enumerate(line_config.machines)}
    for step in range(6):
        for spec in line_config.machines:
            mid = spec.machine_id
            queue = base_queue[mid] + (step * 3 if mid == "M3" else step)
            units = step * (spec.default_capacity_uph * 5 / 60.0)
            service.ingest_machine_state(MachineState(
                machine_id=mid,
                status=MachineStatus.RUNNING,
                cycle_time_sec=spec.default_processing_time_sec,
                units_processed_total=int(units),
                queue_length=int(queue),
                capacity_units_per_hour=spec.default_capacity_uph,
                timestamp=ts(step),
            ))
        service.refresh()

    for spec in line_config.machines:
        mid = spec.machine_id
        if mid == "M4":
            service.ingest_fault_event(FaultEvent(
                machine_id=mid, fault_status=FaultStatus.FAULT,
                fault_type="MECHANICAL/BEARING FAULT", confidence=0.93,
            ))
            service.ingest_health_event(MachineHealthEvent(
                machine_id=mid, health_status=HealthStatus.DEGRADED, health_score=0.42,
            ))
        else:
            service.ingest_fault_event(FaultEvent(machine_id=mid, fault_status=FaultStatus.OK))
            service.ingest_health_event(MachineHealthEvent(
                machine_id=mid, health_status=HealthStatus.HEALTHY, health_score=0.95,
            ))
    service.refresh()


_SERVICES: dict[str, ProductionLineService] = {}


def get_service(line_name: str) -> ProductionLineService:
    line_name = (line_name or "ELECTRONICS").upper()
    if line_name not in LINES:
        line_name = "ELECTRONICS"
    if line_name not in _SERVICES:
        svc = ProductionLineService(LINES[line_name])
        seed_demo_data(svc, LINES[line_name])
        _SERVICES[line_name] = svc
    return _SERVICES[line_name]


# ---------------------------------------------------------------------------
# HTML / CSS / JS (single page, no build step, no external assets)
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Layer 3 Digital Twin - Dev Dashboard</title>
<style>
  :root {
    --bg: #0f1216; --panel: #161b22; --border: #2a313c; --text: #e6edf3;
    --muted: #8b949e; --accent: #58a6ff; --ok: #3fb950; --warn: #d29922; --bad: #f85149;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    background: var(--bg); color: var(--text); font-size: 13px;
  }
  header {
    display: flex; align-items: center; gap: 14px; padding: 12px 20px;
    border-bottom: 1px solid var(--border); background: var(--panel);
  }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; }
  header .sub { color: var(--muted); font-size: 12px; }
  select, input, button {
    background: #0d1117; color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
  }
  button {
    background: var(--accent); color: #0d1117; font-weight: 600; cursor: pointer; border: none;
  }
  button.secondary { background: #21262d; color: var(--text); border: 1px solid var(--border); }
  button:hover { opacity: 0.9; }
  main { padding: 18px 20px; display: grid; grid-template-columns: 1fr; gap: 18px; max-width: 1400px; margin: 0 auto; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
  .panel h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; }
  tr.fault td { background: rgba(248,81,73,0.10); }
  tr.degraded td { background: rgba(210,153,34,0.10); }
  tr.stale td { opacity: 0.55; }
  .badge { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .badge.ok { background: rgba(63,185,80,0.15); color: var(--ok); }
  .badge.fault { background: rgba(248,81,73,0.15); color: var(--bad); }
  .badge.degraded { background: rgba(210,153,34,0.15); color: var(--warn); }
  .badge.unknown { background: rgba(139,148,158,0.15); color: var(--muted); }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 980px) { .grid2 { grid-template-columns: 1fr; } }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
  .row label { color: var(--muted); font-size: 12px; margin-right: 4px; }
  pre { background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 10px; overflow: auto; max-height: 340px; }
  .muted { color: var(--muted); }
  .score-bar { height: 6px; border-radius: 3px; background: #21262d; overflow: hidden; width: 90px; display: inline-block; vertical-align: middle; }
  .score-bar > div { height: 100%; background: var(--accent); }
  footer { text-align: center; color: var(--muted); padding: 20px; font-size: 11px; }
</style>
</head>
<body>

<header>
  <h1>&#9881; Layer 3 Digital Twin</h1>
  <span class="sub">developer dashboard - read-only view + what-if runner</span>
  <span style="flex:1"></span>
  <label class="sub">Line</label>
  <select id="lineSelect">
    <option value="ELECTRONICS">Electronics</option>
    <option value="AUTOMOBILE">Automobile</option>
  </select>
  <label class="sub"><input type="checkbox" id="autoRefresh"> auto-refresh (3s)</label>
  <button class="secondary" id="refreshBtn">Refresh</button>
</header>

<main>

  <div class="panel">
    <h2>Live Machine Snapshot</h2>
    <table id="snapshotTable">
      <thead>
        <tr>
          <th>#</th><th>ID</th><th>Name</th><th>Status</th><th>Fault</th><th>Fault Type</th>
          <th>Health</th><th>Score</th><th>Capacity</th><th>Eff. Cap.</th><th>Proc. Time (s)</th>
          <th>Queue</th><th>Q. Growth</th><th>Throughput</th><th>Utilization</th><th>Availability</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
    <div class="muted" id="snapshotMeta" style="margin-top:8px;"></div>
  </div>

  <div class="panel">
    <h2>Bottleneck Ranking <span class="muted">(multi-factor, not utilization alone)</span></h2>
    <table id="bottleneckTable">
      <thead>
        <tr>
          <th>Rank</th><th>Machine</th><th>Score</th><th>Bottleneck?</th>
          <th>Utilization</th><th>Queue Growth</th><th>Proc. Time</th>
          <th>Capacity Erosion</th><th>Availability</th><th>Health/Fault</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="grid2">
    <div class="panel">
      <h2>Run What-If Simulation</h2>
      <div class="row">
        <label>Affected machine</label>
        <select id="wiMachine"></select>
        <label>Scenario</label>
        <select id="wiKind">
          <option value="DEGRADED">DEGRADED</option>
          <option value="UNAVAILABLE">UNAVAILABLE</option>
          <option value="REDUCED_CAPACITY">REDUCED_CAPACITY</option>
          <option value="INCREASED_PROCESSING_TIME">INCREASED_PROCESSING_TIME</option>
          <option value="SHIFT_WORKLOAD">SHIFT_WORKLOAD</option>
        </select>
      </div>
      <div class="row">
        <label>Factor</label>
        <input id="wiFactor" type="number" step="0.05" placeholder="e.g. 0.5" style="width:90px">
        <label id="wiShiftLabel" style="display:none">Shift to</label>
        <select id="wiShiftTo" style="display:none"></select>
        <label>Duration (hr)</label>
        <input id="wiDuration" type="number" value="8" style="width:70px">
        <label>Seed</label>
        <input id="wiSeed" type="number" value="42" style="width:70px">
      </div>
      <button id="runWhatIf">Run simulation</button>
      <span id="wiError" class="muted" style="color:var(--bad); margin-left:10px;"></span>
    </div>

    <div class="panel">
      <h2>Simulation Result</h2>
      <pre id="wiResult" class="muted">Run a scenario to see structured results here.</pre>
    </div>
  </div>

</main>

<footer>Backend-only interfaces (integration / digital twin / bottleneck / what-if) live in <code>digital_twin_layer3/</code> - this page only calls them.</footer>

<script>
const $ = (id) => document.getElementById(id);
let currentLine = "ELECTRONICS";

function badge(cls, text) {
  return `<span class="badge ${cls}">${text}</span>`;
}
function healthClass(h) {
  if (h === "CRITICAL") return "fault";
  if (h === "DEGRADED") return "degraded";
  if (h === "HEALTHY") return "ok";
  return "unknown";
}
function faultClass(f) {
  if (f === "FAULT") return "fault";
  if (f === "OK") return "ok";
  return "unknown";
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function loadSnapshot() {
  const snap = await fetchJSON(`/api/snapshot?line=${currentLine}`);
  const tbody = document.querySelector("#snapshotTable tbody");
  tbody.innerHTML = "";
  for (const m of snap.machines) {
    const tr = document.createElement("tr");
    if (m.fault_status === "FAULT") tr.classList.add("fault");
    else if (m.health_status === "DEGRADED" || m.health_status === "CRITICAL") tr.classList.add("degraded");
    if (m.stale) tr.classList.add("stale");
    tr.innerHTML = `
      <td>${m.sequence}</td><td><b>${m.machine_id}</b></td><td>${m.name}</td>
      <td>${m.machine_status}</td>
      <td>${badge(faultClass(m.fault_status), m.fault_status)}</td>
      <td>${m.fault_type || "-"}</td>
      <td>${badge(healthClass(m.health_status), m.health_status)}</td>
      <td>${m.health_score ?? "-"}</td>
      <td>${m.capacity_units_per_hour}</td>
      <td>${m.effective_capacity_units_per_hour}</td>
      <td>${m.processing_time_sec}</td>
      <td>${m.queue_length}</td>
      <td>${m.queue_growth_rate}</td>
      <td>${m.throughput_units_per_hour}</td>
      <td>${(m.utilization * 100).toFixed(1)}%</td>
      <td>${(m.availability * 100).toFixed(1)}%</td>
    `;
    tbody.appendChild(tr);
  }
  $("snapshotMeta").textContent = `${snap.line_name} - generated at ${snap.generated_at}`;

  const wiMachine = $("wiMachine"), wiShiftTo = $("wiShiftTo");
  const ids = snap.machines.map(m => m.machine_id);
  wiMachine.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join("");
  wiShiftTo.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join("");
}

async function loadBottleneck() {
  const data = await fetchJSON(`/api/bottleneck?line=${currentLine}`);
  const tbody = document.querySelector("#bottleneckTable tbody");
  tbody.innerHTML = "";
  for (const r of data.ranking) {
    const tr = document.createElement("tr");
    if (r.is_bottleneck) tr.classList.add("fault");
    const pct = Math.round(r.score * 100);
    tr.innerHTML = `
      <td>${r.rank}</td><td><b>${r.machine_id}</b> ${r.name}</td>
      <td><span class="score-bar"><div style="width:${pct}%"></div></span> ${r.score}</td>
      <td>${r.is_bottleneck ? badge("fault","YES") : badge("ok","no")}</td>
      <td>${r.factors.utilization}</td>
      <td>${r.factors.queue_growth}</td>
      <td>${r.factors.processing_time}</td>
      <td>${r.factors.capacity_erosion}</td>
      <td>${r.factors.availability}</td>
      <td>${r.factors.health_fault}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function refreshAll() {
  try {
    await loadSnapshot();
    await loadBottleneck();
  } catch (e) {
    console.error(e);
  }
}

$("lineSelect").addEventListener("change", (e) => {
  currentLine = e.target.value;
  refreshAll();
});

$("refreshBtn").addEventListener("click", refreshAll);

let autoTimer = null;
$("autoRefresh").addEventListener("change", (e) => {
  if (e.target.checked) {
    autoTimer = setInterval(refreshAll, 3000);
  } else {
    clearInterval(autoTimer);
  }
});

$("wiKind").addEventListener("change", (e) => {
  const isShift = e.target.value === "SHIFT_WORKLOAD";
  $("wiShiftLabel").style.display = isShift ? "inline" : "none";
  $("wiShiftTo").style.display = isShift ? "inline" : "none";
});

$("runWhatIf").addEventListener("click", async () => {
  $("wiError").textContent = "";
  $("wiResult").textContent = "Running...";
  const kind = $("wiKind").value;
  const body = {
    scenario_name: `${$("wiMachine").value}_${kind}`.toLowerCase(),
    kind,
    affected_machine_id: $("wiMachine").value,
    duration_hr: parseFloat($("wiDuration").value || "8"),
    seed: parseInt($("wiSeed").value || "42", 10),
  };
  const factor = $("wiFactor").value;
  if (factor !== "") body.factor = parseFloat(factor);
  if (kind === "SHIFT_WORKLOAD") body.shift_to_machine_id = $("wiShiftTo").value;

  try {
    const result = await fetchJSON(`/api/whatif?line=${currentLine}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("wiResult").textContent = JSON.stringify(result, null, 2);
  } catch (e) {
    $("wiError").textContent = e.message;
    $("wiResult").textContent = "Failed - see error above.";
  }
});

refreshAll();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep the console quiet

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        line = qs.get("line", ["ELECTRONICS"])[0]

        try:
            if parsed.path == "/":
                self._send_html(INDEX_HTML)
            elif parsed.path == "/api/topology":
                svc = get_service(line)
                self._send_json({"line": line, "topology": svc.get_topology()})
            elif parsed.path == "/api/snapshot":
                self._send_json(get_service(line).get_line_snapshot())
            elif parsed.path == "/api/combined":
                machine_id = qs.get("machine_id", [None])[0]
                if not machine_id:
                    self._send_json({"error": "machine_id is required"}, status=400)
                    return
                self._send_json(get_service(line).get_combined_condition(machine_id))
            elif parsed.path == "/api/bottleneck":
                svc = get_service(line)
                self._send_json({
                    "ranking": svc.get_bottleneck_ranking(),
                    "primary_bottleneck": svc.get_primary_bottleneck(),
                })
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as e:  # noqa: BLE001 - dev tool, surface any error to the UI
            self._send_json({"error": str(e)}, status=500)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        line = qs.get("line", ["ELECTRONICS"])[0]

        if parsed.path != "/api/whatif":
            self._send_json({"error": "not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
            svc = get_service(line)
            result = svc.run_what_if(
                scenario_name=payload.get("scenario_name", "adhoc"),
                kind=payload["kind"],
                affected_machine_id=payload["affected_machine_id"],
                factor=payload.get("factor"),
                shift_to_machine_id=payload.get("shift_to_machine_id"),
                duration_hr=float(payload.get("duration_hr", 8.0)),
                arrival_rate_uph=payload.get("arrival_rate_uph"),
                seed=int(payload.get("seed", 42)),
            )
            self._send_json(result)
        except (KeyError, ValueError) as e:
            self._send_json({"error": str(e)}, status=400)
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, status=500)


def main():
    # pre-seed both lines so the first page load is instant
    get_service("ELECTRONICS")
    get_service("AUTOMOBILE")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Layer 3 dev UI running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

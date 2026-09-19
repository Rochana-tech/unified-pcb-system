# Unified PCB Assembly Digital Twin

This integrates the supplied Layer 1 acquisition, Layer 2A ANN, Layer 3 digital twin, Layer 4 recovery engine, and developer workspace into one FastAPI process. The alert explanation package is connected as a separate backend layer.

The default is an **interactive simulation**, not a connection to a factory. It requires no camera, physical sensors, MQTT broker, or API key. The ANN actually runs inference on generated readings. No factory controller commands are issued.

## Run on this computer

Open a terminal in this folder:

```powershell
.\.venv\Scripts\python.exe main.py
```

Open **http://127.0.0.1:8002**. API documentation: **http://127.0.0.1:8002/docs**.

Alternative launcher (also sets up dependencies if the environment is missing):

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Stop with Ctrl+C. If port 8002 is occupied, use `--port 8003`. Use one server process: multiple workers would create independent simulation/timer state.

## Run the ZIP on another computer

Install Python 3.12, extract the ZIP, open its folder, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Only the initial dependency installation requires internet. The ZIP excludes the local virtual environment and runtime database.

## Review demonstration

1. Start on **Line overview** and watch output counters and queues change.
2. Open **Machine details → M4** and select **Inject bearing-fault demo**.
3. Generated values change; the supplied ANN classifies them. The simulated controller also reports a stoppage. The event starts a 20-second correction window.
4. Open **Alerts & explanations → Explain alert**. The eight clickable questions return structured, evidence-backed answers. Causes and repair duration remain unknown unless provided.
5. Either click **Simulate correction** in time, or let the window expire.
6. After expiry, the supplied recovery engine checks the configured testing standby, simulates alternatives, and applies the feasible route in the virtual line. Boards still visit packaging after testing.
7. **Recovery & what-if** compares assumed downtime with standby use without changing live routing.
8. **System & event log → Reset demo session** starts a new demo while retaining the SQLite audit log.

Try a soldering fault: the testing standby cannot solder, so the system reports no compatible alternative. To demonstrate a line without any standby, run:

```powershell
.\.venv\Scripts\python.exe main.py --no-demo-backup
```

## Architecture

```text
Generated demo flow OR external controller telemetry (HTTP / optional MQTT)
                 |
        validation and Layer 1 StateManager
                 |
         +-------+---------------------+
         |                             |
 optional four sensor readings    controller status/counters/queues
         |                             |
 supplied ANN (Layer 2A) --------------+
                 |
       supplied Digital Twin (Layer 3)
       capacity, rolling throughput, queue trends, bottleneck ranking
                 |
       supplied recovery engine (Layer 4)
       human timer -> compatible standby -> isolated simulation
                 |
       demo-only route application + SQLite audit
                 |
       grounded alert explanation -> structured JSON
                 |
       REST / WebSocket -> supplied HTML dashboard
```

### Files and source reuse

- `layers/layer1/`: supplied acquisition package, with imports made package-relative.
- `layers/layer2a/`: supplied ANN, scaler, configuration, synthetic training CSV, and tests.
- `layers/layer3/`: supplied fusion, twin, bottleneck code and original simulator. Fixed controller freshness, duplicate sampling, counter-reset handling, stopped-machine capacity, and zero-rate simulation behavior.
- `layers/layer4/`: supplied recovery state machine with real protocol adapters. Fixed repeated-fault timer resets and acceptance of expired corrections.
- `integration/`: shared configuration, data contracts, flow model, orchestration, recovery adapters, SQLite persistence, MQTT, APIs and explanation adapter.
- `frontend/`: the supplied HTML design, now using real API/WebSocket data. Fake service restart/model-switch buttons were removed.
- `alert_explanation/`: separate evidence-only explanation package. Default output uses templates; it does not claim an LLM generated the diagnosis.
- `controller/`: the four supplied controller generator, feature engineering, training and prediction scripts, retained as standalone research utilities. See the limitations below: their trained artifacts were not supplied.
- `SOURCE_MANIFEST.json`: original source paths and archive hashes. Original files were not modified.

The current frontend is the supplied HTML/JavaScript workspace, not a new React implementation. The versioned JSON API and WebSocket snapshot can also be consumed by your React dashboard.

## External controller data: no sensors required

Run:

```powershell
.\.venv\Scripts\python.exe main.py --mode external
```

No generated values are inserted in this mode. Send timestamped machine records to `POST /api/telemetry`. IDs are M1 through M5; timestamps must be timezone-aware and fresh. Duplicate/out-of-order readings, readings older than 30 seconds, and timestamps more than 5 seconds ahead are rejected.

Example PowerShell request:

```powershell
$reading = @{
  machine_id = "M4"
  timestamp = [DateTimeOffset]::UtcNow.ToString("o")
  status = "RUNNING"
  units_processed_total = 120
  queue_length = 3
  cycle_time_sec = 8.0
  capacity_units_per_hour = 450
  downtime_seconds = 0
}
Invoke-RestMethod -Uri "http://127.0.0.1:8002/api/telemetry" -Method Post -ContentType "application/json" -Body ($reading | ConvertTo-Json)
```

Repeat for every station with monotonically increasing timestamps. Use controller counters rather than submitting a calculated rate as a counter. Counter resets are recorded and start a new throughput window.

Optional `sensors` must contain all four numeric values: `current` (A), `temperature` (°C), `vibration` (mm/s RMS), and `rpm`. Without them, the sensor ANN is **unknown/unavailable**, while production monitoring and controller-down alerts still work. Missing values are never replaced with zero readings.

External what-if comparisons require fresh records for all five stages. External machine control and automatic physical reallocation are not implemented. Only explicitly configured, verified machine capabilities could enable that in a real installation.

### MQTT

```powershell
$env:MQTT_HOST = "localhost"
$env:MQTT_PORT = "1883"
.\.venv\Scripts\python.exe main.py --mode external --mqtt
```

Publish the same JSON contract to `factory/M4/telemetry` (or the relevant ID). A separately running broker is required. Topic and payload IDs must match. Optional environment variables: `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TLS=1`. MQTT failures remain visible in the service state; the app never pretends a broker is connected.

The supplied Layer 1 used separate sensor topics. The unified optional MQTT adapter intentionally consumes a validated combined telemetry record; existing publishers need a mapping adapter.

## Modeling decisions and honest limitations

- The serial operations are component placement, soldering, inspection, testing and packaging. The standby is parallel to testing, not a sixth required processing stage.
- **M4-BACKUP is synthetic and demo-only.** It is not evidence that your factory owns a compatible spare.
- The runtime and integrated what-if engine share a deterministic finite-buffer flow model, including blocking, starvation, queued/in-process boards, and 0.25-second time steps. What-ifs clone state and cannot mutate it. The original Layer 3 stochastic simulator is retained but is not used by the unified comparison endpoint. This implementation does not use SimPy.
- Demo assumptions: 500 arriving boards/hour, 12 waiting boards per buffer, the supplied cycle/capacity configuration, all boards passing inspection, no rework, and zero transfer/setup time. Interrupted tests restart in full on the standby. These assumptions are returned with each comparison.
- External simulations do not know actual progress within an active cycle; they assume a full remaining cycle. Configure arrivals/buffers and validate timings against real factory records before relying on predicted output.
- Throughput uses output-counter differences over up to 50 samples. The demo also shows actual simulated busy time. The supplied twin's throughput/capacity ratio is not a complete OEE calculation; quality/OEE is not claimed.
- ANN diagnosis is current-fault classification trained on synthetic data, not validated physical diagnosis. Demo readings use the supplied training profiles with small jitter. They are not real factory sensor measurements or independent validation data.
- The original Layer 1 sensor generator and ANN training generator use different ranges. The unified demo uses the latter profiles explicitly rather than silently presenting that distribution mismatch as reliable classification.
- The fault label chosen by the demo injector is not passed into the ANN. Only four numeric readings are passed. Injection also models an actual stoppage; it does not demonstrate that every bearing fault necessarily stops a real machine.
- **Future failure prediction / Layer 2B is unavailable.** No trained `failure_model.joblib` or `anomaly_model.joblib` was supplied. No ground-truth health label is substituted for a prediction.
- The controller research generator chooses faults randomly and advances counters per poll, not elapsed production time. Its training script randomly splits overlapping windows and includes truncated future-label windows. These scripts are retained for review, not promoted as a validated failure forecast. Before integrating them, use time/group-separated evaluation, complete future labels, controller-ID mapping, and relevant historical failure data.
- The explanation layer is deterministic evidence-grounded text by default. It explains ANN outputs, twin metrics and recovery results; it does not invent maintenance procedures or infer a confirmed root cause.
- A restart begins a new runtime session. SQLite preserves event history; it does not restore active recovery timers, WIP or routes. This local prototype has no multi-user authentication or production deployment hardening.

## Tests and verification

From this folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m layers.layer2a.tests.test_inference
```

Integration tests cover actual model inference, finite-buffer board conservation, blocking/starvation, human correction before/after deadline, compatible/no-alternative recovery, applied routing, simulation isolation, controller-only ingestion, stale/out-of-order data, counter resets, JSON explanations, REST/WebSockets and SQLite persistence.

`tests/browser-smoke.cjs` checks the running dashboard using Playwright and Edge. Set `PLAYWRIGHT_MODULE` to your Playwright module path and `BROWSER_EXECUTABLE` to your browser executable if needed. Set `TEST_URL` to change the server URL. It injects and resets demo incidents. Browser checks covered desktop/mobile layout, live updates, preserved form inputs, what-if results, eight questions, automatic route changes, and no JavaScript exceptions.

Verified locally with Python 3.12 and scikit-learn 1.8.0, matching the saved ANN artifacts. Exact installed versions are in `requirements.lock.txt`. HTTP/WebSocket and browser flows were exercised. A physical factory and an external MQTT broker were not available for end-to-end verification.


## Live 3D machine view

The line overview now uses Three.js 0.180.0/WebGL with local vendored dependencies and OrbitControls. No CDN connection is required when running the dashboard.

Six recognizable procedural machine models represent the five production stages and testing standby: an XY pick-and-place head with feeder reels, a three-zone reflow oven with exhausts, an inspection camera with scan light, a pneumatic test fixture with contact pins, and a carton packaging gantry.

Drag to orbit, scroll/pinch to zoom, select a machine, and use **Focus selected** for a close-up. Machine motion runs only while the backend reports RUNNING and the data connection is fresh. DOWN, BLOCKED, IDLE and stale data pause process motion. Queue visuals show up to 12 boards; the numeric label preserves the full backend queue count. Observed output-counter increases trigger illustrative board-transfer animations. The standby route becomes visible when the backend actually reallocates testing work.

Geometry and mechanism motion are representative, not measured CAD dimensions or live axis-position telemetry. Timing is visually interpolated between updates; these animations do not create output, faults or production predictions. The factory model stays separate from recovery logic.

Additional browser verification: `tests/three-smoke.cjs` uses isolated browser fixtures without changing the user's live simulation. It checks WebGL startup, machine motion, fault/blockage pauses, queue counts, standby routing, counter-driven transfers, selection, orbit, focus, stale-data pause, scene disposal/remount, and mobile layout. Third-party license: `frontend/vendor/THREE-LICENSE.txt`. Official documentation: https://threejs.org/docs/


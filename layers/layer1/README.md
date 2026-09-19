# Layer 1 — Data Acquisition & Real-Time Communication

Smart Manufacturing Intelligence System — **Layer 1 only**.
Factory: `M1` Component Placement, `M2` Soldering, `M3` Inspection, `M4` Testing, `M5` Packaging.

This layer does **not** build the ANN, Digital Twin, scheduler, or dashboard — it only
produces, validates and exposes two independent real-time data streams for Layers 2/3.

## Architecture

```
STREAM A — SENSOR DATA (machine health / ANN fault detection)
  SensorSimulator (dummy, threaded, ticks every SENSOR_PUBLISH_INTERVAL_SEC)
        │  NORMAL / DEGRADED / FAULT state machine per machine
        ▼
  MQTTSensorPublisher --publish--> MQTT broker --topics--> factory/M1..M5/sensors
                                                                  │
                                                                  ▼
                                                    MQTTSensorConsumer (subscribe,
                                                    validate schema, reject malformed/
                                                    stale, cache latest per machine)

STREAM B — MACHINE / PRODUCTION DATA (Digital Twin / production intelligence)
  DummyMachineDataProvider (implements MachineDataProvider interface,
  threaded, ticks every MACHINE_DATA_INTERVAL_SEC) --subscribe callback-->
        latest state cache, no MQTT assumption baked in

Both streams feed a shared StateManager that correlates them by
machine_id + timestamp WITHOUT mixing them at the source.

A FastAPI app (api/app.py) exposes both streams + fused state to Layer 2/3:
  GET  /sensors/latest, /sensors/{id}/latest
  GET  /production/latest, /production/{id}/latest
  GET  /state, /state/{id}
  WS   /ws/production   (continuous Stream B feed)
```

## Folder structure

```
layer1_data_acquisition/
├── main.py                        # orchestrator - run this
├── requirements.txt
├── config/
│   └── config.py                  # machines, intervals, MQTT settings, fault probabilities
├── common/
│   ├── logger.py
│   └── utils.py                   # timestamps, JSON/schema validation, staleness check
├── sensor_stream/                 # STREAM A
│   ├── fault_patterns.py          # NORMAL/DEGRADED/FAULT state machine + value generator
│   ├── sensor_simulator.py        # continuous generator (threaded loop, not batch)
│   ├── mqtt_publisher.py          # publishes to factory/<machine>/sensors
│   └── mqtt_consumer.py           # subscribes, validates, rejects malformed/stale
├── machine_stream/                # STREAM B
│   ├── machine_data_provider.py   # abstract MachineDataProvider interface
│   ├── dummy_machine_provider.py  # dummy implementation (swap later for real source)
│   └── state_manager.py           # latest fused state for all 5 machines
├── api/
│   └── app.py                     # FastAPI read interface + WebSocket for Layer 2/3
└── schemas/
    ├── sensor_schema.json         # Stream A JSON schema + example
    └── machine_schema.json        # Stream B JSON schema + example
```

## Run instructions

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get an MQTT broker running (Stream A needs one)
Easiest for a hackathon — run a local Mosquitto broker:
```bash
# Docker (recommended)
docker run -it -p 1883:1883 eclipse-mosquitto

# or, if Mosquitto is installed locally
mosquitto -p 1883
```
No broker handy? Point `MQTT_BROKER_HOST` at a public test broker instead
(fine for a demo, not for production):
```bash
export MQTT_BROKER_HOST=test.mosquitto.org
```

### 3. Run Layer 1
```bash
python main.py
```
This starts, in one process:
- the sensor simulator + MQTT publisher (Stream A)
- the MQTT consumer/validator (Stream A)
- the dummy machine/production provider (Stream B)
- the FastAPI server on `http://localhost:8000` (`/docs` for interactive API)

You'll see continuous log lines every publish tick, and a stats summary
(`received/accepted/rejected`) every 5 seconds. `[FAULT]` lines mark injected
fault conditions, especially on M4.

### 4. Watch the streams directly (optional)
```bash
# raw MQTT traffic, Stream A
mosquitto_sub -h localhost -t 'factory/+/sensors' -v

# Stream B + fused state via the API
curl http://localhost:8000/production/latest
curl http://localhost:8000/state/M4
```

### 5. Configuration
All intervals and connection settings are environment-variable overridable
(see `config/config.py`), e.g.:
```bash
export SENSOR_PUBLISH_INTERVAL_SEC=1.0
export MACHINE_DATA_INTERVAL_SEC=2.0
export STALE_MESSAGE_THRESHOLD_SEC=15
```

## Fault injection

- Every machine runs an independent NORMAL → DEGRADED → FAULT Markov chain
  (`config.DEFAULT_STATE_TRANSITION`), so faults appear organically over time.
- M4 uses a higher-probability table (`config.M4_STATE_TRANSITION`) and the
  spec's explicit pattern under FAULT: **vibration ↑, temperature ↑, RPM ↓**.
- For a deterministic demo, call `simulator.inject_fault("M4")` from code, or
  add a small trigger endpoint in `api/app.py` if you want it exposed over HTTP.

## Why two independent streams, not one

- Stream A is transport-committed to MQTT (pub/sub, many downstream ANN
  consumers, decoupled timing) — a real plant's PLC/sensor gateways would
  speak MQTT/OPC-UA the same way.
- Stream B is intentionally **not** tied to MQTT. `MachineDataProvider` is an
  abstract interface; `DummyMachineDataProvider` is the only implementation
  today. A future real MES/SCADA adapter (REST polling, Kafka, DB triggers,
  whatever the real system exposes) just implements the same four methods
  (`start`, `stop`, `get_latest_state`, `subscribe`) and gets swapped into
  `main.py` — nothing in Layer 2/3 changes.
- `StateManager` correlates both by `machine_id` + `timestamp` for anyone who
  wants a fused view, but the two sources are never merged upstream of it.

## Tinkercad

Not connected to this software. It is a separate physical/sensor demo only.

## Simple UI (added)

A standalone, presentation-friendly UI is included in `frontend/`.
It uses demo values only and does **not** connect to the Layer 1 API or MQTT.
This keeps the UI independent from the Layer 1 backend while showing the two
streams clearly.

### Run the UI

From the `layer1_data_acquisition` folder:

```bash
run_ui.bat
```

Then open `http://localhost:5173` in a browser.

A sample controller dataset is included at:

```text
datasets/controller_sample.csv
```

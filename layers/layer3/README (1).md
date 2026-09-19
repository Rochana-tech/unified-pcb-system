# Layer 3 — Manufacturing Line Digital Twin

A production Digital Twin that fuses Layer 1 (machine/production data),
Layer 2A (ANN fault detection), and Layer 2B (ML machine-health scoring)
into one live, queryable model of the line — plus a bottleneck detector
and an isolated what-if simulator, both exposed through a clean interface
for Layer 4.

## Package layout

| File               | Responsibility |
|---------------------|----------------|
| `models.py`          | Event contracts: `FaultEvent`, `MachineHealthEvent`, `MachineState`, and the fused `CombinedMachineCondition`. |
| `integration.py`     | **First integration interface.** Ingests the three event streams and fuses them per machine, e.g. `{"machine_id": "M4", "fault_status": "FAULT", "fault_type": "MECHANICAL/BEARING FAULT", "health_status": "DEGRADED"}`. |
| `config.py`          | Static line topologies: `ELECTRONICS_LINE` (M1 Component Placement → M2 Soldering → M3 Inspection → M4 Testing → M5 Packaging) and `AUTOMOBILE_LINE` (M1 Welding → M2 Painting → M3 Assembly → M4 Testing → M5 Packaging). |
| `digital_twin.py`    | The live twin. Tracks status, capacity, processing time, utilization, queue length, throughput, availability, health, and fault/degradation state per machine, derived from the fused conditions. |
| `bottleneck.py`      | Multi-factor bottleneck scorer (utilization, queue growth, processing time, capacity erosion, availability, health/fault) — never utilization alone. |
| `simulation.py`      | Isolated what-if discrete-event simulator. Operates on a **copy** of twin state; never mutates live state. |
| `interfaces.py`      | `ProductionLineService` — the one class Layer 4 needs. |
| `dev_ui.py`          | **Optional developer UI.** A single-file, stdlib-only local dashboard (no Flask/npm/build step) for visually inspecting the twin, bottleneck ranking, and running what-if scenarios while developing. Not part of Layer 3's backend contract. |
| `example_usage.py`   | End-to-end runnable example (see below). |

## Developer UI (optional)

For convenience while developing against this package, `dev_ui.py` spins
up a small local HTTP server (Python's stdlib `http.server`, no external
dependencies) with a single-page dashboard: a live machine snapshot table,
the bottleneck ranking with factor breakdown, and a form to run what-if
scenarios and see the structured JSON result.

```bash
cd /path/to/folder/containing/digital_twin_layer3
python3 -m digital_twin_layer3.dev_ui
# -> open http://127.0.0.1:8765
```

It seeds both sample lines with a short synthetic history on first request
purely so the dashboard isn't empty — real deployments would call
`service.ingest_*` from actual Layer 1/2A/2B feeds instead. This UI is a
developer convenience only; it is not the production dashboard the spec
explicitly puts out of scope for Layer 3.

## Quick start

```python
from digital_twin_layer3 import (
    ELECTRONICS_LINE, ProductionLineService,
    MachineState, FaultEvent, MachineHealthEvent,
    MachineStatus, FaultStatus, HealthStatus,
)

service = ProductionLineService(ELECTRONICS_LINE)

# Layer 1
service.ingest_machine_state(MachineState(
    machine_id="M4", status=MachineStatus.RUNNING,
    cycle_time_sec=8.0, units_processed_total=1000,
    queue_length=11, capacity_units_per_hour=450,
))

# Layer 2A (ANN)
service.ingest_fault_event(FaultEvent(
    machine_id="M4", fault_status=FaultStatus.FAULT,
    fault_type="MECHANICAL/BEARING FAULT", confidence=0.93,
))

# Layer 2B (ML)
service.ingest_health_event(MachineHealthEvent(
    machine_id="M4", health_status=HealthStatus.DEGRADED, health_score=0.42,
))

service.refresh()  # recompute derived twin metrics from latest events

service.get_combined_condition("M4")
# {"machine_id": "M4", "machine_status": "RUNNING", "fault_status": "FAULT",
#  "fault_type": "MECHANICAL/BEARING FAULT", "health_status": "DEGRADED", ...}

service.get_line_snapshot()          # full live twin state, in sequence order
service.get_bottleneck_ranking()     # all machines, ranked by composite score
service.get_primary_bottleneck()     # the flagged bottleneck, or None

service.run_what_if(
    scenario_name="M4_unavailable_8h",
    kind="UNAVAILABLE",              # or DEGRADED / REDUCED_CAPACITY /
                                      # INCREASED_PROCESSING_TIME / SHIFT_WORKLOAD
    affected_machine_id="M4",
    duration_hr=8.0,
    seed=7,                          # reproducible
)
```

Run the full demo:

```bash
PYTHONPATH=. python3 example_usage.py
```

## Design notes

**Integration is deliberately dumb.** `IntegrationService` only fuses the
latest known state from each of the three sources per machine; it does not
compute any metric. That keeps the "first integration interface" the spec
asked for trivially testable and independent from everything downstream.

**Bottleneck score is multi-factor and transparent.** Six weighted, capped
[0,1] factors combine into one score (weights live in `bottleneck.WEIGHTS`,
easy to retune). The result carries the full factor breakdown so a human
or Layer 4 can see *why* a machine scored the way it did — without Claude
or any model generating a natural-language explanation, per the spec.

**What-if simulation cannot touch live state — by construction, not by
convention.** `WhatIfSimulator` is built from
`DigitalTwin.clone_metrics_for_simulation()`, which deep-copies metrics
into plain numbers and immediately discards any reference to the live
`MachineMetrics` objects. It also builds its own internal `_SimStation`
graph. There is no code path from the simulator back into the twin.
`example_usage.py` asserts the twin's snapshot is byte-for-byte identical
before and after running scenarios.

**Why a hand-rolled DES engine instead of `simpy`.** `simpy` isn't
installable in this offline environment. The spec explicitly allows "SimPy
or an equivalent discrete-event simulation approach" — `simulation.py`
implements a heap-based priority-queue event scheduler with the same
core semantics (timestamped events, processes scheduling future events).
Swapping in real `simpy.Environment` later only touches `_run_engine()`.

**Simulation modeling assumptions** (stated explicitly, not hidden):
each station is a single-queue/single-server node; inter-arrival and
service times are exponential (a standard, reproducible M/M/1-per-station
approximation, seeded for reproducibility); a `SHIFT_WORKLOAD` scenario
tags each unit with its true next station so, after being served by the
alternate machine, it continues on down the original line rather than
looping back through the alternate.

## Explicitly out of scope (per spec)

- No recovery/scheduling decisions
- No AI-generated explanations (bottleneck output is structured factor
  data only)
- No dashboard/UI
- No developer workspace

These are left for Layer 4 or a human to act on.

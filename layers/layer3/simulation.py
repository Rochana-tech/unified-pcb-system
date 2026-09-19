"""
Layer 3 - What-If Simulation
=============================
A discrete-event simulation (DES) of the production line used to answer
"what if" questions WITHOUT ever touching live Digital Twin state.

Why a hand-rolled DES instead of the `simpy` package
------------------------------------------------------
`simpy` is not installable in this offline environment, and the spec
explicitly allows "SimPy or an equivalent discrete-event simulation
approach". This module implements a minimal, heap-based event scheduler
with the same core semantics SimPy uses (a priority queue of timestamped
events, processes that schedule future events) - it is a drop-in
*approach*, not a shortcut. Swapping in real `simpy.Environment` later is
a localized change limited to `_run_engine()`.

Modeling assumptions (documented, not hidden)
------------------------------------------------
- Each station is modeled as a single-queue, single-server node whose
  service RATE is that station's effective capacity (units/hour). This
  already folds in the health/fault capacity derate applied by the twin.
- Arrivals to the first station follow a Poisson process (exponential
  inter-arrival times); service times are exponential with mean
  1/effective_capacity. This is a standard, reproducible M/M/1-per-station
  approximation appropriate for comparative "what-if" analysis (i.e. we
  care about the *relative* impact of a scenario, not a certified capacity
  plan).
- A completed unit is routed immediately to the next station in sequence,
  unless a `SHIFT_WORKLOAD` scenario reroutes the affected station's
  intake to a designated alternate station.

Isolation guarantee
------------------------
`WhatIfSimulator.run()` only ever reads a *copy* of live metrics
(`DigitalTwin.clone_metrics_for_simulation()`) and a plain list of
machine_ids (topology). It builds its own internal `_SimStation` objects
and never holds a reference to, or writes to, any live DigitalTwin /
MachineMetrics object.
"""

from __future__ import annotations

import heapq
import itertools
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .digital_twin import MachineMetrics


class ScenarioKind(str, Enum):
    DEGRADED = "DEGRADED"                             # sustained health-degraded capacity derate
    UNAVAILABLE = "UNAVAILABLE"                        # machine goes down (rate -> 0)
    REDUCED_CAPACITY = "REDUCED_CAPACITY"              # capacity * factor
    INCREASED_PROCESSING_TIME = "INCREASED_PROCESSING_TIME"  # mean service time * factor
    SHIFT_WORKLOAD = "SHIFT_WORKLOAD"                  # reroute intake to alternate machine


@dataclass
class ScenarioSpec:
    name: str
    kind: ScenarioKind
    affected_machine_id: str
    factor: Optional[float] = None            # for REDUCED_CAPACITY / INCREASED_PROCESSING_TIME / DEGRADED override
    shift_to_machine_id: Optional[str] = None  # for SHIFT_WORKLOAD


@dataclass
class MachineSimResult:
    machine_id: str
    throughput_units_per_hour: float
    avg_queue_length: float
    max_queue_length: int
    avg_delay_sec: float
    utilization: float

    def to_dict(self) -> Dict:
        return {
            "machine_id": self.machine_id,
            "throughput_units_per_hour": round(self.throughput_units_per_hour, 2),
            "avg_queue_length": round(self.avg_queue_length, 2),
            "max_queue_length": self.max_queue_length,
            "avg_delay_sec": round(self.avg_delay_sec, 1),
            "utilization": round(self.utilization, 4),
        }


@dataclass
class SimulationResult:
    scenario_name: str
    duration_hr: float
    seed: int
    affected_machines: List[str]
    line_throughput_units_per_hour: float   # completions out of the last station
    per_machine: Dict[str, MachineSimResult]

    def to_dict(self) -> Dict:
        return {
            "scenario_name": self.scenario_name,
            "duration_hr": self.duration_hr,
            "seed": self.seed,
            "affected_machines": self.affected_machines,
            "line_throughput_units_per_hour": round(self.line_throughput_units_per_hour, 2),
            "per_machine": {mid: r.to_dict() for mid, r in self.per_machine.items()},
        }


# ---------------------------------------------------------------------------
# Internal simulation-only station model (independent of live MachineMetrics)
# ---------------------------------------------------------------------------

@dataclass
class _SimStation:
    machine_id: str
    service_rate_uph: float          # units/hour, > 0 unless UNAVAILABLE
    next_id: Optional[str]           # normal successor in the line, or None if last
    redirect_intake_to: Optional[str] = None  # SHIFT_WORKLOAD override

    # each entry: (arrival_time, forward_after) - forward_after is the
    # logical next station once this unit's work here is done (independent
    # of which physical machine actually performs the work)
    queue: List = field(default_factory=list)
    busy_until: Optional[float] = None
    completions: int = 0
    busy_time_accum: float = 0.0
    delay_samples: List[float] = field(default_factory=list)
    queue_area: float = 0.0          # integral of queue length over time (for time-avg)
    max_queue: int = 0
    last_event_time: float = 0.0
    unavailable: bool = False


class WhatIfSimulator:
    """
    Runs isolated what-if scenarios against a *copy* of the current line
    state. Never mutates, and never even references, live DigitalTwin
    objects after construction.
    """

    def __init__(self, machine_metrics_snapshot: Dict[str, MachineMetrics], topology: List[str]):
        # Copy out only the plain numbers we need; drop all references to
        # the original MachineMetrics objects so nothing here can reach
        # back into live state.
        self._baseline_rate: Dict[str, float] = {
            mid: max(0.0, machine_metrics_snapshot[mid].effective_capacity_units_per_hour)
            for mid in topology
        }
        self._topology: List[str] = list(topology)

    # -- public API ---------------------------------------------------------

    def run(
        self,
        scenario: ScenarioSpec,
        duration_hr: float = 8.0,
        arrival_rate_uph: Optional[float] = None,
        seed: int = 42,
    ) -> SimulationResult:
        stations = self._build_stations(scenario)

        if arrival_rate_uph is None:
            # Default load: 85% of the *baseline* (unmodified) first-station
            # capacity, so scenario impact is visible without an unrealistically
            # overloaded baseline.
            arrival_rate_uph = 0.85 * self._baseline_rate[self._topology[0]]

        self._run_engine(stations, arrival_rate_uph, duration_hr, seed)

        per_machine: Dict[str, MachineSimResult] = {}
        for mid in self._topology:
            st = stations[mid]
            avg_delay = sum(st.delay_samples) / len(st.delay_samples) if st.delay_samples else 0.0
            avg_queue = st.queue_area / duration_hr if duration_hr > 0 else 0.0
            utilization = (st.busy_time_accum / duration_hr) if duration_hr > 0 else 0.0
            per_machine[mid] = MachineSimResult(
                machine_id=mid,
                throughput_units_per_hour=st.completions / duration_hr if duration_hr > 0 else 0.0,
                avg_queue_length=avg_queue,
                max_queue_length=st.max_queue,
                avg_delay_sec=avg_delay * 3600.0,
                utilization=min(1.0, utilization),
            )

        last_station_id = self._effective_last_station(stations)
        line_throughput = per_machine[last_station_id].throughput_units_per_hour

        affected = [scenario.affected_machine_id]
        if scenario.kind == ScenarioKind.SHIFT_WORKLOAD and scenario.shift_to_machine_id:
            affected.append(scenario.shift_to_machine_id)

        return SimulationResult(
            scenario_name=scenario.name,
            duration_hr=duration_hr,
            seed=seed,
            affected_machines=affected,
            line_throughput_units_per_hour=line_throughput,
            per_machine=per_machine,
        )

    # -- construction of the scenario-modified station graph ----------------

    def _build_stations(self, scenario: ScenarioSpec) -> Dict[str, _SimStation]:
        stations: Dict[str, _SimStation] = {}
        for i, mid in enumerate(self._topology):
            next_id = self._topology[i + 1] if i + 1 < len(self._topology) else None
            stations[mid] = _SimStation(
                machine_id=mid,
                service_rate_uph=self._baseline_rate[mid],
                next_id=next_id,
            )

        target = scenario.affected_machine_id
        if target not in stations:
            raise ValueError(f"affected_machine_id '{target}' is not in this line's topology")
        st = stations[target]

        if scenario.kind == ScenarioKind.DEGRADED:
            factor = scenario.factor if scenario.factor is not None else 0.7  # matches twin's DEGRADED derate
            st.service_rate_uph *= factor

        elif scenario.kind == ScenarioKind.UNAVAILABLE:
            st.unavailable = True
            st.service_rate_uph = 0.0

        elif scenario.kind == ScenarioKind.REDUCED_CAPACITY:
            factor = scenario.factor if scenario.factor is not None else 0.5
            st.service_rate_uph *= factor

        elif scenario.kind == ScenarioKind.INCREASED_PROCESSING_TIME:
            factor = scenario.factor if scenario.factor is not None else 1.5
            # processing time up  <=>  service rate down by the same factor
            st.service_rate_uph /= factor

        elif scenario.kind == ScenarioKind.SHIFT_WORKLOAD:
            if not scenario.shift_to_machine_id or scenario.shift_to_machine_id not in stations:
                raise ValueError("SHIFT_WORKLOAD requires a valid shift_to_machine_id in the topology")
            st.redirect_intake_to = scenario.shift_to_machine_id

        else:
            raise ValueError(f"Unsupported scenario kind: {scenario.kind}")

        return stations

    def _effective_last_station(self, stations: Dict[str, _SimStation]) -> str:
        # last station in sequence order (topology order is production order)
        return self._topology[-1]

    # -- the DES engine (heap-based; SimPy-equivalent semantics) -------------

    def _run_engine(
        self,
        stations: Dict[str, _SimStation],
        arrival_rate_uph: float,
        duration_hr: float,
        seed: int,
    ) -> None:
        rng = random.Random(seed)
        counter = itertools.count()   # tie-breaker for heap ordering
        events: List = []  # (time, seq, kind, payload)

        def schedule(time: float, kind: str, payload):
            heapq.heappush(events, (time, next(counter), kind, payload))

        # seed first external arrival into the first station
        first_id = self._topology[0]
        if arrival_rate_uph > 0:
            t0 = rng.expovariate(arrival_rate_uph)
            schedule(t0, "EXTERNAL_ARRIVAL", first_id)

        def maybe_start_service(mid: str, now: float):
            st = stations[mid]
            if st.unavailable or st.busy_until is not None or not st.queue:
                return
            arrival_time, forward_after = st.queue.pop(0)
            st.delay_samples.append(now - arrival_time)  # wait + about-to-be-served
            service_time = rng.expovariate(st.service_rate_uph) if st.service_rate_uph > 0 else float("inf")
            st.busy_until = now + service_time
            schedule(st.busy_until, "SERVICE_END", (mid, forward_after))

        def enqueue(logical_dest: str, now: float):
            """
            Route a unit to `logical_dest` (a position in the original
            production sequence). If that station's intake has been
            redirected (SHIFT_WORKLOAD), the unit is physically queued at
            the alternate machine instead - but it is tagged with
            `logical_dest`'s own normal successor, so once the alternate
            machine finishes it, the unit still continues on to the correct
            next station rather than looping back through the alternate.
            """
            dest_st = stations[logical_dest]
            forward_after = dest_st.next_id
            actual_mid = dest_st.redirect_intake_to or logical_dest
            actual_st = stations[actual_mid]
            advance_queue_area(actual_st, now)
            actual_st.queue.append((now, forward_after))
            actual_st.max_queue = max(actual_st.max_queue, len(actual_st.queue))
            if actual_st.busy_until is None and not actual_st.unavailable:
                busy_start[actual_mid] = now
            maybe_start_service(actual_mid, now)

        def advance_queue_area(st: _SimStation, now: float):
            dt = now - st.last_event_time
            if dt > 0:
                st.queue_area += len(st.queue) * dt
            st.last_event_time = now

        # busy-time accounting is tracked directly via busy intervals
        busy_start: Dict[str, Optional[float]] = {mid: None for mid in stations}

        while events:
            now, _, kind, payload = heapq.heappop(events)
            if now > duration_hr:
                break

            if kind == "EXTERNAL_ARRIVAL":
                mid = payload
                enqueue(mid, now)

                # schedule next external arrival
                if arrival_rate_uph > 0:
                    nxt = now + rng.expovariate(arrival_rate_uph)
                    schedule(nxt, "EXTERNAL_ARRIVAL", first_id)

            elif kind == "SERVICE_END":
                mid, forward_after = payload
                st = stations[mid]
                advance_queue_area(st, now)
                st.completions += 1
                if busy_start[mid] is not None:
                    st.busy_time_accum += now - busy_start[mid]
                    busy_start[mid] = None
                st.busy_until = None

                # start next unit at this station if any waiting
                if st.queue:
                    busy_start[mid] = now
                maybe_start_service(mid, now)

                # route the completed unit onward to its logical next
                # station (which may differ from `mid`'s own normal
                # successor if `mid` was standing in for a redirected
                # station), resolving any further redirects along the way
                if forward_after is not None:
                    enqueue(forward_after, now)

        # close out queue-area integration to the end of the horizon
        for mid, st in stations.items():
            if st.last_event_time < duration_hr:
                st.queue_area += len(st.queue) * (duration_hr - st.last_event_time)
                if busy_start[mid] is not None:
                    st.busy_time_accum += duration_hr - busy_start[mid]
                st.last_event_time = duration_hr

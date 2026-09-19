"""
Mock/fake implementations of the interfaces Layer 4 depends on.

These exist ONLY so Layer 4 can be run and demonstrated standalone before
Layers 1, 2A, 2B and 3 are built. Replace with real adapters when those
layers exist — nothing in `layer4/` besides `demo.py` should import this
module.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional

from .models import (
    BottleneckInfo,
    DigitalTwinState,
    MachineHealthEvent,
    MachineState,
    WhatIfResult,
)

_scenario_ids = itertools.count(1)


class InMemoryMachineStateProvider:
    def __init__(self, states: Dict[str, MachineState]):
        self._states = states

    def get_state(self, machine_id: str) -> Optional[MachineState]:
        return self._states.get(machine_id)

    def find_candidates(self, machine_types: List[str]) -> List[MachineState]:
        return [s for s in self._states.values() if s.machine_type in machine_types]

    def set_status(self, machine_id: str, status) -> None:
        if machine_id in self._states:
            self._states[machine_id].status = status


class InMemoryHealthEventProvider:
    def __init__(self, events: Dict[str, MachineHealthEvent]):
        self._events = events

    def get_latest(self, machine_id: str) -> Optional[MachineHealthEvent]:
        return self._events.get(machine_id)


class InMemoryDigitalTwinProvider:
    def __init__(
        self,
        twin_states: Dict[str, DigitalTwinState],
        bottleneck: Optional[BottleneckInfo] = None,
    ):
        self._twin_states = twin_states
        self._bottleneck = bottleneck

    def get_twin_state(self, machine_id: str) -> Optional[DigitalTwinState]:
        return self._twin_states.get(machine_id)

    def get_bottleneck_info(self) -> Optional[BottleneckInfo]:
        return self._bottleneck


class SimpleWhatIfClient:
    """Deterministic stand-in for Layer 3's what-if simulator: feasible
    whenever the candidate machine's queue/load are healthy, matching the
    same thresholds config would use, plus a small throughput note."""

    def __init__(self, digital_twin: InMemoryDigitalTwinProvider, max_queue: int, max_load: float):
        self._twin = digital_twin
        self._max_queue = max_queue
        self._max_load = max_load

    def run_whatif(self, source_machine_id: str, candidate_machine_id: str) -> WhatIfResult:
        scenario_id = f"WI-{next(_scenario_ids):05d}"
        twin = self._twin.get_twin_state(candidate_machine_id)
        feasible = bool(
            twin is not None
            and twin.queue_length <= self._max_queue
            and twin.current_load <= self._max_load
        )
        return WhatIfResult(
            scenario_id=scenario_id,
            source_machine_id=source_machine_id,
            candidate_machine_id=candidate_machine_id,
            feasible=feasible,
            projected_throughput_change_pct=-8.5 if feasible else None,
            projected_impact_notes=(
                "Short-term throughput dip expected during handover."
                if feasible
                else "Candidate machine at or above safe queue/load threshold."
            ),
        )


class ConsoleOperatorNotifier:
    """Real deployment would push to a UI/paging system; this just prints."""

    def notify_fault(self, machine_id: str, fault_type: str, deadline: str) -> None:
        print(f"[OPERATOR ALERT] {machine_id}: fault '{fault_type}'. Correct by {deadline}.")

    def notify_recovery_outcome(self, machine_id: str, summary: str) -> None:
        print(f"[OPERATOR UPDATE] {machine_id}: {summary}")

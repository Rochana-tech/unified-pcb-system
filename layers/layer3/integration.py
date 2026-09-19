"""
Layer 3 - Integration Interface
================================
Receives events from Layer 1, Layer 2A (ANN), and Layer 2B (ML) and
fuses them into a single CombinedMachineCondition per machine.

This module has exactly ONE job: fuse the three input streams into the
shape described in the spec, e.g.

    {
      "machine_id": "M4",
      "fault_status": "FAULT",
      "fault_type": "MECHANICAL/BEARING FAULT",
      "health_status": "DEGRADED"
    }

It does NOT compute utilization/throughput/bottlenecks - that is the
DigitalTwin's job (digital_twin.py), which consumes this fused output.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Dict

from .models import (
    FaultEvent,
    MachineHealthEvent,
    MachineState,
    CombinedMachineCondition,
    FaultStatus,
    HealthStatus,
    MachineStatus,
)

DEFAULT_STALE_AFTER = timedelta(seconds=60)


class IntegrationService:
    """
    Thread-safe "latest value wins" store + fuser for the three input
    streams described in the spec.

    Usage
    -----
        integ = IntegrationService()
        integ.ingest_machine_state(state)      # Layer 1
        integ.ingest_fault_event(fault)        # Layer 2A (ANN)
        integ.ingest_health_event(health)      # Layer 2B (ML)

        condition = integ.get_combined_condition("M4")
    """

    def __init__(self, stale_after: timedelta = DEFAULT_STALE_AFTER):
        self._lock = RLock()
        self._stale_after = stale_after
        self._faults: Dict[str, FaultEvent] = {}
        self._health: Dict[str, MachineHealthEvent] = {}
        self._states: Dict[str, MachineState] = {}

    # -- ingestion (one call per source, per event) ---------------------

    def ingest_fault_event(self, event: FaultEvent) -> None:
        with self._lock:
            self._faults[event.machine_id] = event

    def ingest_health_event(self, event: MachineHealthEvent) -> None:
        with self._lock:
            self._health[event.machine_id] = event

    def ingest_machine_state(self, state: MachineState) -> None:
        with self._lock:
            self._states[state.machine_id] = state

    # -- fusion -----------------------------------------------------------

    def get_combined_condition(self, machine_id: str) -> CombinedMachineCondition:
        with self._lock:
            state = self._states.get(machine_id)
            fault = self._faults.get(machine_id)
            health = self._health.get(machine_id)

            now = datetime.now(timezone.utc)
            timestamps = [e.timestamp for e in (state, fault, health) if e is not None]

            # Controller freshness is independent of optional ANN/health streams.
            stale = state is None or (now - state.timestamp) > self._stale_after
            if fault and (now - fault.timestamp) > self._stale_after:
                fault = None
            if health and (now - health.timestamp) > self._stale_after:
                health = None

            return CombinedMachineCondition(
                machine_id=machine_id,
                machine_status=state.status if state else MachineStatus.UNKNOWN,
                fault_status=fault.fault_status if fault else FaultStatus.UNKNOWN,
                fault_type=fault.fault_type if fault else None,
                health_status=health.health_status if health else HealthStatus.UNKNOWN,
                health_score=health.health_score if health else None,
                queue_length=state.queue_length if state else 0,
                capacity_units_per_hour=state.capacity_units_per_hour if state else None,
                processing_time_sec=state.cycle_time_sec if state else None,
                last_updated=state.timestamp if state else now,
                stale=stale,
            )

    def get_all_combined_conditions(self) -> Dict[str, CombinedMachineCondition]:
        """Fuse every machine_id seen from any of the three sources."""
        with self._lock:
            machine_ids = set(self._states) | set(self._faults) | set(self._health)
        return {mid: self.get_combined_condition(mid) for mid in machine_ids}

    def raw_machine_state(self, machine_id: str) -> MachineState | None:
        with self._lock:
            return self._states.get(machine_id)

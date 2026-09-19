"""
Layer 3 - Digital Twin
======================
Represents the production line as machines connected in production
sequence, and maintains a live, continuously-updated picture of each
machine combining:

  - Layer 1 production data (via IntegrationService / MachineState)
  - Layer 2A ANN fault information
  - Layer 2B ML machine-health information

Tracked per machine:
  status, capacity, processing time, utilization, queue length,
  throughput, availability, health, fault/degradation state.

This module holds LIVE state only. What-if simulation (simulation.py)
never mutates any object owned by this module - it only reads a snapshot.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Deque, Dict, List, Optional, Tuple

from .config import LineConfig, MachineSpec
from .integration import IntegrationService
from .models import (
    CombinedMachineCondition,
    FaultStatus,
    HealthStatus,
    MachineStatus,
)

_HISTORY_LEN = 50  # samples kept for trend/growth calculations


@dataclass
class MachineMetrics:
    """Live, derived metrics for a single machine (Layer 3 output shape)."""
    machine_id: str
    name: str
    sequence: int

    machine_status: MachineStatus = MachineStatus.UNKNOWN
    fault_status: FaultStatus = FaultStatus.UNKNOWN
    fault_type: Optional[str] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_score: Optional[float] = None

    capacity_units_per_hour: float = 0.0        # nominal (design) capacity
    effective_capacity_units_per_hour: float = 0.0  # capacity after health/fault derate
    processing_time_sec: float = 0.0
    queue_length: int = 0
    throughput_units_per_hour: float = 0.0
    utilization: float = 0.0                    # 0..1 (throughput / effective capacity)
    availability: float = 1.0                   # 0..1 (fraction of time not DOWN)
    queue_growth_rate: float = 0.0               # units of queue / sample step

    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = True

    # internal history (not serialized)
    _queue_history: Deque[int] = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN), repr=False)
    _units_history: Deque[Tuple[datetime, int]] = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN), repr=False)
    _status_history: Deque[bool] = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN), repr=False)  # True=running/available

    def to_dict(self) -> Dict:
        d = {
            "machine_id": self.machine_id,
            "name": self.name,
            "sequence": self.sequence,
            "machine_status": self.machine_status.value,
            "fault_status": self.fault_status.value,
            "fault_type": self.fault_type,
            "health_status": self.health_status.value,
            "health_score": self.health_score,
            "capacity_units_per_hour": round(self.capacity_units_per_hour, 2),
            "effective_capacity_units_per_hour": round(self.effective_capacity_units_per_hour, 2),
            "processing_time_sec": self.processing_time_sec,
            "queue_length": self.queue_length,
            "throughput_units_per_hour": round(self.throughput_units_per_hour, 2),
            "utilization": round(self.utilization, 4),
            "availability": round(self.availability, 4),
            "queue_growth_rate": round(self.queue_growth_rate, 4),
            "last_updated": self.last_updated.isoformat(),
            "stale": self.stale,
        }
        return d


# Derating applied to effective capacity based on fused health/fault state.
# Kept simple & explicit (no hidden "AI" heuristics) - Layer 4 / policy owners
# can retune these constants without touching the twin's mechanics.
_HEALTH_CAPACITY_FACTOR = {
    HealthStatus.HEALTHY: 1.0,
    HealthStatus.DEGRADED: 0.7,
    HealthStatus.CRITICAL: 0.35,
    HealthStatus.UNKNOWN: 1.0,
}


def _capacity_derate(health_status: HealthStatus, fault_status: FaultStatus) -> float:
    factor = _HEALTH_CAPACITY_FACTOR.get(health_status, 1.0)
    if fault_status == FaultStatus.FAULT:
        factor = min(factor, 0.5)
    return factor


class DigitalTwin:
    """
    Live representation of one production line.

    The twin is fed by an IntegrationService (fused Layer1+2A+2B data).
    Call `refresh()` periodically (e.g. on a timer, or once per new
    Layer-1 sample) to pull the latest fused conditions and recompute
    derived metrics (utilization, throughput, availability, queue growth).
    """

    def __init__(self, line_config: LineConfig, integration: IntegrationService):
        self._lock = RLock()
        self.line_config = line_config
        self.integration = integration
        self._metrics: Dict[str, MachineMetrics] = {
            spec.machine_id: MachineMetrics(
                machine_id=spec.machine_id,
                name=spec.name,
                sequence=spec.sequence,
                capacity_units_per_hour=spec.default_capacity_uph,
                effective_capacity_units_per_hour=spec.default_capacity_uph,
                processing_time_sec=spec.default_processing_time_sec,
            )
            for spec in line_config.machines
        }

    # -- refresh / update ------------------------------------------------

    def refresh(self, machine_id: Optional[str] = None) -> None:
        """Pull latest fused condition(s) and recompute derived metrics."""
        ids = [machine_id] if machine_id else list(self._metrics.keys())
        with self._lock:
            for mid in ids:
                condition = self.integration.get_combined_condition(mid)
                self._apply_condition(mid, condition)

    def _apply_condition(self, machine_id: str, c: CombinedMachineCondition) -> None:
        m = self._metrics.get(machine_id)
        if m is None:
            return  # machine not part of this line's topology

        spec = self.line_config.get(machine_id)
        now = datetime.now(timezone.utc)

        m.machine_status = c.machine_status
        m.fault_status = c.fault_status
        m.fault_type = c.fault_type
        m.health_status = c.health_status
        m.health_score = c.health_score
        m.queue_length = c.queue_length
        m.last_updated = c.last_updated
        m.stale = c.stale

        if c.processing_time_sec:
            m.processing_time_sec = c.processing_time_sec
        nominal_capacity = c.capacity_units_per_hour if c.capacity_units_per_hour is not None else (spec.default_capacity_uph if spec else m.capacity_units_per_hour)
        m.capacity_units_per_hour = nominal_capacity

        derate = _capacity_derate(m.health_status, m.fault_status)
        m.effective_capacity_units_per_hour = nominal_capacity * derate
        if m.processing_time_sec > 0:
            m.effective_capacity_units_per_hour = min(m.effective_capacity_units_per_hour, 3600 / m.processing_time_sec)
        if m.machine_status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE) or m.stale:
            m.effective_capacity_units_per_hour = 0.0
        raw_state = self.integration.raw_machine_state(machine_id)
        if raw_state is None or (m._units_history and raw_state.timestamp <= m._units_history[-1][0]):
            return
        if m._units_history and raw_state.units_processed_total < m._units_history[-1][1]:
            m._units_history.clear()
            m.throughput_units_per_hour = 0.0

        # -- queue growth trend --
        m._queue_history.append(m.queue_length)
        if len(m._queue_history) >= 2:
            span = len(m._queue_history) - 1
            m.queue_growth_rate = (m._queue_history[-1] - m._queue_history[0]) / span
        else:
            m.queue_growth_rate = 0.0

        # -- throughput from Layer1's monotonic units counter --
        raw_state = self.integration.raw_machine_state(machine_id)
        if raw_state is not None:
            m._units_history.append((raw_state.timestamp, raw_state.units_processed_total))
            if len(m._units_history) >= 2:
                (t0, u0), (t1, u1) = m._units_history[0], m._units_history[-1]
                dt_hr = (t1 - t0).total_seconds() / 3600.0
                if dt_hr > 0:
                    m.throughput_units_per_hour = max(0.0, (u1 - u0) / dt_hr)

        # -- availability from status history (RUNNING/IDLE = available) --
        available_now = m.machine_status not in (MachineStatus.DOWN, MachineStatus.MAINTENANCE)
        m._status_history.append(available_now)
        if m._status_history:
            m.availability = sum(m._status_history) / len(m._status_history)

        # -- utilization = demand met vs. what the machine could do now --
        if m.effective_capacity_units_per_hour > 0:
            m.utilization = min(1.0, m.throughput_units_per_hour / m.effective_capacity_units_per_hour)
        else:
            m.utilization = 0.0

    # -- read access -------------------------------------------------------

    def get_machine_metrics(self, machine_id: str) -> Optional[MachineMetrics]:
        with self._lock:
            return self._metrics.get(machine_id)

    def get_all_metrics(self) -> Dict[str, MachineMetrics]:
        """Shallow snapshot dict of current MachineMetrics, keyed by machine_id."""
        with self._lock:
            return dict(self._metrics)

    def get_line_snapshot(self) -> Dict:
        """Full point-in-time state of the line, ordered by sequence."""
        with self._lock:
            ordered = sorted(self._metrics.values(), key=lambda m: m.sequence)
            return {
                "line_name": self.line_config.line_name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "machines": [m.to_dict() for m in ordered],
            }

    def get_topology(self) -> List[str]:
        return self.line_config.machine_ids_in_order()

    def clone_metrics_for_simulation(self) -> Dict[str, MachineMetrics]:
        """
        Deep-enough copy of current metrics for the What-If simulator.
        The simulator must NEVER receive (and thus never mutate) the live
        MachineMetrics objects held by this twin.
        """
        import copy
        with self._lock:
            return {mid: copy.deepcopy(m) for mid, m in self._metrics.items()}

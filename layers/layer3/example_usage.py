"""
End-to-end example / smoke test.

Simulates:
  - Layer 1 pushing MachineState telemetry for all 5 machines
  - Layer 2A (ANN) flagging M4 with a bearing fault
  - Layer 2B (ML) scoring M4 as DEGRADED, and slowly building queue at M3

Then demonstrates:
  1. The combined machine condition (the exact shape from the spec)
  2. A full live digital twin snapshot
  3. Bottleneck ranking (multi-factor, not utilization-only)
  4. Two isolated what-if scenarios, proving live state is untouched
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from digital_twin_layer3 import (
    ELECTRONICS_LINE,
    FaultEvent,
    FaultStatus,
    HealthStatus,
    MachineHealthEvent,
    MachineState,
    MachineStatus,
    ProductionLineService,
)


def _ts(offset_sec: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_sec)


def seed_layer1(service: ProductionLineService) -> None:
    """Feed a short synthetic time series so throughput/availability/queue
    growth have something to compute from."""
    base_units = {"M1": 0, "M2": 0, "M3": 0, "M4": 0, "M5": 0}
    base_queue = {"M1": 2, "M2": 3, "M3": 4, "M4": 6, "M5": 1}

    step_minutes = 5
    for step in range(6):
        for spec in ELECTRONICS_LINE.machines:
            mid = spec.machine_id
            # M3 queue climbs steadily -> should show up in queue_growth_rate
            queue = base_queue[mid] + (step * 3 if mid == "M3" else step)
            # units accumulate at roughly the machine's nominal rate per step
            units = base_units[mid] + step * (spec.default_capacity_uph * step_minutes / 60.0)
            status = MachineStatus.RUNNING
            service.ingest_machine_state(
                MachineState(
                    machine_id=mid,
                    status=status,
                    cycle_time_sec=spec.default_processing_time_sec,
                    units_processed_total=int(units),
                    queue_length=int(queue),
                    capacity_units_per_hour=spec.default_capacity_uph,
                    timestamp=_ts(step * step_minutes * 60),
                )
            )
        service.refresh()


def seed_layer2(service: ProductionLineService) -> None:
    """Layer 2A (ANN) + Layer 2B (ML) events for M4."""
    service.ingest_fault_event(
        FaultEvent(
            machine_id="M4",
            fault_status=FaultStatus.FAULT,
            fault_type="MECHANICAL/BEARING FAULT",
            confidence=0.93,
        )
    )
    service.ingest_health_event(
        MachineHealthEvent(
            machine_id="M4",
            health_status=HealthStatus.DEGRADED,
            health_score=0.42,
            remaining_useful_life_hr=120,
        )
    )
    # Healthy baseline for the rest of the line
    for mid in ("M1", "M2", "M3", "M5"):
        service.ingest_health_event(
            MachineHealthEvent(machine_id=mid, health_status=HealthStatus.HEALTHY, health_score=0.95)
        )
        service.ingest_fault_event(FaultEvent(machine_id=mid, fault_status=FaultStatus.OK))
    service.refresh()


def main():
    service = ProductionLineService(ELECTRONICS_LINE)

    seed_layer1(service)
    seed_layer2(service)

    print("=" * 70)
    print("1) COMBINED MACHINE CONDITION (M4) — spec's target shape")
    print("=" * 70)
    print(json.dumps(service.get_combined_condition("M4"), indent=2))

    print("\n" + "=" * 70)
    print("2) LIVE DIGITAL TWIN SNAPSHOT")
    print("=" * 70)
    print(json.dumps(service.get_line_snapshot(), indent=2))

    print("\n" + "=" * 70)
    print("3) BOTTLENECK RANKING (multi-factor)")
    print("=" * 70)
    print(json.dumps(service.get_bottleneck_ranking(), indent=2))
    print("\nPrimary bottleneck:", json.dumps(service.get_primary_bottleneck(), indent=2))

    before = service.get_line_snapshot()

    print("\n" + "=" * 70)
    print("4a) WHAT-IF: M4 becomes UNAVAILABLE")
    print("=" * 70)
    result_unavailable = service.run_what_if(
        scenario_name="M4_unavailable_8h",
        kind="UNAVAILABLE",
        affected_machine_id="M4",
        duration_hr=8.0,
        seed=7,
    )
    print(json.dumps(result_unavailable, indent=2))

    print("\n" + "=" * 70)
    print("4b) WHAT-IF: shift M4's workload to M3 (compatible alternate)")
    print("=" * 70)
    result_shift = service.run_what_if(
        scenario_name="M4_shift_to_M3_8h",
        kind="SHIFT_WORKLOAD",
        affected_machine_id="M4",
        shift_to_machine_id="M3",
        duration_hr=8.0,
        seed=7,
    )
    print(json.dumps(result_shift, indent=2))

    after = service.get_line_snapshot()
    assert before["machines"] == after["machines"], "Live twin state must be unaffected by what-if simulation!"
    print("\n[OK] Live Digital Twin machine state is IDENTICAL before and after what-if runs.")


if __name__ == "__main__":
    main()

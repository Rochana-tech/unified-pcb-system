"""
Layer 3 - Layer 4 Facing Interfaces
====================================
A thin, stable facade over IntegrationService + DigitalTwin +
BottleneckDetector + WhatIfSimulator so Layer 4 only needs to know about
this one module.

Everything returned here is plain dict/JSON-serializable data - no
internal objects leak out.

Explicitly OUT of scope (per spec): no recovery/scheduler decisions, no
AI-generated explanations, no dashboard/UI, no developer workspace.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .bottleneck import BottleneckDetector
from .config import LineConfig
from .digital_twin import DigitalTwin
from .integration import IntegrationService
from .models import FaultEvent, MachineHealthEvent, MachineState
from .simulation import ScenarioKind, ScenarioSpec, WhatIfSimulator


class ProductionLineService:
    """
    One instance per physical production line (e.g. one for the
    electronics line, one for the automobile line).
    """

    def __init__(self, line_config: LineConfig, bottleneck_threshold: Optional[float] = None):
        self.line_config = line_config
        self.integration = IntegrationService()
        self.twin = DigitalTwin(line_config, self.integration)
        self.bottleneck_detector = (
            BottleneckDetector(threshold=bottleneck_threshold)
            if bottleneck_threshold is not None
            else BottleneckDetector()
        )

    # -- ingestion passthroughs (Layer 1 / 2A / 2B -> here) ------------------

    def ingest_fault_event(self, event: FaultEvent) -> None:
        self.integration.ingest_fault_event(event)

    def ingest_health_event(self, event: MachineHealthEvent) -> None:
        self.integration.ingest_health_event(event)

    def ingest_machine_state(self, state: MachineState) -> None:
        self.integration.ingest_machine_state(state)

    def refresh(self) -> None:
        """Recompute the twin's derived metrics from latest ingested events."""
        self.twin.refresh()

    # -- Layer 4 read interface: combined condition --------------------------

    def get_combined_condition(self, machine_id: str) -> Dict:
        """
        Returns the fused Layer1+2A+2B condition, e.g.:
        {"machine_id": "M4", "fault_status": "FAULT",
         "fault_type": "MECHANICAL/BEARING FAULT", "health_status": "DEGRADED", ...}
        """
        return self.integration.get_combined_condition(machine_id).to_dict()

    def get_all_combined_conditions(self) -> Dict[str, Dict]:
        return {mid: c.to_dict() for mid, c in self.integration.get_all_combined_conditions().items()}

    # -- Layer 4 read interface: Digital Twin --------------------------------

    def get_line_snapshot(self) -> Dict:
        """Full live state of the line: status, capacity, processing time,
        utilization, queue length, throughput, availability, health, fault."""
        return self.twin.get_line_snapshot()

    def get_machine_snapshot(self, machine_id: str) -> Optional[Dict]:
        m = self.twin.get_machine_metrics(machine_id)
        return m.to_dict() if m else None

    def get_topology(self) -> List[str]:
        return self.twin.get_topology()

    # -- Layer 4 read interface: bottleneck ----------------------------------

    def get_bottleneck_ranking(self) -> List[Dict]:
        """All machines ranked by composite bottleneck score, highest first."""
        metrics = self.twin.get_all_metrics()
        return [r.to_dict() for r in self.bottleneck_detector.detect(metrics)]

    def get_primary_bottleneck(self) -> Optional[Dict]:
        """The single flagged bottleneck, if any machine crosses the threshold."""
        metrics = self.twin.get_all_metrics()
        result = self.bottleneck_detector.primary_bottleneck(metrics)
        return result.to_dict() if result else None

    # -- Layer 4 read interface: what-if simulation --------------------------

    def run_what_if(
        self,
        scenario_name: str,
        kind: str,
        affected_machine_id: str,
        factor: Optional[float] = None,
        shift_to_machine_id: Optional[str] = None,
        duration_hr: float = 8.0,
        arrival_rate_uph: Optional[float] = None,
        seed: int = 42,
    ) -> Dict:
        """
        Run an isolated what-if simulation. Never touches live twin state -
        operates on a snapshot copy only.

        `kind` one of: "DEGRADED", "UNAVAILABLE", "REDUCED_CAPACITY",
                        "INCREASED_PROCESSING_TIME", "SHIFT_WORKLOAD"
        """
        scenario = ScenarioSpec(
            name=scenario_name,
            kind=ScenarioKind(kind),
            affected_machine_id=affected_machine_id,
            factor=factor,
            shift_to_machine_id=shift_to_machine_id,
        )
        snapshot = self.twin.clone_metrics_for_simulation()
        simulator = WhatIfSimulator(snapshot, self.twin.get_topology())
        result = simulator.run(
            scenario,
            duration_hr=duration_hr,
            arrival_rate_uph=arrival_rate_uph,
            seed=seed,
        )
        return result.to_dict()

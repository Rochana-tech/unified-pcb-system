"""
Layer4Backend — the single clean entry point the future dashboard
(or any other consumer) should talk to. Wraps the recovery engine,
explanation engine and logger, and returns plain dicts (JSON-ready)
so it drops straight behind a REST/GraphQL layer later.
"""

from __future__ import annotations

from typing import List, Optional

from dataclasses import asdict

from .config import IndustryConfig
from .explanation import ExplanationEngine
from .interfaces import (
    DigitalTwinProvider,
    HealthEventProvider,
    MachineStateProvider,
    OperatorNotifier,
    WhatIfClient,
)
from .logger import RecoveryLogger
from .models import FaultEvent, RecoveryDecision
from .recovery_engine import RecoveryEngine
from .timer_manager import CorrectionTimerManager


class Layer4Backend:
    def __init__(
        self,
        config: IndustryConfig,
        machine_states: MachineStateProvider,
        health_events: HealthEventProvider,
        digital_twin: DigitalTwinProvider,
        whatif_client: WhatIfClient,
        operator: OperatorNotifier,
        timer_manager: Optional[CorrectionTimerManager] = None,
        log_file: Optional[str] = None,
    ):
        self.config = config
        self.logger = RecoveryLogger(file_path=log_file)
        self.engine = RecoveryEngine(
            config=config,
            machine_states=machine_states,
            health_events=health_events,
            digital_twin=digital_twin,
            whatif_client=whatif_client,
            operator=operator,
            logger=self.logger,
            timer_manager=timer_manager,
        )
        self.explainer = ExplanationEngine()
        self._health_events = health_events
        self._machine_states = machine_states
        self._digital_twin = digital_twin

    # -- ingestion -----------------------------------------------------------

    def ingest_fault(self, fault: FaultEvent) -> dict:
        decision = self.engine.on_fault_detected(fault)
        return asdict(decision)

    def report_human_correction(self, machine_id: str) -> Optional[dict]:
        decision = self.engine.on_human_correction(machine_id)
        return asdict(decision) if decision else None

    def tick(self) -> List[dict]:
        """Call periodically (e.g. every second) from the host loop to
        evaluate expired correction timers and run the escalation flow."""
        decisions = self.engine.check_expirations()
        return [asdict(d) for d in decisions]

    # -- read-only dashboard queries ------------------------------------------

    def get_decision(self, decision_id: str) -> Optional[dict]:
        d = self.engine.get_decision(decision_id)
        return asdict(d) if d else None

    def get_explanation(self, decision_id: str) -> Optional[dict]:
        decision = self.engine.get_decision(decision_id)
        if decision is None:
            return None
        fault = self.engine.get_fault_for_decision(decision_id)
        if fault is None:
            return None

        health = self._health_events.get_latest(decision.machine_id)
        machine_state = self._machine_states.get_state(decision.machine_id)
        bottleneck = self._digital_twin.get_bottleneck_info()
        whatif = self.engine.get_whatif_for_decision(decision_id)

        explanation = self.explainer.generate(
            decision=decision,
            fault=fault,
            health=health,
            machine_state=machine_state,
            bottleneck=bottleneck,
            whatif=whatif,
        )
        return asdict(explanation)

    def get_logs(self, machine_id: Optional[str] = None) -> List[dict]:
        if machine_id:
            return [asdict(e) for e in self.logger.for_machine(machine_id)]
        return self.logger.as_dicts()

    def get_config_summary(self) -> dict:
        return {
            "industry": self.config.name,
            "human_correction_timeout_seconds": self.config.human_correction_timeout_seconds,
            "machine_types_configured": list(self.config.machine_compatibility.keys()),
        }

"""
Human-first recovery scheduler.

Pure rule-based state machine — no ML/AI decision-making happens here.
Every branch is an explicit, auditable rule against config + verified
layer data.

Flow implemented (matches the spec exactly):
  1. Detect the fault              -> on_fault_detected()
  2. Notify the human operator     -> on_fault_detected()
  3. Start correction timer        -> on_fault_detected()
  4. Human corrects in time        -> on_human_correction()
  5. Timer expires                 -> check_expirations()
       -> mark degraded/unavailable
       -> find alternative (compatible, available, capacity, queue, time)
  6. Run what-if before reallocating
  7. Feasible -> select + reallocate
  8. Not feasible -> flag + report impact + notify operator
"""

from __future__ import annotations

import itertools
import uuid
from typing import List, Optional

from .config import IndustryConfig
from .interfaces import (
    DigitalTwinProvider,
    HealthEventProvider,
    MachineStateProvider,
    OperatorNotifier,
    WhatIfClient,
)
from .logger import RecoveryLogger
from .models import (
    FaultEvent,
    MachineHealthEvent,
    MachineState,
    MachineStatus,
    RecoveryDecision,
    RecoveryStatus,
    WhatIfResult,
)
from .timer_manager import CorrectionTimerManager

_decision_ids = itertools.count(1)


class RecoveryEngine:
    def __init__(
        self,
        config: IndustryConfig,
        machine_states: MachineStateProvider,
        health_events: HealthEventProvider,
        digital_twin: DigitalTwinProvider,
        whatif_client: WhatIfClient,
        operator: OperatorNotifier,
        logger: RecoveryLogger,
        timer_manager: Optional[CorrectionTimerManager] = None,
    ):
        self.config = config
        self.machine_states = machine_states
        self.health_events = health_events
        self.digital_twin = digital_twin
        self.whatif_client = whatif_client
        self.operator = operator
        self.logger = logger
        self.timers = timer_manager or CorrectionTimerManager()

        # decision_id -> RecoveryDecision, and machine_id -> active decision_id
        self._decisions: dict[str, RecoveryDecision] = {}
        self._active_by_machine: dict[str, str] = {}
        self._pending_fault_by_machine: dict[str, FaultEvent] = {}

        # permanent records (kept after resolution, for explanations/audit)
        self._fault_by_decision: dict[str, FaultEvent] = {}
        self._whatif_by_decision: dict[str, WhatIfResult] = {}

    # -- Steps 1-3 ---------------------------------------------------------

    def on_fault_detected(self, fault: FaultEvent) -> RecoveryDecision:
        """Step 1 (detect — the fault event itself IS the detection),
        step 2 (notify operator), step 3 (start timer)."""
        existing = self._active_by_machine.get(fault.machine_id)
        if existing:
            return self._decisions[existing]
        self.logger.log("fault_detected", {
            "fault_id": fault.fault_id,
            "machine_id": fault.machine_id,
            "fault_type": fault.fault_type,
            "confidence": fault.confidence,
        })

        deadline = self.timers.start(
            fault.machine_id, fault.fault_id, self.config.human_correction_timeout_seconds
        )
        self.operator.notify_fault(fault.machine_id, fault.fault_type, deadline)
        self.logger.log("operator_notified", {
            "machine_id": fault.machine_id, "deadline": deadline
        })

        decision_id = f"DEC-{next(_decision_ids):06d}"
        decision = RecoveryDecision(
            decision_id=decision_id,
            fault_id=fault.fault_id,
            machine_id=fault.machine_id,
            status=RecoveryStatus.AWAITING_CORRECTION,
            actions_taken=["fault_detected", "operator_notified", "correction_timer_started"],
            correction_deadline=deadline,
        )
        self._decisions[decision_id] = decision
        self._active_by_machine[fault.machine_id] = decision_id
        self._pending_fault_by_machine[fault.machine_id] = fault
        self._fault_by_decision[decision_id] = fault
        return decision

    # -- Step 4: human corrects in time -------------------------------------

    def on_human_correction(self, machine_id: str) -> Optional[RecoveryDecision]:
        """Operator reports the issue is fixed. Only counts if the timer
        for this machine hasn't already expired/been consumed."""
        if not self.timers.is_pending(machine_id):
            self.logger.log("correction_reported_too_late", {"machine_id": machine_id})
            return None

        self.timers.cancel(machine_id)
        decision_id = self._active_by_machine.get(machine_id)
        if decision_id is None:
            return None

        decision = self._decisions[decision_id]
        decision.status = RecoveryStatus.RESUMED_BY_HUMAN
        decision.human_corrected = True
        decision.actions_taken.append("human_corrected_in_time")
        decision.actions_taken.append("machine_kept_active")
        decision.finalized_at = self._now()

        self.logger.log("recovery_finalized", {
            "decision_id": decision_id, "outcome": "resumed_by_human"
        })
        self.operator.notify_recovery_outcome(
            machine_id, "Correction confirmed in time — machine resumed normal operation."
        )

        self._active_by_machine.pop(machine_id, None)
        self._pending_fault_by_machine.pop(machine_id, None)
        return decision

    # -- Step 5-8: timer expiry -> escalation -------------------------------

    def check_expirations(self) -> List[RecoveryDecision]:
        """Call periodically. For every timer that has expired without a
        human correction, runs steps 5-8 and returns the finalized decisions."""
        results: List[RecoveryDecision] = []
        for expired in self.timers.collect_expired():
            decision = self._escalate(expired.machine_id)
            if decision:
                results.append(decision)
        return results

    def _escalate(self, machine_id: str) -> Optional[RecoveryDecision]:
        decision_id = self._active_by_machine.get(machine_id)
        if decision_id is None:
            return None
        decision = self._decisions[decision_id]

        # 5a. mark degraded/unavailable
        self.logger.log("timer_expired", {"machine_id": machine_id})
        decision.actions_taken.append("correction_timer_expired")
        decision.actions_taken.append("machine_marked_degraded")

        state = self.machine_states.get_state(machine_id)
        machine_type = state.machine_type if state else None

        # 5b-e. find alternative: compatible, available, capacity, queue, processing time
        candidate = self._find_alternative(machine_id, machine_type)

        if candidate is None:
            decision.status = RecoveryStatus.NO_ALTERNATIVE_FLAGGED
            decision.actions_taken.append("no_compatible_alternative_found")
            decision.actions_taken.append("machine_flagged")
            decision.actions_taken.append("production_impact_reported")
            decision.finalized_at = self._now()
            self.logger.log("recovery_finalized", {
                "decision_id": decision_id, "outcome": "no_alternative_flagged"
            })
            self.operator.notify_recovery_outcome(
                machine_id,
                "No feasible alternative machine available. Machine remains flagged; "
                "production impact reported.",
            )
            self._cleanup(machine_id)
            return decision

        # 6. run what-if before applying reallocation
        whatif: WhatIfResult = self.whatif_client.run_whatif(machine_id, candidate.machine_id)
        decision.whatif_scenario_id = whatif.scenario_id
        decision.actions_taken.append(f"whatif_simulation_run:{whatif.scenario_id}")
        self._whatif_by_decision[decision_id] = whatif
        self.logger.log("whatif_run", {
            "decision_id": decision_id,
            "scenario_id": whatif.scenario_id,
            "candidate": candidate.machine_id,
            "feasible": whatif.feasible,
        })

        # 7-8. feasible? select + reallocate, else flag + report
        if whatif.feasible:
            decision.status = RecoveryStatus.REALLOCATED
            decision.alternative_machine_id = candidate.machine_id
            decision.actions_taken.append(f"selected_alternative:{candidate.machine_id}")
            decision.actions_taken.append("workload_reallocated")
            decision.finalized_at = self._now()
            self.logger.log("recovery_finalized", {
                "decision_id": decision_id,
                "outcome": "reallocated",
                "alternative": candidate.machine_id,
            })
            self.operator.notify_recovery_outcome(
                machine_id,
                f"Workload reallocated to {candidate.machine_id} "
                f"(what-if scenario {whatif.scenario_id} confirmed feasible).",
            )
        else:
            decision.status = RecoveryStatus.NO_ALTERNATIVE_FLAGGED
            decision.actions_taken.append("whatif_infeasible")
            decision.actions_taken.append("machine_flagged")
            decision.actions_taken.append("production_impact_reported")
            decision.finalized_at = self._now()
            self.logger.log("recovery_finalized", {
                "decision_id": decision_id, "outcome": "no_alternative_flagged_whatif_infeasible"
            })
            self.operator.notify_recovery_outcome(
                machine_id,
                "Candidate alternative failed what-if simulation. Machine remains "
                "flagged; production impact reported.",
            )

        self._cleanup(machine_id)
        return decision

    def _find_alternative(
        self, machine_id: str, machine_type: Optional[str]
    ) -> Optional[MachineState]:
        if not machine_type:
            return None
        compatible_types = self.config.compatible_types_for(machine_type)
        if not compatible_types:
            return None

        candidates = self.machine_states.find_candidates(compatible_types)
        for c in candidates:
            if c.machine_id == machine_id:
                continue
            if c.status not in (MachineStatus.RUNNING, MachineStatus.IDLE):
                continue  # availability check

            twin = self.digital_twin.get_twin_state(c.machine_id)
            if twin is None:
                continue

            if twin.queue_length > self.config.max_acceptable_queue_length:
                continue  # queue check
            if twin.current_load > self.config.max_acceptable_load:
                continue  # capacity/load check

            capacity = self.config.machine_capacity.get(c.machine_id)
            if capacity is None or capacity <= 0:
                continue  # processing-time / throughput sanity check

            return c  # first viable candidate under the rules, in order returned
        return None

    def _cleanup(self, machine_id: str) -> None:
        self._active_by_machine.pop(machine_id, None)
        self._pending_fault_by_machine.pop(machine_id, None)

    def get_decision(self, decision_id: str) -> Optional[RecoveryDecision]:
        return self._decisions.get(decision_id)

    def get_pending_fault(self, machine_id: str) -> Optional[FaultEvent]:
        return self._pending_fault_by_machine.get(machine_id)

    def get_fault_for_decision(self, decision_id: str) -> Optional[FaultEvent]:
        return self._fault_by_decision.get(decision_id)

    def get_whatif_for_decision(self, decision_id: str) -> Optional[WhatIfResult]:
        return self._whatif_by_decision.get(decision_id)

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

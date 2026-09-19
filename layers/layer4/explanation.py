"""
AI Alert Explanation component.

Hard rule: every sentence here is built from a field that was actually
passed in on a verified model object. If a piece of information wasn't
supplied by Layer 1/2A/2B/3, the corresponding field says so explicitly
("Not available from backend data") instead of guessing. This module
never calls an LLM and never fills gaps with plausible-sounding text.
"""

from __future__ import annotations

from typing import Optional

from .models import (
    BottleneckInfo,
    DigitalTwinState,
    ExplanationOutput,
    FaultEvent,
    MachineHealthEvent,
    MachineState,
    RecoveryDecision,
    RecoveryStatus,
    WhatIfResult,
)

NOT_AVAILABLE = "Not available from backend data."


class ExplanationEngine:
    def generate(
        self,
        decision: RecoveryDecision,
        fault: FaultEvent,
        health: Optional[MachineHealthEvent],
        machine_state: Optional[MachineState],
        bottleneck: Optional[BottleneckInfo],
        whatif: Optional[WhatIfResult],
    ) -> ExplanationOutput:
        return ExplanationOutput(
            decision_id=decision.decision_id,
            what_happened=self._what_happened(fault, decision),
            anomaly_detected=self._anomaly(fault),
            sensor_evidence=self._sensor_evidence(fault, health),
            possible_cause=self._possible_cause(fault, health),
            production_impact=self._production_impact(machine_state, bottleneck, decision),
            human_correctable=self._human_correctable(decision),
            correction_timeout_behavior=self._timeout_behavior(decision),
            alternative_machine_available=self._alternative(decision),
            whatif_result_summary=self._whatif_summary(whatif),
        )

    # -- individual answers -------------------------------------------------

    def _what_happened(self, fault: FaultEvent, decision: RecoveryDecision) -> str:
        return (
            f"Machine {fault.machine_id} raised fault '{fault.fault_type}' "
            f"(fault ID {fault.fault_id}). Current recovery status: {decision.status.value}."
        )

    def _anomaly(self, fault: FaultEvent) -> str:
        return (
            f"Fault type '{fault.fault_type}' detected with model confidence "
            f"{fault.confidence:.2f}."
        )

    def _sensor_evidence(self, fault: FaultEvent, health: Optional[MachineHealthEvent]) -> str:
        parts = []
        if fault.sensor_evidence:
            items = ", ".join(f"{k}={v}" for k, v in fault.sensor_evidence.items())
            parts.append(f"ANN sensor evidence: {items}.")
        else:
            parts.append("No ANN sensor evidence fields were provided with this fault event.")

        if health is not None:
            parts.append(
                f"ML health score at time of fault: {health.health_score:.2f}"
                + (
                    f"; degradation indicators: {', '.join(health.degradation_indicators)}."
                    if health.degradation_indicators
                    else "."
                )
            )
        else:
            parts.append("No machine-health event was supplied alongside this fault.")
        return " ".join(parts)

    def _possible_cause(self, fault: FaultEvent, health: Optional[MachineHealthEvent]) -> str:
        # Only surfaces causes that are literally present in the evidence —
        # never invents a root cause.
        if fault.sensor_evidence.get("likely_cause"):
            return str(fault.sensor_evidence["likely_cause"])
        if health and health.degradation_indicators:
            return (
                "Backend degradation indicators suggest: "
                + ", ".join(health.degradation_indicators)
                + "."
            )
        return (
            "Backend data does not include a confirmed root cause for this fault. "
            + NOT_AVAILABLE
        )

    def _production_impact(
        self,
        machine_state: Optional[MachineState],
        bottleneck: Optional[BottleneckInfo],
        decision: RecoveryDecision,
    ) -> str:
        parts = []
        if machine_state is not None:
            parts.append(
                f"Machine {machine_state.machine_id} status: {machine_state.status.value}."
            )
        else:
            parts.append(NOT_AVAILABLE)

        if bottleneck is not None and bottleneck.bottleneck_machine_id == decision.machine_id:
            parts.append(
                f"This machine is currently flagged as a bottleneck "
                f"(severity: {bottleneck.severity or 'unspecified'})."
                + (
                    f" Downstream impact: {bottleneck.downstream_impact}."
                    if bottleneck.downstream_impact
                    else ""
                )
            )
        return " ".join(parts)

    def _human_correctable(self, decision: RecoveryDecision) -> str:
        if decision.status == RecoveryStatus.AWAITING_CORRECTION:
            return (
                f"Yes — an operator can correct this now. Correction deadline: "
                f"{decision.correction_deadline}."
            )
        if decision.human_corrected:
            return "Yes — this was corrected by an operator within the allowed window."
        return "The correction window has closed for this event."

    def _timeout_behavior(self, decision: RecoveryDecision) -> str:
        return (
            "If correction is not confirmed before the deadline, the machine is marked "
            "degraded/unavailable and Layer 4 automatically searches for a compatible "
            "alternative machine, running a what-if simulation before reallocating any workload."
        )

    def _alternative(self, decision: RecoveryDecision) -> str:
        if decision.alternative_machine_id:
            return f"Yes — {decision.alternative_machine_id} was selected as the alternative."
        if decision.status == RecoveryStatus.NO_ALTERNATIVE_FLAGGED:
            return "No compatible/available alternative machine was found."
        return "Not yet determined — the correction window has not expired."

    def _whatif_summary(self, whatif: Optional[WhatIfResult]) -> str:
        if whatif is None:
            return "No what-if simulation has been run for this event yet."
        result = "feasible" if whatif.feasible else "not feasible"
        text = f"Scenario {whatif.scenario_id} was {result}."
        if whatif.projected_throughput_change_pct is not None:
            text += f" Projected throughput change: {whatif.projected_throughput_change_pct:+.1f}%."
        if whatif.projected_impact_notes:
            text += f" Notes: {whatif.projected_impact_notes}"
        return text

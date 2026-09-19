"""
Data contracts for Layer 4.

Everything Layer 4 knows about the world arrives as one of these objects.
Layer 4 never fabricates a field on these models — if a value is unknown,
it must be None / empty, and the explanation component is required to say
so rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Inputs from Layers 1, 2A, 2B, 3
# ---------------------------------------------------------------------------

class MachineStatus(str, Enum):
    RUNNING = "running"
    IDLE = "idle"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAULTED = "faulted"


@dataclass
class MachineState:
    """Layer 1 — current production state of a machine."""
    machine_id: str
    machine_type: str
    status: MachineStatus
    current_job_id: Optional[str] = None
    production_rate: Optional[float] = None
    timestamp: str = field(default_factory=_now)


@dataclass
class FaultEvent:
    """Layer 2A — ANN-based fault detection output."""
    fault_id: str
    machine_id: str
    fault_type: str
    confidence: float
    sensor_evidence: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)


@dataclass
class MachineHealthEvent:
    """Layer 2B — ML-based machine health output."""
    machine_id: str
    health_score: float  # 0.0 (failed) - 1.0 (healthy)
    degradation_indicators: list = field(default_factory=list)
    predicted_remaining_life_hours: Optional[float] = None
    timestamp: str = field(default_factory=_now)


@dataclass
class BottleneckInfo:
    """Layer 3 — bottleneck analysis for the production line."""
    bottleneck_machine_id: Optional[str]
    severity: Optional[str] = None  # e.g. "low" | "medium" | "high"
    downstream_impact: Optional[str] = None
    timestamp: str = field(default_factory=_now)


@dataclass
class DigitalTwinState:
    """Layer 3 — simulated/mirrored state of the production line."""
    machine_id: str
    twin_status: str
    queue_length: int
    current_load: float  # 0.0 - 1.0
    timestamp: str = field(default_factory=_now)


@dataclass
class WhatIfResult:
    """Layer 3 — result of a what-if simulation for a proposed reallocation."""
    scenario_id: str
    source_machine_id: str
    candidate_machine_id: str
    feasible: bool
    projected_throughput_change_pct: Optional[float] = None
    projected_impact_notes: Optional[str] = None
    timestamp: str = field(default_factory=_now)


# ---------------------------------------------------------------------------
# Layer 4 outputs
# ---------------------------------------------------------------------------

class RecoveryStatus(str, Enum):
    AWAITING_CORRECTION = "awaiting_correction"
    RESUMED_BY_HUMAN = "resumed_by_human"
    REALLOCATED = "reallocated"
    NO_ALTERNATIVE_FLAGGED = "no_alternative_flagged"


@dataclass
class RecoveryDecision:
    """The final, transparent decision record produced by the scheduler."""
    decision_id: str
    fault_id: str
    machine_id: str
    status: RecoveryStatus
    actions_taken: list = field(default_factory=list)
    alternative_machine_id: Optional[str] = None
    whatif_scenario_id: Optional[str] = None
    human_corrected: bool = False
    correction_deadline: Optional[str] = None
    created_at: str = field(default_factory=_now)
    finalized_at: Optional[str] = None


@dataclass
class ExplanationOutput:
    """
    Answers to the fixed set of operator-facing questions.
    Every field is populated ONLY from verified inputs that were actually
    passed in — never inferred or invented. Use None / "Not available from
    backend data" when a source layer didn't provide something.
    """
    decision_id: str
    what_happened: str
    anomaly_detected: str
    sensor_evidence: str
    possible_cause: str
    production_impact: str
    human_correctable: str
    correction_timeout_behavior: str
    alternative_machine_available: str
    whatif_result_summary: str
    generated_at: str = field(default_factory=_now)

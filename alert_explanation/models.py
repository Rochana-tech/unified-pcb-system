from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


Text = str
class SourceStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    STALE = "stale"


class Record(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")


class Alert(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    machine_id: str = Field(min_length=1, max_length=100)
    machine_name: str = Field(min_length=1, max_length=200)
    occurred_at: AwareDatetime
    severity: Literal["info", "warning", "critical", "unknown"] = "unknown"


class Source(StrictModel):
    status: SourceStatus = SourceStatus.MISSING
    reported_at: AwareDatetime | None = None
    machine_id: str | None = Field(default=None, max_length=100)


class Observation(Record):
    signal: str = Field(min_length=1, max_length=200)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=60)
    trend: Literal["increased", "decreased", "abnormal", "unchanged", "unknown"] = "unknown"
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def usable(self):
        if self.value is None and self.trend == "unknown" and not self.description:
            raise ValueError("An observation must contain a value, trend, or description")
        if self.value is not None and not self.unit:
            raise ValueError("A numeric observation requires an explicit unit, including count/dimensionless")
        return self


class DataAcquisition(Source):
    observations: list[Observation] = Field(default_factory=list, max_length=100)


class Anomaly(Record):
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    confidence_score: float | None = Field(default=None, ge=0, le=1)


class Cause(Record):
    label: str = Field(min_length=1, max_length=300)
    supporting_observation_ids: list[str] = Field(default_factory=list, max_length=100)


class ANNDetection(Source):
    model_name: str | None = Field(default=None, max_length=100)
    anomalies: list[Anomaly] = Field(default_factory=list, max_length=30)
    suspected_causes: list[Cause] = Field(default_factory=list, max_length=30)


class Fact(Record):
    description: str = Field(min_length=1, max_length=1500)


class DigitalTwin(Source):
    impacts: list[Fact] = Field(default_factory=list, max_length=30)


class DurationRange(StrictModel):
    minimum: float = Field(ge=0)
    maximum: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError("Repair-time minimum must not exceed maximum")
        return self


class HumanAssessment(Record):
    correction_possible: Literal["yes", "no", "unknown"] = "unknown"
    quick_correction: Literal["yes", "no", "unknown"] = "unknown"
    estimated_minutes: DurationRange | None = None
    estimate_basis: str | None = Field(default=None, max_length=1000)
    approved_actions: list[str] = Field(default_factory=list, max_length=20)
    # All actions must originate in approved backend maintenance guidance.

    @model_validator(mode="after")
    def coherent(self):
        if self.correction_possible == "no" and self.quick_correction == "yes":
            raise ValueError("Quick correction cannot be yes when correction is impossible")
        if any(not a.strip() or len(a) > 1000 for a in self.approved_actions):
            raise ValueError("Actions must be nonempty and no more than 1000 characters")
        return self


class Alternative(Record):
    machine_id: str = Field(min_length=1, max_length=100)
    machine_name: str = Field(min_length=1, max_length=200)
    compatibility: Literal["confirmed", "incompatible", "unknown"] = "unknown"
    available: bool | None = None
    allocation_status: Literal["not_planned", "proposed", "scheduled", "executed"] = "not_planned"
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def allocation_requires_evidence(self):
        if self.allocation_status != "not_planned":
            if self.compatibility != "confirmed" or self.available is not True:
                raise ValueError("Allocation requires confirmed compatibility and availability")
        return self


class Scenario(Record):
    name: str = Field(min_length=1, max_length=200)
    throughput: float = Field(ge=0)
    throughput_unit: str = Field(min_length=1, max_length=100)
    horizon_minutes: float | None = Field(default=None, gt=0)
    starting_state_id: str | None = Field(default=None, max_length=100)
    output_scope: str | None = Field(default=None, max_length=200)
    assumptions: list[str] = Field(default_factory=list, max_length=20)


class Recovery(Source):
    human: HumanAssessment | None = None
    delay_consequences: list[Fact] = Field(default_factory=list, max_length=30)
    alternatives: list[Alternative] = Field(default_factory=list, max_length=30)
    scenarios: list[Scenario] = Field(default_factory=list, max_length=30)
    baseline_scenario_id: str | None = None
    recovery_scenario_id: str | None = None
    recommended_scenario_id: str | None = None

    @model_validator(mode="after")
    def scenario_references(self):
        known = {s.id for s in self.scenarios}
        for key in ("baseline_scenario_id", "recovery_scenario_id", "recommended_scenario_id"):
            ref = getattr(self, key)
            if ref is not None and ref not in known:
                raise ValueError(f"{key} must reference a provided scenario")
        if self.baseline_scenario_id is not None and self.baseline_scenario_id == self.recovery_scenario_id:
            raise ValueError("Baseline and recovery must be different scenarios")
        return self


class AlertInput(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    alert: Alert
    data_acquisition: DataAcquisition = Field(default_factory=DataAcquisition)
    ann_fault_detection: ANNDetection = Field(default_factory=ANNDetection)
    digital_twin: DigitalTwin = Field(default_factory=DigitalTwin)
    decision_recovery: Recovery = Field(default_factory=Recovery)

    @model_validator(mode="after")
    def references_and_sources(self):
        groups = [
            (self.data_acquisition, self.data_acquisition.observations),
            (self.ann_fault_detection, self.ann_fault_detection.anomalies + self.ann_fault_detection.suspected_causes),
            (self.digital_twin, self.digital_twin.impacts),
            (self.decision_recovery, ([self.decision_recovery.human] if self.decision_recovery.human else []) + self.decision_recovery.delay_consequences + self.decision_recovery.alternatives + self.decision_recovery.scenarios),
        ]
        for source, records in groups:
            if source.status != SourceStatus.MISSING:
                if source.machine_id != self.alert.machine_id:
                    raise ValueError("Each available/stale source must identify the alert machine")
                if source.reported_at is None:
                    raise ValueError("Each available/stale source requires a timezone-aware reported_at")
            if source.status == SourceStatus.MISSING and records:
                raise ValueError("A missing source cannot contain evidence records")
            ids = [r.id for r in records]
            if len(ids) != len(set(ids)):
                raise ValueError("Evidence IDs must be unique within each source")
        observation_ids = {r.id for r in self.data_acquisition.observations}
        for cause in self.ann_fault_detection.suspected_causes:
            if not set(cause.supporting_observation_ids).issubset(observation_ids):
                raise ValueError("Cause support must reference provided observations")
        if any(a.machine_id == self.alert.machine_id for a in self.decision_recovery.alternatives):
            raise ValueError("An alternate cannot be the failed machine itself")
        return self


class Evidence(StrictModel):
    id: str
    source: str
    record_id: str
    reported_at: AwareDatetime
    data: dict


class Answer(StrictModel):
    key: str
    question: str
    status: Literal["supported", "partial", "unavailable"]
    answer: str
    evidence_ids: list[str]
    details: list[dict] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class Comparison(StrictModel):
    status: Literal["comparable", "not_comparable", "insufficient_metadata", "not_provided"]
    reason: str
    baseline_scenario_id: str | None = None
    recovery_scenario_id: str | None = None
    throughput_difference: float | None = None
    throughput_unit: str | None = None
    horizon_minutes: float | None = None


class Explanation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    alert: Alert
    explanation_mode: Literal["evidence_templates", "ai_ordered_evidence"]
    answers: list[Answer]
    evidence: list[Evidence]
    comparison: Comparison
    recommended_scenario_id: str | None = None
    warnings: list[str]
    control_actions_executed: Literal[False] = False


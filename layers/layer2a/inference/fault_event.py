"""
FaultEvent schema — the structured output of Layer 2A for every sensor
reading it evaluates.

Severity is a transparent, config-driven rule layered on top of the
ANN's (fault_type, confidence) output. It is deliberately NOT learned by
the ANN and NOT a health/criticality model — Layer 2A's only job is
"what fault is this?"; severity here is just a thin, inspectable label
derived from that answer, per the project's stated scope boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from layers.layer2a.config.industry_config import IndustryConfig


@dataclass
class FaultEvent:
    machine_id: str
    timestamp: str
    fault_status: str  # "NORMAL" or "FAULT"
    fault_type: str
    confidence: float
    severity: str
    sensor_data: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "timestamp": self.timestamp,
            "fault_status": self.fault_status,
            "fault_type": self.fault_type,
            "confidence": round(float(self.confidence), 4),
            "severity": self.severity,
            "sensor_data": self.sensor_data,
        }


def determine_severity(
    fault_type: str, confidence: float, config: IndustryConfig
) -> str:
    """
    Look up severity from the industry config's severity_rules.

    Rule shape per fault type:
      default: severity used when confidence is at/above the threshold
      low_confidence_below / low_confidence_severity: optional downgrade
        when the ANN itself isn't very sure.
    """
    rule = config.severity_rules.get(fault_type)
    if rule is None:
        # Unknown fault type slipped through — fail safe with a
        # clearly-flagged severity rather than guessing.
        return "UNKNOWN"

    if (
        rule.low_confidence_below is not None
        and confidence < rule.low_confidence_below
        and rule.low_confidence_severity is not None
    ):
        return rule.low_confidence_severity
    return rule.default


def build_fault_event(
    machine_id: str,
    timestamp: str,
    fault_type: str,
    confidence: float,
    sensor_data: Dict[str, float],
    config: IndustryConfig,
) -> FaultEvent:
    fault_status = "NORMAL" if fault_type == "NORMAL" else "FAULT"
    severity = determine_severity(fault_type, confidence, config)
    return FaultEvent(
        machine_id=machine_id,
        timestamp=timestamp,
        fault_status=fault_status,
        fault_type=fault_type,
        confidence=confidence,
        severity=severity,
        sensor_data=sensor_data,
    )

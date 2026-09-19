"""
Layer 3 - Bottleneck Detection
===============================
Per the spec, a bottleneck is NOT determined from utilization alone.
This module computes a composite, transparent score per machine from:

    - utilization                (is it busy?)
    - queue growth rate          (is work piling up in front of it?)
    - processing time            (is it slow relative to the line?)
    - effective capacity         (has fault/health eroded its capacity?)
    - throughput                 (is it actually getting units out?)
    - availability               (is it up and running?)
    - health / fault state       (is degradation the root cause?)

Output is fully structured data (factor scores + weights + total), never
a natural-language explanation - that's intentionally left for Layer 4 or
a human.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .digital_twin import MachineMetrics
from .models import FaultStatus, HealthStatus, MachineStatus

# Weights are explicit and tunable - no hidden logic.
WEIGHTS = {
    "utilization": 0.25,
    "queue_growth": 0.25,
    "processing_time": 0.15,
    "capacity_erosion": 0.15,
    "availability": 0.10,
    "health_fault": 0.10,
}

BOTTLENECK_SCORE_THRESHOLD = 0.55  # score at/above this => flagged bottleneck


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class FactorScores:
    utilization: float
    queue_growth: float
    processing_time: float
    capacity_erosion: float
    availability: float
    health_fault: float

    def weighted_total(self) -> float:
        return (
            self.utilization * WEIGHTS["utilization"]
            + self.queue_growth * WEIGHTS["queue_growth"]
            + self.processing_time * WEIGHTS["processing_time"]
            + self.capacity_erosion * WEIGHTS["capacity_erosion"]
            + self.availability * WEIGHTS["availability"]
            + self.health_fault * WEIGHTS["health_fault"]
        )

    def to_dict(self) -> Dict:
        return {
            "utilization": round(self.utilization, 3),
            "queue_growth": round(self.queue_growth, 3),
            "processing_time": round(self.processing_time, 3),
            "capacity_erosion": round(self.capacity_erosion, 3),
            "availability": round(self.availability, 3),
            "health_fault": round(self.health_fault, 3),
        }


@dataclass
class BottleneckResult:
    machine_id: str
    name: str
    score: float
    is_bottleneck: bool
    factors: FactorScores
    rank: int = 0

    def to_dict(self) -> Dict:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "score": round(self.score, 4),
            "is_bottleneck": self.is_bottleneck,
            "rank": self.rank,
            "factors": self.factors.to_dict(),
        }


class BottleneckDetector:
    """
    Stateless scorer. Call `detect()` with a snapshot of MachineMetrics
    (e.g. from DigitalTwin.get_line_snapshot() / internal metrics dict).
    """

    def __init__(self, threshold: float = BOTTLENECK_SCORE_THRESHOLD):
        self.threshold = threshold

    def detect(self, metrics_by_id: Dict[str, MachineMetrics]) -> List[BottleneckResult]:
        if not metrics_by_id:
            return []

        machines = list(metrics_by_id.values())
        avg_processing_time = sum(m.processing_time_sec for m in machines) / len(machines)
        max_queue_growth = max((abs(m.queue_growth_rate) for m in machines), default=0.0) or 1.0

        results: List[BottleneckResult] = []
        for m in machines:
            factors = FactorScores(
                utilization=_clip01(m.utilization),
                # only *positive* (growing) queues count toward bottleneck pressure
                queue_growth=_clip01(max(0.0, m.queue_growth_rate) / max_queue_growth),
                processing_time=_clip01(
                    (m.processing_time_sec / avg_processing_time - 1.0) if avg_processing_time > 0 else 0.0
                ),
                capacity_erosion=_clip01(
                    1.0 - (m.effective_capacity_units_per_hour / m.capacity_units_per_hour)
                    if m.capacity_units_per_hour > 0 else 0.0
                ),
                availability=_clip01(1.0 - m.availability),
                health_fault=_clip01(_health_fault_pressure(m)),
            )
            score = factors.weighted_total()
            results.append(
                BottleneckResult(
                    machine_id=m.machine_id,
                    name=m.name,
                    score=score,
                    is_bottleneck=score >= self.threshold,
                    factors=factors,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(results, start=1):
            r.rank = i
        return results

    def primary_bottleneck(self, metrics_by_id: Dict[str, MachineMetrics]) -> BottleneckResult | None:
        ranked = self.detect(metrics_by_id)
        if not ranked:
            return None
        top = ranked[0]
        return top if top.is_bottleneck else None


def _health_fault_pressure(m: MachineMetrics) -> float:
    pressure = 0.0
    if m.fault_status == FaultStatus.FAULT:
        pressure += 0.6
    if m.health_status == HealthStatus.DEGRADED:
        pressure += 0.4
    elif m.health_status == HealthStatus.CRITICAL:
        pressure += 0.7
    if m.machine_status == MachineStatus.DOWN:
        pressure += 0.5
    return pressure

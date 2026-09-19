"""
Layer 3 - Digital Twin: Data Models
=====================================
Defines the data contracts that flow between:
  - Layer 1  (machine/production data)
  - Layer 2A (ANN fault detection)
  - Layer 2B (ML machine-health scoring)
  - Layer 3  (this Digital Twin)

These are plain, serializable dataclasses so any consumer (Layer 4, a
message bus, a REST handler, tests, etc.) can work with them directly or
via `to_dict()` / JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FaultStatus(str, Enum):
    OK = "OK"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class MachineStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    DOWN = "DOWN"
    BLOCKED = "BLOCKED"
    MAINTENANCE = "MAINTENANCE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Inbound events (Layer 1 / 2A / 2B -> Layer 3)
# ---------------------------------------------------------------------------

@dataclass
class FaultEvent:
    """Output of Layer 2A (ANN fault classifier)."""
    machine_id: str
    fault_status: FaultStatus
    fault_type: Optional[str] = None            # e.g. "MECHANICAL/BEARING FAULT"
    confidence: Optional[float] = None          # 0..1
    timestamp: datetime = field(default_factory=_utc_now)
    source: str = "ANN"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["fault_status"] = self.fault_status.value
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class MachineHealthEvent:
    """Output of Layer 2B (ML machine-health model)."""
    machine_id: str
    health_status: HealthStatus
    health_score: Optional[float] = None            # 0..1, 1 = perfectly healthy
    remaining_useful_life_hr: Optional[float] = None
    timestamp: datetime = field(default_factory=_utc_now)
    source: str = "ML"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["health_status"] = self.health_status.value
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class MachineState:
    """Raw production/machine telemetry from Layer 1."""
    machine_id: str
    status: MachineStatus = MachineStatus.UNKNOWN
    cycle_time_sec: Optional[float] = None       # observed processing time / unit
    units_processed_total: int = 0               # monotonically increasing counter
    queue_length: int = 0
    capacity_units_per_hour: Optional[float] = None
    timestamp: datetime = field(default_factory=_utc_now)
    source: str = "LAYER1"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ---------------------------------------------------------------------------
# Combined output (Layer 3 integration result)
# ---------------------------------------------------------------------------

@dataclass
class CombinedMachineCondition:
    """The unified per-machine condition produced by the integration layer."""
    machine_id: str
    machine_status: MachineStatus = MachineStatus.UNKNOWN
    fault_status: FaultStatus = FaultStatus.UNKNOWN
    fault_type: Optional[str] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_score: Optional[float] = None
    queue_length: int = 0
    capacity_units_per_hour: Optional[float] = None
    processing_time_sec: Optional[float] = None
    last_updated: datetime = field(default_factory=_utc_now)
    stale: bool = False   # True if a source hasn't reported / gone quiet

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["machine_status"] = self.machine_status.value
        d["fault_status"] = self.fault_status.value
        d["health_status"] = self.health_status.value
        d["last_updated"] = self.last_updated.isoformat()
        return d

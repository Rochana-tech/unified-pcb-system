"""
Layer 3 - Manufacturing Line Digital Twin
==========================================
Public package surface. Layer 4 (or any consumer) should generally only
need `ProductionLineService` from `interfaces.py`, plus the event
dataclasses from `models.py` to construct inbound events, and the line
configs from `config.py`.
"""

from .models import (
    FaultEvent,
    MachineHealthEvent,
    MachineState,
    CombinedMachineCondition,
    FaultStatus,
    HealthStatus,
    MachineStatus,
)
from .config import ELECTRONICS_LINE, AUTOMOBILE_LINE, LINE_REGISTRY, LineConfig, MachineSpec
from .integration import IntegrationService
from .digital_twin import DigitalTwin, MachineMetrics
from .bottleneck import BottleneckDetector, BottleneckResult
from .simulation import WhatIfSimulator, ScenarioSpec, ScenarioKind, SimulationResult
from .interfaces import ProductionLineService

__all__ = [
    "FaultEvent",
    "MachineHealthEvent",
    "MachineState",
    "CombinedMachineCondition",
    "FaultStatus",
    "HealthStatus",
    "MachineStatus",
    "ELECTRONICS_LINE",
    "AUTOMOBILE_LINE",
    "LINE_REGISTRY",
    "LineConfig",
    "MachineSpec",
    "IntegrationService",
    "DigitalTwin",
    "MachineMetrics",
    "BottleneckDetector",
    "BottleneckResult",
    "WhatIfSimulator",
    "ScenarioSpec",
    "ScenarioKind",
    "SimulationResult",
    "ProductionLineService",
]

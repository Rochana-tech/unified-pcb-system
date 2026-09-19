"""
Layer 4 — Decision, Recovery & AI Explanation
Industrial AI Platform

This package implements ONLY Layer 4: the human-first recovery scheduler
and the verified-data-only AI explanation component.

It consumes data produced by Layers 1, 2A, 2B and 3 through plain
interfaces (see `interfaces.py`). Those layers are NOT implemented here —
`mock_sources.py` provides fakes purely so this module is runnable and
testable end-to-end.
"""

from .models import (
    MachineState,
    FaultEvent,
    MachineHealthEvent,
    DigitalTwinState,
    BottleneckInfo,
    WhatIfResult,
    RecoveryDecision,
    RecoveryStatus,
    ExplanationOutput,
)
from .config import IndustryConfig, ELECTRONICS_PCB_CONFIG, AUTOMOBILE_CONFIG
from .backend import Layer4Backend

__all__ = [
    "MachineState",
    "FaultEvent",
    "MachineHealthEvent",
    "DigitalTwinState",
    "BottleneckInfo",
    "WhatIfResult",
    "RecoveryDecision",
    "RecoveryStatus",
    "ExplanationOutput",
    "IndustryConfig",
    "ELECTRONICS_PCB_CONFIG",
    "AUTOMOBILE_CONFIG",
    "Layer4Backend",
]

"""
Interfaces Layer 4 depends on but does not implement.

Layer 1, 2A, 2B and 3 are built separately. Wire real implementations of
these Protocols in when they exist; until then `mock_sources.py` supplies
fakes so this module runs standalone.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from .models import (
    BottleneckInfo,
    DigitalTwinState,
    MachineHealthEvent,
    MachineState,
    WhatIfResult,
)


class MachineStateProvider(Protocol):
    """Layer 1 access."""

    def get_state(self, machine_id: str) -> Optional[MachineState]: ...

    def find_candidates(self, machine_types: List[str]) -> List[MachineState]:
        """Return current states of all machines of the given types."""
        ...


class HealthEventProvider(Protocol):
    """Layer 2B access."""

    def get_latest(self, machine_id: str) -> Optional[MachineHealthEvent]: ...


class DigitalTwinProvider(Protocol):
    """Layer 3 access — twin state and bottleneck info."""

    def get_twin_state(self, machine_id: str) -> Optional[DigitalTwinState]: ...

    def get_bottleneck_info(self) -> Optional[BottleneckInfo]: ...


class WhatIfClient(Protocol):
    """Layer 3 access — runs a what-if simulation for a proposed reallocation."""

    def run_whatif(
        self, source_machine_id: str, candidate_machine_id: str
    ) -> WhatIfResult: ...


class OperatorNotifier(Protocol):
    """Notifies a human operator; a real implementation might push to a UI,
    SMS, or paging system. Layer 4 only depends on this narrow interface."""

    def notify_fault(self, machine_id: str, fault_type: str, deadline: str) -> None: ...

    def notify_recovery_outcome(self, machine_id: str, summary: str) -> None: ...

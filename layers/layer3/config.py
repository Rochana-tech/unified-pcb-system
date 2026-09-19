"""
Layer 3 - Production Line Configurations
=========================================
Static topology definitions. A "line" is an ordered sequence of stations
(machines) that a unit passes through, M1 -> M2 -> ... -> Mn.

`alternates` lists machine_ids that can absorb workload from a given
machine for what-if "shift workload to a compatible alternative machine"
scenarios (must perform a compatible/interchangeable operation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass(frozen=True)
class MachineSpec:
    machine_id: str
    name: str
    sequence: int                      # 1-based position in the line
    default_capacity_uph: float        # units/hour, nominal (healthy) capacity
    default_processing_time_sec: float # nominal cycle time per unit
    alternates: tuple = ()             # machine_ids that can take over work


@dataclass(frozen=True)
class LineConfig:
    line_name: str
    machines: List[MachineSpec]

    def machine_ids_in_order(self) -> List[str]:
        return [m.machine_id for m in sorted(self.machines, key=lambda m: m.sequence)]

    def get(self, machine_id: str) -> Optional[MachineSpec]:
        for m in self.machines:
            if m.machine_id == machine_id:
                return m
        return None

    def as_dict(self) -> Dict:
        return {
            "line_name": self.line_name,
            "machines": [m.__dict__ for m in sorted(self.machines, key=lambda m: m.sequence)],
        }


# ---------------------------------------------------------------------------
# Initial Electronics configuration
# ---------------------------------------------------------------------------
ELECTRONICS_LINE = LineConfig(
    line_name="ELECTRONICS",
    machines=[
        MachineSpec("M1", "Component Placement", 1, 600, 6.0),
        MachineSpec("M2", "Soldering", 2, 500, 7.2),
        MachineSpec("M3", "Inspection", 3, 700, 5.1),
        MachineSpec("M4", "Testing", 4, 450, 8.0),
        MachineSpec("M5", "Packaging", 5, 650, 5.5),
    ],
)

# ---------------------------------------------------------------------------
# Initial Automobile configuration
# ---------------------------------------------------------------------------
AUTOMOBILE_LINE = LineConfig(
    line_name="AUTOMOBILE",
    machines=[
        MachineSpec("M1", "Welding", 1, 120, 30.0),
        MachineSpec("M2", "Painting", 2, 100, 36.0),
        MachineSpec("M3", "Assembly", 3, 90, 40.0),
        MachineSpec("M4", "Testing", 4, 110, 32.7),
        MachineSpec("M5", "Packaging", 5, 150, 24.0),
    ],
)

LINE_REGISTRY: Dict[str, LineConfig] = {
    ELECTRONICS_LINE.line_name: ELECTRONICS_LINE,
    AUTOMOBILE_LINE.line_name: AUTOMOBILE_LINE,
}

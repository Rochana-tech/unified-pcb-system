"""
Industry configuration.

Layer 4's scheduler is deliberately dumb and rule-based: every recovery
choice it makes traces back to a value in one of these config objects,
never to a learned model. Add a new industry by adding a new
IndustryConfig — no code changes needed elsewhere in Layer 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class IndustryConfig:
    name: str

    # machine_type -> list of machine_types that can substitute for it
    machine_compatibility: Dict[str, List[str]] = field(default_factory=dict)

    # machine_id -> max concurrent capacity (units/hour or job slots)
    machine_capacity: Dict[str, float] = field(default_factory=dict)

    # ordered station/machine_type flow, used to reason about downstream impact
    production_flow: List[str] = field(default_factory=list)

    # seconds an operator has to correct a fault before Layer 4 escalates
    human_correction_timeout_seconds: int = 120

    # max queue length Layer 4 will accept on a candidate alternative machine
    max_acceptable_queue_length: int = 5

    # max load (0-1) a candidate alternative can already be at
    max_acceptable_load: float = 0.85

    def compatible_types_for(self, machine_type: str) -> List[str]:
        return self.machine_compatibility.get(machine_type, [])


ELECTRONICS_PCB_CONFIG = IndustryConfig(
    name="Electronics/PCB",
    machine_compatibility={
        "smt_placement": ["smt_placement_backup"],
        "smt_placement_backup": ["smt_placement"],
        "reflow_oven": ["reflow_oven_secondary"],
        "reflow_oven_secondary": ["reflow_oven"],
        "aoi_inspection": ["aoi_inspection_backup"],
        "aoi_inspection_backup": ["aoi_inspection"],
    },
    machine_capacity={
        "SMT-01": 1200, "SMT-02": 1200,
        "REFLOW-01": 900, "REFLOW-02": 900,
        "AOI-01": 1500, "AOI-02": 1500,
    },
    production_flow=["smt_placement", "reflow_oven", "aoi_inspection"],
    human_correction_timeout_seconds=90,
    max_acceptable_queue_length=4,
    max_acceptable_load=0.85,
)

AUTOMOBILE_CONFIG = IndustryConfig(
    name="Automobile",
    machine_compatibility={
        "welding_robot": ["welding_robot_secondary"],
        "welding_robot_secondary": ["welding_robot"],
        "paint_booth": ["paint_booth_backup"],
        "paint_booth_backup": ["paint_booth"],
        "assembly_station": ["assembly_station_flex"],
        "assembly_station_flex": ["assembly_station"],
    },
    machine_capacity={
        "WELD-01": 60, "WELD-02": 60,
        "PAINT-01": 40, "PAINT-02": 40,
        "ASM-01": 80, "ASM-02": 80,
    },
    production_flow=["welding_robot", "paint_booth", "assembly_station"],
    human_correction_timeout_seconds=180,
    max_acceptable_queue_length=6,
    max_acceptable_load=0.90,
)

INDUSTRY_REGISTRY: Dict[str, IndustryConfig] = {
    ELECTRONICS_PCB_CONFIG.name: ELECTRONICS_PCB_CONFIG,
    AUTOMOBILE_CONFIG.name: AUTOMOBILE_CONFIG,
}

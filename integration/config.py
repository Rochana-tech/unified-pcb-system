from dataclasses import dataclass, field
from layers.layer3.config import ELECTRONICS_LINE, LineConfig, MachineSpec

@dataclass(frozen=True)
class Settings:
    mode: str = 'demo'
    database: str = 'data/manufacturing.sqlite3'
    correction_seconds: int = 20
    demo_backup: bool = True
    stale_seconds: int = 30
    public_site: bool = False
    operator_key: str = field(default="", repr=False)

TOPOLOGY = ['M1', 'M2', 'M3', 'M4', 'M5']
TYPES = dict(zip(TOPOLOGY, ['placement', 'soldering', 'inspection', 'testing', 'packaging']))
TYPES['M4-BACKUP'] = 'testing'

def line_config(backup: bool) -> LineConfig:
    machines = list(ELECTRONICS_LINE.machines)
    if backup:
        machines.append(MachineSpec('M4-BACKUP', 'Testing standby (simulated)', 6, 450, 8.0))
    return LineConfig('PCB assembly', machines)

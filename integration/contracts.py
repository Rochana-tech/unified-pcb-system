from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Sensors(Strict):
    current: float = Field(ge=0, le=10000)
    temperature: float = Field(ge=-273.15, le=3000)
    vibration: float = Field(ge=0, le=10000)
    rpm: float = Field(ge=0, le=1000000)

class Telemetry(Strict):
    machine_id: str = Field(pattern=r'^M[1-5]$')
    timestamp: AwareDatetime
    status: Literal['RUNNING', 'IDLE', 'DOWN', 'BLOCKED', 'MAINTENANCE']
    units_processed_total: int = Field(ge=0)
    queue_length: int = Field(ge=0, le=10000)
    cycle_time_sec: float = Field(gt=0, le=86400)
    capacity_units_per_hour: float = Field(ge=0, le=100000)
    downtime_seconds: float = Field(default=0, ge=0)
    sensors: Sensors | None = None

class InjectFault(Strict):
    fault_type: Literal['BEARING_FAULT', 'MOTOR_OVERLOAD', 'MOTOR_OVERHEAT', 'STOPPED'] = 'BEARING_FAULT'

class ScenarioRequest(Strict):
    machine_id: str = Field(default='M4', pattern=r'^M[1-5]$')
    downtime_seconds: int = Field(default=120, ge=0, le=3600)
    horizon_minutes: int = Field(default=15, ge=1, le=60)
    use_backup: bool = True

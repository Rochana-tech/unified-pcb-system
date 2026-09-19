"""
Configurable human-correction timer.

Deliberately clock-injectable (no `time.sleep`, no threads) so:
- a real host loop can call `check_expirations()` on its own schedule
  (e.g. every second), and
- tests/demos can simulate time passing instantly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional


@dataclass
class _PendingTimer:
    machine_id: str
    fault_id: str
    started_at: datetime
    deadline: datetime


class CorrectionTimerManager:
    def __init__(self, clock: Optional[Callable[[], datetime]] = None):
        self._clock = clock or datetime.utcnow
        self._timers: Dict[str, _PendingTimer] = {}  # keyed by machine_id

    def start(self, machine_id: str, fault_id: str, timeout_seconds: int) -> str:
        now = self._clock()
        deadline = now + timedelta(seconds=timeout_seconds)
        self._timers[machine_id] = _PendingTimer(machine_id, fault_id, now, deadline)
        return deadline.isoformat() + "Z"

    def cancel(self, machine_id: str) -> None:
        self._timers.pop(machine_id, None)

    def is_pending(self, machine_id: str) -> bool:
        timer = self._timers.get(machine_id)
        return timer is not None and self._clock() < timer.deadline

    def deadline_for(self, machine_id: str) -> Optional[str]:
        t = self._timers.get(machine_id)
        return (t.deadline.isoformat() + "Z") if t else None

    def collect_expired(self) -> List[_PendingTimer]:
        """Return and remove all timers whose deadline has passed."""
        now = self._clock()
        expired = [t for t in self._timers.values() if t.deadline <= now]
        for t in expired:
            self._timers.pop(t.machine_id, None)
        return expired

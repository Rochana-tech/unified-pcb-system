"""
Structured logging for every step of the recovery lifecycle:
fault, human intervention, timer result, recovery decision,
alternative selected, what-if result, final action.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class LogEntry:
    event_type: str
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class RecoveryLogger:
    """In-memory log store, optionally mirrored to a JSON-lines file."""

    def __init__(self, file_path: Optional[str] = None):
        self._entries: List[LogEntry] = []
        self._file_path = Path(file_path) if file_path else None

    def log(self, event_type: str, payload: dict) -> LogEntry:
        entry = LogEntry(event_type=event_type, payload=payload)
        self._entries.append(entry)
        if self._file_path:
            with open(self._file_path, "a") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def all(self) -> List[LogEntry]:
        return list(self._entries)

    def for_machine(self, machine_id: str) -> List[LogEntry]:
        return [e for e in self._entries if e.payload.get("machine_id") == machine_id]

    def for_decision(self, decision_id: str) -> List[LogEntry]:
        return [e for e in self._entries if e.payload.get("decision_id") == decision_id]

    def as_dicts(self) -> List[dict]:
        return [asdict(e) for e in self._entries]

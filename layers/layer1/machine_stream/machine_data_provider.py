"""
Abstract interface for Stream B (machine/production data).

Any future real machine-data source (PLC/SCADA/MES integration, OPC-UA,
REST polling, Kafka, DB polling, etc.) implements this same interface, so
Layer 2 / Layer 3 code never has to change when the dummy source is swapped
for the real one - just point the orchestrator at a different implementation.
"""
from abc import ABC, abstractmethod


class MachineDataProvider(ABC):
    @abstractmethod
    def start(self):
        """Begin producing continuous machine/production records."""
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        """Stop producing records."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_state(self, machine_id: str = None):
        """Return the latest known state for one machine, or all machines if None."""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, callback):
        """Register a callback(record: dict) invoked on every new record."""
        raise NotImplementedError

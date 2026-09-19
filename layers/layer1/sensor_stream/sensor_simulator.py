"""
Stream A - Sensor data simulator.
Generates continuous, real-time sensor records per machine (never a static
batch), driven by a NORMAL/DEGRADED/FAULT health state machine with
controlled fault injection.
"""
import threading

from layers.layer1.common.logger import get_logger
from layers.layer1.common.utils import now_iso
from layers.layer1.config import config
from layers.layer1.sensor_stream.fault_patterns import MachineHealthState, generate_sensor_values

log = get_logger("sensor_simulator")


class SensorSimulator:
    def __init__(self, machine_ids=None, interval_sec=None, on_record=None):
        self.machine_ids = machine_ids or config.MACHINES
        self.interval_sec = interval_sec or config.SENSOR_PUBLISH_INTERVAL_SEC
        self.on_record = on_record  # callback(record: dict)
        self.health_states = {mid: MachineHealthState(mid) for mid in self.machine_ids}
        self._stop_event = threading.Event()
        self._thread = None

    def inject_fault(self, machine_id: str):
        """Manually force a machine into FAULT state (demo / testing hook)."""
        if machine_id in self.health_states:
            self.health_states[machine_id].force_fault()
            log.warning(f"Manual fault injected on {machine_id}")

    def _generate_one_cycle(self):
        records = []
        for mid in self.machine_ids:
            health = self.health_states[mid]
            state = health.step()
            values = generate_sensor_values(mid, state)
            record = {
                "machine_id": mid,
                "timestamp": now_iso(),
                "health_state": state,  # diagnostic hint; ANN layer may use or ignore
                **values,
            }
            records.append(record)
        return records

    def _run(self):
        log.info(f"Sensor simulator started | machines={self.machine_ids} | interval={self.interval_sec}s")
        while not self._stop_event.is_set():
            for record in self._generate_one_cycle():
                if record["health_state"] == "FAULT":
                    log.warning(f"[FAULT] {record['machine_id']} -> {record}")
                if self.on_record:
                    self.on_record(record)
            self._stop_event.wait(self.interval_sec)
        log.info("Sensor simulator stopped")

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sensor-simulator")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

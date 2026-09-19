"""
Maintains the latest combined (sensor + production) state for all five
machines. This is the single object Layer 2/3 can query for a fused
machine_id + timestamp view without caring how each stream is produced,
while the two streams stay logically separate internally.
"""
import threading


class StateManager:
    def __init__(self, machine_ids):
        self.machine_ids = machine_ids
        self._lock = threading.Lock()
        self._sensor_state = {mid: None for mid in machine_ids}
        self._production_state = {mid: None for mid in machine_ids}

    def update_sensor(self, record: dict):
        with self._lock:
            self._sensor_state[record["machine_id"]] = record

    def update_production(self, record: dict):
        with self._lock:
            self._production_state[record["machine_id"]] = record

    def get_fused_state(self, machine_id: str = None):
        with self._lock:
            if machine_id:
                return {
                    "machine_id": machine_id,
                    "sensor": self._sensor_state.get(machine_id),
                    "production": self._production_state.get(machine_id),
                }
            return {
                mid: {
                    "sensor": self._sensor_state.get(mid),
                    "production": self._production_state.get(mid),
                }
                for mid in self.machine_ids
            }

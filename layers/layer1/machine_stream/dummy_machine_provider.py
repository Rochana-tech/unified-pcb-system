"""
Dummy/simulated implementation of MachineDataProvider (Stream B).

Produces continuous production-state records for M1..M5 at a configurable
interval, behaving like a live data source (not a static batch). Swap this
class for a real adapter later - main.py is the only place that needs to
change (see MachineDataProvider interface).
"""
import random
import threading

from layers.layer1.common.logger import get_logger
from layers.layer1.common.utils import now_iso
from layers.layer1.config import config
from layers.layer1.machine_stream.machine_data_provider import MachineDataProvider

log = get_logger("dummy_machine_provider")

STATUSES = ["RUNNING", "IDLE", "BLOCKED", "DOWN"]
STATUS_WEIGHTS = [0.75, 0.15, 0.07, 0.03]


class DummyMachineDataProvider(MachineDataProvider):
    def __init__(self, machine_ids=None, interval_sec=None):
        self.machine_ids = machine_ids or config.MACHINES
        self.interval_sec = interval_sec or config.MACHINE_DATA_INTERVAL_SEC
        self._subscribers = []
        self._latest = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._queue = {mid: random.randint(0, 5) for mid in self.machine_ids}

    def subscribe(self, callback):
        self._subscribers.append(callback)

    def _generate_record(self, machine_id: str) -> dict:
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        processing_time = round(random.uniform(8.0, 25.0), 2)  # seconds/unit
        capacity = 100  # rated units/hour
        utilization = round(
            random.uniform(0.5, 0.98) if status == "RUNNING" else random.uniform(0.0, 0.3), 3
        )
        self._queue[machine_id] = max(0, self._queue[machine_id] + random.choice([-1, 0, 0, 1, 1]))
        throughput = round(capacity * utilization / 60.0, 2)  # units/min
        availability = round(
            random.uniform(0.85, 1.0) if status != "DOWN" else random.uniform(0.0, 0.4), 3
        )

        return {
            "machine_id": machine_id,
            "timestamp": now_iso(),
            "status": status,
            "processing_time": processing_time,
            "capacity": capacity,
            "utilization": utilization,
            "queue_length": self._queue[machine_id],
            "throughput": throughput,
            "availability": availability,
        }

    def _run(self):
        log.info(f"Machine data provider started | machines={self.machine_ids} | interval={self.interval_sec}s")
        while not self._stop_event.is_set():
            for mid in self.machine_ids:
                record = self._generate_record(mid)
                with self._lock:
                    self._latest[mid] = record
                for cb in self._subscribers:
                    try:
                        cb(record)
                    except Exception as e:
                        log.error(f"Subscriber callback error: {e}")
            self._stop_event.wait(self.interval_sec)
        log.info("Machine data provider stopped")

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dummy-machine-provider")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_latest_state(self, machine_id: str = None):
        with self._lock:
            if machine_id:
                return self._latest.get(machine_id)
            return dict(self._latest)

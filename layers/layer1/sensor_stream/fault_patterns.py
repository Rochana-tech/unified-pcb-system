"""
Per-machine health state machine (NORMAL / DEGRADED / FAULT) and the sensor
value generator driven by that state. M4 (Testing) follows the spec's
explicit fault pattern: vibration UP, temperature UP, RPM DOWN.
"""
import random

from layers.layer1.config import config

BASELINES = {
    "M1": {"current": 4.0, "temperature": 35.0, "vibration": 0.20, "rpm": 1500},
    "M2": {"current": 6.0, "temperature": 55.0, "vibration": 0.30, "rpm": 1200},
    "M3": {"current": 2.5, "temperature": 30.0, "vibration": 0.10, "rpm": 800},
    "M4": {"current": 5.0, "temperature": 40.0, "vibration": 0.25, "rpm": 1000},
    "M5": {"current": 3.5, "temperature": 32.0, "vibration": 0.15, "rpm": 900},
}


class MachineHealthState:
    """Tracks and evolves the health condition of one machine over time."""

    def __init__(self, machine_id: str):
        self.machine_id = machine_id
        self.state = "NORMAL"
        self.transition_table = (
            config.M4_STATE_TRANSITION if machine_id == "M4" else config.DEFAULT_STATE_TRANSITION
        )

    def step(self) -> str:
        probs = self.transition_table[self.state]
        r = random.random()
        cumulative = 0.0
        for next_state, p in probs.items():
            cumulative += p
            if r <= cumulative:
                self.state = next_state
                break
        return self.state

    def force_fault(self):
        """Manual fault injection hook, e.g. for a live demo."""
        self.state = "FAULT"

    def force_state(self, state: str):
        assert state in ("NORMAL", "DEGRADED", "FAULT")
        self.state = state


def generate_sensor_values(machine_id: str, state: str) -> dict:
    base = BASELINES[machine_id]
    current, temperature = base["current"], base["temperature"]
    vibration, rpm = base["vibration"], base["rpm"]

    if state == "NORMAL":
        current *= random.uniform(0.95, 1.05)
        temperature *= random.uniform(0.97, 1.03)
        vibration *= random.uniform(0.80, 1.20)
        rpm *= random.uniform(0.98, 1.02)

    elif state == "DEGRADED":
        current *= random.uniform(1.05, 1.20)
        temperature *= random.uniform(1.08, 1.20)
        vibration *= random.uniform(1.50, 2.50)
        rpm *= random.uniform(0.90, 0.97)

    elif state == "FAULT":
        if machine_id == "M4":
            # explicit spec pattern: vibration up, temperature up, rpm down
            vibration *= random.uniform(3.0, 5.0)
            temperature *= random.uniform(1.25, 1.50)
            rpm *= random.uniform(0.50, 0.70)
            current *= random.uniform(1.20, 1.60)
        else:
            current *= random.uniform(1.30, 1.80)
            temperature *= random.uniform(1.30, 1.60)
            vibration *= random.uniform(2.50, 4.00)
            rpm *= random.uniform(0.60, 0.85)

    # small continuous jitter so the stream never looks static/batch-like
    current += random.uniform(-0.05, 0.05)
    temperature += random.uniform(-0.3, 0.3)
    vibration += random.uniform(-0.02, 0.02)
    rpm += random.uniform(-5, 5)

    return {
        "current": round(max(current, 0), 3),
        "temperature": round(max(temperature, 0), 2),
        "vibration": round(max(vibration, 0), 3),
        "rpm": round(max(rpm, 0), 1),
    }

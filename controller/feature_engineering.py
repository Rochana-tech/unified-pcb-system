"""
Rolling feature engineering for machine-controller telemetry.

Turns raw per-cycle readings from controller_live_generator.py into a
feature vector suitable for ML models, using only controller-reported
fields (cycle time, counters, tool life) -- no sensor data.
"""

from collections import deque
import numpy as np

WINDOW = 20

FEATURE_NAMES = [
    "mean_cycle_time",
    "std_cycle_time",
    "cycle_time_slope",
    "reject_rate",
    "tool_life_ratio",
    "downtime_seconds",
    "tool_change_count",
]


class MachineFeatureBuilder:
    """Maintains a rolling window of recent readings for one machine and
    turns them into a feature vector on each new reading."""

    def __init__(self, window: int = WINDOW):
        self.window = window
        self.cycle_times = deque(maxlen=window)
        self.reject_flags = deque(maxlen=window)
        self._prev_reject_count = None

    def update(self, reading: dict) -> dict:
        """Feed one new reading, return the current feature vector (dict)."""
        is_running = reading["state"] == "RUNNING"

        if is_running and reading["cycle_time_sec"] is not None:
            self.cycle_times.append(reading["cycle_time_sec"])

        was_reject = 0
        if is_running and self._prev_reject_count is not None:
            was_reject = 1 if reading["reject_count"] > self._prev_reject_count else 0
        if is_running:
            self.reject_flags.append(was_reject)
            self._prev_reject_count = reading["reject_count"]

        return self._compute_features(reading)

    def _compute_features(self, reading: dict) -> dict:
        ct = np.array(self.cycle_times) if self.cycle_times else np.array([0.0])
        rj = np.array(self.reject_flags) if self.reject_flags else np.array([0.0])

        mean_cycle_time = float(ct.mean())
        std_cycle_time = float(ct.std())

        # Slope of cycle time over the window -> captures drift as tool wears
        slope = float(np.polyfit(np.arange(len(ct)), ct, 1)[0]) if len(ct) >= 2 else 0.0

        reject_rate = float(rj.mean())
        tool_life_ratio = reading["units_since_tool_change"] / 2000.0

        return {
            "mean_cycle_time": mean_cycle_time,
            "std_cycle_time": std_cycle_time,
            "cycle_time_slope": slope,
            "reject_rate": reject_rate,
            "tool_life_ratio": tool_life_ratio,
            "downtime_seconds": reading["downtime_seconds"],
            "tool_change_count": reading["tool_change_count"],
        }

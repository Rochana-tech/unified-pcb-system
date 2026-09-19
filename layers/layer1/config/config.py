"""
Central configuration for Layer 1 - Data Acquisition & Real-Time Communication.
All intervals, MQTT settings and machine IDs live here (or override via env vars)
so nothing is hardcoded downstream.
"""
import os

MACHINES = ["M1", "M2", "M3", "M4", "M5"]

MACHINE_NAMES = {
    "M1": "Component Placement",
    "M2": "Soldering",
    "M3": "Inspection",
    "M4": "Testing",
    "M5": "Packaging",
}

# ---- MQTT settings (Stream A: sensor data) ----
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))
MQTT_CLIENT_ID_PUBLISHER = "sensor-publisher"
MQTT_CLIENT_ID_CONSUMER = "sensor-consumer"


def sensor_topic(machine_id: str) -> str:
    return f"factory/{machine_id}/sensors"


SENSOR_TOPIC_WILDCARD = "factory/+/sensors"

# ---- Simulation intervals (seconds) - configurable, real-time not batch ----
SENSOR_PUBLISH_INTERVAL_SEC = float(os.getenv("SENSOR_PUBLISH_INTERVAL_SEC", "2.0"))
MACHINE_DATA_INTERVAL_SEC = float(os.getenv("MACHINE_DATA_INTERVAL_SEC", "3.0"))

# ---- Data quality controls ----
STALE_MESSAGE_THRESHOLD_SEC = float(os.getenv("STALE_MESSAGE_THRESHOLD_SEC", "30.0"))

# ---- Fault injection: per-tick Markov transition probabilities ----
DEFAULT_STATE_TRANSITION = {
    "NORMAL":   {"NORMAL": 0.95, "DEGRADED": 0.05, "FAULT": 0.00},
    "DEGRADED": {"NORMAL": 0.30, "DEGRADED": 0.60, "FAULT": 0.10},
    "FAULT":    {"NORMAL": 0.40, "DEGRADED": 0.40, "FAULT": 0.20},
}

# M4 (Testing) is the spec's featured fault-demo machine -> higher fault odds
M4_STATE_TRANSITION = {
    "NORMAL":   {"NORMAL": 0.90, "DEGRADED": 0.08, "FAULT": 0.02},
    "DEGRADED": {"NORMAL": 0.25, "DEGRADED": 0.55, "FAULT": 0.20},
    "FAULT":    {"NORMAL": 0.35, "DEGRADED": 0.35, "FAULT": 0.30},
}

# ---- API (Layer 2/3 consumption interface) ----
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

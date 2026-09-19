import json
import time
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_epoch() -> float:
    return time.time()


def is_stale(timestamp_iso: str, threshold_sec: float) -> bool:
    """True if the given ISO timestamp is older than threshold_sec, or unparsable."""
    try:
        ts = datetime.fromisoformat(timestamp_iso)
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age > threshold_sec


def safe_json_loads(payload):
    try:
        return json.loads(payload), None
    except (json.JSONDecodeError, TypeError) as e:
        return None, str(e)


REQUIRED_SENSOR_FIELDS = {"machine_id", "timestamp", "current", "temperature", "vibration", "rpm"}
REQUIRED_MACHINE_FIELDS = {
    "machine_id", "timestamp", "status", "processing_time", "capacity",
    "utilization", "queue_length", "throughput", "availability",
}


def validate_sensor_record(record: dict):
    if not isinstance(record, dict):
        return False, "record is not a JSON object"
    missing = REQUIRED_SENSOR_FIELDS - record.keys()
    if missing:
        return False, f"missing fields: {missing}"
    for field in ("current", "temperature", "vibration", "rpm"):
        if not isinstance(record[field], (int, float)):
            return False, f"field '{field}' must be numeric"
    if record["machine_id"] not in {"M1", "M2", "M3", "M4", "M5"}:
        return False, f"unknown machine_id '{record['machine_id']}'"
    return True, None


def validate_machine_record(record: dict):
    if not isinstance(record, dict):
        return False, "record is not a JSON object"
    missing = REQUIRED_MACHINE_FIELDS - record.keys()
    if missing:
        return False, f"missing fields: {missing}"
    return True, None

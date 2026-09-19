"""
Tests for Layer 2A inference — deliberately independent of any dashboard
or Layer 1 transport. Run with:

    python -m pytest tests/test_inference.py -v

or, without pytest:

    python tests/test_inference.py
"""

from __future__ import annotations

import os
import sys

from layers.layer2a.config.industry_config import (  # noqa: E402
    IndustryModelNotTrainedError,
    IndustryNotFoundError,
    list_available_industries,
    load_industry_config,
)
from layers.layer2a.inference.predictor import FaultPredictor, MissingFeatureError  # noqa: E402
from layers.layer2a.interface.layer1_adapter import handle_reading  # noqa: E402

INDUSTRY = "electronics_pcb"

# Representative readings per class, well inside each class's synthetic
# distribution (see data/generate_synthetic.py CLASS_PROFILES).
SAMPLE_READINGS = {
    "NORMAL": {"current": 5.0, "temperature": 45.0, "vibration": 1.0, "rpm": 1500},
    "MOTOR_OVERLOAD": {"current": 12.0, "temperature": 60.0, "vibration": 1.3, "rpm": 1400},
    "MOTOR_OVERHEAT": {"current": 6.5, "temperature": 88.0, "vibration": 1.2, "rpm": 1480},
    "BEARING_FAULT": {"current": 5.5, "temperature": 50.0, "vibration": 5.0, "rpm": 1450},
}


def _make_reading(machine_id, class_name):
    reading = dict(SAMPLE_READINGS[class_name])
    reading["machine_id"] = machine_id
    reading["timestamp"] = "2026-09-19T10:00:00Z"
    return reading


def test_config_registry_lists_industries():
    industries = list_available_industries()
    assert "electronics_pcb" in industries
    assert "automobile" in industries


def test_automobile_is_not_trained_and_fails_loudly():
    cfg = load_industry_config("automobile")
    assert cfg.status == "not_trained"
    try:
        FaultPredictor("automobile")
        assert False, "Expected IndustryModelNotTrainedError"
    except IndustryModelNotTrainedError:
        pass


def test_unknown_industry_raises():
    try:
        load_industry_config("nonexistent_industry")
        assert False, "Expected IndustryNotFoundError"
    except IndustryNotFoundError:
        pass


def test_predictor_produces_correct_fault_event_shape():
    predictor = FaultPredictor(INDUSTRY)
    reading = _make_reading("M-001", "NORMAL")
    event = predictor.predict(reading)

    d = event.as_dict()
    for key in [
        "machine_id",
        "timestamp",
        "fault_status",
        "fault_type",
        "confidence",
        "severity",
        "sensor_data",
    ]:
        assert key in d, f"Missing key: {key}"
    assert d["machine_id"] == "M-001"
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["fault_status"] in ("NORMAL", "FAULT")


def test_predictor_classifies_representative_samples_correctly():
    predictor = FaultPredictor(INDUSTRY)
    correct = 0
    for class_name, features in SAMPLE_READINGS.items():
        reading = _make_reading("M-TEST", class_name)
        event = predictor.predict(reading)
        if event.fault_type == class_name:
            correct += 1
        else:
            print(f"  [warn] expected {class_name}, got {event.fault_type} "
                  f"(confidence={event.confidence:.3f})")
    # All 4 representative (non-borderline) samples should classify correctly.
    assert correct == len(SAMPLE_READINGS), (
        f"Only {correct}/{len(SAMPLE_READINGS)} representative samples "
        f"classified correctly"
    )


def test_normal_reading_has_normal_status_and_no_severity():
    predictor = FaultPredictor(INDUSTRY)
    reading = _make_reading("M-002", "NORMAL")
    event = predictor.predict(reading)
    assert event.fault_status == "NORMAL"
    assert event.severity == "NONE"


def test_fault_reading_has_fault_status_and_nonzero_severity():
    predictor = FaultPredictor(INDUSTRY)
    reading = _make_reading("M-003", "MOTOR_OVERHEAT")
    event = predictor.predict(reading)
    assert event.fault_status == "FAULT"
    assert event.severity in ("LOW", "MEDIUM", "HIGH")


def test_missing_feature_raises():
    predictor = FaultPredictor(INDUSTRY)
    incomplete_reading = {
        "machine_id": "M-004",
        "timestamp": "2026-09-19T10:00:00Z",
        "current": 5.0,
        # temperature, vibration, rpm deliberately missing
    }
    try:
        predictor.predict(incomplete_reading)
        assert False, "Expected MissingFeatureError"
    except MissingFeatureError:
        pass


def test_layer1_adapter_produces_same_result_as_direct_predictor():
    predictor = FaultPredictor(INDUSTRY)
    reading = _make_reading("M-005", "BEARING_FAULT")
    direct_event = predictor.predict(dict(reading))

    reading_via_adapter = dict(reading)
    reading_via_adapter["industry"] = INDUSTRY
    adapter_event = handle_reading(reading_via_adapter)

    assert direct_event.fault_type == adapter_event.fault_type
    assert direct_event.machine_id == adapter_event.machine_id


def _run_all():
    tests = [obj for name, obj in globals().items() if name.startswith("test_")]
    passed, failed = 0, 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"PASS  {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {test_fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)

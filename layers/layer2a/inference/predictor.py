"""
Layer 2A real-time inference.

FaultPredictor loads a trained model + scaler for one industry and turns
a single sensor reading into a FaultEvent. This is the ONLY class other
layers (Layer 1 adapter, future integration layer, tests) need to touch —
everything about training, architecture, and file layout stays behind it.

Independently testable: FaultPredictor has no dependency on a dashboard,
a queue, or any other layer. See tests/test_inference.py.
"""

from __future__ import annotations

import os
import sys
from typing import Dict

import numpy as np

from layers.layer2a.config.industry_config import (  # noqa: E402
    IndustryConfig,
    require_trained_config,
)
from layers.layer2a.inference.fault_event import FaultEvent, build_fault_event  # noqa: E402
from layers.layer2a.preprocessing.scaler import load_scaler, transform  # noqa: E402

import joblib  # noqa: E402


class MissingFeatureError(ValueError):
    """Raised when a sensor reading is missing a required feature."""


class FaultPredictor:
    """
    Loads a trained ANN + scaler for a given industry and predicts faults
    for individual sensor readings.

    Usage:
        predictor = FaultPredictor("electronics_pcb")
        event = predictor.predict({
            "machine_id": "M-001",
            "timestamp": "2026-09-19T10:00:00Z",
            "current": 11.2, "temperature": 60.1, "vibration": 1.4, "rpm": 1390,
        })
    """

    def __init__(self, industry: str):
        self.config: IndustryConfig = require_trained_config(industry)
        self.model = joblib.load(self.config.absolute_model_path())
        self.scaler = load_scaler(self.config.absolute_scaler_path())

    def _extract_feature_vector(self, reading: Dict) -> np.ndarray:
        missing = [f for f in self.config.features if f not in reading]
        if missing:
            raise MissingFeatureError(
                f"Reading is missing required feature(s): {missing}. "
                f"Expected: {self.config.features}"
            )
        values = [float(reading[f]) for f in self.config.features]
        return np.array(values, dtype=float).reshape(1, -1)

    def predict(self, reading: Dict) -> FaultEvent:
        """
        Run inference on one sensor reading.

        `reading` must contain machine_id, timestamp, and every feature
        named in the industry config (current, temperature, vibration, rpm
        for electronics_pcb). Extra keys are ignored.
        """
        raw_vector = self._extract_feature_vector(reading)
        scaled_vector = transform(self.scaler, raw_vector)

        # The model was trained on integer-encoded labels (index into
        # config.fault_classes — see model/train.py), not raw strings, so
        # decode the prediction back to its fault-type name here.
        predicted_index = int(self.model.predict(scaled_vector)[0])
        probabilities = self.model.predict_proba(scaled_vector)[0]
        class_index = list(self.model.classes_).index(predicted_index)
        confidence = float(probabilities[class_index])
        predicted_class = self.config.fault_classes[predicted_index]

        sensor_data = {f: float(reading[f]) for f in self.config.features}

        return build_fault_event(
            machine_id=reading.get("machine_id", "UNKNOWN"),
            timestamp=reading.get("timestamp", ""),
            fault_type=str(predicted_class),
            confidence=confidence,
            sensor_data=sensor_data,
            config=self.config,
        )

    def predict_batch(self, readings: list) -> list:
        """Convenience wrapper: predict() over a list of readings."""
        return [self.predict(r) for r in readings]

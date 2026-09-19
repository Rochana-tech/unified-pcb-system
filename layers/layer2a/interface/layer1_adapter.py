"""
Layer 1 -> Layer 2A adapter.

This is the ONLY place that needs to change if Layer 1's real transport
(queue, socket, REST call, MQTT, etc.) is decided later. Today it accepts
a plain dict shaped like:

    {
        "machine_id": "M-001",
        "timestamp": "2026-09-19T10:00:00Z",
        "industry": "electronics_pcb",   # optional, see below
        "current": 11.2,
        "temperature": 60.1,
        "vibration": 1.4,
        "rpm": 1390,
    }

and calls the matching FaultPredictor to produce a FaultEvent. Everything
behind this adapter (predictor, model, config) is unaffected by how
readings actually arrive in production.

Predictors are cached per industry so repeated readings for the same
industry don't reload the model/scaler from disk each time.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

from layers.layer2a.inference.fault_event import FaultEvent  # noqa: E402
from layers.layer2a.inference.predictor import FaultPredictor  # noqa: E402

DEFAULT_INDUSTRY = "electronics_pcb"

_predictor_cache: Dict[str, FaultPredictor] = {}


def _get_predictor(industry: str) -> FaultPredictor:
    if industry not in _predictor_cache:
        _predictor_cache[industry] = FaultPredictor(industry)
    return _predictor_cache[industry]


def handle_reading(reading: Dict, default_industry: str = DEFAULT_INDUSTRY) -> FaultEvent:
    """
    Process one Layer-1-shaped sensor reading and return a FaultEvent.

    The reading may optionally carry its own "industry" key (e.g. a
    multi-industry deployment routing different machines through the
    same pipeline); otherwise `default_industry` is used.
    """
    industry = reading.get("industry", default_industry)
    predictor = _get_predictor(industry)
    return predictor.predict(reading)


def handle_batch(
    readings: List[Dict], default_industry: str = DEFAULT_INDUSTRY
) -> List[FaultEvent]:
    """Process a list of readings, grouped internally by industry as needed."""
    return [handle_reading(r, default_industry) for r in readings]

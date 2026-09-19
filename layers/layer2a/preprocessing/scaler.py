"""
Feature normalization for Layer 2A.

Thin wrapper around sklearn's StandardScaler so training and inference
always normalize features identically, and the fitted scaler is saved
and loaded alongside the model (never re-fit at inference time).
"""

from __future__ import annotations

import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler


def fit_scaler(features: np.ndarray) -> StandardScaler:
    """Fit a new scaler on training features only (never on val/test)."""
    scaler = StandardScaler()
    scaler.fit(features)
    return scaler


def save_scaler(scaler: StandardScaler, path: str) -> None:
    joblib.dump(scaler, path)


def load_scaler(path: str) -> StandardScaler:
    return joblib.load(path)


def transform(scaler: StandardScaler, features: np.ndarray) -> np.ndarray:
    return scaler.transform(features)

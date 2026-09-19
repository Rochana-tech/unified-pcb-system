"""
Trains two models on simulated controller telemetry:

  1) failure_model  - RandomForest classifier predicting whether a
     machine will FAULT within the next LOOKAHEAD cycles.
  2) anomaly_model   - IsolationForest flagging behaviour that's unusual
     relative to normal operation (unsupervised, no labels needed).

Run:  python train_models.py
Produces: failure_model.joblib, anomaly_model.joblib
"""

import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from controller.controller_live_generator import make_machine, generate_reading
from controller.feature_engineering import MachineFeatureBuilder, FEATURE_NAMES

LOOKAHEAD = 15            # predict fault within next N cycles
CYCLES_PER_MACHINE = 3000
NUM_MACHINES = 10


def simulate_machine_history(seed_index: int):
    """Run one simulated machine forward and record (features, is_fault) per cycle."""
    m = make_machine(seed_index)
    fb = MachineFeatureBuilder()
    rows = []
    for _ in range(CYCLES_PER_MACHINE):
        reading = generate_reading(m)
        feats = fb.update(reading)
        rows.append((feats, reading["state"] == "FAULT"))
    return rows


def build_dataset():
    X, y = [], []
    for i in range(NUM_MACHINES):
        rows = simulate_machine_history(i)
        states = [is_fault for _, is_fault in rows]
        for idx, (feats, _) in enumerate(rows):
            future_window = states[idx + 1: idx + 1 + LOOKAHEAD]
            label = 1 if any(future_window) else 0
            X.append([feats[name] for name in FEATURE_NAMES])
            y.append(label)
    return np.array(X), np.array(y)


def main():
    print("Simulating training data...")
    X, y = build_dataset()
    print(f"Dataset: {X.shape[0]} rows, positive rate: {y.mean():.3f}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("Training failure-prediction model...")
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=8, class_weight="balanced", random_state=42
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred, digits=3))

    print("Training anomaly-detection model...")
    normal_X = X_train[y_train == 0]     # fit only on rows not about to fail
    iso = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    iso.fit(normal_X)

    joblib.dump(clf, "failure_model.joblib")
    joblib.dump(iso, "anomaly_model.joblib")
    print("Saved failure_model.joblib and anomaly_model.joblib")


if __name__ == "__main__":
    main()

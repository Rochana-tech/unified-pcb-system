"""
Training entry point for Layer 2A's ANN fault classifier.

Pipeline: load CSV -> train/val/test split -> fit scaler on train only ->
normalize all splits -> train ANN on train (+ internal val via
early_stopping) -> evaluate on held-out test -> save model + scaler +
metadata.

Run:
    python -m model.train --industry electronics_pcb

Training is intentionally kept separate from inference (predictor.py):
this script never runs in the real-time path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from layers.layer2a.config.industry_config import load_industry_config  # noqa: E402
from layers.layer2a.model.architecture import build_ann  # noqa: E402
from layers.layer2a.model.evaluate import evaluate  # noqa: E402
from layers.layer2a.preprocessing.scaler import fit_scaler, save_scaler, transform  # noqa: E402


def load_dataset(industry: str) -> pd.DataFrame:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(
        project_root, "data", "datasets", f"{industry}_synthetic.csv"
    )
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No dataset found at {path}. Generate one first with: "
            f"python -m data.generate_synthetic --industry {industry}"
        )
    return pd.read_csv(path)


def train(industry: str, test_size: float = 0.15, val_size: float = 0.15) -> dict:
    cfg = load_industry_config(industry)
    df = load_dataset(industry)

    missing = set(cfg.features) - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required feature columns: {missing}")

    X = df[cfg.features].to_numpy(dtype=float)
    y = df["fault_type"].to_numpy()

    unknown_labels = set(y) - set(cfg.fault_classes)
    if unknown_labels:
        raise ValueError(
            f"Dataset contains labels not in config.fault_classes: {unknown_labels}"
        )

    # Encode string labels to integers using the config's declared class
    # order (not sklearn's alphabetical LabelEncoder default) so the
    # mapping is stable and traceable back to electronics_pcb.yaml.
    class_to_idx = {name: i for i, name in enumerate(cfg.fault_classes)}
    idx_to_class = {i: name for name, i in class_to_idx.items()}
    y_encoded = np.array([class_to_idx[label] for label in y])

    # First split off the test set, then split remaining into train/val.
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y_encoded, test_size=test_size, random_state=42, stratify=y_encoded
    )
    relative_val_size = val_size / (1.0 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp,
        y_temp,
        test_size=relative_val_size,
        random_state=42,
        stratify=y_temp,
    )

    # Fit scaler on TRAIN ONLY, apply to all three splits.
    scaler = fit_scaler(X_train)
    X_train_scaled = transform(scaler, X_train)
    X_val_scaled = transform(scaler, X_val)
    X_test_scaled = transform(scaler, X_test)

    ann = build_ann()
    ann.fit(X_train_scaled, y_train)

    # Decode back to fault-type strings for human-readable evaluation
    # (evaluate.py and its reports operate on the class name strings).
    def decode(arr):
        return np.array([idx_to_class[i] for i in arr])

    # Held-out validation report (separate from sklearn's internal
    # early-stopping validation slice, which only sees training data).
    val_pred = ann.predict(X_val_scaled)
    val_report = evaluate(decode(y_val), decode(val_pred), cfg.fault_classes)

    # Final, decisive report on the untouched test set.
    test_pred = ann.predict(X_test_scaled)
    test_report = evaluate(decode(y_test), decode(test_pred), cfg.fault_classes)

    print("=== Validation set ===")
    print(val_report.pretty_print())
    print()
    print("=== Test set (held out) ===")
    print(test_report.pretty_print())

    # Save artifacts.
    os.makedirs(os.path.dirname(cfg.absolute_model_path()), exist_ok=True)
    import joblib

    joblib.dump(ann, cfg.absolute_model_path())
    save_scaler(scaler, cfg.absolute_scaler_path())

    metadata = {
        "industry": industry,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "features": cfg.features,
        "fault_classes": cfg.fault_classes,
        "class_index_mapping": idx_to_class,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "validation_metrics": val_report.as_dict(),
        "test_metrics": test_report.as_dict(),
        "architecture": {
            "type": "MLPClassifier (feed-forward ANN, backprop-trained)",
            "hidden_layer_sizes": list(ann.hidden_layer_sizes)
            if isinstance(ann.hidden_layer_sizes, tuple)
            else ann.hidden_layer_sizes,
            "activation": ann.activation,
            "solver": ann.solver,
        },
    }
    with open(cfg.absolute_metadata_path(), "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nSaved model to      {cfg.absolute_model_path()}")
    print(f"Saved scaler to     {cfg.absolute_scaler_path()}")
    print(f"Saved metadata to   {cfg.absolute_metadata_path()}")

    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry", default="electronics_pcb")
    parser.add_argument("--test-size", type=float, default=0.15)
    parser.add_argument("--val-size", type=float, default=0.15)
    args = parser.parse_args()
    train(args.industry, test_size=args.test_size, val_size=args.val_size)


if __name__ == "__main__":
    main()

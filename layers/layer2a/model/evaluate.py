"""
Evaluation metrics for Layer 2A's ANN.

Kept separate from train.py so the same metric computation can be reused
by training (reporting on the held-out test set) and by tests (checking
the predictor's live behavior against expectations).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
)


@dataclass
class EvaluationReport:
    accuracy: float
    precision_macro: float
    recall_macro: float
    confusion_matrix: np.ndarray
    class_labels: List[str]

    def as_dict(self) -> dict:
        return {
            "accuracy": round(float(self.accuracy), 4),
            "precision_macro": round(float(self.precision_macro), 4),
            "recall_macro": round(float(self.recall_macro), 4),
            "confusion_matrix": self.confusion_matrix.tolist(),
            "class_labels": self.class_labels,
        }

    def pretty_print(self) -> str:
        lines = [
            f"Accuracy:           {self.accuracy:.4f}",
            f"Precision (macro):  {self.precision_macro:.4f}",
            f"Recall (macro):     {self.recall_macro:.4f}",
            "",
            "Confusion matrix (rows=actual, cols=predicted):",
            "labels: " + ", ".join(self.class_labels),
        ]
        for label, row in zip(self.class_labels, self.confusion_matrix):
            lines.append(f"  {label:>16s}: {row.tolist()}")
        return "\n".join(lines)


def evaluate(
    y_true: np.ndarray, y_pred: np.ndarray, class_labels: List[str]
) -> EvaluationReport:
    """Compute accuracy, macro precision/recall, and confusion matrix."""
    return EvaluationReport(
        accuracy=accuracy_score(y_true, y_pred),
        precision_macro=precision_score(
            y_true, y_pred, average="macro", labels=class_labels, zero_division=0
        ),
        recall_macro=recall_score(
            y_true, y_pred, average="macro", labels=class_labels, zero_division=0
        ),
        confusion_matrix=confusion_matrix(y_true, y_pred, labels=class_labels),
        class_labels=class_labels,
    )

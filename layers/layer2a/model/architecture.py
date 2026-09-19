"""
ANN architecture for Layer 2A fault classification.

This is a genuine feed-forward artificial neural network (multi-layer
perceptron) trained via backpropagation — not a rule-based/if-else
classifier. Implemented with sklearn's MLPClassifier, which:
  - trains real weighted connections across hidden layers with a
    nonlinear activation (ReLU) and backprop (Adam optimizer),
  - exposes predict_proba for confidence scores,
  - saves/loads cleanly via joblib.

Wrapped in a small factory function so swapping the architecture later
(e.g. deeper network, different framework) only touches this file —
nothing else in the pipeline depends on sklearn specifically.
"""

from __future__ import annotations

from sklearn.neural_network import MLPClassifier

DEFAULT_HIDDEN_LAYER_SIZES = (16, 8)
DEFAULT_MAX_ITER = 2000
DEFAULT_RANDOM_STATE = 42


def build_ann(
    hidden_layer_sizes: tuple = DEFAULT_HIDDEN_LAYER_SIZES,
    max_iter: int = DEFAULT_MAX_ITER,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> MLPClassifier:
    """
    Build an untrained ANN classifier.

    Architecture: 4 input features -> hidden_layer_sizes (ReLU) -> softmax
    over fault classes. early_stopping carves out an internal validation
    slice from the training set to avoid overfitting during training.
    """
    return MLPClassifier(
        hidden_layer_sizes=hidden_layer_sizes,
        activation="relu",
        solver="adam",
        alpha=1e-4,
        max_iter=max_iter,
        random_state=random_state,
        early_stopping=True,
        n_iter_no_change=20,
        validation_fraction=0.1,
    )

"""
Industry config registry for Layer 2A.

Layer 2A must be "configurable" rather than hard-coding industry logic:
this module is the single place that knows which industries exist, what
their feature/class schema is, and where their trained artifacts live.

Add a new industry by dropping a new <industry>.yaml file next to this
file (same schema as electronics_pcb.yaml) — no other code changes needed
to register it. Training a model for it is a separate step (see model/train.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CONFIG_DIR)


class IndustryNotFoundError(Exception):
    """Raised when a requested industry has no config file at all."""


class IndustryModelNotTrainedError(Exception):
    """
    Raised when an industry is configured but has no trained model yet.

    This is intentional: an untrained industry must fail loudly, never
    silently reuse another industry's model.
    """


@dataclass(frozen=True)
class SeverityRule:
    default: str
    low_confidence_below: float | None = None
    low_confidence_severity: str | None = None


@dataclass(frozen=True)
class IndustryConfig:
    industry: str
    display_name: str
    status: str  # "trained" or "not_trained"
    features: List[str]
    fault_classes: List[str]
    severity_rules: Dict[str, SeverityRule]
    model_path: str
    scaler_path: str
    metadata_path: str

    @property
    def is_trained(self) -> bool:
        return self.status == "trained"

    def absolute_model_path(self) -> str:
        return os.path.join(_PROJECT_ROOT, self.model_path)

    def absolute_scaler_path(self) -> str:
        return os.path.join(_PROJECT_ROOT, self.scaler_path)

    def absolute_metadata_path(self) -> str:
        return os.path.join(_PROJECT_ROOT, self.metadata_path)


def _parse_config(raw: dict) -> IndustryConfig:
    severity_rules = {
        fault_type: SeverityRule(
            default=rule["default"],
            low_confidence_below=rule.get("low_confidence_below"),
            low_confidence_severity=rule.get("low_confidence_severity"),
        )
        for fault_type, rule in raw["severity_rules"].items()
    }
    artifacts = raw["artifacts"]
    return IndustryConfig(
        industry=raw["industry"],
        display_name=raw["display_name"],
        status=raw["status"],
        features=list(raw["features"]),
        fault_classes=list(raw["fault_classes"]),
        severity_rules=severity_rules,
        model_path=artifacts["model_path"],
        scaler_path=artifacts["scaler_path"],
        metadata_path=artifacts["metadata_path"],
    )


def list_available_industries() -> List[str]:
    """Return industry names for every *.yaml config found in this directory."""
    names = []
    for filename in os.listdir(_CONFIG_DIR):
        if filename.endswith(".yaml"):
            names.append(filename[: -len(".yaml")])
    return sorted(names)


def load_industry_config(industry: str) -> IndustryConfig:
    """
    Load and parse the config for one industry.

    Raises IndustryNotFoundError if no such config file exists.
    Does NOT check whether the model is trained — callers that need a
    usable model should call require_trained_config() instead.
    """
    path = os.path.join(_CONFIG_DIR, f"{industry}.yaml")
    if not os.path.exists(path):
        available = ", ".join(list_available_industries()) or "(none)"
        raise IndustryNotFoundError(
            f"No config found for industry '{industry}'. Available: {available}"
        )
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return _parse_config(raw)


def require_trained_config(industry: str) -> IndustryConfig:
    """
    Load a config and guarantee it is trained and ready for inference.

    Raises IndustryModelNotTrainedError (not a silent fallback) if the
    industry exists but has no trained model.
    """
    cfg = load_industry_config(industry)
    if not cfg.is_trained:
        raise IndustryModelNotTrainedError(
            f"Industry '{industry}' is configured but has no trained model yet. "
            f"Train one with model/train.py before requesting inference."
        )
    if not os.path.exists(cfg.absolute_model_path()):
        raise IndustryModelNotTrainedError(
            f"Industry '{industry}' is marked trained in config but model file "
            f"is missing at {cfg.absolute_model_path()}. Retrain before use."
        )
    return cfg

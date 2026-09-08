"""Load and run the trained PR suggestion coverage model."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from pr_suggestion_metrics.feature_preprocessing import coerce_boolean_series


_DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "pr_suggestion_coverage"
_DEFAULT_REGRESSION_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "pr_suggestion_coverage_regression"
_PERCENTAGE_BUCKETS = (
    "0",
    "1-10",
    "11-20",
    "21-30",
    "31-40",
    "41-50",
    "51-60",
    "61-70",
    "71-80",
    "81-90",
    "91-100",
)


def percentage_bucket(value: int | float) -> str:
    """Map a percentage to the shared reporting bucket scheme."""
    percentage = max(0, min(100, int(round(value))))
    if percentage == 0:
        return "0"
    lower_bound = ((percentage - 1) // 10) * 10 + 1
    upper_bound = min(lower_bound + 9, 100)
    return f"{lower_bound}-{upper_bound}"


def load_model_bundle(model_dir: Path = _DEFAULT_MODEL_DIR) -> tuple[Any, dict[str, Any]]:
    """Load the trained estimator and its feature schema.

    Args:
        model_dir: Directory containing `model.joblib` and `feature_schema.json`.

    Returns:
        The sklearn pipeline and the JSON feature schema used during training.

    Raises:
        FileNotFoundError: If the model or schema artifact is missing.
    """
    model_path = model_dir / "model.joblib"
    schema_path = model_dir / "feature_schema.json"

    model = joblib.load(model_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return model, schema


def prepare_model_features(rows: pd.DataFrame | Sequence[Mapping[str, Any]], schema: Mapping[str, Any]) -> pd.DataFrame:
    """Build a model-ready feature frame from metric rows.

    Args:
        rows: One or more metric rows produced by `evaluate_metrics.py`.
        schema: Feature schema loaded from `feature_schema.json`.

    Returns:
        DataFrame containing exactly the columns expected by the trained model.

    Raises:
        ValueError: If required feature columns are missing.
    """
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    feature_columns = list(schema["feature_columns"])
    missing_features = [feature for feature in feature_columns if feature not in frame.columns]
    if missing_features:
        raise ValueError(f"Missing model features: {missing_features}")

    for feature in schema["numeric_features"]:
        frame[feature] = pd.to_numeric(frame[feature], errors="coerce")
    for feature in schema["boolean_features"]:
        frame[feature] = coerce_boolean_series(frame[feature], feature)
    for feature in schema["categorical_features"]:
        frame[feature] = frame[feature].fillna("none").replace("", "none").astype(str)

    return frame[feature_columns]


def predict_coverage_labels(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    model_dir: Path = _DEFAULT_MODEL_DIR,
) -> pd.DataFrame:
    """Predict coverage labels for metric rows using the saved sklearn model.

    Args:
        rows: One or more metric rows produced by `evaluate_metrics.py`.
        model_dir: Directory containing the saved model artifacts.

    Returns:
        DataFrame with `model_prediction` and probability columns when available.
    """
    model, schema = load_model_bundle(model_dir)
    features = prepare_model_features(rows, schema)
    predictions = model.predict(features)
    result = pd.DataFrame({"model_prediction": predictions})

    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(features)
        class_labels = [str(label) for label in model.classes_]
        for index, class_label in enumerate(class_labels):
            result[f"probability_{class_label}"] = np.asarray(probabilities)[:, index]

    return result


def predict_coverage_percentages(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    model_dir: Path = _DEFAULT_REGRESSION_MODEL_DIR,
) -> pd.DataFrame:
    """Predict 0-100 coverage percentages.

    Args:
        rows: One or more metric rows produced by `evaluate_metrics.py`.
        model_dir: Directory containing the saved regression model artifacts.

    Returns:
        DataFrame with the model's `model_predicted_percentage` output.
    """
    model, schema = load_model_bundle(model_dir)
    features = prepare_model_features(rows, schema)
    raw_predictions = np.asarray(model.predict(features), dtype=float)
    clipped_predictions = np.clip(raw_predictions, 0, 100)
    rounded_predictions = np.rint(clipped_predictions).astype(int)
    return pd.DataFrame({"model_predicted_percentage": rounded_predictions})

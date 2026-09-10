"""Load and run the trained PR suggestion coverage model."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from pr_suggestion_metrics.feature_preprocessing import coerce_boolean_series, coerce_numeric_series
from pr_suggestion_metrics.diff_semantics import analyze_change_coverage
from pr_suggestion_metrics.model_artifacts import verify_model_manifest
from pr_suggestion_metrics.uncertainty import apply_conformal_intervals, load_uncertainty_calibration


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
    """Verify and load a trusted local estimator and its feature schema.

    Args:
        model_dir: Directory containing `model.joblib` and `feature_schema.json`.

    Returns:
        The sklearn pipeline and the JSON feature schema used during training.

    Raises:
        FileNotFoundError: If the model, schema, or manifest artifact is missing.
        ValueError: If the artifact manifest or hashes are invalid.

    Warning:
        Joblib files use pickle semantics. Only load artifacts from a trusted source;
        the manifest detects mismatches but does not establish publisher authenticity.
    """
    manifest = verify_model_manifest(model_dir)
    model_path = model_dir / manifest["model_file"]
    schema_path = model_dir / manifest["schema_file"]

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

    row_ids = frame["example_id"].tolist() if "example_id" in frame.columns else None
    for feature in schema["numeric_features"]:
        frame[feature] = coerce_numeric_series(frame[feature], feature, row_ids=row_ids)
    for feature in schema["boolean_features"]:
        frame[feature] = coerce_boolean_series(frame[feature], feature, row_ids=row_ids)
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
    result = pd.DataFrame({"model_prediction": predictions}, index=features.index)

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
    return pd.DataFrame({"model_predicted_percentage": rounded_predictions}, index=features.index)


def predict_coverage_with_uncertainty(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    model_dir: Path = _DEFAULT_REGRESSION_MODEL_DIR,
    *,
    calibration_path: Path | None = None,
) -> pd.DataFrame:
    """Predict percentages with intervals from a matching split-conformal calibration artifact."""
    predictions = predict_coverage_percentages(rows, model_dir=model_dir)
    calibration = load_uncertainty_calibration(model_dir, calibration_path)
    intervals = apply_conformal_intervals(
        predictions["model_predicted_percentage"].to_numpy(dtype=float),
        calibration.residual_quantile,
    )
    result = predictions.copy()
    result["interval_lower"] = np.floor(intervals[:, 0]).astype(int)
    result["interval_upper"] = np.ceil(intervals[:, 1]).astype(int)
    result["interval_coverage"] = 1.0 - calibration.alpha
    return result


def predict_coverage_from_diffs(
    suggested_diff: str,
    merged_pr_diff: str,
    *,
    example_id: str | None = None,
    model_dir: Path = _DEFAULT_REGRESSION_MODEL_DIR,
    enable_gumtree: bool = False,
) -> dict[str, Any]:
    """Predict coverage directly from one supported suggestion and merged-PR diff pair.

    The current public boundary intentionally abstains on deletions, replacements,
    renames, and multi-file or multi-hunk suggestions until those semantics are modeled.
    """
    from pr_suggestion_metrics.evaluate_metrics import (
        metric_result_to_feature_row,
        raw_diff_support_issues,
        score_diff_pair,
    )

    support_issues = raw_diff_support_issues(suggested_diff)
    deterministic_evidence = analyze_change_coverage(suggested_diff, merged_pr_diff)
    if support_issues:
        return {
            "example_id": example_id,
            "status": "abstained",
            "model_predicted_percentage": None,
            "heuristic_coverage_score": None,
            "change_coverage_evidence": deterministic_evidence.model_dump(mode="json"),
            "uncertainty": {"status": "unavailable", "reason": "model abstained"},
            "warnings": support_issues,
        }

    metric_result = score_diff_pair(suggested_diff, merged_pr_diff, enable_gumtree=enable_gumtree)
    feature_row = metric_result_to_feature_row(metric_result)
    if example_id is not None:
        feature_row["example_id"] = example_id
    calibration_path = model_dir / "uncertainty_calibration.json"
    if calibration_path.is_file():
        prediction = predict_coverage_with_uncertainty([feature_row], model_dir=model_dir)
        uncertainty = {
            "status": "calibrated",
            "lower": int(prediction.iloc[0]["interval_lower"]),
            "upper": int(prediction.iloc[0]["interval_upper"]),
            "coverage": float(prediction.iloc[0]["interval_coverage"]),
        }
    else:
        prediction = predict_coverage_percentages([feature_row], model_dir=model_dir)
        uncertainty = {
            "status": "unavailable",
            "reason": "no matching held-out uncertainty calibration artifact",
        }
    return {
        "example_id": example_id,
        "status": "predicted",
        "model_predicted_percentage": int(prediction.iloc[0]["model_predicted_percentage"]),
        "heuristic_coverage_score": metric_result.predicted_percentage,
        "change_coverage_evidence": deterministic_evidence.model_dump(mode="json"),
        "uncertainty": uncertainty,
        "warnings": [
            "Experimental estimate from PR-diff overlap; it does not establish causal adoption or persistence "
            "in the final repository state."
        ],
    }

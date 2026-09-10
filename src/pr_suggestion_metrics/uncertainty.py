"""Split-conformal uncertainty calibration bound to one model artifact."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from pr_suggestion_metrics.model_artifacts import sha256_file, verify_model_manifest


CALIBRATION_FILENAME = "uncertainty_calibration.json"


class UncertaintyCalibration(BaseModel):
    """Finite-sample absolute-residual interval calibration metadata."""

    manifest_version: int = 1
    created_at_utc: str
    method: str = "split_conformal_absolute_residual"
    alpha: float = Field(gt=0.0, lt=1.0)
    residual_quantile: float = Field(ge=0.0)
    calibration_rows: int = Field(ge=1)
    calibration_groups: int = Field(ge=1)
    target_column: str
    group_column: str
    calibration_data_sha256: str
    model_sha256: str
    schema_sha256: str


def conformal_residual_quantile(
    actual: np.ndarray | list[float],
    predicted: np.ndarray | list[float],
    *,
    alpha: float,
) -> float:
    """Return the finite-sample split-conformal absolute-residual quantile."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.ndim != 1 or predicted_array.ndim != 1 or len(actual_array) != len(predicted_array):
        raise ValueError("actual and predicted must be equal-length one-dimensional arrays")
    if len(actual_array) == 0:
        raise ValueError("calibration arrays must not be empty")
    if not np.isfinite(actual_array).all() or not np.isfinite(predicted_array).all():
        raise ValueError("calibration values must be finite")
    residuals = np.sort(np.abs(actual_array - predicted_array))
    rank = min(len(residuals), math.ceil((len(residuals) + 1) * (1.0 - alpha)))
    return float(residuals[rank - 1])


def apply_conformal_intervals(predicted: np.ndarray | list[float], residual_quantile: float) -> np.ndarray:
    """Apply a symmetric bounded conformal interval to percentage predictions."""
    if residual_quantile < 0 or not math.isfinite(residual_quantile):
        raise ValueError("residual_quantile must be a finite non-negative number")
    predictions = np.asarray(predicted, dtype=float)
    lower = np.clip(predictions - residual_quantile, 0, 100)
    upper = np.clip(predictions + residual_quantile, 0, 100)
    return np.column_stack((lower, upper))


def load_uncertainty_calibration(model_dir: Path, calibration_path: Path | None = None) -> UncertaintyCalibration:
    """Load calibration metadata and verify it belongs to the current model/schema bytes."""
    path = calibration_path or model_dir / CALIBRATION_FILENAME
    calibration = UncertaintyCalibration.model_validate_json(path.read_text(encoding="utf-8"))
    manifest = verify_model_manifest(model_dir)
    if calibration.model_sha256 != manifest["model_sha256"]:
        raise ValueError("Uncertainty calibration does not match the model artifact")
    if calibration.schema_sha256 != manifest["schema_sha256"]:
        raise ValueError("Uncertainty calibration does not match the feature schema")
    return calibration


def write_uncertainty_calibration(
    *,
    model_dir: Path,
    calibration_path: Path,
    target_column: str,
    group_column: str,
    alpha: float,
    minimum_rows: int = 100,
    minimum_groups: int = 20,
) -> Path:
    """Fit and write calibration from a dedicated, non-test feature table."""
    from pr_suggestion_metrics.model_inference import predict_coverage_percentages

    rows = pd.read_csv(calibration_path)
    missing = [column for column in (target_column, group_column) if column not in rows.columns]
    if missing:
        raise ValueError(f"Calibration data is missing required columns: {missing}")
    if "split" in rows.columns and rows["split"].astype(str).str.lower().eq("test").any():
        raise ValueError("Test rows must never be used for uncertainty calibration")
    if len(rows) < minimum_rows:
        raise ValueError(f"Calibration requires at least {minimum_rows} rows; received {len(rows)}")
    group_count = rows[group_column].nunique(dropna=True)
    if group_count < minimum_groups:
        raise ValueError(f"Calibration requires at least {minimum_groups} independent groups; received {group_count}")

    actual = pd.to_numeric(rows[target_column], errors="raise").to_numpy(dtype=float)
    if np.any((actual < 0) | (actual > 100)):
        raise ValueError("Calibration targets must be between 0 and 100")
    predictions = predict_coverage_percentages(rows, model_dir=model_dir)["model_predicted_percentage"].to_numpy()
    quantile = conformal_residual_quantile(actual, predictions, alpha=alpha)
    manifest = verify_model_manifest(model_dir)
    calibration = UncertaintyCalibration(
        created_at_utc=datetime.now(UTC).isoformat(),
        alpha=alpha,
        residual_quantile=quantile,
        calibration_rows=len(rows),
        calibration_groups=group_count,
        target_column=target_column,
        group_column=group_column,
        calibration_data_sha256=sha256_file(calibration_path),
        model_sha256=manifest["model_sha256"],
        schema_sha256=manifest["schema_sha256"],
    )
    output_path = model_dir / CALIBRATION_FILENAME
    output_path.write_text(calibration.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    """Parse uncertainty-calibration arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--calibration-data", type=Path, required=True)
    parser.add_argument("--target-column", default="coverage_percentage")
    parser.add_argument("--group-column", default="group_id")
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--minimum-rows", type=int, default=100)
    parser.add_argument("--minimum-groups", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    """Create an uncertainty calibration artifact from dedicated calibration data."""
    args = parse_args()
    output_path = write_uncertainty_calibration(
        model_dir=args.model_dir,
        calibration_path=args.calibration_data,
        target_column=args.target_column,
        group_column=args.group_column,
        alpha=args.alpha,
        minimum_rows=args.minimum_rows,
        minimum_groups=args.minimum_groups,
    )
    print(json.dumps({"calibration_path": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

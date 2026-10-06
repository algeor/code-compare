"""Select and package a percentage model under a frozen benchmark."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pr_suggestion_metrics.artifact_io import staged_output_directory
from pr_suggestion_metrics.benchmark.build_features import build_frozen_feature_tables
from pr_suggestion_metrics.features.policy import NORMALIZATION_POLICY_VERSION
from pr_suggestion_metrics.model_artifacts import sha256_file, verify_model_manifest
from pr_suggestion_metrics.model_inference import percentage_prediction_frame
from pr_suggestion_metrics.percentages import round_bounded_percentage


_BENCHMARK_ARTIFACTS = {
    "train": "train.jsonl",
    "development": "development.jsonl",
    "calibration": "calibration.jsonl",
    "test": "test_inputs.jsonl",
    "private_test_labels": "test_labels.private.jsonl",
}


def _metric_report(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    rounded = round_bounded_percentage(predicted)
    errors = np.abs(actual - rounded)
    report: dict[str, float | None] = {
        "percentage_mae": float(np.mean(errors)),
        "percentage_rmse": float(math.sqrt(np.mean(np.square(actual - rounded)))),
        "within_5_points": float(np.mean(errors <= 5)),
        "within_10_points": float(np.mean(errors <= 10)),
        "dangerous_error_rate": float(
            np.mean(((rounded >= 80) & (actual <= 20)) | ((rounded <= 20) & (actual >= 80)))
        ),
        "r2": None,
    }
    if len(actual) >= 2 and float(np.var(actual)) > 0.0:
        residual_sum = float(np.sum(np.square(actual - rounded)))
        total_sum = float(np.sum(np.square(actual - np.mean(actual))))
        report["r2"] = 1.0 - residual_sum / total_sum
    return report


def _load_and_verify_benchmark(benchmark_dir: Path) -> dict[str, Any]:
    manifest_path = benchmark_dir / "benchmark_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Benchmark manifest must be a JSON object")
    artifact_hashes = manifest.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("Benchmark manifest is missing artifact_sha256")
    for artifact_name, file_name in _BENCHMARK_ARTIFACTS.items():
        expected_hash = artifact_hashes.get(artifact_name)
        if not isinstance(expected_hash, str):
            raise ValueError(f"Benchmark manifest is missing {artifact_name} hash")
        artifact_path = benchmark_dir / file_name
        if not artifact_path.is_file():
            raise ValueError(f"Frozen benchmark is missing {file_name}")
        if sha256_file(artifact_path) != expected_hash:
            raise ValueError(f"Frozen benchmark artifact changed since manifest: {file_name}")
    return manifest


def _load_feature_rows(features_path: Path) -> pd.DataFrame:
    rows = pd.read_csv(features_path)
    required = {"example_id", "split", "coverage_percentage", "normalization_policy_version"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Feature table is missing required columns: {missing}")
    policy_versions = rows["normalization_policy_version"].astype("string").str.strip()
    if policy_versions.isna().any() or not policy_versions.eq(NORMALIZATION_POLICY_VERSION).all():
        raise ValueError("Feature table normalization policy does not match runtime policy")
    split_counts = rows["split"].astype("string").value_counts().to_dict()
    for split in ("train", "development", "calibration"):
        if int(split_counts.get(split, 0)) <= 0:
            raise ValueError(f"Feature table must contain a non-empty {split} split")
    return rows


def _baseline_reports(train_rows: pd.DataFrame, development_rows: pd.DataFrame) -> list[dict[str, Any]]:
    actual = development_rows["coverage_percentage"].to_numpy(dtype=float)
    baselines: list[tuple[str, np.ndarray]] = [
        ("constant_train_mean", np.full(len(development_rows), float(train_rows["coverage_percentage"].mean()))),
        ("constant_train_median", np.full(len(development_rows), float(train_rows["coverage_percentage"].median()))),
    ]
    for column in ("predicted_percentage", "line_recall", "token_recall", "best_hunk_token_recall"):
        if column not in development_rows.columns:
            continue
        values = development_rows[column].to_numpy(dtype=float)
        if column.endswith("recall"):
            values = values * 100.0
        baselines.append((f"baseline_{column}", values))
    return [
        {"name": name, "development_metrics": _metric_report(actual, predictions)}
        for name, predictions in baselines
    ]


def _model_reports(development_rows: pd.DataFrame, candidate_model_dirs: list[Path]) -> list[dict[str, Any]]:
    actual = development_rows["coverage_percentage"].to_numpy(dtype=float)
    reports: list[dict[str, Any]] = []
    for model_dir in candidate_model_dirs:
        try:
            manifest = verify_model_manifest(model_dir)
            predictions = percentage_prediction_frame(development_rows, model_dir=model_dir)
            reports.append(
                {
                    "model_dir": str(model_dir),
                    "model_name": manifest.get("model_name"),
                    "model_sha256": manifest.get("model_sha256"),
                    "status": "evaluated",
                    "development_metrics": _metric_report(
                        actual,
                        predictions["model_raw_percentage"].to_numpy(dtype=float),
                    ),
                }
            )
        except (FileNotFoundError, ValueError, TypeError) as exc:
            reports.append({"model_dir": str(model_dir), "status": "rejected", "reason": str(exc)})
    return reports


def select_model_for_release(
    *,
    benchmark_dir: Path,
    output_dir: Path,
    candidate_model_dirs: list[Path],
    minimum_mae_improvement: float = 0.0,
) -> dict[str, Any]:
    """Evaluate existing models against development rows and package only a justified winner."""
    if minimum_mae_improvement < 0.0:
        raise ValueError("minimum_mae_improvement must be non-negative")
    benchmark_manifest = _load_and_verify_benchmark(benchmark_dir)
    if output_dir.exists():
        raise FileExistsError(f"Selection output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with staged_output_directory(output_dir) as staging_dir:
        build_frozen_feature_tables(benchmark_dir=benchmark_dir, output_dir=staging_dir / "features")
        feature_rows = _load_feature_rows(staging_dir / "features" / "features.csv")
        train_rows = feature_rows.loc[feature_rows["split"].eq("train")].copy()
        development_rows = feature_rows.loc[feature_rows["split"].eq("development")].copy()
        baseline_reports = _baseline_reports(train_rows, development_rows)
        model_reports = _model_reports(development_rows, candidate_model_dirs)
        successful_models = [row for row in model_reports if row["status"] == "evaluated"]
        best_baseline = min(baseline_reports, key=lambda row: row["development_metrics"]["percentage_mae"])
        best_model = (
            min(successful_models, key=lambda row: row["development_metrics"]["percentage_mae"])
            if successful_models
            else None
        )

        decision = "use_baseline_or_train_new_model"
        selected_model: dict[str, Any] | None = None
        if best_model is not None:
            model_mae = float(best_model["development_metrics"]["percentage_mae"])
            baseline_mae = float(best_baseline["development_metrics"]["percentage_mae"])
            if model_mae + minimum_mae_improvement <= baseline_mae:
                source_model_dir = Path(str(best_model["model_dir"]))
                packaged_model_dir = staging_dir / "selected_model"
                shutil.copytree(source_model_dir, packaged_model_dir, symlinks=False)
                selected_model = {
                    **best_model,
                    "packaged_model_dir": str(packaged_model_dir.name),
                    "artifact_manifest_sha256": sha256_file(packaged_model_dir / "artifact_manifest.json"),
                }
                decision = "package_existing_model"

        report = {
            "schema_version": "1.0",
            "phase": "6",
            "decision": decision,
            "benchmark_manifest_sha256": sha256_file(benchmark_dir / "benchmark_manifest.json"),
            "benchmark_annotation_mode": benchmark_manifest.get("annotation_mode"),
            "benchmark_ground_truth_claim": benchmark_manifest.get("ground_truth_claim"),
            "feature_manifest_sha256": sha256_file(staging_dir / "features" / "feature_manifest.json"),
            "feature_rows": int(len(feature_rows)),
            "split_counts": {key: int(value) for key, value in feature_rows["split"].value_counts().to_dict().items()},
            "minimum_mae_improvement": minimum_mae_improvement,
            "best_baseline": best_baseline,
            "candidate_models": model_reports,
            "selected_model": selected_model,
            "next_required_steps": [
                "train a new model only if no existing model beats baselines on development",
                "calibrate uncertainty on calibration split only",
                "consume protected test labels exactly once after model and thresholds are locked",
            ],
        }
        (staging_dir / "selection_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-model-dir", type=Path, action="append", default=[])
    parser.add_argument("--minimum-mae-improvement", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = select_model_for_release(
        benchmark_dir=args.benchmark_dir,
        output_dir=args.output_dir,
        candidate_model_dirs=args.candidate_model_dir,
        minimum_mae_improvement=args.minimum_mae_improvement,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

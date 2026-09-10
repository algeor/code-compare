"""Run one sealed confirmatory evaluation against private frozen test labels."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pr_suggestion_metrics.model_artifacts import sha256_file, verify_model_manifest
from pr_suggestion_metrics.model_inference import predict_coverage_from_diffs


RECEIPT_FILENAME = "CONFIRMATORY_TEST_CONSUMED.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            rows.append(value)
    return rows


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    errors = np.abs(actual - predicted)
    return {
        "mae": float(np.mean(errors)),
        "rmse": float(math.sqrt(np.mean(np.square(actual - predicted)))),
        "within_5_points": float(np.mean(errors <= 5)),
        "within_10_points": float(np.mean(errors <= 10)),
        "dangerous_endpoint_error_rate": float(
            np.mean(((predicted >= 80) & (actual <= 20)) | ((predicted <= 20) & (actual >= 80)))
        ),
    }


def _verify_benchmark_artifacts(benchmark_dir: Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    artifact_hashes = manifest.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("Benchmark manifest is missing artifact_sha256")
    test_inputs_path = benchmark_dir / "test_inputs.jsonl"
    private_labels_path = benchmark_dir / "test_labels.private.jsonl"
    expected_test_hash = artifact_hashes.get("test")
    expected_label_hash = artifact_hashes.get("private_test_labels")
    if sha256_file(test_inputs_path) != expected_test_hash:
        raise ValueError("Frozen test inputs do not match the benchmark manifest")
    if sha256_file(private_labels_path) != expected_label_hash:
        raise ValueError("Private test labels do not match the benchmark manifest")
    return test_inputs_path, private_labels_path


def evaluate_frozen_benchmark(*, benchmark_dir: Path, model_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Evaluate once, reporting abstention and intervals without tuning on test labels."""
    receipt_path = benchmark_dir / RECEIPT_FILENAME
    if receipt_path.exists():
        raise RuntimeError(f"Confirmatory test was already consumed: {receipt_path}")
    benchmark_manifest_path = benchmark_dir / "benchmark_manifest.json"
    benchmark_manifest = json.loads(benchmark_manifest_path.read_text(encoding="utf-8"))
    test_inputs_path, private_labels_path = _verify_benchmark_artifacts(benchmark_dir, benchmark_manifest)
    model_manifest = verify_model_manifest(model_dir)
    output_dir.mkdir(parents=True, exist_ok=False)

    test_rows = _read_jsonl(test_inputs_path)
    predictions: list[dict[str, Any]] = []
    for row in test_rows:
        prediction = predict_coverage_from_diffs(
            str(row["suggested_diff"]),
            str(row["landed_diff"]),
            example_id=str(row["example_id"]),
            model_dir=model_dir,
        )
        predictions.append(prediction)
    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )

    private_labels = _read_jsonl(private_labels_path)
    label_by_id = {str(row["example_id"]): float(row["coverage_unrounded"]) for row in private_labels}
    if set(label_by_id) != {str(row["example_id"]) for row in test_rows}:
        raise ValueError("Private labels and frozen test inputs have different example IDs")

    estimated = [row for row in predictions if row.get("status") == "predicted"]
    estimated_ids = [str(row["example_id"]) for row in estimated]
    actual = np.array([label_by_id[example_id] for example_id in estimated_ids], dtype=float)
    predicted = np.array([float(row["model_predicted_percentage"]) for row in estimated], dtype=float)
    point_metrics = _metrics(actual, predicted) if len(estimated) else None

    calibrated = [row for row in estimated if row.get("uncertainty", {}).get("status") == "calibrated"]
    interval_coverage = None
    mean_interval_width = None
    if calibrated:
        covered = []
        widths = []
        for row in calibrated:
            uncertainty = row["uncertainty"]
            target = label_by_id[str(row["example_id"])]
            lower = float(uncertainty["lower"])
            upper = float(uncertainty["upper"])
            covered.append(lower <= target <= upper)
            widths.append(upper - lower)
        interval_coverage = float(np.mean(covered))
        mean_interval_width = float(np.mean(widths))

    report = {
        "evaluation_type": "sealed_confirmatory_test",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "test_rows": len(test_rows),
        "estimated_rows": len(estimated),
        "abstained_rows": len(test_rows) - len(estimated),
        "prediction_coverage": len(estimated) / len(test_rows) if test_rows else 0.0,
        "point_metrics_on_estimated_rows": point_metrics,
        "calibrated_interval_rows": len(calibrated),
        "empirical_interval_coverage": interval_coverage,
        "mean_interval_width": mean_interval_width,
        "benchmark_manifest_sha256": sha256_file(benchmark_manifest_path),
        "model_sha256": model_manifest["model_sha256"],
        "schema_sha256": model_manifest["schema_sha256"],
        "predictions_sha256": sha256_file(predictions_path),
        "warnings": [
            "Metrics cover only non-abstained rows and must be reported with prediction coverage.",
            "This receipt prevents accidental repeated local evaluation; governance must protect private labels externally.",
        ],
    }
    report_path = output_dir / "confirmatory_evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "consumed_at_utc": report["created_at_utc"],
        "benchmark_manifest_sha256": report["benchmark_manifest_sha256"],
        "model_sha256": report["model_sha256"],
        "evaluation_report_sha256": sha256_file(report_path),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    """Parse sealed-evaluation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Run the sealed confirmatory evaluation once."""
    args = parse_args()
    report = evaluate_frozen_benchmark(
        benchmark_dir=args.benchmark_dir,
        model_dir=args.model_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

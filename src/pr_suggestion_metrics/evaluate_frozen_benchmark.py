"""Run one sealed confirmatory evaluation against private frozen test labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pr_suggestion_metrics.artifact_io import read_jsonl_objects, write_jsonl_objects
from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.model_artifacts import sha256_file, verify_model_manifest
from pr_suggestion_metrics.model_inference import predict_coverage_from_diffs
from pr_suggestion_metrics.percentages import validate_continuous_percentage


RECEIPT_FILENAME = "CONFIRMATORY_TEST_CONSUMED.json"


def _index_unique_rows(rows: list[dict[str, Any]], *, source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row_number, row in enumerate(rows, start=1):
        if "example_id" not in row or not str(row["example_id"]).strip():
            raise ValueError(f"{source} row {row_number} is missing example_id")
        example_id = str(row["example_id"])
        if example_id in indexed:
            raise ValueError(f"Duplicate example_id in {source}: {example_id}")
        indexed[example_id] = row
    return indexed


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


def _grouped_bootstrap_intervals(
    actual: np.ndarray,
    predicted: np.ndarray,
    groups: np.ndarray,
    *,
    iterations: int = 2_000,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    """Return percentile confidence intervals after resampling independent groups."""
    unique_groups = np.unique(groups)
    if not len(actual) or not len(unique_groups):
        return {}
    random = np.random.default_rng(seed)
    sampled_metrics: dict[str, list[float]] = defaultdict(list)
    for _ in range(iterations):
        sampled_groups = random.choice(unique_groups, size=len(unique_groups), replace=True)
        positions = np.concatenate([np.flatnonzero(groups == group) for group in sampled_groups])
        for name, value in _metrics(actual[positions], predicted[positions]).items():
            sampled_metrics[name].append(value)
    return {
        name: {
            "lower_95": float(np.quantile(values, 0.025)),
            "upper_95": float(np.quantile(values, 0.975)),
        }
        for name, values in sampled_metrics.items()
    }


def _edit_type(diff_text: str) -> str:
    parsed = parse_unified_diff(diff_text)
    operations: set[str] = {line.operation for line in parsed.changed_lines}
    if any(file_diff.rename_from or file_diff.rename_to for file_diff in parsed.files):
        operations.add("rename")
    return "+".join(sorted(operations)) or "empty"


def _suggestion_size(diff_text: str) -> str:
    unit_count = sum(bool(line.text.strip()) for line in parse_unified_diff(diff_text).changed_lines)
    if unit_count <= 3:
        return "small"
    if unit_count <= 10:
        return "medium"
    return "large"


def _subgroup_metrics(
    estimated: list[dict[str, Any]],
    input_by_id: dict[str, dict[str, Any]],
    label_by_id: dict[str, float],
) -> dict[str, dict[str, dict[str, float] | int]]:
    dimensions: dict[str, dict[str, list[tuple[float, float]]]] = {
        "repository": defaultdict(list),
        "edit_type": defaultdict(list),
        "suggestion_size": defaultdict(list),
    }
    for prediction in estimated:
        example_id = str(prediction["example_id"])
        source = input_by_id[example_id]
        pair = (label_by_id[example_id], float(prediction["model_predicted_percentage"]))
        dimensions["repository"][str(source.get("repo", "unknown"))].append(pair)
        dimensions["edit_type"][_edit_type(str(source["suggested_diff"]))].append(pair)
        dimensions["suggestion_size"][_suggestion_size(str(source["suggested_diff"]))].append(pair)
    return {
        dimension: {
            name: {
                "rows": len(values),
                **_metrics(
                    np.asarray([value[0] for value in values]),
                    np.asarray([value[1] for value in values]),
                ),
            }
            for name, values in sorted(grouped_values.items())
        }
        for dimension, grouped_values in dimensions.items()
    }


def _resolve_benchmark_artifacts(
    benchmark_dir: Path,
    manifest: dict[str, Any],
    private_labels_path: Path | None = None,
) -> tuple[Path, Path, str]:
    artifact_hashes = manifest.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("Benchmark manifest is missing artifact_sha256")
    test_inputs_path = benchmark_dir / "test_inputs.jsonl"
    resolved_private_labels_path = private_labels_path or benchmark_dir / "test_labels.private.jsonl"
    expected_test_hash = artifact_hashes.get("test")
    expected_label_hash = artifact_hashes.get("private_test_labels")
    if not isinstance(expected_test_hash, str) or not isinstance(expected_label_hash, str):
        raise ValueError("Benchmark manifest is missing test artifact hashes")
    if sha256_file(test_inputs_path) != expected_test_hash:
        raise ValueError("Frozen test inputs do not match the benchmark manifest")
    return test_inputs_path, resolved_private_labels_path, expected_label_hash


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Confirmatory test was already consumed: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def _replace_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _compatibility_receipt_path(canonical_receipt_path: Path, receipt_path: Path | None) -> Path | None:
    if receipt_path is None or receipt_path.resolve() == canonical_receipt_path.resolve():
        return None
    return receipt_path


def evaluate_frozen_benchmark(
    *,
    benchmark_dir: Path,
    model_dir: Path,
    output_dir: Path,
    private_labels_path: Path | None = None,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate once, reporting abstention and intervals without tuning on test labels."""
    canonical_receipt_path = benchmark_dir / RECEIPT_FILENAME
    compatibility_receipt_path = _compatibility_receipt_path(canonical_receipt_path, receipt_path)
    if canonical_receipt_path.exists():
        raise RuntimeError(f"Confirmatory test was already consumed: {canonical_receipt_path}")
    if compatibility_receipt_path is not None and compatibility_receipt_path.exists():
        raise RuntimeError(f"Confirmatory test was already consumed: {compatibility_receipt_path}")
    benchmark_manifest_path = benchmark_dir / "benchmark_manifest.json"
    benchmark_manifest_bytes = benchmark_manifest_path.read_bytes()
    benchmark_manifest = json.loads(benchmark_manifest_bytes)
    test_inputs_path, resolved_private_labels_path, expected_private_labels_hash = _resolve_benchmark_artifacts(
        benchmark_dir,
        benchmark_manifest,
        private_labels_path,
    )
    model_manifest = verify_model_manifest(model_dir)

    test_rows = read_jsonl_objects(test_inputs_path)
    input_by_id = _index_unique_rows(test_rows, source="frozen test inputs")
    if output_dir.exists():
        raise FileExistsError(f"Evaluation output directory already exists: {output_dir}")

    claimed_at_utc = datetime.now(UTC).isoformat()
    benchmark_manifest_sha256 = hashlib.sha256(benchmark_manifest_bytes).hexdigest()
    _write_json_exclusive(
        canonical_receipt_path,
        {
            "status": "claimed",
            "claimed_at_utc": claimed_at_utc,
            "benchmark_manifest_sha256": benchmark_manifest_sha256,
            "model_sha256": model_manifest["model_sha256"],
            "warning": "This fail-closed claim blocks all further confirmatory evaluation attempts.",
        },
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    predictions: list[dict[str, Any]] = []
    for row in test_rows:
        example_id = str(row["example_id"])
        prediction = predict_coverage_from_diffs(
            str(row["suggested_diff"]),
            str(row["landed_diff"]),
            example_id=example_id,
            model_dir=model_dir,
        )
        prediction_row = prediction.model_dump(mode="json")
        if str(prediction_row.get("example_id")) != example_id:
            raise ValueError(f"Model prediction example_id does not match frozen input {example_id}")
        predictions.append(prediction_row)
    predictions_path = output_dir / "predictions.jsonl"
    write_jsonl_objects(predictions_path, predictions, sort_keys=True)

    if sha256_file(resolved_private_labels_path) != expected_private_labels_hash:
        raise ValueError("Private test labels do not match the benchmark manifest")
    private_labels = read_jsonl_objects(resolved_private_labels_path)
    private_label_by_id = _index_unique_rows(private_labels, source="private test labels")
    if set(private_label_by_id) != set(input_by_id):
        raise ValueError("Private labels and frozen test inputs have different example IDs")
    label_by_id = {
        example_id: validate_continuous_percentage(
            row.get("coverage_unrounded"),
            name=f"Private label percentage for {example_id}",
        )
        for example_id, row in private_label_by_id.items()
    }

    estimated = [row for row in predictions if row.get("status") == "predicted"]
    estimated_ids = [str(row["example_id"]) for row in estimated]
    actual = np.array([label_by_id[example_id] for example_id in estimated_ids], dtype=float)
    predicted = np.array(
        [
            validate_continuous_percentage(
                row.get("model_predicted_percentage"),
                name=f"Model prediction percentage for {row['example_id']}",
            )
            for row in estimated
        ],
        dtype=float,
    )
    point_metrics = _metrics(actual, predicted) if len(estimated) else None
    groups = np.asarray(
        [
            f"{input_by_id[example_id].get('repo', 'unknown')}#{input_by_id[example_id].get('pr_number', example_id)}"
            for example_id in estimated_ids
        ],
        dtype=object,
    )
    confidence_intervals = _grouped_bootstrap_intervals(actual, predicted, groups) if len(estimated) else {}
    subgroup_metrics = _subgroup_metrics(estimated, input_by_id, label_by_id)

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
        "grouped_bootstrap_95_percent_intervals": confidence_intervals,
        "subgroup_metrics": subgroup_metrics,
        "calibrated_interval_rows": len(calibrated),
        "empirical_interval_coverage": interval_coverage,
        "mean_interval_width": mean_interval_width,
        "benchmark_manifest_sha256": benchmark_manifest_sha256,
        "model_sha256": model_manifest["model_sha256"],
        "schema_sha256": model_manifest["schema_sha256"],
        "predictions_sha256": sha256_file(predictions_path),
        "private_labels_stored_outside_benchmark": resolved_private_labels_path.parent != benchmark_dir,
        "warnings": [
            "Metrics cover only non-abstained rows and must be reported with prediction coverage.",
            "The canonical atomic claim permanently blocks repeated local evaluation, including after post-claim failure.",
        ],
    }
    report_path = output_dir / "confirmatory_evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "status": "completed",
        "claimed_at_utc": claimed_at_utc,
        "consumed_at_utc": report["created_at_utc"],
        "benchmark_manifest_sha256": report["benchmark_manifest_sha256"],
        "model_sha256": report["model_sha256"],
        "evaluation_report_sha256": sha256_file(report_path),
    }
    if compatibility_receipt_path is not None:
        compatibility_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_exclusive(compatibility_receipt_path, receipt)
    _replace_json_atomically(canonical_receipt_path, receipt)
    return report


def parse_args() -> argparse.Namespace:
    """Parse sealed-evaluation arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-labels", type=Path)
    parser.add_argument("--receipt", type=Path, help="Optional compatibility copy; the canonical benchmark claim is mandatory.")
    return parser.parse_args()


def main() -> int:
    """Run the sealed confirmatory evaluation once."""
    args = parse_args()
    report = evaluate_frozen_benchmark(
        benchmark_dir=args.benchmark_dir,
        model_dir=args.model_dir,
        output_dir=args.output_dir,
        private_labels_path=args.private_labels,
        receipt_path=args.receipt,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

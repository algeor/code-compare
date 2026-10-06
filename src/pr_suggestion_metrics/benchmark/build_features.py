"""Build canonical model feature tables from frozen non-test benchmark splits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.artifact_io import parse_jsonl_objects
from pr_suggestion_metrics.features import (
    assess_raw_diff,
    metric_result_to_feature_row,
    score_diff_pair,
)
from pr_suggestion_metrics.features.policy import NORMALIZATION_POLICY_VERSION
from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.percentages import parse_integer_percentage, validate_continuous_percentage


_INPUT_SPLITS = ("train", "development", "calibration")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        if not fieldnames:
            return
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _verified_split_artifacts(
    benchmark_dir: Path,
) -> tuple[str, dict[str, list[dict[str, Any]]], dict[str, str]]:
    manifest_path = benchmark_dir / "benchmark_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("Benchmark manifest must contain a JSON object")
    artifact_hashes = manifest.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ValueError("Benchmark manifest is missing artifact_sha256")

    split_rows: dict[str, list[dict[str, Any]]] = {}
    verified_hashes: dict[str, str] = {}
    for split in _INPUT_SPLITS:
        input_path = benchmark_dir / f"{split}.jsonl"
        expected_hash = artifact_hashes.get(split)
        if not isinstance(expected_hash, str):
            raise ValueError(f"Benchmark manifest is missing the {split} artifact hash")
        if not input_path.is_file():
            raise ValueError(f"Frozen benchmark is missing {input_path.name}")
        input_bytes = input_path.read_bytes()
        actual_hash = hashlib.sha256(input_bytes).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"Frozen {split} split does not match the benchmark manifest")
        split_rows[split] = parse_jsonl_objects(input_bytes.decode("utf-8"), source=input_path)
        verified_hashes[split] = actual_hash
    return hashlib.sha256(manifest_bytes).hexdigest(), split_rows, verified_hashes


def build_frozen_feature_tables(*, benchmark_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Transform frozen train/development/calibration rows into one feature schema."""
    benchmark_manifest_sha256, rows_by_split, input_hashes = _verified_split_artifacts(benchmark_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    feature_rows: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []

    for split in _INPUT_SPLITS:
        for row in rows_by_split[split]:
            example_id = str(row["example_id"])
            suggested_diff = str(row["suggested_diff"])
            landed_diff = str(row["landed_diff"])
            coverage_percentage = parse_integer_percentage(
                row["coverage_percentage"],
                name=f"coverage_percentage for {example_id}",
            )
            coverage_unrounded = validate_continuous_percentage(
                row["coverage_unrounded"],
                name=f"coverage_unrounded for {example_id}",
            )
            suggested_assessment = assess_raw_diff(suggested_diff)
            merged_assessment = assess_raw_diff(landed_diff, source="merged_pr_diff")
            blocking_assessments = [
                assessment
                for assessment in (suggested_assessment, merged_assessment)
                if assessment.status != "valid"
            ]
            if blocking_assessments:
                sources = [assessment.source for assessment in blocking_assessments]
                abstentions.append(
                    {
                        "example_id": example_id,
                        "split": split,
                        "source": sources[0] if len(sources) == 1 else "multiple_inputs",
                        "sources": sources,
                        "status": (
                            "invalid"
                            if any(assessment.status == "invalid" for assessment in blocking_assessments)
                            else "valid_but_unsupported"
                        ),
                        "reasons": [
                            reason
                            for assessment in blocking_assessments
                            for reason in assessment.reasons
                        ],
                    }
                )
                continue
            metric_result = score_diff_pair(suggested_diff, landed_diff)
            feature_rows.append(
                {
                    "example_id": example_id,
                    "repo": str(row["repo"]),
                    "pr_url": str(row["pr_url"]),
                    "pr_number": int(row["pr_number"]),
                    "group_id": f"{row['repo']}#{row['pr_number']}",
                    "split": split,
                    "coverage_percentage": coverage_percentage,
                    "coverage_unrounded": coverage_unrounded,
                    "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
                    **metric_result_to_feature_row(metric_result),
                }
            )

    features_path = output_dir / "features.csv"
    abstentions_path = output_dir / "feature_abstentions.jsonl"
    _write_csv(features_path, feature_rows)
    abstentions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in abstentions),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0",
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "source_benchmark_dir": str(benchmark_dir),
        "benchmark_manifest_sha256": benchmark_manifest_sha256,
        "input_sha256": input_hashes,
        "feature_rows": len(feature_rows),
        "abstained_rows": len(abstentions),
        "split_counts": {
            split: sum(row["split"] == split for row in feature_rows)
            for split in _INPUT_SPLITS
        },
        "artifacts": {
            "features": sha256_file(features_path),
            "abstentions": sha256_file(abstentions_path),
        },
    }
    (output_dir / "feature_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_frozen_feature_tables(benchmark_dir=args.benchmark_dir, output_dir=args.output_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build canonical model feature tables from frozen non-test benchmark splits."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.evaluate_metrics import (
    metric_result_to_feature_row,
    raw_diff_support_issues,
    score_diff_pair,
)
from pr_suggestion_metrics.model_artifacts import sha256_file


_INPUT_SPLITS = ("train", "development", "calibration")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            rows.append(value)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        if not fieldnames:
            return
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_frozen_feature_tables(*, benchmark_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Transform frozen train/development/calibration rows into one feature schema."""
    output_dir.mkdir(parents=True, exist_ok=False)
    feature_rows: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
    input_hashes: dict[str, str] = {}

    for split in _INPUT_SPLITS:
        input_path = benchmark_dir / f"{split}.jsonl"
        if not input_path.exists():
            continue
        input_hashes[split] = sha256_file(input_path)
        for row in _read_jsonl(input_path):
            example_id = str(row["example_id"])
            suggested_diff = str(row["suggested_diff"])
            landed_diff = str(row["landed_diff"])
            issues = raw_diff_support_issues(suggested_diff)
            if issues:
                abstentions.append({"example_id": example_id, "split": split, "reasons": issues})
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
                    "coverage_percentage": int(row["coverage_percentage"]),
                    "coverage_unrounded": float(row["coverage_unrounded"]),
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
        "source_benchmark_dir": str(benchmark_dir),
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

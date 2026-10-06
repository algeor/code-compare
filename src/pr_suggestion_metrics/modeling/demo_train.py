"""Train an interview-demo percentage model from local weak Phase 5 rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.artifact_io import iter_jsonl_objects
from pr_suggestion_metrics.features import metric_result_to_feature_row, score_diff_pair
from pr_suggestion_metrics.features.policy import NORMALIZATION_POLICY_VERSION
from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.modeling.train import train_from_frozen_features
from pr_suggestion_metrics.percentages import parse_integer_percentage

_SPLITS = ("train", "development", "calibration")
_DEFAULT_DATASET = Path("data/processed/pr_suggestion_coverage/dataset/dataset.jsonl")
_DEFAULT_OUTPUT_DIR = Path("models/demo_percentage_model")
_LABEL_SOURCE = "weak_local_llm_assisted_demo"


def _stable_bucket(group_id: str) -> int:
    digest = hashlib.sha256(group_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _split_for_group(group_id: str) -> str:
    bucket = _stable_bucket(group_id)
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "development"
    return "calibration"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _group_id(row: dict[str, Any]) -> str:
    repo = str(row["repo"])
    pr_number = int(row["pr_number"])
    return f"{repo}#{pr_number}"


def _build_demo_features(*, dataset_path: Path, features_path: Path) -> dict[str, Any]:
    feature_rows: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []

    for line_number, row in iter_jsonl_objects(dataset_path):
        example_id = str(row.get("example_id") or f"line-{line_number}")
        try:
            suggested_diff = str(row["suggested_diff"])
            landed_diff = str(row["landed_diff"])
            coverage_percentage = parse_integer_percentage(
                row["expected_landed_percentage"],
                name=f"expected_landed_percentage for {example_id}",
            )
            group_id = _group_id(row)
            metric_result = score_diff_pair(suggested_diff, landed_diff)
        except (KeyError, TypeError, ValueError) as exc:
            abstentions.append(
                {
                    "example_id": example_id,
                    "line_number": line_number,
                    "reason": str(exc),
                }
            )
            continue

        feature_rows.append(
            {
                "example_id": example_id,
                "repo": str(row["repo"]),
                "pr_url": str(row.get("pr_url", "")),
                "pr_number": int(row["pr_number"]),
                "group_id": group_id,
                "split": _split_for_group(group_id),
                "coverage_percentage": coverage_percentage,
                "coverage_unrounded": float(coverage_percentage),
                "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
                "label_source": _LABEL_SOURCE,
                **metric_result_to_feature_row(metric_result),
            }
        )

    split_counts = {split: sum(row["split"] == split for row in feature_rows) for split in _SPLITS}
    if split_counts["train"] == 0 or split_counts["development"] == 0:
        raise ValueError(f"Demo training needs non-empty train and development splits; got {split_counts}")

    _write_csv(features_path, feature_rows)
    abstentions_path = features_path.with_name("feature_abstentions.jsonl")
    abstentions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in abstentions),
        encoding="utf-8",
    )
    return {
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "features_path": str(features_path),
        "features_sha256": sha256_file(features_path),
        "label_source": _LABEL_SOURCE,
        "feature_rows": len(feature_rows),
        "abstained_rows": len(abstentions),
        "split_counts": split_counts,
    }


def train_demo_model(
    *,
    dataset_path: Path = _DEFAULT_DATASET,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    force: bool = False,
) -> dict[str, Any]:
    """Build weak local features and train a demo-only percentage model."""
    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {output_dir}; pass --force to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    features_path = output_dir / "features.csv"
    feature_report = _build_demo_features(dataset_path=dataset_path, features_path=features_path)
    config_path = output_dir / "training_config.json"
    config_path.write_text(
        json.dumps({"candidates": ["random_forest", "extra_trees", "gradient_boosting"], "random_state": 42}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    model_dir = output_dir / "model"
    training_report = train_from_frozen_features(
        features_path=features_path,
        model_dir=model_dir,
        config_path=config_path,
    )
    demo_manifest = {
        "schema_version": "1.0",
        "purpose": "interview_demo_percentage_model",
        "validation_claim": "weak local labels only; not human validated; not release validated",
        "phase_alignment": "Phase 5 derived local benchmark rows feeding the Phase 6 training path",
        "feature_report": feature_report,
        "training_report": training_report,
        "model_dir": str(model_dir),
    }
    (output_dir / "demo_manifest.json").write_text(
        json.dumps(demo_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# Demo percentage model\n\n"
        "This artifact is for the interview demo only. It is trained on local weak Phase 5-derived labels from "
        "`expected_landed_percentage`, not human ground truth. Do not present it as release-validated.\n",
        encoding="utf-8",
    )
    return demo_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = train_demo_model(dataset_path=args.dataset, output_dir=args.output_dir, force=args.force)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

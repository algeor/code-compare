"""Compare the saved percentage model with PIPELINE3-1376 exact coverage."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from pr_suggestion_metrics.model_inference import predict_coverage_percentages
from pr_suggestion_metrics.pipeline1376_coverage import parse_diff_change_units, score_diff_pair
from pr_suggestion_metrics.train_percentage_regressor import RANDOM_STATE, metrics, prepare_features, read_source


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATASET_DIR = _REPOSITORY_ROOT / "data" / "processed" / "pr_suggestion_coverage" / "dataset"
_SCORES_PATH = _REPOSITORY_ROOT / "reports" / "metric_scores.csv"
_MODEL_DIR = _REPOSITORY_ROOT / "models" / "pr_suggestion_coverage_regression"


@dataclass(frozen=True)
class ComparisonRow:
    """One held-out example scored by both percentage methods."""

    example_id: str
    pr_url: str
    repo: str
    reference_percentage: float
    exact_baseline_percentage: int
    model_percentage: int
    exact_absolute_error: float
    model_absolute_error: float
    suggested_change_units: int


def _load_dataset_by_id(path: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[str(row["example_id"])] = row
    return rows


def build_comparison_rows() -> tuple[list[ComparisonRow], int]:
    """Recreate the model's grouped holdout and score both methods."""
    feature_rows = prepare_features(read_source("internal", _SCORES_PATH, _DATASET_DIR / "labels.csv"))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    _, test_positions = next(splitter.split(feature_rows, groups=feature_rows["group_id"]))
    held_out_rows = feature_rows.iloc[test_positions].copy()
    dataset_rows = _load_dataset_by_id(_DATASET_DIR / "dataset.jsonl")
    model_predictions = predict_coverage_percentages(held_out_rows, model_dir=_MODEL_DIR)[
        "model_predicted_percentage"
    ].to_numpy(dtype=int)

    comparison_rows: list[ComparisonRow] = []
    for held_out_position, (_, row) in enumerate(held_out_rows.iterrows()):
        example_id = str(row["example_id"])
        example = dataset_rows[example_id]
        suggested_diff = str(example["suggested_diff"])
        exact_percentage = round(score_diff_pair(suggested_diff, str(example["landed_diff"])) * 100)
        model_percentage = int(model_predictions[held_out_position])
        reference_percentage = float(row["expected_landed_percentage"])
        comparison_rows.append(
            ComparisonRow(
                example_id=example_id,
                pr_url=str(row["pr_url"]),
                repo=str(row["repo"]),
                reference_percentage=reference_percentage,
                exact_baseline_percentage=exact_percentage,
                model_percentage=model_percentage,
                exact_absolute_error=abs(reference_percentage - exact_percentage),
                model_absolute_error=abs(reference_percentage - model_percentage),
                suggested_change_units=len(parse_diff_change_units(suggested_diff)),
            )
        )
    return comparison_rows, int(held_out_rows["group_id"].nunique())


def summarize(rows: list[ComparisonRow], pull_request_count: int) -> dict[str, object]:
    """Return percentage-only benchmark metrics and improvement values."""
    reference = np.asarray([row.reference_percentage for row in rows], dtype=float)
    exact = np.asarray([row.exact_baseline_percentage for row in rows], dtype=float)
    model = np.asarray([row.model_percentage for row in rows], dtype=float)
    exact_metrics = metrics(reference, exact)
    model_metrics = metrics(reference, model)
    return {
        "comparison": "saved percentage model vs PIPELINE3-1376 rudimentary exact baseline",
        "output_contract": "0-100 integer percentage; no categorical buckets",
        "benchmark": {
            "held_out_rows": len(rows),
            "held_out_pull_requests": pull_request_count,
            "split": "25% grouped holdout by pull request",
            "random_state": RANDOM_STATE,
            "reference_label_caveat": "LLM-assisted weak labels, not independent human ground truth",
        },
        "exact_baseline": {
            "source": "pipeline-fl-control-plane PIPELINE3-1376",
            "source_commit": "93f803ea",
            "algorithm_version": "diff-unit-multiset-v2",
            "method": "matched path+operation+line occurrences / suggested occurrences",
            "metrics": exact_metrics,
        },
        "percentage_model": {
            "artifact": "models/pr_suggestion_coverage_regression/model.joblib",
            "model_name": "weighted_percentage_ensemble",
            "components": {"random_forest": 0.5, "two_stage": 0.3, "catboost_mae": 0.2},
            "metrics": model_metrics,
        },
        "improvement": {
            "mae_points": exact_metrics["percentage_mae"] - model_metrics["percentage_mae"],
            "mae_relative": 1 - (model_metrics["percentage_mae"] / exact_metrics["percentage_mae"]),
            "within_10_percentage_points": (
                model_metrics["within_10_points"] - exact_metrics["within_10_points"]
            ),
            "dangerous_error_percentage_points": (
                exact_metrics["dangerous_error_rate"] - model_metrics["dangerous_error_rate"]
            ),
        },
        "winner": "percentage_model",
    }


def write_rows(path: Path, rows: list[ComparisonRow]) -> None:
    """Write auditable per-example percentages and absolute errors."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ComparisonRow.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=_REPOSITORY_ROOT / "reports" / "pipeline1376_model_comparison.json",
    )
    parser.add_argument(
        "--rows-output",
        type=Path,
        default=_REPOSITORY_ROOT / "reports" / "pipeline1376_model_comparison.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rows, pull_request_count = build_comparison_rows()
    summary = summarize(rows, pull_request_count)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_rows(args.rows_output, rows)

    exact_metrics = summary["exact_baseline"]["metrics"]  # type: ignore[index]
    model_metrics = summary["percentage_model"]["metrics"]  # type: ignore[index]
    print(
        f"held-out rows={len(rows)}, pull requests={pull_request_count}\n"
        f"exact baseline: MAE={exact_metrics['percentage_mae']:.2f}, "
        f"within-10={exact_metrics['within_10_points']:.1%}, "
        f"dangerous={exact_metrics['dangerous_error_rate']:.1%}\n"
        f"percentage model: MAE={model_metrics['percentage_mae']:.2f}, "
        f"within-10={model_metrics['within_10_points']:.1%}, "
        f"dangerous={model_metrics['dangerous_error_rate']:.1%}"
    )
    print(f"wrote summary: {args.summary_output}")
    print(f"wrote rows: {args.rows_output}")


if __name__ == "__main__":
    main()

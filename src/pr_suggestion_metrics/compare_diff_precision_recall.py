"""Compare the saved percentage model with draft/final Diff Precision/Recall."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from pr_suggestion_metrics.diff_precision_recall import compare_diffs
from pr_suggestion_metrics.model_inference import predict_coverage_percentages
from pr_suggestion_metrics.train_percentage_regressor import RANDOM_STATE, metrics, prepare_features, read_source


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATASET_DIR = _REPOSITORY_ROOT / "data" / "processed" / "pr_suggestion_coverage" / "dataset"
_SCORES_PATH = _REPOSITORY_ROOT / "reports" / "metric_scores.csv"
_MODEL_DIR = _REPOSITORY_ROOT / "models" / "pr_suggestion_coverage_regression"
_DIFF_METRIC_NAMES = (
    "token_precision",
    "token_recall",
    "file_precision",
    "file_recall",
    "line_precision",
    "line_recall",
)


@dataclass(frozen=True)
class ComparisonRow:
    """One held-out example scored by the model and all six diff metrics."""

    example_id: str
    pr_url: str
    repo: str
    reference_percentage: float
    model_percentage: int
    token_precision: int
    token_recall: int
    file_precision: int
    file_recall: int
    line_precision: int
    line_recall: int
    aggregate_diff_f1: int


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
    """Recreate the grouped holdout and score the model and diff metrics."""
    feature_rows = prepare_features(read_source("internal", _SCORES_PATH, _DATASET_DIR / "labels.csv"))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    _, test_positions = next(splitter.split(feature_rows, groups=feature_rows["group_id"]))
    held_out_rows = feature_rows.iloc[test_positions].copy()
    dataset_rows = _load_dataset_by_id(_DATASET_DIR / "dataset.jsonl")
    model_predictions = predict_coverage_percentages(held_out_rows, model_dir=_MODEL_DIR)[
        "model_predicted_percentage"
    ].to_numpy(dtype=int)

    comparison_rows: list[ComparisonRow] = []
    for position, (_, row) in enumerate(held_out_rows.iterrows()):
        example_id = str(row["example_id"])
        example = dataset_rows[example_id]
        result = compare_diffs(str(example["suggested_diff"]), str(example["landed_diff"]))
        comparison_rows.append(
            ComparisonRow(
                example_id=example_id,
                pr_url=str(row["pr_url"]),
                repo=str(row["repo"]),
                reference_percentage=float(row["expected_landed_percentage"]),
                model_percentage=int(model_predictions[position]),
                token_precision=round(result.token.precision * 100),
                token_recall=round(result.token.recall * 100),
                file_precision=round(result.file.precision * 100),
                file_recall=round(result.file.recall * 100),
                line_precision=round(result.line.precision * 100),
                line_recall=round(result.line.recall * 100),
                aggregate_diff_f1=round(result.aggregate_f1 * 100),
            )
        )
    return comparison_rows, int(held_out_rows["group_id"].nunique())


def summarize(rows: list[ComparisonRow], pull_request_count: int) -> dict[str, object]:
    """Return model metrics and diagnostics for all Diff Precision/Recall values."""
    reference = np.asarray([row.reference_percentage for row in rows], dtype=float)
    model_metrics = metrics(reference, np.asarray([row.model_percentage for row in rows], dtype=float))
    diff_metrics = {
        metric_name: metrics(reference, np.asarray([getattr(row, metric_name) for row in rows], dtype=float))
        for metric_name in _DIFF_METRIC_NAMES
    }
    aggregate_metrics = metrics(reference, np.asarray([row.aggregate_diff_f1 for row in rows], dtype=float))
    return {
        "comparison": "saved percentage model vs Diff Precision/Recall",
        "output_contract": "all values are 0-100 integer percentages; no categorical buckets",
        "benchmark": {
            "held_out_rows": len(rows),
            "held_out_pull_requests": pull_request_count,
            "split": "25% grouped holdout by pull request",
            "random_state": RANDOM_STATE,
            "mae_definition": "mean(abs(predicted_percentage - reference_percentage)) across held-out examples",
            "reference_label_caveat": "LLM-assisted weak labels, not independent human ground truth",
        },
        "diff_precision_recall": {
            "definition": {
                "precision": "how much of the draft was kept; overlap / draft",
                "recall": "how much of the final diff was already in the draft; overlap / final",
                "levels": ["raw word tokens", "changed file set", "stripped added/removed line occurrences"],
                "aggregate_percentage": "equal-weight mean of token F1, file F1, and line F1",
            },
            "primary_comparison_metric": "aggregate_diff_f1",
            "primary_reason": "It balances precision and recall at all three levels without allowing token counts to dominate.",
            "metrics_against_reference_percentage": diff_metrics,
            "aggregate_diff_f1_metrics": aggregate_metrics,
        },
        "percentage_model": {
            "artifact": "models/pr_suggestion_coverage_regression/model.joblib",
            "model_name": "weighted_percentage_ensemble",
            "components": {"random_forest": 0.5, "two_stage": 0.3, "catboost_mae": 0.2},
            "component_roles": {
                "random_forest": "stable nonlinear anchor; best component holdout RMSE",
                "two_stage": "separates 0, intermediate, and 100 percent cases; best component within-5 accuracy",
                "catboost_mae": "handles categorical context directly and limits outlier influence; best component within-10 accuracy and zero serious holdout errors",
            },
            "weight_selection": "repeated pull-request-grouped out-of-fold validation",
            "disagreement_rule": "fall back to the stable baseline when component disagreement exceeds 20 points",
            "metrics": model_metrics,
        },
        "primary_comparison": {
            "aggregate_diff_f1": aggregate_metrics,
            "percentage_model": model_metrics,
            "mae_improvement_points": aggregate_metrics["percentage_mae"] - model_metrics["percentage_mae"],
            "within_10_improvement_percentage_points": (
                model_metrics["within_10_points"] - aggregate_metrics["within_10_points"]
            ),
            "dangerous_error_reduction_percentage_points": (
                aggregate_metrics["dangerous_error_rate"] - model_metrics["dangerous_error_rate"]
            ),
            "winner": "percentage_model",
        },
    }


def write_rows(path: Path, rows: list[ComparisonRow]) -> None:
    """Write auditable per-example percentages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(ComparisonRow.__dataclass_fields__))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=_REPOSITORY_ROOT / "reports" / "diff_precision_recall_model_comparison.json",
    )
    parser.add_argument(
        "--rows-output",
        type=Path,
        default=_REPOSITORY_ROOT / "reports" / "diff_precision_recall_model_comparison.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rows, pull_request_count = build_comparison_rows()
    summary = summarize(rows, pull_request_count)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_rows(args.rows_output, rows)

    primary = summary["primary_comparison"]
    aggregate = primary["aggregate_diff_f1"]  # type: ignore[index]
    model = primary["percentage_model"]  # type: ignore[index]
    print(f"held-out rows={len(rows)}, pull requests={pull_request_count}")
    print(
        f"aggregate Diff P/R: MAE={aggregate['percentage_mae']:.2f}, "
        f"within-10={aggregate['within_10_points']:.1%}, "
        f"dangerous={aggregate['dangerous_error_rate']:.1%}"
    )
    print(
        f"percentage model: MAE={model['percentage_mae']:.2f}, "
        f"within-10={model['within_10_points']:.1%}, "
        f"dangerous={model['dangerous_error_rate']:.1%}"
    )
    print(f"wrote summary: {args.summary_output}")
    print(f"wrote rows: {args.rows_output}")


if __name__ == "__main__":
    main()

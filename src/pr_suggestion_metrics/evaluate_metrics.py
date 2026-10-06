"""Evaluate PR suggestion coverage metrics against labeled examples."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from pr_suggestion_metrics._paths import REPOSITORY_ROOT as _REPOSITORY_ROOT
from pr_suggestion_metrics.artifact_io import read_jsonl_objects
from pr_suggestion_metrics.features import core as _feature_engine
from pr_suggestion_metrics.features import structural as _structural_features
from pr_suggestion_metrics.percentages import parse_integer_percentage, validate_continuous_percentage


_DEFAULT_DATASET_DIR = _REPOSITORY_ROOT / "data" / "processed" / "pr_suggestion_coverage" / "dataset"
_DEFAULT_OUTPUT_PATH = _REPOSITORY_ROOT / "reports" / "pr_suggestion_metric_scores.csv"

MetricResult = _feature_engine.MetricResult
ScoringExample = _feature_engine.ScoringExample
TokenizedText = _feature_engine.TokenizedText
CandidateHunk = _feature_engine.CandidateHunk
raw_diff_support_issues = _feature_engine.raw_diff_support_issues
score_diff_pair = _feature_engine.score_diff_pair
metric_result_to_feature_row = _feature_engine.metric_result_to_feature_row
_score_example = _feature_engine._score_example
_structural_node_types = _structural_features.structural_node_types


def __getattr__(name: str) -> object:
    """Resolve moved private feature helpers for transitional compatibility."""
    for module in (_feature_engine, _structural_features):
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True)
class DatasetExample:
    """One suggestion/landed-diff pair from dataset.jsonl."""

    example_id: str
    suggested_diff: str
    landed_diff: str


@dataclass(frozen=True)
class LabeledExample:
    """One joined dataset row with a human percentage and baseline estimates."""

    example_id: str
    expected_landed_percentage: int
    deterministic_landed_estimate: int
    file_overlap_ratio: float
    changed_line_overlap_ratio: float
    suggested_diff: str
    landed_diff: str


def _index_dataset_rows(dataset_path: Path) -> dict[str, dict[str, Any]]:
    dataset_rows: dict[str, dict[str, Any]] = {}
    for raw_row in read_jsonl_objects(dataset_path):
        example_id = raw_row["example_id"]
        if example_id in dataset_rows:
            raise ValueError(f"Duplicate example_id {example_id!r} in {dataset_path}")
        dataset_rows[example_id] = raw_row
    return dataset_rows


def _dataset_examples(dataset_rows: Mapping[str, Mapping[str, Any]]) -> dict[str, DatasetExample]:
    return {
        example_id: DatasetExample(
            example_id=example_id,
            suggested_diff=raw_example["suggested_diff"],
            landed_diff=raw_example["landed_diff"],
        )
        for example_id, raw_example in dataset_rows.items()
    }


def _load_dataset(dataset_path: Path) -> dict[str, DatasetExample]:
    return _dataset_examples(_index_dataset_rows(dataset_path))


def _parse_overlap_ratio(value: Any, *, name: str) -> float:
    ratio = validate_continuous_percentage(value, name=name)
    if ratio > 1.0:
        raise ValueError(f"{name} must be between 0 and 1: {value!r}")
    return ratio


def _validate_dataset_label_consistency(
    dataset_dir: Path,
    *,
    dataset_rows: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    resolved_dataset_rows = (
        dataset_rows if dataset_rows is not None else _index_dataset_rows(dataset_dir / "dataset.jsonl")
    )
    mismatches: list[str] = []
    with (dataset_dir / "labels.csv").open(encoding="utf-8", newline="") as labels_file:
        for row in csv.DictReader(labels_file):
            example_id = row["example_id"]
            label_percentage = parse_integer_percentage(
                row["expected_landed_percentage"],
                name=f"labels.csv expected_landed_percentage for {example_id}",
            )
            dataset_row = resolved_dataset_rows.get(example_id)
            if dataset_row is None:
                mismatches.append(f"{example_id}: missing from dataset.jsonl")
                continue
            dataset_percentage = dataset_row.get("expected_landed_percentage")
            if dataset_percentage is not None and parse_integer_percentage(
                dataset_percentage,
                name=f"dataset expected_landed_percentage for {example_id}",
            ) != label_percentage:
                mismatches.append(
                    f"{example_id}: dataset percentage {dataset_percentage!r} "
                    f"!= labels.csv {row['expected_landed_percentage']!r}"
                )

    if mismatches:
        preview = "\n".join(mismatches[:10])
        raise ValueError(f"Dataset labels disagree with labels.csv:\n{preview}")


def _load_labeled_examples(dataset_dir: Path) -> list[LabeledExample]:
    dataset_rows = _index_dataset_rows(dataset_dir / "dataset.jsonl")
    _validate_dataset_label_consistency(dataset_dir, dataset_rows=dataset_rows)
    examples = _dataset_examples(dataset_rows)
    labeled_examples: list[LabeledExample] = []
    with (dataset_dir / "labels.csv").open(encoding="utf-8", newline="") as labels_file:
        for row in csv.DictReader(labels_file):
            example_id = row["example_id"]
            dataset_example = examples[example_id]
            labeled_examples.append(
                LabeledExample(
                    example_id=example_id,
                    expected_landed_percentage=parse_integer_percentage(
                        row["expected_landed_percentage"],
                        name=f"expected_landed_percentage for {example_id}",
                    ),
                    deterministic_landed_estimate=parse_integer_percentage(
                        row["deterministic_landed_estimate"],
                        name=f"deterministic_landed_estimate for {example_id}",
                    ),
                    file_overlap_ratio=_parse_overlap_ratio(
                        row["file_overlap_ratio"],
                        name=f"file_overlap_ratio for {example_id}",
                    ),
                    changed_line_overlap_ratio=_parse_overlap_ratio(
                        row["changed_line_overlap_ratio"],
                        name=f"changed_line_overlap_ratio for {example_id}",
                    ),
                    suggested_diff=dataset_example.suggested_diff,
                    landed_diff=dataset_example.landed_diff,
                )
            )
    return labeled_examples


def _mean_absolute_error(actual_percentages: list[int], predicted_percentages: list[int]) -> float:
    return sum(abs(actual - predicted) for actual, predicted in zip(actual_percentages, predicted_percentages)) / len(
        actual_percentages
    )


def _write_scores(output_path: Path, examples: list[LabeledExample], metric_results: list[MetricResult]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "example_id",
                "expected_landed_percentage",
                "predicted_percentage",
                "suggestion_language",
                "tokenizer",
                "exact_normalized_match",
                "line_recall",
                "token_recall",
                "identifier_normalized_token_recall",
                "literal_normalized_token_recall",
                "identifier_and_literal_normalized_token_recall",
                "best_added_line_overlap",
                "best_hunk_token_recall",
                "best_hunk_token_precision",
                "best_hunk_token_f1",
                "best_hunk_identifier_normalized_recall",
                "best_hunk_literal_normalized_recall",
                "best_hunk_identifier_and_literal_normalized_recall",
                "best_hunk_contiguous_line_ratio",
                "best_hunk_token_lcs_recall",
                "best_hunk_size_ratio",
                "meaningful_anchor_recall",
                "meaningful_anchor_count",
                "best_hunk_size",
                "best_hunk_file",
                "best_hunk_candidate_type",
                "candidate_hunk_count",
                "structural_available",
                "structural_engine",
                "structural_language",
                "structural_similarity",
                "structural_node_recall",
                "structural_error",
                "gumtree_available",
                "gumtree_language",
                "gumtree_operation_count",
                "gumtree_insert_ratio",
                "gumtree_delete_ratio",
                "gumtree_update_ratio",
                "gumtree_move_ratio",
                "gumtree_error",
                "file_overlap_ratio",
                "changed_line_overlap_ratio",
            ],
        )
        writer.writeheader()
        for example, metric_result in zip(examples, metric_results):
            writer.writerow(
                {
                    "example_id": example.example_id,
                    "expected_landed_percentage": example.expected_landed_percentage,
                    "predicted_percentage": metric_result.predicted_percentage,
                    "suggestion_language": metric_result.suggestion_language,
                    "tokenizer": metric_result.tokenizer,
                    "exact_normalized_match": metric_result.exact_normalized_match,
                    "line_recall": f"{metric_result.line_recall:.6f}",
                    "token_recall": f"{metric_result.token_recall:.6f}",
                    "identifier_normalized_token_recall": f"{metric_result.identifier_normalized_token_recall:.6f}",
                    "literal_normalized_token_recall": f"{metric_result.literal_normalized_token_recall:.6f}",
                    "identifier_and_literal_normalized_token_recall": (
                        f"{metric_result.identifier_and_literal_normalized_token_recall:.6f}"
                    ),
                    "best_added_line_overlap": f"{metric_result.best_added_line_overlap:.6f}",
                    "best_hunk_token_recall": f"{metric_result.best_hunk_token_recall:.6f}",
                    "best_hunk_token_precision": f"{metric_result.best_hunk_token_precision:.6f}",
                    "best_hunk_token_f1": f"{metric_result.best_hunk_token_f1:.6f}",
                    "best_hunk_identifier_normalized_recall": (
                        f"{metric_result.best_hunk_identifier_normalized_recall:.6f}"
                    ),
                    "best_hunk_literal_normalized_recall": f"{metric_result.best_hunk_literal_normalized_recall:.6f}",
                    "best_hunk_identifier_and_literal_normalized_recall": (
                        f"{metric_result.best_hunk_identifier_and_literal_normalized_recall:.6f}"
                    ),
                    "best_hunk_contiguous_line_ratio": f"{metric_result.best_hunk_contiguous_line_ratio:.6f}",
                    "best_hunk_token_lcs_recall": f"{metric_result.best_hunk_token_lcs_recall:.6f}",
                    "best_hunk_size_ratio": f"{metric_result.best_hunk_size_ratio:.6f}",
                    "meaningful_anchor_recall": f"{metric_result.meaningful_anchor_recall:.6f}",
                    "meaningful_anchor_count": metric_result.meaningful_anchor_count,
                    "best_hunk_size": metric_result.best_hunk_size,
                    "best_hunk_file": metric_result.best_hunk_file,
                    "best_hunk_candidate_type": metric_result.best_hunk_candidate_type,
                    "candidate_hunk_count": metric_result.candidate_hunk_count,
                    "structural_available": metric_result.structural_available,
                    "structural_engine": metric_result.structural_engine,
                    "structural_language": metric_result.structural_language,
                    "structural_similarity": f"{metric_result.structural_similarity:.6f}",
                    "structural_node_recall": f"{metric_result.structural_node_recall:.6f}",
                    "structural_error": metric_result.structural_error,
                    "gumtree_available": metric_result.gumtree_available,
                    "gumtree_language": metric_result.gumtree_language,
                    "gumtree_operation_count": metric_result.gumtree_operation_count,
                    "gumtree_insert_ratio": f"{metric_result.gumtree_insert_ratio:.6f}",
                    "gumtree_delete_ratio": f"{metric_result.gumtree_delete_ratio:.6f}",
                    "gumtree_update_ratio": f"{metric_result.gumtree_update_ratio:.6f}",
                    "gumtree_move_ratio": f"{metric_result.gumtree_move_ratio:.6f}",
                    "gumtree_error": metric_result.gumtree_error,
                    "file_overlap_ratio": f"{metric_result.file_overlap_ratio:.6f}",
                    "changed_line_overlap_ratio": f"{metric_result.changed_line_overlap_ratio:.6f}",
                }
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate PR suggestion coverage metrics against labeled data.")
    parser.add_argument("--dataset-dir", type=Path, default=_DEFAULT_DATASET_DIR)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--enable-gumtree",
        action="store_true",
        help="Compute optional GumTree edit-script features for supported source files.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    examples = _load_labeled_examples(args.dataset_dir)
    metric_results = [
        _score_example(cast(_feature_engine.ScoringInput, example), enable_gumtree=args.enable_gumtree)
        for example in examples
    ]
    actual_percentages = [example.expected_landed_percentage for example in examples]
    baseline_percentages = [example.deterministic_landed_estimate for example in examples]
    predicted_percentages = [metric_result.predicted_percentage for metric_result in metric_results]

    print(f"examples: {len(examples)}")
    print(f"baseline MAE: {_mean_absolute_error(actual_percentages, baseline_percentages):.2f}")
    print(f"new metric MAE: {_mean_absolute_error(actual_percentages, predicted_percentages):.2f}")
    _write_scores(args.output, examples, metric_results)
    print(f"\nwrote per-example scores: {args.output}")


if __name__ == "__main__":
    main()

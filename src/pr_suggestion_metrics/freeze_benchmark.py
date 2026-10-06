"""Validate and freeze a confirmatory semantic-coverage benchmark."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import cohen_kappa_score

from pr_suggestion_metrics.artifact_io import read_jsonl_objects, write_jsonl_objects
from pr_suggestion_metrics.benchmark.contracts import (
    Split,
    validate_splits as _validate_splits,
)
from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.percentages import round_bounded_percentage, validate_continuous_percentage
from pr_suggestion_metrics.scientific_contracts import (
    AdjudicatedAnnotation,
    BenchmarkCandidate,
    HumanAnnotation,
)

BenchmarkExample = BenchmarkCandidate


def parse_args() -> argparse.Namespace:
    """Parse benchmark-freezing arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True, help="Provenance-complete example JSONL.")
    parser.add_argument("--annotations", type=Path, required=True, help="Independent blind human annotation JSONL.")
    parser.add_argument("--adjudications", type=Path, required=True, help="Final adjudicated annotation JSONL.")
    parser.add_argument("--splits", type=Path, required=True, help="CSV containing example_id and split.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--split-policy",
        choices=("repository_disjoint", "temporal"),
        default="repository_disjoint",
    )
    return parser.parse_args()


def _read_splits(path: Path) -> dict[str, Split]:
    assignments: dict[str, Split] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), start=2):
            example_id = (row.get("example_id") or "").strip()
            split = (row.get("split") or "").strip()
            if not example_id or split not in {"train", "development", "calibration", "test"}:
                raise ValueError(f"Invalid split assignment at {path}:{line_number}")
            if example_id in assignments:
                raise ValueError(f"Duplicate split assignment for {example_id}")
            assignments[example_id] = split  # type: ignore[assignment]
    return assignments


def _validate_annotations(
    example_ids: set[str],
    annotations: list[HumanAnnotation],
    adjudications: list[AdjudicatedAnnotation],
) -> tuple[dict[str, AdjudicatedAnnotation], dict[str, float | None], dict[str, list[str]]]:
    by_example: dict[str, list[HumanAnnotation]] = defaultdict(list)
    unknown_annotation_ids = sorted({annotation.example_id for annotation in annotations} - example_ids)
    if unknown_annotation_ids:
        raise ValueError(f"Annotations reference unknown examples: {unknown_annotation_ids}")
    unknown_adjudication_ids = sorted({adjudication.example_id for adjudication in adjudications} - example_ids)
    if unknown_adjudication_ids:
        raise ValueError(f"Adjudications reference unknown examples: {unknown_adjudication_ids}")

    annotation_keys: set[tuple[str, str]] = set()
    for annotation in annotations:
        annotation_key = (annotation.example_id, annotation.annotator_id)
        if annotation_key in annotation_keys:
            raise ValueError(f"Duplicate annotation record for {annotation.example_id}/{annotation.annotator_id}")
        annotation_keys.add(annotation_key)
        issues = annotation.validation_issues()
        if issues:
            raise ValueError(f"Invalid annotation {annotation.example_id}/{annotation.annotator_id}: {issues}")
        by_example[annotation.example_id].append(annotation)

    adjudicated_by_example: dict[str, AdjudicatedAnnotation] = {}
    absolute_differences: list[float] = []
    paired_percentages: list[tuple[float, float]] = []
    unit_definition_jaccards: list[float] = []
    decision_agreements: list[bool] = []
    abstained_by_example: dict[str, list[str]] = {}
    for example_id in sorted(example_ids):
        example_annotations = by_example.get(example_id, [])
        annotator_ids = {annotation.annotator_id for annotation in example_annotations}
        if len(example_annotations) != 2 or len(annotator_ids) != 2:
            raise ValueError(f"Example {example_id} requires exactly two independent annotators")
        guide_versions = {annotation.guide_version for annotation in example_annotations}
        if len(guide_versions) != 1:
            raise ValueError(f"Example {example_id} has inconsistent annotation guide versions")
        first, second = sorted(example_annotations, key=lambda item: item.annotator_id)
        decision_agreements.append(first.decision == second.decision)
        if any(annotation.decision != "scored" for annotation in example_annotations):
            abstained_by_example[example_id] = sorted(
                {
                    reason
                    for annotation in example_annotations
                    if annotation.decision == "abstain"
                    for reason in annotation.abstention_reasons
                }
            )
            continue
        first_units = {" ".join(unit.description.lower().split()) for unit in first.units}
        second_units = {" ".join(unit.description.lower().split()) for unit in second.units}
        unit_union = first_units | second_units
        unit_definition_jaccards.append(len(first_units & second_units) / len(unit_union) if unit_union else 1.0)
        percentages = [annotation.computed_percentage() for annotation in example_annotations]
        scored_percentages = [value for value in percentages if value is not None]
        paired_percentages.append((scored_percentages[0], scored_percentages[1]))
        for left_index, left in enumerate(scored_percentages):
            for right in scored_percentages[left_index + 1 :]:
                absolute_differences.append(abs(left - right))

    for adjudication in adjudications:
        issues = adjudication.validation_issues()
        if issues:
            raise ValueError(f"Invalid adjudication {adjudication.example_id}: {issues}")
        if adjudication.example_id in adjudicated_by_example:
            raise ValueError(f"Duplicate adjudication for {adjudication.example_id}")
        if adjudication.example_id in abstained_by_example:
            raise ValueError(f"Abstained example {adjudication.example_id} must not have an adjudication")
        source_ids = {annotation.annotator_id for annotation in by_example.get(adjudication.example_id, [])}
        if set(adjudication.source_annotator_ids) != source_ids:
            raise ValueError(f"Adjudication for {adjudication.example_id} must reference both source annotators")
        source_guide_version = by_example[adjudication.example_id][0].guide_version
        if adjudication.guide_version != source_guide_version:
            raise ValueError(f"Adjudication for {adjudication.example_id} uses a different guide version")
        adjudicated_by_example[adjudication.example_id] = adjudication

    scored_example_ids = example_ids - set(abstained_by_example)
    if set(adjudicated_by_example) != scored_example_ids:
        missing = sorted(scored_example_ids - set(adjudicated_by_example))
        extra = sorted(set(adjudicated_by_example) - scored_example_ids)
        raise ValueError(f"Adjudication/example mismatch; missing={missing}, extra={extra}")

    icc: float | None = None
    weighted_kappa: float | None = None
    if len(paired_percentages) >= 2:
        score_matrix = np.asarray(paired_percentages, dtype=float)
        target_means = np.mean(score_matrix, axis=1)
        grand_mean = float(np.mean(score_matrix))
        between = 2 * float(np.sum(np.square(target_means - grand_mean))) / (len(score_matrix) - 1)
        within = float(np.sum(np.square(score_matrix - target_means[:, None]))) / len(score_matrix)
        denominator = between + within
        icc = (between - within) / denominator if denominator else 1.0
        first_bands = np.floor(score_matrix[:, 0] / 10).astype(int)
        second_bands = np.floor(score_matrix[:, 1] / 10).astype(int)
        kappa = cohen_kappa_score(first_bands, second_bands, weights="quadratic")
        weighted_kappa = float(kappa) if np.isfinite(kappa) else None

    agreement: dict[str, float | None] = {
        "pairwise_comparisons": float(len(absolute_differences)),
        "mean_absolute_difference": (
            sum(absolute_differences) / len(absolute_differences) if absolute_differences else 0.0
        ),
        "within_5_points": (
            sum(value <= 5 for value in absolute_differences) / len(absolute_differences)
            if absolute_differences
            else 0.0
        ),
        "within_10_points": (
            sum(value <= 10 for value in absolute_differences) / len(absolute_differences)
            if absolute_differences
            else 0.0
        ),
        "abstained_examples": float(len(abstained_by_example)),
        "abstention_rate": len(abstained_by_example) / len(example_ids) if example_ids else 0.0,
        "decision_agreement": sum(decision_agreements) / len(decision_agreements) if decision_agreements else 0.0,
        "mean_unit_definition_jaccard": (
            sum(unit_definition_jaccards) / len(unit_definition_jaccards) if unit_definition_jaccards else None
        ),
        "continuous_score_icc_1_1": icc,
        "derived_band_quadratic_weighted_kappa": weighted_kappa,
    }
    return adjudicated_by_example, agreement, abstained_by_example


def freeze_benchmark(
    *,
    examples_path: Path,
    annotations_path: Path,
    adjudications_path: Path,
    splits_path: Path,
    output_dir: Path,
    split_policy: str,
) -> dict[str, Any]:
    """Validate evidence, then write immutable train/development/test artifacts."""
    raw_examples = read_jsonl_objects(examples_path)
    examples = [BenchmarkExample.model_validate(row) for row in raw_examples]
    if len({example.example_id for example in examples}) != len(examples):
        raise ValueError("Example IDs must be unique")
    for example in examples:
        issues = example.suggestion_provenance.validation_issues()
        if issues:
            raise ValueError(f"Example {example.example_id} has incomplete provenance: {issues}")

    annotations = [HumanAnnotation.model_validate(row) for row in read_jsonl_objects(annotations_path)]
    adjudications = [AdjudicatedAnnotation.model_validate(row) for row in read_jsonl_objects(adjudications_path)]
    example_ids = {example.example_id for example in examples}
    adjudicated_by_example, agreement, abstained_by_example = _validate_annotations(
        example_ids,
        annotations,
        adjudications,
    )
    assignments = _read_splits(splits_path)
    _validate_splits(examples, assignments, split_policy=split_policy)

    output_dir.mkdir(parents=True, exist_ok=False)
    split_rows: dict[Split, list[dict[str, Any]]] = {
        "train": [],
        "development": [],
        "calibration": [],
        "test": [],
    }
    private_test_labels: list[dict[str, Any]] = []
    abstained_rows: list[dict[str, Any]] = []
    for raw_example, example in sorted(zip(raw_examples, examples, strict=True), key=lambda pair: pair[1].example_id):
        if example.example_id in abstained_by_example:
            abstained_rows.append(
                {
                    **raw_example,
                    "abstention_reasons": abstained_by_example[example.example_id],
                }
            )
            continue
        split = assignments[example.example_id]
        adjudication = adjudicated_by_example[example.example_id]
        percentage = adjudication.computed_percentage()
        if percentage is None:
            raise ValueError(f"Adjudication for {example.example_id} did not produce a score")
        percentage = validate_continuous_percentage(
            percentage,
            name=f"Adjudicated percentage for {example.example_id}",
        )
        rounded_percentage = round_bounded_percentage(percentage)
        if split == "test":
            split_rows[split].append(raw_example)
            private_test_labels.append(
                {
                    "example_id": example.example_id,
                    "coverage_unrounded": percentage,
                    "coverage_percentage": rounded_percentage,
                    "adjudication": adjudication.model_dump(mode="json"),
                }
            )
        else:
            split_rows[split].append(
                {
                    **raw_example,
                    "coverage_unrounded": percentage,
                    "coverage_percentage": rounded_percentage,
                    "adjudication": adjudication.model_dump(mode="json"),
                }
            )

    paths = {
        "train": output_dir / "train.jsonl",
        "development": output_dir / "development.jsonl",
        "calibration": output_dir / "calibration.jsonl",
        "test": output_dir / "test_inputs.jsonl",
        "private_test_labels": output_dir / "test_labels.private.jsonl",
        "abstained": output_dir / "abstained.jsonl",
    }
    for split, path in (
        ("train", paths["train"]),
        ("development", paths["development"]),
        ("calibration", paths["calibration"]),
        ("test", paths["test"]),
    ):
        write_jsonl_objects(path, split_rows[split], sort_keys=True)
    write_jsonl_objects(paths["private_test_labels"], private_test_labels, sort_keys=True)
    write_jsonl_objects(paths["abstained"], abstained_rows, sort_keys=True)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "split_policy": split_policy,
        "counts": {split: len(rows) for split, rows in split_rows.items()},
        "abstained_count": len(abstained_rows),
        "repositories": len({example.repo for example in examples}),
        "pull_requests": len({(example.repo, example.pr_number) for example in examples}),
        "annotation_agreement": agreement,
        "input_sha256": {
            "examples": sha256_file(examples_path),
            "annotations": sha256_file(annotations_path),
            "adjudications": sha256_file(adjudications_path),
            "splits": sha256_file(splits_path),
        },
        "artifact_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "label_counts": dict(
            sorted(
                Counter(
                    round_bounded_percentage(value.computed_percentage() or 0)
                    for value in adjudicated_by_example.values()
                ).items()
            )
        ),
        "confirmatory_test_labels_are_private": True,
    }
    (output_dir / "benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    """Freeze a benchmark from validated human evidence."""
    args = parse_args()
    manifest = freeze_benchmark(
        examples_path=args.examples,
        annotations_path=args.annotations,
        adjudications_path=args.adjudications,
        splits_path=args.splits,
        output_dir=args.output_dir,
        split_policy=args.split_policy,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

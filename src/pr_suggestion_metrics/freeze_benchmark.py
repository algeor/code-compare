"""Validate and freeze a confirmatory semantic-coverage benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.scientific_contracts import (
    AdjudicatedAnnotation,
    HumanAnnotation,
    SuggestionProvenance,
)

Split = Literal["train", "development", "test"]


class BenchmarkExample(BaseModel):
    """Minimum fields required to freeze one benchmark example."""

    example_id: str
    repo: str
    pr_url: str
    pr_number: int
    suggested_diff: str
    landed_diff: str
    suggestion_provenance: SuggestionProvenance


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            rows.append(value)
    return rows


def _read_splits(path: Path) -> dict[str, Split]:
    assignments: dict[str, Split] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), start=2):
            example_id = (row.get("example_id") or "").strip()
            split = (row.get("split") or "").strip()
            if not example_id or split not in {"train", "development", "test"}:
                raise ValueError(f"Invalid split assignment at {path}:{line_number}")
            if example_id in assignments:
                raise ValueError(f"Duplicate split assignment for {example_id}")
            assignments[example_id] = split  # type: ignore[assignment]
    return assignments


def _normalized_diff(diff_text: str) -> str:
    return "\n".join(line.rstrip() for line in diff_text.strip().splitlines())


def _duplicate_fingerprint(example: BenchmarkExample) -> str:
    return hashlib.sha256(_normalized_diff(example.suggested_diff).encode("utf-8")).hexdigest()


def _validate_annotations(
    example_ids: set[str],
    annotations: list[HumanAnnotation],
    adjudications: list[AdjudicatedAnnotation],
) -> tuple[dict[str, AdjudicatedAnnotation], dict[str, float]]:
    by_example: dict[str, list[HumanAnnotation]] = defaultdict(list)
    for annotation in annotations:
        issues = annotation.validation_issues()
        if issues:
            raise ValueError(f"Invalid annotation {annotation.example_id}/{annotation.annotator_id}: {issues}")
        by_example[annotation.example_id].append(annotation)

    adjudicated_by_example: dict[str, AdjudicatedAnnotation] = {}
    absolute_differences: list[float] = []
    for example_id in sorted(example_ids):
        example_annotations = by_example.get(example_id, [])
        annotator_ids = {annotation.annotator_id for annotation in example_annotations}
        if len(annotator_ids) < 2:
            raise ValueError(f"Example {example_id} requires two independent annotators")
        if any(annotation.decision != "scored" for annotation in example_annotations):
            raise ValueError(f"Example {example_id} contains an abstention and cannot enter a scored benchmark")
        percentages = [annotation.computed_percentage() for annotation in example_annotations]
        scored_percentages = [value for value in percentages if value is not None]
        for left_index, left in enumerate(scored_percentages):
            for right in scored_percentages[left_index + 1 :]:
                absolute_differences.append(abs(left - right))

    for adjudication in adjudications:
        issues = adjudication.validation_issues()
        if issues:
            raise ValueError(f"Invalid adjudication {adjudication.example_id}: {issues}")
        if adjudication.example_id in adjudicated_by_example:
            raise ValueError(f"Duplicate adjudication for {adjudication.example_id}")
        source_ids = {annotation.annotator_id for annotation in by_example.get(adjudication.example_id, [])}
        if not set(adjudication.source_annotator_ids).issubset(source_ids):
            raise ValueError(f"Adjudication for {adjudication.example_id} references unknown source annotators")
        adjudicated_by_example[adjudication.example_id] = adjudication

    if set(adjudicated_by_example) != example_ids:
        missing = sorted(example_ids - set(adjudicated_by_example))
        extra = sorted(set(adjudicated_by_example) - example_ids)
        raise ValueError(f"Adjudication/example mismatch; missing={missing}, extra={extra}")

    agreement = {
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
    }
    return adjudicated_by_example, agreement


def _validate_splits(
    examples: list[BenchmarkExample],
    assignments: dict[str, Split],
    *,
    split_policy: str,
) -> None:
    example_ids = {example.example_id for example in examples}
    if set(assignments) != example_ids:
        missing = sorted(example_ids - set(assignments))
        extra = sorted(set(assignments) - example_ids)
        raise ValueError(f"Split/example mismatch; missing={missing}, extra={extra}")
    if set(assignments.values()) != {"train", "development", "test"}:
        raise ValueError("Frozen benchmark must contain train, development, and test examples")

    pr_splits: dict[tuple[str, int], set[Split]] = defaultdict(set)
    duplicate_splits: dict[str, set[Split]] = defaultdict(set)
    repository_splits: dict[str, set[Split]] = defaultdict(set)
    for example in examples:
        split = assignments[example.example_id]
        pr_splits[(example.repo, example.pr_number)].add(split)
        duplicate_splits[_duplicate_fingerprint(example)].add(split)
        repository_splits[example.repo].add(split)
    if any(len(splits) > 1 for splits in pr_splits.values()):
        raise ValueError("Examples from one pull request cross split boundaries")
    if any(len(splits) > 1 for splits in duplicate_splits.values()):
        raise ValueError("Exact duplicate examples cross split boundaries")
    if split_policy == "repository_disjoint" and any(len(splits) > 1 for splits in repository_splits.values()):
        raise ValueError("Repositories cross split boundaries under repository_disjoint policy")

    if split_policy == "temporal":
        split_order = {"train": 0, "development": 1, "test": 2}
        by_repository: dict[str, list[BenchmarkExample]] = defaultdict(list)
        for example in examples:
            by_repository[example.repo].append(example)
        for repository, repository_examples in by_repository.items():
            ordered = sorted(repository_examples, key=lambda item: item.suggestion_provenance.pr_merged_at or datetime.min)
            observed = [split_order[assignments[example.example_id]] for example in ordered]
            if observed != sorted(observed):
                raise ValueError(f"Temporal split order is violated in repository {repository}")


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
    raw_examples = _read_jsonl(examples_path)
    examples = [BenchmarkExample.model_validate(row) for row in raw_examples]
    if len({example.example_id for example in examples}) != len(examples):
        raise ValueError("Example IDs must be unique")
    for example in examples:
        issues = example.suggestion_provenance.validation_issues()
        if issues:
            raise ValueError(f"Example {example.example_id} has incomplete provenance: {issues}")

    annotations = [HumanAnnotation.model_validate(row) for row in _read_jsonl(annotations_path)]
    adjudications = [AdjudicatedAnnotation.model_validate(row) for row in _read_jsonl(adjudications_path)]
    example_ids = {example.example_id for example in examples}
    adjudicated_by_example, agreement = _validate_annotations(example_ids, annotations, adjudications)
    assignments = _read_splits(splits_path)
    _validate_splits(examples, assignments, split_policy=split_policy)

    output_dir.mkdir(parents=True, exist_ok=False)
    split_rows: dict[Split, list[dict[str, Any]]] = {"train": [], "development": [], "test": []}
    private_test_labels: list[dict[str, Any]] = []
    for raw_example, example in sorted(zip(raw_examples, examples, strict=True), key=lambda pair: pair[1].example_id):
        split = assignments[example.example_id]
        adjudication = adjudicated_by_example[example.example_id]
        percentage = adjudication.computed_percentage()
        if percentage is None:
            raise ValueError(f"Adjudication for {example.example_id} did not produce a score")
        if split == "test":
            split_rows[split].append(raw_example)
            private_test_labels.append(
                {
                    "example_id": example.example_id,
                    "coverage_unrounded": percentage,
                    "coverage_percentage": round(percentage),
                    "adjudication": adjudication.model_dump(mode="json"),
                }
            )
        else:
            split_rows[split].append(
                {
                    **raw_example,
                    "coverage_unrounded": percentage,
                    "coverage_percentage": round(percentage),
                    "adjudication": adjudication.model_dump(mode="json"),
                }
            )

    paths = {
        "train": output_dir / "train.jsonl",
        "development": output_dir / "development.jsonl",
        "test": output_dir / "test_inputs.jsonl",
        "private_test_labels": output_dir / "test_labels.private.jsonl",
    }
    for split, path in (("train", paths["train"]), ("development", paths["development"]), ("test", paths["test"])):
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in split_rows[split]), encoding="utf-8")
    paths["private_test_labels"].write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in private_test_labels),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "split_policy": split_policy,
        "counts": {split: len(rows) for split, rows in split_rows.items()},
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
            sorted(Counter(round(value.computed_percentage() or 0) for value in adjudicated_by_example.values()).items())
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

"""Plan deterministic, leakage-resistant benchmark split assignments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.artifact_io import read_jsonl_objects
from pr_suggestion_metrics.benchmark.contracts import (
    Split,
    SplitPolicy,
    near_duplicate_fingerprint,
    validate_splits,
)
from pr_suggestion_metrics.scientific_contracts import BenchmarkCandidate


_SPLIT_RATIOS: dict[Split, float] = {
    "train": 0.60,
    "development": 0.15,
    "calibration": 0.10,
    "test": 0.15,
}

_SPLIT_ORDER: tuple[Split, ...] = ("train", "development", "calibration", "test")


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _active_splits(component_count: int) -> list[Split]:
    if component_count < 3:
        raise ValueError("At least three independent groups are required to create train/development/test splits")
    return list(_SPLIT_ORDER) if component_count >= 4 else ["train", "development", "test"]


def _component_counts(component_count: int) -> dict[Split, int]:
    active_splits = _active_splits(component_count)
    counts: dict[Split, int] = {split: 1 for split in active_splits}
    remaining = component_count - len(active_splits)
    while remaining:
        split = max(active_splits, key=lambda name: _SPLIT_RATIOS[name] * component_count - counts[name])
        counts[split] += 1
        remaining -= 1
    return counts


def _assign_components(
    components: list[list[BenchmarkCandidate]],
    *,
    policy: SplitPolicy,
    seed: int,
) -> tuple[dict[str, Split], dict[Split, float]]:
    active_splits = _active_splits(len(components))
    target_ratios = _target_split_ratios(active_splits)
    total_rows = sum(len(component) for component in components)
    assignments: dict[str, Split] = {}

    if policy == "temporal":
        ordered = sorted(components, key=lambda component: _component_sort_key(component, policy, seed))
        offset = 0
        assigned_rows = 0
        for split_index, split in enumerate(active_splits):
            remaining_splits = len(active_splits) - split_index - 1
            if remaining_splits == 0:
                selected = ordered[offset:]
            else:
                target_rows = round(total_rows * sum(target_ratios[name] for name in active_splits[: split_index + 1]))
                selected = []
                while offset < len(ordered) - remaining_splits and (not selected or assigned_rows < target_rows):
                    selected.append(ordered[offset])
                    assigned_rows += len(ordered[offset])
                    offset += 1
            for component in selected:
                for example in component:
                    assignments[example.example_id] = split
        return assignments, target_ratios

    ordered = sorted(
        components,
        key=lambda component: (-len(component), str(_component_sort_key(component, policy, seed))),
    )
    rows_by_split = {split: 0 for split in active_splits}
    for split, component in zip(active_splits, ordered[: len(active_splits)], strict=True):
        rows_by_split[split] += len(component)
        for example in component:
            assignments[example.example_id] = split
    for component in ordered[len(active_splits) :]:
        split = max(
            active_splits,
            key=lambda name: (target_ratios[name] * total_rows - rows_by_split[name], -_SPLIT_ORDER.index(name)),
        )
        rows_by_split[split] += len(component)
        for example in component:
            assignments[example.example_id] = split
    return assignments, target_ratios


def _target_split_ratios(active_splits: list[Split]) -> dict[Split, float]:
    total = sum(_SPLIT_RATIOS[split] for split in active_splits)
    return {split: (_SPLIT_RATIOS[split] / total) for split in active_splits}


def _build_components(examples: list[BenchmarkCandidate], policy: SplitPolicy) -> list[list[BenchmarkCandidate]]:
    union_find = _UnionFind([example.example_id for example in examples])
    grouping_keys: dict[tuple[str, object], str] = {}
    for example in examples:
        keys: list[tuple[str, object]] = [
            ("pr", (example.repo, example.pr_number)),
            ("near_duplicate", near_duplicate_fingerprint(example)),
        ]
        if policy == "repository_disjoint":
            keys.append(("repository", example.repo))
        for key in keys:
            existing = grouping_keys.get(key)
            if existing is None:
                grouping_keys[key] = example.example_id
            else:
                union_find.union(existing, example.example_id)

    components: dict[str, list[BenchmarkCandidate]] = defaultdict(list)
    for example in examples:
        components[union_find.find(example.example_id)].append(example)
    return list(components.values())


def summarize_split_assignments(
    *,
    examples: list[BenchmarkCandidate],
    assignments: dict[str, Split],
    policy: SplitPolicy,
    included_example_ids: set[str] | None = None,
    coverage_by_example: dict[str, float] | None = None,
    target_split_ratios: dict[Split, float] | None = None,
) -> dict[str, Any]:
    """Return a deterministic per-split summary for reports and manifests."""
    included_ids = included_example_ids or {example.example_id for example in examples}
    selected_examples = [example for example in examples if example.example_id in included_ids]
    total_rows = len(selected_examples)
    selected_by_split: dict[Split, list[BenchmarkCandidate]] = {
        split: sorted(
            [example for example in selected_examples if assignments[example.example_id] == split],
            key=lambda example: example.example_id,
        )
        for split in _SPLIT_ORDER
    }

    group_counts: dict[Split, int] = {split: 0 for split in _SPLIT_ORDER}
    for component in _build_components(examples, policy):
        component_example_ids = [example.example_id for example in component if example.example_id in included_ids]
        if not component_example_ids:
            continue
        component_splits = {assignments[example_id] for example_id in component_example_ids}
        if len(component_splits) != 1:
            raise ValueError("Independent groups must not cross dataset splits")
        group_counts[next(iter(component_splits))] += 1

    def _coverage_summary(split: Split) -> dict[str, float | None]:
        if coverage_by_example is None:
            return {"max": None, "mean": None, "min": None}
        values = [
            coverage_by_example[example.example_id]
            for example in selected_by_split[split]
            if example.example_id in coverage_by_example
        ]
        if not values:
            return {"max": None, "mean": None, "min": None}
        return {
            "max": max(values),
            "mean": sum(values) / len(values),
            "min": min(values),
        }

    splits = {
        split: {
            "actual_percentage": (100.0 * len(selected_by_split[split]) / total_rows) if total_rows else 0.0,
            "coverage_percentage": _coverage_summary(split),
            "group_count": group_counts[split],
            "repo_count": len({example.repo for example in selected_by_split[split]}),
            "row_count": len(selected_by_split[split]),
            "target_percentage": (
                100.0 * target_split_ratios[split] if target_split_ratios is not None and split in target_split_ratios else None
            ),
        }
        for split in _SPLIT_ORDER
    }
    return {
        "splits": splits,
        "target_percentages": {
            split: 100.0 * target_split_ratios[split]
            for split in _SPLIT_ORDER
            if target_split_ratios is not None and split in target_split_ratios
        },
    }


def _component_identity(component: list[BenchmarkCandidate]) -> str:
    return "|".join(sorted(example.example_id for example in component))


def _component_sort_key(
    component: list[BenchmarkCandidate],
    policy: SplitPolicy,
    seed: int,
) -> tuple[datetime, str] | str:
    if policy == "temporal":
        timestamps = [example.suggestion_provenance.pr_merged_at for example in component]
        if any(timestamp is None for timestamp in timestamps):
            raise ValueError("Temporal split planning requires a merge timestamp for every example")
        resolved_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
        if any(timestamp.utcoffset() is None for timestamp in resolved_timestamps):
            raise ValueError("Temporal split planning requires timezone-aware merge timestamps")
        return max(timestamp.astimezone(UTC) for timestamp in resolved_timestamps), _component_identity(component)
    identity = _component_identity(component)
    return hashlib.sha256(f"{seed}:{identity}".encode("utf-8")).hexdigest()


def plan_splits(
    *,
    examples_path: Path,
    output_path: Path,
    report_path: Path,
    policy: SplitPolicy,
    seed: int,
) -> dict[str, Any]:
    """Write deterministic assignments that keep PRs and near duplicates together."""
    if policy not in {"repository_disjoint", "temporal"}:
        raise ValueError(f"Unsupported split policy: {policy}")
    examples = [BenchmarkCandidate.model_validate(row) for row in read_jsonl_objects(examples_path)]
    if len({example.example_id for example in examples}) != len(examples):
        raise ValueError("Example IDs must be unique")
    components = _build_components(examples, policy)
    target_splits = _component_counts(len(components))
    assignments, target_split_ratios = _assign_components(components, policy=policy, seed=seed)

    validate_splits(examples, assignments, split_policy=policy)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["example_id", "split"])
        writer.writeheader()
        for example_id in sorted(assignments):
            writer.writerow({"example_id": example_id, "split": assignments[example_id]})

    report = {
        "schema_version": "1.0",
        "policy": policy,
        "seed": seed,
        "examples": len(examples),
        "independent_components": len(components),
        "split_example_counts": dict(sorted(Counter(assignments.values()).items())),
        "split_repository_counts": {
            split: len({example.repo for example in examples if assignments[example.example_id] == split})
            for split in target_splits
        },
        "split_language_counts": {},
        "split_summary": summarize_split_assignments(
            examples=examples,
            assignments=assignments,
            policy=policy,
            target_split_ratios=target_split_ratios,
        ),
        "created_from": str(examples_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--policy", choices=("repository_disjoint", "temporal"), default="repository_disjoint")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = plan_splits(
        examples_path=args.examples,
        output_path=args.output,
        report_path=args.report,
        policy=args.policy,
        seed=args.seed,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

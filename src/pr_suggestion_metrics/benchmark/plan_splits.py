"""Plan deterministic, leakage-resistant benchmark split assignments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pr_suggestion_metrics.freeze_benchmark import (
    BenchmarkExample,
    Split,
    _near_duplicate_fingerprint,
    _read_jsonl,
    _validate_splits,
)


SplitPolicy = Literal["repository_disjoint", "temporal"]
_SPLIT_RATIOS: dict[Split, float] = {
    "train": 0.60,
    "development": 0.15,
    "calibration": 0.10,
    "test": 0.15,
}


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


def _component_counts(component_count: int) -> dict[Split, int]:
    split_names = list(_SPLIT_RATIOS)
    if component_count < 3:
        raise ValueError("At least three independent groups are required to create train/development/test splits")
    active_splits: list[Split] = split_names if component_count >= 4 else ["train", "development", "test"]
    counts: dict[Split, int] = {split: 1 for split in active_splits}
    remaining = component_count - len(active_splits)
    while remaining:
        split = max(active_splits, key=lambda name: _SPLIT_RATIOS[name] * component_count - counts[name])
        counts[split] += 1
        remaining -= 1
    return counts


def _build_components(examples: list[BenchmarkExample], policy: SplitPolicy) -> list[list[BenchmarkExample]]:
    union_find = _UnionFind([example.example_id for example in examples])
    grouping_keys: dict[tuple[str, object], str] = {}
    for example in examples:
        keys: list[tuple[str, object]] = [
            ("pr", (example.repo, example.pr_number)),
            ("near_duplicate", _near_duplicate_fingerprint(example)),
        ]
        if policy == "repository_disjoint":
            keys.append(("repository", example.repo))
        for key in keys:
            existing = grouping_keys.get(key)
            if existing is None:
                grouping_keys[key] = example.example_id
            else:
                union_find.union(existing, example.example_id)

    components: dict[str, list[BenchmarkExample]] = defaultdict(list)
    for example in examples:
        components[union_find.find(example.example_id)].append(example)
    return list(components.values())


def _component_sort_key(component: list[BenchmarkExample], policy: SplitPolicy, seed: int) -> str:
    if policy == "temporal":
        timestamps = [example.suggestion_provenance.pr_merged_at for example in component]
        if any(timestamp is None for timestamp in timestamps):
            raise ValueError("Temporal split planning requires a merge timestamp for every example")
        return max(timestamp for timestamp in timestamps if timestamp is not None).isoformat()
    identity = "|".join(sorted(example.example_id for example in component))
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
    examples = [BenchmarkExample.model_validate(row) for row in _read_jsonl(examples_path)]
    if len({example.example_id for example in examples}) != len(examples):
        raise ValueError("Example IDs must be unique")
    components = _build_components(examples, policy)
    counts = _component_counts(len(components))
    ordered = sorted(components, key=lambda component: _component_sort_key(component, policy, seed))

    assignments: dict[str, Split] = {}
    offset = 0
    for split, count in counts.items():
        for component in ordered[offset : offset + count]:
            for example in component:
                assignments[example.example_id] = split
        offset += count

    _validate_splits(examples, assignments, split_policy=policy)

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
            for split in counts
        },
        "split_language_counts": {},
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

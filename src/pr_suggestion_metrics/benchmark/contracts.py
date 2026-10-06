"""Shared benchmark identity and split-validation contracts."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.scientific_contracts import BenchmarkCandidate


Split = Literal["train", "development", "calibration", "test"]
SplitPolicy = Literal["repository_disjoint", "temporal"]


def duplicate_fingerprint(example: BenchmarkCandidate) -> str:
    normalized_diff = "\n".join(line.rstrip() for line in example.suggested_diff.strip().splitlines())
    return hashlib.sha256(normalized_diff.encode("utf-8")).hexdigest()


def near_duplicate_fingerprint(example: BenchmarkCandidate) -> str:
    tokens: list[str] = []
    parsed = parse_unified_diff(example.suggested_diff)
    for file_diff in parsed.files:
        if file_diff.rename_from or file_diff.rename_to:
            tokens.extend(("rename", file_diff.rename_from or "", file_diff.rename_to or ""))
    for line in parsed.changed_lines:
        if not line.text.strip():
            continue
        tokens.append(line.operation)
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|\S", line.text):
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
                tokens.append("<identifier>")
            elif re.fullmatch(r"\d+(?:\.\d+)?", token):
                tokens.append("<number>")
            else:
                tokens.append(token)
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()


def validate_splits(
    examples: list[BenchmarkCandidate],
    assignments: dict[str, Split],
    *,
    split_policy: str,
) -> None:
    if split_policy not in {"repository_disjoint", "temporal"}:
        raise ValueError(f"Unsupported split policy: {split_policy}")
    example_ids = {example.example_id for example in examples}
    if set(assignments) != example_ids:
        missing = sorted(example_ids - set(assignments))
        extra = sorted(set(assignments) - example_ids)
        raise ValueError(f"Split/example mismatch; missing={missing}, extra={extra}")
    if not {"train", "development", "test"}.issubset(set(assignments.values())):
        raise ValueError("Frozen benchmark must contain train, development, and test examples")

    pr_splits: dict[tuple[str, int], set[Split]] = defaultdict(set)
    duplicate_splits: dict[str, set[Split]] = defaultdict(set)
    near_duplicate_splits: dict[str, set[Split]] = defaultdict(set)
    repository_splits: dict[str, set[Split]] = defaultdict(set)
    for example in examples:
        split = assignments[example.example_id]
        pr_splits[(example.repo, example.pr_number)].add(split)
        duplicate_splits[duplicate_fingerprint(example)].add(split)
        near_duplicate_splits[near_duplicate_fingerprint(example)].add(split)
        repository_splits[example.repo].add(split)
    if any(len(splits) > 1 for splits in pr_splits.values()):
        raise ValueError("Examples from one pull request cross split boundaries")
    if any(len(splits) > 1 for splits in duplicate_splits.values()):
        raise ValueError("Exact duplicate examples cross split boundaries")
    if any(len(splits) > 1 for splits in near_duplicate_splits.values()):
        raise ValueError("Near-duplicate examples cross split boundaries")
    if split_policy == "repository_disjoint" and any(len(splits) > 1 for splits in repository_splits.values()):
        raise ValueError("Repositories cross split boundaries under repository_disjoint policy")

    if split_policy == "temporal":
        split_order = {"train": 0, "development": 1, "calibration": 2, "test": 3}
        by_repository: dict[str, list[BenchmarkCandidate]] = defaultdict(list)
        for example in examples:
            by_repository[example.repo].append(example)
        for repository, repository_examples in by_repository.items():
            ordered = sorted(
                repository_examples,
                key=lambda item: item.suggestion_provenance.pr_merged_at or datetime.min.replace(tzinfo=UTC),
            )
            observed = [split_order[assignments[example.example_id]] for example in ordered]
            if observed != sorted(observed):
                raise ValueError(f"Temporal split order is violated in repository {repository}")

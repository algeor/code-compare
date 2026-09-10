"""Exact changed-line coverage used by pipeline-fl-control-plane PIPELINE3-1376."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DiffChangeUnit:
    """One path-, operation-, and content-sensitive changed-line occurrence."""

    file_path: str
    operation: Literal["added", "removed"]
    content: str


def parse_diff_change_units(diff_text: str) -> list[DiffChangeUnit]:
    """Parse PIPELINE3-1376 change units from a unified diff."""
    units: list[DiffChangeUnit] = []
    old_path: str | None = None
    new_path: str | None = None
    inside_hunk = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            old_path = None
            new_path = None
            inside_hunk = False
            continue
        if not inside_hunk and line.startswith("--- "):
            old_path = _normalize_diff_path(line[4:])
            continue
        if not inside_hunk and line.startswith("+++ "):
            new_path = _normalize_diff_path(line[4:])
            continue
        if line.startswith("@@"):
            inside_hunk = True
            continue
        if not inside_hunk or line.startswith("\\"):
            continue
        if line.startswith("+") and new_path is not None:
            units.append(DiffChangeUnit(file_path=new_path, operation="added", content=line[1:].rstrip()))
        elif line.startswith("-") and old_path is not None:
            units.append(DiffChangeUnit(file_path=old_path, operation="removed", content=line[1:].rstrip()))

    return units


def compute_suggestion_coverage_score(
    suggested_units: Iterable[DiffChangeUnit],
    merged_units: Iterable[DiffChangeUnit],
) -> float:
    """Return matched suggested occurrences divided by suggested occurrences."""
    suggested_counts = Counter(suggested_units)
    if not suggested_counts:
        return 0.0

    matched_count = sum((suggested_counts & Counter(merged_units)).values())
    return matched_count / sum(suggested_counts.values())


def build_suggested_change_unit_union(suggested_diffs: Iterable[str]) -> list[DiffChangeUnit]:
    """Build the multiset union used when an inspection has multiple handlers."""
    unit_counts: Counter[DiffChangeUnit] = Counter()
    for suggested_diff in suggested_diffs:
        unit_counts |= Counter(parse_diff_change_units(suggested_diff))
    return list(unit_counts.elements())


def score_diff_pair(suggested_diff: str, merged_diff: str) -> float:
    """Score one suggestion/merged-PR pair with the production algorithm."""
    return compute_suggestion_coverage_score(
        parse_diff_change_units(suggested_diff),
        parse_diff_change_units(merged_diff),
    )


def _normalize_diff_path(path: str) -> str | None:
    cleaned = path.strip()
    if cleaned == "/dev/null":
        return None
    if cleaned.startswith(("a/", "b/")):
        return cleaned[2:]
    return cleaned

"""Deterministic, evidence-bearing coverage for unified-diff change units."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from pr_suggestion_metrics.diff.parser import parse_unified_diff


ChangeKind = Literal["addition", "deletion", "rename"]
class ChangeUnit(BaseModel):
    """One changed line or rename operation extracted from a unified diff."""

    unit_id: str
    kind: ChangeKind
    path: str
    text: str
    hunk_index: int
    old_path: str | None = None
    new_path: str | None = None
    source_line: int | None = None
    target_line: int | None = None


class ChangeUnitMatch(BaseModel):
    """One exact one-to-one match between suggested and landed change units."""

    suggested_unit_id: str
    landed_unit_id: str
    kind: ChangeKind
    suggested_path: str
    landed_path: str
    moved_across_files: bool


class ChangeCoverageEvidence(BaseModel):
    """Transparent line-operation coverage evidence across all diff shapes."""

    method: Literal["exact_normalized_change_unit_coverage"] = "exact_normalized_change_unit_coverage"
    coverage_percentage: int | None
    matched_units: int
    total_suggested_units: int
    matched_by_kind: dict[str, int]
    suggested_by_kind: dict[str, int]
    matches: list[ChangeUnitMatch]
    unmatched_suggested_units: list[ChangeUnit]
    warnings: list[str] = Field(default_factory=list)


def _normalize_change_text(text: str) -> str:
    return " ".join(text.strip().split())


def extract_change_units(diff_text: str, *, prefix: str) -> list[ChangeUnit]:
    """Extract additions, deletions, and explicit renames from a unified diff."""
    units: list[ChangeUnit] = []
    parsed = parse_unified_diff(diff_text)

    def append_unit(
        kind: ChangeKind,
        path: str,
        text: str,
        *,
        hunk_index: int,
        old_path: str | None,
        new_path: str | None,
        source_line: int | None = None,
        target_line: int | None = None,
    ) -> None:
        normalized = _normalize_change_text(text)
        if not normalized:
            return
        units.append(
            ChangeUnit(
                unit_id=f"{prefix}-{len(units) + 1}",
                kind=kind,
                path=path,
                text=normalized,
                hunk_index=hunk_index,
                old_path=old_path,
                new_path=new_path,
                source_line=source_line,
                target_line=target_line,
            )
        )

    for file_diff in parsed.files:
        if file_diff.rename_from and file_diff.rename_to:
            append_unit(
                "rename",
                file_diff.rename_to,
                f"{file_diff.rename_from} -> {file_diff.rename_to}",
                hunk_index=0,
                old_path=file_diff.rename_from,
                new_path=file_diff.rename_to,
            )
        for line in file_diff.changed_lines:
            path = line.path or "unknown"
            append_unit(
                "addition" if line.operation == "addition" else "deletion",
                path,
                line.text,
                hunk_index=line.hunk_index,
                old_path=line.old_path,
                new_path=line.new_path,
                source_line=line.old_line_number,
                target_line=line.new_line_number,
            )
    return units


def analyze_change_coverage(suggested_diff: str, landed_diff: str) -> ChangeCoverageEvidence:
    """Match exact normalized change units one-to-one and return inspectable evidence."""
    suggested_units = extract_change_units(suggested_diff, prefix="suggested")
    landed_units = extract_change_units(landed_diff, prefix="landed")
    available = set(range(len(landed_units)))
    matches: list[ChangeUnitMatch] = []
    unmatched: list[ChangeUnit] = []

    for suggested in suggested_units:
        candidates = [
            index
            for index in available
            if landed_units[index].kind == suggested.kind and landed_units[index].text == suggested.text
        ]
        if not candidates:
            unmatched.append(suggested)
            continue
        selected = min(candidates, key=lambda index: landed_units[index].path != suggested.path)
        landed = landed_units[selected]
        available.remove(selected)
        matches.append(
            ChangeUnitMatch(
                suggested_unit_id=suggested.unit_id,
                landed_unit_id=landed.unit_id,
                kind=suggested.kind,
                suggested_path=suggested.path,
                landed_path=landed.path,
                moved_across_files=suggested.path != landed.path,
            )
        )

    total = len(suggested_units)
    warnings = [
        "This is exact normalized change-unit coverage, not semantic equivalence or causal adoption.",
        "Final-state persistence and pre-existing code require repository revision reconstruction.",
    ]
    if total == 0:
        warnings.append("No additions, deletions, or explicit rename operations were found in the suggestion diff.")
    return ChangeCoverageEvidence(
        coverage_percentage=round(100 * len(matches) / total) if total else None,
        matched_units=len(matches),
        total_suggested_units=total,
        matched_by_kind=dict(Counter(match.kind for match in matches)),
        suggested_by_kind=dict(Counter(unit.kind for unit in suggested_units)),
        matches=matches,
        unmatched_suggested_units=unmatched,
        warnings=warnings,
    )

"""Deterministic, evidence-bearing coverage for unified-diff change units."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Literal

from pydantic import BaseModel, Field

from pr_suggestion_metrics.diff.parser import (
    DiffAssessmentStatus,
    DiffDiagnostic,
    DiffDialect,
    assess_unified_diff,
    parse_unified_diff,
)


ChangeKind = Literal["addition", "deletion", "rename"]
MatchScope = Literal["strict_same_file", "relaxed_cross_file"]
DiffEvidenceSource = Literal["suggested_diff", "merged_pr_diff"]


class DiffParserEvidence(BaseModel):
    """Typed parser validity evidence for one exact-evidence input."""

    source: DiffEvidenceSource
    dialect: DiffDialect
    status: DiffAssessmentStatus
    diagnostics: list[DiffDiagnostic] = Field(default_factory=list)


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


class ChangeCoverageBucket(BaseModel):
    """Coverage for one matching scope using all suggested units as denominator."""

    match_scope: MatchScope
    coverage_percentage: int | None
    matched_units: int
    total_suggested_units: int
    matched_by_kind: dict[str, int]
    matches: list[ChangeUnitMatch]


class ChangeCoverageEvidence(BaseModel):
    """Transparent line-operation coverage evidence across all diff shapes."""

    evidence_schema_version: Literal["1.1"] = "1.1"
    method: Literal["exact_normalized_change_unit_coverage"] = "exact_normalized_change_unit_coverage"
    strict_same_file: ChangeCoverageBucket
    relaxed_cross_file: ChangeCoverageBucket
    coverage_percentage: int | None
    matched_units: int
    total_suggested_units: int
    matched_by_kind: dict[str, int]
    suggested_by_kind: dict[str, int]
    matches: list[ChangeUnitMatch]
    unmatched_suggested_units: list[ChangeUnit]
    suggested_diff_assessment: DiffParserEvidence
    merged_pr_diff_assessment: DiffParserEvidence
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
    """Match normalized change units by strict scope first, then relaxed path scope."""
    suggested_assessment = assess_unified_diff(suggested_diff, dialect="suggestion_fragment")
    merged_assessment = assess_unified_diff(landed_diff, dialect="git_unified")
    suggested_units = extract_change_units(suggested_diff, prefix="suggested")
    landed_units = extract_change_units(landed_diff, prefix="landed")
    landed_by_exact_key: dict[tuple[ChangeKind, str, str], deque[int]] = defaultdict(deque)
    for index, landed in enumerate(landed_units):
        landed_by_exact_key[(landed.kind, landed.text, landed.path)].append(index)

    matched_landed_indices: set[int] = set()
    strict_pairs: dict[int, int] = {}
    for suggested_index, suggested in enumerate(suggested_units):
        exact_candidates = landed_by_exact_key[(suggested.kind, suggested.text, suggested.path)]
        if exact_candidates:
            landed_index = exact_candidates.popleft()
            matched_landed_indices.add(landed_index)
            strict_pairs[suggested_index] = landed_index

    landed_by_content_key: dict[tuple[ChangeKind, str], deque[int]] = defaultdict(deque)
    for index, landed in enumerate(landed_units):
        if index not in matched_landed_indices:
            landed_by_content_key[(landed.kind, landed.text)].append(index)

    relaxed_pairs: dict[int, int] = {}
    for suggested_index, suggested in enumerate(suggested_units):
        if suggested_index in strict_pairs:
            continue
        content_candidates = landed_by_content_key[(suggested.kind, suggested.text)]
        if content_candidates:
            relaxed_pairs[suggested_index] = content_candidates.popleft()

    matches: list[ChangeUnitMatch] = []
    strict_matches: list[ChangeUnitMatch] = []
    relaxed_matches: list[ChangeUnitMatch] = []
    unmatched: list[ChangeUnit] = []

    for suggested_index, suggested in enumerate(suggested_units):
        matched_landed_index = strict_pairs.get(suggested_index)
        match_scope: MatchScope = "strict_same_file"
        if matched_landed_index is None:
            matched_landed_index = relaxed_pairs.get(suggested_index)
            match_scope = "relaxed_cross_file"
        if matched_landed_index is None:
            unmatched.append(suggested)
            continue
        landed = landed_units[matched_landed_index]
        match = ChangeUnitMatch(
            suggested_unit_id=suggested.unit_id,
            landed_unit_id=landed.unit_id,
            kind=suggested.kind,
            suggested_path=suggested.path,
            landed_path=landed.path,
            moved_across_files=suggested.path != landed.path,
        )
        matches.append(match)
        if match_scope == "strict_same_file":
            strict_matches.append(match)
        else:
            relaxed_matches.append(match)

    total = len(suggested_units)
    inputs_are_valid = suggested_assessment.is_valid and merged_assessment.is_valid
    if not inputs_are_valid:
        strict_matches = []
        relaxed_matches = []
        matches = []
        unmatched = suggested_units.copy()
    warnings = [
        "Strict evidence requires the same operation, normalized content, and file path.",
        "Relaxed evidence requires the same operation and normalized content but permits a different file path.",
        "Compatibility fields combine strict and relaxed matches for one schema cycle.",
        "This evidence is not semantic equivalence or causal adoption.",
        "Final-state persistence and pre-existing code require repository revision reconstruction.",
    ]
    if total == 0:
        warnings.append("No additions, deletions, or explicit rename operations were found in the suggestion diff.")
    for source, assessment in (
        ("suggested_diff", suggested_assessment),
        ("merged_pr_diff", merged_assessment),
    ):
        warnings.extend(
            f"{source} parser {diagnostic.severity} [{diagnostic.code}]: {diagnostic.message}"
            for diagnostic in assessment.diagnostics
        )
    if not inputs_are_valid:
        warnings.append("Coverage is unavailable because at least one input diff is structurally invalid.")

    def coverage_bucket(match_scope: MatchScope, bucket_matches: list[ChangeUnitMatch]) -> ChangeCoverageBucket:
        return ChangeCoverageBucket(
            match_scope=match_scope,
            coverage_percentage=round(100 * len(bucket_matches) / total) if total and inputs_are_valid else None,
            matched_units=len(bucket_matches),
            total_suggested_units=total,
            matched_by_kind=dict(Counter(match.kind for match in bucket_matches)),
            matches=bucket_matches,
        )

    return ChangeCoverageEvidence(
        strict_same_file=coverage_bucket("strict_same_file", strict_matches),
        relaxed_cross_file=coverage_bucket("relaxed_cross_file", relaxed_matches),
        coverage_percentage=round(100 * len(matches) / total) if total and inputs_are_valid else None,
        matched_units=len(matches),
        total_suggested_units=total,
        matched_by_kind=dict(Counter(match.kind for match in matches)),
        suggested_by_kind=dict(Counter(unit.kind for unit in suggested_units)),
        matches=matches,
        unmatched_suggested_units=unmatched,
        suggested_diff_assessment=DiffParserEvidence(
            source="suggested_diff",
            dialect=suggested_assessment.dialect,
            status=suggested_assessment.status,
            diagnostics=list(suggested_assessment.diagnostics),
        ),
        merged_pr_diff_assessment=DiffParserEvidence(
            source="merged_pr_diff",
            dialect=merged_assessment.dialect,
            status=merged_assessment.status,
            diagnostics=list(merged_assessment.diagnostics),
        ),
        warnings=warnings,
    )

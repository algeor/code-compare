"""Scoring contracts and immutable feature-engine value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pr_suggestion_metrics.diff.parser import DiffDiagnostic, DiffDialect


RawDiffAssessmentStatus = Literal["valid", "invalid", "valid_but_unsupported"]
RawDiffSource = Literal["suggested_diff", "merged_pr_diff"]


@dataclass(frozen=True)
class RawDiffAssessment:
    """Feature-level validity and applicability assessment for one raw diff."""

    source: RawDiffSource
    dialect: DiffDialect
    status: RawDiffAssessmentStatus
    diagnostics: tuple[DiffDiagnostic, ...]
    support_issues: tuple[str, ...]

    @property
    def reasons(self) -> tuple[str, ...]:
        """Return stable parser and shape-support reasons for compatibility APIs."""
        diagnostic_reasons = tuple(
            f"{self.source} is invalid [{diagnostic.code}]: {diagnostic.message}"
            for diagnostic in self.diagnostics
        )
        return diagnostic_reasons + self.support_issues

class ScoringInput(Protocol):
    """Narrow input contract required by deterministic scoring."""

    @property
    def suggested_diff(self) -> str: ...

    @property
    def landed_diff(self) -> str: ...

    @property
    def file_overlap_ratio(self) -> float: ...

    @property
    def changed_line_overlap_ratio(self) -> float: ...

@dataclass(frozen=True)
class ScoringExample:
    """Label-free suggestion/PR-diff pair used by the public scoring boundary."""

    suggested_diff: str
    landed_diff: str
    file_overlap_ratio: float
    changed_line_overlap_ratio: float

@dataclass(frozen=True)
class MetricResult:
    """Computed deterministic suggestion coverage metrics for one example."""

    exact_normalized_match: bool
    suggestion_language: str
    tokenizer: str
    line_recall: float
    token_recall: float
    identifier_normalized_token_recall: float
    literal_normalized_token_recall: float
    identifier_and_literal_normalized_token_recall: float
    best_added_line_overlap: float
    best_hunk_token_recall: float
    best_hunk_token_precision: float
    best_hunk_token_f1: float
    best_hunk_identifier_normalized_recall: float
    best_hunk_literal_normalized_recall: float
    best_hunk_identifier_and_literal_normalized_recall: float
    best_hunk_contiguous_line_ratio: float
    best_hunk_token_lcs_recall: float
    best_hunk_size_ratio: float
    meaningful_anchor_recall: float
    meaningful_anchor_count: int
    best_hunk_size: int
    best_hunk_file: str
    best_hunk_candidate_type: str
    candidate_hunk_count: int
    structural_available: bool
    structural_engine: str
    structural_language: str
    structural_similarity: float
    structural_node_recall: float
    structural_error: str
    gumtree_available: bool
    gumtree_language: str
    gumtree_operation_count: int
    gumtree_insert_ratio: float
    gumtree_delete_ratio: float
    gumtree_update_ratio: float
    gumtree_move_ratio: float
    gumtree_error: str
    file_overlap_ratio: float
    changed_line_overlap_ratio: float
    predicted_percentage: int

@dataclass(frozen=True)
class TokenizedText:
    """Tokens plus the strategy used to derive them."""

    language: str
    tokenizer: str
    tokens: list[str]

@dataclass(frozen=True)
class CandidateHunk:
    """One landed-diff candidate chunk compared against a suggestion."""

    path: str
    lines: list[str]
    candidate_type: str

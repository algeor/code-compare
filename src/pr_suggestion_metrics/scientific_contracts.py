"""Validated contracts for provenance and human benchmark evidence."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FileSnapshot(BaseModel):
    """Text of one repository file bound to an immutable revision."""

    revision_sha: str
    path: str
    content: str
    content_sha256: str
    source: str

    @model_validator(mode="after")
    def verify_content_hash(self) -> FileSnapshot:
        """Reject snapshots whose text no longer matches the recorded digest."""
        actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if actual != self.content_sha256:
            raise ValueError("file snapshot content hash mismatch")
        return self


class SuggestionProvenance(BaseModel):
    """Immutable source metadata needed to interpret one suggestion/merge pair."""

    schema_version: Literal["1.0"] = "1.0"
    source_kind: Literal["github_review_comment", "github_issue_comment", "hdlf", "inspection_api", "unknown"]
    suggestion_id: str
    comment_url: str | None = None
    author_login: str | None = None
    suggestion_created_at: datetime | None = None
    suggestion_updated_at: datetime | None = None
    comment_commit_sha: str | None = None
    original_commit_sha: str | None = None
    path: str | None = None
    line: int | None = None
    start_line: int | None = None
    side: str | None = None
    start_side: str | None = None
    original_line: int | None = None
    original_start_line: int | None = None
    original_position: int | None = None
    pull_base_sha: str | None = None
    pull_head_sha: str | None = None
    merge_commit_sha: str | None = None
    pr_merged_at: datetime | None = None
    compared_diff_base_sha: str | None = None
    compared_diff_head_sha: str | None = None
    compared_diff_source: str | None = None
    suggestion_base_snapshot: FileSnapshot | None = None
    final_state_snapshot: FileSnapshot | None = None
    collection_errors: list[str] = Field(default_factory=list)

    def validation_issues(self) -> list[str]:
        """Return evidence gaps that prevent a strong temporal-coverage claim."""
        issues: list[str] = []
        if self.suggestion_created_at is None:
            issues.append("missing suggestion creation timestamp")
        if self.pr_merged_at is None:
            issues.append("missing PR merge timestamp")
        if self.suggestion_created_at is not None and self.pr_merged_at is not None:
            if self.suggestion_created_at >= self.pr_merged_at:
                issues.append("suggestion was not created before PR merge")
        if self.source_kind == "github_review_comment":
            if self.original_commit_sha is None and self.comment_commit_sha is None:
                issues.append("missing review-comment commit anchor")
            if self.path is None:
                issues.append("missing review-comment file path")
        if self.compared_diff_base_sha is None or self.compared_diff_head_sha is None:
            issues.append("missing immutable revisions for compared PR diff")
        if self.merge_commit_sha is None:
            issues.append("missing merge commit SHA")
        if self.suggestion_base_snapshot is None:
            issues.append("missing suggestion-time target file snapshot")
        if self.final_state_snapshot is None:
            issues.append("missing final merged file snapshot")
        issues.extend(f"collection error: {error}" for error in self.collection_errors)
        return issues

    @property
    def is_temporally_verified(self) -> bool:
        """Return whether required chronology and immutable revision evidence is present."""
        return not self.validation_issues()


class UnitCredit(float, Enum):
    """Allowed fixed semantic-unit credits."""

    ABSENT = 0.0
    PARTIAL = 0.5
    LANDED = 1.0


class SemanticUnit(BaseModel):
    """One independently judgeable unit in a human annotation."""

    unit_id: str
    description: str
    weight: int = Field(ge=1, le=3)
    credit: UnitCredit
    status: Literal[
        "landed_exactly",
        "landed_equivalently",
        "landed_partially",
        "absent",
        "different_implementation",
    ]
    evidence: list[str] = Field(min_length=1)
    preexisting: bool

    @model_validator(mode="after")
    def verify_status_credit(self) -> SemanticUnit:
        """Enforce the annotation guide's fixed status-to-credit mapping."""
        expected_credit = {
            "landed_exactly": UnitCredit.LANDED,
            "landed_equivalently": UnitCredit.LANDED,
            "landed_partially": UnitCredit.PARTIAL,
            "absent": UnitCredit.ABSENT,
            "different_implementation": UnitCredit.ABSENT,
        }[self.status]
        if self.credit != expected_credit:
            raise ValueError(f"status {self.status} requires credit {expected_credit.value}")
        return self


class HumanAnnotation(BaseModel):
    """One blind human judgment with a mechanically reproducible percentage."""

    schema_version: Literal["1.0"] = "1.0"
    guide_version: str
    example_id: str
    annotator_id: str
    decision: Literal["scored", "abstain"]
    abstention_reasons: list[str] = Field(default_factory=list)
    units: list[SemanticUnit] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] | None = None
    notes: str = ""

    def computed_percentage(self) -> float | None:
        """Compute the annotation percentage from units, weights, and fixed credits."""
        if self.decision == "abstain":
            return None
        if not self.units:
            raise ValueError("A scored annotation must contain at least one semantic unit")
        denominator = sum(unit.weight for unit in self.units)
        numerator = sum(unit.weight * unit.credit for unit in self.units)
        return 100.0 * numerator / denominator

    def validation_issues(self) -> list[str]:
        """Return internal inconsistencies in one annotation record."""
        issues: list[str] = []
        if self.decision == "abstain":
            if not self.abstention_reasons:
                issues.append("abstention requires at least one reason")
            if self.units:
                issues.append("abstention must not contain scored units")
            return issues
        if self.abstention_reasons:
            issues.append("scored annotation must not contain abstention reasons")
        if not self.units:
            issues.append("scored annotation requires semantic units")
        if len({unit.unit_id for unit in self.units}) != len(self.units):
            issues.append("semantic unit IDs must be unique within an annotation")
        return issues


class AdjudicatedAnnotation(HumanAnnotation):
    """Final human decision linked to the independent annotations it resolves."""

    source_annotator_ids: list[str] = Field(min_length=2)
    resolution_notes: str = Field(min_length=1)

    def validation_issues(self) -> list[str]:
        """Return inconsistencies in the final adjudicated record."""
        issues = super().validation_issues()
        if len(set(self.source_annotator_ids)) < 2:
            issues.append("adjudication requires at least two distinct source annotators")
        if self.annotator_id in self.source_annotator_ids:
            issues.append("adjudicator must be distinct from source annotators")
        return issues

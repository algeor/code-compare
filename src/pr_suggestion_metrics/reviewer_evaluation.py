"""Evidence-based scoring and mistake explanations for AI code reviews."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator


ReviewCriterion = Literal[
    "correctness",
    "completeness",
    "localization",
    "severity",
    "actionability",
    "fix_safety",
    "rationale",
]
AssessmentVerdict = Literal["correct", "partially_correct", "incorrect", "missed"]
EvidenceSource = Literal["test", "static_analysis", "human_review", "specification", "other"]
MistakeCode = Literal[
    "incorrect_diagnosis",
    "missed_issue",
    "wrong_location",
    "wrong_severity",
    "vague_or_inactionable",
    "unsafe_fix",
    "unsupported_reasoning",
    "incomplete_review",
    "other",
]


_VERDICT_CREDIT: dict[AssessmentVerdict, float] = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "incorrect": 0.0,
    "missed": 0.0,
}


class ReviewAssessmentUnit(BaseModel):
    """One independently verifiable part of an AI review."""

    unit_id: str = Field(min_length=1)
    criterion: ReviewCriterion
    verdict: AssessmentVerdict
    weight: int = Field(ge=1, le=3)
    ai_review_part: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    evidence_source: EvidenceSource
    mistake_code: MistakeCode | None = None

    @model_validator(mode="after")
    def validate_mistake_code(self) -> ReviewAssessmentUnit:
        """Require every deduction to identify the concrete reviewer mistake."""
        if self.verdict == "correct" and self.mistake_code is not None:
            raise ValueError("correct assessment units must not have a mistake_code")
        if self.verdict != "correct" and self.mistake_code is None:
            raise ValueError("non-correct assessment units require a mistake_code")
        return self

    @property
    def credit(self) -> float:
        """Return fixed credit so scoring cannot be adjusted after seeing results."""
        return _VERDICT_CREDIT[self.verdict]


class ReviewDeduction(BaseModel):
    """One transparent explanation for points lost from a perfect review."""

    unit_id: str
    criterion: ReviewCriterion
    mistake_code: MistakeCode
    points_lost: float = Field(gt=0, le=100)
    ai_review_part: str
    expected: str
    explanation: str
    evidence: list[str]
    evidence_source: EvidenceSource


class AIReviewerEvaluation(BaseModel):
    """A quality score where every lost point maps to an inspectable mistake."""

    result_schema_version: Literal["1.0"] = "1.0"
    metric_name: Literal["ai_review_quality_percentage"] = "ai_review_quality_percentage"
    review_id: str
    score_percentage: int = Field(ge=0, le=100)
    score_unrounded: float = Field(ge=0, le=100)
    total_units: int = Field(gt=0)
    correct_units: int = Field(ge=0)
    partially_correct_units: int = Field(ge=0)
    incorrect_units: int = Field(ge=0)
    missed_units: int = Field(ge=0)
    assessments: list[ReviewAssessmentUnit]
    deductions: list[ReviewDeduction]
    warnings: list[str] = Field(default_factory=list)


class AIReviewerSummary(BaseModel):
    """Aggregate quality metrics across independently evaluated reviews."""

    total_reviews: int
    mean_score: float | None = None
    perfect_review_rate: float | None = None
    total_assessment_units: int
    incorrect_unit_rate: float | None = None
    missed_issue_rate: float | None = None
    mistake_counts: dict[str, int]


def evaluate_ai_review(
    review_id: str,
    assessments: Sequence[ReviewAssessmentUnit],
) -> AIReviewerEvaluation:
    """Score an AI review and explain every deduction from 100 percent."""
    units = list(assessments)
    if not units:
        raise ValueError("at least one review assessment unit is required")
    unit_ids = [unit.unit_id for unit in units]
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("review assessment unit IDs must be unique")

    total_weight = sum(unit.weight for unit in units)
    earned_weight = sum(unit.weight * unit.credit for unit in units)
    score_unrounded = 100.0 * earned_weight / total_weight
    deductions = [
        ReviewDeduction(
            unit_id=unit.unit_id,
            criterion=unit.criterion,
            mistake_code=cast(MistakeCode, unit.mistake_code),
            points_lost=100.0 * unit.weight * (1.0 - unit.credit) / total_weight,
            ai_review_part=unit.ai_review_part,
            expected=unit.expected,
            explanation=unit.explanation,
            evidence=unit.evidence,
            evidence_source=unit.evidence_source,
        )
        for unit in units
        if unit.mistake_code is not None
    ]
    verdict_counts = Counter(unit.verdict for unit in units)
    return AIReviewerEvaluation(
        review_id=review_id,
        score_percentage=round(score_unrounded),
        score_unrounded=score_unrounded,
        total_units=len(units),
        correct_units=verdict_counts["correct"],
        partially_correct_units=verdict_counts["partially_correct"],
        incorrect_units=verdict_counts["incorrect"],
        missed_units=verdict_counts["missed"],
        assessments=units,
        deductions=deductions,
        warnings=[
            "This score is only as reliable as its test, static-analysis, specification, or human-review evidence.",
            "PR adoption is not used as proof that the AI review was correct or incorrect.",
        ],
    )


def summarize_ai_reviewer(evaluations: Sequence[AIReviewerEvaluation]) -> AIReviewerSummary:
    """Aggregate review-quality scores and recurring mistake categories."""
    rows = list(evaluations)
    assessment_units = [unit for row in rows for unit in row.assessments]
    mistake_counts = Counter(deduction.mistake_code for row in rows for deduction in row.deductions)
    total_units = len(assessment_units)
    incorrect_units = sum(unit.verdict == "incorrect" for unit in assessment_units)
    missed_units = sum(unit.verdict == "missed" for unit in assessment_units)
    return AIReviewerSummary(
        total_reviews=len(rows),
        mean_score=sum(row.score_unrounded for row in rows) / len(rows) if rows else None,
        perfect_review_rate=(sum(row.score_percentage == 100 for row in rows) / len(rows) if rows else None),
        total_assessment_units=total_units,
        incorrect_unit_rate=incorrect_units / total_units if total_units else None,
        missed_issue_rate=missed_units / total_units if total_units else None,
        mistake_counts={str(code): count for code, count in mistake_counts.items()},
    )

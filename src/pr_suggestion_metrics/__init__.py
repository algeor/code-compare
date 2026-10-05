"""Utilities for evaluating PR suggestion coverage metrics."""

from __future__ import annotations

from typing import Any


__all__ = [
    "AIReviewerEvaluation",
    "AIReviewerSummary",
    "ReviewAssessmentUnit",
    "ReviewDeduction",
    "evaluate_ai_review",
    "predict_coverage_from_diffs",
    "predict_coverage_percentages",
    "predict_coverage_with_uncertainty",
    "prepare_model_features",
    "analyze_change_coverage",
    "CoverageResult",
    "summarize_ai_reviewer",
]


def __getattr__(name: str) -> Any:
    """Load model inference helpers only when callers request them."""
    if name == "analyze_change_coverage":
        from pr_suggestion_metrics.diff_semantics import analyze_change_coverage

        return analyze_change_coverage
    if name == "CoverageResult":
        from pr_suggestion_metrics.model_inference import CoverageResult

        return CoverageResult
    if name in {
        "AIReviewerEvaluation",
        "AIReviewerSummary",
        "ReviewAssessmentUnit",
        "ReviewDeduction",
        "evaluate_ai_review",
        "summarize_ai_reviewer",
    }:
        from pr_suggestion_metrics import reviewer_evaluation

        return getattr(reviewer_evaluation, name)
    if name in __all__:
        from pr_suggestion_metrics import model_inference

        return getattr(model_inference, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

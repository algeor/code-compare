"""Utilities for evaluating PR suggestion coverage metrics."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_PUBLIC_EXPORTS = {
    "AIReviewerEvaluation": ("pr_suggestion_metrics.reviewer_evaluation", "AIReviewerEvaluation"),
    "AIReviewerSummary": ("pr_suggestion_metrics.reviewer_evaluation", "AIReviewerSummary"),
    "AnalysisResult": ("pr_suggestion_metrics.analysis_service", "AnalysisResult"),
    "AnalysisService": ("pr_suggestion_metrics.analysis_service", "AnalysisService"),
    "CoverageResult": ("pr_suggestion_metrics.model_inference", "CoverageResult"),
    "ReviewAssessmentUnit": ("pr_suggestion_metrics.reviewer_evaluation", "ReviewAssessmentUnit"),
    "ReviewDeduction": ("pr_suggestion_metrics.reviewer_evaluation", "ReviewDeduction"),
    "analyze_change_coverage": ("pr_suggestion_metrics.diff_semantics", "analyze_change_coverage"),
    "evaluate_ai_review": ("pr_suggestion_metrics.reviewer_evaluation", "evaluate_ai_review"),
    "predict_coverage_from_diffs": ("pr_suggestion_metrics.model_inference", "predict_coverage_from_diffs"),
    "predict_coverage_percentages": ("pr_suggestion_metrics.model_inference", "predict_coverage_percentages"),
    "predict_coverage_with_uncertainty": (
        "pr_suggestion_metrics.model_inference",
        "predict_coverage_with_uncertainty",
    ),
    "prepare_model_features": ("pr_suggestion_metrics.model_inference", "prepare_model_features"),
    "summarize_ai_reviewer": ("pr_suggestion_metrics.reviewer_evaluation", "summarize_ai_reviewer"),
}

__all__ = list(_PUBLIC_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load model inference helpers only when callers request them."""
    export = _PUBLIC_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = export
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

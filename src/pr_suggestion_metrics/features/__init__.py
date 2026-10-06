"""Supported deterministic feature extraction API."""

from pr_suggestion_metrics.features.core import (
    MetricResult,
    RawDiffAssessment,
    RawDiffAssessmentStatus,
    RawDiffSource,
    assess_raw_diff,
    metric_result_to_feature_row,
    raw_diff_support_issues,
    score_diff_pair,
)
from pr_suggestion_metrics.features.policy import CURRENT_NORMALIZATION_POLICY, NORMALIZATION_POLICY_VERSION

__all__ = [
    "MetricResult",
    "CURRENT_NORMALIZATION_POLICY",
    "NORMALIZATION_POLICY_VERSION",
    "RawDiffAssessment",
    "RawDiffAssessmentStatus",
    "RawDiffSource",
    "assess_raw_diff",
    "metric_result_to_feature_row",
    "raw_diff_support_issues",
    "score_diff_pair",
]

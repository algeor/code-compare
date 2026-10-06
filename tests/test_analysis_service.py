from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pr_suggestion_metrics.analysis_service import AnalysisService
from pr_suggestion_metrics.model_inference import CoverageResult, CoverageUncertainty
from pr_suggestion_metrics.diff_semantics import analyze_change_coverage


SUGGESTED_DIFF = "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n"
MERGED_DIFF = "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n"


def _coverage_result(*, status: str = "predicted") -> CoverageResult:
    return CoverageResult(
        status=status,
        model_name="extra_trees" if status == "predicted" else None,
        model_predicted_percentage=95 if status == "predicted" else None,
        model_raw_percentage=94.7 if status == "predicted" else None,
        heuristic_coverage_score=100,
        change_coverage_evidence=analyze_change_coverage(SUGGESTED_DIFF, MERGED_DIFF),
        uncertainty=CoverageUncertainty(status="unavailable", reason="test fixture"),
        input_hashes={"suggested_diff_sha256": "a", "merged_pr_diff_sha256": "b"},
        artifact_hashes={"model_sha256": "m", "schema_sha256": "s"} if status == "predicted" else {},
        warnings=["percentage warning"],
    )


def test_analysis_service_combines_percentage_evidence_and_explanation() -> None:
    with patch("pr_suggestion_metrics.analysis_service.predict_coverage_from_diffs", return_value=_coverage_result()):
        result = AnalysisService(model_dir=Path("model-dir")).analyze(
            suggested_diff=SUGGESTED_DIFF,
            merged_pr_diff=MERGED_DIFF,
            example_id="demo-1",
        )

    assert result.result_schema_version == "1.0"
    assert result.status == "predicted"
    assert result.percentage.model_predicted_percentage == 95
    assert result.explanation.status == "explained"
    assert result.explanation.landed_units == 1
    assert result.model_versions == {
        "percentage_model": "extra_trees",
        "explanation_model": "deterministic-template-explainer",
        "explanation_model_version": "1.0",
    }
    assert result.artifact_hashes == {"model_sha256": "m", "schema_sha256": "s"}
    assert "percentage warning" in result.warnings


def test_analysis_service_keeps_abstention_explicit() -> None:
    with patch(
        "pr_suggestion_metrics.analysis_service.predict_coverage_from_diffs",
        return_value=_coverage_result(status="abstained"),
    ):
        result = AnalysisService(model_dir=Path("model-dir")).analyze(
            suggested_diff=SUGGESTED_DIFF,
            merged_pr_diff=MERGED_DIFF,
        )

    assert result.status == "abstained"
    assert result.percentage.model_predicted_percentage is None
    assert result.model_versions["percentage_model"] == "abstained"
    assert result.explanation.status == "explained"

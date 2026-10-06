from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from pr_suggestion_metrics.diff_semantics import analyze_change_coverage
from pr_suggestion_metrics.model_inference import (
    CoverageResult,
    CoverageUncertainty,
    _percentage_prediction_frame,
    predict_coverage_from_diffs,
)


_SCHEMA = {
    "schema_version": "1.1",
    "normalization_policy_version": "1.0",
    "numeric_features": ["candidate_hunk_count"],
    "boolean_features": [],
    "categorical_features": [],
    "feature_columns": ["candidate_hunk_count"],
}


def test_prediction_frame_uses_shared_rounding_and_preserves_clipped_raw_values() -> None:
    model = Mock()
    model.predict.return_value = [-2.4, 101.2]
    rounded = np.array([7, 8])

    with (
        patch("pr_suggestion_metrics.model_inference.load_model_bundle", return_value=(model, _SCHEMA)),
        patch("pr_suggestion_metrics.model_inference.round_bounded_percentage", return_value=rounded) as round_shared,
    ):
        result = _percentage_prediction_frame(
            [{"candidate_hunk_count": 1}, {"candidate_hunk_count": 2}],
            model_dir=Path("unused"),
        )

    np.testing.assert_array_equal(result["model_raw_percentage"].to_numpy(), np.array([0.0, 100.0]))
    np.testing.assert_array_equal(result["model_predicted_percentage"].to_numpy(), rounded)
    np.testing.assert_array_equal(round_shared.call_args.args[0], np.array([-2.4, 101.2]))


def test_prediction_frame_rejects_non_vector_model_output() -> None:
    model = Mock()
    model.predict.return_value = [[42.0]]

    with patch("pr_suggestion_metrics.model_inference.load_model_bundle", return_value=(model, _SCHEMA)):
        with pytest.raises(ValueError, match="one-dimensional array"):
            _percentage_prediction_frame([{"candidate_hunk_count": 1}], model_dir=Path("unused"))


def test_prediction_frame_rejects_incompatible_normalization_policy() -> None:
    model = Mock()
    incompatible_schema = {**_SCHEMA, "normalization_policy_version": "0.9"}

    with patch(
        "pr_suggestion_metrics.model_inference.load_model_bundle",
        return_value=(model, incompatible_schema),
    ):
        with pytest.raises(ValueError, match="must match the runtime policy"):
            _percentage_prediction_frame([{"candidate_hunk_count": 1}], model_dir=Path("unused"))


@pytest.mark.parametrize("status", ["predicted", "abstained"])
def test_coverage_result_serializes_v1_1_evidence_for_every_status(status: str) -> None:
    diff = "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n"
    result = CoverageResult(
        status=status,
        model_predicted_percentage=100 if status == "predicted" else None,
        model_raw_percentage=100.0 if status == "predicted" else None,
        change_coverage_evidence=analyze_change_coverage(diff, diff),
        uncertainty=CoverageUncertainty(status="unavailable", reason="test fixture"),
        input_hashes={"suggested_diff_sha256": "a", "merged_pr_diff_sha256": "b"},
    )

    payload = result.model_dump()

    assert payload["result_schema_version"] == "1.1"
    assert payload["normalization_policy_version"] == "1.0"
    assert payload["status"] == status
    assert payload["change_coverage_evidence"]["evidence_schema_version"] == "1.1"
    assert payload["change_coverage_evidence"]["strict_same_file"]["coverage_percentage"] == 100
    assert payload["change_coverage_evidence"]["relaxed_cross_file"]["coverage_percentage"] == 0


@pytest.mark.parametrize(
    ("suggested_diff", "merged_pr_diff", "source", "diagnostic_code"),
    [
        (
            "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1,2 @@\n+value = 1\n",
            "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n",
            "suggested_diff",
            "incomplete_hunk",
        ),
        (
            "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n",
            "--- a/app.py\n+++ b/app.py\n@@ malformed\n+value = 1\n",
            "merged_pr_diff",
            "malformed_hunk_header",
        ),
        (
            "--- a/app.py\n+++ b/app.py\n",
            "--- a/app.py\n+++ b/app.py\n@@ -0,0 +1 @@\n+value = 1\n",
            "suggested_diff",
            "missing_hunk",
        ),
    ],
)
def test_invalid_raw_diff_abstains_before_model_loading(
    suggested_diff: str,
    merged_pr_diff: str,
    source: str,
    diagnostic_code: str,
) -> None:
    with patch("pr_suggestion_metrics.model_inference.load_model_bundle") as load_model:
        result = predict_coverage_from_diffs(
            suggested_diff,
            merged_pr_diff,
            model_dir=Path("/model/does/not/exist"),
        )

    assert result.status == "abstained"
    assert result.model_predicted_percentage is None
    assert result.suggested_diff_assessment is not None
    assert result.merged_pr_diff_assessment is not None
    assessment = getattr(result, f"{source}_assessment")
    assert assessment.status == "invalid"
    assert [diagnostic.code for diagnostic in assessment.diagnostics] == [diagnostic_code]
    assert any(diagnostic_code in reason for reason in result.applicability_reasons)
    load_model.assert_not_called()

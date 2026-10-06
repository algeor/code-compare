from dataclasses import dataclass

from pr_suggestion_metrics import evaluate_metrics
from pr_suggestion_metrics.features import (
    MetricResult,
    metric_result_to_feature_row,
    raw_diff_support_issues,
    score_diff_pair,
)
from pr_suggestion_metrics.features.core import _score_example
from pr_suggestion_metrics.features.structural import structural_node_types


SUGGESTED_DIFF = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1 @@
+value = 1
"""


def test_public_feature_api_and_evaluate_compatibility_aliases() -> None:
    result = score_diff_pair(SUGGESTED_DIFF, SUGGESTED_DIFF)

    assert isinstance(result, MetricResult)
    assert metric_result_to_feature_row(result)["predicted_percentage"] == 100
    assert raw_diff_support_issues(SUGGESTED_DIFF) == []
    assert evaluate_metrics.MetricResult is MetricResult
    assert evaluate_metrics.raw_diff_support_issues is raw_diff_support_issues
    assert evaluate_metrics.score_diff_pair is score_diff_pair
    assert evaluate_metrics.metric_result_to_feature_row is metric_result_to_feature_row
    assert evaluate_metrics._structural_node_types is structural_node_types


def test_scoring_uses_narrow_structural_input_contract() -> None:
    @dataclass(frozen=True)
    class InputPair:
        suggested_diff: str
        landed_diff: str
        file_overlap_ratio: float
        changed_line_overlap_ratio: float

    result = _score_example(
        InputPair(
            suggested_diff=SUGGESTED_DIFF,
            landed_diff=SUGGESTED_DIFF,
            file_overlap_ratio=1.0,
            changed_line_overlap_ratio=1.0,
        ),
        enable_gumtree=False,
    )

    assert result == score_diff_pair(SUGGESTED_DIFF, SUGGESTED_DIFF)


def test_structural_node_types_is_public() -> None:
    nodes, error, engine = structural_node_types("python", "value = 1\n")

    assert error == ""
    assert engine == "python_ast"
    assert "Assign" in nodes

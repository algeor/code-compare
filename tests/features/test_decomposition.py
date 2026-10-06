import ast
from pathlib import Path

from pr_suggestion_metrics import evaluate_metrics
from pr_suggestion_metrics.features import core, gumtree, lexical, matching, scoring
from pr_suggestion_metrics.features.contracts import CandidateHunk, MetricResult, ScoringExample, ScoringInput, TokenizedText


SUGGESTED_DIFF = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1,3 @@
+def calculate_total(items):
+    subtotal = sum(items)
+    return subtotal
"""

LANDED_DIFF = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1,4 @@
+def calculate_total(values):
+    subtotal = sum(values)
+    tax = subtotal * 0.2
+    return subtotal + tax
"""


def test_core_facade_preserves_contract_and_helper_identities() -> None:
    assert core.ScoringInput is ScoringInput
    assert core.ScoringExample is ScoringExample
    assert core.MetricResult is MetricResult
    assert core.TokenizedText is TokenizedText
    assert core.CandidateHunk is CandidateHunk
    assert core._tokenize_for_path is lexical._tokenize_for_path
    assert core._candidate_hunks_for_suggestion is matching._candidate_hunks_for_suggestion
    assert core._gumtree_features_by_file is gumtree._gumtree_features_by_file
    assert core._score_example is scoring._score_example


def test_shared_helpers_have_non_private_names_and_compatibility_aliases() -> None:
    aliases = {
        lexical._prepare_lines_by_file: lexical.prepare_lines_by_file,
        lexical._prepare_hunks_by_file: lexical.prepare_hunks_by_file,
        lexical._tokenize_for_path: lexical.tokenize_for_path,
        lexical._multiset_recall: lexical.multiset_recall,
        lexical._best_added_line_overlap: lexical.calculate_best_added_line_overlap,
        matching._added_lines_by_file_from_diff: matching.added_lines_by_file_from_diff,
        matching._added_hunks_by_file_from_diff: matching.added_hunks_by_file_from_diff,
        matching._best_hunk_scores: matching.calculate_best_hunk_scores,
        matching._best_structural_scores: matching.best_structural_scores,
        gumtree._gumtree_features_by_file: gumtree.gumtree_features_by_file,
        scoring._score_example: scoring.score_example,
    }

    assert all(private_helper is named_helper for private_helper, named_helper in aliases.items())


def test_responsibility_modules_do_not_import_private_feature_helpers() -> None:
    for module in (gumtree, lexical, matching, scoring):
        assert module.__file__ is not None
        module_path = Path(module.__file__)
        tree = ast.parse(module_path.read_text())
        feature_imports = (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("pr_suggestion_metrics.features.")
        )

        assert all(not imported.name.startswith("_") for node in feature_imports for imported in node.names)


def test_evaluate_metrics_resolves_decomposed_private_helpers() -> None:
    assert evaluate_metrics._tokenize_for_path is lexical._tokenize_for_path
    assert evaluate_metrics._candidate_hunks_for_suggestion is matching._candidate_hunks_for_suggestion
    assert evaluate_metrics._gumtree_features_by_file is gumtree._gumtree_features_by_file
    assert evaluate_metrics._score_example is scoring._score_example


def test_public_scoring_matches_assembly_for_representative_partial_result() -> None:
    public_result = core.score_diff_pair(SUGGESTED_DIFF, LANDED_DIFF)
    assembled_result = scoring._score_example(
        ScoringExample(
            suggested_diff=SUGGESTED_DIFF,
            landed_diff=LANDED_DIFF,
            file_overlap_ratio=1.0,
            changed_line_overlap_ratio=0.0,
        ),
        enable_gumtree=False,
    )

    assert public_result == assembled_result
    assert public_result.predicted_percentage == 82
    assert public_result.best_hunk_token_recall == 6 / 7
    assert public_result.best_hunk_candidate_type == "same_file"
    assert public_result.gumtree_error == "disabled"

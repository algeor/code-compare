from __future__ import annotations

import unittest

from pr_suggestion_metrics.diff_semantics import analyze_change_coverage, extract_change_units


class DiffSemanticsTest(unittest.TestCase):
    def test_replacement_counts_both_removed_and_added_units(self) -> None:
        suggestion = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-return old
+return new
"""

        evidence = analyze_change_coverage(suggestion, suggestion)

        self.assertEqual(evidence.coverage_percentage, 100)
        self.assertEqual(evidence.suggested_by_kind, {"deletion": 1, "addition": 1})
        self.assertEqual(evidence.matched_units, 2)

    def test_multi_file_multi_hunk_aggregates_every_unit(self) -> None:
        suggestion = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -0,0 +1 @@
+first()
@@ -3,0 +5 @@
+second()
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -0,0 +1 @@
+third()
"""
        landed = suggestion.replace("+second()\n", "+different()\n")

        evidence = analyze_change_coverage(suggestion, landed)

        self.assertEqual(evidence.total_suggested_units, 3)
        self.assertEqual(evidence.matched_units, 2)
        self.assertEqual(evidence.coverage_percentage, 67)
        self.assertEqual(evidence.unmatched_suggested_units[0].text, "second()")

    def test_cross_file_move_is_reported(self) -> None:
        suggestion = """diff --git a/old.py b/old.py
--- a/old.py
+++ b/old.py
@@ -0,0 +1 @@
+validate(value)
"""
        landed = """diff --git a/new.py b/new.py
--- a/new.py
+++ b/new.py
@@ -0,0 +1 @@
+validate(value)
"""

        evidence = analyze_change_coverage(suggestion, landed)

        self.assertEqual(evidence.strict_same_file.coverage_percentage, 0)
        self.assertEqual(evidence.strict_same_file.matched_units, 0)
        self.assertEqual(evidence.relaxed_cross_file.coverage_percentage, 100)
        self.assertEqual(evidence.relaxed_cross_file.matched_units, 1)
        self.assertEqual(evidence.coverage_percentage, 100)
        self.assertEqual(evidence.matched_units, 1)
        self.assertTrue(evidence.matches[0].moved_across_files)

    def test_duplicate_content_prioritizes_same_path_matches_globally(self) -> None:
        suggestion = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -0,0 +1 @@
+same()
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -0,0 +1 @@
+same()
"""
        landed = """diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -0,0 +1 @@
+same()
diff --git a/c.py b/c.py
--- a/c.py
+++ b/c.py
@@ -0,0 +1 @@
+same()
"""

        evidence = analyze_change_coverage(suggestion, landed)

        self.assertEqual(evidence.strict_same_file.coverage_percentage, 50)
        self.assertEqual(evidence.relaxed_cross_file.coverage_percentage, 50)
        self.assertEqual(evidence.matched_units, 2)
        self.assertEqual(sum(match.moved_across_files for match in evidence.matches), 1)
        self.assertEqual(evidence.strict_same_file.matches[0].suggested_path, "b.py")
        self.assertEqual(evidence.strict_same_file.matches[0].landed_path, "b.py")
        self.assertEqual(evidence.relaxed_cross_file.matches[0].suggested_path, "a.py")
        self.assertEqual(evidence.relaxed_cross_file.matches[0].landed_path, "c.py")
        self.assertEqual(
            {(match.suggested_path, match.landed_path) for match in evidence.matches},
            {("a.py", "c.py"), ("b.py", "b.py")},
        )

    def test_explicit_rename_is_a_change_unit(self) -> None:
        rename = """diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
"""

        units = extract_change_units(rename, prefix="suggested")
        evidence = analyze_change_coverage(rename, rename)

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].kind, "rename")
        self.assertEqual(evidence.coverage_percentage, 100)

    def test_parser_validity_is_additive_to_exact_matching_evidence(self) -> None:
        suggestion = """--- a/app.py
+++ b/app.py
@@
+value = 1
"""
        malformed_landed = """--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+value = 1
"""

        evidence = analyze_change_coverage(suggestion, malformed_landed)

        self.assertIsNone(evidence.coverage_percentage)
        self.assertIsNone(evidence.strict_same_file.coverage_percentage)
        self.assertEqual(evidence.matched_units, 0)
        self.assertEqual(evidence.unmatched_suggested_units[0].text, "value = 1")
        self.assertEqual(evidence.suggested_diff_assessment.status, "valid")
        self.assertEqual(evidence.suggested_diff_assessment.dialect, "suggestion_fragment")
        self.assertEqual(evidence.merged_pr_diff_assessment.status, "invalid")
        self.assertEqual(
            [diagnostic.code for diagnostic in evidence.merged_pr_diff_assessment.diagnostics],
            ["incomplete_hunk"],
        )
        self.assertTrue(any("[incomplete_hunk]" in warning for warning in evidence.warnings))
        self.assertIn(
            "Coverage is unavailable because at least one input diff is structurally invalid.",
            evidence.warnings,
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for the draft/final diff precision and recall metrics."""

from pr_suggestion_metrics.diff_precision_recall import changed_files, changed_lines, compare_diffs, word_tokens


def test_token_precision_and_recall_use_draft_and_final_denominators() -> None:
    result = compare_diffs("+alpha beta beta", "+alpha beta gamma gamma")

    assert result.token.matched_count == 2
    assert result.token.precision == 2 / 3
    assert result.token.recall == 2 / 4


def test_file_precision_and_recall_compare_changed_file_sets() -> None:
    draft = "--- a/app.py\n+++ b/app.py\n@@\n+fix\n"
    final = draft + "--- a/test.py\n+++ b/test.py\n@@\n+test\n"

    result = compare_diffs(draft, final)

    assert result.file.precision == 1.0
    assert result.file.recall == 0.5


def test_line_overlap_strips_whitespace_and_preserves_operation() -> None:
    draft = "--- a/app.py\n+++ b/app.py\n@@\n+  fix()  \n-old()\n"
    final = "--- a/app.py\n+++ b/app.py\n@@\n+fix()\n+old()\n"

    result = compare_diffs(draft, final)

    assert result.line.precision == 0.5
    assert result.line.recall == 0.5


def test_line_overlap_preserves_duplicate_occurrences() -> None:
    draft = "--- a/app.py\n+++ b/app.py\n@@\n+same\n+same\n"
    final = "--- a/app.py\n+++ b/app.py\n@@\n+same\n"

    result = compare_diffs(draft, final)

    assert result.line.matched_count == 1
    assert result.line.precision == 0.5
    assert result.line.recall == 1.0


def test_line_overlap_counts_changed_blank_lines_after_stripping() -> None:
    draft = "--- a/app.py\n+++ b/app.py\n@@\n+   \n"
    final = "--- a/app.py\n+++ b/app.py\n@@\n+\n"

    result = compare_diffs(draft, final)

    assert result.line.precision == 1.0
    assert result.line.recall == 1.0


def test_line_parser_ignores_changes_outside_hunks() -> None:
    diff = "not a unified diff\n+not counted outside hunk\n"

    assert not changed_lines(diff)


def test_line_parser_preserves_header_like_content_inside_hunk() -> None:
    diff = "--- a/notes.txt\n+++ b/notes.txt\n@@ -1 +1 @@\n--- removed heading\n+++ added heading\n"

    assert changed_lines(diff) == {
        ("removed", "-- removed heading"): 1,
        ("added", "++ added heading"): 1,
    }


def test_file_parser_uses_new_path_for_rename_and_old_path_for_delete() -> None:
    diff = """diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
diff --git a/deleted.py b/deleted.py
--- a/deleted.py
+++ /dev/null
"""

    assert changed_files(diff) == {"new.py", "deleted.py"}


def test_empty_draft_and_final_return_zero_ratios() -> None:
    result = compare_diffs("", "")

    assert result.token.precision == 0.0
    assert result.token.recall == 0.0
    assert result.file.precision == 0.0
    assert result.line.recall == 0.0


def test_extractors_ignore_headers_and_normalize_paths() -> None:
    diff = "--- a/app.py\n+++ b/app.py\n@@\n+value = 1\n"

    assert changed_files(diff) == {"app.py"}
    assert changed_lines(diff) == {("added", "value = 1"): 1}
    assert word_tokens(diff)["app"] == 2


def test_aggregate_f1_weights_token_file_and_line_levels_equally() -> None:
    draft = "--- a/app.py\n+++ b/app.py\n@@\n+fix\n"
    final = draft + "--- a/test.py\n+++ b/test.py\n@@\n+test\n"

    result = compare_diffs(draft, final)

    expected = (result.token.f1 + result.file.f1 + result.line.f1) / 3
    assert result.aggregate_f1 == expected

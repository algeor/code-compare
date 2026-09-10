"""Parity tests for the PIPELINE3-1376 production coverage baseline."""

from pr_suggestion_metrics.pipeline1376_coverage import (
    DiffChangeUnit,
    build_suggested_change_unit_union,
    parse_diff_change_units,
    score_diff_pair,
)


def _diff(path: str, *changed_lines: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n" + "\n".join(changed_lines) + "\n"


def test_score_is_one_when_merged_diff_contains_suggestion_and_unrelated_changes() -> None:
    suggested = _diff("app.py", "+fix()")
    merged = _diff("app.py", "+fix()") + _diff("README.md", "+unrelated docs")

    assert score_diff_pair(suggested, merged) == 1.0


def test_score_preserves_duplicate_cardinality() -> None:
    suggested = _diff("app.py", "+same", "+same")
    merged = _diff("app.py", "+same")

    assert score_diff_pair(suggested, merged) == 0.5


def test_union_uses_maximum_duplicate_count_across_handlers() -> None:
    first_handler = _diff("app.py", "+same", "+same")
    second_handler = _diff("app.py", "+same")

    assert build_suggested_change_unit_union([first_handler, second_handler]) == [
        DiffChangeUnit(file_path="app.py", operation="added", content="same"),
        DiffChangeUnit(file_path="app.py", operation="added", content="same"),
    ]


def test_score_distinguishes_additions_from_removals() -> None:
    suggested = _diff("app.py", "-obsolete()")
    merged = _diff("app.py", "+obsolete()")

    assert score_diff_pair(suggested, merged) == 0.0


def test_parser_preserves_leading_and_strips_trailing_whitespace() -> None:
    parsed = parse_diff_change_units(_diff("app.py", "+  value = 1   "))

    assert parsed == [DiffChangeUnit(file_path="app.py", operation="added", content="  value = 1")]


def test_empty_suggestion_scores_zero() -> None:
    assert score_diff_pair("", _diff("app.py", "+fix()")) == 0.0

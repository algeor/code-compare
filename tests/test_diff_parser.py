import pytest

from pr_suggestion_metrics.diff import DiffAssessment, assess_unified_diff, parse_unified_diff


def test_parser_tracks_paths_hunks_and_line_numbers() -> None:
    diff = """diff --git a/old.py b/new.py
similarity index 90%
rename from old.py
rename to new.py
--- a/old.py
+++ b/new.py
@@ -4,2 +7,3 @@
 keep
-old
+new
+extra
"""

    parsed = parse_unified_diff(diff)

    assert len(parsed.files) == 1
    assert parsed.hunk_count == 1
    assert parsed.files[0].rename_from == "old.py"
    assert parsed.files[0].rename_to == "new.py"
    assert [(line.operation, line.old_line_number, line.new_line_number) for line in parsed.lines] == [
        ("context", 4, 7),
        ("deletion", 5, None),
        ("addition", None, 8),
        ("addition", None, 9),
    ]


def test_parser_keeps_header_like_hunk_content() -> None:
    diff = "--- a/notes.txt\n+++ b/notes.txt\n@@ -1 +1 @@\n--- old\n+++ new\n"

    parsed = parse_unified_diff(diff)

    assert [(line.operation, line.text) for line in parsed.changed_lines] == [
        ("deletion", "-- old"),
        ("addition", "++ new"),
    ]


def test_parser_keeps_prefixed_file_markers_as_content_inside_counted_hunk() -> None:
    diff = "--- a/notes.txt\n+++ b/notes.txt\n@@ -1 +1 @@\n--- a/literal\n+++ b/literal\n"

    parsed = parse_unified_diff(diff)

    assert len(parsed.files) == 1
    assert [(line.operation, line.text) for line in parsed.changed_lines] == [
        ("deletion", "-- a/literal"),
        ("addition", "++ b/literal"),
    ]


def test_parser_starts_next_header_only_file_after_counted_hunk() -> None:
    diff = "--- a/one.py\n+++ b/one.py\n@@ -0,0 +1 @@\n+one\n--- a/two.py\n+++ b/two.py\n@@ -0,0 +1 @@\n+two\n"

    parsed = parse_unified_diff(diff)

    assert [file_diff.canonical_path for file_diff in parsed.files] == ["one.py", "two.py"]
    assert [line.text for line in parsed.changed_lines] == ["one", "two"]


def test_git_unified_assessment_accepts_standard_no_newline_marker() -> None:
    diff = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py
@@ -1 +1 @@ function
-old
+new
\\ No newline at end of file
"""

    assessment = assess_unified_diff(diff)

    assert assessment == DiffAssessment(
        dialect="git_unified",
        status="valid",
        parsed_diff=parse_unified_diff(diff),
        diagnostics=(),
    )
    assert assessment.is_valid


def test_git_unified_assessment_accepts_unquoted_paths_with_spaces() -> None:
    diff = """diff --git a/path with spaces.py b/path with spaces.py
--- a/path with spaces.py
+++ b/path with spaces.py
@@ -1 +1 @@
-old
+new
"""

    assessment = assess_unified_diff(diff)

    assert assessment.status == "valid"
    assert assessment.diagnostics == ()
    assert assessment.parsed_diff.files[0].canonical_path == "path with spaces.py"


def test_git_unified_assessment_defers_ambiguous_space_paths_to_markers() -> None:
    diff = """diff --git a/dir b/file.py b/dir b/file.py
--- a/dir b/file.py
+++ b/dir b/file.py
@@ -1 +1 @@
-old
+new
"""

    assessment = assess_unified_diff(diff)

    assert assessment.status == "valid"
    assert assessment.diagnostics == ()
    assert assessment.parsed_diff.files[0].canonical_path == "dir b/file.py"


def test_git_unified_assessment_accepts_c_quoted_paths() -> None:
    diff = '''diff --git "a/file\\tname.py" "b/file\\tname.py"
--- "a/file\\tname.py"
+++ "b/file\\tname.py"
@@ -1 +1 @@
-old
+new
'''

    assessment = assess_unified_diff(diff)

    assert assessment.status == "valid"
    assert assessment.diagnostics == ()
    assert assessment.parsed_diff.files[0].canonical_path == "file\tname.py"


def test_git_unified_assessment_decodes_c_quoted_utf8_octal_paths() -> None:
    diff = r'''diff --git "a/caf\303\251.py" "b/caf\303\251.py"
--- "a/caf\303\251.py"
+++ "b/caf\303\251.py"
@@ -1 +1 @@
-old
+new
'''

    assessment = assess_unified_diff(diff)

    assert assessment.status == "valid"
    assert assessment.parsed_diff.files[0].canonical_path == "café.py"


def test_suggestion_fragment_accepts_bare_hunk_header() -> None:
    diff = """--- a/file.py
+++ b/file.py
@@
+replacement
"""

    assessment = assess_unified_diff(diff, dialect="suggestion_fragment")

    assert assessment.status == "valid"
    assert assessment.diagnostics == ()
    assert [line.text for line in assessment.parsed_diff.changed_lines] == ["replacement"]


def test_git_unified_rejects_bare_fragment_hunk_header() -> None:
    diff = """--- a/file.py
+++ b/file.py
@@
+replacement
"""

    assessment = assess_unified_diff(diff, dialect="git_unified")

    assert [diagnostic.code for diagnostic in assessment.diagnostics] == ["malformed_hunk_header"]
    assert assessment.status == "invalid"
    assert not assessment.is_valid


@pytest.mark.parametrize(
    ("diff", "code", "message", "line_number", "file_path", "hunk_index"),
    [
        ("", "empty_input", "Diff input is empty.", None, None, None),
        (
            "ordinary source text\n",
            "non_diff_input",
            "Input does not contain unified-diff structure.",
            1,
            None,
            None,
        ),
        (
            "diff --git a/file.py\n",
            "malformed_git_header",
            "Git header must contain exactly one valid a/ path and one valid b/ path.",
            1,
            None,
            None,
        ),
        (
            "--- file.py\n",
            "invalid_file_marker",
            "File marker must contain the expected Git-prefixed path or /dev/null.",
            1,
            None,
            None,
        ),
        (
            "--- a/file.py\n+++ b/file.py\n",
            "missing_hunk",
            "A file section with --- and +++ markers must contain at least one hunk.",
            2,
            "file.py",
            None,
        ),
        (
            "diff --git a/file.py b/file.py\n--- a/other.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
            "conflicting_file_path",
            "File marker path conflicts with the corresponding Git header path.",
            2,
            "other.py",
            None,
        ),
        (
            "--- a/file.py\n@@ -1 +1 @@\n-old\n+new\n",
            "missing_file_marker_pair",
            "File section must contain paired --- and +++ markers before a hunk.",
            2,
            "file.py",
            1,
        ),
        (
            "+++ b/file.py\n--- a/file.py\n@@ -1 +1 @@\n-old\n+new\n",
            "reordered_file_markers",
            "The --- file marker must precede the +++ file marker.",
            1,
            "file.py",
            None,
        ),
        (
            "diff --git a/old.py b/new.py\nrename from old.py\n",
            "partial_rename_metadata",
            "Rename metadata must contain both rename from and rename to lines.",
            2,
            "new.py",
            None,
        ),
        (
            "--- a/file.py\n+++ b/file.py\n@@ malformed\n+new\n",
            "malformed_hunk_header",
            "Hunk header is malformed for the selected diff dialect.",
            3,
            "file.py",
            1,
        ),
        (
            "--- a/file.py\n+++ b/file.py\n@@ -1,2 +1,2 @@\n same\n",
            "incomplete_hunk",
            "Hunk body ended before its declared line counts were satisfied.",
            3,
            "file.py",
            1,
        ),
        (
            "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n+extra\n",
            "overflowing_hunk",
            "Hunk body exceeds its declared line counts.",
            6,
            "file.py",
            1,
        ),
        (
            "--- a/file.py\n+++ b/file.py\n@@ -0,0 +0,0 @@\ninvalid\n",
            "invalid_hunk_body_line",
            "Hunk body line must start with a space, +, or -.",
            4,
            "file.py",
            1,
        ),
    ],
)
def test_assessment_reports_stable_typed_diagnostics(
    diff: str,
    code: str,
    message: str,
    line_number: int | None,
    file_path: str | None,
    hunk_index: int | None,
) -> None:
    assessment = assess_unified_diff(diff)

    assert len(assessment.diagnostics) == 1
    diagnostic = assessment.diagnostics[0]
    assert diagnostic.code == code
    assert diagnostic.severity == "error"
    assert diagnostic.message == message
    assert diagnostic.line_number == line_number
    assert diagnostic.file_path == file_path
    assert diagnostic.hunk_index == hunk_index
    assert assessment.status == "invalid"


def test_suggestion_fragment_still_diagnoses_invalid_body_lines() -> None:
    diff = """--- a/file.py
+++ b/file.py
@@
not-prefixed
"""

    assessment = assess_unified_diff(diff, dialect="suggestion_fragment")

    assert [diagnostic.code for diagnostic in assessment.diagnostics] == ["invalid_hunk_body_line"]


@pytest.mark.parametrize(
    "diff",
    [
        "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
        "--- a/file.py\n+++ b/file.py\n@@\n+new\n",
        "--- a/file.py\n+++ b/file.py\n@@ malformed\n+new\n",
        "ordinary source text\n",
    ],
)
def test_assessment_preserves_compatibility_parser_output(diff: str) -> None:
    assert assess_unified_diff(diff).parsed_diff == parse_unified_diff(diff)


def test_assessment_rejects_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="unsupported diff dialect"):
        assess_unified_diff("", dialect="unknown")  # type: ignore[arg-type]

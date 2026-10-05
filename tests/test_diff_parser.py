from pr_suggestion_metrics.diff.parser import parse_unified_diff


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

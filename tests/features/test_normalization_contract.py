from __future__ import annotations

import pytest

from pr_suggestion_metrics.diff_semantics import analyze_change_coverage, extract_change_units
from pr_suggestion_metrics.features import raw_diff_support_issues
from pr_suggestion_metrics.features.policy import CURRENT_NORMALIZATION_POLICY, NORMALIZATION_POLICY_VERSION
from pr_suggestion_metrics.features.lexical import (
    prepare_hunks_by_file,
    prepare_lines_by_file,
    tokenize_for_path,
)
from pr_suggestion_metrics.features.matching import (
    added_hunks_by_file_from_diff,
    added_lines_by_file_from_diff,
    calculate_best_hunk_scores,
)


NORMALIZATION_CASES = [
    pytest.param(
        "src/example.py",
        ["def outer(value):", "\tif ready:", "\t\treturn value", "    ", "\treturn None"],
        ["def outer(value):", "if ready:", "return value", "return None"],
        "python",
        {"python"},
        ["def", "outer", "(", "value", ")", ":", "if", "ready", ":", "return", "value", "return", "None"],
        id="python-indentation",
    ),
    pytest.param(
        "config/app.yaml",
        ["services:", "  api:", "    image: example/app:1.2", "    enabled: true", "  # comment", ""],
        ["services:", "api:", "image: example/app:1.2", "enabled: true", "# comment"],
        "yaml",
        {"yaml_like"},
        [
            "services",
            "services",
            ":",
            "api",
            "api",
            ":",
            "image",
            "image",
            ":",
            "example",
            "/",
            "app",
            ":",
            "1.2",
            "enabled",
            "enabled",
            ":",
            "true",
        ],
        id="yaml-indentation",
    ),
    pytest.param(
        "scripts/deploy.sh",
        ['if [ "$READY" = "true" ]; then', '  echo "deploy now"', "fi", "   "],
        ['if [ "$READY" = "true" ]; then', 'echo "deploy now"', "fi"],
        "shell",
        {"pygments", "regex"},
        ["if", "[", '"', "$", "READY", '"', "=", '"', "true", '"', "]", ";", "then", "echo", '"', "deploy", "now", '"', "fi"],
        id="shell-whitespace",
    ),
    pytest.param(
        "config/app.json",
        ["{", '  "enabled": true,', '  "ports": [8080, 9090],', '  "value": null', "}"],
        ["{", '"enabled": true,', '"ports": [8080, 9090],', '"value": null', "}"],
        "json",
        {"json"},
        ["enabled", "true", "ports", "8080", "9090", "value", "null"],
        id="json-config",
    ),
    pytest.param(
        "config/server.conf",
        ["server   {", "    listen    8080;", "    enabled = true", "}"],
        ["server {", "listen 8080;", "enabled = true", "}"],
        "text",
        {"regex"},
        ["server", "{", "listen", "8080", ";", "enabled", "=", "true", "}"],
        id="generic-config",
    ),
    pytest.param(
        "docs/guide.md",
        [
            "# Deploy Guide",
            "",
            "- Run `deploy.sh`",
            "  - Check status",
            "",
            "```python",
            "if ready:",
            "    deploy()",
            "```",
        ],
        ["# Deploy Guide", "- Run `deploy.sh`", "- Check status", "```python", "if ready:", "deploy()", "```"],
        "markdown",
        {"markdown"},
        ["Deploy", "Guide", "Run", "`", "deploy", ".", "sh", "`", "Check", "status", "if", "ready", ":", "deploy", "(", ")"],
        id="markdown-list-and-fence-indentation",
    ),
]


def test_normalization_policy_is_explicit_and_versioned() -> None:
    assert NORMALIZATION_POLICY_VERSION == "1.0"
    assert CURRENT_NORMALIZATION_POLICY.version == NORMALIZATION_POLICY_VERSION
    assert CURRENT_NORMALIZATION_POLICY.line_whitespace == "strip_and_collapse"
    assert CURRENT_NORMALIZATION_POLICY.blank_lines == "drop"
    assert CURRENT_NORMALIZATION_POLICY.python_indentation_tokens == "omit"
    assert CURRENT_NORMALIZATION_POLICY.identifier_normalization == "replace_with_IDENT"
    assert CURRENT_NORMALIZATION_POLICY.literal_normalization == "replace_with_LITERAL"


@pytest.mark.parametrize(
    ("path", "raw_lines", "normalized_lines", "language", "tokenizers", "tokens"),
    NORMALIZATION_CASES,
)
def test_current_line_normalization_and_tokenization_contract(
    path: str,
    raw_lines: list[str],
    normalized_lines: list[str],
    language: str,
    tokenizers: set[str],
    tokens: list[str],
) -> None:
    prepared = prepare_lines_by_file({path: raw_lines})[path]
    raw_tokenization = tokenize_for_path(path, "\n".join(raw_lines))
    normalized_tokenization = tokenize_for_path(path, "\n".join(prepared))

    assert prepared == normalized_lines
    assert raw_tokenization == normalized_tokenization
    assert raw_tokenization.language == language
    assert raw_tokenization.tokenizer in tokenizers
    assert raw_tokenization.tokens == tokens


def test_python_tokenization_omits_whitespace_indent_and_dedent_tokens() -> None:
    raw_lines = ["def outer():", "    if ready:", "        return value", "    return None"]

    tokenized = tokenize_for_path("src/example.py", "\n".join(raw_lines))

    assert tokenized.tokens == [
        "def",
        "outer",
        "(",
        ")",
        ":",
        "if",
        "ready",
        ":",
        "return",
        "value",
        "return",
        "None",
    ]
    assert not {"INDENT", "DEDENT", "    ", "        "} & set(tokenized.tokens)


def test_rename_only_diff_has_no_normalized_added_lines_and_is_unsupported() -> None:
    rename_diff = """diff --git a/src/old.py b/src/new.py
similarity index 100%
rename from src/old.py
rename to src/new.py
"""

    assert added_lines_by_file_from_diff(rename_diff) == {}
    assert raw_diff_support_issues(rename_diff) == [
        "suggestion diff contains no supported added code lines",
        "renamed suggestion files are not yet supported",
    ]

    rename_units = extract_change_units(rename_diff, prefix="suggested")

    assert len(rename_units) == 1
    assert rename_units[0].kind == "rename"
    assert rename_units[0].path == "src/new.py"
    assert rename_units[0].text == "src/old.py -> src/new.py"
    assert rename_units[0].old_path == "src/old.py"
    assert rename_units[0].new_path == "src/new.py"


def test_cross_file_move_matches_after_python_indentation_is_erased() -> None:
    suggestion_diff = """diff --git a/src/old.py b/src/old.py
--- a/src/old.py
+++ b/src/old.py
@@ -0,0 +1,3 @@
+def deploy():
+    if ready:
+        run()
"""
    landed_diff = """diff --git a/src/new.py b/src/new.py
--- a/src/new.py
+++ b/src/new.py
@@ -0,0 +1,3 @@
+def deploy():
+  if ready:
+    run()
"""

    suggested_lines = prepare_lines_by_file(added_lines_by_file_from_diff(suggestion_diff))
    landed_hunks = prepare_hunks_by_file(added_hunks_by_file_from_diff(landed_diff))

    assert suggested_lines == {"src/old.py": ["def deploy():", "if ready:", "run()"]}
    assert landed_hunks == {"src/new.py": [["def deploy():", "if ready:", "run()"]]}

    scores = calculate_best_hunk_scores(suggested_lines, landed_hunks)

    assert scores["best_hunk_token_recall"] == 1.0
    assert scores["best_hunk_contiguous_line_ratio"] == 1.0
    assert scores["best_hunk_file"] == "src/new.py"
    assert scores["best_hunk_candidate_type"] == "same_extension"

    evidence = analyze_change_coverage(suggestion_diff, landed_diff)

    assert evidence.coverage_percentage == 100
    assert evidence.matched_units == 3
    assert all(match.moved_across_files for match in evidence.matches)

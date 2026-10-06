from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from pr_suggestion_metrics.collect_pr_code_changes import (
    PairedExample,
    _candidate_from_github_pr_url,
    _extract_comment_diff_suggestions,
    _write_pairs_jsonl,
)


class GitHubPrCandidateTest(unittest.TestCase):
    def test_candidate_is_built_from_github_pr_url(self) -> None:
        candidate = _candidate_from_github_pr_url("https://github.example/owner/repo/pull/123")

        self.assertEqual(candidate.inspection_id, "github-pr-github.example-owner-repo-123")
        self.assertEqual(candidate.github_repo_url, "https://github.example/owner/repo")
        self.assertEqual(candidate.repo_name, "owner/repo")
        self.assertEqual(candidate.pipeline_url, "https://github.example/owner/repo/pull/123")
        self.assertEqual(candidate.pr_number, "123")

    def test_candidate_rejects_non_pr_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "must look like /owner/repo/pull/number"):
            _candidate_from_github_pr_url("https://github.example/owner/repo/issues/123")


class GitHubCommentSuggestionTest(unittest.TestCase):
    def test_review_suggestion_is_normalized_to_diff_like_text(self) -> None:
        candidate = _candidate_from_github_pr_url("https://github.example/owner/repo/pull/123")
        comment = {
            "id": 456,
            "body": "```suggestion\nreturn value\n```",
            "html_url": "https://github.example/owner/repo/pull/123#discussion_r456",
            "path": "src/example.py",
            "user": {"login": "reviewer"},
        }

        suggestions = _extract_comment_diff_suggestions(
            candidate,
            comment,
            source="all",
            author_filters=[],
            kind="review",
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].diff_text, "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return value")
        self.assertEqual(suggestions[0].candidate.fault_id, "github-review-comment-456-1")
        provenance = suggestions[0].provenance
        self.assertIsNotNone(provenance)
        assert provenance is not None
        self.assertEqual(provenance.comment_url, comment["html_url"])


class PairJsonlWriterTest(unittest.TestCase):
    def pair(self) -> PairedExample:
        return PairedExample(
            inspection_id="inspection",
            fault_id="fault",
            handler_code_changes_diff="+café",
            merged_pr_diff="+café",
            repo_host="github.example",
            repo_owner="owner",
            repo_name="repo",
            pr_number=123,
            pr_url="https://github.example/owner/repo/pull/123",
            handler_diff_path="handler_results/fault/code_changes.diff",
            merged_pr_diff_source="test",
        )

    def test_file_output_preserves_pydantic_json_and_creates_parent(self) -> None:
        pair = self.pair()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "pairs.jsonl"

            _write_pairs_jsonl([pair], path)

            expected = (pair.model_dump_json(exclude_none=False) + "\n").encode("utf-8")
            self.assertEqual(path.read_bytes(), expected)
            self.assertIn(b'"source_branch":null', expected)

    def test_stdout_output_remains_direct(self) -> None:
        pair = self.pair()
        stdout = StringIO()

        with redirect_stdout(stdout):
            _write_pairs_jsonl([pair], None)

        self.assertEqual(stdout.getvalue(), pair.model_dump_json(exclude_none=False) + "\n")


if __name__ == "__main__":
    unittest.main()

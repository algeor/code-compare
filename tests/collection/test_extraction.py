from __future__ import annotations

import unittest

from pr_suggestion_metrics.collection.extraction import (
    candidate_from_github_pr_url,
    extract_comment_diff_suggestions,
    matches_comment_source,
)


class CommentExtractionTest(unittest.TestCase):
    def test_fault_handler_id_and_temporal_provenance_are_preserved(self) -> None:
        candidate = candidate_from_github_pr_url("https://github.example/owner/repo/pull/17")
        comment = {
            "id": 91,
            "body": "# Fault Localization\n```suggestion\nreturn café\n```\n<!--fault_handler_ids_fault-7, fault-8-->",
            "html_url": "https://github.example/owner/repo/pull/17#discussion_r91",
            "created_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-01-01T10:05:00Z",
            "commit_id": "a" * 40,
            "original_commit_id": "b" * 40,
            "path": "src/example.py",
            "line": 12,
            "side": "RIGHT",
            "user": {"login": "fault-analyzer"},
        }

        suggestions = extract_comment_diff_suggestions(
            candidate,
            comment,
            source="fl",
            author_filters=["analyzer"],
            kind="review",
        )

        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(suggestion.candidate.fault_id, "fault-7")
        self.assertEqual(suggestion.diff_bytes, len(suggestion.diff_text.encode("utf-8")))
        self.assertEqual(
            suggestion.diff_text,
            "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return café",
        )
        assert suggestion.provenance is not None
        self.assertEqual(suggestion.provenance.original_commit_sha, "b" * 40)
        self.assertEqual(suggestion.provenance.author_login, "fault-analyzer")

    def test_source_and_author_filters_are_pure_predicates(self) -> None:
        comment = {"body": "Hyperspace suggested a change", "user": {"login": "review-bot"}}

        self.assertTrue(matches_comment_source(comment, source="hyperspace", author_filters=[]))
        self.assertTrue(matches_comment_source(comment, source="all", author_filters=["REVIEW"]))
        self.assertFalse(matches_comment_source(comment, source="fl", author_filters=[]))
        self.assertFalse(matches_comment_source(comment, source="all", author_filters=["human"]))


if __name__ == "__main__":
    unittest.main()

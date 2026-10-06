from __future__ import annotations

import hashlib
import unittest

from pr_suggestion_metrics.collection.contracts import RepoRef
from pr_suggestion_metrics.collection.extraction import candidate_from_github_pr_url
from pr_suggestion_metrics.collection.service import collect_pairs, load_suggestion_diffs_from_pr_comments
from pr_suggestion_metrics.scientific_contracts import FileSnapshot


class FakeGateway:
    def __init__(self) -> None:
        self.issue_comment_calls = 0
        self.review_comment_calls = 0
        self.pr_json_calls = 0
        self.pr_diff_calls = 0

    async def fetch_pr_json(self, repo: RepoRef) -> dict[str, object]:
        self.pr_json_calls += 1
        return {
            "merged": True,
            "merged_at": "2026-01-02T00:00:00Z",
            "merge_commit_sha": "c" * 40,
            "base": {"ref": "main", "sha": "d" * 40},
            "head": {"ref": "feature", "sha": "e" * 40},
        }

    async def fetch_pr_diff(self, repo: RepoRef) -> str:
        self.pr_diff_calls += 1
        return "diff --git a/src/example.py b/src/example.py\n--- a/src/example.py\n+++ b/src/example.py\n"

    async def fetch_pr_comments(self, repo: RepoRef) -> list[dict[str, object]]:
        self.issue_comment_calls += 1
        return []

    async def fetch_pr_review_comments(self, repo: RepoRef) -> list[dict[str, object]]:
        self.review_comment_calls += 1
        return [
            {
                "id": 42,
                "body": "```suggestion\nreturn value\n```",
                "path": "src/example.py",
                "original_commit_id": "b" * 40,
                "user": {"login": "reviewer"},
            }
        ]

    async def fetch_file_snapshot(self, repo: RepoRef, *, path: str, revision_sha: str) -> FileSnapshot:
        content = f"{path}@{revision_sha}"
        return FileSnapshot(
            revision_sha=revision_sha,
            path=path,
            content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            source="fake",
        )


class CollectionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_fake_gateway_drives_comment_collection_and_pairing(self) -> None:
        candidate = candidate_from_github_pr_url("https://github.example/owner/repo/pull/7")
        gateway = FakeGateway()

        suggestions, suggestion_misses = await load_suggestion_diffs_from_pr_comments(
            [candidate],
            github_token=None,
            source="all",
            author_filters=[],
            review_comments_only=True,
            github_concurrency=4,
            gateway=gateway,
            progress=lambda _message: None,
        )
        pairs, pair_misses = await collect_pairs(
            suggestions,
            github_token=None,
            include_unmerged_prs=False,
            gateway=gateway,
            progress=lambda _message: None,
        )

        self.assertEqual(suggestion_misses, [])
        self.assertEqual(pair_misses, [])
        self.assertEqual(gateway.issue_comment_calls, 0)
        self.assertEqual(gateway.review_comment_calls, 1)
        self.assertEqual(gateway.pr_json_calls, 1)
        self.assertEqual(gateway.pr_diff_calls, 1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].source_branch, "feature")
        assert pairs[0].suggestion_provenance is not None
        self.assertEqual(pairs[0].suggestion_provenance.files[0].suggestion_base_snapshot.source, "fake")


if __name__ == "__main__":
    unittest.main()

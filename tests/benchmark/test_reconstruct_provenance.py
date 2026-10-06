from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.benchmark.reconstruct_provenance import reconstruct_inventory_provenance
from pr_suggestion_metrics.collection.contracts import RepoRef
from pr_suggestion_metrics.scientific_contracts import FileSnapshot


def _snapshot(path: str, revision: str) -> FileSnapshot:
    content = f"{path}@{revision}\n"
    return FileSnapshot(
        revision_sha=revision,
        path=path,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        source="fake_gateway",
    )


def _inventory_row(*, suggested_diff: str, suggestion_anchor: str = "github_review_comment:42#suggestion:1") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "example_id": "example-1",
        "chosen_source": "internal_processed_dataset",
        "source_datasets": ["internal_processed_dataset"],
        "source_row_keys": ["example-1"],
        "repo": "github.example/owner/repo",
        "pr_url": "https://github.example/owner/repo/pull/7",
        "pr_number": 7,
        "suggestion_anchor": suggestion_anchor,
        "suggested_diff": suggested_diff,
        "landed_diff": (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1 +1,2 @@\n"
            " old\n"
            "+return value\n"
        ),
        "original_file_path": "src/example.py",
        "merge_commit_sha": "c" * 40,
        "weak_label_percentage": 100,
        "status": "needs_reconstruction",
        "evidence": {
            "repository_identity": True,
            "pr_identity": True,
            "suggestion_anchor": True,
            "suggested_diff": True,
            "original_file_path": True,
            "original_snapshot_or_context": False,
            "merged_pr_diff": True,
            "final_snapshot_or_context": False,
            "merge_revision": True,
            "final_path_mapping": True,
            "suggestion_provenance": False,
        },
        "missing_requirements": [
            "original file snapshot or enough pre-suggestion context",
            "final file snapshot or enough final evidence",
            "validated suggestion provenance",
        ],
        "quarantine_reasons": [],
        "suggestion_provenance": None,
    }


class FakeGateway:
    def __init__(self, *, body: str = "```suggestion\nreturn value\n```", created_at: str = "2026-01-01T00:00:00Z") -> None:
        self.body = body
        self.created_at = created_at
        self.snapshot_calls: list[tuple[str, str]] = []

    async def fetch_pr_json(self, repo: RepoRef) -> dict[str, object]:
        return {
            "merged": True,
            "merged_at": "2026-01-02T00:00:00Z",
            "merge_commit_sha": "c" * 40,
            "base": {"sha": "b" * 40},
            "head": {"sha": "d" * 40},
        }

    async def fetch_pr_review_comments(self, repo: RepoRef) -> list[dict[str, object]]:
        return [
            {
                "id": 42,
                "body": self.body,
                "html_url": "https://github.example/owner/repo/pull/7#discussion_r42",
                "path": "src/example.py",
                "original_commit_id": "a" * 40,
                "created_at": self.created_at,
                "updated_at": self.created_at,
                "user": {"login": "reviewer"},
            }
        ]

    async def fetch_file_snapshot(self, repo: RepoRef, *, path: str, revision_sha: str) -> FileSnapshot:
        self.snapshot_calls.append((path, revision_sha))
        return _snapshot(path, revision_sha)


class ReconstructProvenanceTest(unittest.IsolatedAsyncioTestCase):
    async def test_reconstruction_promotes_only_provenance_complete_candidates(self) -> None:
        suggested_diff = "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return value"
        gateway = FakeGateway()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "reconstructable.jsonl"
            input_path.write_text(json.dumps(_inventory_row(suggested_diff=suggested_diff)) + "\n", encoding="utf-8")

            summary = await reconstruct_inventory_provenance(
                input_path=input_path,
                output_dir=root / "reconstructed",
                gateway=gateway,
            )

            self.assertEqual(summary["benchmark_candidate_examples"], 1)
            self.assertEqual(summary["dropped_rows"], 0)
            candidates = [
                json.loads(line)
                for line in (root / "reconstructed" / "benchmark_candidates.jsonl").read_text().splitlines()
            ]
            self.assertEqual(candidates[0]["example_id"], "example-1")
            self.assertNotIn("weak_label_percentage", candidates[0])
            provenance = candidates[0]["suggestion_provenance"]
            self.assertEqual(provenance["suggestion_created_at"], "2026-01-01T00:00:00Z")
            self.assertEqual(provenance["pr_merged_at"], "2026-01-02T00:00:00Z")
            self.assertEqual(provenance["suggestion_base_snapshot"]["source"], "fake_gateway")
            self.assertEqual(provenance["final_state_snapshot"]["revision_sha"], "c" * 40)
            self.assertEqual(gateway.snapshot_calls, [("src/example.py", "a" * 40), ("src/example.py", "c" * 40)])

    async def test_reconstruction_drops_mismatched_suggestion_text_without_guessing(self) -> None:
        gateway = FakeGateway(body="```suggestion\nreturn different\n```")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "reconstructable.jsonl"
            input_path.write_text(
                json.dumps(_inventory_row(suggested_diff="--- a/src/example.py\n+++ b/src/example.py\n@@\n+return value"))
                + "\n",
                encoding="utf-8",
            )

            summary = await reconstruct_inventory_provenance(
                input_path=input_path,
                output_dir=root / "reconstructed",
                gateway=gateway,
            )

            self.assertEqual(summary["benchmark_candidate_examples"], 0)
            dropped = [
                json.loads(line)
                for line in (root / "reconstructed" / "dropped_provenance.jsonl").read_text().splitlines()
            ]
            self.assertEqual(dropped[0]["reasons"], ["fetched suggestion text differs from inventory row"])

    async def test_reconstruction_drops_suggestions_created_after_merge(self) -> None:
        suggested_diff = "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return value"
        gateway = FakeGateway(created_at="2026-01-03T00:00:00Z")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "reconstructable.jsonl"
            input_path.write_text(json.dumps(_inventory_row(suggested_diff=suggested_diff)) + "\n", encoding="utf-8")

            summary = await reconstruct_inventory_provenance(
                input_path=input_path,
                output_dir=root / "reconstructed",
                gateway=gateway,
            )

            self.assertEqual(summary["benchmark_candidate_examples"], 0)
            dropped = [
                json.loads(line)
                for line in (root / "reconstructed" / "dropped_provenance.jsonl").read_text().splitlines()
            ]
            self.assertEqual(dropped[0]["reasons"], ["suggestion was not created before PR merge"])


if __name__ == "__main__":
    unittest.main()

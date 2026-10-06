from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.benchmark.inventory_exploration_datasets import inventory_exploration_datasets


def _snapshot(revision: str, content: str) -> dict[str, str]:
    return {
        "revision_sha": revision,
        "path": "src/example.py",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source": "test",
    }


class InventoryExplorationDatasetsTest(unittest.TestCase):
    def test_inventory_classifies_internal_and_external_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            internal_raw_pairs = root / "raw_pairs.jsonl"
            internal_dataset = root / "internal_dataset.jsonl"
            external_dataset = root / "external_dataset.jsonl"

            raw_row = {
                "inspection_id": "inspection-1",
                "fault_id": "fault-1",
                "handler_code_changes_diff": "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return answer",
                "merged_pr_diff": "diff --git a/src/example.py b/src/example.py\n--- a/src/example.py\n+++ b/src/example.py\n@@ -1 +1,2 @@\n value = 1\n+return answer",
                "repo_host": "github.example",
                "repo_owner": "owner",
                "repo_name": "repo",
                "pr_number": 10,
                "pr_url": "https://github.example/owner/repo/pull/10",
                "merge_commit_sha": "d" * 40,
                "handler_diff_path": "github_review_comment:123#suggestion:1",
                "merged_pr_diff_source": "github_pull_diff_api",
            }
            internal_raw_pairs.write_text(json.dumps(raw_row) + "\n", encoding="utf-8")

            processed_row = {
                "example_id": "internal-1",
                "repo": "github.example/owner/repo",
                "pr_url": "https://github.example/owner/repo/pull/10",
                "pr_number": 10,
                "suggestion_source": "github_review_comment:123#suggestion:1",
                "suggested_diff": raw_row["handler_code_changes_diff"],
                "landed_diff": raw_row["merged_pr_diff"],
                "merge_commit_sha": "d" * 40,
                "expected_landed_percentage": 80,
                "metadata": {"renamed_files": False},
            }
            internal_dataset.write_text(json.dumps(processed_row) + "\n", encoding="utf-8")

            external_row = {
                "example_id": "external-1",
                "repo": "host/owner/ext-repo",
                "pr_url": "https://github.com/owner/ext-repo/pull/2",
                "suggested_diff": "--- a/src/other.py\n+++ b/src/other.py\n@@\n+return item",
                "landed_diff": "--- a/src/other.py\n+++ b/src/other.py\n@@ -1 +1,2 @@\n value = 1\n+return item",
                "file_path": "src/other.py",
                "expected_landed_percentage": 100,
                "metadata": {"label_source": "weak_line_overlap"},
            }
            external_dataset.write_text(json.dumps(external_row) + "\n", encoding="utf-8")

            summary = inventory_exploration_datasets(
                internal_raw_pairs_path=internal_raw_pairs,
                internal_dataset_path=internal_dataset,
                external_dataset_path=external_dataset,
                output_dir=root / "inventory",
            )

            self.assertEqual(summary["sources"]["internal_raw_pairs"]["rows"], 1)
            self.assertEqual(summary["sources"]["internal_processed_dataset"]["rows"], 1)
            self.assertEqual(summary["sources"]["external_github_codereview"]["rows"], 1)
            self.assertEqual(summary["reconstructable_examples"], 2)
            self.assertEqual(summary["quarantined_examples"], 1)
            self.assertEqual(summary["benchmark_candidate_examples"], 0)

            candidate_pool_rows = [
                json.loads(line) for line in (root / "inventory" / "candidate_pool.jsonl").read_text().splitlines()
            ]
            internal_record = next(row for row in candidate_pool_rows if row["example_id"] == "internal-1")
            external_record = next(row for row in candidate_pool_rows if row["example_id"] == "external-1")

            self.assertEqual(internal_record["status"], "needs_reconstruction")
            self.assertEqual(internal_record["source_datasets"], ["internal_processed_dataset"])
            self.assertEqual(internal_record["original_file_path"], "src/example.py")
            self.assertIn("original file snapshot or enough pre-suggestion context", internal_record["missing_requirements"])
            self.assertIn("final file snapshot or enough final evidence", internal_record["missing_requirements"])

            self.assertEqual(external_record["status"], "quarantined")
            self.assertIn("stable inline suggestion anchor", external_record["quarantine_reasons"])
            self.assertIn("merge commit or comparable final revision", external_record["quarantine_reasons"])

    def test_inventory_writes_benchmark_candidates_when_provenance_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "raw_pairs.jsonl").write_text("", encoding="utf-8")
            (root / "external_dataset.jsonl").write_text("", encoding="utf-8")
            ready_row = {
                "example_id": "ready-1",
                "repo": "host/owner/repo",
                "pr_url": "https://host/owner/repo/pull/1",
                "pr_number": 1,
                "suggestion_source": "github_review_comment:1#suggestion:1",
                "suggested_diff": "--- a/src/example.py\n+++ b/src/example.py\n@@\n+return value",
                "landed_diff": "diff --git a/src/example.py b/src/example.py\n--- a/src/example.py\n+++ b/src/example.py\n@@ -1 +1,2 @@\n old\n+return value",
                "merge_commit_sha": "d" * 40,
                "suggestion_provenance": {
                    "source_kind": "github_review_comment",
                    "suggestion_id": "suggestion-1",
                    "suggestion_created_at": "2026-01-01T00:00:00Z",
                    "original_commit_sha": "a" * 40,
                    "path": "src/example.py",
                    "merge_commit_sha": "d" * 40,
                    "pr_merged_at": "2026-01-02T00:00:00Z",
                    "compared_diff_base_sha": "b" * 40,
                    "compared_diff_head_sha": "c" * 40,
                    "suggestion_base_snapshot": _snapshot("a" * 40, "before\n"),
                    "final_state_snapshot": _snapshot("d" * 40, "after\n"),
                },
            }
            (root / "internal_dataset.jsonl").write_text(json.dumps(ready_row) + "\n", encoding="utf-8")

            summary = inventory_exploration_datasets(
                internal_raw_pairs_path=root / "raw_pairs.jsonl",
                internal_dataset_path=root / "internal_dataset.jsonl",
                external_dataset_path=root / "external_dataset.jsonl",
                output_dir=root / "inventory",
            )

            self.assertEqual(summary["benchmark_candidate_examples"], 1)
            benchmark_rows = [
                json.loads(line) for line in (root / "inventory" / "benchmark_candidates.jsonl").read_text().splitlines()
            ]
            self.assertEqual(benchmark_rows[0]["example_id"], "ready-1")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from pr_suggestion_metrics.build_dataset import (
    RawPair,
    _dataset_row,
    _read_pairs,
    _write_benchmark_candidates,
    _write_jsonl,
)
from pr_suggestion_metrics.scientific_contracts import BenchmarkCandidate, FileSnapshot, SuggestionProvenance


def raw_pair(**changes: object) -> dict[str, object]:
    return {
        "inspection_id": "inspection",
        "fault_id": "fault",
        "handler_code_changes_diff": "",
        "merged_pr_diff": "",
        "repo_host": "github.example",
        "repo_owner": "owner",
        "repo_name": "repo",
        "pr_number": 1,
        "pr_url": "https://github.example/owner/repo/pull/1",
        "handler_diff_path": "handler_results/fault/code_changes.diff",
        "merged_pr_diff_source": "test",
        **changes,
    }


def snapshot(revision: str, content: str) -> FileSnapshot:
    return FileSnapshot(
        revision_sha=revision,
        path="src/example.py",
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        source="test",
    )


def verified_provenance() -> SuggestionProvenance:
    return SuggestionProvenance(
        source_kind="unknown",
        suggestion_id="suggestion",
        suggestion_created_at=datetime(2025, 1, 1, tzinfo=UTC),
        pr_merged_at=datetime(2025, 1, 2, tzinfo=UTC),
        compared_diff_base_sha="base",
        compared_diff_head_sha="head",
        merge_commit_sha="merge",
        suggestion_base_snapshot=snapshot("base", "before\n"),
        final_state_snapshot=snapshot("merge", "after\n"),
    )


class RawPairValidationTest(unittest.TestCase):
    def test_out_of_range_percentage_is_rejected_at_ingestion(self) -> None:
        with self.assertRaisesRegex(ValidationError, "less than or equal to 100"):
            RawPair.model_validate(raw_pair(expected_landed_percentage=101))

    def test_legacy_bucket_fields_are_not_part_of_the_model(self) -> None:
        pair = RawPair.model_validate(
            raw_pair(
                expected_landed_percentage=50,
                human_label="partial",
                expected_percentage_bucket="41-50",
            )
        )

        self.assertNotIn("human_label", RawPair.model_fields)
        self.assertNotIn("expected_percentage_bucket", pair.model_dump())


class JsonlIoTest(unittest.TestCase):
    def test_read_pairs_preserves_physical_line_in_pydantic_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "pairs.jsonl"
            invalid_pair = raw_pair(pr_number="not-an-integer")
            path.write_text("\n\n" + json.dumps(invalid_pair) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, rf"Could not parse {path}:3:") as raised:
                _read_pairs([path])
            self.assertIn("valid integer", str(raised.exception))

    def test_read_pairs_replaces_invalid_utf8_like_before(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "pairs.jsonl"
            content = json.dumps(raw_pair(fault_id="café"), ensure_ascii=False).encode("utf-8")
            path.write_bytes(content.replace("café".encode(), b"caf\xff") + b"\n")

            pairs = _read_pairs([path])

            self.assertEqual(pairs[0].fault_id, "caf\ufffd")

    def test_dataset_writer_preserves_pydantic_json_and_exclude_none(self) -> None:
        row = _dataset_row(RawPair.model_validate(raw_pair(handler_code_changes_diff="+café")))
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "dataset.jsonl"

            _write_jsonl(path, [row])

            expected = (row.model_dump_json(exclude_none=True) + "\n").encode("utf-8")
            self.assertEqual(path.read_bytes(), expected)
            self.assertNotIn(b'"source_branch"', expected)

    def test_benchmark_writer_preserves_pydantic_json(self) -> None:
        row = _dataset_row(
            RawPair.model_validate(
                raw_pair(handler_code_changes_diff="+café", suggestion_provenance=verified_provenance())
            )
        )
        self.assertIsNotNone(row.suggestion_provenance)
        candidate = BenchmarkCandidate(
            example_id=row.example_id,
            repo=row.repo,
            pr_url=row.pr_url,
            pr_number=row.pr_number,
            suggested_diff=row.suggested_diff,
            landed_diff=row.landed_diff,
            suggestion_provenance=row.suggestion_provenance,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "benchmark.jsonl"

            count = _write_benchmark_candidates(path, [row])

            self.assertEqual(count, 1)
            self.assertEqual(path.read_bytes(), (candidate.model_dump_json() + "\n").encode("utf-8"))


if __name__ == "__main__":
    unittest.main()

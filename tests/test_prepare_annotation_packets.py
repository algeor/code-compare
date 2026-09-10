from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.prepare_annotation_packets import prepare_annotation_packets


def _snapshot(revision: str, content: str) -> dict[str, str]:
    return {
        "revision_sha": revision,
        "path": "src/example.py",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "source": "test",
    }


class PrepareAnnotationPacketsTest(unittest.TestCase):
    def test_packets_are_double_assigned_and_blinded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            examples_path = root / "examples.jsonl"
            rows = []
            for index in range(3):
                rows.append(
                    {
                        "example_id": f"example-{index}",
                        "repo": f"host/owner/repo-{index}",
                        "pr_url": f"https://host/owner/repo-{index}/pull/{index}",
                        "pr_number": index,
                        "suggested_diff": "+return value",
                        "landed_diff": "+return value",
                        "suggestion_provenance": {
                            "source_kind": "github_review_comment",
                            "suggestion_id": f"suggestion-{index}",
                            "author_login": "must-not-leak",
                            "suggestion_created_at": "2026-01-01T00:00:00Z",
                            "original_commit_sha": "a" * 40,
                            "path": "src/example.py",
                            "merge_commit_sha": "d" * 40,
                            "pr_merged_at": "2026-01-02T00:00:00Z",
                            "compared_diff_base_sha": "b" * 40,
                            "compared_diff_head_sha": "c" * 40,
                            "suggestion_base_snapshot": _snapshot("a" * 40, "before"),
                            "final_state_snapshot": _snapshot("d" * 40, "after"),
                        },
                    }
                )
            examples_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            output_dir = root / "packets"
            manifest = prepare_annotation_packets(
                examples_path=examples_path,
                annotator_ids=["a", "b", "c"],
                output_dir=output_dir,
                guide_version="1.0",
                seed=42,
            )

            packet_rows = []
            for packet_path in output_dir.glob("annotator-*.jsonl"):
                packet_rows.extend(json.loads(line) for line in packet_path.read_text().splitlines())
            self.assertEqual(manifest["assignment_count"], 6)
            self.assertEqual(len(packet_rows), 6)
            self.assertTrue(all("author_login" not in row["suggestion_provenance"] for row in packet_rows))
            self.assertTrue(all("expected_landed_percentage" not in row for row in packet_rows))

    def test_existing_labels_are_rejected_before_packet_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            examples_path = root / "examples.jsonl"
            examples_path.write_text(json.dumps({"example_id": "x", "label": "100%"}) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "forbidden label/model fields"):
                prepare_annotation_packets(
                    examples_path=examples_path,
                    annotator_ids=["a", "b"],
                    output_dir=root / "packets",
                    guide_version="1.0",
                    seed=42,
                )


if __name__ == "__main__":
    unittest.main()

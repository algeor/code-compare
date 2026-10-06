from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.freeze_benchmark import freeze_benchmark


def _provenance(day: int) -> dict[str, object]:
    base_content = f"before {day}\n"
    final_content = f"after {day}\n"
    return {
        "source_kind": "github_review_comment",
        "suggestion_id": f"suggestion-{day}",
        "suggestion_created_at": f"2026-01-0{day}T10:00:00Z",
        "original_commit_sha": "a" * 40,
        "path": "src/example.py",
        "pull_base_sha": "b" * 40,
        "pull_head_sha": "c" * 40,
        "merge_commit_sha": "d" * 40,
        "pr_merged_at": f"2026-01-0{day}T12:00:00Z",
        "compared_diff_base_sha": "b" * 40,
        "compared_diff_head_sha": "c" * 40,
        "compared_diff_source": "github_pull_diff_api",
        "suggestion_base_snapshot": {
            "revision_sha": "a" * 40,
            "path": "src/example.py",
            "content": base_content,
            "content_sha256": hashlib.sha256(base_content.encode()).hexdigest(),
            "source": "github_contents_api",
        },
        "final_state_snapshot": {
            "revision_sha": "d" * 40,
            "path": "src/example.py",
            "content": final_content,
            "content_sha256": hashlib.sha256(final_content.encode()).hexdigest(),
            "source": "github_contents_api",
        },
    }


def _annotation(example_id: str, annotator_id: str, credit: float = 1.0) -> dict[str, object]:
    status = "landed_equivalently" if credit == 1.0 else "landed_partially"
    return {
        "guide_version": "1.0",
        "example_id": example_id,
        "annotator_id": annotator_id,
        "decision": "scored",
        "units": [
            {
                "unit_id": "u1",
                "description": "return the computed value",
                "weight": 3,
                "credit": credit,
                "status": status,
                "evidence": ["src/example.py:return"],
                "preexisting": False,
            }
        ],
        "confidence": "high",
    }


class FreezeBenchmarkTest(unittest.TestCase):
    def _write_fixture(self, root: Path, *, omit_second_annotation: bool = False) -> dict[str, Path]:
        examples = []
        annotations = []
        adjudications = []
        splits = []
        suggestion_lines = {1: "return value", 2: "raise Error()", 3: "print(value)"}
        for day, split in ((1, "train"), (2, "development"), (3, "test")):
            example_id = f"example-{day}"
            examples.append(
                {
                    "example_id": example_id,
                    "repo": f"host/owner/repo-{day}",
                    "pr_url": f"https://host/owner/repo-{day}/pull/{day}",
                    "pr_number": day,
                    "suggested_diff": f"--- a/a.py\n+++ b/a.py\n@@\n+{suggestion_lines[day]}",
                    "landed_diff": f"--- a/a.py\n+++ b/a.py\n@@\n+{suggestion_lines[day]}",
                    "suggestion_provenance": _provenance(day),
                }
            )
            annotations.append(_annotation(example_id, "annotator-a"))
            if not omit_second_annotation:
                annotations.append(_annotation(example_id, "annotator-b", 0.5 if day == 2 else 1.0))
            adjudication = _annotation(example_id, "adjudicator")
            adjudication["source_annotator_ids"] = ["annotator-a", "annotator-b"]
            adjudication["resolution_notes"] = "Reviewed both independent records."
            adjudications.append(adjudication)
            splits.append({"example_id": example_id, "split": split})

        paths = {name: root / f"{name}.jsonl" for name in ("examples", "annotations", "adjudications")}
        for name, rows in (("examples", examples), ("annotations", annotations), ("adjudications", adjudications)):
            paths[name].write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        paths["splits"] = root / "splits.csv"
        with paths["splits"].open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["example_id", "split"])
            writer.writeheader()
            writer.writerows(splits)
        return paths

    def test_freeze_separates_private_test_labels_and_writes_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            output_dir = root / "frozen"

            manifest = freeze_benchmark(
                examples_path=paths["examples"],
                annotations_path=paths["annotations"],
                adjudications_path=paths["adjudications"],
                splits_path=paths["splits"],
                output_dir=output_dir,
                split_policy="repository_disjoint",
            )

            test_input = json.loads((output_dir / "test_inputs.jsonl").read_text())
            private_label = json.loads((output_dir / "test_labels.private.jsonl").read_text())
            self.assertNotIn("coverage_percentage", test_input)
            self.assertEqual(private_label["coverage_percentage"], 100)
            self.assertEqual(manifest["counts"], {"train": 1, "development": 1, "calibration": 0, "test": 1})
            self.assertIn("private_test_labels", manifest["artifact_sha256"])

    def test_freeze_rejects_single_annotator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root, omit_second_annotation=True)

            with self.assertRaisesRegex(ValueError, "requires exactly two independent annotators"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="repository_disjoint",
                )

    def test_freeze_rejects_duplicate_annotator_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            duplicate = json.loads(paths["annotations"].read_text().splitlines()[0])
            with paths["annotations"].open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(duplicate) + "\n")

            with self.assertRaisesRegex(ValueError, "Duplicate annotation record"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="repository_disjoint",
                )

    def test_freeze_rejects_annotation_for_unknown_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            unknown = _annotation("unknown-example", "annotator-a")
            with paths["annotations"].open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(unknown) + "\n")

            with self.assertRaisesRegex(ValueError, "Annotations reference unknown examples"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="repository_disjoint",
                )

    def test_freeze_rejects_more_than_two_annotators(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            third = _annotation("example-1", "annotator-c")
            with paths["annotations"].open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(third) + "\n")

            with self.assertRaisesRegex(ValueError, "exactly two independent annotators"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="repository_disjoint",
                )

    def test_freeze_rejects_unknown_split_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)

            with self.assertRaisesRegex(ValueError, "Unsupported split policy"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="typo",
                )

    def test_freeze_quarantines_abstained_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            annotation_rows = [json.loads(line) for line in paths["annotations"].read_text().splitlines()]
            annotation_rows[0].update(decision="abstain", abstention_reasons=["ambiguous evidence"], units=[])
            paths["annotations"].write_text(
                "".join(json.dumps(row) + "\n" for row in annotation_rows),
                encoding="utf-8",
            )
            adjudication_rows = [
                json.loads(line)
                for line in paths["adjudications"].read_text().splitlines()
                if json.loads(line)["example_id"] != "example-1"
            ]
            paths["adjudications"].write_text(
                "".join(json.dumps(row) + "\n" for row in adjudication_rows),
                encoding="utf-8",
            )

            manifest = freeze_benchmark(
                examples_path=paths["examples"],
                annotations_path=paths["annotations"],
                adjudications_path=paths["adjudications"],
                splits_path=paths["splits"],
                output_dir=root / "frozen",
                split_policy="repository_disjoint",
            )

            abstained = [json.loads(line) for line in (root / "frozen" / "abstained.jsonl").read_text().splitlines()]
            self.assertEqual(manifest["abstained_count"], 1)
            self.assertEqual(abstained[0]["example_id"], "example-1")


if __name__ == "__main__":
    unittest.main()

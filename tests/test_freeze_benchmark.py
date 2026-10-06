from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def _annotation(
    example_id: str,
    annotator_id: str,
    credit: float = 1.0,
    *,
    source_type: str = "human",
) -> dict[str, object]:
    status = "landed_equivalently" if credit == 1.0 else "landed_partially"
    row: dict[str, object] = {
        "guide_version": "1.0",
        "source_type": source_type,
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
    if source_type == "llm":
        row["model_id"] = "test-llm-2026-10-06"
        row["prompt_sha256"] = "a" * 64
    return row


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
            self.assertEqual(manifest["normalization_policy_version"], "1.0")

            test_input = json.loads((output_dir / "test_inputs.jsonl").read_text())
            private_label = json.loads((output_dir / "test_labels.private.jsonl").read_text())
            self.assertNotIn("coverage_percentage", test_input)
            self.assertEqual(private_label["coverage_percentage"], 100)
            self.assertEqual(manifest["counts"], {"train": 1, "development": 1, "calibration": 0, "test": 1})
            self.assertIn("private_test_labels", manifest["artifact_sha256"])

    def test_freeze_accepts_explicit_llm_adjudicated_mode_without_human_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            for key in ("annotations", "adjudications"):
                rows = [json.loads(line) for line in paths[key].read_text().splitlines()]
                for row in rows:
                    row["source_type"] = "llm"
                    row["model_id"] = f"{row['annotator_id']}-model"
                    row["prompt_sha256"] = "b" * 64
                paths[key].write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            manifest = freeze_benchmark(
                examples_path=paths["examples"],
                annotations_path=paths["annotations"],
                adjudications_path=paths["adjudications"],
                splits_path=paths["splits"],
                output_dir=root / "frozen",
                split_policy="repository_disjoint",
                annotation_mode="llm_adjudicated",
            )

            self.assertEqual(manifest["annotation_mode"], "llm_adjudicated")
            self.assertEqual(manifest["ground_truth_claim"], "llm_adjudicated_not_human_ground_truth")

    def test_human_mode_rejects_llm_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            rows = [json.loads(line) for line in paths["annotations"].read_text().splitlines()]
            rows[0]["source_type"] = "llm"
            rows[0]["model_id"] = "test-model"
            rows[0]["prompt_sha256"] = "c" * 64
            paths["annotations"].write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Human benchmark cannot use llm annotation"):
                freeze_benchmark(
                    examples_path=paths["examples"],
                    annotations_path=paths["annotations"],
                    adjudications_path=paths["adjudications"],
                    splits_path=paths["splits"],
                    output_dir=root / "frozen",
                    split_policy="repository_disjoint",
                )

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

    def test_freeze_manifest_reports_deterministic_split_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)

            example_rows = [json.loads(line) for line in paths["examples"].read_text().splitlines()]
            extra_example = {
                "example_id": "example-4",
                "repo": "host/owner/repo-4",
                "pr_url": "https://host/owner/repo-4/pull/4",
                "pr_number": 4,
                "suggested_diff": "--- a/a.py\n+++ b/a.py\n@@\n+return left + right",
                "landed_diff": "--- a/a.py\n+++ b/a.py\n@@\n+return left + right",
                "suggestion_provenance": _provenance(4),
            }
            example_rows.append(extra_example)
            paths["examples"].write_text(
                "".join(json.dumps(row) + "\n" for row in example_rows),
                encoding="utf-8",
            )

            annotation_rows = [json.loads(line) for line in paths["annotations"].read_text().splitlines()]
            annotation_rows.extend(
                [
                    _annotation("example-4", "annotator-a", 0.5),
                    _annotation("example-4", "annotator-b", 0.5),
                ]
            )
            paths["annotations"].write_text(
                "".join(json.dumps(row) + "\n" for row in annotation_rows),
                encoding="utf-8",
            )

            adjudication_rows = [json.loads(line) for line in paths["adjudications"].read_text().splitlines()]
            extra_adjudication = _annotation("example-4", "adjudicator", 0.5)
            extra_adjudication["source_annotator_ids"] = ["annotator-a", "annotator-b"]
            extra_adjudication["resolution_notes"] = "Reviewed both independent records."
            adjudication_rows.append(extra_adjudication)
            paths["adjudications"].write_text(
                "".join(json.dumps(row) + "\n" for row in adjudication_rows),
                encoding="utf-8",
            )

            with paths["splits"].open("a", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["example_id", "split"])
                writer.writerow({"example_id": "example-4", "split": "train"})

            manifest = freeze_benchmark(
                examples_path=paths["examples"],
                annotations_path=paths["annotations"],
                adjudications_path=paths["adjudications"],
                splits_path=paths["splits"],
                output_dir=root / "frozen",
                split_policy="repository_disjoint",
            )

            self.assertEqual(
                manifest["split_summary"]["target_percentages"],
                {"train": 60.0, "development": 15.0, "calibration": 10.0, "test": 15.0},
            )
            self.assertEqual(
                manifest["split_summary"]["splits"]["train"],
                {
                    "actual_percentage": 50.0,
                    "coverage_percentage": {"min": 50.0, "max": 100.0, "mean": 75.0},
                    "group_count": 2,
                    "repo_count": 2,
                    "row_count": 2,
                    "target_percentage": 60.0,
                },
            )
            self.assertEqual(
                list(manifest["split_summary"]["splits"]),
                ["train", "development", "calibration", "test"],
            )

    def test_freeze_does_not_publish_partial_output_when_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paths = self._write_fixture(root)
            output_dir = root / "frozen"

            with patch("pr_suggestion_metrics.freeze_benchmark.write_jsonl_objects", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    freeze_benchmark(
                        examples_path=paths["examples"],
                        annotations_path=paths["annotations"],
                        adjudications_path=paths["adjudications"],
                        splits_path=paths["splits"],
                        output_dir=output_dir,
                        split_policy="repository_disjoint",
                    )

            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()

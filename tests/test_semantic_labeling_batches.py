from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.semantic_labeling_batches import normalized_label_row, read_llm_output


class SemanticLabelInputTest(unittest.TestCase):
    def test_duplicate_example_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "labels.jsonl"
            output_path.write_text(
                '{"example_id":"duplicate","expected_landed_percentage":10}\n'
                '{"example_id":"duplicate","expected_landed_percentage":90}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate semantic label"):
                read_llm_output(output_path)

    def test_fractional_percentage_is_rejected_instead_of_truncated(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite integer"):
            normalized_label_row(
                {"example_id": "fractional"},
                {},
                {"expected_landed_percentage": 50.9},
            )

    def test_normalized_row_contains_no_derived_bucket_fields(self) -> None:
        row = normalized_label_row(
            {"example_id": "percentage-only", "deterministic_landed_estimate": 40},
            {"label": "partial", "expected_percentage_bucket": "31-40"},
            {"expected_landed_percentage": 42, "reasoning": "Part of the behavior landed."},
        )

        self.assertEqual(row["expected_landed_percentage"], 42)
        self.assertNotIn("label", row)
        self.assertNotIn("expected_percentage_bucket", row)
        self.assertNotIn("suggested_label", row)


if __name__ == "__main__":
    unittest.main()

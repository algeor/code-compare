from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pr_suggestion_metrics.build_dataset import DatasetRow, DiffStats, _write_labels_csv
from pr_suggestion_metrics.evaluate_metrics import _DEFAULT_DATASET_DIR, _DEFAULT_OUTPUT_PATH, _write_scores
from pr_suggestion_metrics.model_inference import prepare_model_features
from pr_suggestion_metrics.semantic_labeling_batches import _DEFAULT_PROMPT_PATH
from pr_suggestion_metrics.train_percentage_regressor import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    prepare_features,
)


class RepositoryPathRegressionTest(unittest.TestCase):
    def test_package_import_does_not_eagerly_load_model_inference(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import sys; import pr_suggestion_metrics; "
            "assert 'pr_suggestion_metrics.model_inference' not in sys.modules",
        ]

        completed = subprocess.run(command, check=False, capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_default_input_paths_exist_in_repository(self) -> None:
        self.assertTrue(_DEFAULT_DATASET_DIR.is_dir())
        self.assertTrue(_DEFAULT_PROMPT_PATH.is_file())
        self.assertEqual(_DEFAULT_OUTPUT_PATH.parent.name, "reports")

    def test_score_writer_creates_output_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "nested" / "scores.csv"
            _write_scores(output_path, [], [])

            self.assertTrue(output_path.is_file())


class DatasetSerializationRegressionTest(unittest.TestCase):
    def test_zero_percentage_is_not_serialized_as_blank(self) -> None:
        empty_stats = DiffStats(file_count=0, added_lines=0, removed_lines=0, hunk_count=0, files=[])
        row = DatasetRow(
            example_id="example-zero",
            inspection_id="inspection",
            fault_id="fault",
            repo="owner/repository",
            pr_url="https://example.invalid/pull/1",
            pr_number=1,
            source_branch=None,
            target_branch=None,
            base_sha=None,
            head_sha=None,
            merge_commit_sha=None,
            suggestion_source="test",
            merged_pr_diff_source="test",
            suggested_diff="",
            landed_diff="",
            suggested_stats=empty_stats,
            landed_stats=empty_stats,
            file_overlap_ratio=0.0,
            changed_line_overlap_ratio=0.0,
            deterministic_landed_estimate=0,
            label="0%",
            expected_landed_percentage=0,
            expected_percentage_bucket="0",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "labels.csv"
            _write_labels_csv(output_path, [row])
            with output_path.open(newline="") as stream:
                serialized = next(csv.DictReader(stream))

        self.assertEqual(serialized["expected_landed_percentage"], "0")


class BooleanFeatureRegressionTest(unittest.TestCase):
    def test_inference_preserves_all_supported_boolean_forms(self) -> None:
        schema = {
            "numeric_features": [],
            "boolean_features": ["flag"],
            "categorical_features": [],
            "feature_columns": ["flag"],
        }
        rows = pd.DataFrame({"flag": [True, False, 1, 0, "true", "false", "1", "0"]})

        prepared = prepare_model_features(rows, schema)

        self.assertEqual(prepared["flag"].tolist(), [1, 0, 1, 0, 1, 0, 1, 0])

    def test_inference_rejects_ambiguous_boolean(self) -> None:
        schema = {
            "numeric_features": [],
            "boolean_features": ["flag"],
            "categorical_features": [],
            "feature_columns": ["flag"],
        }

        with self.assertRaisesRegex(ValueError, "row index 0"):
            prepare_model_features([{"flag": "yes"}], schema)

    def test_training_preserves_integer_one_booleans(self) -> None:
        row = {feature: 0 for feature in NUMERIC_FEATURES}
        row.update({feature: 1 for feature in BOOLEAN_FEATURES})
        row.update({feature: "none" for feature in CATEGORICAL_FEATURES})
        row["expected_landed_percentage"] = 0

        prepared = prepare_features(pd.DataFrame([row]))

        self.assertEqual(prepared[BOOLEAN_FEATURES].iloc[0].tolist(), [1, 1, 1])

    def test_training_rejects_invalid_boolean(self) -> None:
        row = {feature: 0 for feature in NUMERIC_FEATURES}
        row.update({feature: False for feature in BOOLEAN_FEATURES})
        row.update({feature: "none" for feature in CATEGORICAL_FEATURES})
        row[BOOLEAN_FEATURES[0]] = "not-a-boolean"
        row["expected_landed_percentage"] = 0

        with self.assertRaisesRegex(ValueError, BOOLEAN_FEATURES[0]):
            prepare_features(pd.DataFrame([row]))


if __name__ == "__main__":
    unittest.main()

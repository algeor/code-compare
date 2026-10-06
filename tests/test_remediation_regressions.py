from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from pr_suggestion_metrics.build_dataset import DatasetRow, DiffStats, _write_labels_csv
from pr_suggestion_metrics.collect_pr_code_changes import (
    CandidateRow,
    _extract_comment_diff_suggestions,
    _final_path_for_suggested_path,
)
from pr_suggestion_metrics.evaluate_metrics import _DEFAULT_DATASET_DIR, _DEFAULT_OUTPUT_PATH, _write_scores
from pr_suggestion_metrics.model_artifacts import write_model_manifest
from pr_suggestion_metrics.model_inference import (
    load_model_bundle,
    predict_coverage_from_diffs,
    predict_coverage_percentages,
    prepare_model_features,
)
from pr_suggestion_metrics.modeling.common import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES
from pr_suggestion_metrics.modeling.train import _prepare
from pr_suggestion_metrics.private_collection_adapter import load_hdlf_adapter
from pr_suggestion_metrics.scientific_contracts import FileSnapshot, HumanAnnotation, SemanticUnit, SuggestionProvenance
from pr_suggestion_metrics.semantic_labeling_batches import _DEFAULT_PROMPT_PATH
from tests.model_fixture import write_percentage_model


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


class OptionalCollectionDependencyTest(unittest.TestCase):
    def test_missing_private_hdlf_dependency_has_actionable_error(self) -> None:
        original_import = __import__

        def import_without_fl_shared(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("fl_shared"):
                raise ModuleNotFoundError(name)
            return original_import(name, *args, **kwargs)

        load_hdlf_adapter.cache_clear()
        with patch("builtins.__import__", side_effect=import_without_fl_shared):
            with self.assertRaisesRegex(RuntimeError, "organization-private fl_shared"):
                load_hdlf_adapter()
        load_hdlf_adapter.cache_clear()


class ScientificEvidenceContractTest(unittest.TestCase):
    def test_final_path_resolves_rename(self) -> None:
        merged_diff = """diff --git a/src/old.py b/src/new.py
similarity index 100%
rename from src/old.py
rename to src/new.py
"""

        self.assertEqual(_final_path_for_suggested_path("src/old.py", merged_diff), ("src/new.py", "renamed"))

    def test_file_snapshot_rejects_changed_content(self) -> None:
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            FileSnapshot(
                revision_sha="a" * 40,
                path="src/example.py",
                content="changed",
                content_sha256=hashlib.sha256(b"original").hexdigest(),
                source="test",
            )

    def test_review_comment_extraction_preserves_temporal_anchor(self) -> None:
        candidate = CandidateRow(
            inspection_id="inspection",
            execution_id="execution",
            fault_id="fault",
            handler_status="success",
            github_repo_url="https://github.example/owner/repo",
            pr_number="7",
        )
        comment = {
            "id": 42,
            "body": "```suggestion\nreturn value\n```",
            "html_url": "https://github.example/owner/repo/pull/7#discussion_r42",
            "created_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-01-01T10:05:00Z",
            "commit_id": "a" * 40,
            "original_commit_id": "b" * 40,
            "path": "src/example.py",
            "line": 12,
            "side": "RIGHT",
            "user": {"login": "reviewer"},
        }

        suggestions = _extract_comment_diff_suggestions(
            candidate,
            comment,
            source="all",
            author_filters=[],
            kind="review",
        )

        self.assertEqual(len(suggestions), 1)
        provenance = suggestions[0].provenance
        self.assertIsNotNone(provenance)
        assert provenance is not None
        self.assertEqual(provenance.original_commit_sha, "b" * 40)
        self.assertEqual(provenance.path, "src/example.py")
        self.assertEqual(provenance.author_login, "reviewer")

    def test_provenance_rejects_post_merge_suggestion(self) -> None:
        provenance = SuggestionProvenance(
            source_kind="github_review_comment",
            suggestion_id="suggestion",
            suggestion_created_at="2026-01-02T00:00:00Z",
            pr_merged_at="2026-01-01T00:00:00Z",
            original_commit_sha="a" * 40,
            path="src/example.py",
            compared_diff_base_sha="b" * 40,
            compared_diff_head_sha="c" * 40,
            merge_commit_sha="d" * 40,
        )

        self.assertIn("suggestion was not created before PR merge", provenance.validation_issues())
        self.assertFalse(provenance.is_temporally_verified)

    def test_annotation_percentage_is_recomputed_from_units(self) -> None:
        annotation = HumanAnnotation(
            guide_version="1.0",
            example_id="example",
            annotator_id="annotator-a",
            decision="scored",
            units=[
                SemanticUnit(
                    unit_id="core",
                    description="core behavior",
                    weight=3,
                    credit=1.0,
                    status="landed_equivalently",
                    evidence=["src/example.py:symbol"],
                    preexisting=False,
                ),
                SemanticUnit(
                    unit_id="support",
                    description="supporting behavior",
                    weight=1,
                    credit=0.0,
                    status="absent",
                    evidence=["No matching final-state behavior"],
                    preexisting=False,
                ),
            ],
            confidence="high",
        )

        self.assertEqual(annotation.validation_issues(), [])
        self.assertEqual(annotation.computed_percentage(), 75.0)

    def test_annotation_rejects_status_credit_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires credit 0.0"):
            SemanticUnit(
                unit_id="missing",
                description="missing behavior",
                weight=2,
                credit=1.0,
                status="absent",
                evidence=["No final-state evidence"],
                preexisting=False,
            )


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
            expected_landed_percentage=0,
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

        prepared = _prepare(pd.DataFrame([row]), NUMERIC_FEATURES, BOOLEAN_FEATURES, CATEGORICAL_FEATURES)

        self.assertEqual(prepared[BOOLEAN_FEATURES].iloc[0].tolist(), [1, 1, 1])

    def test_training_rejects_invalid_boolean(self) -> None:
        row = {feature: 0 for feature in NUMERIC_FEATURES}
        row.update({feature: False for feature in BOOLEAN_FEATURES})
        row.update({feature: "none" for feature in CATEGORICAL_FEATURES})
        row[BOOLEAN_FEATURES[0]] = "not-a-boolean"
        row["expected_landed_percentage"] = 0

        with self.assertRaisesRegex(ValueError, BOOLEAN_FEATURES[0]):
            _prepare(pd.DataFrame([row]), NUMERIC_FEATURES, BOOLEAN_FEATURES, CATEGORICAL_FEATURES)


class NumericFeatureRegressionTest(unittest.TestCase):
    def test_inference_rejects_malformed_numeric_with_row_id(self) -> None:
        schema = {
            "numeric_features": ["token_recall"],
            "boolean_features": [],
            "categorical_features": [],
            "feature_columns": ["token_recall"],
        }

        with self.assertRaisesRegex(ValueError, "example-bad"):
            prepare_model_features([{"example_id": "example-bad", "token_recall": "unknown"}], schema)

    def test_inference_rejects_non_finite_numeric(self) -> None:
        schema = {
            "numeric_features": ["candidate_hunk_count"],
            "boolean_features": [],
            "categorical_features": [],
            "feature_columns": ["candidate_hunk_count"],
        }

        with self.assertRaisesRegex(ValueError, "finite number"):
            prepare_model_features([{"candidate_hunk_count": float("inf")}], schema)

    def test_inference_rejects_ratio_outside_unit_interval(self) -> None:
        schema = {
            "numeric_features": ["token_recall"],
            "boolean_features": [],
            "categorical_features": [],
            "feature_columns": ["token_recall"],
        }

        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            prepare_model_features([{"token_recall": 1.01}], schema)

    def test_feature_preparation_preserves_dataframe_index(self) -> None:
        schema = {
            "numeric_features": ["candidate_hunk_count"],
            "boolean_features": [],
            "categorical_features": [],
            "feature_columns": ["candidate_hunk_count"],
        }
        rows = pd.DataFrame({"candidate_hunk_count": [2]}, index=["stable-row"])

        prepared = prepare_model_features(rows, schema)

        self.assertEqual(prepared.index.tolist(), ["stable-row"])

    def test_percentage_inference_rejects_non_finite_model_output(self) -> None:
        schema = {
            "numeric_features": ["candidate_hunk_count"],
            "boolean_features": [],
            "categorical_features": [],
            "feature_columns": ["candidate_hunk_count"],
        }
        model = Mock()
        model.predict.return_value = [float("nan")]

        with patch("pr_suggestion_metrics.model_inference.load_model_bundle", return_value=(model, schema)):
            with self.assertRaisesRegex(ValueError, "only finite values"):
                predict_coverage_percentages([{"candidate_hunk_count": 1}], model_dir=Path("unused"))


class RawDiffInferenceRegressionTest(unittest.TestCase):
    def test_supported_single_hunk_addition_returns_prediction(self) -> None:
        suggestion_diff = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,0 +2,1 @@
+print("landed")
"""

        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = write_percentage_model(Path(temporary_directory))
            result = predict_coverage_from_diffs(
                suggestion_diff,
                suggestion_diff,
                example_id="raw-example",
                model_dir=model_dir,
            )

        self.assertEqual(result["example_id"], "raw-example")
        self.assertEqual(result["status"], "predicted")
        self.assertIsInstance(result["model_predicted_percentage"], int)
        self.assertGreaterEqual(result["model_predicted_percentage"], 0)
        self.assertLessEqual(result["model_predicted_percentage"], 100)
        self.assertIsInstance(result["model_raw_percentage"], float)
        self.assertEqual(result.result_schema_version, "1.0")
        self.assertTrue(result.input_hashes)
        self.assertTrue(result["warnings"])

    def test_replacement_suggestion_abstains_before_loading_model(self) -> None:
        suggestion_diff = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,1 +1,1 @@
-print("old")
+print("new")
"""

        result = predict_coverage_from_diffs(
            suggestion_diff,
            suggestion_diff,
            model_dir=Path("/model/does/not/exist"),
        )

        self.assertEqual(result["status"], "abstained")
        self.assertIsNone(result["model_predicted_percentage"])
        self.assertIn("suggestion deletions and replacements are not yet supported", result["warnings"])


class ModelArtifactIntegrityRegressionTest(unittest.TestCase):
    def test_model_load_rejects_schema_tampering_before_unpickling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = write_percentage_model(Path(temporary_directory))
            with (model_dir / "feature_schema.json").open("a", encoding="utf-8") as stream:
                stream.write("\n")

            with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
                load_model_bundle(model_dir)

    def test_model_load_validates_schema_before_unpickling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = Path(temporary_directory)
            (model_dir / "model.joblib").write_bytes(b"not a pickle")
            (model_dir / "feature_schema.json").write_text(
                json.dumps(
                    {
                        "numeric_features": ["line_recall"],
                        "boolean_features": [],
                        "categorical_features": [],
                        "feature_columns": ["token_recall"],
                    }
                ),
                encoding="utf-8",
            )
            write_model_manifest(model_dir)

            with patch("pr_suggestion_metrics.model_inference.joblib.load") as joblib_load:
                with self.assertRaisesRegex(ValueError, "must match the typed feature lists"):
                    load_model_bundle(model_dir)

            joblib_load.assert_not_called()


if __name__ == "__main__":
    unittest.main()

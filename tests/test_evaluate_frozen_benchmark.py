from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pr_suggestion_metrics.evaluate_frozen_benchmark import (
    _grouped_bootstrap_intervals,
    _write_json_exclusive,
    evaluate_frozen_benchmark,
)
from pr_suggestion_metrics.model_artifacts import sha256_file
from tests.model_fixture import write_percentage_model


_SUGGESTION = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1 @@
+return value
"""


def _write_benchmark(root: Path, *, labels: list[dict[str, object]] | None = None) -> Path:
    benchmark_dir = root / "benchmark"
    benchmark_dir.mkdir()
    test_inputs = benchmark_dir / "test_inputs.jsonl"
    private_labels = benchmark_dir / "test_labels.private.jsonl"
    test_inputs.write_text(
        json.dumps({"example_id": "example", "suggested_diff": _SUGGESTION, "landed_diff": _SUGGESTION}) + "\n",
        encoding="utf-8",
    )
    resolved_labels = labels or [{"example_id": "example", "coverage_unrounded": 100.0}]
    private_labels.write_text(
        "".join(json.dumps(label) + "\n" for label in resolved_labels),
        encoding="utf-8",
    )
    (benchmark_dir / "benchmark_manifest.json").write_text(
        json.dumps(
            {
                "artifact_sha256": {
                    "test": sha256_file(test_inputs),
                    "private_test_labels": sha256_file(private_labels),
                }
            }
        ),
        encoding="utf-8",
    )
    return benchmark_dir


class EvaluateFrozenBenchmarkTest(unittest.TestCase):
    def test_canonical_claim_creation_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            receipt_path = Path(temporary_directory) / "claim.json"
            _write_json_exclusive(receipt_path, {"status": "claimed", "owner": "first"})

            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                _write_json_exclusive(receipt_path, {"status": "claimed", "owner": "second"})

            self.assertEqual(json.loads(receipt_path.read_text())["owner"], "first")

    def test_grouped_bootstrap_returns_metric_intervals(self) -> None:
        intervals = _grouped_bootstrap_intervals(
            np.array([0.0, 10.0, 90.0, 100.0]),
            np.array([5.0, 15.0, 85.0, 95.0]),
            np.array(["pr-1", "pr-1", "pr-2", "pr-2"], dtype=object),
            iterations=50,
            seed=7,
        )

        self.assertIn("mae", intervals)
        self.assertLessEqual(intervals["mae"]["lower_95"], intervals["mae"]["upper_95"])

    def test_confirmatory_test_can_only_be_consumed_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model_dir = write_percentage_model(root)
            benchmark_dir = _write_benchmark(root)

            report = evaluate_frozen_benchmark(
                benchmark_dir=benchmark_dir,
                model_dir=model_dir,
                output_dir=root / "evaluation",
            )

            self.assertEqual(report["test_rows"], 1)
            self.assertEqual(report["estimated_rows"], 1)
            receipt_path = benchmark_dir / "CONFIRMATORY_TEST_CONSUMED.json"
            self.assertEqual(json.loads(receipt_path.read_text())["status"], "completed")
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                evaluate_frozen_benchmark(
                    benchmark_dir=benchmark_dir,
                    model_dir=model_dir,
                    output_dir=root / "evaluation-again",
                )

    def test_confirmatory_test_rejects_duplicate_private_label_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model_dir = write_percentage_model(root)
            label = {"example_id": "example", "coverage_unrounded": 100.0}
            benchmark_dir = _write_benchmark(root, labels=[label, label])

            with self.assertRaisesRegex(ValueError, "Duplicate example_id in private test labels"):
                evaluate_frozen_benchmark(
                    benchmark_dir=benchmark_dir,
                    model_dir=model_dir,
                    output_dir=root / "evaluation",
                )

            receipt = json.loads((benchmark_dir / "CONFIRMATORY_TEST_CONSUMED.json").read_text())
            self.assertEqual(receipt["status"], "claimed")
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                evaluate_frozen_benchmark(
                    benchmark_dir=benchmark_dir,
                    model_dir=model_dir,
                    output_dir=root / "evaluation-again",
                )

    def test_custom_receipt_cannot_redirect_canonical_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model_dir = write_percentage_model(root)
            benchmark_dir = _write_benchmark(root)
            compatibility_receipt = root / "legacy" / "receipt.json"

            evaluate_frozen_benchmark(
                benchmark_dir=benchmark_dir,
                model_dir=model_dir,
                output_dir=root / "evaluation",
                receipt_path=compatibility_receipt,
            )

            canonical_receipt = benchmark_dir / "CONFIRMATORY_TEST_CONSUMED.json"
            self.assertEqual(json.loads(canonical_receipt.read_text())["status"], "completed")
            self.assertEqual(json.loads(compatibility_receipt.read_text())["status"], "completed")
            with self.assertRaisesRegex(RuntimeError, str(canonical_receipt)):
                evaluate_frozen_benchmark(
                    benchmark_dir=benchmark_dir,
                    model_dir=model_dir,
                    output_dir=root / "evaluation-again",
                    receipt_path=root / "different-receipt.json",
                )


if __name__ == "__main__":
    unittest.main()

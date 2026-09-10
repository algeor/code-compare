from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pr_suggestion_metrics.evaluate_frozen_benchmark import evaluate_frozen_benchmark
from pr_suggestion_metrics.model_artifacts import sha256_file


class EvaluateFrozenBenchmarkTest(unittest.TestCase):
    def test_confirmatory_test_can_only_be_consumed_once(self) -> None:
        model_dir = Path(__file__).resolve().parents[1] / "models" / "pr_suggestion_coverage_regression"
        suggestion = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1 @@
+return value
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            benchmark_dir = root / "benchmark"
            benchmark_dir.mkdir()
            test_inputs = benchmark_dir / "test_inputs.jsonl"
            private_labels = benchmark_dir / "test_labels.private.jsonl"
            test_inputs.write_text(
                json.dumps({"example_id": "example", "suggested_diff": suggestion, "landed_diff": suggestion}) + "\n",
                encoding="utf-8",
            )
            private_labels.write_text(
                json.dumps({"example_id": "example", "coverage_unrounded": 100.0}) + "\n",
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

            report = evaluate_frozen_benchmark(
                benchmark_dir=benchmark_dir,
                model_dir=model_dir,
                output_dir=root / "evaluation",
            )

            self.assertEqual(report["test_rows"], 1)
            self.assertEqual(report["estimated_rows"], 1)
            self.assertTrue((benchmark_dir / "CONFIRMATORY_TEST_CONSUMED.json").is_file())
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                evaluate_frozen_benchmark(
                    benchmark_dir=benchmark_dir,
                    model_dir=model_dir,
                    output_dir=root / "evaluation-again",
                )


if __name__ == "__main__":
    unittest.main()

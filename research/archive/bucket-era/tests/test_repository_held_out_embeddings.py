from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from pr_suggestion_metrics.evaluate_repository_held_out_embeddings import (
    completed_repositories,
    configuration_fingerprint,
    macro_metrics,
    metric_differences,
    repository_bootstrap,
)


class RepositoryHeldOutEmbeddingTest(unittest.TestCase):
    def test_metric_differences_are_positive_for_better_candidate(self) -> None:
        actual = np.array([0.0, 50.0, 100.0])
        baseline = np.array([20.0, 70.0, 80.0])
        candidate = np.array([5.0, 55.0, 95.0])

        differences = metric_differences(actual, baseline, candidate)

        self.assertGreater(differences["mae_reduction"], 0)
        self.assertGreater(differences["rmse_reduction"], 0)
        self.assertGreater(differences["within_10_gain"], 0)

    def test_repository_bootstrap_is_reproducible(self) -> None:
        actual = np.array([0.0, 10.0, 90.0, 100.0])
        baseline = np.array([20.0, 30.0, 70.0, 80.0])
        candidate = np.array([5.0, 15.0, 85.0, 95.0])
        repositories = np.array(["a", "a", "b", "b"])

        first = repository_bootstrap(actual, baseline, candidate, repositories, iterations=100)
        second = repository_bootstrap(actual, baseline, candidate, repositories, iterations=100)

        self.assertEqual(first, second)
        self.assertGreater(first["mae_reduction"]["ci_95_low"], 0)

    def test_macro_metrics_return_nulls_when_no_repository_meets_threshold(self) -> None:
        per_repository = {
            "owner/repo": {
                "rows": 3,
                "candidate": {
                    "percentage_mae": 1.0,
                    "percentage_rmse": 1.0,
                    "within_5_points": 1.0,
                    "within_10_points": 1.0,
                    "dangerous_error_rate": 0.0,
                },
            }
        }

        result = macro_metrics(per_repository, "candidate", minimum_rows=10)

        self.assertTrue(all(value is None for value in result.values()))

    def test_configuration_fingerprint_tracks_input_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "input.csv"
            input_path.write_text("first", encoding="utf-8")
            first = configuration_fingerprint({}, {}, {}, [input_path])

            input_path.write_text("second", encoding="utf-8")
            second = configuration_fingerprint({}, {}, {}, [input_path])

        self.assertNotEqual(first, second)

    def test_incomplete_resumed_repository_is_rejected(self) -> None:
        completed = pd.DataFrame(
            [
                {
                    "example_id": "one",
                    "repo": "owner/repo",
                    **{column: 0 for column in (
                        "current_ensemble",
                        "unixcoder_two_stage",
                        "unixcoder_encoder_two_stage",
                        "codebert_two_stage",
                        "combined_two_stage",
                        "selected_embedding_blend",
                    )},
                }
            ]
        )
        external = pd.DataFrame(
            [
                {"example_id": "one", "repo": "owner/repo"},
                {"example_id": "two", "repo": "owner/repo"},
            ]
        )

        with self.assertRaisesRegex(ValueError, "incomplete fold"):
            completed_repositories(completed, external)


if __name__ == "__main__":
    unittest.main()

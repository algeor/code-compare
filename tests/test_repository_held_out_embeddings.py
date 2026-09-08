from __future__ import annotations

import unittest

import numpy as np

from pr_suggestion_metrics.evaluate_repository_held_out_embeddings import (
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

import numpy as np

from pr_suggestion_metrics.train_embedding_percentage_models import blended_predictions


class EmbeddingPercentageModelsTest(unittest.TestCase):
    def test_blend_uses_current_model_as_disagreement_fallback(self) -> None:
        predictions = {
            "current_ensemble": np.array([20.0, 40.0]),
            "embedding": np.array([90.0, 50.0]),
        }

        result = blended_predictions(
            predictions,
            {"current_ensemble": 0.5, "embedding": 0.5},
            disagreement_threshold=20.0,
            fallback_name="current_ensemble",
        )

        np.testing.assert_array_equal(result, np.array([20.0, 45.0]))


if __name__ == "__main__":
    unittest.main()

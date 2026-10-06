from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression

from pr_suggestion_metrics.model_artifacts import write_model_manifest
from pr_suggestion_metrics.model_inference import predict_coverage_percentages
from pr_suggestion_metrics.two_stage_percentage import (
    PercentageModelBlend,
    StackedPercentageEnsemble,
    TwoStageCatBoostRegressor,
    WeightedPercentageEnsemble,
)


class TwoStageCatBoostRegressorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        random = np.random.default_rng(42)
        cls.features = pd.DataFrame(
            {
                "overlap": np.concatenate(
                    [random.uniform(0.0, 0.12, 30), random.uniform(0.35, 0.65, 30), random.uniform(0.88, 1.0, 30)]
                ),
                "language": ["python", "java", "typescript"] * 30,
            }
        )
        cls.target = np.concatenate(
            [np.zeros(30), random.integers(30, 71, 30), np.full(30, 100)]
        )
        cls.model = TwoStageCatBoostRegressor(
            categorical_features=("language",),
            iterations=40,
            depth=3,
            learning_rate=0.1,
            endpoint_threshold=0.65,
            thread_count=1,
        ).fit(cls.features, cls.target)

    def test_predictions_are_bounded_and_ordered(self) -> None:
        predictions = self.model.predict(self.features)

        self.assertEqual(predictions.shape, (90,))
        self.assertTrue(np.all((predictions >= 0) & (predictions <= 100)))
        self.assertLess(predictions[:30].mean(), predictions[30:60].mean())
        self.assertLess(predictions[30:60].mean(), predictions[60:].mean())

    def test_percentage_inference_returns_no_bucket(self) -> None:
        schema = {
            "numeric_features": ["overlap"],
            "boolean_features": [],
            "categorical_features": ["language"],
            "feature_columns": ["overlap", "language"],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = Path(temporary_directory)
            joblib.dump(self.model, model_dir / "model.joblib")
            (model_dir / "feature_schema.json").write_text(json.dumps(schema))
            write_model_manifest(model_dir)

            result = predict_coverage_percentages(self.features, model_dir=model_dir)

        self.assertEqual(list(result.columns), ["model_predicted_percentage"])
        self.assertIn(result["model_predicted_percentage"].dtype.kind, "iu")
        self.assertTrue(result["model_predicted_percentage"].between(0, 100).all())

    def test_invalid_endpoint_threshold_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "endpoint_threshold"):
            self.model.predict_with_threshold(self.features, 0.49)

    def test_blend_combines_and_bounds_component_predictions(self) -> None:
        baseline = DummyRegressor(strategy="constant", constant=-10).fit(self.features, self.target)
        specialist = DummyRegressor(strategy="constant", constant=120).fit(self.features, self.target)
        model = PercentageModelBlend(baseline, specialist, specialist_weight=0.5)

        predictions = model.predict(self.features)

        np.testing.assert_array_equal(predictions, np.full(len(self.features), 55.0))

    def test_weighted_ensemble_normalizes_weights(self) -> None:
        low = DummyRegressor(strategy="constant", constant=20).fit(self.features, self.target)
        high = DummyRegressor(strategy="constant", constant=80).fit(self.features, self.target)
        model = WeightedPercentageEnsemble((low, high), (1.0, 3.0))

        predictions = model.predict(self.features)

        np.testing.assert_array_equal(predictions, np.full(len(self.features), 65.0))

    def test_weighted_ensemble_falls_back_on_large_disagreement(self) -> None:
        baseline = DummyRegressor(strategy="constant", constant=20).fit(self.features, self.target)
        specialist = DummyRegressor(strategy="constant", constant=80).fit(self.features, self.target)
        model = WeightedPercentageEnsemble(
            (baseline, specialist),
            (0.25, 0.75),
            fallback_model_index=0,
            disagreement_threshold=20,
        )

        predictions = model.predict(self.features)

        np.testing.assert_array_equal(predictions, np.full(len(self.features), 20.0))

    def test_stacked_ensemble_uses_component_predictions(self) -> None:
        low = DummyRegressor(strategy="constant", constant=20).fit(self.features, self.target)
        high = DummyRegressor(strategy="constant", constant=80).fit(self.features, self.target)
        meta_model = LinearRegression().fit(np.array([[20, 80], [40, 60]]), np.array([50, 50]))
        model = StackedPercentageEnsemble((low, high), meta_model)

        predictions = model.predict(self.features)

        np.testing.assert_allclose(predictions, np.full(len(self.features), 50.0))


if __name__ == "__main__":
    unittest.main()

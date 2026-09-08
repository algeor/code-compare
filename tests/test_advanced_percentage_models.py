from __future__ import annotations

import unittest

from pr_suggestion_metrics.train_advanced_percentage_models import (
    DEFAULT_BASELINE_SCHEMA,
    resolve_baseline_schema,
)


class ResolveBaselineSchemaTest(unittest.TestCase):
    def test_legacy_ensemble_uses_known_random_forest_fallback(self) -> None:
        schema = {"model_name": "weighted_percentage_ensemble"}

        self.assertEqual(resolve_baseline_schema(schema), DEFAULT_BASELINE_SCHEMA)

    def test_ensemble_preserves_embedded_baseline_configuration(self) -> None:
        baseline = {
            "model_name": "extra_trees",
            "model_parameters": {"min_samples_leaf": 4},
            "weight_profile": {"hf_scale": 0.5},
        }
        schema = {
            "model_name": "weighted_percentage_ensemble",
            "baseline_component": baseline,
        }

        self.assertIs(resolve_baseline_schema(schema), baseline)


if __name__ == "__main__":
    unittest.main()

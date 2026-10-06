from __future__ import annotations

import unittest

import numpy as np

from pr_suggestion_metrics.modeling.common import metrics
from pr_suggestion_metrics.percentages import (
    OBSOLETE_DERIVED_LABEL_FIELDS,
    parse_integer_percentage,
    round_bounded_percentage,
    validate_continuous_percentage,
)


class IntegerPercentageTest(unittest.TestCase):
    def test_parses_integral_values(self) -> None:
        for value, expected in ((0, 0), (100, 100), (42.0, 42), ("73", 73), ("25.0", 25)):
            with self.subTest(value=value):
                self.assertEqual(parse_integer_percentage(value), expected)

    def test_rejects_non_integer_percentages(self) -> None:
        for value in (True, np.bool_(False), 10.5, "10.5", float("nan"), float("inf"), -1, 101):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_integer_percentage(value)


class ContinuousPercentageTest(unittest.TestCase):
    def test_accepts_finite_values_in_range(self) -> None:
        for value, expected in ((0, 0.0), (37.5, 37.5), ("100", 100.0)):
            with self.subTest(value=value):
                self.assertEqual(validate_continuous_percentage(value), expected)

    def test_rejects_invalid_continuous_values(self) -> None:
        for value in (True, float("nan"), float("inf"), -0.1, 100.1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_continuous_percentage(value)


class BoundedRoundingTest(unittest.TestCase):
    def test_clips_then_uses_ties_to_even_rounding(self) -> None:
        values = np.array([-10.0, 0.5, 1.5, 98.5, 99.5, 110.0])

        rounded = round_bounded_percentage(values)

        np.testing.assert_array_equal(rounded, np.array([0, 0, 2, 98, 100, 100]))
        self.assertEqual(round_bounded_percentage(42.6), 43)

    def test_model_metrics_use_shared_bounded_rounding(self) -> None:
        result = metrics(np.array([0.0, 2.0, 100.0]), np.array([-0.6, 1.5, 100.6]))

        self.assertEqual(result["percentage_mae"], 0.0)
        self.assertEqual(result["percentage_rmse"], 0.0)


class LabelPolicyTest(unittest.TestCase):
    def test_obsolete_derived_fields_are_centralized(self) -> None:
        self.assertEqual(
            OBSOLETE_DERIVED_LABEL_FIELDS,
            frozenset({"label", "expected_percentage_bucket", "suggested_label"}),
        )


if __name__ == "__main__":
    unittest.main()

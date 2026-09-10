from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pr_suggestion_metrics.uncertainty import (
    UncertaintyCalibration,
    apply_conformal_intervals,
    conformal_residual_quantile,
    load_uncertainty_calibration,
)


class UncertaintyTest(unittest.TestCase):
    def test_finite_sample_quantile_and_bounds(self) -> None:
        actual = np.array([0, 10, 20, 30, 40], dtype=float)
        predicted = np.array([0, 8, 24, 35, 30], dtype=float)

        quantile = conformal_residual_quantile(actual, predicted, alpha=0.2)
        intervals = apply_conformal_intervals([2, 50, 98], quantile)

        self.assertEqual(quantile, 10.0)
        np.testing.assert_array_equal(intervals, np.array([[0, 12], [40, 60], [88, 100]], dtype=float))

    def test_calibration_rejects_model_hash_mismatch(self) -> None:
        source_model_dir = Path(__file__).resolve().parents[1] / "models" / "pr_suggestion_coverage_regression"
        with tempfile.TemporaryDirectory() as temporary_directory:
            calibration_path = Path(temporary_directory) / "calibration.json"
            calibration = UncertaintyCalibration(
                created_at_utc="2026-01-01T00:00:00Z",
                alpha=0.1,
                residual_quantile=12.0,
                calibration_rows=100,
                calibration_groups=20,
                target_column="coverage_percentage",
                group_column="group_id",
                calibration_data_sha256="a" * 64,
                model_sha256="b" * 64,
                schema_sha256="c" * 64,
            )
            calibration_path.write_text(json.dumps(calibration.model_dump(mode="json")), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match the model artifact"):
                load_uncertainty_calibration(source_model_dir, calibration_path)


if __name__ == "__main__":
    unittest.main()

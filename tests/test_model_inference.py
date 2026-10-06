from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from pr_suggestion_metrics.model_inference import _percentage_prediction_frame


_SCHEMA = {
    "numeric_features": ["candidate_hunk_count"],
    "boolean_features": [],
    "categorical_features": [],
    "feature_columns": ["candidate_hunk_count"],
}


def test_prediction_frame_uses_shared_rounding_and_preserves_clipped_raw_values() -> None:
    model = Mock()
    model.predict.return_value = [-2.4, 101.2]
    rounded = np.array([7, 8])

    with (
        patch("pr_suggestion_metrics.model_inference.load_model_bundle", return_value=(model, _SCHEMA)),
        patch("pr_suggestion_metrics.model_inference.round_bounded_percentage", return_value=rounded) as round_shared,
    ):
        result = _percentage_prediction_frame(
            [{"candidate_hunk_count": 1}, {"candidate_hunk_count": 2}],
            model_dir=Path("unused"),
        )

    np.testing.assert_array_equal(result["model_raw_percentage"].to_numpy(), np.array([0.0, 100.0]))
    np.testing.assert_array_equal(result["model_predicted_percentage"].to_numpy(), rounded)
    np.testing.assert_array_equal(round_shared.call_args.args[0], np.array([-2.4, 101.2]))


def test_prediction_frame_rejects_non_vector_model_output() -> None:
    model = Mock()
    model.predict.return_value = [[42.0]]

    with patch("pr_suggestion_metrics.model_inference.load_model_bundle", return_value=(model, _SCHEMA)):
        with pytest.raises(ValueError, match="one-dimensional array"):
            _percentage_prediction_frame([{"candidate_hunk_count": 1}], model_dir=Path("unused"))

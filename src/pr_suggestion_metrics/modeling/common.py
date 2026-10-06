"""Shared feature definitions and percentage metrics for supported training."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from pr_suggestion_metrics.percentages import round_bounded_percentage


NUMERIC_FEATURES = [
    "line_recall",
    "token_recall",
    "identifier_normalized_token_recall",
    "literal_normalized_token_recall",
    "identifier_and_literal_normalized_token_recall",
    "best_added_line_overlap",
    "best_hunk_token_recall",
    "best_hunk_token_precision",
    "best_hunk_token_f1",
    "best_hunk_identifier_normalized_recall",
    "best_hunk_literal_normalized_recall",
    "best_hunk_identifier_and_literal_normalized_recall",
    "best_hunk_contiguous_line_ratio",
    "best_hunk_token_lcs_recall",
    "best_hunk_size_ratio",
    "meaningful_anchor_recall",
    "meaningful_anchor_count",
    "best_hunk_size",
    "candidate_hunk_count",
    "structural_similarity",
    "structural_node_recall",
    "gumtree_operation_count",
    "gumtree_insert_ratio",
    "gumtree_delete_ratio",
    "gumtree_update_ratio",
    "gumtree_move_ratio",
    "file_overlap_ratio",
    "changed_line_overlap_ratio",
]
BOOLEAN_FEATURES = ["exact_normalized_match", "structural_available", "gumtree_available"]
CATEGORICAL_FEATURES = [
    "suggestion_language",
    "tokenizer",
    "best_hunk_candidate_type",
    "structural_engine",
    "structural_language",
]


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    bounded_predictions = round_bounded_percentage(np.asarray(predicted, dtype=float))
    actual_values = np.asarray(actual, dtype=float)
    return {
        "percentage_mae": float(mean_absolute_error(actual_values, bounded_predictions)),
        "percentage_rmse": float(mean_squared_error(actual_values, bounded_predictions) ** 0.5),
        "r2": float(r2_score(actual_values, bounded_predictions)),
        "within_5_points": float(np.mean(np.abs(actual_values - bounded_predictions) <= 5)),
        "within_10_points": float(np.mean(np.abs(actual_values - bounded_predictions) <= 10)),
        "dangerous_error_rate": float(
            np.mean(
                ((bounded_predictions >= 80) & (actual_values <= 20))
                | ((bounded_predictions <= 20) & (actual_values >= 80))
            )
        ),
    }

from __future__ import annotations

import csv
import json
from pathlib import Path

from pr_suggestion_metrics.model_inference import predict_coverage_percentages
from pr_suggestion_metrics.modeling.train import train_from_frozen_features


def test_trainer_uses_train_and_development_but_reserves_calibration(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    rows = []
    for index in range(12):
        split = "train" if index < 8 else "development" if index < 10 else "calibration"
        rows.append(
            {
                "example_id": f"example-{index}",
                "group_id": f"pr-{index}",
                "split": split,
                "coverage_percentage": index * 8,
                "line_recall": index / 11,
                "token_recall": (11 - index) / 11,
                "exact_normalized_match": index % 2 == 0,
                "suggestion_language": "python" if index % 2 else "go",
                "file_overlap_ratio": 1.0,
                "gumtree_operation_count": 0,
            }
        )
    with features_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"candidates": ["random_forest"], "random_state": 7}))
    model_dir = tmp_path / "model"

    report = train_from_frozen_features(
        features_path=features_path,
        model_dir=model_dir,
        config_path=config_path,
    )
    predictions = predict_coverage_percentages(rows[:1], model_dir=model_dir)

    assert report["calibration_rows_reserved"] == 2
    assert "file_overlap_ratio" not in report["feature_columns"]
    assert "gumtree_operation_count" not in report["feature_columns"]
    assert predictions["model_predicted_percentage"].between(0, 100).all()

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

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
                "normalization_policy_version": "1.0",
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
    schema = json.loads((model_dir / "feature_schema.json").read_text(encoding="utf-8"))

    assert report["calibration_rows_reserved"] == 2
    assert report["normalization_policy_version"] == "1.0"
    assert schema["schema_version"] == "1.1"
    assert schema["normalization_policy_version"] == "1.0"
    assert "file_overlap_ratio" not in report["feature_columns"]
    assert "gumtree_operation_count" not in report["feature_columns"]
    assert predictions["model_predicted_percentage"].between(0, 100).all()


def test_trainer_rejects_groups_shared_across_splits(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    rows = [
        {
            "example_id": "train-example",
            "group_id": "shared-pr",
            "split": "train",
            "coverage_percentage": 10,
            "normalization_policy_version": "1.0",
            "line_recall": 0.1,
        },
        {
            "example_id": "development-example",
            "group_id": "shared-pr",
            "split": "development",
            "coverage_percentage": 90,
            "normalization_policy_version": "1.0",
            "line_recall": 0.9,
        },
    ]
    with features_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    try:
        train_from_frozen_features(features_path=features_path, model_dir=tmp_path / "model")
    except ValueError as exc:
        assert "must not cross dataset splits" in str(exc)
    else:
        raise AssertionError("Expected cross-split group leakage to be rejected")


def test_trainer_rejects_out_of_range_targets(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    features_path.write_text(
        "group_id,split,coverage_percentage,normalization_policy_version,line_recall\n"
        "train-pr,train,-1,1.0,0.1\n"
        "development-pr,development,50,1.0,0.9\n",
        encoding="utf-8",
    )

    try:
        train_from_frozen_features(features_path=features_path, model_dir=tmp_path / "model")
    except ValueError as exc:
        assert "finite and between 0 and 100" in str(exc)
    else:
        raise AssertionError("Expected invalid targets to be rejected")


def test_trainer_rejects_incompatible_normalization_policy(tmp_path: Path) -> None:
    features_path = tmp_path / "features.csv"
    features_path.write_text(
        "group_id,split,coverage_percentage,normalization_policy_version,line_recall\n"
        "train-pr,train,10,0.9,0.1\n"
        "development-pr,development,50,0.9,0.9\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="normalization_policy_version"):
        train_from_frozen_features(features_path=features_path, model_dir=tmp_path / "model")

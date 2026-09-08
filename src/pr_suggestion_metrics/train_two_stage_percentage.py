"""Benchmark and conditionally deploy a two-stage CatBoost percentage model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from pr_suggestion_metrics.train_percentage_regressor import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    RANDOM_STATE,
    metrics,
    prepare_features,
    read_source,
    training_weights,
)
from pr_suggestion_metrics.two_stage_percentage import TwoStageCatBoostRegressor


ENDPOINT_THRESHOLDS = (0.55, 0.7, 0.85)
WEIGHT_PROFILES = (
    {"hf_scale": 1.1, "confidence_floor": 0.0, "internal_scale": 1.0, "minority_scale": 1.0},
    {"hf_scale": 0.9, "confidence_floor": 0.25, "internal_scale": 1.0, "minority_scale": 1.0},
    {"hf_scale": 0.85, "confidence_floor": 0.5, "internal_scale": 1.0, "minority_scale": 1.0},
)
MODEL_PARAMETERS = (
    {"iterations": 250, "depth": 4, "learning_rate": 0.05, "l2_leaf_reg": 5.0, "auto_class_weights": None},
    {"iterations": 400, "depth": 4, "learning_rate": 0.03, "l2_leaf_reg": 7.0, "auto_class_weights": None},
    {"iterations": 300, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 5.0, "auto_class_weights": None},
    {"iterations": 400, "depth": 6, "learning_rate": 0.025, "l2_leaf_reg": 10.0, "auto_class_weights": None},
    {"iterations": 300, "depth": 5, "learning_rate": 0.04, "l2_leaf_reg": 7.0, "auto_class_weights": "SqrtBalanced"},
)


def make_model(parameters: dict[str, Any], endpoint_threshold: float = 0.7) -> TwoStageCatBoostRegressor:
    return TwoStageCatBoostRegressor(
        categorical_features=tuple(CATEGORICAL_FEATURES),
        endpoint_threshold=endpoint_threshold,
        random_state=RANDOM_STATE,
        **parameters,
    )


def average_metrics(fold_metrics: list[dict[str, float]]) -> dict[str, float]:
    return {name: float(np.mean([result[name] for result in fold_metrics])) for name in fold_metrics[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-scores", type=Path, required=True)
    parser.add_argument("--internal-labels", type=Path, required=True)
    parser.add_argument("--hf-scores", type=Path, required=True)
    parser.add_argument("--hf-labels", type=Path, required=True)
    parser.add_argument("--hf-audit", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()

    internal = prepare_features(read_source("internal", args.internal_scores, args.internal_labels))
    hf = prepare_features(read_source("hf_github_codereview", args.hf_scores, args.hf_labels, args.hf_audit))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    dev_positions, test_positions = next(splitter.split(internal, groups=internal["group_id"]))
    internal_dev = internal.iloc[dev_positions].copy()
    internal_test = internal.iloc[test_positions].copy()

    baseline_model = joblib.load(args.model_dir / "model.joblib")
    actual_test = internal_test["expected_landed_percentage"].to_numpy()
    baseline_metrics = metrics(actual_test, baseline_model.predict(internal_test[FEATURE_COLUMNS]))

    folds = GroupKFold(n_splits=4)
    tuning_results: list[dict[str, Any]] = []
    for parameters in MODEL_PARAMETERS:
        for weight_profile in WEIGHT_PROFILES:
            threshold_metrics: dict[float, list[dict[str, float]]] = {
                threshold: [] for threshold in ENDPOINT_THRESHOLDS
            }
            for train_positions, validation_positions in folds.split(internal_dev, groups=internal_dev["group_id"]):
                train_rows = pd.concat([internal_dev.iloc[train_positions], hf], ignore_index=True)
                validation_rows = internal_dev.iloc[validation_positions]
                model = make_model(parameters)
                model.fit(
                    train_rows[FEATURE_COLUMNS],
                    train_rows["expected_landed_percentage"],
                    sample_weight=training_weights(train_rows, weight_profile),
                )
                for threshold in ENDPOINT_THRESHOLDS:
                    predictions = model.predict_with_threshold(validation_rows[FEATURE_COLUMNS], threshold)
                    threshold_metrics[threshold].append(
                        metrics(validation_rows["expected_landed_percentage"].to_numpy(), predictions)
                    )
            for threshold, fold_results in threshold_metrics.items():
                tuning_results.append(
                    {
                        "parameters": parameters,
                        "weight_profile": weight_profile,
                        "endpoint_threshold": threshold,
                        "cv_internal": average_metrics(fold_results),
                    }
                )

    tuning_results.sort(
        key=lambda result: (
            result["cv_internal"]["percentage_mae"],
            result["cv_internal"]["dangerous_error_rate"],
            result["cv_internal"]["percentage_rmse"],
        )
    )
    selected = tuning_results[0]
    final_train = pd.concat([internal_dev, hf], ignore_index=True)
    model = make_model(selected["parameters"], selected["endpoint_threshold"])
    model.fit(
        final_train[FEATURE_COLUMNS],
        final_train["expected_landed_percentage"],
        sample_weight=training_weights(final_train, selected["weight_profile"]),
    )
    tuned_metrics = metrics(actual_test, model.predict(internal_test[FEATURE_COLUMNS]))

    deployment_checks = {
        "mae_improved": tuned_metrics["percentage_mae"] < baseline_metrics["percentage_mae"],
        "rmse_not_worse": tuned_metrics["percentage_rmse"] <= baseline_metrics["percentage_rmse"],
        "dangerous_error_not_worse": tuned_metrics["dangerous_error_rate"] <= baseline_metrics["dangerous_error_rate"],
    }
    deploy = all(deployment_checks.values())
    report = {
        "objective": "improve percentage accuracy with endpoint classification plus intermediate regression",
        "architecture": {
            "stage_1": "CatBoost three-regime classifier: 0, intermediate, 100",
            "stage_2": "CatBoost regressor trained only on 1-99 percentages",
            "output": "probability-weighted 0-100 percentage with high-confidence endpoint routing",
        },
        "internal_dev_rows": len(internal_dev),
        "internal_test_rows": len(internal_test),
        "hf_rows": len(hf),
        "selected": selected,
        "baseline_model": baseline_metrics,
        "two_stage_model": tuned_metrics,
        "improvement_vs_baseline_mae": baseline_metrics["percentage_mae"] - tuned_metrics["percentage_mae"],
        "deployment_checks": deployment_checks,
        "artifact_decision": "saved_two_stage_model" if deploy else "kept_existing_baseline",
        "top_tuning_results": tuning_results[:15],
    }

    args.model_dir.mkdir(parents=True, exist_ok=True)
    (args.model_dir / "two_stage_evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if deploy:
        joblib.dump(model, args.model_dir / "model.joblib")
        schema = {
            "model_name": "two_stage_catboost",
            "model_parameters": selected["parameters"],
            "weight_profile": selected["weight_profile"],
            "endpoint_threshold": selected["endpoint_threshold"],
            "selection_policy": "lowest grouped internal CV percentage MAE; deploy only when holdout MAE and RMSE improve without increasing dangerous errors",
            "prediction_type": "percentage_regression",
            "prediction_output": "0-100 integer percentage",
            "numeric_features": NUMERIC_FEATURES,
            "boolean_features": BOOLEAN_FEATURES,
            "categorical_features": CATEGORICAL_FEATURES,
            "feature_columns": FEATURE_COLUMNS,
        }
        (args.model_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
        (args.model_dir / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

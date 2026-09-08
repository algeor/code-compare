"""Tune and conditionally deploy an out-of-fold percentage-model blend."""

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
    fit,
    make_pipeline,
    metrics,
    prepare_features,
    read_source,
    training_weights,
)
from pr_suggestion_metrics.train_two_stage_percentage import make_model as make_two_stage_model
from pr_suggestion_metrics.two_stage_percentage import PercentageModelBlend


BLEND_WEIGHTS = tuple(float(round(value, 2)) for value in np.linspace(0.0, 1.0, 21))
GROUP_SPLIT_SEEDS = (17, 42, 83)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fit_components(
    rows: pd.DataFrame,
    baseline_schema: dict[str, Any],
    two_stage_selection: dict[str, Any],
) -> tuple[Any, Any]:
    baseline_model = fit(
        make_pipeline(baseline_schema["model_name"], baseline_schema["model_parameters"]),
        rows,
        baseline_schema["weight_profile"],
    )
    specialist_model = make_two_stage_model(
        two_stage_selection["parameters"],
        two_stage_selection["endpoint_threshold"],
    )
    specialist_model.fit(
        rows[FEATURE_COLUMNS],
        rows["expected_landed_percentage"],
        sample_weight=training_weights(rows, two_stage_selection["weight_profile"]),
    )
    return baseline_model, specialist_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-scores", type=Path, required=True)
    parser.add_argument("--internal-labels", type=Path, required=True)
    parser.add_argument("--hf-scores", type=Path, required=True)
    parser.add_argument("--hf-labels", type=Path, required=True)
    parser.add_argument("--hf-audit", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--two-stage-report", type=Path)
    args = parser.parse_args()

    internal = prepare_features(read_source("internal", args.internal_scores, args.internal_labels))
    hf = prepare_features(read_source("hf_github_codereview", args.hf_scores, args.hf_labels, args.hf_audit))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    dev_positions, test_positions = next(splitter.split(internal, groups=internal["group_id"]))
    internal_dev = internal.iloc[dev_positions].reset_index(drop=True)
    internal_test = internal.iloc[test_positions].copy()

    baseline_schema = load_json(args.model_dir / "feature_schema.json")
    if baseline_schema["model_name"] not in {"extra_trees", "random_forest", "gradient_boosting"}:
        raise ValueError("ensemble training requires a deployed single-stage baseline model")
    two_stage_report_path = args.two_stage_report or args.model_dir / "two_stage_evaluation_report.json"
    two_stage_selection = load_json(two_stage_report_path)["selected"]

    prediction_sums = {
        "baseline": np.zeros(len(internal_dev), dtype=float),
        "specialist": np.zeros(len(internal_dev), dtype=float),
    }
    prediction_counts = np.zeros(len(internal_dev), dtype=int)
    for seed in GROUP_SPLIT_SEEDS:
        folds = GroupKFold(n_splits=4, shuffle=True, random_state=seed)
        for train_positions, validation_positions in folds.split(internal_dev, groups=internal_dev["group_id"]):
            train_rows = pd.concat([internal_dev.iloc[train_positions], hf], ignore_index=True)
            baseline_model, specialist_model = fit_components(train_rows, baseline_schema, two_stage_selection)
            validation_features = internal_dev.iloc[validation_positions][FEATURE_COLUMNS]
            prediction_sums["baseline"][validation_positions] += baseline_model.predict(validation_features)
            prediction_sums["specialist"][validation_positions] += specialist_model.predict(validation_features)
            prediction_counts[validation_positions] += 1

    if np.any(prediction_counts == 0):
        raise RuntimeError("grouped out-of-fold predictions did not cover every internal development row")
    baseline_oof = prediction_sums["baseline"] / prediction_counts
    specialist_oof = prediction_sums["specialist"] / prediction_counts
    actual_dev = internal_dev["expected_landed_percentage"].to_numpy()
    baseline_oof_metrics = metrics(actual_dev, baseline_oof)
    specialist_oof_metrics = metrics(actual_dev, specialist_oof)

    blend_results = []
    for specialist_weight in BLEND_WEIGHTS:
        predictions = (1.0 - specialist_weight) * baseline_oof + specialist_weight * specialist_oof
        blend_results.append(
            {
                "specialist_weight": specialist_weight,
                **metrics(actual_dev, predictions),
            }
        )
    eligible_results = [
        result
        for result in blend_results
        if result["percentage_rmse"] <= baseline_oof_metrics["percentage_rmse"]
        and result["dangerous_error_rate"] <= baseline_oof_metrics["dangerous_error_rate"]
    ]
    selected = min(
        eligible_results,
        key=lambda result: (
            result["percentage_mae"],
            result["percentage_rmse"],
            -result["within_5_points"],
        ),
    )

    final_train = pd.concat([internal_dev, hf], ignore_index=True)
    baseline_component, specialist_component = fit_components(final_train, baseline_schema, two_stage_selection)
    ensemble_model = PercentageModelBlend(
        baseline_component,
        specialist_component,
        selected["specialist_weight"],
    )
    deployed_model = joblib.load(args.model_dir / "model.joblib")
    test_features = internal_test[FEATURE_COLUMNS]
    actual_test = internal_test["expected_landed_percentage"].to_numpy()
    baseline_metrics = metrics(actual_test, deployed_model.predict(test_features))
    ensemble_metrics = metrics(actual_test, ensemble_model.predict(test_features))
    deployment_checks = {
        "uses_both_models": bool(0.0 < selected["specialist_weight"] < 1.0),
        "mae_improved": ensemble_metrics["percentage_mae"] < baseline_metrics["percentage_mae"],
        "rmse_improved": ensemble_metrics["percentage_rmse"] < baseline_metrics["percentage_rmse"],
        "dangerous_error_not_worse": ensemble_metrics["dangerous_error_rate"] <= baseline_metrics["dangerous_error_rate"],
    }
    deploy = all(deployment_checks.values())
    report = {
        "objective": "combine complementary single-stage and two-stage percentage predictions",
        "validation": "three repetitions of four-fold PR-grouped out-of-fold evaluation",
        "internal_dev_rows": len(internal_dev),
        "internal_test_rows": len(internal_test),
        "hf_rows": len(hf),
        "baseline_component": {
            "model_name": baseline_schema["model_name"],
            "model_parameters": baseline_schema["model_parameters"],
            "weight_profile": baseline_schema["weight_profile"],
            "oof_metrics": baseline_oof_metrics,
        },
        "specialist_component": {
            **two_stage_selection,
            "oof_metrics": specialist_oof_metrics,
        },
        "selected_blend": selected,
        "baseline_model": baseline_metrics,
        "ensemble_model": ensemble_metrics,
        "improvement_vs_baseline_mae": baseline_metrics["percentage_mae"] - ensemble_metrics["percentage_mae"],
        "deployment_checks": deployment_checks,
        "artifact_decision": "saved_ensemble_model" if deploy else "kept_existing_baseline",
        "blend_results": blend_results,
    }

    args.model_dir.mkdir(parents=True, exist_ok=True)
    (args.model_dir / "ensemble_evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if deploy:
        joblib.dump(ensemble_model, args.model_dir / "model.joblib")
        schema = {
            "model_name": "random_forest_two_stage_catboost_blend",
            "baseline_component": report["baseline_component"],
            "specialist_component": two_stage_selection,
            "specialist_weight": selected["specialist_weight"],
            "selection_policy": "repeated grouped OOF blend; deploy only when holdout MAE and RMSE improve without increasing dangerous errors",
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

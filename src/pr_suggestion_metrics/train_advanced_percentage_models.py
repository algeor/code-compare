"""Compare robust tabular regressors and build an out-of-fold ensemble."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

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
from pr_suggestion_metrics.two_stage_percentage import StackedPercentageEnsemble, WeightedPercentageEnsemble


GROUP_SPLIT_SEEDS = (17, 42, 83)
ENSEMBLE_WEIGHT_STEPS = 10
DISAGREEMENT_THRESHOLDS: tuple[float | None, ...] = (10.0, 20.0, 30.0, 40.0, None)
STACKING_ALPHAS = (0.1, 1.0, 10.0, 100.0)
MIN_BASELINE_WEIGHT = 0.5
MAX_RMSE_REGRESSION_RATIO = 0.02
DEFAULT_BASELINE_SCHEMA = {
    "model_name": "random_forest",
    "model_parameters": {
        "min_samples_leaf": 7,
        "max_features": 0.8,
    },
    "weight_profile": {
        "hf_scale": 1.1,
        "confidence_floor": 0.0,
        "internal_scale": 1.0,
        "minority_scale": 1.0,
    },
}


def resolve_baseline_schema(deployed_schema: dict[str, Any]) -> dict[str, Any]:
    if deployed_schema["model_name"] in {"extra_trees", "random_forest", "gradient_boosting"}:
        return deployed_schema
    return deployed_schema.get("baseline_component", DEFAULT_BASELINE_SCHEMA)


def candidate_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "catboost_mae",
            "family": "catboost",
            "parameters": {"loss_function": "MAE", "iterations": 400, "depth": 6, "learning_rate": 0.03, "l2_leaf_reg": 7.0},
        },
        {
            "name": "catboost_huber",
            "family": "catboost",
            "parameters": {"loss_function": "Huber:delta=10", "iterations": 400, "depth": 6, "learning_rate": 0.03, "l2_leaf_reg": 7.0},
        },
        {
            "name": "lightgbm_l1",
            "family": "lightgbm",
            "parameters": {"objective": "regression_l1", "n_estimators": 400, "num_leaves": 15, "learning_rate": 0.03, "min_child_samples": 15},
        },
        {
            "name": "lightgbm_huber",
            "family": "lightgbm",
            "parameters": {"objective": "huber", "n_estimators": 400, "num_leaves": 15, "learning_rate": 0.03, "min_child_samples": 15},
        },
        {
            "name": "xgboost_l1",
            "family": "xgboost",
            "parameters": {"objective": "reg:absoluteerror", "n_estimators": 400, "max_depth": 4, "learning_rate": 0.03, "min_child_weight": 5.0},
        },
        {
            "name": "xgboost_pseudohuber",
            "family": "xgboost",
            "parameters": {"objective": "reg:pseudohubererror", "n_estimators": 400, "max_depth": 4, "learning_rate": 0.03, "min_child_weight": 5.0},
        },
    ]


def tabular_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("numeric", SimpleImputer(strategy="median"), NUMERIC_FEATURES + BOOLEAN_FEATURES),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="constant", fill_value="none")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ]
    )


def make_candidate(specification: dict[str, Any]) -> Any:
    parameters = dict(specification["parameters"])
    family = specification["family"]
    if family == "catboost":
        return CatBoostRegressor(
            **parameters,
            eval_metric="MAE",
            random_seed=RANDOM_STATE,
            thread_count=-1,
            verbose=False,
            allow_writing_files=False,
        )
    if family == "lightgbm":
        estimator = LGBMRegressor(
            **parameters,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=-1,
        )
    elif family == "xgboost":
        estimator = XGBRegressor(
            **parameters,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            tree_method="hist",
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=5.0,
        )
    else:
        raise ValueError(f"unsupported model family: {family}")
    return Pipeline([("preprocessor", tabular_preprocessor()), ("regressor", estimator)])


def fit_candidate(model: Any, specification: dict[str, Any], rows: pd.DataFrame, weights: np.ndarray) -> Any:
    if specification["family"] == "catboost":
        model.fit(
            rows[FEATURE_COLUMNS],
            rows["expected_landed_percentage"],
            cat_features=CATEGORICAL_FEATURES,
            sample_weight=weights,
        )
    else:
        model.fit(
            rows[FEATURE_COLUMNS],
            rows["expected_landed_percentage"],
            regressor__sample_weight=weights,
        )
    return model


def simplex_weights(component_count: int, steps: int) -> list[tuple[float, ...]]:
    combinations = []
    for dividers in itertools.combinations(range(steps + component_count - 1), component_count - 1):
        boundaries = (-1, *dividers, steps + component_count - 1)
        counts = tuple(boundaries[index + 1] - boundaries[index] - 1 for index in range(component_count))
        combinations.append(tuple(count / steps for count in counts))
    return combinations


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
    internal_dev = internal.iloc[dev_positions].reset_index(drop=True)
    internal_test = internal.iloc[test_positions].copy()

    deployed_schema = json.loads((args.model_dir / "feature_schema.json").read_text())
    baseline_schema = resolve_baseline_schema(deployed_schema)
    two_stage_selection = json.loads((args.model_dir / "two_stage_evaluation_report.json").read_text())["selected"]
    weight_profile = baseline_schema["weight_profile"]
    specifications = candidate_specs()
    prediction_sums = {
        "baseline": np.zeros(len(internal_dev), dtype=float),
        "two_stage": np.zeros(len(internal_dev), dtype=float),
        **{specification["name"]: np.zeros(len(internal_dev), dtype=float) for specification in specifications},
    }
    prediction_counts = np.zeros(len(internal_dev), dtype=int)

    for seed in GROUP_SPLIT_SEEDS:
        folds = GroupKFold(n_splits=4, shuffle=True, random_state=seed)
        for train_positions, validation_positions in folds.split(internal_dev, groups=internal_dev["group_id"]):
            train_rows = pd.concat([internal_dev.iloc[train_positions], hf], ignore_index=True)
            validation_features = internal_dev.iloc[validation_positions][FEATURE_COLUMNS]
            weights = training_weights(train_rows, weight_profile)

            baseline_model = fit(
                make_pipeline(baseline_schema["model_name"], baseline_schema["model_parameters"]),
                train_rows,
                weight_profile,
            )
            prediction_sums["baseline"][validation_positions] += baseline_model.predict(validation_features)

            two_stage_model = make_two_stage_model(
                two_stage_selection["parameters"],
                two_stage_selection["endpoint_threshold"],
            )
            two_stage_model.fit(
                train_rows[FEATURE_COLUMNS],
                train_rows["expected_landed_percentage"],
                sample_weight=training_weights(train_rows, two_stage_selection["weight_profile"]),
            )
            prediction_sums["two_stage"][validation_positions] += two_stage_model.predict(validation_features)

            for specification in specifications:
                candidate = fit_candidate(make_candidate(specification), specification, train_rows, weights)
                prediction_sums[specification["name"]][validation_positions] += candidate.predict(validation_features)
            prediction_counts[validation_positions] += 1

    if np.any(prediction_counts == 0):
        raise RuntimeError("repeated grouped validation did not cover every internal development row")
    oof_predictions = {name: values / prediction_counts for name, values in prediction_sums.items()}
    actual_dev = internal_dev["expected_landed_percentage"].to_numpy()
    oof_metrics = {name: metrics(actual_dev, predictions) for name, predictions in oof_predictions.items()}

    selected_by_family = {}
    for family in ("catboost", "lightgbm", "xgboost"):
        family_specs = [specification for specification in specifications if specification["family"] == family]
        selected_by_family[family] = min(
            family_specs,
            key=lambda specification: (
                oof_metrics[specification["name"]]["percentage_mae"],
                oof_metrics[specification["name"]]["percentage_rmse"],
            ),
        )

    component_names = ["baseline", "two_stage", *[selected_by_family[family]["name"] for family in selected_by_family]]
    baseline_oof_metrics = oof_metrics["baseline"]
    blend_results = []
    for weights in simplex_weights(len(component_names), ENSEMBLE_WEIGHT_STEPS):
        if sum(weight > 0 for weight in weights) < 2:
            continue
        if weights[component_names.index("baseline")] < MIN_BASELINE_WEIGHT:
            continue
        blended_predictions = sum(
            weight * oof_predictions[name]
            for name, weight in zip(component_names, weights, strict=True)
        )
        for disagreement_threshold in DISAGREEMENT_THRESHOLDS:
            predictions = blended_predictions
            if disagreement_threshold is not None:
                use_fallback = np.abs(blended_predictions - oof_predictions["baseline"]) > disagreement_threshold
                predictions = np.where(use_fallback, oof_predictions["baseline"], blended_predictions)
            blend_results.append(
                {
                    "weights": dict(zip(component_names, weights, strict=True)),
                    "disagreement_threshold": disagreement_threshold,
                    **metrics(actual_dev, predictions),
                }
            )
    eligible_blends = [
        result
        for result in blend_results
        if result["percentage_rmse"] <= baseline_oof_metrics["percentage_rmse"]
        and result["dangerous_error_rate"] <= baseline_oof_metrics["dangerous_error_rate"]
    ]
    selected_blend = min(
        eligible_blends,
        key=lambda result: (
            result["percentage_mae"],
            result["percentage_rmse"],
            -result["within_5_points"],
        ),
    )

    stacking_features = np.column_stack([oof_predictions[name] for name in component_names])
    stacking_results = []
    for alpha in STACKING_ALPHAS:
        prediction_sum = np.zeros(len(internal_dev), dtype=float)
        prediction_count = np.zeros(len(internal_dev), dtype=int)
        for seed in GROUP_SPLIT_SEEDS:
            folds = GroupKFold(n_splits=4, shuffle=True, random_state=seed)
            for train_positions, validation_positions in folds.split(internal_dev, groups=internal_dev["group_id"]):
                meta_model = Ridge(alpha=alpha, positive=True)
                meta_model.fit(stacking_features[train_positions], actual_dev[train_positions])
                prediction_sum[validation_positions] += meta_model.predict(stacking_features[validation_positions])
                prediction_count[validation_positions] += 1
        predictions = prediction_sum / prediction_count
        stacking_results.append({"alpha": alpha, **metrics(actual_dev, predictions)})
    eligible_stackers = [
        result
        for result in stacking_results
        if result["percentage_rmse"] <= baseline_oof_metrics["percentage_rmse"]
        and result["dangerous_error_rate"] <= baseline_oof_metrics["dangerous_error_rate"]
    ]
    selected_stacker = min(
        eligible_stackers,
        key=lambda result: (
            result["percentage_mae"],
            result["percentage_rmse"],
            -result["within_5_points"],
        ),
    )
    use_stacker = selected_stacker["percentage_mae"] < selected_blend["percentage_mae"]

    final_train = pd.concat([internal_dev, hf], ignore_index=True)
    final_weights = training_weights(final_train, weight_profile)
    final_models: dict[str, Any] = {}
    final_models["baseline"] = fit(
        make_pipeline(baseline_schema["model_name"], baseline_schema["model_parameters"]),
        final_train,
        weight_profile,
    )
    final_models["two_stage"] = make_two_stage_model(
        two_stage_selection["parameters"],
        two_stage_selection["endpoint_threshold"],
    )
    final_models["two_stage"].fit(
        final_train[FEATURE_COLUMNS],
        final_train["expected_landed_percentage"],
        sample_weight=training_weights(final_train, two_stage_selection["weight_profile"]),
    )
    selected_specs = {specification["name"]: specification for specification in selected_by_family.values()}
    for name, specification in selected_specs.items():
        final_models[name] = fit_candidate(make_candidate(specification), specification, final_train, final_weights)

    active_names = [name for name in component_names if selected_blend["weights"][name] > 0]
    if selected_blend["disagreement_threshold"] is not None and "baseline" not in active_names:
        active_names.insert(0, "baseline")
    convex_model = WeightedPercentageEnsemble(
        models=tuple(final_models[name] for name in active_names),
        weights=tuple(selected_blend["weights"][name] for name in active_names),
        fallback_model_index=active_names.index("baseline") if selected_blend["disagreement_threshold"] is not None else None,
        disagreement_threshold=selected_blend["disagreement_threshold"],
    )
    meta_model = Ridge(alpha=selected_stacker["alpha"], positive=True)
    meta_model.fit(stacking_features, actual_dev)
    stacked_model = StackedPercentageEnsemble(
        models=tuple(final_models[name] for name in component_names),
        meta_model=meta_model,
    )
    ensemble_model = stacked_model if use_stacker else convex_model
    deployed_model = joblib.load(args.model_dir / "model.joblib")
    test_features = internal_test[FEATURE_COLUMNS]
    actual_test = internal_test["expected_landed_percentage"].to_numpy()
    baseline_metrics = metrics(actual_test, deployed_model.predict(test_features))
    component_test_metrics = {
        name: metrics(actual_test, model.predict(test_features))
        for name, model in final_models.items()
    }
    convex_metrics = metrics(actual_test, convex_model.predict(test_features))
    stacked_metrics = metrics(actual_test, stacked_model.predict(test_features))
    ensemble_metrics = metrics(actual_test, ensemble_model.predict(test_features))
    rmse_regression_ratio = (
        ensemble_metrics["percentage_rmse"] - baseline_metrics["percentage_rmse"]
    ) / baseline_metrics["percentage_rmse"]
    deployment_checks = {
        "mae_improved": ensemble_metrics["percentage_mae"] < baseline_metrics["percentage_mae"],
        "rmse_within_2_percent": rmse_regression_ratio <= MAX_RMSE_REGRESSION_RATIO,
        "within_10_not_worse": ensemble_metrics["within_10_points"] >= baseline_metrics["within_10_points"],
        "dangerous_error_not_worse": ensemble_metrics["dangerous_error_rate"] <= baseline_metrics["dangerous_error_rate"],
    }
    deploy = all(deployment_checks.values())
    report = {
        "objective": "compare robust tabular regressors and combine complementary models",
        "research_sources": {
            "catboost_categorical_features": "https://catboost.ai/en/docs/features/categorical-features",
            "xgboost_robust_objectives": "https://xgboost.readthedocs.io/en/stable/parameter.html",
            "lightgbm_robust_objectives": "https://lightgbm.readthedocs.io/en/stable/Parameters.html",
            "stacked_generalization": "https://scikit-learn.org/stable/modules/ensemble.html#stacked-generalization",
        },
        "validation": "three repetitions of four-fold PR-grouped out-of-fold evaluation",
        "internal_dev_rows": len(internal_dev),
        "internal_test_rows": len(internal_test),
        "hf_rows": len(hf),
        "candidate_oof_metrics": oof_metrics,
        "selected_by_family": selected_by_family,
        "selected_blend": selected_blend,
        "stacking_results": stacking_results,
        "selected_stacker": selected_stacker,
        "selected_ensemble_type": "ridge_stacker" if use_stacker else "convex_blend",
        "baseline_model": baseline_metrics,
        "component_test_metrics": component_test_metrics,
        "convex_blend_test_metrics": convex_metrics,
        "ridge_stacker_test_metrics": stacked_metrics,
        "final_ensemble": ensemble_metrics,
        "improvement_vs_baseline_mae": baseline_metrics["percentage_mae"] - ensemble_metrics["percentage_mae"],
        "rmse_regression_ratio": rmse_regression_ratio,
        "deployment_checks": deployment_checks,
        "artifact_decision": "saved_advanced_ensemble" if deploy else "kept_existing_baseline",
    }

    args.model_dir.mkdir(parents=True, exist_ok=True)
    (args.model_dir / "advanced_model_comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    if deploy:
        joblib.dump(ensemble_model, args.model_dir / "model.joblib")
        schema = {
            "model_name": "stacked_percentage_ensemble" if use_stacker else "weighted_percentage_ensemble",
            "components": component_names if use_stacker else active_names,
            "weights": None if use_stacker else {name: selected_blend["weights"][name] for name in active_names},
            "disagreement_threshold": None if use_stacker else selected_blend["disagreement_threshold"],
            "meta_model": {"name": "positive_ridge", "alpha": selected_stacker["alpha"]} if use_stacker else None,
            "baseline_component": {
                "model_name": baseline_schema["model_name"],
                "model_parameters": baseline_schema["model_parameters"],
                "weight_profile": baseline_schema["weight_profile"],
            },
            "selected_by_family": selected_by_family,
            "selection_policy": "repeated grouped OOF ensemble; deploy when holdout MAE and within-10 accuracy improve, dangerous errors do not increase, and RMSE regression stays within 2%",
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

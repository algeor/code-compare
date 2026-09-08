"""Evaluate frozen embedding features against the deployed percentage ensemble."""

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
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pr_suggestion_metrics.embedding_features import FeatureSubsetRegressor, add_embedding_interactions
from pr_suggestion_metrics.train_advanced_percentage_models import (
    DISAGREEMENT_THRESHOLDS,
    GROUP_SPLIT_SEEDS,
    resolve_baseline_schema,
    simplex_weights,
)
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
from pr_suggestion_metrics.two_stage_percentage import WeightedPercentageEnsemble


MIN_CURRENT_MODEL_WEIGHT = 0.5
BLEND_WEIGHT_STEPS = 10


def parse_named_path(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("embedding features must use NAME=PATH")
    return name, Path(raw_path)


def make_random_forest(feature_columns: list[str], parameters: dict[str, Any]) -> Pipeline:
    numeric_columns = [column for column in feature_columns if column not in CATEGORICAL_FEATURES]
    categorical_columns = [column for column in CATEGORICAL_FEATURES if column in feature_columns]
    preprocessor = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric_columns,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="constant", fill_value="none")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical_columns,
            ),
        ]
    )
    estimator = RandomForestRegressor(
        n_estimators=400,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        **parameters,
    )
    return Pipeline([("preprocessor", preprocessor), ("regressor", estimator)])


def fit_random_forest(
    rows: pd.DataFrame,
    feature_columns: list[str],
    parameters: dict[str, Any],
    weight_profile: dict[str, float],
) -> Pipeline:
    model = make_random_forest(feature_columns, parameters)
    model.fit(
        rows[feature_columns],
        rows["expected_landed_percentage"],
        regressor__sample_weight=training_weights(rows, weight_profile),
    )
    return model


def fit_catboost(
    rows: pd.DataFrame,
    feature_columns: list[str],
    parameters: dict[str, Any],
    weight_profile: dict[str, float],
) -> CatBoostRegressor:
    categorical_columns = [column for column in CATEGORICAL_FEATURES if column in feature_columns]
    model = CatBoostRegressor(
        **parameters,
        eval_metric="MAE",
        random_seed=RANDOM_STATE,
        thread_count=-1,
        verbose=False,
        allow_writing_files=False,
    )
    model.fit(
        rows[feature_columns],
        rows["expected_landed_percentage"],
        cat_features=categorical_columns,
        sample_weight=training_weights(rows, weight_profile),
    )
    return model


def blended_predictions(
    predictions: dict[str, np.ndarray],
    weights: dict[str, float],
    disagreement_threshold: float | None,
    fallback_name: str,
) -> np.ndarray:
    active = [(name, weight) for name, weight in weights.items() if weight > 0]
    total_weight = sum(weight for _, weight in active)
    blended = sum(predictions[name] * (weight / total_weight) for name, weight in active)
    if disagreement_threshold is not None:
        fallback = predictions[fallback_name]
        blended = np.where(np.abs(blended - fallback) > disagreement_threshold, fallback, blended)
    return np.clip(blended, 0, 100)


def load_embedding_features(
    named_paths: list[tuple[str, Path]],
) -> tuple[pd.DataFrame, dict[str, list[str]], dict[str, Any]]:
    merged: pd.DataFrame | None = None
    feature_sets: dict[str, list[str]] = {}
    metadata: dict[str, Any] = {}
    for name, path in named_paths:
        frame = pd.read_csv(path)
        keys = ["dataset_source", "example_id"]
        feature_columns = [column for column in frame if column not in keys]
        if not feature_columns:
            raise ValueError(f"no embedding features found in {path}")
        if merged is None:
            merged = frame
        else:
            merged = merged.merge(frame, on=keys, how="outer", validate="one_to_one")
        feature_sets[name] = feature_columns
        metadata_path = path.with_suffix(".metadata.json")
        metadata[name] = json.loads(metadata_path.read_text()) if metadata_path.exists() else {"path": str(path)}
    if merged is None:
        raise ValueError("at least one embedding feature file is required")
    if len(feature_sets) > 1:
        feature_sets["combined"] = [column for columns in feature_sets.values() for column in columns]
    return merged, feature_sets, metadata


def attach_embedding_features(
    rows: pd.DataFrame,
    embedding_frame: pd.DataFrame,
    all_embedding_columns: list[str],
) -> pd.DataFrame:
    merged = rows.merge(
        embedding_frame,
        on=["dataset_source", "example_id"],
        how="left",
        validate="one_to_one",
    )
    missing = merged[all_embedding_columns].isna().any(axis=1)
    if missing.any():
        missing_examples = merged.loc[missing, "example_id"].head(10).tolist()
        raise ValueError(f"missing embedding features for examples: {missing_examples}")
    return add_embedding_interactions(merged, all_embedding_columns)


def expanded_feature_sets(feature_sets: dict[str, list[str]]) -> dict[str, list[str]]:
    expanded = {}
    for name, columns in feature_sets.items():
        interactions = []
        for column in columns:
            if column.endswith("_best_cosine") and "same_file" not in column and "cross_file" not in column:
                interactions.extend(
                    [
                        f"{column}_x_token_recall",
                        f"{column}_x_structural_similarity",
                    ]
                )
        expanded[name] = [*FEATURE_COLUMNS, *columns, *interactions]
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-scores", type=Path, required=True)
    parser.add_argument("--internal-labels", type=Path, required=True)
    parser.add_argument("--hf-scores", type=Path, required=True)
    parser.add_argument("--hf-labels", type=Path, required=True)
    parser.add_argument("--hf-audit", type=Path, required=True)
    parser.add_argument("--base-model-dir", type=Path, required=True)
    parser.add_argument("--embedding-features", action="append", type=parse_named_path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    embedding_frame, raw_feature_sets, embedding_metadata = load_embedding_features(args.embedding_features)
    all_embedding_columns = list(dict.fromkeys(column for columns in raw_feature_sets.values() for column in columns))
    feature_sets = expanded_feature_sets(raw_feature_sets)

    internal = prepare_features(read_source("internal", args.internal_scores, args.internal_labels))
    hf = prepare_features(read_source("hf_github_codereview", args.hf_scores, args.hf_labels, args.hf_audit))
    internal = attach_embedding_features(internal, embedding_frame, all_embedding_columns)
    hf = attach_embedding_features(hf, embedding_frame, all_embedding_columns)

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    dev_positions, test_positions = next(splitter.split(internal, groups=internal["group_id"]))
    internal_dev = internal.iloc[dev_positions].reset_index(drop=True)
    internal_test = internal.iloc[test_positions].copy()

    deployed_schema = json.loads((args.base_model_dir / "feature_schema.json").read_text())
    baseline_schema = resolve_baseline_schema(deployed_schema)
    two_stage_selection = json.loads((args.base_model_dir / "two_stage_evaluation_report.json").read_text())["selected"]
    catboost_specification = deployed_schema["selected_by_family"]["catboost"]
    current_weights = deployed_schema["weights"]
    current_threshold = deployed_schema["disagreement_threshold"]

    candidate_definitions: dict[str, tuple[str, str, list[str]]] = {}
    for feature_set_name, columns in feature_sets.items():
        candidate_definitions[f"{feature_set_name}_random_forest"] = ("random_forest", feature_set_name, columns)
        candidate_definitions[f"{feature_set_name}_catboost_mae"] = ("catboost", feature_set_name, columns)
        candidate_definitions[f"{feature_set_name}_two_stage"] = ("two_stage", feature_set_name, columns)

    prediction_sums = {
        "current_baseline": np.zeros(len(internal_dev), dtype=float),
        "current_two_stage": np.zeros(len(internal_dev), dtype=float),
        "current_catboost_mae": np.zeros(len(internal_dev), dtype=float),
        **{name: np.zeros(len(internal_dev), dtype=float) for name in candidate_definitions},
    }
    prediction_counts = np.zeros(len(internal_dev), dtype=int)

    for seed in GROUP_SPLIT_SEEDS:
        folds = GroupKFold(n_splits=4, shuffle=True, random_state=seed)
        for train_positions, validation_positions in folds.split(internal_dev, groups=internal_dev["group_id"]):
            train_rows = pd.concat([internal_dev.iloc[train_positions], hf], ignore_index=True)
            validation_rows = internal_dev.iloc[validation_positions]
            validation_base = validation_rows[FEATURE_COLUMNS]

            baseline_model = fit(
                make_pipeline(baseline_schema["model_name"], baseline_schema["model_parameters"]),
                train_rows,
                baseline_schema["weight_profile"],
            )
            two_stage_model = make_two_stage_model(
                two_stage_selection["parameters"],
                two_stage_selection["endpoint_threshold"],
            )
            two_stage_model.fit(
                train_rows[FEATURE_COLUMNS],
                train_rows["expected_landed_percentage"],
                sample_weight=training_weights(train_rows, two_stage_selection["weight_profile"]),
            )
            direct_catboost = fit_catboost(
                train_rows,
                FEATURE_COLUMNS,
                catboost_specification["parameters"],
                baseline_schema["weight_profile"],
            )
            component_predictions = {
                "baseline": np.asarray(baseline_model.predict(validation_base), dtype=float),
                "two_stage": np.asarray(two_stage_model.predict(validation_base), dtype=float),
                "catboost_mae": np.asarray(direct_catboost.predict(validation_base), dtype=float),
            }
            prediction_sums["current_baseline"][validation_positions] += component_predictions["baseline"]
            prediction_sums["current_two_stage"][validation_positions] += component_predictions["two_stage"]
            prediction_sums["current_catboost_mae"][validation_positions] += component_predictions["catboost_mae"]

            for candidate_name, (family, _, columns) in candidate_definitions.items():
                if family == "random_forest":
                    model = fit_random_forest(
                        train_rows,
                        columns,
                        baseline_schema["model_parameters"],
                        baseline_schema["weight_profile"],
                    )
                elif family == "catboost":
                    model = fit_catboost(
                        train_rows,
                        columns,
                        catboost_specification["parameters"],
                        baseline_schema["weight_profile"],
                    )
                else:
                    model = make_two_stage_model(
                        two_stage_selection["parameters"],
                        two_stage_selection["endpoint_threshold"],
                    )
                    model.fit(
                        train_rows[columns],
                        train_rows["expected_landed_percentage"],
                        sample_weight=training_weights(train_rows, two_stage_selection["weight_profile"]),
                    )
                prediction_sums[candidate_name][validation_positions] += model.predict(validation_rows[columns])
            prediction_counts[validation_positions] += 1

    if np.any(prediction_counts == 0):
        raise RuntimeError("repeated grouped validation did not cover every development row")
    oof_predictions = {name: values / prediction_counts for name, values in prediction_sums.items()}
    oof_predictions["current_ensemble"] = blended_predictions(
        {
            "baseline": oof_predictions.pop("current_baseline"),
            "two_stage": oof_predictions.pop("current_two_stage"),
            "catboost_mae": oof_predictions.pop("current_catboost_mae"),
        },
        current_weights,
        current_threshold,
        "baseline",
    )
    actual_dev = internal_dev["expected_landed_percentage"].to_numpy(dtype=float)
    oof_metrics = {name: metrics(actual_dev, predictions) for name, predictions in oof_predictions.items()}
    current_metrics = oof_metrics["current_ensemble"]

    selected_per_feature_set = {}
    for feature_set_name in feature_sets:
        candidate_names = [name for name, (_, set_name, _) in candidate_definitions.items() if set_name == feature_set_name]
        selected_per_feature_set[feature_set_name] = min(
            candidate_names,
            key=lambda name: (oof_metrics[name]["percentage_mae"], oof_metrics[name]["percentage_rmse"]),
        )

    blend_components = ["current_ensemble", *selected_per_feature_set.values()]
    blend_results = []
    for weights in simplex_weights(len(blend_components), BLEND_WEIGHT_STEPS):
        weight_map = dict(zip(blend_components, weights, strict=True))
        if weight_map["current_ensemble"] < MIN_CURRENT_MODEL_WEIGHT:
            continue
        if sum(weight > 0 for weight in weights) < 2:
            continue
        for threshold in DISAGREEMENT_THRESHOLDS:
            predictions = blended_predictions(oof_predictions, weight_map, threshold, "current_ensemble")
            blend_results.append(
                {
                    "weights": weight_map,
                    "disagreement_threshold": threshold,
                    **metrics(actual_dev, predictions),
                }
            )
    eligible_blends = [
        result
        for result in blend_results
        if result["percentage_mae"] < current_metrics["percentage_mae"]
        and result["percentage_rmse"] <= current_metrics["percentage_rmse"]
        and result["within_10_points"] >= current_metrics["within_10_points"]
        and result["dangerous_error_rate"] <= current_metrics["dangerous_error_rate"]
    ]
    selected_blend = min(
        eligible_blends or blend_results,
        key=lambda result: (
            result["percentage_mae"],
            result["percentage_rmse"],
            -result["within_10_points"],
        ),
    )
    oof_eligible = selected_blend in eligible_blends

    final_train = pd.concat([internal_dev, hf], ignore_index=True)
    active_candidate_names = [
        name for name, weight in selected_blend["weights"].items() if name != "current_ensemble" and weight > 0
    ]
    final_candidate_models: dict[str, Any] = {}
    for candidate_name in active_candidate_names:
        family, _, columns = candidate_definitions[candidate_name]
        if family == "random_forest":
            final_candidate_models[candidate_name] = fit_random_forest(
                final_train,
                columns,
                baseline_schema["model_parameters"],
                baseline_schema["weight_profile"],
            )
        elif family == "catboost":
            final_candidate_models[candidate_name] = fit_catboost(
                final_train,
                columns,
                catboost_specification["parameters"],
                baseline_schema["weight_profile"],
            )
        else:
            model = make_two_stage_model(
                two_stage_selection["parameters"],
                two_stage_selection["endpoint_threshold"],
            )
            model.fit(
                final_train[columns],
                final_train["expected_landed_percentage"],
                sample_weight=training_weights(final_train, two_stage_selection["weight_profile"]),
            )
            final_candidate_models[candidate_name] = model

    deployed_model = joblib.load(args.base_model_dir / "model.joblib")
    active_names = [name for name, weight in selected_blend["weights"].items() if weight > 0]
    wrapped_models = []
    active_weights = []
    for name in active_names:
        if name == "current_ensemble":
            wrapped_models.append(FeatureSubsetRegressor(deployed_model, tuple(FEATURE_COLUMNS)))
        else:
            wrapped_models.append(
                FeatureSubsetRegressor(final_candidate_models[name], tuple(candidate_definitions[name][2]))
            )
        active_weights.append(selected_blend["weights"][name])
    embedding_model = WeightedPercentageEnsemble(
        models=tuple(wrapped_models),
        weights=tuple(active_weights),
        fallback_model_index=active_names.index("current_ensemble") if selected_blend["disagreement_threshold"] is not None else None,
        disagreement_threshold=selected_blend["disagreement_threshold"],
    )

    actual_test = internal_test["expected_landed_percentage"].to_numpy(dtype=float)
    current_test_metrics = metrics(actual_test, deployed_model.predict(internal_test[FEATURE_COLUMNS]))
    embedding_test_metrics = metrics(actual_test, embedding_model.predict(internal_test))
    deployment_checks = {
        "oof_selection_eligible": oof_eligible,
        "holdout_mae_improved": embedding_test_metrics["percentage_mae"] < current_test_metrics["percentage_mae"],
        "holdout_rmse_improved": embedding_test_metrics["percentage_rmse"] < current_test_metrics["percentage_rmse"],
        "holdout_within_10_not_worse": embedding_test_metrics["within_10_points"] >= current_test_metrics["within_10_points"],
        "holdout_dangerous_error_not_worse": embedding_test_metrics["dangerous_error_rate"] <= current_test_metrics["dangerous_error_rate"],
    }
    recommended_for_deployment = all(deployment_checks.values())

    report = {
        "objective": "measure incremental value of frozen code-embedding similarities",
        "validation": "three repetitions of four-fold PR-grouped out-of-fold evaluation",
        "internal_dev_rows": len(internal_dev),
        "internal_test_rows": len(internal_test),
        "hf_rows": len(hf),
        "embedding_models": embedding_metadata,
        "feature_sets": feature_sets,
        "candidate_oof_metrics": oof_metrics,
        "selected_per_feature_set": selected_per_feature_set,
        "selected_blend": selected_blend,
        "oof_selection_eligible": oof_eligible,
        "current_holdout": current_test_metrics,
        "embedding_holdout": embedding_test_metrics,
        "deployment_checks": deployment_checks,
        "recommended_for_deployment": recommended_for_deployment,
        "interpretation": (
            "embedding candidate clears all strict gates"
            if recommended_for_deployment
            else "retain the current production model; embedding evidence is not yet strong enough"
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if oof_eligible:
        joblib.dump(embedding_model, args.output_dir / "model.joblib")
        required_feature_columns = list(
            dict.fromkeys(
                column
                for name in active_names
                if name != "current_ensemble"
                for column in candidate_definitions[name][2]
            )
        )
        schema = {
            "model_name": "embedding_augmented_percentage_ensemble",
            "base_model_dir": str(args.base_model_dir),
            "components": active_names,
            "weights": {name: selected_blend["weights"][name] for name in active_names},
            "disagreement_threshold": selected_blend["disagreement_threshold"],
            "embedding_models": embedding_metadata,
            "prediction_type": "percentage_regression",
            "prediction_output": "0-100 integer percentage",
            "recommended_for_deployment": recommended_for_deployment,
            "numeric_features": [
                column
                for column in required_feature_columns
                if column not in BOOLEAN_FEATURES and column not in CATEGORICAL_FEATURES
            ],
            "boolean_features": [column for column in BOOLEAN_FEATURES if column in required_feature_columns],
            "categorical_features": [column for column in CATEGORICAL_FEATURES if column in required_feature_columns],
            "feature_columns": required_feature_columns,
        }
        (args.output_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

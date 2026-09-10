"""Train and tune a 0-100 suggestion-coverage percentage regressor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pr_suggestion_metrics.feature_preprocessing import coerce_boolean_series
from pr_suggestion_metrics.model_artifacts import write_model_manifest


RANDOM_STATE = 42
NUMERIC_FEATURES = [
    "line_recall", "token_recall", "identifier_normalized_token_recall", "literal_normalized_token_recall",
    "identifier_and_literal_normalized_token_recall", "best_added_line_overlap", "best_hunk_token_recall",
    "best_hunk_token_precision", "best_hunk_token_f1", "best_hunk_identifier_normalized_recall",
    "best_hunk_literal_normalized_recall", "best_hunk_identifier_and_literal_normalized_recall",
    "best_hunk_contiguous_line_ratio", "best_hunk_token_lcs_recall", "best_hunk_size_ratio",
    "meaningful_anchor_recall", "meaningful_anchor_count", "best_hunk_size", "candidate_hunk_count",
    "structural_similarity", "structural_node_recall", "gumtree_operation_count", "gumtree_insert_ratio",
    "gumtree_delete_ratio", "gumtree_update_ratio", "gumtree_move_ratio", "file_overlap_ratio",
    "changed_line_overlap_ratio",
]
BOOLEAN_FEATURES = ["exact_normalized_match", "structural_available", "gumtree_available"]
CATEGORICAL_FEATURES = [
    "suggestion_language", "tokenizer", "best_hunk_candidate_type", "structural_engine", "structural_language"
]
FEATURE_COLUMNS = NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    predicted = np.rint(np.clip(np.asarray(predicted, dtype=float), 0, 100))
    actual = np.asarray(actual, dtype=float)
    return {
        "percentage_mae": float(mean_absolute_error(actual, predicted)),
        "percentage_rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r2": float(r2_score(actual, predicted)),
        "within_5_points": float(np.mean(np.abs(actual - predicted) <= 5)),
        "within_10_points": float(np.mean(np.abs(actual - predicted) <= 10)),
        "dangerous_error_rate": float(np.mean(((predicted >= 80) & (actual <= 20)) | ((predicted <= 20) & (actual >= 80)))),
    }


def read_source(
    source: str,
    scores_path: Path,
    labels_path: Path,
    audit_path: Path | None = None,
) -> pd.DataFrame:
    scores = pd.read_csv(scores_path)
    labels = pd.read_csv(labels_path)[["example_id", "expected_landed_percentage", "label", "pr_url", "repo"]]
    stale = [column for column in ("expected_landed_percentage", "label", "expected_percentage_bucket") if column in scores.columns]
    rows = scores.drop(columns=stale).merge(labels, on="example_id", how="inner")
    rows["dataset_source"] = source
    rows["group_id"] = source + ":" + rows["pr_url"].fillna(rows["repo"] + "#unknown").astype(str)
    rows["sample_weight"] = 1.0
    if audit_path is not None:
        audit = pd.read_json(audit_path, lines=True)[["example_id", "training_weight", "audit_status"]]
        rows = rows.merge(audit, on="example_id", how="left")
        rows["sample_weight"] = rows["training_weight"].fillna(0.10)
    return rows


def prepare_features(rows: pd.DataFrame) -> pd.DataFrame:
    prepared = rows.copy()
    for feature in NUMERIC_FEATURES:
        prepared[feature] = pd.to_numeric(prepared[feature], errors="coerce")
    for feature in BOOLEAN_FEATURES:
        prepared[feature] = coerce_boolean_series(prepared[feature], feature)
    for feature in CATEGORICAL_FEATURES:
        prepared[feature] = prepared[feature].fillna("none").replace("", "none").astype(str)
    prepared["expected_landed_percentage"] = pd.to_numeric(prepared["expected_landed_percentage"], errors="raise").clip(0, 100)
    return prepared


def make_pipeline(model_name: str, params: dict[str, Any]) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), NUMERIC_FEATURES + BOOLEAN_FEATURES),
            ("categorical", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value="none")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), CATEGORICAL_FEATURES),
        ]
    )
    if model_name == "extra_trees":
        estimator = ExtraTreesRegressor(n_estimators=400, random_state=RANDOM_STATE, n_jobs=-1, **params)
    elif model_name == "random_forest":
        estimator = RandomForestRegressor(n_estimators=400, random_state=RANDOM_STATE, n_jobs=-1, **params)
    else:
        estimator = GradientBoostingRegressor(random_state=RANDOM_STATE, **params)
    return Pipeline([("preprocessor", preprocessor), ("regressor", estimator)])


def candidates() -> list[tuple[str, dict[str, Any], dict[str, float]]]:
    result = []
    weight_profiles = (
        {"hf_scale": 0.0, "confidence_floor": 0.0, "internal_scale": 2.0, "minority_scale": 1.8},
        {"hf_scale": 0.1, "confidence_floor": 0.0, "internal_scale": 2.0, "minority_scale": 1.8},
        {"hf_scale": 0.5, "confidence_floor": 0.0, "internal_scale": 2.0, "minority_scale": 1.8},
        {"hf_scale": 1.1, "confidence_floor": 0.0, "internal_scale": 1.0, "minority_scale": 1.0},
        {"hf_scale": 0.9, "confidence_floor": 0.25, "internal_scale": 1.0, "minority_scale": 1.0},
        {"hf_scale": 0.85, "confidence_floor": 0.5, "internal_scale": 1.0, "minority_scale": 1.0},
        {"hf_scale": 0.85, "confidence_floor": 0.5, "internal_scale": 1.25, "minority_scale": 1.25},
    )
    for weight_profile in weight_profiles:
        for leaf in (1, 2, 4, 7):
            for max_features in (0.65, 1.0):
                result.append(("extra_trees", {"min_samples_leaf": leaf, "max_features": max_features}, weight_profile))
        for leaf in (2, 4, 7):
            result.append(("random_forest", {"min_samples_leaf": leaf, "max_features": 0.8}, weight_profile))
        for depth, estimators, rate in ((2, 250, 0.04), (2, 400, 0.03), (3, 250, 0.04)):
            result.append(("gradient_boosting", {"max_depth": depth, "n_estimators": estimators, "learning_rate": rate}, weight_profile))
    return result


def training_weights(rows: pd.DataFrame, weight_profile: dict[str, float]) -> np.ndarray:
    confidence_weights = rows["sample_weight"].astype(float).to_numpy()
    internal = rows["dataset_source"].eq("internal").to_numpy()
    minority = rows["label"].isin(["partial", "mostly"]).to_numpy()
    confidence_floor = weight_profile["confidence_floor"]
    hf_weights = confidence_floor + ((1.0 - confidence_floor) * confidence_weights)
    weights = np.where(internal, weight_profile["internal_scale"], hf_weights * weight_profile["hf_scale"])
    return np.where(internal & minority, weights * weight_profile["minority_scale"], weights)


def fit(model: Pipeline, rows: pd.DataFrame, weight_profile: dict[str, float]) -> Pipeline:
    weights = training_weights(rows, weight_profile)
    model.fit(rows[FEATURE_COLUMNS], rows["expected_landed_percentage"], regressor__sample_weight=weights)
    return model


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
    dev_pos, test_pos = next(splitter.split(internal, groups=internal["group_id"]))
    internal_dev = internal.iloc[dev_pos].copy()
    internal_test = internal.iloc[test_pos].copy()

    current_model_path = args.model_dir / "model.joblib"
    baseline_model = joblib.load(current_model_path) if current_model_path.exists() else None
    baseline_metrics = metrics(
        internal_test["expected_landed_percentage"].to_numpy(),
        baseline_model.predict(internal_test[FEATURE_COLUMNS]) if baseline_model is not None else internal_test["predicted_percentage"].to_numpy(),
    )
    rule_metrics = metrics(internal_test["expected_landed_percentage"].to_numpy(), internal_test["predicted_percentage"].to_numpy())

    folds = GroupKFold(n_splits=4)
    results = []
    for model_name, params, weight_profile in candidates():
        fold_mae = []
        for train_pos, valid_pos in folds.split(internal_dev, groups=internal_dev["group_id"]):
            train_rows = pd.concat([internal_dev.iloc[train_pos], hf], ignore_index=True)
            valid_rows = internal_dev.iloc[valid_pos]
            model = fit(make_pipeline(model_name, params), train_rows, weight_profile)
            fold_predictions = np.rint(np.clip(model.predict(valid_rows[FEATURE_COLUMNS]), 0, 100))
            fold_mae.append(mean_absolute_error(valid_rows["expected_landed_percentage"], fold_predictions))
        results.append({"model": model_name, "params": params, "weight_profile": weight_profile, "cv_internal_mae": float(np.mean(fold_mae))})

    tuning = sorted(results, key=lambda row: row["cv_internal_mae"])
    best = tuning[0]
    final_train = pd.concat([internal_dev, hf], ignore_index=True)
    model = fit(make_pipeline(best["model"], best["params"]), final_train, best["weight_profile"])
    predictions = np.clip(model.predict(internal_test[FEATURE_COLUMNS]), 0, 100)
    tuned_metrics = metrics(internal_test["expected_landed_percentage"].to_numpy(), predictions)
    improvement = baseline_metrics["percentage_mae"] - tuned_metrics["percentage_mae"]
    model_improved = improvement > 0

    args.model_dir.mkdir(parents=True, exist_ok=True)
    if model_improved:
        joblib.dump(model, args.model_dir / "model.joblib")
        schema = {
            "model_name": best["model"],
            "model_parameters": best["params"],
            "weight_profile": best["weight_profile"],
            "selection_policy": "lowest grouped internal cross-validation percentage MAE, deployed only when holdout MAE improves",
            "prediction_type": "percentage_regression",
            "prediction_output": "0-100 integer percentage",
            "numeric_features": NUMERIC_FEATURES,
            "boolean_features": BOOLEAN_FEATURES,
            "categorical_features": CATEGORICAL_FEATURES,
            "feature_columns": FEATURE_COLUMNS,
        }
        (args.model_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
        write_model_manifest(args.model_dir)
    report = {
        "objective": "minimize percentage MAE on internal semantic labels",
        "internal_dev_rows": len(internal_dev),
        "internal_test_rows": len(internal_test),
        "hf_rows": len(hf),
        "selected": best,
        "baseline_model": baseline_metrics,
        "rule_metric": rule_metrics,
        "tuned_model": tuned_metrics,
        "improvement_vs_baseline_mae": improvement,
        "artifact_decision": "saved_tuned_model" if model_improved else "kept_existing_baseline",
        "top_tuning_results": tuning[:20],
    }
    (args.model_dir / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

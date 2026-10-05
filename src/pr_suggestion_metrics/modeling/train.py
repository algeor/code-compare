"""Train one supported percentage model from frozen benchmark feature rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pr_suggestion_metrics.feature_preprocessing import coerce_boolean_series, coerce_numeric_series
from pr_suggestion_metrics.model_artifacts import sha256_file, write_model_manifest
from pr_suggestion_metrics.train_percentage_regressor import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    metrics,
)


_EXCLUDED_FEATURES = {
    "file_overlap_ratio",
    "changed_line_overlap_ratio",
    "gumtree_operation_count",
    "gumtree_insert_ratio",
    "gumtree_delete_ratio",
    "gumtree_update_ratio",
    "gumtree_move_ratio",
    "gumtree_available",
    "gumtree_language",
}


def _active_features(rows: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    """Select present, non-constant features while excluding known leakage/dead fields."""
    def available(features: list[str]) -> list[str]:
        return [
            feature
            for feature in features
            if feature in rows.columns
            and feature not in _EXCLUDED_FEATURES
            and rows[feature].nunique(dropna=False) > 1
        ]

    numeric = available(NUMERIC_FEATURES)
    boolean = available(BOOLEAN_FEATURES)
    categorical = available(CATEGORICAL_FEATURES)
    if not numeric and not boolean and not categorical:
        raise ValueError("No varying supported model features are available")
    return numeric, boolean, categorical


def _prepare(rows: pd.DataFrame, numeric: list[str], boolean: list[str], categorical: list[str]) -> pd.DataFrame:
    prepared = rows.copy()
    row_ids = prepared["example_id"].tolist() if "example_id" in prepared else None
    for feature in numeric:
        prepared[feature] = coerce_numeric_series(prepared[feature], feature, row_ids=row_ids)
    for feature in boolean:
        prepared[feature] = coerce_boolean_series(prepared[feature], feature, row_ids=row_ids)
    for feature in categorical:
        prepared[feature] = prepared[feature].fillna("none").replace("", "none").astype(str)
    return prepared


def _pipeline(
    model_name: str,
    numeric: list[str],
    boolean: list[str],
    categorical: list[str],
    random_state: int,
) -> Pipeline:
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if numeric or boolean:
        transformers.append(
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric + boolean,
            )
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="constant", fill_value="none")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            )
        )
    preprocessor = ColumnTransformer(transformers)
    if model_name == "random_forest":
        estimator = RandomForestRegressor(
            n_estimators=400,
            min_samples_leaf=3,
            random_state=random_state,
            n_jobs=-1,
        )
    elif model_name == "extra_trees":
        estimator = ExtraTreesRegressor(
            n_estimators=400,
            min_samples_leaf=3,
            random_state=random_state,
            n_jobs=-1,
        )
    elif model_name == "gradient_boosting":
        estimator = GradientBoostingRegressor(random_state=random_state, loss="huber")
    else:
        raise ValueError(f"Unknown model candidate: {model_name}")
    return Pipeline([("preprocessor", preprocessor), ("regressor", estimator)])


def train_from_frozen_features(
    *,
    features_path: Path,
    model_dir: Path,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Select on development only, then fit the chosen model on train+development."""
    rows = pd.read_csv(features_path)
    required = {"split", "coverage_percentage", "group_id"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Feature table is missing required columns: {missing}")
    if rows["split"].eq("test").any():
        raise ValueError("The official trainer must not receive test rows")
    train_rows = rows.loc[rows["split"].eq("train")].copy()
    development_rows = rows.loc[rows["split"].eq("development")].copy()
    if train_rows.empty or development_rows.empty:
        raise ValueError("Feature table must contain non-empty train and development splits")

    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path else {}
    candidates = config.get("candidates", ["random_forest", "extra_trees", "gradient_boosting"])
    random_state = int(config.get("random_state", 42))
    numeric, boolean, categorical = _active_features(train_rows)
    train_rows = _prepare(train_rows, numeric, boolean, categorical)
    development_rows = _prepare(development_rows, numeric, boolean, categorical)
    feature_columns = numeric + boolean + categorical

    candidate_results: list[dict[str, Any]] = []
    fitted: dict[str, Pipeline] = {}
    for model_name in candidates:
        model = _pipeline(str(model_name), numeric, boolean, categorical, random_state)
        model.fit(train_rows[feature_columns], train_rows["coverage_percentage"])
        result = metrics(
            development_rows["coverage_percentage"].to_numpy(),
            model.predict(development_rows[feature_columns]),
        )
        candidate_results.append({"model_name": model_name, "development_metrics": result})
        fitted[str(model_name)] = model

    selected = min(candidate_results, key=lambda item: item["development_metrics"]["percentage_mae"])
    selected_name = str(selected["model_name"])
    final_rows = pd.concat([train_rows, development_rows], ignore_index=True)
    final_model = _pipeline(selected_name, numeric, boolean, categorical, random_state)
    final_model.fit(final_rows[feature_columns], final_rows["coverage_percentage"])

    model_dir.mkdir(parents=True, exist_ok=False)
    joblib.dump(final_model, model_dir / "model.joblib")
    schema = {
        "schema_version": "1.0",
        "model_name": selected_name,
        "prediction_type": "percentage_regression",
        "prediction_output": "0-100 raw and rounded percentage",
        "selection_policy": "lowest development MAE; test rows inaccessible to trainer",
        "numeric_features": numeric,
        "boolean_features": boolean,
        "categorical_features": categorical,
        "feature_columns": feature_columns,
        "excluded_features": sorted(_EXCLUDED_FEATURES),
    }
    (model_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    write_model_manifest(model_dir)
    report = {
        "schema_version": "1.0",
        "features_sha256": sha256_file(features_path),
        "train_rows": len(train_rows),
        "development_rows": len(development_rows),
        "calibration_rows_reserved": int(rows["split"].eq("calibration").sum()),
        "selected_model": selected_name,
        "candidate_results": candidate_results,
        "feature_columns": feature_columns,
    }
    (model_dir / "training_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = train_from_frozen_features(
        features_path=args.features,
        model_dir=args.model_dir,
        config_path=args.config,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

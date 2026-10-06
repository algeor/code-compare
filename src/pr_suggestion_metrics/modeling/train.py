"""Train one supported percentage model from frozen benchmark feature rows."""

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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pr_suggestion_metrics.feature_preprocessing import coerce_boolean_series, coerce_numeric_series
from pr_suggestion_metrics.features.policy import NORMALIZATION_POLICY_VERSION
from pr_suggestion_metrics.model_artifacts import sha256_file, write_model_manifest
from pr_suggestion_metrics.modeling.common import (
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
_ALLOWED_SPLITS = {"train", "development", "calibration"}
_SUPPORTED_CANDIDATES = {"random_forest", "extra_trees", "gradient_boosting"}


def _validate_training_rows(rows: pd.DataFrame) -> pd.DataFrame:
    required = {"split", "coverage_percentage", "group_id", "normalization_policy_version"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f"Feature table is missing required columns: {missing}")

    validated = rows.copy()
    normalized_splits = validated["split"].astype("string").str.strip().str.lower()
    invalid_splits = normalized_splits.isna() | ~normalized_splits.isin(_ALLOWED_SPLITS)
    if invalid_splits.any():
        invalid_values = sorted(validated.loc[invalid_splits, "split"].astype(str).unique().tolist())
        raise ValueError(
            f"Feature table contains unsupported split values: {invalid_values}; "
            "expected only train, development, or calibration rows"
        )
    validated["split"] = normalized_splits.astype(str)

    group_ids = validated["group_id"].astype("string").str.strip()
    invalid_groups = group_ids.isna() | group_ids.eq("")
    if invalid_groups.any():
        raise ValueError("Feature table group_id values must be non-empty")
    validated["group_id"] = group_ids.astype(str)

    try:
        targets = pd.to_numeric(validated["coverage_percentage"], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Feature table coverage_percentage values must be numeric") from exc
    if not np.isfinite(targets).all() or np.any((targets < 0) | (targets > 100)):
        raise ValueError("Feature table coverage_percentage values must be finite and between 0 and 100")
    validated["coverage_percentage"] = targets

    policy_versions = validated["normalization_policy_version"].astype("string").str.strip()
    if policy_versions.isna().any() or not policy_versions.eq(NORMALIZATION_POLICY_VERSION).all():
        received = sorted(policy_versions.dropna().unique().tolist())
        raise ValueError(
            "Feature table normalization_policy_version must contain only "
            f"{NORMALIZATION_POLICY_VERSION!r}; received {received}"
        )
    validated["normalization_policy_version"] = policy_versions.astype(str)

    split_counts = validated.groupby("group_id", sort=False)["split"].nunique()
    overlapping_groups = split_counts[split_counts > 1].index.tolist()
    if overlapping_groups:
        preview = overlapping_groups[:5]
        raise ValueError(f"group_id values must not cross dataset splits; overlapping groups: {preview}")
    return validated


def _training_config(config_path: Path | None) -> tuple[list[str], int]:
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path else {}
    if not isinstance(config, dict):
        raise ValueError("Training config must be a JSON object")

    candidates = config.get("candidates", ["random_forest", "extra_trees", "gradient_boosting"])
    if not isinstance(candidates, list) or not candidates or not all(isinstance(name, str) for name in candidates):
        raise ValueError("Training config candidates must be a non-empty list of model names")
    if len(candidates) != len(set(candidates)):
        raise ValueError("Training config candidates must not contain duplicates")
    unsupported = sorted(set(candidates) - _SUPPORTED_CANDIDATES)
    if unsupported:
        raise ValueError(f"Unknown model candidates: {unsupported}")

    random_state_value = config.get("random_state", 42)
    if isinstance(random_state_value, bool) or not isinstance(random_state_value, int):
        raise ValueError("Training config random_state must be an integer")
    return candidates, random_state_value


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
    rows = _validate_training_rows(pd.read_csv(features_path))
    train_rows = rows.loc[rows["split"].eq("train")].copy()
    development_rows = rows.loc[rows["split"].eq("development")].copy()
    if train_rows.empty or development_rows.empty:
        raise ValueError("Feature table must contain non-empty train and development splits")

    candidates, random_state = _training_config(config_path)
    numeric, boolean, categorical = _active_features(train_rows)
    train_rows = _prepare(train_rows, numeric, boolean, categorical)
    development_rows = _prepare(development_rows, numeric, boolean, categorical)
    feature_columns = numeric + boolean + categorical

    candidate_results: list[dict[str, Any]] = []
    for model_name in candidates:
        model = _pipeline(model_name, numeric, boolean, categorical, random_state)
        model.fit(train_rows[feature_columns], train_rows["coverage_percentage"])
        result = metrics(
            development_rows["coverage_percentage"].to_numpy(),
            model.predict(development_rows[feature_columns]),
        )
        if not all(np.isfinite(value) for value in result.values()):
            raise ValueError(
                "Development metrics must be finite; provide enough valid development rows for model selection"
            )
        candidate_results.append({"model_name": model_name, "development_metrics": result})

    selected = min(candidate_results, key=lambda item: item["development_metrics"]["percentage_mae"])
    selected_name = str(selected["model_name"])
    final_rows = pd.concat([train_rows, development_rows], ignore_index=True)
    final_model = _pipeline(selected_name, numeric, boolean, categorical, random_state)
    final_model.fit(final_rows[feature_columns], final_rows["coverage_percentage"])

    model_dir.mkdir(parents=True, exist_ok=False)
    joblib.dump(final_model, model_dir / "model.joblib")
    schema = {
        "schema_version": "1.1",
        "model_name": selected_name,
        "prediction_type": "percentage_regression",
        "prediction_output": "0-100 raw and rounded percentage",
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "selection_policy": "lowest development MAE; test rows inaccessible to trainer",
        "numeric_features": numeric,
        "boolean_features": boolean,
        "categorical_features": categorical,
        "feature_columns": feature_columns,
        "excluded_features": sorted(_EXCLUDED_FEATURES),
    }
    (model_dir / "feature_schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_model_manifest(model_dir)
    report = {
        "schema_version": "1.0",
        "features_sha256": sha256_file(features_path),
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "train_rows": len(train_rows),
        "development_rows": len(development_rows),
        "calibration_rows_reserved": int(rows["split"].eq("calibration").sum()),
        "selected_model": selected_name,
        "candidate_results": candidate_results,
        "feature_columns": feature_columns,
    }
    (model_dir / "training_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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

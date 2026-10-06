from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor

from pr_suggestion_metrics.model_artifacts import write_model_manifest


def write_percentage_model(root: Path) -> Path:
    model_dir = root / "model"
    model_dir.mkdir()
    features = pd.DataFrame({"candidate_hunk_count": [0, 1]})
    model = DummyRegressor(strategy="constant", constant=50).fit(features, [0.0, 100.0])
    joblib.dump(model, model_dir / "model.joblib")
    schema = {
        "schema_version": "1.0",
        "model_name": "test_percentage_regressor",
        "prediction_type": "percentage_regression",
        "numeric_features": ["candidate_hunk_count"],
        "boolean_features": [],
        "categorical_features": [],
        "feature_columns": ["candidate_hunk_count"],
    }
    (model_dir / "feature_schema.json").write_text(json.dumps(schema), encoding="utf-8")
    write_model_manifest(model_dir)
    return model_dir

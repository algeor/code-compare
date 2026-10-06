from __future__ import annotations

import json
from pathlib import Path

import pytest
import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor

from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.modeling.select import select_model_for_release


_SUGGESTED_DIFF = "--- a/src/example.py\n+++ b/src/example.py\n@@ -0,0 +1 @@\n+return value\n"
_LANDED_DIFF = "diff --git a/src/example.py b/src/example.py\n--- a/src/example.py\n+++ b/src/example.py\n@@ -0,0 +1 @@\n+return value\n"


def _row(example_id: str, repo: str, pr_number: int, coverage: int) -> dict[str, object]:
    return {
        "example_id": example_id,
        "repo": repo,
        "pr_url": f"https://{repo}/pull/{pr_number}",
        "pr_number": pr_number,
        "suggested_diff": _SUGGESTED_DIFF,
        "landed_diff": _LANDED_DIFF,
        "coverage_percentage": coverage,
        "coverage_unrounded": float(coverage),
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_percentage_model(root: Path) -> Path:
    model_dir = root / "model"
    model_dir.mkdir()
    model = DummyRegressor(strategy="constant", constant=50).fit(
        pd.DataFrame({"candidate_hunk_count": [0, 1]}),
        [0.0, 100.0],
    )
    joblib.dump(model, model_dir / "model.joblib")
    schema = {
        "schema_version": "1.1",
        "model_name": "test_percentage_regressor",
        "prediction_type": "percentage_regression",
        "normalization_policy_version": "1.0",
        "numeric_features": ["candidate_hunk_count"],
        "boolean_features": [],
        "categorical_features": [],
        "feature_columns": ["candidate_hunk_count"],
    }
    (model_dir / "feature_schema.json").write_text(json.dumps(schema), encoding="utf-8")
    from pr_suggestion_metrics.model_artifacts import write_model_manifest

    write_model_manifest(model_dir)
    return model_dir


def _write_frozen_benchmark(root: Path) -> Path:
    benchmark_dir = root / "benchmark"
    benchmark_dir.mkdir()
    _write_jsonl(benchmark_dir / "train.jsonl", [_row("train", "host/owner/repo-a", 1, 0)])
    _write_jsonl(benchmark_dir / "development.jsonl", [_row("development", "host/owner/repo-b", 2, 50)])
    _write_jsonl(benchmark_dir / "calibration.jsonl", [_row("calibration", "host/owner/repo-c", 3, 100)])
    _write_jsonl(benchmark_dir / "test_inputs.jsonl", [_row("test", "host/owner/repo-d", 4, 100)])
    _write_jsonl(benchmark_dir / "test_labels.private.jsonl", [{"example_id": "test", "coverage_unrounded": 100.0}])
    artifact_files = {
        "train": "train.jsonl",
        "development": "development.jsonl",
        "calibration": "calibration.jsonl",
        "test": "test_inputs.jsonl",
        "private_test_labels": "test_labels.private.jsonl",
    }
    manifest = {
        "schema_version": "1.0",
        "annotation_mode": "llm_adjudicated",
        "ground_truth_claim": "llm_adjudicated_not_human_ground_truth",
        "artifact_sha256": {
            artifact_name: sha256_file(benchmark_dir / file_name)
            for artifact_name, file_name in artifact_files.items()
        },
    }
    (benchmark_dir / "benchmark_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return benchmark_dir


def test_select_model_packages_existing_model_that_beats_baselines(tmp_path: Path) -> None:
    benchmark_dir = _write_frozen_benchmark(tmp_path)
    model_dir = _write_percentage_model(tmp_path)

    report = select_model_for_release(
        benchmark_dir=benchmark_dir,
        output_dir=tmp_path / "selection",
        candidate_model_dirs=[model_dir],
    )

    assert report["decision"] == "package_existing_model"
    assert report["benchmark_annotation_mode"] == "llm_adjudicated"
    assert report["selected_model"]["model_dir"] == str(model_dir)
    assert (tmp_path / "selection" / "selected_model" / "artifact_manifest.json").is_file()
    assert (tmp_path / "selection" / "features" / "feature_manifest.json").is_file()


def test_select_model_rejects_tampered_frozen_test_inputs(tmp_path: Path) -> None:
    benchmark_dir = _write_frozen_benchmark(tmp_path)
    (benchmark_dir / "test_inputs.jsonl").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="test_inputs.jsonl"):
        select_model_for_release(
            benchmark_dir=benchmark_dir,
            output_dir=tmp_path / "selection",
            candidate_model_dirs=[],
        )


def test_select_model_reports_baseline_when_no_compatible_model_wins(tmp_path: Path) -> None:
    benchmark_dir = _write_frozen_benchmark(tmp_path)

    report = select_model_for_release(
        benchmark_dir=benchmark_dir,
        output_dir=tmp_path / "selection",
        candidate_model_dirs=[],
    )

    assert report["decision"] == "use_baseline_or_train_new_model"
    assert report["selected_model"] is None
    assert report["best_baseline"]["name"].startswith("constant_")

"""Evaluate embedding models with each external repository held out from training."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pr_suggestion_metrics.train_advanced_percentage_models import resolve_baseline_schema
from pr_suggestion_metrics.train_embedding_percentage_models import (
    attach_embedding_features,
    blended_predictions,
    expanded_feature_sets,
    fit_catboost,
    load_embedding_features,
    parse_named_path,
)
from pr_suggestion_metrics.train_percentage_regressor import (
    FEATURE_COLUMNS,
    fit,
    make_pipeline,
    metrics,
    prepare_features,
    read_source,
    training_weights,
    validate_disjoint_sources,
)
from pr_suggestion_metrics.train_two_stage_percentage import make_model as make_two_stage_model


EVALUATION_VERSION = "repository-held-out-v1"
BOOTSTRAP_SEED = 20260908
BOOTSTRAP_ITERATIONS = 10_000
PREDICTION_COLUMNS = (
    "current_ensemble",
    "unixcoder_two_stage",
    "unixcoder_encoder_two_stage",
    "codebert_two_stage",
    "combined_two_stage",
    "selected_embedding_blend",
)


def clean_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    result = metrics(actual, predicted)
    return {name: value if np.isfinite(value) else None for name, value in result.items()}


def metric_differences(
    actual: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, float]:
    baseline_metrics = metrics(actual, baseline)
    candidate_metrics = metrics(actual, candidate)
    return {
        "mae_reduction": baseline_metrics["percentage_mae"] - candidate_metrics["percentage_mae"],
        "rmse_reduction": baseline_metrics["percentage_rmse"] - candidate_metrics["percentage_rmse"],
        "within_5_gain": candidate_metrics["within_5_points"] - baseline_metrics["within_5_points"],
        "within_10_gain": candidate_metrics["within_10_points"] - baseline_metrics["within_10_points"],
        "dangerous_error_reduction": baseline_metrics["dangerous_error_rate"] - candidate_metrics["dangerous_error_rate"],
    }


def repository_bootstrap(
    actual: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    repositories: np.ndarray,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, dict[str, float]]:
    random = np.random.default_rng(BOOTSTRAP_SEED)
    unique_repositories = np.unique(repositories)
    positions_by_repository = {
        repository: np.flatnonzero(repositories == repository)
        for repository in unique_repositories
    }
    samples: dict[str, list[float]] = {
        "mae_reduction": [],
        "rmse_reduction": [],
        "within_5_gain": [],
        "within_10_gain": [],
        "dangerous_error_reduction": [],
    }
    for _ in range(iterations):
        sampled_repositories = random.choice(
            unique_repositories,
            size=len(unique_repositories),
            replace=True,
        )
        sampled_positions = np.concatenate(
            [positions_by_repository[repository] for repository in sampled_repositories]
        )
        differences = metric_differences(
            actual[sampled_positions],
            baseline[sampled_positions],
            candidate[sampled_positions],
        )
        for name, value in differences.items():
            samples[name].append(value)

    estimates = metric_differences(actual, baseline, candidate)
    return {
        name: {
            "estimate": float(estimates[name]),
            "ci_95_low": float(np.percentile(values, 2.5)),
            "ci_95_high": float(np.percentile(values, 97.5)),
            "probability_positive": float(np.mean(np.asarray(values) > 0)),
        }
        for name, values in samples.items()
    }


def macro_metrics(
    per_repository: dict[str, dict[str, Any]],
    candidate: str,
    minimum_rows: int = 1,
) -> dict[str, float | None]:
    rows = [
        repository_result[candidate]
        for repository_result in per_repository.values()
        if repository_result["rows"] >= minimum_rows
    ]
    metric_names = [
        "percentage_mae",
        "percentage_rmse",
        "within_5_points",
        "within_10_points",
        "dangerous_error_rate",
    ]
    result: dict[str, float | None] = {}
    for name in metric_names:
        values = [row[name] for row in rows if row[name] is not None]
        result[name] = float(np.mean(values)) if values else None
    return result


def repository_wins(
    per_repository: dict[str, dict[str, Any]],
    candidate: str,
    minimum_rows: int = 1,
) -> dict[str, int]:
    differences = []
    for repository_result in per_repository.values():
        if repository_result["rows"] < minimum_rows:
            continue
        differences.append(
            repository_result["current_ensemble"]["percentage_mae"]
            - repository_result[candidate]["percentage_mae"]
        )
    return {
        "wins": sum(difference > 0 for difference in differences),
        "ties": sum(difference == 0 for difference in differences),
        "losses": sum(difference < 0 for difference in differences),
    }


def configuration_fingerprint(
    embedding_metadata: dict[str, Any],
    base_schema: dict[str, Any],
    selected_embedding_schema: dict[str, Any],
    input_paths: Sequence[Path] = (),
) -> str:
    payload = json.dumps(
        {
            "evaluation_version": EVALUATION_VERSION,
            "embedding_metadata": embedding_metadata,
            "base_schema": base_schema,
            "selected_embedding_schema": selected_embedding_schema,
            "input_sha256": {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in input_paths
            },
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def completed_repositories(completed: pd.DataFrame, external: pd.DataFrame) -> set[str]:
    """Validate resumed predictions and return repositories with complete folds."""
    required_columns = {"example_id", "repo", *PREDICTION_COLUMNS}
    missing_columns = required_columns - set(completed)
    if missing_columns:
        raise ValueError(f"partial predictions are missing columns: {sorted(missing_columns)}")
    if completed["example_id"].duplicated().any():
        raise ValueError("partial predictions contain duplicate example_id values")

    external_ids = set(external["example_id"])
    unknown_ids = sorted(str(example_id) for example_id in set(completed["example_id"]) - external_ids)
    if unknown_ids:
        raise ValueError(f"partial predictions contain unknown example_id values: {unknown_ids[:10]}")

    repositories: set[str] = set()
    for repository, rows in completed.groupby("repo", sort=False):
        expected_ids = set(external.loc[external["repo"].eq(repository), "example_id"])
        completed_ids = set(rows["example_id"])
        if completed_ids != expected_ids:
            raise ValueError(f"partial predictions contain an incomplete fold for repository {repository!r}")
        repositories.add(str(repository))
    return repositories


def write_csv_atomically(frame: pd.DataFrame, path: Path) -> None:
    """Replace a CSV only after its complete contents are on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            frame.to_csv(temporary_file, index=False)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def fit_two_stage(
    train_rows: pd.DataFrame,
    feature_columns: list[str],
    selection: dict[str, Any],
) -> Any:
    model = make_two_stage_model(selection["parameters"], selection["endpoint_threshold"])
    model.fit(
        train_rows[feature_columns],
        train_rows["expected_landed_percentage"],
        sample_weight=training_weights(train_rows, selection["weight_profile"]),
    )
    return model


def train_fold(
    train_rows: pd.DataFrame,
    test_rows: pd.DataFrame,
    baseline_schema: dict[str, Any],
    two_stage_selection: dict[str, Any],
    catboost_specification: dict[str, Any],
    current_schema: dict[str, Any],
    feature_sets: dict[str, list[str]],
    selected_embedding_schema: dict[str, Any],
) -> dict[str, np.ndarray]:
    baseline_model = fit(
        make_pipeline(baseline_schema["model_name"], baseline_schema["model_parameters"]),
        train_rows,
        baseline_schema["weight_profile"],
    )
    current_two_stage = fit_two_stage(train_rows, FEATURE_COLUMNS, two_stage_selection)
    current_catboost = fit_catboost(
        train_rows,
        FEATURE_COLUMNS,
        catboost_specification["parameters"],
        baseline_schema["weight_profile"],
    )
    current_components = {
        "baseline": np.asarray(baseline_model.predict(test_rows[FEATURE_COLUMNS]), dtype=float),
        "two_stage": np.asarray(current_two_stage.predict(test_rows[FEATURE_COLUMNS]), dtype=float),
        "catboost_mae": np.asarray(current_catboost.predict(test_rows[FEATURE_COLUMNS]), dtype=float),
    }
    predictions = {
        "current_ensemble": blended_predictions(
            current_components,
            current_schema["weights"],
            current_schema["disagreement_threshold"],
            "baseline",
        )
    }

    feature_set_to_prediction = {
        "unixcoder": "unixcoder_two_stage",
        "unixcoder_encoder": "unixcoder_encoder_two_stage",
        "codebert": "codebert_two_stage",
        "combined": "combined_two_stage",
    }
    for feature_set_name, prediction_name in feature_set_to_prediction.items():
        columns = feature_sets[feature_set_name]
        model = fit_two_stage(train_rows, columns, two_stage_selection)
        predictions[prediction_name] = np.asarray(model.predict(test_rows[columns]), dtype=float)

    selected_components = {
        name: predictions[name]
        for name, weight in selected_embedding_schema["weights"].items()
        if weight > 0
    }
    predictions["selected_embedding_blend"] = blended_predictions(
        selected_components,
        selected_embedding_schema["weights"],
        selected_embedding_schema["disagreement_threshold"],
        "current_ensemble",
    )
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-scores", type=Path, required=True)
    parser.add_argument("--internal-labels", type=Path, required=True)
    parser.add_argument("--hf-scores", type=Path, required=True)
    parser.add_argument("--hf-labels", type=Path, required=True)
    parser.add_argument("--hf-audit", type=Path, required=True)
    parser.add_argument("--base-model-dir", type=Path, required=True)
    parser.add_argument("--embedding-model-dir", type=Path, required=True)
    parser.add_argument("--embedding-features", action="append", type=parse_named_path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    embedding_frame, raw_feature_sets, embedding_metadata = load_embedding_features(args.embedding_features)
    all_embedding_columns = list(
        dict.fromkeys(column for columns in raw_feature_sets.values() for column in columns)
    )
    feature_sets = expanded_feature_sets(raw_feature_sets)
    required_feature_sets = {"unixcoder", "unixcoder_encoder", "codebert", "combined"}
    missing_feature_sets = required_feature_sets - set(feature_sets)
    if missing_feature_sets:
        raise ValueError(f"missing required embedding feature sets: {sorted(missing_feature_sets)}")

    internal = prepare_features(read_source("internal", args.internal_scores, args.internal_labels))
    external = prepare_features(
        read_source(
            "hf_github_codereview",
            args.hf_scores,
            args.hf_labels,
            args.hf_audit,
        )
    )
    validate_disjoint_sources(internal, external)
    internal = attach_embedding_features(internal, embedding_frame, all_embedding_columns)
    external = attach_embedding_features(external, embedding_frame, all_embedding_columns)
    audit = pd.read_json(args.hf_audit, lines=True)[["example_id", "confidence", "audit_status"]]
    external = external.drop(columns=["audit_status"], errors="ignore").merge(
        audit,
        on="example_id",
        how="left",
        validate="one_to_one",
    )

    current_schema = json.loads((args.base_model_dir / "feature_schema.json").read_text())
    baseline_schema = resolve_baseline_schema(current_schema)
    two_stage_selection = json.loads(
        (args.base_model_dir / "two_stage_evaluation_report.json").read_text()
    )["selected"]
    catboost_specification = current_schema["selected_by_family"]["catboost"]
    selected_embedding_schema = json.loads(
        (args.embedding_model_dir / "feature_schema.json").read_text()
    )
    fingerprint = configuration_fingerprint(
        embedding_metadata,
        current_schema,
        selected_embedding_schema,
        input_paths=[
            args.internal_scores,
            args.internal_labels,
            args.hf_scores,
            args.hf_labels,
            args.hf_audit,
            args.base_model_dir / "model.joblib",
            args.base_model_dir / "feature_schema.json",
            args.base_model_dir / "two_stage_evaluation_report.json",
            args.embedding_model_dir / "feature_schema.json",
            *(path for _, path in args.embedding_features),
        ],
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    partial_path = args.output_dir / "repository_predictions.partial.csv"
    completed = pd.DataFrame()
    if args.resume and partial_path.exists():
        completed = pd.read_csv(partial_path)
        fingerprint_path = args.output_dir / "configuration_fingerprint.txt"
        if not fingerprint_path.exists() or fingerprint_path.read_text().strip() != fingerprint:
            raise ValueError("partial predictions were generated by a different configuration")
    (args.output_dir / "configuration_fingerprint.txt").write_text(fingerprint + "\n")
    completed_repository_names = completed_repositories(completed, external) if not completed.empty else set()

    repositories = sorted(external["repo"].unique())
    fold_frames = [completed] if not completed.empty else []
    for fold_number, repository in enumerate(repositories, start=1):
        if repository in completed_repository_names:
            print(f"[{fold_number}/{len(repositories)}] skipping completed {repository}", flush=True)
            continue
        test_rows = external.loc[external["repo"].eq(repository)].copy()
        train_rows = pd.concat(
            [internal, external.loc[~external["repo"].eq(repository)]],
            ignore_index=True,
        )
        print(
            f"[{fold_number}/{len(repositories)}] holding out {repository}: "
            f"train={len(train_rows)}, test={len(test_rows)}",
            flush=True,
        )
        predictions = train_fold(
            train_rows,
            test_rows,
            baseline_schema,
            two_stage_selection,
            catboost_specification,
            current_schema,
            feature_sets,
            selected_embedding_schema,
        )
        fold_frame = test_rows[
            [
                "example_id",
                "repo",
                "pr_url",
                "confidence",
                "audit_status",
                "expected_landed_percentage",
            ]
        ].copy()
        for name, values in predictions.items():
            fold_frame[name] = np.rint(np.clip(values, 0, 100)).astype(int)
        fold_frames.append(fold_frame)
        write_csv_atomically(pd.concat(fold_frames, ignore_index=True), partial_path)

    predictions = pd.concat(fold_frames, ignore_index=True)
    predictions = predictions.sort_values(["repo", "example_id"]).reset_index(drop=True)
    if len(predictions) != len(external) or predictions["example_id"].duplicated().any():
        raise RuntimeError("repository-held-out predictions are incomplete or duplicated")
    prediction_path = args.output_dir / "repository_predictions.csv"
    predictions.to_csv(prediction_path, index=False)

    actual = predictions["expected_landed_percentage"].to_numpy(dtype=float)
    overall = {
        name: clean_metrics(actual, predictions[name].to_numpy(dtype=float))
        for name in PREDICTION_COLUMNS
    }
    per_repository: dict[str, dict[str, Any]] = {}
    for repository, group in predictions.groupby("repo", sort=True):
        repository_actual = group["expected_landed_percentage"].to_numpy(dtype=float)
        per_repository[repository] = {
            "rows": len(group),
            "pull_requests": int(group["pr_url"].nunique()),
            **{
                name: clean_metrics(repository_actual, group[name].to_numpy(dtype=float))
                for name in PREDICTION_COLUMNS
            },
        }

    confidence_metrics = {}
    for confidence, group in predictions.groupby("confidence", sort=True):
        confidence_actual = group["expected_landed_percentage"].to_numpy(dtype=float)
        confidence_metrics[str(confidence)] = {
            "rows": len(group),
            **{
                name: clean_metrics(confidence_actual, group[name].to_numpy(dtype=float))
                for name in PREDICTION_COLUMNS
            },
        }

    repository_values = predictions["repo"].to_numpy()
    paired_comparisons = {
        name: {
            "bootstrap": repository_bootstrap(
                actual,
                predictions["current_ensemble"].to_numpy(dtype=float),
                predictions[name].to_numpy(dtype=float),
                repository_values,
            ),
            "repository_wins_all": repository_wins(per_repository, name),
            "repository_wins_minimum_10_rows": repository_wins(per_repository, name, minimum_rows=10),
        }
        for name in PREDICTION_COLUMNS
        if name != "current_ensemble"
    }
    report = {
        "objective": "estimate cross-repository transfer using leave-one-external-repository-out retraining",
        "evaluation_version": EVALUATION_VERSION,
        "interpretation_scope": "exploratory because external semantic labels are confidence-weighted LLM-assisted references",
        "training_policy": "all internal rows plus all external repositories except the held-out repository",
        "external_rows": len(external),
        "external_repositories": len(repositories),
        "external_pull_requests": int(external["pr_url"].nunique()),
        "internal_training_rows_per_fold": len(internal),
        "models": list(PREDICTION_COLUMNS),
        "overall_micro_metrics": overall,
        "macro_repository_metrics": {
            name: macro_metrics(per_repository, name)
            for name in PREDICTION_COLUMNS
        },
        "macro_repository_metrics_minimum_10_rows": {
            name: macro_metrics(per_repository, name, minimum_rows=10)
            for name in PREDICTION_COLUMNS
        },
        "confidence_metrics": confidence_metrics,
        "paired_comparisons_vs_current": paired_comparisons,
        "per_repository": per_repository,
        "bootstrap": {
            "iterations": BOOTSTRAP_ITERATIONS,
            "seed": BOOTSTRAP_SEED,
            "sampling_unit": "repository",
        },
        "configuration_fingerprint": fingerprint,
    }
    (args.output_dir / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if partial_path.exists():
        partial_path.unlink()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

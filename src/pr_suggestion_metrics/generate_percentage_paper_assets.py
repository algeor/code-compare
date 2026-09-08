"""Generate reproducible statistics and figures for the percentage-model paper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from pr_suggestion_metrics.train_percentage_regressor import (
    FEATURE_COLUMNS,
    RANDOM_STATE,
    metrics,
    prepare_features,
    read_source,
)


BOOTSTRAP_SEED = 20260907
BOOTSTRAP_ITERATIONS = 10_000


def rounded_predictions(model: Any, features: pd.DataFrame) -> np.ndarray:
    return np.rint(np.clip(np.asarray(model.predict(features), dtype=float), 0, 100)).astype(int)


def metric_differences(actual: np.ndarray, baseline: np.ndarray, ensemble: np.ndarray) -> dict[str, float]:
    baseline_metrics = metrics(actual, baseline)
    ensemble_metrics = metrics(actual, ensemble)
    return {
        "mae_reduction": baseline_metrics["percentage_mae"] - ensemble_metrics["percentage_mae"],
        "rmse_reduction": baseline_metrics["percentage_rmse"] - ensemble_metrics["percentage_rmse"],
        "within_5_gain": ensemble_metrics["within_5_points"] - baseline_metrics["within_5_points"],
        "within_10_gain": ensemble_metrics["within_10_points"] - baseline_metrics["within_10_points"],
        "dangerous_error_reduction": baseline_metrics["dangerous_error_rate"] - ensemble_metrics["dangerous_error_rate"],
    }


def grouped_bootstrap(
    actual: np.ndarray,
    baseline: np.ndarray,
    ensemble: np.ndarray,
    groups: np.ndarray,
) -> dict[str, dict[str, float]]:
    random = np.random.default_rng(BOOTSTRAP_SEED)
    unique_groups = np.unique(groups)
    positions_by_group = {group: np.flatnonzero(groups == group) for group in unique_groups}
    samples: dict[str, list[float]] = {
        "mae_reduction": [],
        "rmse_reduction": [],
        "within_5_gain": [],
        "within_10_gain": [],
        "dangerous_error_reduction": [],
    }

    for _ in range(BOOTSTRAP_ITERATIONS):
        sampled_groups = random.choice(unique_groups, size=len(unique_groups), replace=True)
        sampled_positions = np.concatenate([positions_by_group[group] for group in sampled_groups])
        differences = metric_differences(
            actual[sampled_positions],
            baseline[sampled_positions],
            ensemble[sampled_positions],
        )
        for name, value in differences.items():
            samples[name].append(value)

    point_estimates = metric_differences(actual, baseline, ensemble)
    return {
        name: {
            "estimate": float(point_estimates[name]),
            "ci_95_low": float(np.percentile(values, 2.5)),
            "ci_95_high": float(np.percentile(values, 97.5)),
            "probability_positive": float(np.mean(np.asarray(values) > 0)),
        }
        for name, values in samples.items()
    }


def dataset_summary(labels: pd.DataFrame, detailed_labels: pd.DataFrame) -> dict[str, Any]:
    percentages = labels["expected_landed_percentage"]
    return {
        "rows": len(labels),
        "repositories": int(labels["repo"].nunique()),
        "pull_requests": int(labels["pr_url"].nunique()),
        "mean_percentage": float(percentages.mean()),
        "median_percentage": float(percentages.median()),
        "zero_rows": int((percentages == 0).sum()),
        "intermediate_rows": int(percentages.between(1, 99).sum()),
        "hundred_rows": int((percentages == 100).sum()),
        "coarse_labels": {str(name): int(count) for name, count in labels["label"].value_counts().items()},
        "label_confidence": {
            str(name): int(count) for name, count in detailed_labels["confidence"].value_counts().items()
        },
    }


def subgroup_metrics(
    holdout: pd.DataFrame,
    actual: np.ndarray,
    baseline: np.ndarray,
    ensemble: np.ndarray,
) -> dict[str, dict[str, Any]]:
    regimes = np.where(actual == 0, "zero", np.where(actual == 100, "hundred", "intermediate"))
    result = {}
    for regime in ("zero", "intermediate", "hundred"):
        selected = regimes == regime
        result[regime] = {
            "rows": int(selected.sum()),
            "baseline": metrics(actual[selected], baseline[selected]),
            "ensemble": metrics(actual[selected], ensemble[selected]),
        }

    language_result = {}
    for language, positions in holdout.groupby("suggestion_language", sort=True).indices.items():
        selected_positions = np.asarray(positions)
        if len(selected_positions) < 5:
            continue
        language_result[str(language)] = {
            "rows": len(selected_positions),
            "baseline": metrics(actual[selected_positions], baseline[selected_positions]),
            "ensemble": metrics(actual[selected_positions], ensemble[selected_positions]),
        }
    result["languages_with_at_least_five_rows"] = language_result
    return result


def plot_target_distribution(internal_labels: pd.DataFrame, hf_labels: pd.DataFrame, output_path: Path) -> None:
    bins = np.arange(-0.5, 110.5, 10)
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=False)
    for axis, title, frame, color in (
        (axes[0], "Internal semantic labels", internal_labels, "#2F6B9A"),
        (axes[1], "Audited external labels", hf_labels, "#D97A31"),
    ):
        axis.hist(frame["expected_landed_percentage"], bins=bins, color=color, edgecolor="white")
        axis.set_title(title)
        axis.set_xlabel("Landed suggestion coverage (%)")
        axis.set_ylabel("Examples")
        axis.set_xlim(-2, 102)
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("Target distributions are concentrated at 0 and 100")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_candidate_comparison(report: dict[str, Any], output_path: Path) -> None:
    display_names = {
        "baseline": "Random Forest",
        "two_stage": "Two-stage CatBoost",
        "catboost_mae": "CatBoost MAE",
        "catboost_huber": "CatBoost Huber",
        "lightgbm_l1": "LightGBM L1",
        "lightgbm_huber": "LightGBM Huber",
        "xgboost_l1": "XGBoost L1",
        "xgboost_pseudohuber": "XGBoost Pseudo-Huber",
    }
    names = list(display_names)
    mae = [report["candidate_oof_metrics"][name]["percentage_mae"] for name in names]
    rmse = [report["candidate_oof_metrics"][name]["percentage_rmse"] for name in names]
    positions = np.arange(len(names))
    width = 0.38
    figure, axis = plt.subplots(figsize=(11, 5))
    axis.bar(positions - width / 2, mae, width, label="MAE", color="#2F6B9A")
    axis.bar(positions + width / 2, rmse, width, label="RMSE", color="#D97A31")
    axis.set_xticks(positions, [display_names[name] for name in names], rotation=28, ha="right")
    axis.set_ylabel("Error in percentage points (lower is better)")
    axis.set_title("Repeated grouped out-of-fold model comparison")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_holdout_error_cdf(
    actual: np.ndarray,
    baseline: np.ndarray,
    ensemble: np.ndarray,
    output_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(7, 4.5))
    for label, predictions, color in (
        ("Random Forest", baseline, "#777777"),
        ("Final ensemble", ensemble, "#2F6B9A"),
    ):
        errors = np.sort(np.abs(actual - predictions))
        cumulative = np.arange(1, len(errors) + 1) / len(errors)
        axis.step(errors, cumulative, where="post", label=label, color=color, linewidth=2)
    axis.axvline(10, color="#D97A31", linestyle="--", linewidth=1.5, label="10-point tolerance")
    axis.set_xlabel("Absolute error (percentage points)")
    axis.set_ylabel("Share of holdout examples")
    axis.set_title("Holdout error distribution")
    axis.set_xlim(left=0)
    axis.set_ylim(0, 1.02)
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_embedding_comparison(report: dict[str, Any], output_path: Path) -> None:
    selected_names = [
        "current_ensemble",
        "unixcoder_two_stage",
        "unixcoder_encoder_two_stage",
        "codebert_two_stage",
        "combined_two_stage",
    ]
    display_names = {
        "current_ensemble": "Current ensemble",
        "unixcoder_two_stage": "UniXcoder",
        "unixcoder_encoder_two_stage": "UniXcoder encoder-only",
        "codebert_two_stage": "CodeBERT",
        "combined_two_stage": "All embedding features",
    }
    available = [name for name in selected_names if name in report["candidate_oof_metrics"]]
    mae = [report["candidate_oof_metrics"][name]["percentage_mae"] for name in available]
    rmse = [report["candidate_oof_metrics"][name]["percentage_rmse"] for name in available]
    positions = np.arange(len(available))
    width = 0.38
    figure, axis = plt.subplots(figsize=(9, 4.8))
    axis.bar(positions - width / 2, mae, width, label="MAE", color="#2F6B9A")
    axis.bar(positions + width / 2, rmse, width, label="RMSE", color="#D97A31")
    axis.set_xticks(positions, [display_names[name] for name in available], rotation=22, ha="right")
    axis.set_ylabel("Error in percentage points (lower is better)")
    axis.set_title("Frozen embedding feature comparison")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_repository_mae_differences(report: dict[str, Any], output_path: Path) -> None:
    repositories = []
    differences = []
    for repository, repository_metrics in report["per_repository"].items():
        if repository_metrics["rows"] < 10:
            continue
        repositories.append(repository)
        differences.append(
            repository_metrics["current_ensemble"]["percentage_mae"]
            - repository_metrics["selected_embedding_blend"]["percentage_mae"]
        )
    order = np.argsort(differences)
    ordered_repositories = np.asarray(repositories)[order]
    ordered_differences = np.asarray(differences)[order]
    colors = np.where(ordered_differences >= 0, "#2F6B9A", "#D97A31")

    figure, axis = plt.subplots(figsize=(9, 7))
    positions = np.arange(len(ordered_repositories))
    axis.barh(positions, ordered_differences, color=colors)
    axis.axvline(0, color="#444444", linewidth=1)
    axis.set_yticks(positions, ordered_repositories)
    axis.set_xlabel("MAE reduction versus current ensemble (percentage points)")
    axis.set_title("Repository-held-out embedding blend results")
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_confidence_comparison(report: dict[str, Any], output_path: Path) -> None:
    confidence_levels = [name for name in ("high", "medium", "low") if name in report["confidence_metrics"]]
    current_mae = [
        report["confidence_metrics"][name]["current_ensemble"]["percentage_mae"]
        for name in confidence_levels
    ]
    embedding_mae = [
        report["confidence_metrics"][name]["selected_embedding_blend"]["percentage_mae"]
        for name in confidence_levels
    ]
    positions = np.arange(len(confidence_levels))
    width = 0.36

    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.bar(positions - width / 2, current_mae, width, label="Current ensemble", color="#777777")
    axis.bar(positions + width / 2, embedding_mae, width, label="Embedding blend", color="#2F6B9A")
    axis.set_xticks(positions, [name.title() for name in confidence_levels])
    axis.set_xlabel("Reference-label confidence")
    axis.set_ylabel("MAE in percentage points (lower is better)")
    axis.set_title("Embeddings help only on high-confidence labels")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/paper"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/pr_suggestion_coverage_regression"))
    args = parser.parse_args()

    assets_dir = args.output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    internal_labels = pd.read_csv("data/processed/pr_suggestion_coverage/dataset/labels.csv")
    hf_labels = pd.read_csv("data/external/github_codereview/dataset/labels.csv")
    internal_detailed_labels = pd.read_json(
        "data/processed/pr_suggestion_coverage/dataset/llm_labels.jsonl", lines=True
    )
    hf_detailed_labels = pd.read_json("data/external/github_codereview/dataset/llm_labels.jsonl", lines=True)
    audit = pd.read_json("data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl", lines=True)
    internal = prepare_features(
        read_source(
            "internal",
            Path("reports/metric_scores.csv"),
            Path("data/processed/pr_suggestion_coverage/dataset/labels.csv"),
        )
    )
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    _, test_positions = next(splitter.split(internal, groups=internal["group_id"]))
    holdout = internal.iloc[test_positions].copy()

    model = joblib.load(args.model_dir / "model.joblib")
    schema = json.loads((args.model_dir / "feature_schema.json").read_text())
    baseline_index = schema["components"].index("baseline")
    baseline_model = model.models[baseline_index]
    features = holdout[FEATURE_COLUMNS]
    actual = holdout["expected_landed_percentage"].to_numpy(dtype=float)
    baseline_predictions = rounded_predictions(baseline_model, features)
    ensemble_predictions = rounded_predictions(model, features)
    comparison = json.loads((args.model_dir / "advanced_model_comparison.json").read_text())
    embedding_report_path = Path("models/pr_suggestion_coverage_embeddings/evaluation_report.json")
    repository_report_path = Path(
        "models/pr_suggestion_coverage_embeddings/repository_held_out/evaluation_report.json"
    )

    results = {
        "generated_from": {
            "model": str(args.model_dir / "model.joblib"),
            "schema": str(args.model_dir / "feature_schema.json"),
            "comparison": str(args.model_dir / "advanced_model_comparison.json"),
            "repository_held_out_embedding_report": str(repository_report_path),
        },
        "datasets": {
            "internal": dataset_summary(internal_labels, internal_detailed_labels),
            "external_hf": dataset_summary(hf_labels, hf_detailed_labels),
        },
        "external_label_audit": {
            "confidence": {str(name): int(count) for name, count in audit["confidence"].value_counts().items()},
            "audit_status": {str(name): int(count) for name, count in audit["audit_status"].value_counts().items()},
            "mean_training_weight": float(audit["training_weight"].mean()),
        },
        "holdout": {
            "rows": len(holdout),
            "pull_request_groups": int(holdout["group_id"].nunique()),
            "baseline": metrics(actual, baseline_predictions),
            "ensemble": metrics(actual, ensemble_predictions),
            "grouped_bootstrap": grouped_bootstrap(
                actual,
                baseline_predictions,
                ensemble_predictions,
                holdout["group_id"].to_numpy(),
            ),
            "subgroups": subgroup_metrics(holdout, actual, baseline_predictions, ensemble_predictions),
        },
        "bootstrap": {
            "iterations": BOOTSTRAP_ITERATIONS,
            "seed": BOOTSTRAP_SEED,
            "sampling_unit": "pull request group",
        },
    }
    plot_target_distribution(internal_labels, hf_labels, assets_dir / "target-distributions.png")
    plot_candidate_comparison(comparison, assets_dir / "candidate-comparison.png")
    plot_holdout_error_cdf(actual, baseline_predictions, ensemble_predictions, assets_dir / "holdout-error-cdf.png")
    if embedding_report_path.exists():
        embedding_report = json.loads(embedding_report_path.read_text())
        results["embedding_experiment"] = {
            "candidate_oof_metrics": embedding_report["candidate_oof_metrics"],
            "selected_blend": embedding_report["selected_blend"],
            "current_holdout": embedding_report["current_holdout"],
            "embedding_holdout": embedding_report["embedding_holdout"],
            "deployment_checks": embedding_report["deployment_checks"],
            "recommended_for_deployment": embedding_report["recommended_for_deployment"],
        }
        plot_embedding_comparison(embedding_report, assets_dir / "embedding-oof-comparison.png")
    if repository_report_path.exists():
        repository_report = json.loads(repository_report_path.read_text())
        results["repository_held_out_embedding_experiment"] = {
            "objective": repository_report["objective"],
            "interpretation_scope": repository_report["interpretation_scope"],
            "training_policy": repository_report["training_policy"],
            "external_rows": repository_report["external_rows"],
            "external_repositories": repository_report["external_repositories"],
            "external_pull_requests": repository_report["external_pull_requests"],
            "overall_micro_metrics": repository_report["overall_micro_metrics"],
            "macro_repository_metrics_minimum_10_rows": repository_report[
                "macro_repository_metrics_minimum_10_rows"
            ],
            "confidence_metrics": repository_report["confidence_metrics"],
            "paired_comparisons_vs_current": repository_report["paired_comparisons_vs_current"],
            "bootstrap": repository_report["bootstrap"],
        }
        plot_repository_mae_differences(
            repository_report,
            assets_dir / "repository-held-out-mae-differences.png",
        )
        plot_confidence_comparison(
            repository_report,
            assets_dir / "repository-held-out-confidence.png",
        )
    (args.output_dir / "analysis_results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

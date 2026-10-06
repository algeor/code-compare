# Reproducibility Guide

**Status:** canonical engineering and research reproduction procedure

**Audience:** contributors, reviewers, model developers, and release engineers

**Purpose:** reproduce supported validation, benchmark, training, calibration, and evaluation workflows

**Scope:** reproduce the checked-in engineering and exploratory evaluation artifacts. This workflow does not convert current labels into human ground truth or make the reported metrics confirmatory.

## 1. Prerequisites

- macOS or Linux;
- Git;
- `uv` compatible with `uv.lock`;
- Python 3.11-3.14 (the checked environment used Python 3.14.6);
- network access for the first dependency sync;
- `libomp` on macOS when running LightGBM experiments.

Never commit `.env`, tokens, Jupyter runtime files, caches, local virtual environments, or IDE metadata. The repository `.gitignore` covers these classes. Credentials previously committed must be rotated and purged from history separately.

## 2. Clean Installation

From the repository root:

```bash
uv lock --check
uv sync --locked --all-extras
```

For the minimal core plus tests:

```bash
uv sync --locked --extra test
```

The organization-private HDLF collector adapter is intentionally not a public dependency. GitHub collection and all core inference imports must work without `fl_shared`; HDLF collection requires the private package at runtime and fails with an actionable message when absent.

## 3. Integrity Checks

Verify every checked-in model before inference:

```bash
uv run --locked python - <<'PY'
from pathlib import Path
from pr_suggestion_metrics.model_artifacts import verify_model_manifest

for model_dir in sorted(Path("models").iterdir()):
    if (model_dir / "model.joblib").is_file():
        manifest = verify_model_manifest(model_dir)
        print(model_dir, manifest["model_name"])
PY
```

The hash manifest provides integrity, not publisher authenticity. Only deserialize trusted `joblib` files.

## 4. Test and Static Validation

```bash
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy \
  src/pr_suggestion_metrics/model_artifacts.py \
  src/pr_suggestion_metrics/model_inference.py \
  src/pr_suggestion_metrics/feature_preprocessing.py
git diff --check
```

Validate notebook syntax without executing external/private collection:

```bash
uv run --locked python - <<'PY'
import json
from pathlib import Path

for path in Path("notebooks").rglob("*.ipynb"):
    json.loads(path.read_text(encoding="utf-8"))
    print(path)
PY
```

## 5. Deterministic Feature Evaluation

Recompute all internal feature rows:

```bash
uv run --locked --extra structural pr-suggestion-evaluate \
  --dataset-dir data/processed/pr_suggestion_coverage/dataset \
  --output /tmp/pr-suggestion-metric-scores.csv
```

Structural features depend on parser availability. Verify parsers first:

```bash
uv run --locked --extra structural pr-suggestion-prepare-parsers
```

Compare the regenerated report by schema, row IDs, row count, and numeric tolerances. Do not overwrite evidence used by a paper without recording hashes and the exact code revision.

## 6. Inference Smoke Tests

Feature-row inference over all 279 internal examples:

```bash
uv run --locked --extra train python - <<'PY'
from pathlib import Path

import pandas as pd
from pr_suggestion_metrics.model_inference import predict_coverage_percentages

rows = pd.read_csv("/tmp/pr-suggestion-metric-scores.csv")
predictions = predict_coverage_percentages(
    rows,
    model_dir=Path("/secure/trusted-percentage-model"),
)
assert len(predictions) == 279
assert predictions["model_predicted_percentage"].between(0, 100).all()
print(predictions.describe())
PY
```

Raw-diff supported/abstention behavior is covered by `tests/test_remediation_regressions.py`. The supported path is intentionally limited to single-file, single-hunk, pure-addition suggestions.

## 7. Training Commands

Use only the frozen benchmark workflow documented below and in `README.md`. The former mixed-corpus training commands, generated score tables, and bundled models are preserved under `research/archive/bucket-era/` for provenance only.

Do not reuse the historical holdout as a confirmatory experiment. A valid final evaluation requires a new frozen test manifest.

## 8. Artifact Record

For every reported run, archive:

- Git commit and dirty-worktree status;
- `uv.lock` SHA-256;
- input data and split-manifest SHA-256 values;
- annotation-guide and label-file versions;
- exact command and environment variables excluding secrets;
- Python/platform/package versions;
- model/schema/manifest hashes;
- stdout/stderr and generated report hashes;
- random seeds and hardware details where relevant.

## 9. Non-Reproducible or External Steps

- Private HDLF collection requires organization-only credentials and dependencies.
- GitHub refreshes depend on mutable remote API state unless commits and responses are archived.
- LLM-owned benchmark labels depend on provider/model/prompt versions and are not human ground truth.
- Existing artifact manifests cannot reconstruct original training runtime details retroactively.
- Embedding downloads require network access and pinned upstream model revisions.

## 10. Confirmatory Reproduction Standard

A reliable confirmatory run must start from an immutable data release, frozen labels, and frozen splits; build features and artifacts in a clean environment; evaluate the untouched test once; and emit one manifest binding code, data, annotations, configuration, model, and reports. LLM-owned labels must be reported as LLM-adjudicated, not human ground truth.

## 11. New Benchmark Workflow

The implementation now enforces that standard for newly collected evidence:

```bash
# Create deterministic PR/repository/near-duplicate-safe assignments.
uv run --locked pr-suggestion-plan-splits \
  --examples data/benchmark-source/examples.jsonl \
  --output /secure/splits.csv \
  --report /secure/split-report.json \
  --policy repository_disjoint

# Create blinded packets. Existing labels and model-derived fields are rejected.
uv run --locked pr-suggestion-prepare-annotations \
  --examples data/benchmark-source/examples.jsonl \
  --annotator llm-pass-a --annotator llm-pass-b \
  --annotation-mode llm \
  --output-dir /secure/annotation-packets

# Freeze only after two independent records and adjudication exist per example.
uv run --locked pr-suggestion-freeze-benchmark \
  --examples data/benchmark-source/examples.jsonl \
  --annotations /secure/annotations.jsonl \
  --adjudications /secure/adjudications.jsonl \
  --splits /secure/splits.csv \
  --annotation-mode llm_adjudicated \
  --split-policy repository_disjoint \
  --output-dir /secure/frozen-benchmark

# Build one canonical feature table from frozen non-test rows.
uv run --locked pr-suggestion-build-features \
  --benchmark-dir /secure/frozen-benchmark \
  --output-dir /secure/frozen-features

# Evaluate compatible existing models on development before training more.
uv run --locked pr-suggestion-select-model \
  --benchmark-dir /secure/frozen-benchmark \
  --candidate-model-dir /secure/current-model \
  --output-dir /secure/model-selection

# Select on development and train without exposing test rows.
uv run --locked pr-suggestion-train \
  --features /secure/frozen-features/features.csv \
  --model-dir /secure/model

# Calibrate intervals from a dedicated non-test table with sufficient independent groups.
uv run --locked --extra train pr-suggestion-calibrate-uncertainty \
  --model-dir /secure/trusted-percentage-model \
  --calibration-data /secure/calibration_features.csv

# Evaluate private test labels once. A receipt blocks accidental repeated use.
uv run --locked --extra train pr-suggestion-evaluate-frozen \
  --benchmark-dir /secure/frozen-benchmark \
  --private-labels /protected-evaluator/test_labels.private.jsonl \
  --receipt /protected-evaluator/receipts/model-v1.json \
  --model-dir /secure/trusted-percentage-model \
  --output-dir /secure/confirmatory-evaluation
```

The current internal corpus can enter this workflow only after provenance reconstruction succeeds and produces complete `benchmark_candidates.jsonl` rows.

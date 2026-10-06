# Getting Started

**Status:** canonical onboarding guide

**Audience:** new contributors, reviewers, and researchers joining the project

**Purpose:** get a new person productive in the first hour without learning everything at once

## 1. First Hour Path

If you only do five things, do these in order:

1. Install dependencies.
2. Run the test suite once.
3. Launch the local demo.
4. Read the architecture map.
5. Pick one supported area before you edit anything.

```bash
uv sync --locked --all-extras
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra demo pr-suggestion-demo
```

Then read:

1. [`../README.md`](../README.md)
2. [`project-guide.md`](project-guide.md)
3. [`architecture.md`](architecture.md)
4. [`reproducibility.md`](reproducibility.md)
5. [`implementation-progress.md`](implementation-progress.md)

## 2. Words You Will See

| Term | Simple meaning |
|---|---|
| Diff | A text view of code changes. |
| Coverage | How much of the suggestion appears in the merged PR diff. |
| Evidence | The exact lines or renames the tool found. |
| Benchmark | The answer key used to test the model. |
| Abstain | The model says, "I can't score this safely." |

## 3. Mental Model

This repository is easiest to understand as **three tools plus research helpers**.

### Tool A: exact evidence

This answers:

> Which suggested change units can we find in the merged PR diff?

Main code:

- `src/pr_suggestion_metrics/diff_semantics.py`
- `src/pr_suggestion_metrics/diff/`
- `src/pr_suggestion_metrics/features/`

### Tool B: experimental percentage score

This answers:

> For a simple supported suggestion, what 0-100 score does the model predict?

Main code:

- `src/pr_suggestion_metrics/model_inference.py`
- `src/pr_suggestion_metrics/model_artifacts.py`
- `src/pr_suggestion_metrics/uncertainty.py`
- `src/pr_suggestion_metrics/modeling/`

### Tool C: AI reviewer grading

This answers:

> How good was an AI review when compared with independent evidence?

Main code:

- `src/pr_suggestion_metrics/reviewer_evaluation.py`

### Research helpers

These commands help create datasets, benchmarks, and training files:

- `src/pr_suggestion_metrics/collection/`
- `src/pr_suggestion_metrics/benchmark/`
- `src/pr_suggestion_metrics/prepare_annotation_packets.py`
- `src/pr_suggestion_metrics/freeze_benchmark.py`
- `src/pr_suggestion_metrics/build_dataset.py`

## 4. Where To Read First In Code

Use this order if you want the smallest useful slice:

1. [`../src/pr_suggestion_metrics/__init__.py`](../src/pr_suggestion_metrics/__init__.py) to see the public API.
2. [`../tests/test_public_api.py`](../tests/test_public_api.py) to see the API boundary enforced.
3. [`../src/pr_suggestion_metrics/analysis_service.py`](../src/pr_suggestion_metrics/analysis_service.py) to understand the top-level composed result.
4. [`../src/pr_suggestion_metrics/model_inference.py`](../src/pr_suggestion_metrics/model_inference.py) to understand percentage prediction.
5. [`../src/pr_suggestion_metrics/reviewer_evaluation.py`](../src/pr_suggestion_metrics/reviewer_evaluation.py) to understand review-quality scoring.
6. [`architecture.md`](architecture.md) for the full package boundaries.

If you start in `research/archive/`, you will get historical context fast, but you will understand the supported system more slowly.

## 5. Common Commands

### Validate before and after a change

```bash
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy src/pr_suggestion_metrics
python3 scripts/check_documentation.py
```

### Run the demo locally

```bash
uv run --locked --extra demo pr-suggestion-demo
```

### Run the analysis CLI on two diff files

```bash
uv run --locked pr-suggestion-analyze \
  --suggested-diff /path/to/suggested.diff \
  --merged-pr-diff /path/to/merged.diff
```

### Build dataset artifacts

```bash
uv run --locked pr-suggestion-build-dataset INPUT.jsonl --output-dir OUTPUT_DIR
```

### Plan frozen benchmark splits

```bash
uv run --locked pr-suggestion-plan-splits \
  --examples OUTPUT_DIR/benchmark_candidates.jsonl \
  --output /secure/splits.csv \
  --report /secure/split-report.json \
  --policy repository_disjoint
```

The full benchmark, training, and confirmatory workflow lives in [`reproducibility.md`](reproducibility.md).

## 6. Where To Work By Goal

If your task is about one of these areas, start here:

| Goal | Start in |
|---|---|
| Public API behavior | `src/pr_suggestion_metrics/__init__.py`, `tests/test_public_api.py` |
| Exact diff matching | `diff_semantics.py`, `diff/`, `features/` |
| Model loading or prediction | `model_inference.py`, `model_artifacts.py` |
| Review-quality scoring | `reviewer_evaluation.py` |
| Data collection | `collection/`, `cli/collect.py` |
| Benchmark freezing | `benchmark/`, `prepare_annotation_packets.py`, `freeze_benchmark.py` |
| Local demo or hosted demo | `demo_gradio.py`, `analysis_service.py`, `space/app.py` |
| Docs or repo-wide framing | `README.md`, `docs/README.md`, the relevant card or guide |

## 7. Important Project Rules

These will save you time:

- The learned raw-diff API is narrow. If input is unsupported, it should say **abstained**.
- Exact evidence is useful, but it still does not prove the suggestion caused the change.
- Current datasets are exploratory. They are not the validated benchmark the project still needs.
- `joblib` model files are trusted-input only. Hashes catch file changes; they do not prove who made the file.
- `research/archive/` is history. Do not make current code depend on it again.
- `uv.lock` is the dependency source of truth.

## 8. Safe First Changes

Good first contributions usually look like one of these:

- tighten or extend tests around existing behavior;
- improve docs and cross-links when behavior already exists;
- add characterization coverage before moving code;
- improve CLI error messages without changing what the command does;
- cleanly extract code within an existing boundary defined in [`architecture.md`](architecture.md).

Riskier changes usually need more design attention:

- changing what the score means;
- widening raw-diff model support;
- reusing archived code in active paths;
- presenting exploratory labels or demo files as validated results.

## 9. What Success Looks Like

After onboarding, a new contributor should be able to do all of this confidently:

- explain the difference between exact evidence and the learned percentage score;
- run tests and the local demo from the repository root;
- find the right module for a bug or feature request;
- know which doc is authoritative for claims, data, models, and workflows;
- avoid turning archived research artifacts into active dependencies by accident.

## 10. Next Reads

- [`architecture.md`](architecture.md) if you are about to edit code.
- [`project-guide.md`](project-guide.md) if you want the history, structure, and common pitfalls in one place.
- [`reproducibility.md`](reproducibility.md) if you are about to run data, benchmark, or model workflows.
- [`data-card.md`](data-card.md) and [`model-card.md`](model-card.md) if you are about to make claims about results.
- [`implementation-progress.md`](implementation-progress.md) if you want the latest shipped state.

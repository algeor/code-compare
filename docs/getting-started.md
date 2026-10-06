# Getting Started

**Status:** canonical onboarding guide

**Audience:** new contributors, reviewers, and researchers joining the project

**Purpose:** get a new person productive in the first hour without learning the whole repository at once

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

## 2. Mental Model

This repository is easiest to understand if you think of it as **three related products plus supporting research infrastructure**.

### Product A: deterministic evidence

This answers:

> Which suggested change units can we find in the merged PR diff?

Main code:

- `src/pr_suggestion_metrics/diff_semantics.py`
- `src/pr_suggestion_metrics/diff/`
- `src/pr_suggestion_metrics/features/`

### Product B: experimental percentage inference

This answers:

> For a narrow raw-diff shape, what percentage does the learned model predict?

Main code:

- `src/pr_suggestion_metrics/model_inference.py`
- `src/pr_suggestion_metrics/model_artifacts.py`
- `src/pr_suggestion_metrics/uncertainty.py`
- `src/pr_suggestion_metrics/modeling/`

### Product C: AI reviewer evaluation

This answers:

> How good was an AI review when compared with independent evidence?

Main code:

- `src/pr_suggestion_metrics/reviewer_evaluation.py`

### Supporting infrastructure

This makes the research workflow reproducible:

- `src/pr_suggestion_metrics/collection/`
- `src/pr_suggestion_metrics/benchmark/`
- `src/pr_suggestion_metrics/prepare_annotation_packets.py`
- `src/pr_suggestion_metrics/freeze_benchmark.py`
- `src/pr_suggestion_metrics/build_dataset.py`

## 3. Where To Read First In Code

Use this order if you want the smallest useful slice:

1. [`../src/pr_suggestion_metrics/__init__.py`](../src/pr_suggestion_metrics/__init__.py) to see the public API.
2. [`../tests/test_public_api.py`](../tests/test_public_api.py) to see the API boundary enforced.
3. [`../src/pr_suggestion_metrics/analysis_service.py`](../src/pr_suggestion_metrics/analysis_service.py) to understand the top-level composed result.
4. [`../src/pr_suggestion_metrics/model_inference.py`](../src/pr_suggestion_metrics/model_inference.py) to understand percentage prediction.
5. [`../src/pr_suggestion_metrics/reviewer_evaluation.py`](../src/pr_suggestion_metrics/reviewer_evaluation.py) to understand review-quality scoring.
6. [`architecture.md`](architecture.md) for the full package boundaries.

If you start in `research/archive/`, you will get historical context fast, but you will understand the supported system more slowly.

## 4. Common Commands

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

## 5. Where To Work By Goal

If your task is about one of these areas, start here:

| Goal | Start in |
|---|---|
| Public API behavior | `src/pr_suggestion_metrics/__init__.py`, `tests/test_public_api.py` |
| Deterministic diff matching | `diff_semantics.py`, `diff/`, `features/` |
| Model loading or prediction | `model_inference.py`, `model_artifacts.py` |
| Review-quality scoring | `reviewer_evaluation.py` |
| Data collection | `collection/`, `cli/collect.py` |
| Benchmark freezing | `benchmark/`, `prepare_annotation_packets.py`, `freeze_benchmark.py` |
| Local demo or hosted demo | `demo_gradio.py`, `analysis_service.py`, `space/app.py` |
| Docs or repo-wide framing | `README.md`, `docs/README.md`, the relevant card or guide |

## 6. Important Project Rules

These will save you time:

- The learned raw-diff API is intentionally narrow and should abstain on unsupported inputs.
- Deterministic evidence is stronger than similarity, but it is still not causal adoption proof.
- Current corpora are exploratory. They are not the validated benchmark the roadmap still calls for.
- `joblib` artifacts are trusted-input only. Manifest hashes protect integrity, not publisher authenticity.
- `research/archive/` is preserved for provenance and should not become a live dependency again.
- `uv.lock` is the dependency source of truth.

## 7. Safe First Changes

Good first contributions usually look like one of these:

- tighten or extend tests around an existing contract;
- improve docs and cross-links when behavior already exists;
- add characterization coverage before moving code;
- improve CLI error messages without changing the underlying contract;
- cleanly extract code within an existing boundary defined in [`architecture.md`](architecture.md).

Riskier changes usually need more design attention:

- changing metric semantics;
- widening raw-diff model support;
- reusing archived code in active paths;
- presenting exploratory labels or demo artifacts as validated results.

## 8. What Success Looks Like

After onboarding, a new contributor should be able to do all of this confidently:

- explain the difference between deterministic evidence and learned percentage output;
- run tests and the local demo from the repository root;
- find the right module for a bug or feature request;
- know which doc is authoritative for claims, data, models, and workflows;
- avoid turning archived research artifacts into active dependencies by accident.

## 9. Next Reads

- [`architecture.md`](architecture.md) if you are about to edit code.
- [`project-guide.md`](project-guide.md) if you want the history, structure, and common pitfalls in one place.
- [`reproducibility.md`](reproducibility.md) if you are about to run data, benchmark, or model workflows.
- [`data-card.md`](data-card.md) and [`model-card.md`](model-card.md) if you are about to make claims about results.
- [`implementation-progress.md`](implementation-progress.md) if you want the latest shipped state.

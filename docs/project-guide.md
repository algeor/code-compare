# Project Guide

**Status:** canonical project overview

**Audience:** contributors, maintainers, reviewers, researchers, and future agents

**Purpose:** explain enough history, structure, workflows, and constraints to become effective in the project quickly

## 1. Project In One Minute

This repository studies **semantic PR suggestion coverage**: how much of a code-review suggestion is represented in a merged pull-request diff.

The current project is a strong research prototype. It has production-quality contracts in several places, but it is not yet a scientifically validated model release.

The safest claim is:

> The project compares suggested diffs with merged PR diffs, returns deterministic evidence, and can produce an experimental coverage percentage for a narrow supported raw-diff shape.

Do not describe the score as proof of adoption, causality, reviewer quality, or final-state semantic equivalence.

## 2. Current Building Blocks

| Building block | Main question | Current status | Start here |
|---|---|---|---|
| Deterministic change evidence | Which suggested change units appear in the merged diff? | Implemented for additions, deletions, renames, moves, multi-file, and multi-hunk evidence | `diff_semantics.py`, `diff/`, `features/` |
| Experimental percentage inference | What 0-100 score does the learned model predict? | Implemented only for single-file, single-hunk, pure-addition raw suggestions | `model_inference.py`, `model_artifacts.py`, `modeling/` |
| Grounded explanation service | How can evidence be explained without unsupported claims? | Implemented with deterministic templates; CodeBERT provider is future work | `analysis_service.py`, `explanations/` |
| AI reviewer evaluation | What did an AI review get right or wrong against independent evidence? | Implemented as a separate construct from coverage | `reviewer_evaluation.py` |
| Benchmark production | How do we create leak-resistant frozen data? | Tooling implemented; valid benchmark still needs new evidence | `benchmark/`, `prepare_annotation_packets.py`, `freeze_benchmark.py` |
| Demo UI | How can the current system be shown locally? | Implemented with Gradio and a weak demo model | `demo_gradio.py`, `space/app.py` |

## 3. History And Pivot Points

### Early research era

The repository began as an exploratory comparison project with notebooks, generated datasets, embedding experiments, bucket/range labels, dashboards, paper assets, and several model attempts.

That era produced useful research context, but its artifacts are no longer the supported path.

### Bucket-era archive

The old bucket/range work was moved under `research/archive/bucket-era/`.

That archive preserves:

- superseded bucket-label experiments;
- historical notebooks and reports;
- old model artifacts;
- generated review examples;
- migration helpers and archive manifests.

Treat it as provenance, not product code. Supported modules must not import from it.

### Current continuous-percentage era

The active project now uses continuous percentages from `0` to `100`, typed diff diagnostics, explicit abstention, versioned evidence/result schemas, deterministic artifact hashes, grouped splits, calibration tooling, and protected-evaluation receipts.

The main current priority is **valid evidence**, not model tuning.

## 4. Repository Map

```text
src/pr_suggestion_metrics/   supported Python package
tests/                      active unit, regression, and contract tests
docs/                       canonical docs and research references
models/                     demo artifact metadata and local weak model bundle
space/                      Hugging Face Space / Gradio app entry point
scripts/                    small repository validation helpers
data/                       active small datasets and source snapshots
reports/                    generated outputs; read with context
notebooks/                  exploratory notebooks, not runtime dependencies
research/archive/           unsupported historical research preserved for provenance
```

If you are new, start in `README.md`, this guide, `docs/architecture.md`, and `docs/reproducibility.md`. Do not start in `research/archive/` unless you are reconstructing history.

## 5. Active Package Structure

```text
analysis_service.py          composed result for CLI, API, and demo surfaces
diff_semantics.py            exact normalized change-unit evidence
model_inference.py           trusted model loading and raw-diff inference
reviewer_evaluation.py       separate AI review quality scoring
artifact_io.py               strict JSONL and atomic artifact helpers
percentages.py               shared percentage validation and rounding
scientific_contracts.py      research contract types

diff/                        unified-diff parsing and diagnostics
features/                    lexical, structural, matching, and scoring features
collection/                  GitHub collection contracts, extraction, gateway, service
benchmark/                   split planning, provenance reconstruction, feature building
modeling/                    training, model selection, and shared evaluation helpers
explanations/                evidence-provider contract and grounded templates
cli/                         command orchestration kept outside core logic
```

Compatibility modules such as `collect_pr_code_changes.py` and `evaluate_metrics.py` are thin shells around newer responsibility modules. New code should import from the responsibility module when possible.

## 6. Main Data Flow

The intended validated path is:

```text
verified suggestion event
  -> provenance-complete candidate
  -> blinded annotation packets
  -> independent labeling and adjudication
  -> grouped split plan
  -> frozen benchmark
  -> canonical feature table
  -> model selection and training
  -> calibration
  -> protected evaluation
  -> versioned release artifact
```

The current demo path is shorter:

```text
suggested diff + merged PR diff
  -> raw-diff assessment
  -> deterministic change evidence
  -> model feature row when supported
  -> weak local percentage model or abstention
  -> deterministic explanation templates
  -> AnalysisResult
```

Unsupported raw-diff shapes should abstain rather than returning a confident-looking score.

## 7. Commands You Should Know

### First setup

```bash
uv sync --locked --all-extras
```

### Validate active code and docs

```bash
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy src/pr_suggestion_metrics
python3 scripts/check_documentation.py
uv build
```

### Run the local demo

```bash
uv run --locked --extra demo pr-suggestion-demo
```

### Run analysis on two diff files

```bash
uv run --locked pr-suggestion-analyze \
  --suggested-diff /path/to/suggested.diff \
  --merged-pr-diff /path/to/merged.diff
```

### Benchmark workflow commands

- `pr-suggestion-plan-splits`
- `pr-suggestion-prepare-annotations`
- `pr-suggestion-freeze-benchmark`
- `pr-suggestion-build-features`
- `pr-suggestion-select-model`
- `pr-suggestion-train`
- `pr-suggestion-calibrate-uncertainty`
- `pr-suggestion-evaluate-frozen`

Use `docs/reproducibility.md` as the command source of truth.

## 8. What Is Current Versus Historical

Current:

- `src/pr_suggestion_metrics/` package code;
- active tests under `tests/`;
- root docs and `docs/*.md` linked from `docs/README.md`;
- demo-only model metadata under `models/pr_suggestion_coverage/demo_weak_local/`;
- Gradio demo entry points.

Historical or reference-only:

- bucket/range experiments under `research/archive/bucket-era/`;
- large generated review examples;
- old reports that reference archived model paths;
- exploratory notebooks;
- legacy bucket labels and range classifiers.

The archive can explain why the project changed direction. It should not define current claims.

## 9. Claims And Language Rules

Use these phrases:

- **suggestion coverage**;
- **semantic agreement**;
- **deterministic evidence**;
- **experimental percentage estimate**;
- **LLM-assisted or weak labels**;
- **LLM-adjudicated benchmark**, when that workflow is used.

Avoid these phrases unless new evidence really supports them:

- **adoption**;
- **causal impact**;
- **validated production model**;
- **human ground truth**, for current labels;
- **final-state semantic equivalence**, when only PR diffs were compared.

## 10. Common Pitfalls

- The deterministic evidence supports more edit shapes than the learned raw-diff API.
- Exact text evidence is still not proof that a suggestion caused a change.
- The current demo model is weak and local. It is useful for showing the interface, not for release claims.
- Current corpora are exploratory and have leakage and provenance limits.
- `joblib` model artifacts are trusted-input only, even when local hashes match.
- Structural feature values can change when optional parser tooling is unavailable.
- Reports in `reports/` may be historical diagnostics; check the linked docs before citing them.

## 11. Reading Path To Mastery

### First hour

1. Read `README.md`.
2. Read `docs/getting-started.md`.
3. Run the validation and demo commands.
4. Read this guide.

### First day

1. Read `docs/architecture.md`.
2. Read `docs/pr-suggestion-diff-metrics.md`.
3. Read `docs/reproducibility.md`.
4. Skim `tests/test_public_api.py`, `tests/test_diff_semantics.py`, and `tests/test_model_inference.py`.

### Before changing research or model behavior

1. Read `docs/data-card.md`.
2. Read `docs/model-card.md`.
3. Read `docs/annotation-guide.md`.
4. Read `docs/implementation-progress.md` and `docs/senior-code-review.md`.

### Before citing historical results

1. Read `research/archive/bucket-era/README.md`.
2. Verify whether the report references archived models or bucket-era labels.
3. Cite the limitation beside the number.

## 12. How To Extend Safely

- Keep source collection separate from feature/model code.
- Keep feature extraction separate from benchmark writing and training.
- Keep runtime inference separate from training commands.
- Version result, evidence, feature, and artifact schema changes.
- Add characterization tests before moving behavior.
- Update the canonical docs in the same change set as behavior changes.
- Preserve explicit abstention for unsupported or invalid inputs.

The project gets stronger when uncertainty is visible. A clean abstention is better than a polished unsupported score.

# Project Guide

**Status:** canonical project overview

**Audience:** contributors, maintainers, reviewers, researchers, and future agents

**Purpose:** explain the project in plain language so a new reader can get useful quickly

## 1. Project In One Minute

This repository studies **PR suggestion coverage**.

Plain meaning: it checks how much of a code-review suggestion appears in the merged pull-request diff.

The current project is a strong research prototype. Some parts are solid and tested. The model is still experimental.

The safest claim is:

> The project compares a suggested diff with a merged PR diff, shows the matching evidence, and sometimes gives an experimental 0-100 score.

Do not describe the score as proof that the suggestion caused the code change.

## 2. Plain Words

| Term | Simple meaning |
|---|---|
| Diff | A text view of code changes. |
| Suggestion | The code change proposed in a review comment. |
| Merged PR diff | The code changes that actually landed in the pull request. |
| Coverage | How much of the suggestion appears in the merged PR diff. |
| Exact evidence | Specific changed lines or renames the tool can point to. |
| Benchmark | An answer key used to test the model. |
| Frozen benchmark | An answer key saved in a fixed version so results cannot quietly change. |
| Abstention | The model refuses to guess because the input is unsupported or unsafe to score. |
| Artifact | A saved file created by the workflow, such as a model, report, or dataset. |
| Provenance | Where an example came from and enough history to trust it. |

## 3. Current Building Blocks

| Building block | Main question | Current status | Start here |
|---|---|---|---|
| Exact evidence | Which suggested changes can we find in the merged diff? | Implemented for many diff shapes | `diff_semantics.py`, `diff/`, `features/` |
| Experimental score | What 0-100 score does the model predict? | Implemented only for simple addition suggestions | `model_inference.py`, `model_artifacts.py`, `modeling/` |
| Explanation service | How do we explain the answer without overclaiming? | Implemented with safe templates; smarter model is future work | `analysis_service.py`, `explanations/` |
| AI reviewer grading | What did an AI review get right or wrong? | Implemented separately from coverage | `reviewer_evaluation.py` |
| Benchmark tools | How do we make a better answer key? | Tools exist; better labels are still needed | `benchmark/`, `prepare_annotation_packets.py`, `freeze_benchmark.py` |
| Demo UI | How can the current system be shown locally? | Implemented with Gradio and a weak demo model | `demo_gradio.py`, `space/app.py` |

## 4. History And Pivot Points

### Early research era

The repository started as an experiment. It had notebooks, generated datasets, old labels, dashboards, paper drafts, and several model attempts.

That era produced useful research context, but its artifacts are no longer the supported path.

### Bucket-era archive

The old bucket/range work was moved under `research/archive/bucket-era/`.

That archive preserves:

- superseded bucket-label experiments;
- historical notebooks and reports;
- old model artifacts;
- generated review examples;
- migration helpers and archive manifests.

Treat it as history, not product code. Current code must not import from it.

### Current continuous-percentage era

The active project now uses scores from `0` to `100`, clear parse errors, explicit abstention, versioned result shapes, file hashes, split planning, calibration tools, and protected evaluation receipts.

The main current priority is **better answer-key data**, not model tuning.

## 5. Repository Map

```text
src/pr_suggestion_metrics/   supported Python package
tests/                      active unit and regression tests
docs/                       current docs and research references
models/                     demo artifact metadata and local weak model bundle
space/                      Hugging Face Space / Gradio app entry point
scripts/                    small repository validation helpers
data/                       active small datasets and source snapshots
reports/                    generated outputs; read with context
notebooks/                  exploratory notebooks, not runtime dependencies
research/archive/           unsupported historical research kept for project history
```

If you are new, start in `README.md`, this guide, `docs/architecture.md`, and `docs/reproducibility.md`. Do not start in `research/archive/` unless you are reconstructing history.

## 6. Active Package Structure

```text
analysis_service.py          composed result for CLI, API, and demo surfaces
diff_semantics.py            exact simplified change-line evidence
model_inference.py           trusted model loading and raw-diff scoring
reviewer_evaluation.py       separate AI review quality scoring
artifact_io.py               strict JSONL and safe file-writing helpers
percentages.py               shared percentage validation and rounding
scientific_contracts.py      research contract types

diff/                        unified-diff parsing and diagnostics
features/                    lexical, structural, matching, and scoring features
collection/                  GitHub collection rules, extraction, gateway, service
benchmark/                   split planning, history reconstruction, feature building
modeling/                    training, model selection, and shared evaluation helpers
explanations/                evidence-provider rules and grounded templates
cli/                         command orchestration kept outside core logic
```

Compatibility modules such as `collect_pr_code_changes.py` and `evaluate_metrics.py` are thin shells around newer responsibility modules. New code should import from the responsibility module when possible.

## 7. Main Data Flow

The intended validated path is:

```text
verified suggestion event
  -> example with enough history to trust
  -> blinded annotation packets
  -> independent labels and disagreement checks
  -> grouped split plan
  -> frozen benchmark
  -> standard feature table
  -> model selection and training
  -> calibration
  -> protected evaluation
  -> versioned release files
```

Plain version:

```text
collect examples
  -> make answer sheets
  -> check disagreements
  -> freeze the answer key
  -> train the model
  -> test once on protected examples
```

The current demo path is shorter:

```text
suggested diff + merged PR diff
  -> raw-diff assessment
  -> exact change evidence
  -> model feature row when supported
  -> weak local percentage model or abstention
  -> safe explanation templates
  -> AnalysisResult
```

Unsupported raw-diff shapes should return **abstained** rather than a confident-looking guess.

## 8. Commands You Should Know

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

## 9. What Is Current Versus Historical

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

## 10. Claims And Language Rules

Use these phrases:

- **suggestion coverage**;
- **semantic agreement**, if you also explain it means "meaning-level overlap";
- **exact evidence**;
- **experimental percentage estimate**;
- **LLM-assisted or weak labels**;
- **LLM-adjudicated benchmark**, when that workflow is used.

Avoid these phrases unless new evidence really supports them:

- **adoption**;
- **causal impact**;
- **validated production model**;
- **production-grade validation labels**, for current labels;
- **final-state semantic equivalence**, when only PR diffs were compared.

## 11. Common Pitfalls

- The exact evidence supports more edit shapes than the learned raw-diff API.
- Exact text evidence is still not proof that a suggestion caused a change.
- The current demo model is weak and local. It is useful for showing the interface, not for release claims.
- Current datasets are exploratory and have trust limits.
- `joblib` model artifacts are trusted-input only, even when local hashes match.
- Some feature values can change when optional parser tools are missing.
- Reports in `reports/` may be historical diagnostics; check the linked docs before citing them.

## 12. Reading Path To Mastery

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

## 13. How To Extend Safely

- Keep source collection separate from feature/model code.
- Keep feature extraction separate from benchmark writing and training.
- Keep runtime scoring separate from training commands.
- Version result, evidence, feature, and saved-file format changes.
- Add characterization tests before moving behavior.
- Update the main docs in the same change set as behavior changes.
- Preserve explicit abstention for unsupported or invalid inputs.

The project gets stronger when uncertainty is visible. A clean "I can't score this" is better than a polished unsupported score.

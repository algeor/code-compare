# Semantic PR Suggestion Coverage

This project checks whether a code-review suggestion shows up in the final merged pull request.

In plain words: it compares **what someone suggested** with **what actually got merged**.

The project currently ships four useful building blocks:

- **Exact evidence:** lines or renames from the suggestion that can be found in the merged PR diff.
- **Experimental score:** a 0-100 estimate for simple supported suggestions.
- **AI review scoring:** a separate way to grade an AI review against known facts.
- **Local demo app:** a small Gradio UI that shows the score, evidence, warnings, and explanation.

## Plain Words

| Term | Simple meaning |
|---|---|
| Diff | A text view of code changes: added lines, removed lines, renamed files. |
| Merged PR | The pull request after it was accepted and merged. |
| Coverage | How much of the suggestion appears in the merged PR diff. |
| Evidence | The specific changed lines or renames the tool found. |
| Benchmark | An answer key used to test whether the model is right. |
| Abstention | The model says, "I can't score this safely," instead of guessing. |

## Start Here

If you are new to the repository, take this path first:

1. Install the workspace.
2. Run the tests.
3. Launch the demo.
4. Read the onboarding guide.

```bash
uv sync --locked --all-extras
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra demo pr-suggestion-demo
```

Then read:

- [`docs/getting-started.md`](docs/getting-started.md) for the first-hour onboarding path.
- [`docs/project-guide.md`](docs/project-guide.md) for the project history, structure, and mastery map.
- [`docs/architecture.md`](docs/architecture.md) for the system boundaries.
- [`docs/README.md`](docs/README.md) for the full documentation map.

## What The Project Does Today

### 1. Exact change evidence

`analyze_change_coverage` compares suggested diff units with merged diff units and reports:

- `strict_same_file`: same file, same kind of change, same simplified text.
- `relaxed_cross_file`: same kind of change and same simplified text, but in a different file.

This is **evidence you can inspect**. It is not proof that the reviewer caused the change.

### 2. Experimental coverage score

`predict_coverage_from_diffs` gives a learned 0-100 score only when the suggestion is simple:

- one file;
- one hunk;
- pure addition;
- not a rename, deletion, or replacement.

If the input is too complex, the model returns **abstained**. That means: "I can't score this safely."

### 3. AI reviewer evaluation

`evaluate_ai_review` grades an AI review against known facts. Every lost point has a concrete reason, such as:

- `incorrect_diagnosis`
- `missed_issue`
- `wrong_location`
- `wrong_severity`
- `unsafe_fix`
- `unsupported_reasoning`

This is separate from suggestion coverage. A merged PR does **not** prove an AI review was correct.

### 4. Grounded local demo

`pr-suggestion-demo` starts the local app and shows:

- exact evidence;
- weak local percentage output;
- a short explanation based on the evidence;
- model versions and artifact hashes.

## What The Project Does Not Claim

Be careful not to overstate what this project can prove:

- It does **not** prove the suggestion caused the change.
- It does **not** prove the final code behaves the same as the suggestion.
- It does **not** ship a production-validated bundled model.
- It does **not** treat current labels as production-grade validation labels.
- It does **not** support every raw-diff shape in the learned API.

The safest current description is: this repository studies **suggestion coverage**, not confirmed adoption.

## Quick Examples

### Run the local demo

```bash
uv run --locked --extra demo pr-suggestion-demo
```

The Gradio app starts locally and uses the demo artifact at `models/pr_suggestion_coverage/demo_weak_local/model`.

### Score one diff pair from Python

```python
from pathlib import Path

from pr_suggestion_metrics import predict_coverage_from_diffs

result = predict_coverage_from_diffs(
    suggested_diff,
    merged_pr_diff,
    model_dir=Path("models/pr_suggestion_coverage/demo_weak_local/model"),
)

print(result.status)
print(result.model_predicted_percentage)
print(result.change_coverage_evidence.strict_same_file.coverage_percentage)
```

### Run the stable analysis service from the CLI

```bash
uv run --locked pr-suggestion-analyze \
  --suggested-diff /path/to/suggested.diff \
  --merged-pr-diff /path/to/merged.diff
```

This returns JSON with the score, evidence, explanation, warnings, and artifact hashes.

### Collect paired examples from GitHub pull requests

```bash
uv run --locked --extra collection pr-suggestion-collect \
  --github-pr-url https://github.com/ORG/REPO/pull/123 \
  --output /tmp/pairs.jsonl
```

Use `--github-token` when needed. The GitHub collector is public; the HDLF collector path remains private-runtime-only.

## Common Workflows

### Validate the active codebase

```bash
uv run --locked --all-extras python -m pytest -q
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy src/pr_suggestion_metrics
python3 scripts/check_documentation.py
uv build
```

### Reproduce the checked-in research workflow

Read [`docs/reproducibility.md`](docs/reproducibility.md). That document is the source of truth for:

- environment setup;
- validation commands;
- benchmark creation;
- model selection and training;
- calibration and protected evaluation.

### Work on the benchmark workflow

The supported flow is:

```text
examples -> split planning -> annotation packets -> adjudication -> frozen benchmark -> feature table -> training
```

Plain version:

```text
examples -> answer sheets -> checked dataset -> model training
```

The main commands are:

- `pr-suggestion-plan-splits`
- `pr-suggestion-prepare-annotations`
- `pr-suggestion-freeze-benchmark`
- `pr-suggestion-build-features`
- `pr-suggestion-select-model`
- `pr-suggestion-train`
- `pr-suggestion-calibrate-uncertainty`
- `pr-suggestion-evaluate-frozen`

## Repository Map

Start with these directories:

```text
src/pr_suggestion_metrics/   supported package code
tests/                      active tests
docs/                       current docs and plans
models/                     demo artifact metadata and local demo model bundle
space/                      Hugging Face Space entry point
scripts/                    small validation helpers
```

Know these before you edit:

```text
data/                       active small datasets and fixtures
research/archive/           unsupported historical work kept for project history
notebooks/                  exploratory notebooks, not runtime dependencies
reports/                    generated outputs
```

If you are new, do **not** start in `research/archive/`. It is intentionally preserved history, not the supported code path.

## Documentation Map

- [`docs/getting-started.md`](docs/getting-started.md) — best first read for a new contributor.
- [`docs/project-guide.md`](docs/project-guide.md) — history, structure, workflows, and pitfalls.
- [`docs/README.md`](docs/README.md) — document index and where each fact should live.
- [`docs/architecture.md`](docs/architecture.md) — package boundaries and data flow.
- [`docs/reproducibility.md`](docs/reproducibility.md) — exact check, benchmark, and training commands.
- [`docs/data-card.md`](docs/data-card.md) — where datasets came from, limits, and allowed claims.
- [`docs/model-card.md`](docs/model-card.md) — what the model can safely do and where it fails.
- [`docs/deployment.md`](docs/deployment.md) — demo deployment guidance.
- [`docs/implementation-progress.md`](docs/implementation-progress.md) — shipped state and next implementation gate.
- [`docs/senior-code-review.md`](docs/senior-code-review.md) — findings, risks, and remaining priorities.

## Public API At A Glance

The package exposes these main public entry points from `pr_suggestion_metrics`:

- `predict_coverage_from_diffs`
- `predict_coverage_percentages`
- `predict_coverage_with_uncertainty`
- `analyze_change_coverage`
- `AnalysisService`
- `evaluate_ai_review`
- `summarize_ai_reviewer`

The public API is checked by [`tests/test_public_api.py`](tests/test_public_api.py).

## Working Agreements

- `uv.lock` is the dependency source of truth.
- Model files are loaded only from an explicit trusted `model_dir`.
- Supported code must not import from `research/archive/`.
- Behavior changes should update the relevant docs, not just code.
- Documentation changes should pass `python3 scripts/check_documentation.py`.

## Next Read

The fastest useful next step for a new person is [`docs/getting-started.md`](docs/getting-started.md).

# Semantic PR Suggestion Coverage

Research tooling for comparing a code-review suggestion with a merged pull request.

The project currently ships four useful building blocks:

- **Deterministic evidence** for exact and path-relaxed diff matches.
- **Experimental percentage inference** for a narrow, explicitly supported raw-diff shape.
- **AI reviewer evaluation** for scoring review quality against independent evidence.
- **A local demo app** that combines the percentage result with grounded explanation templates.

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

### 1. Deterministic change evidence

`analyze_change_coverage` compares suggested diff units with merged diff units and reports:

- `strict_same_file` matches: same path, same operation, normalized content match.
- `relaxed_cross_file` matches: same operation and normalized content, different path allowed.

This is **inspectable evidence**, not semantic proof.

### 2. Experimental coverage percentage

`predict_coverage_from_diffs` produces a learned percentage only when the suggestion is:

- one file;
- one hunk;
- pure addition;
- not a rename, deletion, or replacement.

Unsupported inputs return a typed **abstention** instead of a made-up score.

### 3. AI reviewer evaluation

`evaluate_ai_review` scores an AI review against independently verified assessment units. Every lost point maps to a concrete deduction such as:

- `incorrect_diagnosis`
- `missed_issue`
- `wrong_location`
- `wrong_severity`
- `unsafe_fix`
- `unsupported_reasoning`

This is separate from suggestion coverage. A merged PR does **not** prove an AI review was correct.

### 4. Grounded local demo

`pr-suggestion-demo` wraps the local `AnalysisService` and shows:

- deterministic evidence;
- weak local percentage output;
- grounded explanation templates;
- model versions and artifact hashes.

## What The Project Does Not Claim

Be careful not to overstate the current system:

- It does **not** prove causal adoption.
- It does **not** prove final-state semantic equivalence.
- It does **not** ship a production-validated bundled model.
- It does **not** treat current labels as double-human ground truth.
- It does **not** support every raw-diff shape in the learned API.

The safest current description is: this repository studies **suggestion coverage/agreement**, not confirmed adoption.

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

This returns a JSON result that includes percentage output, deterministic evidence, explanation output, warnings, and artifact hashes.

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

### Reproduce the checked-in research pipeline

Read [`docs/reproducibility.md`](docs/reproducibility.md). That document is the source of truth for:

- environment setup;
- validation commands;
- benchmark freezing;
- model selection and training;
- calibration and protected evaluation.

### Work on the benchmark pipeline

The supported flow is:

```text
examples -> split planning -> annotation packets -> adjudication -> frozen benchmark -> feature table -> training
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
tests/                      active regression and contract tests
docs/                       canonical docs and plans
models/                     demo artifact metadata and local demo model bundle
space/                      Hugging Face Space entry point
scripts/                    small validation helpers
```

Know these before you edit:

```text
data/                       active small datasets and fixtures
research/archive/           unsupported historical work kept for provenance
notebooks/                  exploratory notebooks, not runtime dependencies
reports/                    generated outputs
```

If you are new, do **not** start in `research/archive/`. It is intentionally preserved history, not the supported code path.

## Documentation Map

- [`docs/getting-started.md`](docs/getting-started.md) — best first read for a new contributor.
- [`docs/project-guide.md`](docs/project-guide.md) — history, structure, workflows, and pitfalls.
- [`docs/README.md`](docs/README.md) — document index and source-of-truth rules.
- [`docs/architecture.md`](docs/architecture.md) — package boundaries and data flow.
- [`docs/reproducibility.md`](docs/reproducibility.md) — exact validation, benchmark, and training commands.
- [`docs/data-card.md`](docs/data-card.md) — dataset provenance, limitations, and allowed claims.
- [`docs/model-card.md`](docs/model-card.md) — model contract, failure modes, and validation blockers.
- [`docs/deployment.md`](docs/deployment.md) — demo deployment guidance.
- [`docs/implementation-progress.md`](docs/implementation-progress.md) — what has actually shipped.
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

The lazy export contract is covered by [`tests/test_public_api.py`](tests/test_public_api.py).

## Working Agreements

- `uv.lock` is the dependency source of truth.
- Model files are loaded only from an explicit trusted `model_dir`.
- Supported code must not import from `research/archive/`.
- Active behavior changes should update the relevant canonical docs, not just code.
- Documentation changes should pass `python3 scripts/check_documentation.py`.

## Next Read

The fastest useful next step for a new person is [`docs/getting-started.md`](docs/getting-started.md).

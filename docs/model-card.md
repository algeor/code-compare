# Model Card: Experimental PR Suggestion Coverage Estimator

**Status:** implementation available; no bundled production-validated model
**Primary artifact:** user-supplied trusted percentage model
**Output:** rounded integer estimate from 0 to 100

## 1. Model Purpose

The model estimates an LLM-assisted **semantic agreement/coverage score** between a code-review suggestion and changes in a merged PR. It does not prove that the suggestion caused the code, that matching code was absent before the suggestion, or that it persisted after merge.

## 2. Model and Features

Archived percentage experiments used ensembles of:

- a Random Forest baseline;
- a two-stage endpoint/intermediate model;
- a CatBoost MAE component;
- deterministic lexical, hunk, structural, GumTree availability, and file-overlap features.

The supported training command now selects a percentage regressor from frozen non-test feature rows. Model input is normally a precomputed feature row. The public raw-diff convenience API computes that row only for a deliberately narrow supported case.

Frozen embedding artifacts are research-only. They were not promoted because internal holdout and repository-held-out evidence did not show a consistent practical improvement.

## 3. Intended Use

Permitted use:

- exploratory research on suggestion/merged-diff similarity;
- ranking examples for manual error analysis;
- comparing deterministic feature families;
- prototyping a future validated coverage metric.

The estimate should always be labeled experimental and shown with its limitations.

## 4. Out-of-Scope Use

Do not use the model for:

- causal adoption claims;
- developer/reviewer evaluation or automated decision-making;
- compliance, compensation, or performance scoring;
- unsupported edit types without abstention;
- repositories or languages assumed equivalent without validation;
- untrusted `joblib` artifacts.

## 5. Training and Evaluation Data

- Internal: 279 examples from one repository with LLM-assisted percentages.
- External: 2,500 examples from 29 repositories with weak labels and audit-derived weights.
- Development/test split used by percentage experiments: 209/70 internal rows, grouped by PR.
- Candidate tuning used repeated grouped out-of-fold evaluation.

See `docs/data-card.md` for composition and limitations.

## 6. Reported Results

No active bundled model has confirmatory results. Superseded exploratory artifacts and their reports are preserved under `research/archive/bucket-era/` and must not be presented as current model performance.

## 7. Public Inference Contract

`predict_coverage_percentages` accepts complete metric-feature rows plus an explicit trusted `model_dir` and returns a bounded integer percentage.

`predict_coverage_from_diffs` accepts raw diffs only when the suggestion is:

- one file;
- one hunk;
- pure addition;
- not a rename, deletion, or replacement.

It requires an explicit trusted `model_dir` and abstains before model loading on unsupported suggestions. It returns the same versioned `CoverageResult` shape for predictions and abstentions, including raw and rounded estimates, uncertainty state, applicability reasons, exact evidence, and input/artifact hashes.

The API now returns exact normalized change-unit evidence for additions, deletions, replacements, renames, moves, and multi-file/multi-hunk suggestions. This evidence is explicitly not semantic equivalence. Grouped split-conformal interval support is implemented and cryptographically bound to model/schema bytes, but the checked-in model has no valid held-out calibration artifact; its uncertainty status therefore remains `unavailable`. Out-of-distribution detection remains open.

## 8. Known Failure Modes

- unrelated code in a large PR can look like suggestion coverage;
- pre-existing code can be mistaken for landed code;
- replacements, deletions, moves, renames, and multi-hunk/multi-file suggestions are not modeled by the raw API;
- token/AST similarity can miss behaviorally equivalent code or reward superficial similarity;
- missing structural tooling changes feature availability;
- weak and LLM-assisted targets can encode systematic bias;
- one internal repository cannot establish broad generalization;
- a rounded point estimate hides uncertainty and disagreement.

## 9. Artifact Safety and Versioning

A deployable model directory must contain:

- `model.joblib`;
- `feature_schema.json`;
- `artifact_manifest.json` with SHA-256 hashes and runtime package versions.

Inference verifies model and schema hashes before deserializing. This catches accidental or unauthorized file changes but does not authenticate the publisher. `joblib` uses pickle semantics and can execute code while loading; load only artifacts from a trusted repository/revision.

The repository intentionally does not bundle a model until a bucket-free frozen benchmark and confirmatory evaluation exist.

## 10. Validation Blockers

The model must not be called scientifically validated until all of the following exist:

1. verified suggestion-time and final-state provenance;
2. a frozen unit-level double-human benchmark;
3. removal of label-feature leakage;
4. support or explicit abstention across required edit semantics;
5. a new held-out human-labeled calibration set and a generated uncertainty artifact;
6. repository/time/duplicate-aware frozen splits;
7. one untouched confirmatory evaluation;
8. subgroup and error analysis on the real target population.

## 11. Recommended Claim

Use:

> This exploratory model predicts LLM-assisted semantic-agreement scores from deterministic overlap features and abstains on several unsupported raw-diff cases.

Do not use:

> This metric measures how much suggested code was adopted in a merged PR.

# Implementation Plan

**Status:** active technical execution plan

**Audience:** maintainers and implementation reviewers

**Updated:** 2026-10-06

**Source:** `docs/senior-code-review.md`

**Purpose:** order the remaining work by dependency and risk

## Decision

Implement the review suggestions in this order:

```text
stabilize current cleanup
-> extract stable shared services
-> split the monoliths
-> lock metric semantics
-> harden benchmark production
-> build the human benchmark
-> train and evaluate percentage and explanation models independently
-> compose both models behind one API
-> expand and release the product
```

Do not start by tuning the current model. The main blocker is valid evidence, and the code needs cleaner dependency boundaries before metric behavior changes.

## Current Worktree Note

Repository cleanup is already in progress:

- bucket-era models, reports, notebooks, generated data, code, and documents have archive counterparts under `research/archive/bucket-era/`;
- all 584 files removed from active locations have a mapped archive copy;
- `archive_manifest.json` verifies 586 archive payload files across seven sections;
- repository-root path handling has started moving into `_paths.py`;
- full-package mypy passes for all 28 active source files;
- the active suite contains 88 passing tests after legacy tests moved into the archive.

Phases 0–3 are complete. The active package now has extracted foundations, decomposed orchestration, typed diff
diagnostics, explicit input states, and versioned normalization and evidence contracts. Detailed checkpoints are
recorded in `docs/implementation-progress.md`.

## Order Summary

| Order | Phase | Main findings | Why now |
|---:|---|---|---|
| 0 | Stabilize active migration | F-003, F-006 | Prevent new work from building on an inconsistent archive/removal state. |
| 1 | Extract stable foundations | F-005, F-008 | Reverse bad dependency direction before splitting large modules. |
| 2 | Split orchestration monoliths | F-004 | Make later behavior changes small, testable, and reviewable. |
| 3 | Lock metric contracts | F-014, F-015, F-016 | Correct semantics before generating benchmark features or new models. |
| 4 | Harden benchmark production | F-022, F-027, F-028 | Ensure data creation is balanced, transactional, and reproducible. |
| 5 | Build human benchmark | F-001 | Replace weak labels with valid evidence. |
| 6 | Train and evaluate model bundle | F-033, F-032 | Train percentage and explanation models independently after data and semantics are frozen. |
| 7 | Compose, showcase, and release | F-002, F-007, F-010 | Combine validated model outputs behind one API and expand only where evidence supports it. |

## Phase 0 — Stabilize the Active Migration

**Goal:** restore one trustworthy baseline before further refactoring.

### Implementation order

1. Keep bucket-era research isolated under `research/archive/bucket-era/`; do not expose it through package imports or CLI entry points.
2. Verify the archive inventory with `python3 research/archive/bucket-era/scripts/verify_bucket_archive.py`.
3. Check every active README, script, test, and document for references to removed models, reports, notebooks, prompts, and paper assets.
4. Confirm which archived `data/` files may legally remain in Git and which require external storage.
5. Keep history rewriting out of this phase; it requires a separate explicit decision and coordinated migration.
6. Run the complete test, lint, type-check, build, and installed-wheel smoke suite.

### Exit gate

- Every deletion or move is intentional and documented.
- Active commands do not reference removed paths.
- The archive description matches the archive contents or external location.
- The full supported validation suite is green.
- This migration is reviewable as one isolated change set.

## Phase 1 — Extract Stable Foundations

**Goal:** supported code no longer depends on legacy scripts or private monolith helpers.

### Change set 1: shared domain and I/O

- Create one typed JSONL/CSV read-write layer with consistent row validation and error context.
- Add atomic file and directory promotion helpers for multi-artifact workflows.
- Move percentage/label conversion policy into one domain module.
- Replace duplicated helpers in benchmark, annotation, audit, and evaluation commands.

### Change set 2: deterministic feature service

- Extract supported feature calculation from `evaluate_metrics.py` into `features/` modules.
- Separate lexical, hunk, structural, applicability, and feature-row assembly responsibilities.
- Make `benchmark/build_features.py`, `model_inference.py`, and research scripts consume the same public feature API.

### Change set 3: model evaluation service

- Extract shared regression metrics and feature declarations from `train_percentage_regressor.py`.
- Make `modeling/train.py` depend only on supported modeling/domain modules.
- Leave compatibility re-exports in legacy modules until callers migrate.

### Exit gate

- Supported modules do not import `evaluate_metrics.py` or `train_percentage_regressor.py`.
- No supported module imports underscore-prefixed helpers from another feature area.
- Shared behavior has direct unit tests before legacy callers are redirected.
- Public outputs remain byte- or value-compatible unless a versioned change is declared.

## Phase 2 — Split the Monoliths

**Goal:** isolate I/O, domain logic, orchestration, and CLI concerns.

### Change set 4: evaluation decomposition

Split `evaluate_metrics.py` behind a compatibility facade:

```text
features/lexical.py
features/hunks.py
features/structural.py
features/scoring.py
cli/evaluate.py
```

- Move pure functions first.
- Move optional parser integrations second.
- Keep the old module as a thin import/CLI compatibility layer temporarily.

### Change set 5: collection decomposition

Split `collect_pr_code_changes.py` by external boundary:

```text
collection/github_gateway.py
collection/hdlf_gateway.py
collection/database_gateway.py
collection/provenance.py
collection/service.py
cli/collect.py
```

- Keep HTTP, database, certificate, and retry behavior inside gateways.
- Keep provenance and candidate construction free of network calls.
- Keep argument parsing and console output in the CLI layer.

### Exit gate

- CLI modules contain orchestration, not domain algorithms.
- Gateways can be tested with fake clients without invoking the full command.
- Pure feature/provenance services have focused unit tests.
- Compatibility facades have deprecation notes and removal criteria.

## Phase 3 — Lock Metric Contracts

**Goal:** make parsing and matching semantics explicit before new benchmark features are generated.

**Status:** complete.

### Change set 6: parser diagnostics

- Return typed diagnostics for malformed headers, incomplete hunk counts, unsupported paths, and truncated diffs.
- Distinguish `valid`, `invalid`, and `valid_but_unsupported` inputs.
- Make public inference abstain on structural parse errors.

### Change set 7: normalization policy

- Preserve raw text beside every normalized change unit.
- Define language-aware policies for indentation, whitespace-only changes, literals, and identifiers.
- Version the normalization policy in result and benchmark manifests.
- Add golden tests for Python, YAML, shell, config, docs, and representative rename/move cases.

### Change set 8: strict and relaxed evidence

- Report strict same-file, same-operation evidence separately.
- Report relaxed move/cross-file evidence as a distinct field.
- Prevent token additions from matching removals unless a declared policy allows it.
- Version any changed output contract instead of silently changing existing fields.

### Exit gate

- Invalid diffs never produce plausible-looking partial scores.
- Normalization cannot silently erase meaningful indentation without a declared policy.
- Strict and relaxed evidence are independently inspectable.
- Existing benchmark candidates can be regenerated deterministically under a named policy version.

## Phase 4 — Harden Benchmark Production

**Goal:** make benchmark creation transactional, balanced, and policy-driven.

**Status:** complete.

### Change set 9: deterministic balanced splitting

- Replace component-count ratios with deterministic constrained assignment by example count.
- Preserve repository, PR, time, and near-duplicate grouping.
- Report target versus actual rows and groups per split.
- Fail with an actionable explanation when constraints are infeasible.

### Change set 10: transactional artifacts

- Stage dataset, labels, packets, audit reports, and manifests in a temporary version directory.
- Validate hashes and row relationships before promotion.
- Atomically publish one versioned directory or manifest pointer.
- Never update related semantic artifacts independently.

### Change set 11: externalized audit policy

- Move manual overrides from Python into a versioned input artifact.
- Validate override IDs, authorship, rationale, guide version, and hashes.
- Keep the audit engine reusable and dataset-agnostic.

### Exit gate

- Re-running the same inputs produces the same assignments and hashes.
- Interrupted generation leaves the previous complete version intact.
- Split reports show acceptable row and group balance.
- No dataset-specific curation decisions are hidden in package code.

## Phase 5 — Build LLM-Owned Benchmark v1

**Goal:** create a provenance-complete, LLM-adjudicated benchmark without claiming human ground truth.

### Implementation order

1. Freeze the target population and supported edit semantics.
2. Complete privacy, licensing, retention, and access review.
3. Collect provenance-complete candidates with suggestion-time and final-state snapshots.
4. Run a small LLM annotation pilot to test the guide and prompts.
5. Freeze the guide before full labeling.
6. Run two blinded LLM annotation passes and separate LLM adjudication.
7. Generate balanced grouped splits using Phase 4 tooling.
8. Freeze and hash Benchmark v1 with private test labels externally governed.

### Exit gate

- Every scored example has complete chronology and file provenance.
- Every percentage is reproducible from stored units, weights, and credits.
- Agreement and abstention are reported by repository, language, and edit type.
- The manifest labels the benchmark as `llm_adjudicated_not_human_ground_truth`.
- Test labels remain inaccessible to model development.

## Phase 6 — Train and Evaluate the Model Bundle

**Goal:** produce independently validated percentage and explanation artifacts that can be composed without coupling their training pipelines.

### Change set 12: authoritative group provenance

- Store training, development, calibration, and test group manifests.
- Bind the training-group manifest to the model artifact.
- Verify calibration groups are absent from all fitted groups.

### Change set 13: model selection

- Start with exact, line, token, and constant baselines.
- Use grouped development evaluation and feature-family ablations.
- Promote complexity only when confidence intervals show a robust gain.
- Freeze feature policy, model, thresholds, dependencies, and hashes together.

### Change set 14: calibration and protected evaluation

- Calibrate on the dedicated calibration split only.
- Lock model and abstention policy before test access.
- Run the protected test once using the canonical receipt.
- Publish error analysis, subgroup results, prediction coverage, and a go/no-go decision.

### Change set 15: grounded explanation model

- Train the explanation model separately from the percentage regressor using its own labels, splits, metrics, and artifact manifest.
- Use CodeBERT as an encoder for semantic evidence, classification, retrieval, or ranking; do not treat the encoder alone as a free-form text generator.
- Start with CodeBERT-backed evidence selection plus controlled explanation templates.
- Consider a code-aware encoder-decoder such as CodeT5 only after grounded template quality is measured.
- Require every explanation to reference inspectable matched, missing, or changed evidence.
- Evaluate factual grounding, omission detection, unsupported claims, consistency, and human usefulness separately from percentage error.

### Change set 16: release bundle

- Keep percentage and explanation model artifacts in separate versioned directories.
- Create one release manifest binding both model versions, schemas, dataset manifests, dependencies, and hashes.
- Reject startup when either artifact is missing, incompatible, or fails integrity validation.
- Never merge model weights merely to simplify deployment; compose outputs through a typed runtime service.

### Exit gate

- Calibration-group independence is machine-verifiable.
- The released model beats required baselines with defensible uncertainty.
- One immutable confirmatory report is linked to exact code, data, and artifact hashes.
- Explanation claims are grounded in stored evidence and pass independent release thresholds.
- The release manifest authenticates compatible percentage and explanation artifacts.

## Phase 7 — Compose, Showcase, and Release

**Goal:** expose both validated models through one stable product contract, showcase it on Hugging Face, and expand only what the evidence supports.

### Implementation order

1. Add an `AnalysisService` that validates one input and invokes deterministic evidence, percentage inference, and explanation inference.
2. Return one versioned result containing percentage, uncertainty, matched/missing evidence, grounded explanation, model versions, hashes, abstentions, and warnings.
3. Keep unsupported shapes as explicit abstentions; one model may abstain while the other returns a supported partial result.
4. Package the API and demonstration UI as a Docker-based Hugging Face Space using FastAPI plus Gradio or an equivalent thin UI.
5. Keep the option to move each model to a separate Hugging Face Inference Endpoint later; the API remains the orchestrator.
6. Cache expensive CodeBERT embeddings and allow percentage and explanation workloads to scale independently.
7. Add authenticated model distribution, signatures or attestations, compatibility checks, rollback, health checks, safe logging, and resource limits.
8. Expand learned inference by edit type only when subgroup evidence passes the release gate.
9. Finish moving approved large artifacts to external versioned storage.
10. Decide separately whether Git history should be rewritten; never combine this with normal feature work.
11. Expand mypy and Ruff coverage one cleaned module at a time.

### Exit gate

- Package, CLI, and hosted interface share one result contract.
- Percentage and explanation models can be upgraded or rolled back independently.
- The hosted response identifies both model versions and the evidence used for the explanation.
- Every supported edit type has confirmatory subgroup evidence.
- Model artifacts come from an authenticated distribution channel.
- Full-package type and lint gates pass at the agreed strictness.
- Git contains only approved source, tiny fixtures, manifests, and compact evidence.

## Target Product Architecture

Keep historical exploration, reproducible training, and deployable inference as separate lifecycle layers:

```text
research/archive/               historical collectors, experiments, reports, and abandoned models
collection/                     supported gateways, provenance, and candidate construction
datasets/                       manifests, schemas, hashes, and tiny fixtures; large payloads external
features/                       deterministic parsing, evidence, and shared feature contracts
modeling/percentage/            percentage training, selection, calibration, and evaluation
modeling/explanation/           CodeBERT evidence model and explanation evaluation
inference/percentage.py         percentage artifact loading and prediction
inference/explanation.py        evidence selection and grounded explanation
inference/analysis_service.py   typed composition of both model outputs
api/                            stable request/response schemas and hosted routes
```

### Combined runtime contract

The models share validated inputs and deterministic evidence, but remain independently trained and versioned:

```text
suggested diff + merged diff
        -> parse and validate
        -> deterministic matched/missing evidence
        -> percentage model
        -> explanation evidence model
        -> AnalysisService result
```

The combined result should include at least:

- `coverage_percentage`, raw value, uncertainty interval, and abstention reasons;
- grounded explanation text plus matched, missing, and changed evidence;
- deterministic evidence and input hashes;
- percentage and explanation model names, versions, schema versions, and artifact hashes;
- warnings distinguishing correlation with a merged diff from proof of causal adoption or final-state equivalence.

### Deployment boundary

- Training code never runs in the hosted API process.
- Historical research modules are never imported by supported training or inference entry points.
- The hosted service loads only a validated release bundle and exposes the same result schema as package and CLI callers.
- A Docker-based Hugging Face Space is the first showcase target; separate managed endpoints are a scaling option, not an API redesign.

## Cross-Cutting Rules

Apply these in every phase:

- One behavior change per reviewable change set.
- Add characterization tests before moving legacy logic.
- Keep compatibility facades until all active callers migrate.
- Expand mypy/Ruff gates only for modules cleaned in that phase.
- Update the senior-review finding status when its exit gate passes.
- Never tune against protected test labels.
- Never purge Git history without explicit approval and coordination.

## Parallel Work

These tasks may start early without changing the implementation order:

- **Data governance:** privacy, licensing, retention, and access review can start during Phases 0–3.
- **Annotation staffing:** recruit and train annotators during Phases 3–4; full annotation starts after metric and evidence contracts are locked.
- **Artifact hosting:** evaluate authenticated storage during Phases 1–5; publish the final model only after Phase 6.
- **AI reviewer quality:** keep it as a separate workstream with separate evidence and reports.

## Do Not Do Next

- Do not tune or replace the current ensemble.
- Do not expand raw-diff inference to more edit shapes.
- Do not rewrite both monoliths in one patch.
- Do not enable every lint/type rule at once.
- Do not purge repository history as part of ordinary cleanup.

## Immediate Next Action

Start **Phase 5** by building the human benchmark under the locked metric, split, artifact, and audit-policy contracts.

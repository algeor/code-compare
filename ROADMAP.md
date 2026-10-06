# Project Roadmap

**Updated:** 2026-10-06  
**Project:** Semantic PR Suggestion Coverage  
**Current stage:** strong research prototype; not yet scientifically or production validated

## North Star

Deliver a trustworthy answer to:

> How much of a code-review suggestion is present in the final merged implementation?

The primary output is `suggestion_coverage_percentage`, backed by:

- transparent exact change-unit evidence;
- a calibrated semantic estimate when the input is supported;
- explicit abstention when provenance, applicability, or confidence is insufficient;
- reproducible data, model, and evaluation artifacts.

The score must not be presented as proof that a suggestion caused a code change.

## Current Position

### Completed foundation

- [x] Canonical unified-diff parsing with path, hunk, operation, and rename handling.
- [x] Exact path-aware evidence for additions, deletions, replacements, moves, renames, and multi-file changes.
- [x] Versioned `CoverageResult` with prediction, evidence, warnings, hashes, and abstention reasons.
- [x] Explicit trusted model-directory requirement and artifact-integrity checks.
- [x] Label-free candidate creation, blinded packet preparation, benchmark freezing, and split planning tools.
- [x] Canonical frozen-feature builder and one supported training entry point.
- [x] Group-aware calibration support and protected frozen-test evaluation receipts.
- [x] CI for tests, linting, type checks, optional integrations, wheel builds, and installed-wheel smoke checks.
- [x] Separate evidence-based AI reviewer scoring with concrete deduction reasons.

### Release blockers

- [ ] No provenance-complete, independently annotated human benchmark exists yet.
- [ ] Current model targets are reused LLM-assisted or weak labels with leakage risk.
- [ ] The checked-in model has no valid held-out calibration artifact.
- [ ] Learned raw-diff inference supports only single-file, single-hunk, addition-only suggestions.
- [ ] Generalization across repositories, languages, and edit types is unproven.
- [ ] Research data and generated artifacts still need privacy, licensing, retention, and storage cleanup.

## Delivery Roadmap

### Milestone 1 — Build an Evidence-Ready Corpus

**Goal:** produce label-free examples with trustworthy chronology and repository state.

**Deliverables**

- Define the target population: repositories, languages, suggestion sources, and edit types.
- Collect verified suggestion timestamps, merge commits, and immutable source revisions.
- Store suggestion-time and final-state snapshots for every affected file.
- Resolve renames and multi-file changes without losing file identity.
- Reject or quarantine examples with missing chronology, ambiguous anchors, or incomplete snapshots.
- Complete privacy, licensing, and data-retention review before sharing any corpus.

**Exit gate**

- Every scoreable candidate passes the provenance contract.
- Unsupported candidates remain visible as typed exclusions; they are not silently dropped.
- Dataset version, collection rules, source revisions, and content hashes are recorded.

### Milestone 2 — Freeze Human Benchmark v1

**Goal:** replace weak labels with reproducible semantic-unit judgments.

**Deliverables**

- Freeze the construct and annotation guide before labeling.
- Run blinded annotation with at least two independent trained annotators per test example.
- Store semantic units, weights, landed credits, evidence, abstentions, and original judgments.
- Adjudicate disagreements through a separate reviewer.
- Report agreement overall and by language, repository, edit type, and coverage range.
- Group exact and near duplicates before creating repository/time-aware splits.
- Keep private test labels outside normal development access.

**Exit gate**

- A hash-bound frozen benchmark contains train, development, calibration, and protected test splits.
- No model-derived feature or prior score was visible during annotation.
- Every non-abstained percentage can be recomputed from stored units.

### Milestone 3 — Retrain and Calibrate

**Goal:** select one model using only valid non-test evidence.

**Deliverables**

- Build one canonical feature table from the frozen benchmark.
- Compare exact change-unit, changed-line, token, constant, and current-ensemble baselines.
- Run grouped cross-validation and feature-family ablations on train/development only.
- Prefer the smallest model with a robust, confidence-bounded improvement.
- Fit grouped calibration using raw predictions and independent groups.
- Freeze model, schema, thresholds, dependency versions, and artifact hashes together.

**Exit gate**

- Calibration meets the implementation minimum of 100 rows and 20 independent groups.
- Model selection and abstention thresholds are locked before test-label access.
- The exact baseline remains beside every learned prediction.

### Milestone 4 — Run Confirmatory Evaluation

**Goal:** make one defensible go/no-go decision on the protected test set.

**Deliverables**

- Evaluate the protected test split once and create the consumption receipt.
- Report MAE, RMSE, within-5, within-10, dangerous-error rate, and prediction coverage.
- Report grouped confidence intervals and subgroup calibration.
- Analyze false-high, false-zero, high-uncertainty, and abstained cases.
- Compare model performance with baselines and human repeatability.

**Exit gate**

- Publish one immutable evaluation report linked to dataset, code, model, and environment hashes.
- Record a go/no-go decision for broader inference support and product use.
- If the result is a no-go, return to data or model work without reusing the protected test set.

### Milestone 5 — Harden the Product Path

**Goal:** expose only behavior supported by confirmatory evidence.

**Deliverables**

- Expand multi-file, replacement, deletion, rename, and move inference only where validated.
- Add out-of-distribution detection and stable uncertainty reporting.
- Define model distribution, compatibility, rollback, and deprecation policies.
- Add request limits, timeouts, health checks, structured errors, and safe logging for hosted use.
- Build a demo or API that shows exact evidence, uncertainty, limitations, and abstention clearly.
- Never persist submitted proprietary diffs without explicit authorization.

**Exit gate**

- The package, CLI, and hosted interface return the same versioned result contract.
- Operational tests cover malformed, oversized, unsupported, and adversarial inputs.
- Documentation and UI use the validated claim exactly.

### Milestone 6 — Release and Maintain

**Goal:** make the project easy to audit, install, reproduce, and evolve safely.

**Deliverables**

- Keep obsolete bucket models and legacy LLM labeling isolated under `research/archive/bucket-era/`.
- Move large generated data, caches, and model artifacts to versioned external storage.
- Keep only small public fixtures, schemas, manifests, and compact reports in Git.
- Consolidate superseded plans and historical worklogs under an archive area.
- Publish architecture, security, reproducibility, data-card, and model-card updates.
- Define drift checks, revalidation triggers, ownership, and a release cadence.

**Exit gate**

- A clean installation reproduces the documented smoke test.
- A clean research environment reproduces the released report from pinned inputs.
- CI enforces package, artifact, documentation, and evaluation contracts.

## Immediate Next Deliverable

Create the **first provenance-complete candidate cohort** and run it through:

```text
collect/build candidates
-> plan grouped splits
-> prepare blinded annotation packets
-> annotate and adjudicate
-> freeze benchmark
```

Do not spend the next cycle tuning the current ensemble. Better evidence is the critical path.

## Parallel Track: AI Reviewer Quality

`evaluate_ai_review` measures review quality against independently verified findings. It is useful, but it is a separate construct from suggestion coverage.

- Keep its datasets, reports, and claims separate from coverage-model evaluation.
- Add reporting only when assessment units cite tests, static analysis, specifications, or human verification.
- Do not use merged-code outcomes as correctness ground truth.

## Definition of Done

The project may claim a validated suggestion-coverage metric only when:

- one percentage construct is used across code, research, docs, and UI;
- provenance is complete for every scored example;
- the benchmark is blinded, independent, adjudicated, and frozen;
- duplicates cannot cross data splits;
- uncertainty is calibrated on independent groups;
- protected test evaluation occurs once under explicit governance;
- supported and unsupported edit shapes are documented and enforced;
- model and exact evidence are returned together;
- package behavior matches the installation contract;
- privacy, licensing, security, and retention reviews are complete.

## Supporting Documents

- `IMPLEMENTATION_PLAN.md` — dependency-ordered execution plan for unresolved review findings.
- `README.md` — supported public API and current claim.
- `docs/annotation-guide.md` — semantic-unit labeling protocol.
- `docs/data-card.md` — existing corpus limitations and replacement requirements.
- `docs/model-card.md` — current model behavior, results, and validation blockers.
- `docs/reproducibility.md` — verified research workflow.
- `docs/final-polish-review-2026-09-14.md` — detailed technical and scientific review.

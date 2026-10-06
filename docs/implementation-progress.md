# Senior Review Implementation Progress

**Last updated:** 2026-10-06

This file is the durable implementation log for `IMPLEMENTATION_PLAN.md`.

## Current Phase

- **Phase 0 — Stabilize the active migration:** complete.
- **Phase 1 — Extract stable foundations:** complete.
- **Phase 2 — Split the monoliths:** complete.
- **Phase 3 — Lock metric contracts:** next.
- **Next gate:** malformed diffs cannot produce plausible scores, and normalization/evidence policies are explicit and versioned.

## Completed

- Archived bucket-era code, data, documentation, models, notebooks, reports, and tests under `research/archive/bucket-era/`.
- Added `research/archive/bucket-era/archive_manifest.json` and `scripts/verify_bucket_archive.py`.
- Added archive verification to CI.
- Expanded CI type checking to the full active package.
- Extracted shared path handling to `src/pr_suggestion_metrics/_paths.py`.
- Extracted shared modeling helpers to `src/pr_suggestion_metrics/modeling/common.py`.
- Added shared strict UTF-8 JSONL object parsing and configurable writing in `src/pr_suggestion_metrics/artifact_io.py`.
- Added benchmark split contracts in `src/pr_suggestion_metrics/benchmark/contracts.py`.
- Removed supported imports of private freeze helpers from split planning and annotation packet generation.
- Authenticated frozen split inputs before feature generation.
- Extracted the public deterministic feature API to `src/pr_suggestion_metrics/features/`.
- Reduced `evaluate_metrics.py` to evaluation-specific loading, reporting, CLI orchestration, and compatibility exports.
- Removed active imports from `evaluate_metrics.py` and cross-feature private helpers.
- Centralized strict integer percentages, continuous percentage validation, bounded rounding, and obsolete label fields.
- Added atomic text replacement and staged output-directory promotion primitives.
- Added streaming JSONL parsing while preserving Pydantic line diagnostics and exact serialized bytes.
- Split the feature engine into contracts, lexical, matching, structural, GumTree, and scoring modules.
- Reduced `features/core.py` to a compatibility facade with identity-preserving legacy aliases.
- Split collection into contracts, pure extraction, a GitHub gateway, a gateway-driven service, and CLI orchestration.
- Reduced `collect_pr_code_changes.py` to a compatibility facade and pointed the console script at `cli.collect`.

## Validation Record

- Phase 0 baseline: 88 tests passed; Ruff passed; full-package mypy passed; package build passed.
- Phase 1 final gate: 128 tests and 21 subtests passed on 2026-10-06.
- Ruff passed across `src`, `tests`, and `scripts`.
- Mypy passed across all 34 active source files.
- Source distribution and wheel builds passed.
- Archive verifier: 586 payload files across 7 sections.
- Phase 2 final gate: 139 tests and 21 subtests passed; Ruff, mypy over 46 source files, package build, and archive verification passed.

## Next Implementation Order

1. Add typed diff diagnostics and explicit parser dialects.
2. Gate inference on invalid versus unsupported inputs.
3. Characterize language and indentation normalization.
4. Separate strict and relaxed evidence contracts.
5. Apply transactional staging to multi-artifact workflows.

## Phase 1 Audit Notes

### JSONL boundary

- Safe direct migrations: `audit_semantic_labels.py` and `semantic_labeling_batches.py` readers and writers.
- Hash-sensitive writers in benchmark freeze, packet preparation, feature generation, and frozen evaluation must preserve their current bytes exactly.
- `build_dataset.py` needs a streaming typed reader before migration because it preserves physical line diagnostics and tolerates replacement decoding.
- `collect_pr_code_changes.py` should share only file-artifact writing; stdout streaming remains command-specific.
- `evaluate_metrics.py` currently parses the dataset twice and can silently overwrite duplicate IDs; fix this when its CLI/data-loading shell is separated from deterministic features.

### Deterministic feature boundary

- Active source has three evaluator dependencies: `benchmark/build_features.py`, `model_inference.py`, and `prepare_structural_parsers.py`.
- Extract the feature engine into `features/`; keep dataset loading, reports, CLI arguments, and CSV output in `evaluate_metrics.py`.
- Use a small scoring-input protocol instead of coupling the feature engine to evaluation-only row types.
- Keep public compatibility re-exports in `evaluate_metrics.py` while active callers move to `pr_suggestion_metrics.features`.
- Preserve lazy optional integrations and caches for Pygments, Tree-sitter, and GumTree.
- Runtime parser availability can change generated feature values; make that an explicit reproducibility contract in Phase 3.

### Percentage and publication boundary

- Percentage inputs are parsed inconsistently: strict integer validation, direct `int(...)`, and truncating `int(float(...))` currently disagree.
- Rounding also drifts between benchmark freezing, inference, metrics, and semantic audit; centralize strict label parsing, continuous-value validation, and bounded rounding.
- Do not recreate bucket or coarse-label conversion; those derived fields belong to the archived bucket era.
- Highest atomicity risks are in-place semantic-label application and audit mutation, followed by stale batch files and partially published output directories.
- The sealed-evaluation claim is intentionally fail-closed and must remain outside normal rollback semantics.

## Phase 3 Prepared Findings

- The parser currently accepts malformed hunk headers, incomplete/overflowing hunk counts, invalid body lines, missing marker pairs, partial renames, and non-diff text without typed validity diagnostics.
- Current shape checks can classify malformed input as model-supported, and landed diffs are not structurally validated before feature scoring.
- Add a non-breaking `DiffAssessment` contract with `valid`, `invalid`, and `valid_but_unsupported` states before changing any scoring formulas.
- Distinguish strict `git_unified` input from the internal `suggestion_fragment` dialect because collection intentionally emits bare `@@` pseudo-hunks.
- Preserve `parse_unified_diff()` as a compatibility wrapper while diagnostics are threaded through exact evidence, feature generation, and inference.
- Add characterization tests for malformed structure plus Python indentation, YAML, shell, config, Markdown, and rename/move cases before changing normalization behavior.

## Deferred By Design

- Do not restore bucket-era files to active paths.
- Do not start broad monolith decomposition until Phase 1 dependency direction is clean.
- Do not change metric semantics until Phase 3 contract work.
- Do not run full validation after every small edit; validate coherent change sets.

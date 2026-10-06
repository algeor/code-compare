# Senior Review Implementation Progress

**Last updated:** 2026-10-06

This file is the durable implementation log for shipped phases and the next implementation gate.

## Current Phase

- **Phase 0 — Stabilize the active migration:** complete.
- **Phase 1 — Extract stable foundations:** complete.
- **Phase 2 — Split the monoliths:** complete.
- **Phase 3 — Lock metric contracts:** complete.
- **Phase 4 — Harden benchmark production:** complete.
- **Phase 5 — Build LLM-adjudicated benchmark v1:** next.
- **Next gate:** collect lineage-checked candidates and run LLM-assisted adjudication under the finalized metric and artifact contracts.

## Completed

- Phase 4: added deterministic row-balanced split assignment, split-balance reporting, staged frozen-benchmark publishing, and versioned external manual-audit override policy.
- Archived bucket-era code, data, documentation, models, notebooks, reports, and tests under `research/archive/bucket-era/`.
- Added `research/archive/bucket-era/archive_manifest.json` and `research/archive/bucket-era/scripts/verify_bucket_archive.py`.
- Added archive verification tooling; run it manually before relying on archived provenance.
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

Counts below are historical phase snapshots. For the current validation gate, run the commands in `docs/reproducibility.md`.

- Phase 0 baseline: 88 tests passed; Ruff passed; full-package mypy passed; package build passed.
- Phase 1 final gate: 128 tests and 21 subtests passed on 2026-10-06.
- Ruff passed across `src`, `tests`, and `scripts`.
- Mypy passed across all 34 active source files.
- Source distribution and wheel builds passed.
- Archive verifier: 586 payload files across 7 sections.
- Phase 2 final gate: 139 tests and 21 subtests passed; Ruff, mypy over 46 source files, package build, and archive verification passed.
- Added typed diff diagnostics for strict Git unified diffs and internal suggestion fragments.
- Added explicit `valid`, `invalid`, and `valid_but_unsupported` assessment states and fail-closed inference/feature gates.
- Versioned normalization policy `1.0`, evidence schema `1.1`, and result schema `1.1` in generated artifacts.
- Separated strict same-file evidence from relaxed cross-file evidence and preserved operation polarity in token diagnostics.
- Added malformed-input, language, indentation, rename, evidence, manifest, and inference regressions.
- Phase 3 final gate: 195 tests and 21 subtests passed; Ruff, mypy over 51 source files, package build, archive verification, documentation verification, and whitespace validation passed.
- Phase 4 final gate: 199 tests and 21 subtests passed; Ruff, mypy over 51 source files, package build, archive verification, documentation verification, and whitespace validation passed.

## Checkpoint Commits

- `6a7c7d0` — archive bucket-era research and extract stable foundations.
- `44a9f5a` — split feature and collection monoliths.

## Next Implementation Order

1. Build the LLM-adjudicated benchmark under the locked metric contracts.
2. Collect independent annotations and adjudications.
3. Freeze the benchmark with transactional artifacts.
4. Generate authenticated feature tables.
5. Train percentage and explanation models independently.

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

## Phase 3 Completion Notes

- `DiffAssessment` reports stable diagnostic codes across `git_unified` and `suggestion_fragment` dialects.
- `parse_unified_diff()` remains a compatibility wrapper while assessment drives exact evidence, feature generation, and inference.
- Invalid exact evidence returns `coverage_percentage=None`; invalid inputs cannot produce plausible partial scores.
- Cross-file matching is exposed separately from strict same-file evidence under evidence schema `1.1`.
- Token diagnostics and relaxed matching preserve addition/removal polarity.
- Normalization policy `1.0` and language/indentation characterization tests freeze current behavior without silently changing model features.
- Frozen benchmark and feature manifests record the normalization policy used to generate them.
- Future lexical or structural feature changes require a feature-schema bump and model retraining.

## Phase 3 Independent Review — 2026-10-06

- **P1, fixed:** strict Git headers now accept real paths containing spaces, including ambiguous ` b/` segments resolved by file markers and Git C-quoted paths with escaped UTF-8 octal bytes.
- **P1, fixed:** marker-only file sections now emit `missing_hunk`, so truncated inputs abstain before model loading.
- **P2, fixed:** conflicting `diff --git` and `---`/`+++` paths now emit `conflicting_file_path` diagnostics.
- **P2, fixed:** normalization-policy compatibility is now required in feature rows, feature schemas, model manifests, and inference loading; model schema version is `1.1` and artifact manifest version is `2`.
- **P2, fixed:** normalization policy now names the actual identifier token behavior, `replace_with_IDENT`.

## Deferred By Design

- Do not restore bucket-era files to active paths.
- Do not start broad monolith decomposition until Phase 1 dependency direction is clean.
- Do not change metric semantics until Phase 3 contract work.
- Do not run full validation after every small edit; validate coherent change sets.

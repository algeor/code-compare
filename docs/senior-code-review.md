# Senior Code Review Notes

**Started:** 2026-10-05  
**Scope:** logic, architecture, code quality, data integrity, model safety, and maintainability  
**Status:** completed

This is the live source of truth for review findings. Findings are recorded here as they are discovered rather than held in conversation memory.

## Executive Summary

- The repository now passes its full 128-test suite, configured Ruff checks, full active-package mypy checks, package build, and archive verification.
- Confirmed high-severity defects were fixed in diff parsing, annotation integrity, split leakage, protected evaluation, feature provenance, label ingestion, legacy joins, resumable evaluation, and temporary credential handling.
- The supported runtime is materially safer, but the project remains a research prototype until a provenance-complete independently annotated benchmark exists.
- The next structural priority is to separate supported domain/features/modeling services from the two large collection/evaluation monoliths and legacy experiment entry points.

## Review Method

- Review the repository in independent code-area passes.
- Record evidence before making broad structural changes.
- Fix high-confidence defects and low-risk design problems immediately.
- Keep speculative or high-cost changes as explicit follow-up items.
- Re-run focused tests after each patch and the complete validation suite at the end.

## Baseline

- `pytest`: **77 passed**.
- `ruff check src tests`: **passed**.
- Focused `mypy` validation over supported runtime and benchmark modules: **passed**.
- Existing unrelated untracked files were present before this review: `docs/deployment.md` and `docs/final-polish-review-2026-09-14.md`.

## Final Validation

- `uv run --locked --extra test pytest -q`: **113 passed**.
- `uv run --locked --all-extras pytest -q`: **113 passed**.
- `uv run --locked --extra dev ruff check src tests`: **passed**.
- Mypy over 17 supported runtime and benchmark modules: **passed**.
- Full-package mypy inventory: **54 existing errors in 10 legacy/exploratory files**; tracked as F-010.
- `uv build`: **source distribution and wheel built successfully**.
- Clean external wheel environment: **public import smoke test passed**.
- `git diff --check`: **passed**.

## Findings Log

### F-001 — Scientific evidence is the release bottleneck

- **Severity:** High
- **Area:** product validity
- **Status:** documented; implementation work pending real data
- **Evidence:** the checked-in estimator is trained on reused LLM-assisted or weak labels; no provenance-complete, independently annotated frozen benchmark is present.
- **Risk:** clean code and passing tests can still produce a scientifically unsupported percentage.
- **Action:** prioritize provenance-complete collection, blinded double annotation, adjudication, grouped splits, calibration, and one protected test evaluation.

### F-002 — Learned raw-diff support is narrower than exact evidence

- **Severity:** Medium
- **Area:** API consistency
- **Status:** intentionally guarded
- **Evidence:** exact evidence handles multi-file and richer edit semantics, while learned raw-diff inference abstains outside single-file, single-hunk, addition-only suggestions.
- **Risk:** callers may assume both outputs support the same input space.
- **Action:** preserve explicit abstention and expand learned support only after benchmark evidence exists.

### F-003 — Research artifacts need lifecycle cleanup

- **Severity:** Medium
- **Area:** repository structure
- **Status:** fixed for bucket-era artifacts
- **Evidence:** legacy training programs, embedding experiments, generated datasets, and reports remain beside the supported package path.
- **Risk:** obsolete experiments can appear supported, increase repository weight, and complicate privacy/licensing review.
- **Action:** bucket-era code, tests, models, generated data, reports, notebooks, and documents now live under `research/archive/bucket-era/` with a deterministic inventory manifest. External storage remains tracked separately under F-006.

### F-004 — Two modules are oversized orchestration monoliths

- **Severity:** High
- **Area:** architecture and maintainability
- **Status:** fixed
- **Evidence:** `evaluate_metrics.py` and `collect_pr_code_changes.py` are now thin compatibility/CLI shells. Feature logic is split across contracts, lexical, matching, structural, optional-adapter, and scoring modules; collection is split across contracts, extraction, GitHub gateway, service, and CLI modules.
- **Risk:** changes have broad regression surfaces, unit tests require too much setup, and internal helpers become accidental APIs.
- **Action:** split by responsibility behind compatibility-preserving facades; do not perform a blind file move while logic review is active.

### F-005 — Supported pipelines depend on legacy implementation modules

- **Severity:** High
- **Area:** dependency direction
- **Status:** fixed
- **Evidence:** benchmark feature generation and inference import the supported `features` API, parser preparation imports `features.structural`, and supported training imports `modeling.common`.
- **Risk:** archived experiments cannot be removed safely, and changes to research scripts can break supported runtime paths.
- **Action:** extract stable feature, data-I/O, and model-evaluation services into dedicated package modules, then make both supported and legacy entry points depend on them.

### F-006 — Large generated and potentially sensitive artifacts are tracked in Git

- **Severity:** High
- **Area:** repository hygiene, privacy, and distribution
- **Status:** partially addressed; active paths cleaned, external migration pending
- **Evidence:** 529 of 664 tracked files are under `data/`; the checkout's tracked-file footprint is about 305 MB; Git packs are about 66 MB; individual tracked raw/processed JSONL files are about 50 MB; multiple model binaries are 6–11 MB.
- **Risk:** repository history remains permanently heavy; source/diff material may have privacy or licensing constraints; clones and reviews become slower.
- **Action:** inventory ownership and redistribution rights, move approved artifacts to versioned external storage, retain hashes/manifests and tiny fixtures, and purge history only through a separately approved migration.

### F-007 — Quality gates cover only a narrow lint rule set

- **Severity:** Medium
- **Area:** static analysis
- **Status:** open
- **Evidence:** Ruff still enables only `E4`, `E7`, `E9`, and `F`; full active-package mypy is now enforced, but broader complexity and exception-safety rules remain non-gating.
- **Risk:** complexity, unsafe exception patterns, inconsistent APIs, and typing regressions in legacy/collection modules can pass CI.
- **Action:** first reduce current debt, then incrementally enable broader Ruff families and expand type checking without introducing a noisy all-at-once migration.

### F-008 — Repeated file-format helpers and label mappings can drift

- **Severity:** Medium
- **Area:** duplication
- **Status:** fixed for active shared contracts
- **Evidence:** active JSONL object I/O, atomic artifact primitives, strict/continuous percentage validation, bounded rounding, and obsolete derived-label fields now have shared implementations.
- **Risk:** malformed-row behavior, encoding, atomic writes, and bucket boundaries can diverge across commands.
- **Action:** consolidate stable I/O and label conversion functions after the behavioral review establishes one contract.

### F-009 — Public lazy exports relied on an implicit fallback

- **Severity:** Low
- **Area:** package API
- **Status:** fixed
- **Evidence:** `__getattr__` special-cased some names and routed every other public name to `model_inference`, without an explicit name-to-module contract or caching.
- **Risk:** adding an export from another module could fail at runtime, and repeated attribute access repeated dynamic resolution.
- **Action:** replaced the fallback with an explicit export map, cached resolved attributes, added `__dir__`, and added a complete export-resolution test.

### F-010 — Full-package type checking does not pass

- **Severity:** Medium
- **Area:** correctness and maintainability
- **Status:** fixed for the active package
- **Evidence:** the 54 errors were confined to legacy experiment modules that are now isolated under the bucket-era archive. `mypy src/pr_suggestion_metrics` passes for all 28 active source files.
- **Risk:** archived research remains intentionally unsupported and must not return to the active import graph.
- **Action:** CI now type-checks the complete active package rather than a selected module list.

### F-011 — Client certificate secrets use predictable shared temporary paths

- **Severity:** High
- **Area:** security and collection
- **Status:** fixed
- **Evidence:** `_write_ias_cert_files` writes certificate and private-key material to fixed names under the shared system temp directory, follows any existing path, restricts only the key mode, and `_get_ias_token` does not remove the files.
- **Risk:** concurrent runs can overwrite each other; another local process could pre-create a symlink; credentials remain on disk after token retrieval; the certificate can inherit broader permissions.
- **Action:** credentials now use randomized exclusive files inside a private `0700` temporary directory, both files use `0600`, and context-managed cleanup covers request success and failure.

### F-012 — File-marker-like hunk content corrupted diff parsing

- **Severity:** High
- **Area:** diff parser correctness
- **Status:** fixed
- **Evidence:** changed lines beginning with `--- a/` or `+++ b/` were interpreted as file headers before hunk content was considered.
- **Risk:** valid changed lines could split a parsed file and silently corrupt exact evidence and downstream features.
- **Action:** track declared hunk line counts and treat file markers as metadata only outside an active counted hunk; added regressions for marker-like content and the following file header.

### F-013 — Greedy duplicate matching created avoidable cross-file moves

- **Severity:** Medium
- **Area:** exact evidence logic
- **Status:** fixed
- **Evidence:** one-pass matching could consume a duplicate line from the wrong file before a later same-file suggestion used it.
- **Risk:** order-dependent evidence overstated moved code even when a globally valid same-path match existed.
- **Action:** reserve all exact same-path matches first, then assign remaining content-equivalent cross-file matches through one-to-one queues.

### F-014 — Diff normalization can erase meaningful syntax

- **Severity:** Medium
- **Area:** metric semantics
- **Status:** open; contract decision required
- **Evidence:** whitespace normalization collapses indentation and internal whitespace, and whitespace-only changed lines are excluded.
- **Risk:** indentation-sensitive code can be counted as exact after a semantic change, while formatting-only obligations cannot be represented.
- **Action:** define language-aware normalization policies and preserve the raw unit beside every normalized unit before changing scoring behavior.

### F-015 — Malformed diffs can produce plausible metrics without diagnostics

- **Severity:** Medium
- **Area:** input validation
- **Status:** open
- **Evidence:** malformed hunk headers can fall back to line number zero; declared hunk counts are not currently surfaced as validity errors when the body is incomplete.
- **Risk:** truncated or invalid diffs may return partial-looking evidence rather than an abstention.
- **Action:** add parser diagnostics and make supported inference abstain on structural parse errors.

### F-016 — Some fallback similarity metrics ignore edit context

- **Severity:** Medium
- **Area:** metric validity
- **Status:** open
- **Evidence:** token overlap ignores operation polarity and file identity; cross-file exact fallback can match common normalized lines anywhere.
- **Risk:** additions can match removals or unrelated common code, inflating apparent coverage.
- **Action:** make operation/path policy explicit and report strict same-file evidence separately from relaxed move evidence.

### F-017 — Benchmark freeze accepted inconsistent annotation sets

- **Severity:** High
- **Area:** benchmark data integrity
- **Status:** fixed
- **Evidence:** annotations for unknown examples were ignored; more than two annotators were accepted although agreement logic used inconsistent subsets; guide versions and adjudication linkage were not fully enforced.
- **Risk:** a frozen benchmark could report misleading agreement or include evidence that was not produced under one protocol.
- **Action:** reject unknown records, duplicate records across versions, counts other than exactly two independent annotators, guide-version mismatch, incomplete source-annotator linkage, and adjudications for quarantined examples.

### F-018 — Programmatic split-policy bypass and unstable temporal ordering

- **Severity:** High
- **Area:** leakage prevention and reproducibility
- **Status:** fixed
- **Evidence:** direct callers could pass an unsupported policy string and skip the intended repository/temporal validation; equal timestamps inherited input order; naive timestamps could reach aware comparisons.
- **Risk:** leakage controls could be silently bypassed and equivalent inputs could yield unstable assignments.
- **Action:** validate policies fail-closed, require timezone-aware timestamps, normalize to UTC, and use stable component identity as a temporal tie-breaker.

### F-019 — Frozen evaluation silently collapsed bad IDs and percentages

- **Severity:** High
- **Area:** evaluation integrity
- **Status:** fixed
- **Evidence:** duplicate test/private-label IDs were collapsed by dictionary construction, and labels/predictions were not uniformly checked for finite values in `[0, 100]`.
- **Risk:** confirmatory metrics could be silently distorted or become non-finite.
- **Action:** require present unique IDs, verify prediction-to-input identity, and reject non-numeric, non-finite, or out-of-range percentages before reporting.

### F-020 — One-shot evaluation receipt is not a complete governance lock

- **Severity:** High
- **Area:** protected test governance
- **Status:** fixed locally; external governance still required
- **Evidence:** receipt creation uses a check-then-write flow and accepts a caller-selected path.
- **Risk:** concurrent or deliberately redirected runs can evaluate the same private labels more than once.
- **Action:** evaluation now atomically creates canonical `CONFIRMATORY_TEST_CONSUMED.json` inside the benchmark before private-label access. Custom receipt paths are compatibility copies only. Failures after the claim remain fail-closed; external governance is still required for truly private labels.

### F-021 — Feature generation does not authenticate frozen split inputs

- **Severity:** High
- **Area:** artifact integrity
- **Status:** fixed
- **Evidence:** feature generation hashes files for its output manifest but does not first compare consumed split files with the frozen benchmark manifest.
- **Risk:** edited train/development/calibration rows can enter model training while still appearing to come from the frozen benchmark.
- **Action:** require `benchmark_manifest.json`, verify every non-test split hash before creating output, and bind the feature manifest to the exact benchmark-manifest hash.

### F-022 — Split targets count components instead of examples

- **Severity:** Medium
- **Area:** benchmark quality
- **Status:** open
- **Evidence:** assignment ratios are based on independent component count; component sizes may differ substantially.
- **Risk:** train, development, calibration, or test row counts can be severely imbalanced even when the nominal ratios look correct.
- **Action:** use a deterministic constrained assignment that balances example counts while preserving repository, time, PR, and duplicate grouping.

### F-023 — Legacy training silently changed the training population

- **Severity:** High
- **Area:** training data integrity
- **Status:** fixed
- **Evidence:** unchecked inner joins dropped unmatched score/label rows and could multiply duplicate IDs; invalid percentages were clipped into `[0, 100]` instead of rejected.
- **Risk:** corrupt labels could become valid-looking targets and reported sample counts could differ from source data without warning.
- **Action:** require unique IDs and equal score/label identity sets, use validated one-to-one joins, and reject missing, non-finite, or out-of-range targets.

### F-024 — Semantic-label ingestion accepted ambiguous output

- **Severity:** High
- **Area:** labeling data integrity
- **Status:** fixed
- **Evidence:** duplicate LLM outputs overwrote earlier rows, unknown example IDs were accepted, fractional percentages were truncated, and batch counts were wrong for empty or exact-multiple datasets.
- **Risk:** label files could silently attach the wrong or altered ground truth to examples.
- **Action:** reject duplicate, missing, unknown, fractional, and out-of-range labels; compute batch counts from emitted batches.

### F-025 — Repository-held-out resume could mix stale or partial folds

- **Severity:** High
- **Area:** experimental evaluation integrity
- **Status:** fixed
- **Evidence:** resume fingerprints did not include input/model file contents, and any rows for a repository marked that fold complete.
- **Risk:** changed datasets or artifacts could be combined with stale predictions and reported as one evaluation.
- **Action:** bind fingerprints to input contents, validate fold completeness, and replace checkpoints atomically.

### F-026 — Legacy cross-source training may leak pull requests

- **Severity:** High
- **Area:** evaluation leakage
- **Status:** fixed
- **Evidence:** legacy trainers append external rows to internal folds without rejecting shared example or PR identities across sources.
- **Risk:** the same review outcome can appear in both training and holdout data under different source labels.
- **Action:** all six cross-source legacy entry points now reject normalized example-ID or pull-request identity overlap before splitting. PR identity ignores scheme, query, fragment, trailing path, leading number zeroes, case, and a repository `.git` suffix; missing or unparseable identities do not collide.

### F-027 — Multi-file semantic outputs are not transactional

- **Severity:** Medium
- **Area:** artifact consistency
- **Status:** open
- **Evidence:** semantic apply/audit commands replace related dataset, label, batch, and audit files independently.
- **Risk:** interruption can leave artifacts from different logical versions mixed together.
- **Action:** stage a complete output generation in a temporary directory, validate it, then atomically promote a versioned directory or manifest pointer.

### F-028 — Dataset-specific audit policy is hard-coded in reusable code

- **Severity:** Medium
- **Area:** separation of concerns
- **Status:** open
- **Evidence:** manual semantic-label overrides live inside the Python audit module.
- **Risk:** changing one dataset's curation policy changes package code and obscures provenance.
- **Action:** move overrides into a versioned, hash-bound input artifact and keep the audit engine dataset-agnostic.

### F-029 — Official training allowed groups to cross data splits

- **Severity:** High
- **Area:** model leakage
- **Status:** fixed
- **Evidence:** the same `group_id` could appear in train, development, and calibration rows; split names and target domains were not fully validated.
- **Risk:** model selection and conformal calibration could reuse related examples and report optimistic performance.
- **Action:** normalize and validate supported split labels, reject empty groups and any cross-split group overlap, validate finite `[0, 100]` targets, and reject invalid or empty candidate configurations.

### F-030 — Calibration accepted non-calibration data

- **Severity:** High
- **Area:** uncertainty validity
- **Status:** fixed
- **Evidence:** calibration rejected test rows but accepted train/development rows even when an explicit `split` column was present.
- **Risk:** intervals could be calibrated on training residuals and appear narrower than warranted.
- **Action:** require only `calibration` rows whenever split metadata exists; reject blank groups, non-finite targets/predictions, and malformed conformal inputs.

### F-031 — Trusted model schema was validated after unpickling

- **Severity:** Medium
- **Area:** artifact loading
- **Status:** fixed
- **Evidence:** bundle hashes were checked before `joblib.load`, but schema structure and manifest/schema model identity were checked afterward.
- **Risk:** malformed bundles failed later than necessary and loaded executable pickle content before deterministic metadata rejection.
- **Action:** validate schema structure and manifest consistency first; reject malformed hashes and symlinked artifacts; validate prediction shape and finiteness before clipping.

### F-032 — Local artifact hashes do not authenticate a publisher

- **Severity:** Medium
- **Area:** supply-chain security
- **Status:** open by design
- **Evidence:** an attacker able to replace a model can also replace its adjacent manifest and hashes; `joblib` uses executable pickle semantics.
- **Risk:** untrusted artifact distribution can lead to arbitrary code execution during load.
- **Action:** distribute model bundles through an authenticated, access-controlled channel and bind release signatures or attestations outside the local manifest.

### F-033 — Calibration provenance lacks an authoritative group registry

- **Severity:** Medium
- **Area:** research governance
- **Status:** open
- **Evidence:** calibration now enforces split labels, but there is no independent registry proving those groups were never used during model fitting.
- **Risk:** mislabeled or manually edited input can still violate calibration independence.
- **Action:** bind training and calibration group manifests into the model artifact and verify disjointness when calibration is generated.

## Implemented Changes

- Added `ROADMAP.md` with evidence-first milestones and measurable exit gates.
- Linked the roadmap from `README.md`.
- Made package-level lazy exports explicit, cached, discoverable, and covered by a public-API test.
- Corrected diff parsing for header-like content inside hunks.
- Made duplicate exact matching globally prefer same-path evidence before cross-file fallback.
- Hardened benchmark freezing against inconsistent annotations and guide versions.
- Made split policy validation fail closed and temporal ordering deterministic.
- Hardened protected evaluation against duplicate IDs and invalid percentages.
- Added an atomic, non-redirectable canonical claim for protected test consumption.
- Bound feature generation to the frozen benchmark manifest and split hashes.
- Secured temporary certificate/key handling and guaranteed cleanup.
- Hardened legacy score/label joins and target validation.
- Hardened semantic label ingestion and batching.
- Bound resumable repository-held-out evaluation to exact inputs and complete folds.
- Added shared cross-source identity validation before legacy training and evaluation splits.
- Prevented group leakage across official train, development, and calibration splits.
- Hardened calibration split, group, target, and prediction validation.
- Moved schema and manifest consistency checks before model deserialization.
- Added strict shared JSONL readers/writers, streaming readers, exact-line writers, atomic text replacement, and staged-directory promotion.
- Added one percentage-policy module for integer labels, continuous values, bounded rounding, and obsolete derived fields.
- Extracted deterministic feature and structural-parser APIs from `evaluate_metrics.py` while preserving compatibility exports.
- Removed active imports from `evaluate_metrics.py`, archived training modules, and cross-feature private helpers.
- Split the deterministic feature engine by responsibility behind a compatibility facade.
- Split collection into contracts, pure extraction, GitHub gateway, service, and CLI modules with fake-gateway tests.

## Next Priorities

1. Lock parser diagnostics and explicit strict-versus-fragment input dialects.
2. Version normalization and strict-versus-relaxed evidence contracts.
3. Make multi-artifact benchmark workflows transactional using the new staging primitives.
4. Replace component-count splitting with deterministic example-balanced assignment.
5. Build the provenance-complete human benchmark described in `ROADMAP.md`.

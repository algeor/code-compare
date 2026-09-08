# Graduation Codebase Review: Semantic Suggestion Coverage

**Review date:** 2026-09-08

**Reviewed commit:** `d149dbb` (`main`) plus the existing uncommitted paper/embedding-evaluation work

**Review posture:** master’s graduation review, with production-safety criteria

**Target claim:** estimate what percentage of a code suggestion landed in a merged pull request

## 1. Executive Verdict

### Decision

**Major revision required.**

The repository is a promising exploratory research prototype. It is **not yet a defensible production metric** and should not currently be described as measuring the true percentage of suggested code that landed.

The strongest current implementation is a bounded ensemble over deterministic overlap features. The engineering work is substantial, the current paper is unusually honest about several limitations, and PR-grouped splitting is a sound improvement over row-level splitting. However, the central scientific construct, data provenance, and production boundary remain unresolved.

### What the current number actually means

The deployed output is best described as:

> A model-predicted agreement score, from 0 to 100, learned from LLM-assisted judgments over selected suggestion/PR-diff pairs.

It is **not yet** safely interpretable as:

> The measured percentage of a suggestion that was adopted because of the suggestion and exists in the final merged code.

The distinction matters. The current system observes similarity inside a PR diff. It does not prove chronology, causality, persistence in the merge result, or coverage of all meaningful suggestion units.

### Graduation blockers

1. **No end-to-end inference contract.** Public inference requires an already-computed 36-column metric row instead of accepting a suggestion and merged diff.
2. **No defensible ground truth.** The 279 internal labels and 2,500 external labels are primarily LLM-generated; only 20 external examples have explicit manual overrides.
3. **Label leakage and anchoring.** The labeler sees weak labels and deterministic overlap values that are later used as model features.
4. **Invalid suggestion-time provenance.** All 279 internal rows record `inspection_commit_sha == merge_commit_sha`; comment timestamps and original review anchors are absent.
5. **The percentage lacks an auditable denominator.** Internal labels do not persist semantic units or unit weights.
6. **The same small holdout has guided repeated deployment decisions.** It is no longer an untouched test set.
7. **Core change semantics are incomplete.** Deletions are ignored, multiple suggestion hunks are collapsed to one best match, and unrelated PR changes can become candidates.
8. **The repository is not reproducible from its declared setup.** Paths still point to the former `ml/` layout, requirements are unpinned and incomplete, and collection cannot import in the supplied environment.

### Positive assessment

- PR-grouped splitting is directionally correct.
- The current paper explicitly admits weak labels, one-repository internal data, adaptive holdout reuse, and the failed embedding deployment attempt.
- The deployed percentage artifact returns bounded values and correctly returns `0` for an all-zero feature row.
- The current ensemble has a conservative disagreement fallback.
- Repository-held-out embedding evaluation is a meaningful improvement over a random external row split.
- The embedding experiment was not promoted after failing the internal holdout gates.
- The focused test suite passes: **18/18 tests**.
- Structural parser smoke checks pass for Python, C, C++, Go, HTML, Java, JavaScript, Rust, and TypeScript in the current local environment.

## 2. Scope and Evidence

This review covered:

- collection and pairing;
- dataset construction;
- LLM-label preparation and auditing;
- deterministic feature extraction;
- percentage-model training and selection;
- embedding generation and evaluation;
- production inference helpers;
- notebooks and documentation;
- stored datasets, reports, model artifacts, caches, and repository hygiene;
- test coverage and focused runtime checks.

No implementation files or existing user-generated artifacts were modified during the review. This document is the only added file.

### Validation performed

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .ml-venv/bin/python -m unittest discover -s tests -v`
  - Result: **18 tests passed**.
- Evaluator with explicit paths:
  - Result: succeeded on 279 internal examples and wrote `/tmp/code-compare-review-eval/metric_scores.csv`.
- Evaluator with defaults:
  - Result: failed because its dataset default resolves to `/Users/I551270/Documents/GitHub/ml/...`.
- Evaluator with only an explicit dataset:
  - Result: completed scoring and then failed because `ml/reports/` does not exist and the writer does not create it.
- Collector import in `.ml-venv`:
  - Result: failed at `pydantic`; the dependency is not declared or installed.
- Dataset consistency validator:
  - Result: both current internal and external datasets passed their existing label/bucket consistency checks.
- Current percentage-model smoke test:
  - Result: inference loads and returns bounded integer predictions.
- Numeric boolean input test:
  - Result: all integer `1` boolean features were silently converted to `0`.

### Remediation checkpoint — 2026-09-08

The first corrective slice has been implemented after the initial review:

| Finding | Status | Implemented change |
|---|---|---|
| Repository hygiene / exposed runtime credentials | Partially remediated | Removed all 45 tracked machine-generated artifacts from the working tree: Jupyter runtime/configuration, IDE metadata, Finder metadata, Python bytecode, Matplotlib caches, and compiled Tree-sitter caches. Ignore rules now cover those classes. Secret rotation, Git-history purging, and committing the deletions still require repository-owner action. |
| G-21 — incomplete root migration | Partially remediated | Evaluator dataset/output defaults and semantic-labeling prompt defaults now resolve from the repository root. The score writer creates missing output directories. Historical notebook and documentation paths remain to be migrated. |
| G-20 — private collection coupling | Partially remediated | Package-level inference exports are now lazy, so importing `pr_suggestion_metrics` no longer forces model dependencies. Public collection dependencies are grouped separately, but the collector still imports the organization-private `fl_shared` package and must be split behind an adapter. |
| G-22 — incomplete dependencies | Partially remediated | Added `pyproject.toml`, declared Python 3.11–3.14 support, grouped structural/training/embedding/collection/notebook/development dependencies, exposed five CLI entry points, generated a 153-package `uv.lock`, and exported 143 pinned runtime requirement entries. Artifact/runtime version binding remains open. |
| G-15 — unsafe boolean coercion | Partially remediated | Training and inference now share strict coercion for booleans, numeric `0`/`1`, and explicit `"true"`/`"false"`/`"0"`/`"1"` strings. Invalid values raise an indexed validation error. Strict numeric/range validation remains open. |
| G-23 — dropped zero labels | Remediated | Dataset CSV writing now preserves a legitimate `0` percentage. |

Validation after this slice:

- Added **7 regression tests** for defaults, output-directory creation, zero serialization, and boolean handling.
- Verified that **zero ignored tracked artifacts remain on disk** and that the cleanup staged no unrelated changes.
- Full suite: **25/25 tests passed**.
- Evaluator smoke test: loaded the default in-repository dataset, scored all **279 examples**, and wrote to a new temporary output directory.
- Clean-package validation: installed the locked core, structural, training, and test groups into a temporary Python 3.14 environment.
- Distribution validation: built both the source archive and wheel, and verified all **5 console entry points**.
- Clean-environment suite: **26/26 tests passed**; focused Ruff and mypy checks passed.
- `git diff --check`: passed.

This checkpoint improves repository safety and prevents known data corruption. It does **not** change the major-revision verdict or make the metric scientifically valid; the construct, labels, provenance, matching semantics, split policy, and raw-input API remain graduation blockers.

## 3. Required Definition of the Metric

### 3.1 Define the construct before tuning another model

The phrase “percentage of suggested code that landed” currently mixes four different ideas:

1. **Textual coverage:** how many suggested lines/tokens appear in the result.
2. **Structural coverage:** how much of the suggested syntax/control structure appears.
3. **Behavioral coverage:** how many intended behaviors are implemented.
4. **Causal adoption:** how much was implemented because of the suggestion.

The repository currently approximates the first three and sometimes describes the result as the fourth. Causal adoption cannot be inferred from a final diff alone.

The thesis and API should use one explicit primary construct:

> **Semantic suggestion coverage:** the weighted fraction of meaningful units in a suggestion that are present in the final merged implementation, regardless of textual form.

Use “adoption” only when temporal and provenance checks support it. Otherwise use “coverage” or “agreement.”

### 3.2 Give the percentage a denominator

For suggestion units `u_i`, human-assigned importance weights `w_i > 0`, and landed-credit values `c_i` in `[0, 1]`:

```text
coverage = 100 * sum(w_i * c_i) / sum(w_i)
```

Recommended unit-credit rubric:

```text
1.00  landed exactly or behaviorally equivalently
0.50  landed partially
0.00  absent or replaced by behavior outside the suggestion
```

The exact partial-credit rule can differ, but it must be fixed before annotation and persisted with every label. Without stored units, weights, and credits, `73%` is a subjective score, not a reproducible percentage.

### 3.3 Required output contract

A safe result should include more than one integer:

```json
{
  "coverage_percentage": 73,
  "confidence": 0.81,
  "interval": [62, 84],
  "decision": "estimated",
  "matched_units": [],
  "unmatched_units": [],
  "warnings": [],
  "model_version": "...",
  "feature_version": "..."
}
```

Allow `decision: "abstain"` when the input is unsupported, causally ambiguous, too large, malformed, or out of distribution.

## 4. Current End-to-End Flow

### Current flow

```text
GitHub/HDLF source
  -> collect candidate suggestions
  -> pair every suggestion with the whole PR diff
  -> build dataset and overlap priors
  -> send suggestion, landed diff, and priors to an LLM labeler
  -> extract deterministic lexical/hunk/structural features
  -> train several regressors against LLM-assisted percentages
  -> select/deploy using a repeatedly consulted 70-row holdout
  -> require callers to provide the precomputed feature row
  -> return one rounded integer
```

### Required flow

```text
verified suggestion event + immutable suggestion snapshot
  -> verify suggestion timestamp precedes merge
  -> reconstruct exact base state at suggestion time
  -> compute final target-branch state at merge
  -> parse additions, deletions, replacements, moves, and renames
  -> map suggestion units to candidate landed units
  -> aggregate unit-level coverage
  -> apply calibrated model only where it adds validated value
  -> return estimate + uncertainty + evidence + provenance
```

## 5. Critical Findings

### G-01 — There is no production input-to-output API

**Severity:** Blocker

**Evidence**

- `src/pr_suggestion_metrics/model_inference.py:118` accepts metric rows, not raw diffs.
- `src/pr_suggestion_metrics/evaluate_metrics.py:1075` contains the actual feature computation in private `_score_example`.
- `_score_example` requires `LabeledExample`, including reference labels and precomputed overlap fields.

**Why this is not logical**

The stated product receives a suggestion and merged PR code/diff. The exported package receives a table that only the evaluation pipeline knows how to build. A downstream caller cannot safely reproduce training-time preprocessing.

**Required change**

- Introduce a label-free `SuggestionPair` input model.
- Expose `extract_features(suggested_diff, landed_diff, context) -> FeatureRow`.
- Expose `predict_coverage(pair) -> CoverageResult`.
- Keep label loading entirely outside feature extraction.

**Files**

- `src/pr_suggestion_metrics/evaluate_metrics.py`
- `src/pr_suggestion_metrics/model_inference.py`
- `src/pr_suggestion_metrics/__init__.py`
- new `src/pr_suggestion_metrics/domain.py`
- new `src/pr_suggestion_metrics/features.py`
- new end-to-end tests

### G-02 — Suggestion-time provenance is not trustworthy

**Severity:** Blocker

**Evidence**

- `src/pr_suggestion_metrics/collect_pr_code_changes.py:472` reads the PR merge SHA.
- `src/pr_suggestion_metrics/collect_pr_code_changes.py:479` stores that merge SHA as the candidate `commit_id`.
- `src/pr_suggestion_metrics/collect_pr_code_changes.py:1512` later writes the candidate `commit_id` as `inspection_commit_sha`.
- In the current raw dataset, **279/279 rows have `inspection_commit_sha == merge_commit_sha`**.
- `PairedExample` has no comment `created_at`, `updated_at`, original commit ID, original line, side, start line, or review-thread state.

**Why this is not logical**

The data model gives the appearance of preserving an inspection-time commit, but for comment-collected rows it stores the merge commit instead. The system cannot prove that the suggestion existed before merge or identify the exact code context the reviewer saw.

**Required change**

- Add `suggestion_created_at`, `suggestion_updated_at`, `pr_merged_at`, `comment_commit_id`, `original_commit_id`, `path`, `line`, `start_line`, `side`, and `original_position`.
- Reject rows where `suggestion_created_at >= pr_merged_at`.
- Preserve the GitHub review-comment payload or a content-addressed immutable subset.
- Rename `inspection_commit_sha` or populate it from the actual inspection/review event.
- Backfill or discard current rows that cannot pass chronology checks.

**Files**

- `src/pr_suggestion_metrics/collect_pr_code_changes.py`
- `src/pr_suggestion_metrics/build_dataset.py`
- `data/raw/pipeline-fl-control-plane-closed-prs/export/raw_pairs.jsonl`
- `data/processed/pr_suggestion_coverage/dataset/dataset.jsonl`

### G-03 — Reference percentages are not independent human ground truth

**Severity:** Blocker

**Evidence**

- Internal set: 279 rows, 73 PRs, one repository.
- External set: 2,500 rows, 1,196 PRs, 29 repositories.
- Internal `llm_labels.jsonl` has no model, prompt, prompt hash, annotator, timestamp, temperature, or seed fields.
- External `llm_labels.jsonl` has no such provenance either.
- Only **20/2,500 external rows** have explicit manual overrides.
- `README.md:39` calls `labels.csv` “ground-truth.”
- `README.md:88` and `README.md:291` call the internal data “hand-labeled.”
- `data/processed/pr_suggestion_coverage/dataset/README.md:9` calls the labels manual.
- The paper correctly calls the labels LLM-assisted and the result exploratory.

**Why this is not logical**

A model evaluated against labels generated by another model is validated against that model’s judgment, not against independently established truth. Confidence fields generated by the same labeler are not a substitute for inter-annotator agreement.

**Required change**

- Relabel a representative frozen benchmark with at least two independent human annotators.
- Blind annotators to deterministic metrics and previous labels.
- Adjudicate disagreements and retain both original annotations.
- Report agreement at unit and percentage levels.
- Call current labels `weak_reference_percentage`, never `ground_truth`.

### G-04 — Label generation is anchored to the features later evaluated

**Severity:** Blocker

**Evidence**

`src/pr_suggestion_metrics/semantic_labeling_batches.py:144-170` sends the labeler:

- the previous weak label;
- the previous weak percentage;
- `deterministic_landed_estimate`;
- `file_overlap_ratio`;
- `changed_line_overlap_ratio`;
- suggested and landed file lists.

The trained model later uses those same overlap signals. Internal deterministic estimate and final LLM percentage correlate at **0.7772**; external correlation is **0.6161**.

**Why this is not logical**

The evaluation partially asks whether learned overlap features can predict a label that was produced while seeing those overlap features. This inflates apparent validity and masks genuine semantic failures.

**Required change**

- Remove all weak labels and metric values from the annotation prompt.
- Randomize example order.
- Run a blind relabeling study.
- Compare blind labels against assisted labels to measure anchoring bias.
- Never use a labeler’s self-reported confidence as the only basis for training weights.

### G-05 — The percentage is not reproducible from stored evidence

**Severity:** Blocker

**Evidence**

- The prompt says to weight semantic units.
- Internal labels store no `semantic_units`; **0/279** internal label rows contain that field.
- External labels store semantic units, but explicit numeric unit weights and per-unit credit are absent.
- Internal targets have only 24 distinct values; **94.62%** are multiples of five and **62.37%** are exactly 0 or 100.

**Why this is not logical**

There is no recorded numerator or denominator from which a reviewer can reconstruct the percentage. The task is framed as regression, but the target is an uncalibrated ordinal judgment with endpoint clustering.

**Required change**

- Persist semantic unit, importance weight, landed status, evidence location, and credit.
- Compute percentage deterministically from those records.
- Permit annotators to dispute unit decomposition separately from unit matching.
- Evaluate percentage error and unit-level precision/recall.

### G-06 — The internal holdout is no longer a test set

**Severity:** Blocker

**Evidence**

- `src/pr_suggestion_metrics/train_percentage_regressor.py:152`
- `src/pr_suggestion_metrics/train_two_stage_percentage.py:69`
- `src/pr_suggestion_metrics/train_percentage_ensemble.py:75`
- `src/pr_suggestion_metrics/train_advanced_percentage_models.py`
- `src/pr_suggestion_metrics/train_embedding_percentage_models.py:223`

All recreate the same `GroupShuffleSplit(test_size=0.25, random_state=42)`, producing 70 rows from 19 PRs. Multiple model families and deployment gates were chosen after observing this holdout.

One exact suggestion hash also appears on both sides of this development/test split.

**Why this is not logical**

Repeated model and threshold decisions adapt to the holdout. Its reported performance is optimistic, even though the rows remain PR-group separated.

**Required change**

- Retire the current holdout to development status.
- Create a versioned split manifest, not an implicit random split.
- Deduplicate before splitting using canonical suggestion and pair hashes.
- Freeze a new repository- and time-separated test set.
- Evaluate it once after the model and thresholds are locked.

### G-07 — External data is not the same task as internal data

**Severity:** Blocker

**Evidence**

`notebooks/05_external/import_hf_github_codereview.ipynb`:

- keeps positive rows with fenced code blocks;
- excludes negative rows by default;
- uses only the **first** code block;
- turns a file-level before/after snippet into a synthetic diff;
- derives initial labels directly from added-line overlap (`0/40/80/100`);
- hard-codes `file_overlap_ratio = 1.0`;
- later sends the weak label and overlap values to the LLM relabeler.

Internal rows instead pair a suggestion with an entire PR diff. The same feature name also has different semantics:

- Internal `changed_line_overlap_ratio` includes both added and removed lines (`build_dataset.py:179-189`).
- External `changed_line_overlap_ratio` includes only added lines (notebook source lines 143-165).

**Why this is not logical**

The external set is easier, selected differently, scoped differently, and partly labeled from the same overlap signal used for prediction. Its excellent scores do not demonstrate transfer to the target production problem.

**Required change**

- Define one canonical pair schema and one feature implementation.
- Include true negatives and ambiguous cases according to a documented sampling frame.
- Preserve all suggestion blocks or explicitly justify selecting one.
- Do not hard-code overlap features.
- Treat current external results as weak-supervision experiments, not external validation.

### G-08 — Duplicate examples can leak across splits and disagree sharply

**Severity:** Major

**Evidence**

Internal data:

- 13 duplicate-suggestion groups covering 29 rows;
- 11 duplicate full-pair groups covering 24 rows;
- one duplicate-suggestion group has labels `{0, 100}` across three PRs;
- one exact suggestion hash crosses the current development/test split.

External data:

- 77 duplicate-suggestion groups covering 197 rows;
- 29 duplicate full-pair groups covering 58 rows;
- 17 duplicate-suggestion groups have conflicting labels;
- one duplicate full-pair group has labels `{50, 88}`.

**Required change**

- Canonicalize diffs before hashing.
- Group splits by PR, canonical suggestion hash, and duplicate-pair cluster.
- Resolve conflicting exact-pair labels before training.
- Publish duplicate-policy counts with every dataset version.

### G-09 — Label inputs are silently truncated

**Severity:** Major

**Evidence**

- `semantic_labeling_batches.py:122-126` keeps only the head and tail.
- Default limit is 24,000 characters per diff.
- **185/279 internal landed diffs** exceed that limit.
- **26/2,500 external landed diffs** exceed that limit.

**Why this is not logical**

The omitted middle can contain the actual implementation. A head-plus-tail view is especially unsafe for large PRs and can produce confident but unsupported percentages.

**Required change**

- Retrieve candidate hunks first, then show annotators complete relevant context.
- Persist a `truncated` flag and exact omitted ranges.
- Require low confidence or abstention when relevant context cannot be shown.
- Report performance separately for truncated and non-truncated examples.

### G-10 — Deletions and replacements are outside the metric

**Severity:** Major

**Evidence**

- `evaluate_metrics.py:313-351` extracts only lines beginning with `+`.
- `embedding_features.py:141-142` uses the same addition-only helpers.
- A deletion-only suggestion becomes an empty suggestion and cannot receive meaningful coverage.

The present datasets contain no true deletion suggestions, so the evaluation never exercises this failure mode.

**Required change**

- Parse typed edit operations: add, delete, replace, move, rename.
- Match deleted suggestion units against deletions from the final change.
- Match replacements as old-unit removal plus new-unit presence.
- Add explicit tests for deletion-only and mixed edits.

### G-11 — Best-hunk scoring does not measure total coverage

**Severity:** Major

**Evidence**

- `evaluate_metrics.py:818-903` retains one global best candidate across all suggestion files.
- `evaluate_metrics.py:801-813` considers every same-extension hunk in the PR.
- `embedding_features.py:97-129` retrieves candidates using the same overlap family later used for scoring.
- `embedding_features.py:423-448` uses maxima over all suggestion chunks and candidate chunks.
- Internal `candidate_hunk_count` ranges from 0 to **678**; external median is only 2.

**Why this is not logical**

- A multi-part suggestion can score highly because one small fragment matches.
- More PR hunks create more chances for an accidental best match.
- The retrieval stage and scoring stage reinforce the same lexical bias.
- Candidate counts vary dramatically by source, creating a source-specific best-of-many effect.

**Required change**

- Match each suggestion unit or hunk separately.
- Use constrained bipartite matching so one landed hunk cannot explain every suggestion unit.
- Aggregate matched weight across the entire suggestion.
- Penalize unsupported or many-candidate searches.
- Use review path/line anchors before cross-file retrieval.

### G-12 — Whole-PR matching confounds adoption with unrelated work

**Severity:** Major

Each suggestion is compared against the whole PR diff. Multiple suggestions on one PR reuse the same landed diff. Similar code elsewhere in the PR can be counted even when it was unrelated or already present before the comment.

**Required change**

- Reconstruct code before the suggestion and final code after merge.
- Prefer the original review hunk and nearby changed symbols.
- Compare incremental changes after the suggestion timestamp where history permits.
- Record whether evidence was local, moved, pre-existing, or ambiguous.

### G-13 — Structural similarity is weaker than its name implies

**Severity:** Major

**Evidence**

- `evaluate_metrics.py:969-1003` extracts mostly AST node-type names.
- `evaluate_metrics.py:947` computes multiset recall over those names.
- Tree-sitter results are accepted when node types exist; parse-error nodes are not explicitly rejected.

**Why this is not logical**

Two snippets can contain the same multiset of `if_statement`, `identifier`, and `call_expression` nodes while implementing unrelated behavior. `structural_similarity` and `structural_node_recall` are currently the same value.

**Required change**

- Rename this feature to `ast_node_type_recall` unless a stronger structural matcher is implemented.
- Reject or flag parse trees containing errors.
- Add parent-child structure, identifiers, operators, calls, and data-flow anchors.
- Do not describe node-type overlap as semantic equivalence.

### G-14 — Heuristic percentages are magic constants

**Severity:** Major

`evaluate_metrics.py:1275-1362` contains many undocumented thresholds, multipliers, caps, and endpoint returns, including `95`, `0.98`, `0.90`, `0.40`, `0.25`, `0.80`, and `0.55`.

The heuristic may be useful as a baseline, but it is not a calibrated percentage. It should be named and versioned as a heuristic score.

**Required change**

- Rename `predicted_percentage` in deterministic reports to `heuristic_coverage_score`.
- Move thresholds into a versioned configuration.
- Document how each threshold was selected.
- Evaluate ablations and sensitivity instead of tuning by repeated holdout inspection.

### G-15 — Inference coercion silently changes valid inputs

**Severity:** Major

`model_inference.py:81-86` converts booleans using string equality with `"true"`. Integer `1` becomes `"1"` and therefore becomes `0`. This was reproduced for all three boolean features.

Numeric values are coerced with invalid text becoming `NaN`, after which model imputers can silently replace the value.

**Required change**

- Validate accepted boolean forms explicitly.
- Reject malformed numeric values instead of silently imputing API input.
- Validate finite ranges for ratios and counts.
- Include row IDs in validation errors.
- Preserve caller indexes or return stable input IDs.

### G-16 — No uncertainty, abstention, or out-of-distribution guard

**Severity:** Major

`predict_coverage_percentages` returns only `model_predicted_percentage`. It exposes no confidence, interval, model version, feature version, warning, or abstention state.

**Required change**

- Calibrate prediction intervals by PR or repository.
- Detect unsupported languages, parse failures, extreme candidate counts, empty changes, and feature drift.
- Return an explicit abstention result for unsafe cases.
- Preserve component predictions for debugging.

### G-17 — Training is stateful and repeatedly overwrites artifacts

**Severity:** Major

- `train_percentage_regressor.py:157-188` loads `model.joblib` from the output directory as its baseline and may overwrite the same file.
- Later trainers read reports and models from that same mutable directory.
- Several scripts write `evaluation_report.json` with different experiment meanings.
- Current `evaluation_report.json` says `kept_existing_baseline`; it does not independently prove which earlier run produced the stored model.

**Why this is not logical**

The result of a run depends on what artifact happened to exist before the run. The repository cannot reconstruct lineage from source and parameters alone.

**Required change**

- Write immutable run directories.
- Record input hashes, split-manifest hash, code commit, dependency lock hash, seed, model parameters, and artifact hash.
- Separate `candidate_report.json`, `selection_report.json`, and `deployed_model_manifest.json`.
- Promote a model via an explicit copy/registry step, never by in-place conditional overwrite.

### G-18 — Embedding artifact schema is incomplete

**Severity:** Major

`train_embedding_percentage_models.py:463-489` writes only the non-current components’ required columns to `feature_schema.json`. The serialized ensemble also contains a wrapped current model that requires all base `FEATURE_COLUMNS`.

The saved artifact is marked `recommended_for_deployment: false`, but it can still be loaded as a normal model file.

**Required change**

- Include the union of base and embedding columns in the schema.
- Store component-specific schemas explicitly.
- Move non-deployable artifacts under `experiments/` and omit a production-looking `model.joblib`, or add an enforced deployment-state check.
- Add a test that loads the saved artifact using only its declared schema.

### G-19 — GumTree fields are dead features in current training data

**Severity:** Major

Across both current metric tables:

- `gumtree_available` is always false;
- operation count and all four operation ratios are always zero.

These six model inputs carry no information. They enlarge the schema and imply a capability not used by the trained artifact.

**Required change**

- Remove them from the production schema, or regenerate every training/evaluation row with a reproducible GumTree setup.
- Do not mix “optional at scoring time” with “required model feature” without an explicit missingness strategy validated in production.

### G-20 — Collection is coupled to another private repository

**Severity:** Major

- `collect_pr_code_changes.py:25` derives a parent directory as `REPO_ROOT`.
- `collect_pr_code_changes.py:29-30` imports `fl_shared` from outside this repository.
- `requirements.txt` does not declare `pydantic`, `pydantic-settings`, `SQLAlchemy`, or `fl_shared`.
- The supplied `.ml-venv` also lacks `pydantic`, `pydantic-settings`, and `SQLAlchemy`.

**Required change**

- Move organization-specific DB/HDLF collection behind an optional adapter.
- Keep GitHub-only collection independently importable.
- Declare optional dependency groups such as `core`, `train`, `embeddings`, `collection`, and `dev`.
- Remove the package-level eager import in `__init__.py` that forces model dependencies for unrelated commands.

### G-21 — Repository migration from `ml/` is incomplete

**Severity:** Major

Examples:

- `README.md:8-109` still documents an `ml/` root layout.
- `README.md:298` invokes a nonexistent `ml/src/...` path.
- `evaluate_metrics.py:36` resolves its default dataset outside this repository.
- `evaluate_metrics.py:1558` writes to nonexistent `ml/reports/`.
- `semantic_labeling_batches.py:341` defaults to nonexistent `ml/docs/...`.
- Collection, preparation, evaluation, visualization, classifier, and regression notebooks hard-code the former `pipeline-fl-control-plane/ml` location.
- The remaining `ml/` directory contains only `.DS_Store`.

**Required change**

- Complete the root-layout migration in one change.
- Derive repository root from a package/project marker, not an absolute personal path.
- Add a smoke test for every README command.
- Delete the empty legacy `ml/` directory after removing its tracked `.DS_Store`.

### G-22 — Dependency and packaging claims are false

**Severity:** Major

- The paper says “Install the pinned project requirements.”
- `requirements.txt` contains no version pins.
- There is no `pyproject.toml`, package metadata, lockfile, or supported-Python declaration.
- Runtime model compatibility is not recorded.
- `joblib` artifacts are pickle-based and should only be loaded from trusted, verified sources.

**Required change**

- Add `pyproject.toml` with explicit Python compatibility.
- Generate a locked environment.
- Record training/runtime library versions with each artifact.
- Hash and verify model and schema files together.
- Document that model files are trusted-only inputs.

### G-23 — Dataset writing drops a valid zero

**Severity:** Major bug

`build_dataset.py:306` writes:

```python
row.expected_landed_percentage or ""
```

A legitimate `0` becomes an empty string.

**Required change**

Use an explicit `is not None` test and add a regression test.

### G-24 — Source filters are not identity verification

**Severity:** Major

`collect_pr_code_changes.py:1193-1210` treats a comment as “hyperspace” if the author login or body merely contains the substring `hyperspace`. Author filters also use substring matching.

**Required change**

- Use an allowlist of exact bot/application identities.
- Record author ID, login, account type, and GitHub App slug.
- Make source verification status part of the pair schema.
- Reject unverified rows from the primary dataset.

### G-25 — Test coverage misses the actual product path

**Severity:** Major

The 18 tests cover model wrapper behavior, embedding helpers, and repository-bootstrap mechanics. There are no focused tests for:

- diff parsing;
- additions, deletions, replacements, and renames;
- multi-file aggregation;
- collector comment parsing and chronology;
- dataset building and zero preservation;
- blind labeling batch construction;
- raw-diff-to-percentage inference;
- artifact/schema compatibility;
- malformed production inputs;
- golden end-to-end examples.

**Required change**

Build tests around the target behavior, not only model wrappers.

## 6. Additional Major and Moderate Findings

### Data integrity

- `train_percentage_regressor.py:60-70` uses an inner merge without validating one-to-one IDs or asserting that no score/label rows were dropped.
- Target percentages are clipped to `[0,100]` during training instead of rejecting invalid labels.
- `split` is stored in all 279 internal dataset rows but is always `unassigned`; training ignores it and recreates splits dynamically.
- `human_label`, `expected_landed_percentage`, and `reviewer_edited_version` are present in the raw pair schema but null in all 279 raw rows.
- `renamed_files` and `config_files_touched` are collected but not used by the scorer or model.
- Two internal examples contain no parseable added suggestion lines. They happen to be labeled zero, but should be rejected or explicitly classified as unsupported.
- Three external examples contain no landed additions. They are labeled zero, but this edge case needs an explicit contract.

### Naming and conceptual drift

- `deterministic_landed_estimate` is the original 35/65 file-and-line prior.
- `predicted_percentage` in metric CSVs is a later hand-coded heuristic.
- `model_predicted_percentage` is the learned-model result.
- The three names can easily be mistaken for the same production quantity.
- `Label` still models four bucket-era categories inside the evaluator.
- `PercentageBucket` in `evaluate_metrics.py:21-34` still accepts obsolete bucket `"100"`, while the valid terminal bucket is `"91-100"`.
- `data/processed/pr_suggestion_coverage/dataset/README.md:17-29` also lists obsolete `100` as a separate bucket.
- The classifier API remains exported even though percentage regression is the stated goal.

Recommended names:

```text
weak_overlap_prior
deterministic_heuristic_score
coverage_estimate
reference_coverage_percentage
```

### Metric semantics

- Exact matching flattens all added lines from suggested files and can match lines across distant hunks.
- Same-file path matching is brittle under renames and moves.
- Same-extension retrieval creates false-positive opportunities in large PRs.
- Common-token filtering and language-specific tokenizers are useful heuristics, but not a semantic guarantee.
- LCS returns zero when the pair exceeds 250,000 cells, conflating “too expensive” with “no similarity.”
- Parser unavailability, parse failure, and true zero structural similarity can collapse into similar numeric inputs.
- `structural_similarity` duplicates `structural_node_recall` in the current implementation.
- Embedding `fraction_above_*` measures the fraction of candidate chunks that look similar, not the fraction of suggestion content covered.
- Embedding truncation caps suggestion chunks and candidate chunks, but no truncation feature reaches the final model.

### Evaluation interpretation

- Reported internal holdout: MAE `9.743`, RMSE `19.310`, within 10 points `74.3%`, dangerous error `1.43%`.
- The MAE improvement confidence interval crosses zero; the paper acknowledges this.
- RMSE is slightly worse than the baseline.
- The repository-held-out embedding blend improves MAE by only `0.022` points with a 95% interval `[-0.043, 0.083]`, while RMSE and within-10 performance worsen.
- Repository-held-out external evaluation is still against labels created from an overlap-derived and LLM-assisted process. It is not an independent semantic benchmark.
- “Dangerous error” only measures endpoint reversal (`<=20` versus `>=80`). Other operationally dangerous errors are not represented.
- There is no cost model for false claims of adoption versus false misses.

### Reproducibility and operations

- No CI workflow is present.
- No formatter, linter, type checker, or coverage configuration is present.
- No supported operating systems or architectures are declared.
- Tree-sitter binaries checked into Git are macOS ARM64-specific.
- The runtime benchmark excludes loading, parsing, retrieval, cache I/O, and regression; it is not an end-to-end latency benchmark.
- Notebook cells contain absolute paths to the author’s machine.
- Notebook outputs are committed, making reviews noisy and artifacts hard to distinguish from source.
- The repository has only five commits, limiting historical traceability for methodological decisions.

## 7. Repository Hygiene and Security

### Immediate security action

The repository tracks:

- `.jupyter-runtime/jupyter_cookie_secret`;
- a Jupyter server file containing a token;
- kernel connection files containing HMAC keys and ports.

These files were introduced in repository history. Delete them, add ignore rules, and rotate/restart any still-valid Jupyter credentials. If this repository has ever been shared, treat the values as exposed even after deletion from the latest commit.

### Generated and platform-specific material currently tracked

- 7 `.DS_Store` files;
- 7 compiled `.pyc` files;
- 9 macOS ARM64 Tree-sitter `.dylib` files;
- a 24 MB Tree-sitter bundle;
- IDE configuration under `.idea/`;
- notebook runtime files;
- generated model artifacts, reports, figures, label batches, and caches.

The tracked working tree is approximately **356 MB** across **656 files**.

The current `.gitignore` contains only:

```text
data/embeddings/cache/
```

### Recommended storage policy

- **Git:** source, tests, small manifests, documentation, schemas, tiny fixtures.
- **Artifact store/release:** trained models, evaluation reports, figures.
- **DVC/object storage:** raw and processed datasets, label batches, embedding features.
- **Never tracked:** runtime secrets, kernels, caches, virtual environments, compiled bytecode, `.DS_Store`, IDE workspace state.

## 8. Files and Artifacts to Remove or Archive

Removal should happen only after references are updated and artifact consumers are confirmed.

| Candidate | Recommendation | Reason |
|---|---|---|
| `models/pr_suggestion_coverage/` | Archive/remove | Obsolete four-class classifier artifact; percentage model is the stated product. |
| `notebooks/06_train/train_metric_classifier.ipynb` | Move to `archive/bucket-era/` | Trains the superseded coarse classifier. |
| `src/pr_suggestion_metrics/model_inference.py::predict_coverage_labels` | Deprecate, then remove | Public bucket-era API with no current product role. |
| `notebooks/07_visualize/model_performance_dashboard.ipynb` | Replace or archive | Primarily classifier/confusion-dashboard logic. |
| `reports/model_performance_dashboard/` | Regenerate from current percentage evaluation or archive | Contains bucket/classifier-era charts. |
| `docs/prompts/llm_labeling_prompt.md` | Archive | Old coarse-label prompt with obsolete absolute paths. |
| `docs/prompts/llm_bucket_labeling_prompt.md` | Archive | Bucket-era labeling process; bucket should be derived reporting metadata. |
| `notebooks/08_train/train_regression_coverage_model.ipynb` | Archive after parity check | Duplicates the script-based percentage training path. |
| `src/pr_suggestion_metrics/train_percentage_ensemble.py` | Archive/remove after confirming history needs | Superseded by the advanced multi-model ensemble trainer. |
| `two_stage_percentage.py::PercentageModelBlend` | Remove with old ensemble trainer | Only supports the superseded two-component path. |
| `evaluate_metrics.py::_anchor_recall` | Remove | Static audit found no use. |
| `evaluate_metrics.py::_normalize_lines_by_file` | Remove | Static audit found no use. |
| `build_dataset.py::_changed_files_from_headers` | Remove or use | Static audit found no use. |
| `train_embedding_percentage_models.py::itertools` | Remove | Unused import. |
| `train_embedding_percentage_models.py::NUMERIC_FEATURES` | Remove | Unused import. |
| `data/processed/pr_suggestion_coverage/dataset/supervised_training.jsonl` | Remove or document a consumer | 53 MB generated duplicate not consumed by current training scripts. |
| `data/processed/pr_suggestion_coverage/dataset/review_examples/` | Generate on demand | 52 MB of repeated full PR diffs. |
| `data/processed/pr_suggestion_coverage/dataset/metric_scores.csv` | Remove duplicate | Byte-identical to `reports/metric_scores.csv`. |
| `reports/pr_suggestion_metric_scores.csv` | Remove/archive | Older, different score schema and confusing name. |
| `ml/` | Remove | Contains only `.DS_Store`; all documented paths should target repository root. |
| `.jupyter-runtime/` | Delete and purge/rotate secrets | Runtime credentials and machine state. |
| `.tree-sitter-cache/` | Delete from Git | Platform-specific generated cache. |
| `src/pr_suggestion_metrics/__pycache__/` | Delete from Git | Generated bytecode. |
| `.idea/`, `.DS_Store`, `.matplotlib-cache/` | Delete from Git | Local tool state. |

## 9. Target Repository Structure

Recommended structure:

```text
code-compare/
  pyproject.toml
  uv.lock
  README.md
  src/pr_suggestion_metrics/
    domain.py
    diff_parser.py
    candidate_retrieval.py
    deterministic_features.py
    coverage_aggregation.py
    inference.py
    artifact.py
    cli.py
    collection/
      github.py
      hdlf.py
    labeling/
      schema.py
      batches.py
      adjudication.py
    training/
      data.py
      split.py
      train.py
      evaluate.py
  tests/
    unit/
    integration/
    golden/
  configs/
    feature-v2.json
    training-v2.json
  data/
    README.md
    fixtures/
  experiments/
    README.md
  docs/
    method.md
    data-card.md
    model-card.md
    graduation-codebase-review.md
  archive/
    bucket-era/
```

Core rules:

- Library code must not know about labels.
- Collection adapters must not import training libraries.
- Training must consume immutable manifests.
- Production inference must consume raw domain inputs.
- Artifacts must declare exact schema and provenance.
- Notebooks may call library functions; they must not contain the canonical implementation.

## 10. File-by-File Change Plan

### `README.md`

- Replace the obsolete `ml/` tree and commands.
- Lead with one supported end-to-end command and API.
- Remove “ground-truth,” “hand-labeled,” and premature “production” claims.
- Separate current method, historical experiments, and artifact generation.
- State the exact interpretation and limitations of the percentage.

### `requirements.txt` / new `pyproject.toml` / new lockfile

- Replace unpinned requirements with locked, grouped dependencies.
- Add missing collection dependencies.
- Declare Python versions and package entry points.
- Add test, lint, type-check, and notebook extras.

### `.gitignore`

Ignore at minimum:

```text
.DS_Store
.idea/
.jupyter-runtime/
.jupyter-data/
.matplotlib-cache/
.tree-sitter-cache/
.uv-cache/
.ml-venv/
__pycache__/
*.py[cod]
*.dylib
```

Also decide whether data, models, reports, and notebook outputs are tracked via Git LFS/DVC or generated externally.

### `src/pr_suggestion_metrics/collect_pr_code_changes.py`

- Split GitHub collection from organization-specific DB/HDLF adapters.
- Record complete comment and merge provenance.
- Verify comment source identity exactly.
- Enforce chronology.
- Preserve review anchors.
- Fetch or derive final merged state deliberately.
- Remove label fields from raw collection records.

### `src/pr_suggestion_metrics/build_dataset.py`

- Fix zero serialization.
- Use one typed, versioned dataset schema.
- Normalize diff semantics consistently.
- Record content hashes and provenance.
- Validate duplicates and contradictions.
- Stop generating unconsumed duplicate training files by default.

### `src/pr_suggestion_metrics/semantic_labeling_batches.py`

- Remove prior labels and feature hints from labeler input.
- Replace head/tail truncation with evidence retrieval and explicit truncation metadata.
- Persist prompt hash, model ID, model revision, parameters, run timestamp, and raw response hash.
- Keep LLM output in a weak-label namespace.

### `src/pr_suggestion_metrics/audit_semantic_labels.py`

- Move manual overrides into a versioned annotation file.
- Require annotator identity and adjudication status.
- Do not assign confidence weights solely from LLM-generated confidence.
- Make every override traceable without changing source code.

### `src/pr_suggestion_metrics/evaluate_metrics.py`

- Split reusable parsing/features from evaluation reporting.
- Accept label-free inputs.
- Add deletion/replacement/rename semantics.
- Replace one-best-hunk scoring with unit-level constrained matching.
- Distinguish parse failure from zero similarity.
- Remove obsolete `"100"` bucket.
- Fix repository-root defaults and create output parents.
- Rename heuristic output to avoid confusion with model output.

### `src/pr_suggestion_metrics/model_inference.py`

- Add raw-pair inference.
- Fix boolean parsing.
- Reject invalid numeric data.
- Validate artifact/schema versions and hashes.
- Return confidence, warnings, evidence, and model metadata.
- Deprecate/remove classifier inference.

### Training modules

Affected:

- `train_percentage_regressor.py`
- `train_two_stage_percentage.py`
- `train_percentage_ensemble.py`
- `train_advanced_percentage_models.py`
- `train_embedding_percentage_models.py`
- `evaluate_repository_held_out_embeddings.py`

Required changes:

- Centralize split creation and persist manifests.
- Deduplicate before splitting.
- Use nested grouped validation for tuning.
- Keep a new final test set untouched.
- Eliminate mutable baseline/output coupling.
- Emit immutable run manifests and artifact hashes.
- Use one model-selection policy.
- Compare against trivial, deterministic, and human-agreement baselines.
- Separate exploratory external weak-label results from confirmatory results.

### `src/pr_suggestion_metrics/embedding_features.py`

- Make retrieval use verified scope and anchors.
- Measure coverage of suggestion chunks, not maxima over candidate chunks.
- Expose truncation and retrieval diagnostics.
- Fix model-schema completeness before any deployment attempt.

### `src/pr_suggestion_metrics/generate_percentage_paper_assets.py`

- Pass every source artifact as an argument; avoid hidden fixed paths.
- Verify input hashes against the paper manifest.
- Fail if reports have incompatible schema/version.
- Generate tables and figures from one immutable evaluation run.

### Notebooks

- Convert canonical logic into importable modules and tests.
- Keep notebooks as thin demonstrations.
- Remove absolute paths and all `ml/` assumptions.
- Clear outputs before committing.
- Archive classifier/bucket-era notebooks separately.

### Data and model documentation

Create:

- `docs/data-card.md`: collection dates, repositories, sampling, exclusions, provenance, licenses, known bias.
- `docs/annotation-guide.md`: unit decomposition and scoring protocol.
- `docs/model-card.md`: intended use, non-use, metrics, uncertainty, training data, versions, risks.
- `docs/reproducibility.md`: exact commands from clean checkout to final report.

## 11. Remediation Roadmap

### Phase 0 — Stop unsafe claims and secure the repository

1. Remove/rotate Jupyter runtime credentials.
2. Replace “ground truth,” “hand-labeled,” and “production” wording.
3. Add comprehensive ignore rules.
4. Complete root-path migration.
5. Add package metadata and a lockfile.

**Exit condition:** a clean checkout installs and all documented smoke commands run.

### Phase 1 — Establish a valid dataset

1. Define the semantic-unit percentage formula.
2. Repair collection provenance and chronology.
3. Sample across repositories, languages, sizes, and outcomes.
4. Blindly double-annotate a frozen benchmark.
5. Resolve duplicates and contradictory labels.
6. Freeze train/development/test manifests.

**Exit condition:** every test label is reconstructible from unit-level human evidence.

### Phase 2 — Rebuild the deterministic core

1. Parse additions, deletions, replacements, renames, and moves.
2. Scope candidates using review anchors and temporal code state.
3. Match suggestion units with constrained assignment.
4. Aggregate coverage across all units.
5. Return diagnostics and abstentions.

**Exit condition:** golden examples demonstrate correct behavior for core edit types.

### Phase 3 — Train without test contamination

1. Tune only inside development data.
2. Keep external weak labels auxiliary and separately reported.
3. Calibrate uncertainty.
4. Lock code, features, data, and thresholds.
5. Evaluate the frozen test exactly once.

**Exit condition:** confirmatory metrics and intervals are generated from an untouched test manifest.

### Phase 4 — Productionize

1. Publish a raw-diff inference API.
2. Validate and version all inputs and artifacts.
3. Add monitoring for drift, abstention, and unsupported cases.
4. Add CI, golden tests, and reproducible artifact builds.
5. Define model promotion and rollback.

**Exit condition:** a new environment can reproduce and serve the result safely.

## 12. Minimum Graduation Acceptance Criteria

### Scientific validity

- At least two independent human labels per frozen test example.
- Stored semantic units, weights, statuses, and evidence.
- Inter-annotator agreement reported.
- No weak label or overlap metric shown to annotators.
- Repository-, PR-, time-, and duplicate-aware split policy.
- No test-set use for model or threshold selection.
- Confidence intervals grouped at the correct dependency level.
- External validation on the real target task, not a synthetic easier proxy.

### Metric validity

- Additions, deletions, replacements, moves, and renames covered.
- Multi-file and multi-hunk suggestions aggregated.
- Pre-existing code distinguished from post-suggestion changes where possible.
- Unrelated PR changes do not receive credit.
- Percentage denominator is explicit and reconstructible.
- Unsupported or ambiguous inputs can abstain.

### Engineering quality

- Raw suggestion + merged state can be passed directly to the public API.
- Clean installation from locked dependencies.
- No dependency on an adjacent private checkout for core operation.
- Model/schema/data/code versions bound in one manifest.
- End-to-end tests and golden fixtures pass in CI.
- No secrets, runtime state, compiled binaries, or local caches tracked.

### Evidence quality

- Model is compared with simple lexical, hunk, and human baselines.
- Performance is broken down by repository, language, suggestion size, edit type, and confidence/abstention band.
- Calibration is reported, not only MAE.
- Error analysis includes false high-coverage claims and false zero claims.
- Thesis language matches what the experiment can actually establish.

## 13. Recommended Final Claim After Remediation

A defensible claim would be:

> Given a verified pre-merge code suggestion and the final merged code state, the system estimates the weighted semantic coverage of explicitly annotated suggestion units. On a frozen, repository- and time-separated, independently human-adjudicated test set, it achieves the reported error and calibration bounds, and abstains when evidence is insufficient.

Until those conditions are met, use this narrower claim:

> The repository contains an exploratory model that predicts LLM-assisted semantic-agreement scores from deterministic overlap features. Its current internal results are promising but not confirmatory.

## 14. Final Assessment

The project has enough technical substance for a strong master’s work: data collection, language-aware diff processing, structural analysis, multiple model families, grouped validation, embeddings, and honest negative results. The weakness is not effort or scope. The weakness is that the research question and the evidence chain are not yet aligned.

The next major gain will not come from another regressor. It will come from:

1. a precise percentage definition;
2. trustworthy temporal provenance;
3. blind, unit-level human labels;
4. a label-free end-to-end production API;
5. one untouched confirmatory evaluation.

Complete those five items before treating the number as a real metric.

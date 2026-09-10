# Data Card: PR Suggestion Coverage Corpora

**Status:** exploratory research data, not validated ground truth  
**Snapshot reviewed:** 2026-09-08  
**Primary task:** estimate how much suggested code is represented in a merged pull-request diff

## 1. Scope

The repository contains two labeled corpora with materially different origins:

| Corpus | Location | Rows | Repositories | Label source | Permitted role |
|---|---|---:|---:|---|---|
| Internal | `data/processed/pr_suggestion_coverage/dataset/` | 279 | 1 | LLM-assisted semantic scoring | exploratory development only |
| External | `data/external/github_codereview/dataset/` | 2,500 | 29 | weak labels derived from review-response metadata, later audited/weighted | auxiliary training and transfer research only |

Neither corpus is a frozen, independently double-human-annotated benchmark. Results trained or evaluated on these labels must not be described as performance against human ground truth.

## 2. Intended Construct

The intended construct is **semantic suggestion coverage**:

> the weighted fraction of meaningful units in a code suggestion that are present in the final merged implementation, regardless of exact textual form.

The current rows pair a suggested diff with a pull-request diff. They do not establish that matching code was introduced because of the suggestion, was absent before the suggestion, or persisted in the final target-branch state. Therefore the data supports exploratory **coverage/agreement** research, not causal **adoption** claims.

## 3. Internal Corpus

### Composition

- **279 examples** from one internal repository: `github.tools.sap/Lenny/pipeline-fl-control-plane`.
- Suggestions are GitHub review-comment suggestion blocks.
- The compared target is the whole PR diff from the GitHub pull-diff API.
- Current coarse labels: 70 `0%`, 35 `partial`, 70 `mostly`, and 104 `100%`.
- Current percentages range from 0 to 100, with a mean of approximately 62.93.
- No immutable train/development/test assignment is stored in `labels.csv`; training scripts derive grouped splits at runtime.

### Files

- `dataset.jsonl`: suggestion/landed-diff pairs, metadata, deterministic priors, and current labels.
- `labels.csv`: compact current targets keyed by `example_id`.
- `llm_labels.jsonl`: LLM reasoning and semantic-unit output.
- `metric_scores.csv`: deterministic features computed from the pairs.
- `supervised_training.jsonl`: joined training-oriented records.

### Known limitations

- All examples come from one repository and organizational context.
- Labels are LLM-assisted, not two independent blind human annotations.
- The labeling prompt receives deterministic overlap priors, creating label-feature leakage.
- The entire PR diff is searched, which can reward unrelated changes.
- Suggestion chronology and exact suggestion-time base state are not reliably reconstructed.
- Unit weights and partial credits are not stored in a form that deterministically reproduces every percentage.
- The same 70-row holdout has been consulted across multiple experiments.

## 4. External Corpus

### Composition

- **2,500 examples** retained from 11,325 scanned rows of `ronantakizawa/github-codereview`.
- **29 repositories** and multiple languages are represented.
- Largest language groups recorded in metadata are Python (893), Julia (325), Kotlin (283), Swift (207), TypeScript (165), and Java (150).
- Current coarse labels: 250 `0%`, 310 `partial`, 587 `mostly`, and 1,353 `100%`.
- Current percentages range from 0 to 100, with a mean of approximately 77.55.

### Known limitations

- Labels originate from response metadata and are weak supervision, not direct human coverage judgments.
- The task and collection process differ from the internal target setting.
- High-coverage outcomes are overrepresented.
- Repository and language representation are uneven.
- Public-source licensing and redistribution obligations must be checked against the upstream dataset and each source repository before publication.

## 5. Collection and Processing

The implemented flow is:

```text
review suggestion + PR diff
  -> normalized JSONL pair
  -> deterministic overlap and structural features
  -> LLM-assisted or weak percentage label
  -> exploratory grouped model evaluation
```

The desired confirmatory flow is:

```text
verified pre-merge suggestion event
  -> immutable suggestion-time base state
  -> final merge state
  -> supported edit decomposition
  -> blind double-human unit annotation
  -> adjudication
  -> frozen repository/time/duplicate-aware splits
```

## 6. Quality Controls Present

- Stable `example_id` values join data, labels, and scores.
- Label/percentage/bucket consistency can be audited.
- Model training groups examples by pull request.
- External audit records can lower training weight for uncertain rows.
- Numeric and boolean model inputs now reject malformed values instead of silently coercing them.

These controls improve engineering reliability. They do not solve construct validity, annotation independence, chronology, or holdout reuse.

## 7. Prohibited Uses

Do not use these corpora to:

- claim a percentage of code was causally adopted from a suggestion;
- rank individual developers or reviewers;
- make employment, performance, or compliance decisions;
- report confirmatory accuracy against human ground truth;
- infer behavior for unsupported replacements, deletions, renames, moves, multi-file, or multi-hunk suggestions;
- publish private repository content without authorization.

## 8. Required Replacement Benchmark

Before a validated production claim, create a new benchmark with:

1. a written semantic-unit definition fixed before labeling;
2. verified suggestion timestamps and immutable before/after revisions;
3. at least two independent, blind human annotators per test example;
4. stored units, importance weights, credits, evidence, and original annotations;
5. adjudication records and inter-annotator agreement;
6. repository-, PR-, time-, and near-duplicate-aware split manifests;
7. an untouched confirmatory test set used once after model and thresholds are frozen;
8. coverage across languages, repositories, suggestion sizes, and edit types.

## 9. Maintenance

Any refreshed corpus must receive a new immutable version and content hashes. Never overwrite a published benchmark in place. Record source revision, collection date, filtering rules, deduplication method, annotation-guide version, split manifest, and code revision.

The repository now supplies enforcement tools for the replacement release: `pr-suggestion-prepare-annotations`, `pr-suggestion-freeze-benchmark`, `pr-suggestion-calibrate-uncertainty`, and `pr-suggestion-evaluate-frozen`. These tools do not make the current corpora valid; they reject missing provenance and require new independent human evidence.

# Documentation Home

**Status:** canonical index

**Audience:** contributors, reviewers, researchers, and deployers

**Purpose:** identify the authoritative document for each project question

## Start Here

| Question | Read this |
|---|---|
| What does the project do today? | [`../README.md`](../README.md) |
| How is the code and data flow organized? | [`architecture.md`](architecture.md) |
| What is the delivery order? | [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) |
| What outcomes define the roadmap? | [`../ROADMAP.md`](../ROADMAP.md) |
| What is actively completed or in progress? | [`implementation-progress.md`](implementation-progress.md) |
| What problems did the senior review find? | [`senior-code-review.md`](senior-code-review.md) |

## Authoritative Documents

### Product and architecture

- [`../README.md`](../README.md) — supported public behavior, quick start, and current product claim.
- [`architecture.md`](architecture.md) — current package boundaries, end-to-end flows, and target dual-model architecture.
- [`deployment.md`](deployment.md) — current percentage-demo deployment instructions and operational follow-up.
- [`explanation-model-design.md`](explanation-model-design.md) — grounded CodeBERT explanation design and future combined deployment.

### Metrics and evidence

- [`pr-suggestion-diff-metrics.md`](pr-suggestion-diff-metrics.md) — metric vocabulary and exact-versus-learned evidence contract.
- [`annotation-guide.md`](annotation-guide.md) — human annotation units, credits, evidence, abstention, and adjudication rules.
- [`data-card.md`](data-card.md) — corpus composition, provenance limitations, prohibited uses, and replacement benchmark requirements.
- [`model-card.md`](model-card.md) — current percentage-model scope, limitations, artifact safety, and allowed claims.
- [`reproducibility.md`](reproducibility.md) — installation, validation, benchmark, training, calibration, and protected evaluation commands.

### Planning and review

- [`../ROADMAP.md`](../ROADMAP.md) — milestone outcomes and release gates. It answers **what must be achieved**.
- [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) — dependency-ordered technical execution. It answers **what is implemented next**.
- [`implementation-progress.md`](implementation-progress.md) — durable current-state log. It answers **what has actually happened**.
- [`senior-code-review.md`](senior-code-review.md) — findings, evidence, severity, and remediation status.

### Research reference

- [`language-aware-code-comparison-research.md`](language-aware-code-comparison-research.md) — evaluated parsing and comparison technologies. It informs design but is not a runtime contract.
- [`../research/archive/bucket-era/README.md`](../research/archive/bucket-era/README.md) — unsupported historical experiments and generated artifacts retained for provenance.

## Source-of-Truth Rules

Use one authoritative location per type of information:

| Information | Source of truth |
|---|---|
| Public capability and limitations | `README.md` and `model-card.md` |
| Package boundaries and dependency direction | `docs/architecture.md` |
| Metric meaning | `docs/pr-suggestion-diff-metrics.md` |
| Dataset facts and governance | `docs/data-card.md` |
| Annotation decisions | `docs/annotation-guide.md` |
| Reproducible commands | `docs/reproducibility.md` |
| Technical implementation order | `IMPLEMENTATION_PLAN.md` |
| Current execution status | `docs/implementation-progress.md` |
| Review evidence and unresolved risks | `docs/senior-code-review.md` |

Do not copy the same changing facts into several documents. Link to the source of truth instead.

## Document Lifecycle

Every new substantial document should declare:

```text
Status: canonical | active plan | reference | archived
Audience: who should use it
Purpose: the single question it answers
```

Lifecycle rules:

1. **Canonical docs** describe supported behavior and must change with the code.
2. **Active plans** may describe future behavior but must label it as future work.
3. **Reference docs** provide research context and must not be mistaken for product guarantees.
4. **Archived docs** live under `research/archive/` and are not imported or presented as current behavior.
5. Completed work updates `implementation-progress.md`; do not create another dated worklog.
6. Superseded documents are moved to the appropriate archive with a short replacement note.

## Update Checklist

When changing the project:

- **Public API or behavior:** update `README.md`, the relevant contract document, and tests.
- **Metric semantics:** update `pr-suggestion-diff-metrics.md`, model/data cards, and golden tests.
- **Training data or labels:** update `data-card.md`, `annotation-guide.md`, and `reproducibility.md`.
- **Model artifact or claim:** update `model-card.md`, release manifest documentation, and deployment instructions.
- **Architecture:** update `architecture.md` and `implementation-progress.md`.
- **Roadmap decision:** update `ROADMAP.md`; update `IMPLEMENTATION_PLAN.md` only when execution order changes.

## Documentation Definition of Done

- The document has one clear purpose and lifecycle status.
- Current behavior and future design are visibly separated.
- Commands are runnable from the repository root unless stated otherwise.
- Claims link to evidence, tests, manifests, or the appropriate card.
- No active document points to a deleted file.
- Historical results are labeled unsupported and remain under `research/archive/`.

Run the active-document consistency check from the repository root:

```bash
python3 scripts/check_documentation.py
```

The checker intentionally excludes `research/archive/` because archived generated Markdown may contain code fragments that
look like links and must remain byte-preserved for provenance.

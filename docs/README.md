# Documentation Home

**Status:** canonical index

**Audience:** contributors, reviewers, researchers, and deployers

**Purpose:** help each reader pick the next document without guessing

## Start Here

### If you are new to the repository

Read these in order:

1. [`../README.md`](../README.md)
2. [`getting-started.md`](getting-started.md)
3. [`project-guide.md`](project-guide.md)
4. [`architecture.md`](architecture.md)
5. [`reproducibility.md`](reproducibility.md)

### If you need one answer fast

| Question | Read this |
|---|---|
| What does the project do today? | [`../README.md`](../README.md) |
| How do I get productive quickly? | [`getting-started.md`](getting-started.md) |
| What history and structure should I understand? | [`project-guide.md`](project-guide.md) |
| Can I see the project architecture quickly? | [`project-architecture-overview.md`](project-architecture-overview.md) |
| How is the system organized? | [`architecture.md`](architecture.md) |
| Which commands are authoritative? | [`reproducibility.md`](reproducibility.md) |
| What has actually shipped? | [`implementation-progress.md`](implementation-progress.md) |
| What is planned next? | [`implementation-progress.md`](implementation-progress.md) |
| What risks define the remaining work? | [`senior-code-review.md`](senior-code-review.md) |
| What review findings matter? | [`senior-code-review.md`](senior-code-review.md) |

## Read By Role

### New contributor

- [`../README.md`](../README.md)
- [`getting-started.md`](getting-started.md)
- [`project-guide.md`](project-guide.md)
- [`architecture.md`](architecture.md)
- [`implementation-progress.md`](implementation-progress.md)

### Research or model work

- [`reproducibility.md`](reproducibility.md)
- [`data-card.md`](data-card.md)
- [`model-card.md`](model-card.md)
- [`annotation-guide.md`](annotation-guide.md)
- [`pr-suggestion-diff-metrics.md`](pr-suggestion-diff-metrics.md)

### Demo or deployment work

- [`deployment.md`](deployment.md)
- [`architecture.md`](architecture.md)
- [`model-card.md`](model-card.md)
- [`explanation-model-design.md`](explanation-model-design.md)

### Planning and review work

- [`implementation-progress.md`](implementation-progress.md)
- [`senior-code-review.md`](senior-code-review.md)

## Active Documents

### Front door and onboarding

- [`../README.md`](../README.md) — public capability, limits, quick start, and repo map.
- [`getting-started.md`](getting-started.md) — first-hour onboarding path and common commands.
- [`project-guide.md`](project-guide.md) — project history, current structure, workflows, and pitfalls.

### Product and architecture

- [`architecture.md`](architecture.md) — package boundaries, flows, and target combined architecture.
- [`project-architecture-overview.md`](project-architecture-overview.md) — compact architecture map and linked Mermaid diagram.
- [`deployment.md`](deployment.md) — current combined demo deployment instructions.
- [`explanation-model-design.md`](explanation-model-design.md) — explanation-provider boundary and future design.

### Scores, data, and model rules

- [`pr-suggestion-diff-metrics.md`](pr-suggestion-diff-metrics.md) — what each score means.
- [`annotation-guide.md`](annotation-guide.md) — how answer-key labels should be made and checked.
- [`data-card.md`](data-card.md) — where datasets came from, what is weak, and what not to claim.
- [`model-card.md`](model-card.md) — what the model can and cannot safely do.
- [`reproducibility.md`](reproducibility.md) — exact setup, test, benchmark, training, and evaluation commands.

### Supporting repository docs

- [`../space/README.md`](../space/README.md) — operator notes for the local/Hugging Face demo UI.
- [`../models/pr_suggestion_coverage/demo_weak_local/README.md`](../models/pr_suggestion_coverage/demo_weak_local/README.md) — demo model scope and non-release warning.
- [`../data/processed/pr_suggestion_coverage/dataset/README.md`](../data/processed/pr_suggestion_coverage/dataset/README.md) — internal processed dataset snapshot summary.
- [`../data/external/github_codereview/dataset/README.md`](../data/external/github_codereview/dataset/README.md) — external imported dataset snapshot summary.
- [`../research/prompts/llm_semantic_percentage_labeling_prompt.md`](../research/prompts/llm_semantic_percentage_labeling_prompt.md) — active semantic-labeling prompt used by labeling utilities.

### Planning and review

- [`implementation-progress.md`](implementation-progress.md) — durable shipped-state log.
- [`senior-code-review.md`](senior-code-review.md) — findings, evidence, and remediation status.

### Research reference

- [`language-aware-code-comparison-research.md`](language-aware-code-comparison-research.md) — comparison-technology research that informs design.
- [`../research/archive/bucket-era/README.md`](../research/archive/bucket-era/README.md) — unsupported historical experiments kept for project history.

## Archive Boundary

Most tracked Markdown files in this repository are **not** active docs.

- The current-doc set is the root docs plus the active files under `docs/`.
- Supporting Markdown under `space/`, `models/`, `data/`, and `research/prompts/` is still relevant, but it is narrower in scope.
- Large Markdown collections under `research/archive/`, especially generated `review_examples/*.md`, are history files and should not be used for onboarding or current product claims.
- If you are unsure whether a file is current, start from this index and only branch out when a linked document points you there.

## Where Facts Should Live

Plain meaning: each changing fact should live in one main place. Other docs should link to it instead of copying it.

Use one authoritative location per type of information:

| Information | Source of truth |
|---|---|
| Public capability and limitations | `README.md` and `docs/model-card.md` |
| New-contributor onboarding | `docs/getting-started.md` |
| Project history and mastery map | `docs/project-guide.md` |
| Package boundaries and dependency direction | `docs/architecture.md` |
| Metric meaning | `docs/pr-suggestion-diff-metrics.md` |
| Dataset facts and governance | `docs/data-card.md` |
| Dataset snapshot contents | `data/processed/.../README.md` and `data/external/.../README.md` |
| Annotation decisions | `docs/annotation-guide.md` |
| Active LLM labeling prompt | `research/prompts/llm_semantic_percentage_labeling_prompt.md` |
| Reproducible commands | `docs/reproducibility.md` |
| Demo operator notes and model-file caveats | `space/README.md` and `models/.../README.md` |
| Technical implementation order | `docs/implementation-progress.md` and `docs/senior-code-review.md` |
| Current execution status | `docs/implementation-progress.md` |
| Review evidence and unresolved risks | `docs/senior-code-review.md` |

Do not copy changing facts into several docs. Link back to the source of truth instead.

## Document Lifecycle

Every new substantial active document should declare:

```text
Status: current | active plan | reference | archived
Audience: who should use it
Purpose: the single question it answers
```

Lifecycle rules:

1. **Current docs** describe supported behavior and should change with the code.
2. **Active plans** describe intended future work and must stay visibly separate from current behavior.
3. **Reference docs** provide context without becoming product guarantees.
4. **Archived docs** belong under `research/archive/` and are preserved, not maintained as current behavior.
5. Completed work updates `implementation-progress.md` instead of creating a new drifting worklog.

## Update Checklist

When changing the project:

- **Public API or behavior:** update `README.md`, the relevant rules doc, and tests.
- **Onboarding flow:** update `README.md`, `docs/getting-started.md`, and any changed commands.
- **Metric semantics:** update `pr-suggestion-diff-metrics.md`, the model/data cards, and golden tests.
- **Training data or labels:** update `data-card.md`, `annotation-guide.md`, and `reproducibility.md`.
- **Model artifact or claim:** update `model-card.md`, manifests, and deployment guidance.
- **Architecture:** update `architecture.md` and `implementation-progress.md`.
- **Roadmap or priority decision:** update `docs/implementation-progress.md` and `docs/senior-code-review.md` when execution order or unresolved risk changes.

## Documentation Definition Of Done

- The next reader can tell whether the document is current, planned, reference-only, or archived.
- A newcomer can find the next relevant doc without already knowing the repo structure.
- Commands are runnable from the repository root unless stated otherwise.
- Claims link to evidence, tests, manifests, or the correct card.
- Active docs do not point to deleted files.
- Historical files remain clearly labeled unsupported.

Run the active-document consistency check from the repository root:

```bash
python3 scripts/check_documentation.py
```

The checker intentionally excludes `research/archive/` because archived generated Markdown is preserved as history.

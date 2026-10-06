# Grounded Explanation Model Design

**Status:** active design; implementation foundation available, CodeBERT adapter and trained artifact pending

**Audience:** model developers, API developers, reviewers, and demo operators

**Purpose:** define the grounded explanation contract and production path for the second model

## Decision

The percentage estimator and explanation model remain separately trained, evaluated, versioned, and deployable.
They are composed by one runtime service rather than merged into one model.

CodeBERT is treated as an evidence encoder. It identifies and ranks relevant landed-code evidence; deterministic templates
turn that evidence into user-facing text. Free-form generation is not part of the first production demo.

## Lifecycle Separation

```text
research/archive/              historical experiments and unsupported models
collection/                    supported source gateways and provenance
features/                      deterministic feature and evidence extraction
modeling/percentage/           percentage training and evaluation
modeling/explanation/          CodeBERT evidence training and evaluation
explanations/                  stable runtime contracts and grounded composition
inference/                     validated artifact loading and model execution
api/                           combined request and response schemas
```

Historical collectors and experiments may inform new work, but supported training and inference must never import them.

## Implemented Runtime Boundary

`pr_suggestion_metrics.explanations` now provides:

- `ExplanationEvidence`: one versionable claim with verdict, confidence, source, path, and inspectable evidence;
- `EvidenceProviderResult`: model identity plus a unique set of evidence units;
- `EvidenceProvider`: the adapter protocol a CodeBERT implementation must satisfy;
- `ExplanationService`: request limits, input hashes, provider invocation, and deterministic composition;
- `GroundedExplanation`: a stable explained-or-abstained result contract.

The service rejects blank or oversized diffs before invoking a model. Explanations are generated only from validated
evidence units. Unsupported units are excluded from prose and reported explicitly.

## CodeBERT Adapter Contract

The future adapter implements:

```python
class CodeBertEvidenceProvider:
    def extract_evidence(
        self,
        *,
        suggested_diff: str,
        merged_diff: str,
    ) -> EvidenceProviderResult:
        ...
```

The adapter should:

1. Parse suggested and landed diffs into file- and hunk-scoped semantic units.
2. Preserve file paths, operations, and line evidence alongside normalized model text.
3. Chunk inputs below the encoder token limit rather than silently truncating full diffs.
4. Encode suggested units and candidate landed units in batches.
5. Rank candidates within policy-approved file and operation boundaries.
6. Classify each suggestion unit as `landed`, `partial`, `missing`, or `unsupported`.
7. Emit confidence, model revision, and inspectable evidence for every verdict.
8. Abstain inside an explicitly calibrated uncertainty band.

The initial adapter should not generate prose. This keeps evidence scoring testable and lets templates be reviewed without
retraining the encoder.

## Better Reasoning Without Hallucination

The explanation quality comes from decomposition and evidence, not longer prose:

- Explain atomic suggestion units instead of summarizing a complete diff in one pass.
- Separate `missing` from `unsupported`; unsupported input is not evidence that behavior is absent.
- Keep exact deterministic matches visible beside semantic CodeBERT matches.
- Require a path, excerpt, similarity/classification confidence, or explicit absence rationale for every claim.
- Prefer missing and partial evidence in the summary because those findings are most actionable.
- Cap summary details while preserving the complete evidence list in the structured response.
- Never let the explanation model change the percentage model output.

## Training Requirements

Train the explanation provider independently from the percentage regressor.

Required data:

- atomic suggested behavior units;
- candidate landed hunks with immutable provenance;
- `landed`, `partial`, `missing`, and `unsupported` labels;
- evidence spans or absence rationales;
- repository, pull request, language, and edit-type groups.

Evaluation must report:

- verdict precision, recall, and macro F1;
- evidence retrieval recall at K;
- unsupported-claim rate;
- missing-change detection recall;
- calibration and abstention coverage;
- results by repository, language, and edit type;
- blinded human ratings for factual grounding and usefulness.

Do not select thresholds on protected test data. Pin the final model revision and thresholds in the explanation artifact
manifest.

## Combined Product Contract

The eventual `AnalysisService` composes three independent results:

```text
deterministic change evidence
percentage prediction + uncertainty
grounded explanation + evidence
```

The API response must identify both model artifacts:

```json
{
  "coverage_percentage": 72,
  "coverage_interval": [64, 80],
  "explanation": "Evidence assessment: 2 landed units and 1 missing unit. Missing: retry handling.",
  "matched_evidence": [],
  "missing_evidence": [],
  "percentage_model_version": "coverage-v1",
  "explanation_model_version": "codebert-evidence-v1",
  "input_hashes": {},
  "warnings": []
}
```

One model may abstain without forcing the other to invent an answer. The combined response preserves each component's
status and limitations.

## Demo Production Checklist

### Artifact bundle

- Store percentage and explanation artifacts in separate directories.
- Pin the Hugging Face repository and immutable revision for CodeBERT weights.
- Record SHA-256 hashes, schemas, thresholds, tokenizer revision, and runtime versions.
- Validate metadata and compatibility before loading executable model artifacts.

### Runtime

- Preload models at startup and expose readiness only after verification succeeds.
- Apply request size, file count, hunk count, timeout, and concurrency limits.
- Batch and cache CodeBERT embeddings by content hash.
- Do not log source code or raw diffs.
- Return structured abstentions and stable error codes.

### Hugging Face showcase

- Start with a Docker Space containing FastAPI and a thin Gradio interface.
- Load artifacts from pinned Hub revisions; use Space secrets for private repositories.
- Display evidence and limitations beside every explanation.
- Include curated examples that demonstrate landed, partial, missing, unsupported, and malformed inputs.
- Move CodeBERT to a separate Inference Endpoint only when measured latency or memory requires independent scaling.

## Next Implementation Steps

1. Convert deterministic `ChangeCoverageEvidence` into `ExplanationEvidence` as a baseline provider.
2. Define CodeBERT input chunks and the evidence artifact manifest.
3. Build an offline CodeBERT adapter behind `EvidenceProvider`.
4. Add calibrated verdict thresholds and an abstention band.
5. Evaluate evidence retrieval and unsupported claims on grouped development data.
6. Add the combined `AnalysisService` only after both component contracts are stable.
7. Package the first Docker Space and run latency, memory, privacy, and failure-path checks.

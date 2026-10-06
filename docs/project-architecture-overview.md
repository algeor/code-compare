# Project Architecture Overview

**Status:** canonical architecture overview

**Audience:** contributors, reviewers, researchers, demo operators, and future agents

**Purpose:** provide a compact system architecture map for the current project

## 1. Purpose

The project measures how much of a code-review suggestion is represented in a merged pull-request diff.

It produces:

- deterministic evidence from exact diff-unit matching;
- an experimental coverage percentage for supported raw diff shapes;
- grounded explanations based on inspectable evidence;
- separate AI review quality scoring against independent evidence.

It does not prove causal adoption or production-validated semantic equivalence.

## 2. High-Level Architecture

```text
User / CLI / Demo UI
        |
        v
AnalysisService
        |
        +--> diff validation + deterministic evidence
        |
        +--> feature extraction
        |
        +--> percentage model inference
        |
        +--> grounded explanation templates
        |
        v
Versioned AnalysisResult
```

See [`project-architecture.mmd`](project-architecture.mmd) for a Mermaid diagram version.

## 3. Main Layers

### Interface layer

Entry points for users, demos, and hosted showcases.

```text
README / docs
CLI commands
Gradio demo
Hugging Face Space shim
```

Key files:

```text
src/pr_suggestion_metrics/analysis_service.py
src/pr_suggestion_metrics/demo_gradio.py
space/app.py
```

### Domain layer

Core project meaning lives here.

```text
diff_semantics.py        exact change-unit evidence
reviewer_evaluation.py   separate AI review scoring
percentages.py           shared percentage validation
scientific_contracts.py  research contracts
```

### Diff and feature layer

This layer turns diffs into validated evidence and model-ready features.

```text
diff/        unified diff parsing and diagnostics
features/    lexical, matching, structural, scoring features
```

Flow:

```text
raw suggested diff + merged PR diff
        -> parse / assess
        -> normalize change units
        -> strict same-file evidence
        -> relaxed cross-file evidence
        -> feature row
```

### Model runtime layer

This layer loads trusted model artifacts and performs inference.

```text
model_inference.py
model_artifacts.py
uncertainty.py
```

Rules:

- model directory must be explicit;
- manifest hashes are verified;
- unsupported inputs abstain;
- `joblib` artifacts are trusted-input only.

### Research pipeline layer

This layer creates reproducible benchmark and training artifacts.

```text
collection/
benchmark/
modeling/
prepare_annotation_packets.py
freeze_benchmark.py
evaluate_frozen_benchmark.py
```

Target flow:

```text
collect candidates
 -> prepare blinded annotation packets
 -> adjudicate labels
 -> freeze benchmark
 -> build feature table
 -> select/train model
 -> calibrate uncertainty
 -> protected evaluation
```

### Documentation and governance layer

This layer defines what the project can safely claim.

```text
README.md
docs/README.md
docs/architecture.md
docs/project-guide.md
docs/reproducibility.md
docs/data-card.md
docs/model-card.md
docs/implementation-progress.md
docs/senior-code-review.md
```

## 4. Important Boundaries

- `research/archive/` is historical only.
- Runtime inference must not import training code.
- Supported code must not import archived bucket-era code.
- Deterministic evidence is not semantic proof.
- Coverage scoring is separate from AI reviewer quality scoring.

## 5. Current Product Shape

```text
suggested diff + merged PR diff
        |
        v
AnalysisService
        |
        +--> deterministic evidence
        +--> weak/demo percentage model
        +--> template explanation
        |
        v
JSON result with hashes, warnings, evidence, score/abstention
```

## 6. Future Product Shape

```text
validated diff evidence
        |
        +--> calibrated percentage model
        |
        +--> CodeBERT-style evidence provider
        |
        v
stable API / CLI / hosted demo result
```

The key next architecture goal is not more model tuning. It is better benchmark evidence: provenance-complete, independently labeled, frozen, and evaluated once.

# Project Architecture

**Status:** canonical architecture map

**Audience:** contributors, reviewers, model developers, and deployers

**Purpose:** explain current boundaries, end-to-end flows, and the intended dual-model product

## System Summary

The project compares a code-review suggestion with a merged pull-request diff. It currently exposes:

1. **Deterministic evidence** — inspectable matching of normalized change units.
2. **Experimental percentage inference** — a learned estimate for a deliberately narrow raw-diff input shape.
3. **Grounded explanation foundation** — deterministic-template explanations behind a future CodeBERT evidence provider.
4. **AnalysisService composition** — one local service shape used by CLI, API, and demo surfaces.

The percentage result does not prove causal adoption. The explanation layer must not convert similarity into an unsupported
claim of semantic equivalence.

## Current Package Boundaries

```text
collection/          supported GitHub collection, provenance, and pair construction
diff/                unified-diff parsing and structural diagnostics
features/            deterministic lexical, matching, structural, and scoring features
benchmark/           split planning and canonical feature-table creation
modeling/            percentage training and shared evaluation metrics
model_inference.py   verified percentage-artifact loading and inference
diff_semantics.py    exact evidence-bearing change-unit coverage
explanations/        grounded explanation contracts, provider boundary, and templates
artifact_io.py       validated and atomic artifact I/O primitives
```

Compatibility modules may temporarily re-export moved functions. New supported code should import from the responsibility
module, not from a compatibility facade or underscore-prefixed helper.

## Repository Lifecycle Boundaries

```text
research/archive/    unsupported historical code, models, reports, notebooks, and generated data
data/                active small fixtures and approved source data
src/                 supported package code
tests/               active behavior and contract tests
docs/                canonical, planning, operational, and research-reference documentation
```

Archived code is evidence of past exploration, not a supported dependency. Large future datasets and model bundles should
live in versioned external storage with repository-held schemas, manifests, and hashes.

## Data and Training Flow

```text
source gateway
    -> provenance-complete candidate
    -> blinded annotation packets
    -> independent annotation + adjudication
    -> grouped split plan
    -> frozen benchmark
    -> deterministic feature table
    -> percentage training
    -> calibration
    -> protected evaluation
    -> versioned model artifact
```

Important boundaries:

- Collection performs network and source-specific work; feature and model code do not.
- Benchmark creation uses immutable inputs, grouped splits, and hash-bound outputs.
- Training reads train and development data, while calibration remains separate.
- Protected test labels are unavailable during feature design, training, selection, and calibration.
- Runtime inference loads validated artifacts but never runs training code.

## Current Inference Flow

```text
suggested diff + merged diff
    -> applicability checks
    -> deterministic change evidence
    -> deterministic model features
    -> verified percentage model
    -> optional calibrated interval
    -> CoverageResult
```

Unsupported raw-diff shapes return a typed abstention. Exact evidence may still be available for shapes the learned model
does not support.

## Grounded Explanation Flow

The explanation foundation intentionally separates evidence production from prose composition:

```text
suggested diff + merged diff
    -> EvidenceProvider
    -> landed / partial / missing / unsupported evidence units
    -> deterministic grounded templates
    -> GroundedExplanation
```

`EvidenceProvider` is the future CodeBERT adapter boundary. CodeBERT should rank or classify evidence; it should not be
treated as a free-form generator. The first production demo should use controlled templates so every sentence maps back to
inspectable evidence.

See [`explanation-model-design.md`](explanation-model-design.md) for the training, evaluation, and deployment contract.

## Target Combined Product

The percentage and explanation models remain independently trained, evaluated, versioned, and replaceable:

```text
                         -> percentage model -> score + uncertainty
validated diff evidence -|
                         -> CodeBERT provider -> grounded explanation
                                              |
                                              -> AnalysisService result
```

The runtime combines outputs, not model weights. This allows:

- separate benchmarks and release thresholds;
- independent rollback and scaling;
- explicit partial success when one model abstains;
- one package, CLI, API, and hosted response schema;
- a Hugging Face Space demo without importing training or historical research code.

The combined result should include model names, versions, schema versions, artifact hashes, input hashes, evidence,
abstention reasons, and limitations.

## Dependency Rules

1. `collection` may depend on source clients and domain contracts; domain code must not depend on CLI parsing.
2. `features` may depend on `diff`; it must not depend on benchmark, training, or deployment code.
3. `benchmark` may depend on domain and feature contracts; model inference must not depend on benchmark-writing commands.
4. `modeling` may depend on stable feature schemas; runtime modules must not import training entry points.
5. `explanations` accepts evidence-provider results; templates must not import transformer libraries.
6. API and UI layers orchestrate supported services and contain no metric or model-training algorithms.
7. Supported modules never import from `research/archive/`.

## Current Versus Future

| Capability | Current | Future gate |
|---|---|---|
| Exact change evidence | Implemented | Version normalization and strict/relaxed evidence policies |
| Percentage inference | Implemented, experimental and narrow | Human benchmark, calibration, and protected evaluation |
| Grounded explanation contracts | Implemented | CodeBERT provider and grouped evidence evaluation |
| Combined analysis service | Implemented with deterministic-template explanations | Validated release bundle and future CodeBERT provider |
| Hugging Face showcase | Documented | Validated artifacts, Docker runtime, limits, and smoke tests |

## Architecture Change Checklist

Before merging a boundary change:

- preserve or version public result contracts;
- add characterization tests before moving behavior;
- keep compatibility facades temporary and documented;
- avoid importing private helpers across responsibility areas;
- update this architecture map and `implementation-progress.md`;
- run focused tests followed by the project validation gate.

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pr_suggestion_metrics.explanations import (
    EvidenceProviderResult,
    ExplanationEvidence,
    ExplanationService,
)


@dataclass
class FakeProvider:
    result: EvidenceProviderResult
    calls: int = 0

    def extract_evidence(self, *, suggested_diff: str, merged_diff: str) -> EvidenceProviderResult:
        self.calls += 1
        return self.result


def evidence(unit_id: str, verdict: str, description: str, confidence: float) -> ExplanationEvidence:
    return ExplanationEvidence(
        unit_id=unit_id,
        description=description,
        verdict=verdict,
        confidence=confidence,
        source="codebert",
        evidence=[f"evidence for {unit_id}"],
        path="src/example.py",
    )


def test_service_composes_deterministic_grounded_summary_and_hashes() -> None:
    provider = FakeProvider(
        EvidenceProviderResult(
            model_name="codebert-evidence",
            model_version="revision-123",
            evidence=[
                evidence("landed", "landed", "input validation", 0.98),
                evidence("missing", "missing", "retry handling", 0.91),
                evidence("partial", "partial", "error propagation", 0.83),
            ],
        )
    )

    result = ExplanationService(provider).explain(suggested_diff="+validate", merged_diff="+validate_input")

    assert result.status == "explained"
    assert result.landed_units == 1
    assert result.partial_units == 1
    assert result.missing_units == 1
    assert result.summary == (
        "Evidence assessment: 1 landed unit, 1 partially landed unit, 1 missing unit. "
        "Missing: retry handling. Partial: error propagation. Matched: input validation."
    )
    assert [item.unit_id for item in result.evidence] == ["missing", "partial", "landed"]
    assert result.explanation_model_version == "revision-123"
    assert len(result.input_hashes["suggested_diff_sha256"]) == 64
    assert provider.calls == 1


def test_service_abstains_when_provider_returns_only_unsupported_evidence() -> None:
    provider = FakeProvider(
        EvidenceProviderResult(
            model_name="codebert-evidence",
            model_version="revision-123",
            evidence=[evidence("unsupported", "unsupported", "binary file change", 1.0)],
        )
    )

    result = ExplanationService(provider).explain(suggested_diff="+binary", merged_diff="+binary")

    assert result.status == "abstained"
    assert result.summary == "No supported explanation evidence was produced."
    assert result.unsupported_units == 1
    assert "1 evidence units were unsupported" in result.warnings[0]


def test_provider_result_rejects_duplicate_unit_ids() -> None:
    duplicate = evidence("same", "landed", "validation", 0.9)

    with pytest.raises(ValueError, match="unit IDs must be unique"):
        EvidenceProviderResult(
            model_name="codebert-evidence",
            model_version="revision-123",
            evidence=[duplicate, duplicate],
        )


def test_service_rejects_large_input_before_provider_call() -> None:
    provider = FakeProvider(
        EvidenceProviderResult(
            model_name="codebert-evidence",
            model_version="revision-123",
            evidence=[],
        )
    )

    with pytest.raises(ValueError, match="suggested_diff exceeds"):
        ExplanationService(provider, maximum_diff_characters=3).explain(
            suggested_diff="+long",
            merged_diff="+ok",
        )

    assert provider.calls == 0

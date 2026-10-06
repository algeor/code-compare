"""Deterministic templates for evidence-grounded explanations."""

from __future__ import annotations

from collections import Counter

from pr_suggestion_metrics.explanations.contracts import (
    EvidenceProviderResult,
    EvidenceVerdict,
    ExplanationEvidence,
    GroundedExplanation,
)


_VERDICT_ORDER: dict[EvidenceVerdict, int] = {"missing": 0, "partial": 1, "landed": 2, "unsupported": 3}
_SUMMARY_LABELS: tuple[tuple[EvidenceVerdict, str], ...] = (
    ("landed", "landed"),
    ("partial", "partially landed"),
    ("missing", "missing"),
)
_DETAIL_VERDICTS: tuple[EvidenceVerdict, ...] = ("missing", "partial", "landed")
_EXPERIMENTAL_WARNING = (
    "Explanation evidence is grounded in diff matches and model/provider confidence; it does not prove causal adoption "
    "or final-state semantic equivalence."
)


def _unit_phrase(count: int, label: str) -> str:
    noun = "unit" if count == 1 else "units"
    return f"{count} {label} {noun}"


def _summary_counts(evidence: list[ExplanationEvidence]) -> str:
    counts = Counter(item.verdict for item in evidence)
    parts = [
        _unit_phrase(counts[verdict], label)
        for verdict, label in _SUMMARY_LABELS
        if counts[verdict]
    ]
    return ", ".join(parts)


def _opening_sentence(counts: Counter[EvidenceVerdict]) -> str:
    if counts["missing"] and (counts["landed"] or counts["partial"]):
        return "The merged PR appears to cover part of the suggestion, with remaining gaps."
    if counts["missing"]:
        return "The suggestion does not appear to be represented in the merged PR evidence."
    if counts["partial"] and counts["landed"]:
        return "The merged PR shows strong evidence for the suggestion, with some partial matches."
    if counts["partial"]:
        return "The merged PR shows partial evidence for the suggestion."
    return "The suggestion appears to be represented in the merged PR evidence."


def _detail_sentence(evidence: list[ExplanationEvidence], *, maximum_items: int) -> str:
    details: list[str] = []
    labels: dict[EvidenceVerdict, str] = {
        "missing": "Potential gap",
        "partial": "Partial match",
        "landed": "Matched evidence",
    }
    for verdict in _DETAIL_VERDICTS:
        descriptions = [item.description for item in evidence if item.verdict == verdict][:maximum_items]
        if descriptions:
            details.append(f"{labels[verdict]}: {'; '.join(descriptions)}.")
    return " ".join(details)


def compose_grounded_explanation(
    provider_result: EvidenceProviderResult,
    *,
    input_hashes: dict[str, str],
    maximum_summary_items: int,
) -> GroundedExplanation:
    """Compose a deterministic explanation without introducing unsupported claims."""
    ordered_evidence = sorted(
        provider_result.evidence,
        key=lambda item: (_VERDICT_ORDER[item.verdict], -item.confidence, item.unit_id),
    )
    supported_evidence = [item for item in ordered_evidence if item.verdict != "unsupported"]
    counts = Counter(item.verdict for item in ordered_evidence)
    warnings = list(provider_result.warnings)
    if counts["unsupported"]:
        warnings.append(f"{counts['unsupported']} evidence units were unsupported and excluded from the summary.")
    warnings.append(_EXPERIMENTAL_WARNING)

    if not supported_evidence:
        return GroundedExplanation(
            status="abstained",
            summary=(
                "No supported explanation evidence was produced. "
                "This is an abstention, not evidence that the suggestion is absent."
            ),
            landed_units=0,
            partial_units=0,
            missing_units=0,
            unsupported_units=counts["unsupported"],
            evidence=ordered_evidence,
            explanation_model_name=provider_result.model_name,
            explanation_model_version=provider_result.model_version,
            input_hashes=input_hashes,
            warnings=warnings,
        )

    count_summary = _summary_counts(supported_evidence)
    detail_summary = _detail_sentence(supported_evidence, maximum_items=maximum_summary_items)
    summary = f"{_opening_sentence(counts)} Evidence breakdown: {count_summary}."
    if detail_summary:
        summary = f"{summary} {detail_summary}"
    summary = f"{summary} Review the evidence list for paths, excerpts, and confidence."
    return GroundedExplanation(
        status="explained",
        summary=summary,
        landed_units=counts["landed"],
        partial_units=counts["partial"],
        missing_units=counts["missing"],
        unsupported_units=counts["unsupported"],
        evidence=ordered_evidence,
        explanation_model_name=provider_result.model_name,
        explanation_model_version=provider_result.model_version,
        input_hashes=input_hashes,
        warnings=warnings,
    )

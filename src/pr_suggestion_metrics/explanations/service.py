"""Runtime orchestration for grounded explanation providers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from pr_suggestion_metrics.explanations.contracts import EvidenceProviderResult, GroundedExplanation
from pr_suggestion_metrics.explanations.templates import compose_grounded_explanation


class EvidenceProvider(Protocol):
    """Adapter boundary implemented by CodeBERT or deterministic evidence providers."""

    def extract_evidence(self, *, suggested_diff: str, merged_diff: str) -> EvidenceProviderResult:
        """Return grounded evidence without composing user-facing prose."""
        ...


@dataclass(frozen=True)
class ExplanationService:
    """Validate requests and compose provider evidence into a stable result."""

    provider: EvidenceProvider
    maximum_diff_characters: int = 200_000
    maximum_summary_items: int = 3

    def explain(self, *, suggested_diff: str, merged_diff: str) -> GroundedExplanation:
        """Explain one diff pair while enforcing input and grounding boundaries."""
        if not suggested_diff.strip() or not merged_diff.strip():
            raise ValueError("suggested_diff and merged_diff must both be non-empty")
        if self.maximum_diff_characters < 1:
            raise ValueError("maximum_diff_characters must be positive")
        if self.maximum_summary_items < 1:
            raise ValueError("maximum_summary_items must be positive")
        if len(suggested_diff) > self.maximum_diff_characters:
            raise ValueError("suggested_diff exceeds the configured character limit")
        if len(merged_diff) > self.maximum_diff_characters:
            raise ValueError("merged_diff exceeds the configured character limit")

        provider_result = self.provider.extract_evidence(
            suggested_diff=suggested_diff,
            merged_diff=merged_diff,
        )
        input_hashes = {
            "suggested_diff_sha256": sha256(suggested_diff.encode("utf-8")).hexdigest(),
            "merged_diff_sha256": sha256(merged_diff.encode("utf-8")).hexdigest(),
        }
        return compose_grounded_explanation(
            provider_result,
            input_hashes=input_hashes,
            maximum_summary_items=self.maximum_summary_items,
        )

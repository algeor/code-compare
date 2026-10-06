"""Versioned contracts for evidence-grounded model explanations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EvidenceVerdict = Literal["landed", "partial", "missing", "unsupported"]
EvidenceSource = Literal["deterministic", "codebert", "human"]


class ExplanationEvidence(BaseModel):
    """One inspectable claim produced by an explanation evidence provider."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    description: str
    verdict: EvidenceVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    source: EvidenceSource
    evidence: list[str] = Field(min_length=1)
    path: str | None = None

    @field_validator("unit_id", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """Reject identifiers and descriptions that cannot ground a claim."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("evidence")
    @classmethod
    def validate_evidence_text(cls, values: list[str]) -> list[str]:
        """Require non-empty evidence strings and normalize surrounding space."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("evidence entries must not be blank")
        return normalized


class EvidenceProviderResult(BaseModel):
    """Evidence and metadata returned by a deterministic or learned provider."""

    model_config = ConfigDict(extra="forbid")

    model_name: str
    model_version: str
    evidence: list[ExplanationEvidence]
    warnings: list[str] = Field(default_factory=list)

    @field_validator("model_name", "model_version")
    @classmethod
    def validate_model_identity(cls, value: str) -> str:
        """Require explicit model identity for every explanation."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("model identity must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_unique_units(self) -> EvidenceProviderResult:
        """Prevent duplicate units from inflating or contradicting summaries."""
        unit_ids = [item.unit_id for item in self.evidence]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("explanation evidence unit IDs must be unique")
        return self


class GroundedExplanation(BaseModel):
    """Stable explanation result composed only from inspectable evidence units."""

    model_config = ConfigDict(extra="forbid")

    result_schema_version: Literal["1.0"] = "1.0"
    status: Literal["explained", "abstained"]
    summary: str
    landed_units: int = Field(ge=0)
    partial_units: int = Field(ge=0)
    missing_units: int = Field(ge=0)
    unsupported_units: int = Field(ge=0)
    evidence: list[ExplanationEvidence]
    explanation_model_name: str
    explanation_model_version: str
    input_hashes: dict[str, str]
    warnings: list[str] = Field(default_factory=list)

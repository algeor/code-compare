"""Stable local analysis service for demo/API/UI entry points."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pr_suggestion_metrics.diff_semantics import ChangeCoverageEvidence, analyze_change_coverage
from pr_suggestion_metrics.explanations import (
    EvidenceProviderResult,
    ExplanationEvidence,
    ExplanationService,
    GroundedExplanation,
)
from pr_suggestion_metrics.model_inference import CoverageResult, predict_coverage_from_diffs


DEFAULT_DEMO_MODEL_DIR = Path("models/pr_suggestion_coverage/demo_weak_local/model")


class AnalysisResult(BaseModel):
    """One stable result shape shared by CLI/API/UI demo paths."""

    model_config = ConfigDict(extra="forbid")

    result_schema_version: Literal["1.0"] = "1.0"
    status: Literal["predicted", "abstained"]
    percentage: CoverageResult
    explanation: GroundedExplanation
    model_versions: dict[str, str]
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class DeterministicExplanationProvider:
    """Convert exact deterministic coverage evidence into explanation units."""

    model_name: str = "deterministic-template-explainer"
    model_version: str = "1.0"

    def extract_evidence(self, *, suggested_diff: str, merged_diff: str) -> EvidenceProviderResult:
        coverage = analyze_change_coverage(suggested_diff, merged_diff)
        return EvidenceProviderResult(
            model_name=self.model_name,
            model_version=self.model_version,
            evidence=_explanation_evidence_from_coverage(coverage),
            warnings=list(coverage.warnings),
        )


@dataclass(frozen=True)
class AnalysisService:
    """Compose deterministic evidence, percentage prediction, and explanation."""

    model_dir: Path = DEFAULT_DEMO_MODEL_DIR
    explanation_service: ExplanationService = ExplanationService(DeterministicExplanationProvider())
    enable_gumtree: bool = False

    def analyze(self, *, suggested_diff: str, merged_pr_diff: str, example_id: str | None = None) -> AnalysisResult:
        percentage = predict_coverage_from_diffs(
            suggested_diff,
            merged_pr_diff,
            example_id=example_id,
            model_dir=self.model_dir,
            enable_gumtree=self.enable_gumtree,
        )
        explanation = self.explanation_service.explain(
            suggested_diff=suggested_diff,
            merged_diff=merged_pr_diff,
        )
        model_versions = {
            "percentage_model": percentage.model_name or "abstained",
            "explanation_model": explanation.explanation_model_name,
            "explanation_model_version": explanation.explanation_model_version,
        }
        return AnalysisResult(
            status=percentage.status,
            percentage=percentage,
            explanation=explanation,
            model_versions=model_versions,
            artifact_hashes=percentage.artifact_hashes,
            warnings=[*percentage.warnings, *explanation.warnings],
        )


def _explanation_evidence_from_coverage(coverage: ChangeCoverageEvidence) -> list[ExplanationEvidence]:
    if coverage.suggested_diff_assessment.status != "valid" or coverage.merged_pr_diff_assessment.status != "valid":
        return [
            ExplanationEvidence(
                unit_id="unsupported-input",
                description="Input diff could not be parsed safely",
                verdict="unsupported",
                confidence=1.0,
                source="deterministic",
                evidence=["At least one input diff is structurally invalid."],
            )
        ]
    if coverage.total_suggested_units == 0:
        return [
            ExplanationEvidence(
                unit_id="unsupported-empty-suggestion",
                description="Suggestion contains no supported change units",
                verdict="unsupported",
                confidence=1.0,
                source="deterministic",
                evidence=["No additions, deletions, or explicit renames were found."],
            )
        ]

    rows: list[ExplanationEvidence] = []
    for match in coverage.matches:
        verdict: Literal["landed", "partial"] = "partial" if match.moved_across_files else "landed"
        scope = "in another file" if match.moved_across_files else "in the same file"
        rows.append(
            ExplanationEvidence(
                unit_id=match.suggested_unit_id,
                description=f"Suggested {match.kind} is present {scope}",
                verdict=verdict,
                confidence=0.85 if match.moved_across_files else 1.0,
                source="deterministic",
                evidence=[f"Suggested path {match.suggested_path}; merged path {match.landed_path}."],
                path=match.suggested_path,
            )
        )
    for unit in coverage.unmatched_suggested_units:
        rows.append(
            ExplanationEvidence(
                unit_id=unit.unit_id,
                description=f"Suggested {unit.kind} was not found in the merged diff",
                verdict="missing",
                confidence=0.9,
                source="deterministic",
                evidence=[unit.text],
                path=unit.path,
            )
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suggested-diff", type=Path, required=True)
    parser.add_argument("--merged-pr-diff", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_DEMO_MODEL_DIR)
    parser.add_argument("--example-id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = AnalysisService(model_dir=args.model_dir).analyze(
        suggested_diff=args.suggested_diff.read_text(encoding="utf-8"),
        merged_pr_diff=args.merged_pr_diff.read_text(encoding="utf-8"),
        example_id=args.example_id,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

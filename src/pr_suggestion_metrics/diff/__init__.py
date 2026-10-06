"""Canonical unified-diff parsing primitives."""

from pr_suggestion_metrics.diff.parser import (
    DiffAssessment,
    DiffAssessmentStatus,
    DiffDiagnostic,
    DiffDiagnosticCode,
    DiffDiagnosticSeverity,
    DiffDialect,
    DiffFile,
    DiffLine,
    ParsedDiff,
    assess_unified_diff,
    parse_unified_diff,
)

__all__ = [
    "DiffAssessment",
    "DiffAssessmentStatus",
    "DiffDiagnostic",
    "DiffDiagnosticCode",
    "DiffDiagnosticSeverity",
    "DiffDialect",
    "DiffFile",
    "DiffLine",
    "ParsedDiff",
    "assess_unified_diff",
    "parse_unified_diff",
]

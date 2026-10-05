"""Canonical unified-diff parsing primitives."""

from pr_suggestion_metrics.diff.parser import DiffFile, DiffLine, ParsedDiff, parse_unified_diff

__all__ = ["DiffFile", "DiffLine", "ParsedDiff", "parse_unified_diff"]

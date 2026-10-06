"""Compatibility facade for the decomposed deterministic feature engine.

Public imports remain stable here. Private helpers are resolved lazily from
their responsibility modules so legacy imports and ``evaluate_metrics``
compatibility lookups continue to return the implementation objects.
"""

from __future__ import annotations

from pr_suggestion_metrics.features import contracts as _contracts
from pr_suggestion_metrics.features import gumtree as _gumtree
from pr_suggestion_metrics.features import lexical as _lexical
from pr_suggestion_metrics.features import matching as _matching
from pr_suggestion_metrics.features import scoring as _scoring
from pr_suggestion_metrics.features.scoring import (
    metric_result_to_feature_row,
    raw_diff_support_issues,
    score_diff_pair,
    score_example,
)

CandidateHunk = _contracts.CandidateHunk
MetricResult = _contracts.MetricResult
ScoringExample = _contracts.ScoringExample
ScoringInput = _contracts.ScoringInput
TokenizedText = _contracts.TokenizedText
_score_example = score_example

__all__ = [
    "MetricResult",
    "metric_result_to_feature_row",
    "raw_diff_support_issues",
    "score_diff_pair",
]

_COMPATIBILITY_MODULES = (_contracts, _lexical, _matching, _gumtree, _scoring)


def __getattr__(name: str) -> object:
    """Resolve legacy private feature-engine names from their owning module."""
    for module in _COMPATIBILITY_MODULES:
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include delegated compatibility names in interactive discovery."""
    delegated_names = {name for module in _COMPATIBILITY_MODULES for name in vars(module)}
    return sorted(set(globals()) | delegated_names)

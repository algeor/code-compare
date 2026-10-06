"""Versioned contracts for deterministic text normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


NormalizationPolicyVersion = Literal["1.0"]


@dataclass(frozen=True)
class NormalizationPolicy:
    """Describe the normalization semantics used to generate metric features."""

    version: NormalizationPolicyVersion
    line_whitespace: Literal["strip_and_collapse"]
    blank_lines: Literal["drop"]
    python_indentation_tokens: Literal["omit"]
    identifier_normalization: Literal["replace_with_IDENT"]
    literal_normalization: Literal["replace_with_LITERAL"]


CURRENT_NORMALIZATION_POLICY = NormalizationPolicy(
    version="1.0",
    line_whitespace="strip_and_collapse",
    blank_lines="drop",
    python_indentation_tokens="omit",
    identifier_normalization="replace_with_IDENT",
    literal_normalization="replace_with_LITERAL",
)

NORMALIZATION_POLICY_VERSION: NormalizationPolicyVersion = CURRENT_NORMALIZATION_POLICY.version


__all__ = [
    "CURRENT_NORMALIZATION_POLICY",
    "NORMALIZATION_POLICY_VERSION",
    "NormalizationPolicy",
    "NormalizationPolicyVersion",
]

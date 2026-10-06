"""Diff precision and recall at token, file, and changed-line levels."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal, TypeVar

from pr_suggestion_metrics.diff.parser import parse_unified_diff


_WORD_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_Item = TypeVar("_Item", bound=object)
TokenOperation = Literal["added", "removed"]


@dataclass(frozen=True)
class PrecisionRecall:
    """Overlap ratios using the draft and final collections as denominators."""

    precision: float
    recall: float
    matched_count: int
    draft_count: int
    final_count: int

    @property
    def f1(self) -> float:
        """Return the harmonic mean of precision and recall."""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)


@dataclass(frozen=True)
class DiffPrecisionRecallResult:
    """Precision and recall for changed-code tokens, files, and path-aware lines."""

    token: PrecisionRecall
    relaxed_content_token: PrecisionRecall
    file: PrecisionRecall
    line: PrecisionRecall


def word_tokens(diff_text: str) -> Counter[tuple[TokenOperation, str]]:
    """Return operation-aware tokens from non-blank changed code."""
    parsed = parse_unified_diff(diff_text)
    tokens: Counter[tuple[TokenOperation, str]] = Counter()
    for line in parsed.changed_lines:
        if not line.text.strip():
            continue
        operation: TokenOperation = "added" if line.operation == "addition" else "removed"
        tokens.update((operation, token) for token in _WORD_TOKEN_PATTERN.findall(line.text))
    return tokens


def relaxed_content_word_tokens(diff_text: str) -> Counter[str]:
    """Return changed-code tokens while intentionally ignoring operation polarity."""
    parsed = parse_unified_diff(diff_text)
    return Counter(
        token
        for line in parsed.changed_lines
        if line.text.strip()
        for token in _WORD_TOKEN_PATTERN.findall(line.text)
    )


def raw_diff_word_tokens(diff_text: str) -> Counter[str]:
    """Return legacy raw-diff tokens for explicitly named diagnostics only."""
    return Counter(_WORD_TOKEN_PATTERN.findall(diff_text))


def changed_files(diff_text: str) -> set[str]:
    """Return canonical repository-relative paths from a unified diff."""
    return {
        file_diff.canonical_path
        for file_diff in parse_unified_diff(diff_text).files
        if file_diff.canonical_path is not None
    }


def changed_lines(diff_text: str) -> Counter[tuple[str, str, str]]:
    """Return path-aware, non-blank changed-line occurrences with polarity."""
    lines: Counter[tuple[str, str, str]] = Counter()
    for line in parse_unified_diff(diff_text).changed_lines:
        normalized = line.text.strip()
        if not normalized or line.path is None:
            continue
        operation = "added" if line.operation == "addition" else "removed"
        lines[(operation, line.path, normalized)] += 1
    return lines


def _counter_precision_recall(draft: Counter[_Item], final: Counter[_Item]) -> PrecisionRecall:
    matched_count = sum((draft & final).values())
    draft_count = sum(draft.values())
    final_count = sum(final.values())
    return PrecisionRecall(
        precision=matched_count / draft_count if draft_count else 0.0,
        recall=matched_count / final_count if final_count else 0.0,
        matched_count=matched_count,
        draft_count=draft_count,
        final_count=final_count,
    )


def _set_precision_recall(draft: Collection[_Item], final: Collection[_Item]) -> PrecisionRecall:
    matched_count = len(set(draft) & set(final))
    return PrecisionRecall(
        precision=matched_count / len(draft) if draft else 0.0,
        recall=matched_count / len(final) if final else 0.0,
        matched_count=matched_count,
        draft_count=len(draft),
        final_count=len(final),
    )


def compare_diffs(draft_diff: str, final_diff: str) -> DiffPrecisionRecallResult:
    """Compare unified diffs at changed-code token, file, and changed-line levels.

    Precision uses the draft as denominator: how much of the draft was kept.
    Recall uses the final diff as denominator: how much of the final was already
    present in the draft.
    """
    return DiffPrecisionRecallResult(
        token=_counter_precision_recall(word_tokens(draft_diff), word_tokens(final_diff)),
        relaxed_content_token=_counter_precision_recall(
            relaxed_content_word_tokens(draft_diff),
            relaxed_content_word_tokens(final_diff),
        ),
        file=_set_precision_recall(changed_files(draft_diff), changed_files(final_diff)),
        line=_counter_precision_recall(changed_lines(draft_diff), changed_lines(final_diff)),
    )

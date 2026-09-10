"""Diff precision and recall at token, file, and changed-line levels."""

from __future__ import annotations

import re
import shlex
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from typing import TypeVar


_WORD_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_Item = TypeVar("_Item", bound=object)


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
    """Precision and recall for raw tokens, changed files, and changed lines."""

    token: PrecisionRecall
    file: PrecisionRecall
    line: PrecisionRecall

    @property
    def aggregate_f1(self) -> float:
        """Return the equal-weight mean of token, file, and line F1 scores."""
        return (self.token.f1 + self.file.f1 + self.line.f1) / 3


def word_tokens(diff_text: str) -> Counter[str]:
    """Return case-sensitive word-token occurrences from the raw unified diff."""
    return Counter(_WORD_TOKEN_PATTERN.findall(diff_text))


def changed_files(diff_text: str) -> set[str]:
    """Return canonical repository-relative paths from a unified diff."""
    files: set[str] = set()
    old_path: str | None = None
    new_path: str | None = None
    inside_hunk = False

    def record_current_path() -> None:
        canonical_path = new_path or old_path
        if canonical_path is not None:
            files.add(canonical_path)

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            record_current_path()
            old_path, new_path = _parse_git_header_paths(line)
            inside_hunk = False
            continue
        if line.startswith("--- ") and _looks_like_diff_path(line[4:]):
            record_current_path()
            old_path = _normalize_diff_path(line[4:])
            new_path = None
            inside_hunk = False
            continue
        if not inside_hunk and line.startswith("+++ "):
            new_path = _normalize_diff_path(line[4:])
            continue
        if line.startswith("@@"):
            inside_hunk = True

    record_current_path()
    return files


def changed_lines(diff_text: str) -> Counter[tuple[str, str]]:
    """Return stripped added and removed line occurrences, including polarity."""
    lines: Counter[tuple[str, str]] = Counter()
    old_path: str | None = None
    new_path: str | None = None
    inside_hunk = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            old_path, new_path = _parse_git_header_paths(line)
            inside_hunk = False
            continue
        if line.startswith("--- ") and _looks_like_diff_path(line[4:]):
            old_path = _normalize_diff_path(line[4:])
            new_path = None
            inside_hunk = False
            continue
        if not inside_hunk and line.startswith("+++ "):
            new_path = _normalize_diff_path(line[4:])
            continue
        if line.startswith("@@"):
            inside_hunk = True
            continue
        if not inside_hunk or line.startswith("\\"):
            continue
        if line.startswith("+") and new_path is not None:
            lines[("added", line[1:].strip())] += 1
        elif line.startswith("-") and old_path is not None:
            lines[("removed", line[1:].strip())] += 1
    return lines


def _parse_git_header_paths(line: str) -> tuple[str | None, str | None]:
    try:
        parts = shlex.split(line)
    except ValueError:
        return None, None
    if len(parts) < 4:
        return None, None
    return _normalize_diff_path(parts[2]), _normalize_diff_path(parts[3])


def _looks_like_diff_path(path: str) -> bool:
    cleaned = path.strip()
    return cleaned == "/dev/null" or cleaned.startswith(("a/", "b/"))


def _normalize_diff_path(path: str) -> str | None:
    cleaned = path.strip()
    if cleaned == "/dev/null":
        return None
    if cleaned.startswith(("a/", "b/")):
        return cleaned[2:]
    return cleaned


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
    """Compare raw unified diffs at token, changed-file, and changed-line levels.

    Precision uses the draft as denominator: how much of the draft was kept.
    Recall uses the final diff as denominator: how much of the final was already
    present in the draft.
    """
    return DiffPrecisionRecallResult(
        token=_counter_precision_recall(word_tokens(draft_diff), word_tokens(final_diff)),
        file=_set_precision_recall(changed_files(draft_diff), changed_files(final_diff)),
        line=_counter_precision_recall(changed_lines(draft_diff), changed_lines(final_diff)),
    )

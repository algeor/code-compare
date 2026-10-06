"""Parse Git-style unified diffs into immutable, path-aware data objects.

The parser records file identity, rename metadata, hunk membership, change
operations, and line numbers on both sides of a diff. It accepts standard Git
headers as well as unified diffs that begin directly with ``---``/``+++`` file
markers.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Literal


DiffOperation = Literal["addition", "deletion", "context"]
_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(frozen=True)
class DiffLine:
    """Represent one addition, deletion, or context line inside a diff hunk."""

    operation: DiffOperation
    text: str
    old_path: str | None
    new_path: str | None
    hunk_index: int
    old_line_number: int | None
    new_line_number: int | None

    @property
    def path(self) -> str | None:
        """Return the file path on the side where this line exists.

        Deleted lines belong to the old file. Additions and context lines use
        the new file path. The result is ``None`` when that side of the diff is
        represented by Git's ``/dev/null`` sentinel.
        """
        if self.operation == "deletion":
            return self.old_path
        return self.new_path


@dataclass(frozen=True)
class DiffFile:
    """Represent one file section and all of its parsed hunk lines."""

    old_path: str | None
    new_path: str | None
    rename_from: str | None
    rename_to: str | None
    lines: tuple[DiffLine, ...]

    @property
    def canonical_path(self) -> str | None:
        """Return the final path, or the original path when the file was deleted."""
        return self.new_path or self.old_path

    @property
    def hunk_count(self) -> int:
        """Count distinct hunks represented by this file's parsed lines."""
        return len({line.hunk_index for line in self.lines})

    @property
    def changed_lines(self) -> tuple[DiffLine, ...]:
        """Return this file's additions and deletions in source order.

        Context lines are excluded. Formatting-only additions and deletions are
        retained because the parser does not classify semantic significance.
        """
        return tuple(line for line in self.lines if line.operation != "context")


@dataclass(frozen=True)
class ParsedDiff:
    """Represent all file sections parsed from one unified diff string."""

    files: tuple[DiffFile, ...]

    @property
    def lines(self) -> tuple[DiffLine, ...]:
        """Flatten every file's parsed hunk lines into one ordered tuple."""
        return tuple(line for file_diff in self.files for line in file_diff.lines)

    @property
    def changed_lines(self) -> tuple[DiffLine, ...]:
        """Return additions and deletions from every parsed file.

        Context lines are excluded, while formatting-only changes are retained.
        """
        return tuple(line for line in self.lines if line.operation != "context")

    @property
    def hunk_count(self) -> int:
        """Return the sum of the distinct hunk counts for all parsed files."""
        return sum(file_diff.hunk_count for file_diff in self.files)


@dataclass
class _FileBuilder:
    """Accumulate mutable file state before creating an immutable ``DiffFile``."""

    old_path: str | None = None
    new_path: str | None = None
    rename_from: str | None = None
    rename_to: str | None = None
    saw_file_markers: bool = False
    lines: list[DiffLine] = field(default_factory=list)

    def freeze(self) -> DiffFile:
        """Create an immutable snapshot of the accumulated file metadata and lines."""
        return DiffFile(
            old_path=self.old_path,
            new_path=self.new_path,
            rename_from=self.rename_from,
            rename_to=self.rename_to,
            lines=tuple(self.lines),
        )


def normalize_diff_path(raw_path: str) -> str | None:
    """Normalize a path read from unified-diff metadata.

    Surrounding whitespace and tab-separated metadata are removed. Git's
    synthetic ``a/`` and ``b/`` prefixes are stripped, and ``/dev/null`` or an
    empty path becomes ``None``.
    """
    cleaned = raw_path.strip().split("\t", maxsplit=1)[0]
    if cleaned == "/dev/null":
        return None
    if cleaned.startswith(("a/", "b/")):
        return cleaned[2:]
    return cleaned or None


def _is_diff_path(raw_path: str) -> bool:
    """Return whether a value uses a Git diff prefix or ``/dev/null``."""
    cleaned = raw_path.strip().split("\t", maxsplit=1)[0]
    return cleaned == "/dev/null" or cleaned.startswith(("a/", "b/"))


def _git_header_paths(line: str) -> tuple[str | None, str | None]:
    """Extract normalized old and new paths from a ``diff --git`` header.

    Shell-style tokenization supports quoted paths containing spaces. Malformed
    quoting or a header with fewer than four fields produces ``(None, None)``.
    """
    try:
        parts = shlex.split(line)
    except ValueError:
        return None, None
    if len(parts) < 4:
        return None, None
    return normalize_diff_path(parts[2]), normalize_diff_path(parts[3])


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    """Parse unified-diff text into file, hunk, operation, and line metadata.

    Args:
        diff_text: A Git-style unified diff. Preamble text and unsupported
            metadata lines are ignored.

    Returns:
        An immutable ``ParsedDiff`` whose files and lines preserve source order.

    The parser understands ``diff --git`` headers, ``---``/``+++`` markers,
    rename metadata, and standard ``@@`` hunk headers. Added lines receive only
    a new line number, deleted lines receive only an old line number, and
    context lines receive both.
    """
    files: list[DiffFile] = []
    current: _FileBuilder | None = None
    inside_hunk = False
    hunk_index = 0
    old_line_number = 0
    new_line_number = 0

    def finish_file() -> None:
        """Store the current non-empty file builder and clear parser state."""
        nonlocal current
        if current is not None and (
            current.old_path is not None
            or current.new_path is not None
            or current.rename_from is not None
            or current.rename_to is not None
            or current.lines
        ):
            files.append(current.freeze())
        current = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            finish_file()
            old_path, new_path = _git_header_paths(raw_line)
            current = _FileBuilder(old_path=old_path, new_path=new_path)
            inside_hunk = False
            hunk_index = 0
            continue

        if raw_line.startswith("--- ") and _is_diff_path(raw_line[4:]):
            if current is None:
                current = _FileBuilder()
            elif current.lines or current.saw_file_markers:
                finish_file()
                current = _FileBuilder()
            current.old_path = normalize_diff_path(raw_line[4:])
            current.saw_file_markers = True
            inside_hunk = False
            continue

        if raw_line.startswith("+++ ") and _is_diff_path(raw_line[4:]):
            if current is None:
                current = _FileBuilder()
            current.new_path = normalize_diff_path(raw_line[4:])
            current.saw_file_markers = True
            inside_hunk = False
            continue

        if current is None:
            continue

        if raw_line.startswith("rename from ") and not inside_hunk:
            current.rename_from = normalize_diff_path(raw_line.removeprefix("rename from "))
            current.old_path = current.rename_from
            continue

        if raw_line.startswith("rename to ") and not inside_hunk:
            current.rename_to = normalize_diff_path(raw_line.removeprefix("rename to "))
            current.new_path = current.rename_to
            continue

        hunk_match = _HUNK_HEADER.match(raw_line)
        if raw_line.startswith("@@"):
            inside_hunk = True
            hunk_index += 1
            old_line_number = int(hunk_match.group("old_start")) if hunk_match else 0
            new_line_number = int(hunk_match.group("new_start")) if hunk_match else 0
            continue

        if not inside_hunk or raw_line.startswith("\\"):
            continue

        if raw_line.startswith("+"):
            current.lines.append(
                DiffLine(
                    operation="addition",
                    text=raw_line[1:],
                    old_path=current.old_path,
                    new_path=current.new_path,
                    hunk_index=hunk_index,
                    old_line_number=None,
                    new_line_number=new_line_number,
                )
            )
            new_line_number += 1
        elif raw_line.startswith("-"):
            current.lines.append(
                DiffLine(
                    operation="deletion",
                    text=raw_line[1:],
                    old_path=current.old_path,
                    new_path=current.new_path,
                    hunk_index=hunk_index,
                    old_line_number=old_line_number,
                    new_line_number=None,
                )
            )
            old_line_number += 1
        elif raw_line.startswith(" "):
            current.lines.append(
                DiffLine(
                    operation="context",
                    text=raw_line[1:],
                    old_path=current.old_path,
                    new_path=current.new_path,
                    hunk_index=hunk_index,
                    old_line_number=old_line_number,
                    new_line_number=new_line_number,
                )
            )
            old_line_number += 1
            new_line_number += 1

    finish_file()
    return ParsedDiff(files=tuple(files))

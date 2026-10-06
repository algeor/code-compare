"""Parse Git-style unified diffs into immutable, path-aware data objects.

The parser records file identity, rename metadata, hunk membership, change
operations, and line numbers on both sides of a diff. It accepts standard Git
headers as well as unified diffs that begin directly with ``---``/``+++`` file
markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


DiffOperation = Literal["addition", "deletion", "context"]
DiffDialect = Literal["git_unified", "suggestion_fragment"]
DiffAssessmentStatus = Literal["valid", "invalid"]
DiffDiagnosticSeverity = Literal["error", "warning"]
DiffDiagnosticCode = Literal[
    "empty_input",
    "non_diff_input",
    "malformed_git_header",
    "invalid_file_marker",
    "conflicting_file_path",
    "missing_file_marker_pair",
    "missing_hunk",
    "reordered_file_markers",
    "partial_rename_metadata",
    "malformed_hunk_header",
    "incomplete_hunk",
    "overflowing_hunk",
    "invalid_hunk_body_line",
]
_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)
_STRICT_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?: .*)?$"
)
_NO_NEWLINE_MARKER = r"\ No newline at end of file"
_QUOTED_GIT_PATH = r'"(?:\\.|[^"\\])*"'
_GIT_C_ESCAPES = {
    "a": 0x07,
    "b": 0x08,
    "t": 0x09,
    "n": 0x0A,
    "v": 0x0B,
    "f": 0x0C,
    "r": 0x0D,
    '"': 0x22,
    "\\": 0x5C,
}
_DIAGNOSTIC_MESSAGES: dict[DiffDiagnosticCode, str] = {
    "empty_input": "Diff input is empty.",
    "non_diff_input": "Input does not contain unified-diff structure.",
    "malformed_git_header": "Git header must contain exactly one valid a/ path and one valid b/ path.",
    "invalid_file_marker": "File marker must contain the expected Git-prefixed path or /dev/null.",
    "conflicting_file_path": "File marker path conflicts with the corresponding Git header path.",
    "missing_file_marker_pair": "File section must contain paired --- and +++ markers before a hunk.",
    "missing_hunk": "A file section with --- and +++ markers must contain at least one hunk.",
    "reordered_file_markers": "The --- file marker must precede the +++ file marker.",
    "partial_rename_metadata": "Rename metadata must contain both rename from and rename to lines.",
    "malformed_hunk_header": "Hunk header is malformed for the selected diff dialect.",
    "incomplete_hunk": "Hunk body ended before its declared line counts were satisfied.",
    "overflowing_hunk": "Hunk body exceeds its declared line counts.",
    "invalid_hunk_body_line": "Hunk body line must start with a space, +, or -.",
}


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


@dataclass(frozen=True)
class DiffDiagnostic:
    """Describe one stable structural problem in unified-diff input."""

    code: DiffDiagnosticCode
    severity: DiffDiagnosticSeverity
    message: str
    line_number: int | None
    file_path: str | None
    hunk_index: int | None


@dataclass(frozen=True)
class DiffAssessment:
    """Pair compatibility parse output with structural validity diagnostics."""

    dialect: DiffDialect
    status: DiffAssessmentStatus
    parsed_diff: ParsedDiff
    diagnostics: tuple[DiffDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether no structural errors were diagnosed."""
        return self.status == "valid"


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


@dataclass
class _DiagnosticFileState:
    """Track structural metadata for one file section during assessment."""

    old_path: str | None = None
    new_path: str | None = None
    header_old_path: str | None = None
    header_new_path: str | None = None
    rename_from_line: int | None = None
    rename_to_line: int | None = None
    old_marker_line: int | None = None
    new_marker_line: int | None = None
    marker_pair_reported: bool = False
    hunk_count: int = 0

    @property
    def path(self) -> str | None:
        """Return the best available path for diagnostic context."""
        return self.new_path or self.old_path


@dataclass
class _DiagnosticHunkState:
    """Track declared and observed line counts for one hunk."""

    index: int
    header_line: int
    expected_old: int | None
    expected_new: int | None
    observed_old: int = 0
    observed_new: int = 0
    overflow_reported: bool = False

    @property
    def counts_satisfied(self) -> bool:
        """Return whether a counted hunk has consumed both declared sides."""
        return (
            self.expected_old is not None
            and self.expected_new is not None
            and self.observed_old >= self.expected_old
            and self.observed_new >= self.expected_new
        )


def _decode_git_quoted_path(path: str) -> str:
    """Decode Git's double-quoted C-style path representation."""
    payload = path[1:-1]
    decoded = bytearray()
    index = 0
    while index < len(payload):
        character = payload[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(payload):
            decoded.extend(b"\\")
            break
        escaped = payload[index]
        if escaped in _GIT_C_ESCAPES:
            decoded.append(_GIT_C_ESCAPES[escaped])
            index += 1
            continue
        octal_match = re.match(r"[0-7]{1,3}", payload[index:])
        if octal_match is not None:
            octal_value = int(octal_match.group(), 8)
            if octal_value <= 0xFF:
                decoded.append(octal_value)
            else:
                decoded.extend(f"\\{octal_match.group()}".encode("ascii"))
            index += len(octal_match.group())
            continue
        decoded.extend(escaped.encode("utf-8"))
        index += 1
    return decoded.decode("utf-8", errors="surrogateescape")


def _clean_diff_path(raw_path: str) -> str:
    cleaned = raw_path.strip().split("\t", maxsplit=1)[0]
    if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
        return _decode_git_quoted_path(cleaned)
    return cleaned


def normalize_diff_path(raw_path: str) -> str | None:
    """Normalize a path read from unified-diff metadata.

    Surrounding whitespace and tab-separated metadata are removed. Git's
    synthetic ``a/`` and ``b/`` prefixes are stripped, and ``/dev/null`` or an
    empty path becomes ``None``.
    """
    cleaned = _clean_diff_path(raw_path)
    if cleaned == "/dev/null":
        return None
    if cleaned.startswith(("a/", "b/")):
        return cleaned[2:]
    return cleaned or None


def _is_diff_path(raw_path: str) -> bool:
    """Return whether a value uses a Git diff prefix or ``/dev/null``."""
    cleaned = _clean_diff_path(raw_path)
    return cleaned == "/dev/null" or cleaned.startswith(("a/", "b/"))


def _validated_git_header_paths(line: str) -> tuple[str | None, str | None] | None:
    """Parse unambiguous paths and defer ambiguous space-containing paths to markers."""
    prefix = "diff --git "
    if not line.startswith(prefix):
        return None
    raw_paths = line.removeprefix(prefix)
    pair_pattern = (
        rf"(?P<old>{_QUOTED_GIT_PATH}) (?P<new>{_QUOTED_GIT_PATH}|b/.+)"
        rf"|(?P<plain_old>a/\S+) (?P<plain_new>b/\S+)"
        rf"|(?P<mixed_old>a/\S+) (?P<quoted_new>{_QUOTED_GIT_PATH})"
    )
    pair_match = re.fullmatch(pair_pattern, raw_paths)
    if pair_match is not None:
        old_path = pair_match.group("old") or pair_match.group("plain_old") or pair_match.group("mixed_old")
        new_path = pair_match.group("new") or pair_match.group("plain_new") or pair_match.group("quoted_new")
        if not _is_diff_path(old_path) or not _is_diff_path(new_path):
            return None
        normalized_old = normalize_diff_path(old_path)
        normalized_new = normalize_diff_path(new_path)
        if normalized_old is None or normalized_new is None:
            return None
        return normalized_old, normalized_new

    has_unquoted_new_path = " b/" in raw_paths and not raw_paths.endswith(" b/")
    has_quoted_new_path = re.search(rf" {_QUOTED_GIT_PATH}$", raw_paths) is not None
    if raw_paths.startswith("a/") and (has_unquoted_new_path or has_quoted_new_path):
        return None, None
    return None


def _git_header_paths(line: str) -> tuple[str | None, str | None]:
    """Extract normalized old and new paths from a ``diff --git`` header.

    Shell-style tokenization supports quoted paths containing spaces. Malformed
    quoting or a header with fewer than four fields produces ``(None, None)``.
    """
    parsed_paths = _validated_git_header_paths(line)
    return parsed_paths if parsed_paths is not None else (None, None)


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
    remaining_old_lines: int | None = None
    remaining_new_lines: int | None = None

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

        inside_counted_hunk = (
            inside_hunk and remaining_old_lines is not None and remaining_new_lines is not None
        )
        if raw_line.startswith("--- ") and _is_diff_path(raw_line[4:]) and not inside_counted_hunk:
            if current is None:
                current = _FileBuilder()
            elif current.lines or current.saw_file_markers:
                finish_file()
                current = _FileBuilder()
            current.old_path = normalize_diff_path(raw_line[4:])
            current.saw_file_markers = True
            inside_hunk = False
            continue

        if raw_line.startswith("+++ ") and _is_diff_path(raw_line[4:]) and not inside_counted_hunk:
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
            remaining_old_lines = (
                int(hunk_match.group("old_count") or 1) if hunk_match else None
            )
            remaining_new_lines = (
                int(hunk_match.group("new_count") or 1) if hunk_match else None
            )
            if remaining_old_lines == remaining_new_lines == 0:
                inside_hunk = False
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
            if remaining_new_lines is not None:
                remaining_new_lines -= 1
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
            if remaining_old_lines is not None:
                remaining_old_lines -= 1
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
            if remaining_old_lines is not None:
                remaining_old_lines -= 1
            if remaining_new_lines is not None:
                remaining_new_lines -= 1

        if remaining_old_lines == remaining_new_lines == 0:
            inside_hunk = False

    finish_file()
    return ParsedDiff(files=tuple(files))


def _strict_git_header_paths(line: str) -> tuple[str | None, str | None] | None:
    """Return validated Git header paths, or ``None`` for malformed input."""
    return _validated_git_header_paths(line)


def _validated_marker_path(line: str, marker: Literal["---", "+++"]) -> tuple[bool, str | None]:
    """Validate and normalize one strict Git file marker."""
    if not line.startswith(f"{marker} "):
        return False, None
    raw_path = line[4:].strip().split("\t", maxsplit=1)[0]
    expected_prefix = "a/" if marker == "---" else "b/"
    cleaned_path = _clean_diff_path(raw_path)
    if cleaned_path != "/dev/null" and (
        not cleaned_path.startswith(expected_prefix) or len(cleaned_path) == 2
    ):
        return False, None
    return True, normalize_diff_path(raw_path)


def assess_unified_diff(
    diff_text: str,
    *,
    dialect: DiffDialect = "git_unified",
) -> DiffAssessment:
    """Assess unified-diff structure without changing compatibility parse output.

    ``git_unified`` requires counted hunk headers. ``suggestion_fragment`` also
    accepts the bare ``@@`` pseudo-hunk emitted by internal suggestion
    collection. Both dialects require ordered Git-style file marker pairs and
    diagnose malformed structure. This low-level contract intentionally does
    not classify whether a structurally valid diff is supported by a model.
    """
    if dialect not in ("git_unified", "suggestion_fragment"):
        raise ValueError(f"unsupported diff dialect: {dialect}")

    parsed_diff = parse_unified_diff(diff_text)
    diagnostics: list[DiffDiagnostic] = []
    section: _DiagnosticFileState | None = None
    hunk: _DiagnosticHunkState | None = None
    saw_diff_structure = False

    def add_diagnostic(
        code: DiffDiagnosticCode,
        *,
        line_number: int | None,
        file_path: str | None = None,
        hunk_index: int | None = None,
    ) -> None:
        diagnostics.append(
            DiffDiagnostic(
                code=code,
                severity="error",
                message=_DIAGNOSTIC_MESSAGES[code],
                line_number=line_number,
                file_path=file_path,
                hunk_index=hunk_index,
            )
        )

    def ensure_section() -> _DiagnosticFileState:
        nonlocal section
        if section is None:
            section = _DiagnosticFileState()
        return section

    def finish_hunk() -> None:
        nonlocal hunk
        if hunk is None:
            return
        incomplete_old = hunk.expected_old is not None and hunk.observed_old < hunk.expected_old
        incomplete_new = hunk.expected_new is not None and hunk.observed_new < hunk.expected_new
        if incomplete_old or incomplete_new:
            add_diagnostic(
                "incomplete_hunk",
                line_number=hunk.header_line,
                file_path=section.path if section is not None else None,
                hunk_index=hunk.index,
            )
        hunk = None

    def report_missing_marker_pair(
        current: _DiagnosticFileState,
        line_number: int,
        *,
        hunk_index: int | None = None,
    ) -> None:
        if current.marker_pair_reported:
            return
        current.marker_pair_reported = True
        add_diagnostic(
            "missing_file_marker_pair",
            line_number=line_number,
            file_path=current.path,
            hunk_index=hunk_index,
        )

    def finish_section() -> None:
        nonlocal section
        finish_hunk()
        if section is None:
            return
        if (section.old_marker_line is None) != (section.new_marker_line is None):
            marker_line = section.old_marker_line or section.new_marker_line
            if marker_line is not None:
                report_missing_marker_pair(section, marker_line)
        if section.old_marker_line is not None and section.new_marker_line is not None and section.hunk_count == 0:
            add_diagnostic(
                "missing_hunk",
                line_number=section.new_marker_line,
                file_path=section.path,
            )
        if (section.rename_from_line is None) != (section.rename_to_line is None):
            rename_line = section.rename_from_line or section.rename_to_line
            add_diagnostic(
                "partial_rename_metadata",
                line_number=rename_line,
                file_path=section.path,
            )
        section = None

    def process_hunk_body(line: str, line_number: int) -> None:
        if hunk is None:
            return
        if line == _NO_NEWLINE_MARKER:
            return

        old_increment = 0
        new_increment = 0
        if line.startswith("+"):
            new_increment = 1
        elif line.startswith("-"):
            old_increment = 1
        elif line.startswith(" "):
            old_increment = 1
            new_increment = 1
        else:
            add_diagnostic(
                "invalid_hunk_body_line",
                line_number=line_number,
                file_path=section.path if section is not None else None,
                hunk_index=hunk.index,
            )
            return

        exceeds_old = hunk.expected_old is not None and hunk.observed_old + old_increment > hunk.expected_old
        exceeds_new = hunk.expected_new is not None and hunk.observed_new + new_increment > hunk.expected_new
        if (exceeds_old or exceeds_new) and not hunk.overflow_reported:
            hunk.overflow_reported = True
            add_diagnostic(
                "overflowing_hunk",
                line_number=line_number,
                file_path=section.path if section is not None else None,
                hunk_index=hunk.index,
            )
        hunk.observed_old += old_increment
        hunk.observed_new += new_increment

    if not diff_text.strip():
        add_diagnostic("empty_input", line_number=None)
    else:
        for line_number, raw_line in enumerate(diff_text.splitlines(), start=1):
            starts_git_header = raw_line.startswith("diff --git")
            starts_hunk_header = raw_line.startswith("@@")
            looks_like_marker = raw_line.startswith(("---", "+++"))

            if hunk is not None:
                counted_body_incomplete = hunk.expected_old is not None and not hunk.counts_satisfied
                marker_ends_hunk = looks_like_marker and not counted_body_incomplete
                if not starts_git_header and not starts_hunk_header and not marker_ends_hunk:
                    process_hunk_body(raw_line, line_number)
                    continue
                finish_hunk()

            if starts_git_header:
                saw_diff_structure = True
                finish_section()
                header_paths = _strict_git_header_paths(raw_line)
                if header_paths is None:
                    section = _DiagnosticFileState()
                    add_diagnostic("malformed_git_header", line_number=line_number)
                else:
                    section = _DiagnosticFileState(
                        old_path=header_paths[0],
                        new_path=header_paths[1],
                        header_old_path=header_paths[0],
                        header_new_path=header_paths[1],
                    )
                continue

            if raw_line.startswith("---"):
                saw_diff_structure = True
                valid_marker, marker_path = _validated_marker_path(raw_line, "---")
                if not valid_marker:
                    add_diagnostic(
                        "invalid_file_marker",
                        line_number=line_number,
                        file_path=section.path if section is not None else None,
                    )
                    continue
                current = ensure_section()
                if current.old_marker_line is not None or current.hunk_count:
                    finish_section()
                    current = ensure_section()
                if (
                    marker_path is not None
                    and current.header_old_path is not None
                    and marker_path != current.header_old_path
                ):
                    add_diagnostic(
                        "conflicting_file_path",
                        line_number=line_number,
                        file_path=marker_path,
                    )
                current.old_marker_line = line_number
                current.old_path = marker_path
                continue

            if raw_line.startswith("+++"):
                saw_diff_structure = True
                valid_marker, marker_path = _validated_marker_path(raw_line, "+++")
                if not valid_marker:
                    add_diagnostic(
                        "invalid_file_marker",
                        line_number=line_number,
                        file_path=section.path if section is not None else None,
                    )
                    continue
                current = ensure_section()
                if current.new_marker_line is not None or current.hunk_count:
                    finish_section()
                    current = ensure_section()
                if current.old_marker_line is None:
                    add_diagnostic(
                        "reordered_file_markers",
                        line_number=line_number,
                        file_path=marker_path or current.path,
                    )
                if (
                    marker_path is not None
                    and current.header_new_path is not None
                    and marker_path != current.header_new_path
                ):
                    add_diagnostic(
                        "conflicting_file_path",
                        line_number=line_number,
                        file_path=marker_path,
                    )
                current.new_marker_line = line_number
                current.new_path = marker_path
                continue

            if raw_line.startswith("rename from "):
                saw_diff_structure = True
                current = ensure_section()
                current.rename_from_line = line_number
                current.old_path = normalize_diff_path(raw_line.removeprefix("rename from "))
                continue

            if raw_line.startswith("rename to "):
                saw_diff_structure = True
                current = ensure_section()
                current.rename_to_line = line_number
                current.new_path = normalize_diff_path(raw_line.removeprefix("rename to "))
                continue

            if starts_hunk_header:
                saw_diff_structure = True
                current = ensure_section()
                if current.old_marker_line is None or current.new_marker_line is None:
                    report_missing_marker_pair(
                        current,
                        line_number,
                        hunk_index=current.hunk_count + 1,
                    )
                current.hunk_count += 1
                hunk_match = _STRICT_HUNK_HEADER.fullmatch(raw_line)
                bare_fragment_hunk = dialect == "suggestion_fragment" and raw_line == "@@"
                if hunk_match is None and not bare_fragment_hunk:
                    add_diagnostic(
                        "malformed_hunk_header",
                        line_number=line_number,
                        file_path=current.path,
                        hunk_index=current.hunk_count,
                    )
                hunk = _DiagnosticHunkState(
                    index=current.hunk_count,
                    header_line=line_number,
                    expected_old=(
                        int(hunk_match.group("old_count") or 1) if hunk_match is not None else None
                    ),
                    expected_new=(
                        int(hunk_match.group("new_count") or 1) if hunk_match is not None else None
                    ),
                )

        finish_section()
        if not saw_diff_structure:
            add_diagnostic("non_diff_input", line_number=1)

    status: DiffAssessmentStatus = "invalid" if diagnostics else "valid"
    return DiffAssessment(
        dialect=dialect,
        status=status,
        parsed_diff=parsed_diff,
        diagnostics=tuple(diagnostics),
    )

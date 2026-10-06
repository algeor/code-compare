"""Shared serialization helpers for validated project artifacts."""

from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def atomic_replace_text(path: Path, content: str) -> None:
    """Atomically replace *path* with UTF-8 text via a sibling temporary file."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@contextmanager
def staged_output_directory(path: Path) -> Iterator[Path]:
    """Yield a sibling staging directory, then rename it to a new final path."""
    if os.path.lexists(path):
        raise FileExistsError(errno.EEXIST, "Output target already exists", path)

    staging_path = Path(
        tempfile.mkdtemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
    )
    try:
        yield staging_path
        if os.path.lexists(path):
            raise FileExistsError(errno.EEXIST, "Output target already exists", path)
        os.rename(staging_path, path)
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)


def parse_jsonl_objects(content: str, *, source: str | Path) -> list[dict[str, Any]]:
    """Parse non-empty JSONL lines and require one object per line."""
    return [row for _, row in _iter_jsonl_objects(content.splitlines(), source=source)]


def _iter_jsonl_objects(
    lines: Iterable[str], *, source: str | Path
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Parse JSONL lines while retaining their physical line numbers."""
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {source}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object at {source}:{line_number}")
        yield line_number, value


def iter_jsonl_objects(
    path: Path, *, errors: str = "strict"
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Stream UTF-8 JSONL objects with physical line numbers."""
    with path.open(encoding="utf-8", errors=errors) as stream:
        yield from _iter_jsonl_objects(stream, source=path)


def read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    """Read UTF-8 JSONL objects with consistent path and line diagnostics."""
    return [row for _, row in iter_jsonl_objects(path)]


def write_jsonl_object_lines(
    path: Path,
    lines: Iterable[str],
    *,
    atomic: bool = False,
) -> None:
    """Write pre-serialized JSON objects without changing their bytes."""
    validated_lines: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object at {path}:{line_number}")
        validated_lines.append(line + "\n")

    content = "".join(validated_lines)
    if atomic:
        atomic_replace_text(path, content)
    else:
        path.write_text(content, encoding="utf-8")


def write_jsonl_objects(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    separators: tuple[str, str] | None = None,
    atomic: bool = False,
) -> None:
    """Write UTF-8 JSONL with one strictly validated object per line."""
    lines: list[str] = []
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Expected a JSON object at {path}:{line_number}")
        lines.append(
            json.dumps(
                row,
                ensure_ascii=ensure_ascii,
                sort_keys=sort_keys,
                separators=separators,
            )
        )
    write_jsonl_object_lines(path, lines, atomic=atomic)

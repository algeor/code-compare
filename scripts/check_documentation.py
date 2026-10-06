#!/usr/bin/env python3
"""Validate active documentation structure without scanning archived generated Markdown."""

from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCUMENTS = ("README.md",)
STALE_REFERENCES = (
    "docs/final-polish-review-2026-09-14.md",
    "docs/team-codebase-review.md",
    "docs/presentation/",
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def active_documents() -> list[Path]:
    """Return root and active docs while intentionally excluding research archives."""
    root_documents = [REPOSITORY_ROOT / relative_path for relative_path in ROOT_DOCUMENTS]
    docs_documents = sorted((REPOSITORY_ROOT / "docs").glob("*.md"))
    return [path for path in [*root_documents, *docs_documents] if path.is_file()]


def relative_name(path: Path) -> str:
    """Return a stable repository-relative POSIX path."""
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def validate_document(path: Path) -> list[str]:
    """Return validation errors for one active Markdown document."""
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    name = relative_name(path)

    if not lines or not lines[0].startswith("# "):
        errors.append(f"{name}: first line must be one H1 heading")
    for line_number, line in enumerate(lines, start=1):
        if line != line.rstrip():
            errors.append(f"{name}:{line_number}: trailing whitespace")
    for stale_reference in STALE_REFERENCES:
        if stale_reference in content:
            errors.append(f"{name}: stale reference to {stale_reference}")

    for match in MARKDOWN_LINK_PATTERN.finditer(content):
        raw_target = match.group(1).strip().removeprefix("<").removesuffix(">")
        target = raw_target.split("#", maxsplit=1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved_target = (path.parent / target).resolve()
        if not resolved_target.exists():
            errors.append(f"{name}: relative link does not exist: {raw_target}")

    if name.startswith("docs/") and name != "docs/implementation-progress.md" and "**Status:**" not in content:
        errors.append(f"{name}: missing **Status:** metadata")
    if name == "docs/implementation-progress.md" and "**Last updated:**" not in content:
        errors.append(f"{name}: missing **Last updated:** metadata")
    return errors


def validate_index(documents: list[Path]) -> list[str]:
    """Require every active docs file to be discoverable from docs/README.md."""
    index_path = REPOSITORY_ROOT / "docs" / "README.md"
    index_content = index_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for path in documents:
        if path.parent != index_path.parent or path == index_path:
            continue
        if path.name not in index_content:
            errors.append(f"docs/README.md: missing active document {path.name}")
    return errors


def main() -> int:
    """Validate all active documentation and print one concise result."""
    documents = active_documents()
    errors = [error for path in documents for error in validate_document(path)]
    errors.extend(validate_index(documents))
    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation verified: {len(documents)} active Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

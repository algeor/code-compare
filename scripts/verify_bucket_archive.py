"""Verify the unsupported bucket-era archive against its inventory manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = REPOSITORY_ROOT / "research" / "archive" / "bucket-era"
MANIFEST_PATH = ARCHIVE_ROOT / "archive_manifest.json"


def _section_inventory(section: str) -> dict[str, Any]:
    directory = ARCHIVE_ROOT / section
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for path in files:
        payload = path.read_bytes()
        total_bytes += len(payload)
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return {
        "files": len(files),
        "bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_sections = manifest.get("sections")
    if not isinstance(expected_sections, dict) or not expected_sections:
        raise ValueError("Archive manifest must define non-empty sections")

    failures: list[str] = []
    for section, expected in expected_sections.items():
        actual = _section_inventory(section)
        if actual != expected:
            failures.append(f"{section}: expected {expected}, received {actual}")

    unexpected_sections = sorted(
        path.name for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name not in expected_sections
    )
    if unexpected_sections:
        failures.append(f"unexpected sections: {unexpected_sections}")

    if failures:
        print("Bucket archive verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    file_count = sum(section["files"] for section in expected_sections.values())
    print(f"Bucket archive verified: {file_count} payload files across {len(expected_sections)} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared filesystem anchors for the package.

Centralizes the repository-root computation so the brittle ``parents[2]``
directory-hop count lives in exactly one place.
"""

from __future__ import annotations

from pathlib import Path

#: Absolute path to the repository root (``src/pr_suggestion_metrics`` -> root).
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

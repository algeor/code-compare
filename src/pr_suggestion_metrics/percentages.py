"""Shared validation and rounding policy for percentage values."""

from __future__ import annotations

from typing import Any

import numpy as np


OBSOLETE_DERIVED_LABEL_FIELDS = frozenset({"label", "expected_percentage_bucket", "suggested_label"})


def _is_boolean(value: Any) -> bool:
    return isinstance(value, (bool, np.bool_))


def _parse_numeric_percentage(value: Any, *, name: str) -> float:
    if _is_boolean(value):
        raise ValueError(f"{name} must be numeric, not boolean")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric: {value!r}") from error


def parse_integer_percentage(value: Any, *, name: str = "percentage") -> int:
    """Parse an integer percentage, rejecting coercions that lose information."""
    percentage = _parse_numeric_percentage(value, name=name)
    if not np.isfinite(percentage) or not percentage.is_integer():
        raise ValueError(f"{name} must be a finite integer: {value!r}")
    parsed = int(percentage)
    if not 0 <= parsed <= 100:
        raise ValueError(f"{name} must be between 0 and 100: {value!r}")
    return parsed


def validate_continuous_percentage(value: Any, *, name: str = "percentage") -> float:
    """Return a finite continuous percentage in the inclusive 0..100 range."""
    percentage = _parse_numeric_percentage(value, name=name)
    if not np.isfinite(percentage) or not 0.0 <= percentage <= 100.0:
        raise ValueError(f"{name} must be finite and between 0 and 100: {value!r}")
    return percentage


def round_bounded_percentage(value: Any) -> int | np.ndarray:
    """Clip model output to 0..100, then round ties to even."""
    try:
        values = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"model percentage must be numeric: {value!r}") from error
    rounded = np.rint(np.clip(values, 0.0, 100.0))
    if np.any(np.isnan(rounded)):
        raise ValueError("model percentage must not be NaN")
    if rounded.ndim == 0:
        return int(rounded.item())
    return rounded.astype(int)

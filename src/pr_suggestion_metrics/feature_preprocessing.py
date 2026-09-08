"""Shared validation and coercion for model feature values."""

from __future__ import annotations

from numbers import Real

import pandas as pd


_BOOLEAN_STRINGS = {
    "false": 0,
    "true": 1,
    "0": 0,
    "1": 1,
}


def coerce_boolean_series(values: pd.Series, feature_name: str) -> pd.Series:
    """Convert explicit boolean representations to integers and reject all others."""
    converted: list[int] = []
    for row_index, value in values.items():
        if isinstance(value, bool):
            converted.append(int(value))
            continue
        if isinstance(value, Real) and value in (0, 1):
            converted.append(1 if value == 1 else 0)
            continue
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in _BOOLEAN_STRINGS:
                converted.append(_BOOLEAN_STRINGS[normalized])
                continue
        raise ValueError(
            f"Invalid boolean value for feature {feature_name!r} at row index {row_index!r}: {value!r}. "
            "Expected true, false, 1, or 0."
        )
    return pd.Series(converted, index=values.index, dtype="int64")

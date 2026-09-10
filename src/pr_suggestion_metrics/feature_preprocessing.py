"""Shared validation and coercion for model feature values."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import pandas as pd


_BOOLEAN_STRINGS = {
    "false": 0,
    "true": 1,
    "0": 0,
    "1": 1,
}
_UNIT_INTERVAL_SUFFIXES = ("_f1", "_overlap", "_precision", "_ratio", "_recall", "_similarity")
_NONNEGATIVE_SUFFIXES = ("_count", "_norm", "_size")


def _row_reference(row_index: Any, position: int, row_ids: list[Any] | None) -> str:
    if row_ids is None:
        return f"row index {row_index!r}"
    return f"row {row_ids[position]!r} (index {row_index!r})"


def coerce_boolean_series(
    values: pd.Series,
    feature_name: str,
    *,
    row_ids: list[Any] | None = None,
) -> pd.Series:
    """Convert explicit boolean representations to integers and reject all others."""
    converted: list[int] = []
    for position, (row_index, value) in enumerate(values.items()):
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
            f"Invalid boolean value for feature {feature_name!r} at "
            f"{_row_reference(row_index, position, row_ids)}: {value!r}. "
            "Expected true, false, 1, or 0."
        )
    return pd.Series(converted, index=values.index, dtype="int64")


def coerce_numeric_series(
    values: pd.Series,
    feature_name: str,
    *,
    row_ids: list[Any] | None = None,
) -> pd.Series:
    """Convert finite numeric values and enforce known feature-domain constraints."""
    converted: list[float] = []
    for position, (row_index, value) in enumerate(values.items()):
        row_reference = _row_reference(row_index, position, row_ids)
        if isinstance(value, bool) or type(value).__name__ == "bool_":
            raise ValueError(
                f"Invalid numeric value for feature {feature_name!r} at {row_reference}: {value!r}. "
                "Boolean values are not accepted as numeric features."
            )
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid numeric value for feature {feature_name!r} at {row_reference}: {value!r}."
            ) from exc
        if not math.isfinite(numeric_value):
            raise ValueError(
                f"Invalid numeric value for feature {feature_name!r} at {row_reference}: {value!r}. "
                "Expected a finite number."
            )
        if feature_name.endswith(_UNIT_INTERVAL_SUFFIXES) or "_fraction_above_" in feature_name:
            if not 0.0 <= numeric_value <= 1.0:
                raise ValueError(
                    f"Numeric feature {feature_name!r} at {row_reference} must be between 0 and 1, "
                    f"got {numeric_value!r}."
                )
        elif feature_name.endswith(_NONNEGATIVE_SUFFIXES) and numeric_value < 0:
            raise ValueError(
                f"Numeric feature {feature_name!r} at {row_reference} must be non-negative, "
                f"got {numeric_value!r}."
            )
        converted.append(numeric_value)
    return pd.Series(converted, index=values.index, dtype="float64")

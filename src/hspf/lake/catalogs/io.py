"""Shared catalog IO and lightweight coercion helpers.

Catalog modules should keep their domain-specific builders and enums local, but
use this module for the repeated mechanics of converting records to frames,
ordering columns, reading/writing Parquet catalog tables, appending run-scoped
rows, and simple scalar cleanup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from hspf.core.errors import ConventionError
from hspf.lake.layout import LakeLayout




def records_to_frame(records: Iterable[Any], columns: Sequence[str]) -> pd.DataFrame:
    """Convert dataclass-like records or mappings to a catalog frame."""

    rows = []
    for record in records:
        if hasattr(record, "as_dict"):
            rows.append(record.as_dict())
        else:
            rows.append(dict(record))
    return pd.DataFrame(rows, columns=list(columns))


def to_catalog_frame(
    records: Iterable[Any] | pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Return ``records`` as a DataFrame with catalog columns first."""

    if isinstance(records, pd.DataFrame):
        return coerce_catalog_frame(records, columns)
    return records_to_frame(records, columns)


def empty_catalog_frame(columns: Sequence[str]) -> pd.DataFrame:
    """Return an empty catalog frame with the canonical columns."""

    return pd.DataFrame(columns=list(columns))


def coerce_catalog_frame(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    keep_extra_columns: bool = True,
) -> pd.DataFrame:
    """Return ``frame`` with canonical columns present and ordered first."""

    coerced = frame.copy()
    for column in columns:
        if column not in coerced.columns:
            coerced[column] = pd.NA
    if not keep_extra_columns:
        return coerced.loc[:, list(columns)]
    extra_columns = [column for column in coerced.columns if column not in columns]
    return coerced.loc[:, [*columns, *extra_columns]]


def read_catalog_table(
    layout: LakeLayout,
    catalog_name: str,
    columns: Sequence[str] | None = None,
    *,
    subdir: str | None = None,
    missing: str = "empty",
) -> pd.DataFrame:
    """Read a catalog Parquet table.

    Parameters
    ----------
    missing:
        ``"empty"`` returns an empty canonical frame when the table is missing.
        ``"raise"`` raises ``ConventionError`` instead.
    """

    path = layout.catalog_path(catalog_name, subdir=subdir)
    if not path.exists():
        if missing == "empty":
            return empty_catalog_frame(()) if columns is None else empty_catalog_frame(columns)
        if missing == "raise":
            raise ConventionError(f"Catalog table does not exist: {path}")
        raise ConventionError(f"Invalid missing policy: {missing!r}")

    frame = pd.read_parquet(path)
    return frame if columns is None else coerce_catalog_frame(frame, columns)


def write_catalog_table(
    layout: LakeLayout,
    catalog_name: str,
    records: Iterable[Any] | pd.DataFrame,
    columns: Sequence[str] | None = None,
    *,
    subdir: str | None = None,
    overwrite: bool = True,
    label: str | None = None,
) -> Path:
    """Write a catalog Parquet table and return its path."""

    path = layout.catalog_path(catalog_name, subdir=subdir)
    if path.exists() and not overwrite:
        name = label or catalog_name
        raise ConventionError(f"{name} catalog already exists: {path}")

    if columns is None:
        frame = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    else:
        frame = to_catalog_frame(records, columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def append_catalog_rows(
    layout: LakeLayout,
    catalog_name: str,
    records: Iterable[Any] | pd.DataFrame,
    columns: Sequence[str],
    *,
    subdir: str | None = None,
    key_column: str = "run_id",
    replace_existing: bool = False,
    label: str | None = None,
) -> Path:
    """Append rows, optionally replacing all existing rows with matching keys."""

    incoming = to_catalog_frame(records, columns)
    existing = read_catalog_table(layout, catalog_name, columns, subdir=subdir)
    if incoming.empty:
        return write_catalog_table(
            layout,
            catalog_name,
            existing,
            columns,
            subdir=subdir,
            overwrite=True,
            label=label,
        )

    if key_column not in incoming.columns:
        raise ConventionError(f"Incoming catalog rows are missing {key_column!r}")
    if key_column not in existing.columns:
        existing[key_column] = pd.NA

    incoming_keys = set(incoming[key_column].dropna())
    existing_keys = set(existing[key_column].dropna()) if not existing.empty else set()
    conflicts = incoming_keys.intersection(existing_keys)
    if conflicts and not replace_existing:
        name = label or catalog_name
        raise ConventionError(
            f"{name} catalog already has rows for {key_column}s: "
            f"{sorted(conflicts)!r}"
        )
    if conflicts:
        existing = existing.loc[~existing[key_column].isin(conflicts)].copy()

    frame = pd.concat([existing, incoming], ignore_index=True)
    return write_catalog_table(
        layout,
        catalog_name,
        frame,
        columns,
        subdir=subdir,
        overwrite=True,
        label=label,
    )


def append_one_record(
    layout: LakeLayout,
    catalog_name: str,
    record: Any,
    columns: Sequence[str],
    *,
    key_column: str,
    key_value: Any,
    subdir: str | None = None,
    replace_existing: bool = False,
    label: str | None = None,
) -> Path:
    """Append one record while checking a single key value."""

    existing = read_catalog_table(layout, catalog_name, columns, subdir=subdir)
    if not existing.empty and key_value in set(existing[key_column].dropna()):
        if not replace_existing:
            name = label or catalog_name
            raise ConventionError(f"{name} is already registered: {key_value}")
        existing = existing.loc[existing[key_column] != key_value].copy()

    frame = pd.concat(
        [existing, records_to_frame([record], columns)],
        ignore_index=True,
    )
    return write_catalog_table(
        layout,
        catalog_name,
        frame,
        columns,
        subdir=subdir,
        overwrite=True,
        label=label,
    )


def _is_missing(value: Any) -> bool:
    """Return True for None/pandas missing scalar values."""

    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _positive_int(value: Any, label: str) -> int:
    """Coerce a value to a positive integer."""

    integer = int(float(str(value).strip()))
    if integer <= 0:
        raise ConventionError(f"{label} must be positive: {value!r}")
    return integer


def _nonnegative_int(value: Any, label: str) -> int:
    """Coerce a value to a non-negative integer."""

    integer = int(float(str(value).strip()))
    if integer < 0:
        raise ConventionError(f"{label} cannot be negative: {value!r}")
    return integer


def _optional_int(value: Any) -> int | None:
    """Coerce a value to int, preserving empty/missing values as None."""

    if _is_missing(value):
        return None
    text = str(value).strip()
    return None if not text else int(float(text))


def _optional_float(value: Any) -> float | None:
    """Coerce a value to float, preserving empty/missing values as None."""

    if _is_missing(value):
        return None
    text = str(value).strip()
    return None if not text else float(text)


def _optional_text(value: Any) -> str | None:
    """Coerce a value to stripped text, preserving empties as None."""

    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, label: str) -> str:
    """Coerce a value to non-empty text."""

    text = _optional_text(value)
    if text is None:
        raise ConventionError(f"{label} cannot be empty")
    return text


def _enum_value(value: Any) -> Any:
    """Return enum ``.value`` when present, otherwise return the value itself."""

    return getattr(value, "value", value)

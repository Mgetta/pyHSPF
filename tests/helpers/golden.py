from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd


DEFAULT_FLOAT_FORMAT = "%.10g"


def slugify(value: object) -> str:
    """Make a value safe for use in a golden filename."""
    if isinstance(value, (list, tuple, set)):
        value = "-".join(str(item) for item in value)
    text = str(value).strip().replace(" ", "-")
    text = re.sub(r"[^A-Za-z0-9_.=-]+", "-", text)
    return text.strip("-").lower() or "na"


def golden_filename(function_name: str, extension: str, **context: object) -> str:
    """Name a golden by source function and the arguments that define it."""
    stem = slugify(function_name)
    for key, value in context.items():
        stem += f"__{slugify(key)}={slugify(value)}"
    extension = extension if extension.startswith(".") else f".{extension}"
    return f"{stem}{extension}"


def normalize_frame(
    df: pd.DataFrame,
    sort_by: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Make a DataFrame stable enough to save as a golden file."""
    result = df.copy()

    if not isinstance(result.index, pd.RangeIndex) or result.index.name is not None:
        result = result.reset_index(drop=False)
        if "index" in result.columns and "datetime" not in result.columns:
            result = result.rename(columns={"index": "datetime"})
    else:
        result = result.reset_index(drop=True)

    if sort_by is not None:
        sort_columns = [column for column in sort_by if column in result.columns]
        if sort_columns:
            result = result.sort_values(sort_columns, kind="mergesort")

    return result.reset_index(drop=True)


def write_golden(
    df: pd.DataFrame,
    path: Path,
    *,
    sort_by: Optional[Sequence[str]] = None,
    float_format: str = DEFAULT_FLOAT_FORMAT,
) -> Path:
    """Write a golden DataFrame as CSV or Parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_frame(df, sort_by=sort_by)

    if path.suffix.lower() == ".csv":
        normalized.to_csv(
            path,
            index=False,
            float_format=float_format,
            date_format="%Y-%m-%dT%H:%M:%S",
        )
    elif path.suffix.lower() == ".parquet":
        normalized.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported golden format: {path.suffix}")

    return path

"""Golden file IO helpers.

The list of expected goldens lives in ``tests.helpers.cases``. This module only
knows how to turn a case into a deterministic file path, write the output, load
it back, and compare a freshly computed result to the saved golden.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Sequence
from collections import Counter

import pandas as pd

from tests.configs import GoldenTestConfig,load_model, ALL_MODEL_CONFIGS
from tests.helpers.cases import Case, compute_case, golden_slug, cases



GOLDEN_GROUPS = ("raw", "recipes", "reports", "network")


def golden_filename(function_name: str, **context: object) -> str:
    """Return the Parquet filename for a golden derived from a function."""
    return f"{golden_slug(function_name, **context)}.parquet"

def _normalize_column_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Convert column labels to strings before Parquet write/read comparison."""
    columns = [str(column) for column in df.columns]
    duplicates = [column for column, count in Counter(columns).items() if count > 1]
    if duplicates:
        raise ValueError(
            "Column labels are not unique after converting to strings: "
            f"{duplicates}"
        )

    result = df.copy()
    result.columns = columns
    return result



def normalize_frame(
    df: pd.DataFrame,
    sort_by: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Make a DataFrame stable enough to save or compare as a golden file."""
    result = df.copy()

    if not isinstance(result.index, pd.RangeIndex) or result.index.name is not None:
        result = result.reset_index(drop=False)
        if "index" in result.columns and "datetime" not in result.columns:
            result = result.rename(columns={"index": "datetime"})
    else:
        result = result.reset_index(drop=True)

    result = _normalize_column_labels(result)


    if sort_by is not None:
        sort_columns = [str(column) for column in sort_by if str(column) in result.columns]
        if sort_columns:
            result = result.sort_values(sort_columns, kind="mergesort")

    return result.reset_index(drop=True)


def create_golden_folders(model_dir: Path) -> Path:
    """Create the goldens subfolders for one model."""
    goldens_dir = Path(model_dir) / "goldens"
    for name in GOLDEN_GROUPS:
        (goldens_dir / name).mkdir(parents=True, exist_ok=True)
    return goldens_dir


def golden_path(model_dir: Path, case: Case) -> Path:
    """Return the path where one case's golden output belongs."""
    return Path(model_dir) / "goldens" / case.group / case.filename


def write_golden(
    df: pd.DataFrame,
    path: Path,
    *,
    sort_by: Optional[Sequence[str]] = None,
) -> Path:
    """Write a golden DataFrame as Parquet."""
    path = Path(path)
    if path.suffix.lower() != ".parquet":
        raise ValueError(f"Golden files must be Parquet: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_frame(df, sort_by=sort_by)
    normalized.to_parquet(path, index=False)
    return path


def write_case_golden(model, config: GoldenTestConfig, case: Case) -> Path:
    """Compute and write one golden case."""
    df = compute_case(model, case)
    return write_golden(df, config.golden_path(case), sort_by=case.sort_by)

def load_golden(
    config: GoldenTestConfig,
    case: Case,
) -> pd.DataFrame:
    """Load one golden DataFrame.

    Prefer passing a ``Case``. The older ``group, name, **context`` calling style
    is kept so existing ad-hoc scripts do not have to change immediately.
    """
    path = config.golden_path(case)

    if not path.exists():
        raise FileNotFoundError(f"Golden file not found: {path}")
    return pd.read_parquet(path)


def generate_goldens(config: GoldenTestConfig) -> None:
    """Generate all golden files for one model."""
    for config in ALL_MODEL_CONFIGS:
        model = load_model(config.uci_file_path)
        for case in cases(config):
            write_case_golden(model, config, case)

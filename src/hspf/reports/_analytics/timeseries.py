# -*- coding: utf-8 -*-
"""
Model-agnostic timeseries filtering and aggregation.

Pure computation functions operating on wide-format pandas DataFrames
with DatetimeIndex. Columns represent spatial units (reaches, catchments,
etc.). No HSPF imports, no uci/hbn references.
"""
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Filters — row selection, return same type with fewer rows
# ---------------------------------------------------------------------------

def filter_years(ts, start_year=None, end_year=None):
    """Filter a timeseries to a closed year range.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        First year to include (inclusive). If None, no lower bound.
    end_year : int, optional
        Last year to include (inclusive). If None, no upper bound.

    Returns
    -------
    pd.DataFrame or pd.Series
        Filtered timeseries.
    """
    mask = pd.Series(True, index=ts.index)
    if start_year is not None:
        mask = mask & (ts.index.year >= start_year)
    if end_year is not None:
        mask = mask & (ts.index.year <= end_year)
    return ts.loc[mask]


def filter_months(ts, months):
    """Filter a timeseries to specific calendar months.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    months : list of int
        Calendar months to keep (1=January, ..., 12=December).

    Returns
    -------
    pd.DataFrame or pd.Series
        Filtered timeseries.
    """
    return ts.loc[ts.index.month.isin(months)]


# ---------------------------------------------------------------------------
# Aggregation — group by temporal attribute(s) and apply function
# ---------------------------------------------------------------------------

# Season mapping: month number → season name
_DEFAULT_SEASON_MAP = {
    12: 'DJF', 1: 'DJF', 2: 'DJF',
    3: 'MAM', 4: 'MAM', 5: 'MAM',
    6: 'JJA', 7: 'JJA', 8: 'JJA',
    9: 'SON', 10: 'SON', 11: 'SON',
}


def _resolve_grouper(key, index, season_map=None):
    """Map a grouping key name to an array-like grouper."""
    if key == 'year':
        return index.year
    elif key == 'month':
        return index.month
    elif key == 'season':
        smap = season_map or _DEFAULT_SEASON_MAP
        return index.month.map(smap)
    else:
        raise ValueError(
            f"Unknown grouping key: '{key}'. Expected 'year', 'month', or 'season'."
        )


def aggregate(ts, by=None, agg_func='mean', season_map=None):
    """Group a timeseries by temporal attribute(s) and apply an aggregation function.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    by : str, list of str, or None
        Temporal grouping key(s). Options: 'year', 'month', 'season'.
        Can combine as a list: ['year', 'season'] for per-year seasonal values.
        None collapses all time into a single value per column.
    agg_func : str or callable
        Aggregation function: 'mean', 'sum', 'max', 'min', 'std', 'median', etc.
    season_map : dict, optional
        Custom mapping of month number (1-12) to season name.
        Defaults to DJF/MAM/JJA/SON.

    Returns
    -------
    pd.DataFrame or pd.Series
        Aggregated values. If by is not None, index is the grouping key(s).
        If by is None, returns a Series (one value per column) for DataFrame input,
        or a scalar for Series input.
    """
    if by is None:
        return ts.agg(agg_func)

    if isinstance(by, str):
        by = [by]

    groupers = [_resolve_grouper(key, ts.index, season_map) for key in by]

    if len(groupers) == 1:
        return ts.groupby(groupers[0]).agg(agg_func)
    else:
        return ts.groupby(groupers).agg(agg_func)

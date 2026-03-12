# -*- coding: utf-8 -*-
"""
Model-agnostic constituent yield analytics.

Pure computation functions that accept generic pandas objects (DataFrame /
Series with DatetimeIndex) and scalar or Series drainage areas.  No HSPF
imports, no ``uci`` / ``hbn`` references — fully reusable by any watershed
model (SWMM, SWAT, HEC-HMS, etc.).
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _filter_years(ts, start_year=None, end_year=None):
    """Filter a timeseries to a closed year range.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        First year to include (inclusive).  If None, no lower bound is applied.
    end_year : int, optional
        Last year to include (inclusive).  If None, no upper bound is applied.

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


# ---------------------------------------------------------------------------
# Core analytics
# ---------------------------------------------------------------------------

def compute_yield(load_ts, drainage_area):
    """Compute constituent yield from a load timeseries and drainage area.

    Parameters
    ----------
    load_ts : pd.DataFrame or pd.Series
        Timeseries of constituent load.  If DataFrame, columns are reach / unit
        IDs and the index is a DatetimeIndex.  Units are whatever the caller
        provides (lb, acre-ft, kg, etc.).
    drainage_area : float or pd.Series
        Drainage area.  If float, applied uniformly to all columns.  If
        pd.Series, should be indexed by the same IDs as ``load_ts`` columns.
        Units should be consistent with ``load_ts`` (acres, km², etc.).

    Returns
    -------
    pd.DataFrame or pd.Series
        Yield timeseries (load per unit area per timestep).
    """
    return load_ts / drainage_area


def compute_net_load(load_ts, upstream_load_ts=None):
    """Compute net load by subtracting upstream contributions.

    Parameters
    ----------
    load_ts : pd.DataFrame or pd.Series
        Load timeseries at the target location(s).
    upstream_load_ts : pd.DataFrame or pd.Series, optional
        Load timeseries at the upstream boundary.  If None, returns
        ``load_ts`` unchanged.

    Returns
    -------
    pd.DataFrame or pd.Series
        Net load timeseries.
    """
    if upstream_load_ts is None:
        return load_ts
    return load_ts - upstream_load_ts


def average_annual(ts, start_year=None, end_year=None):
    """Compute the average annual value of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        Start year for filtering (inclusive).  If None, uses full range.
    end_year : int, optional
        End year for filtering (inclusive).  If None, uses full range.

    Returns
    -------
    pd.Series or scalar
        Mean value over the filtered period.
    """
    filtered = _filter_years(ts, start_year, end_year)
    return filtered.mean()


def average_monthly(ts, start_year=None, end_year=None):
    """Compute average monthly values (12 months) of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        Start year for filtering (inclusive).
    end_year : int, optional
        End year for filtering (inclusive).

    Returns
    -------
    pd.DataFrame or pd.Series
        Mean values grouped by calendar month (1–12).
    """
    filtered = _filter_years(ts, start_year, end_year)
    return filtered.groupby(filtered.index.month).mean()


def annual_totals(ts, start_year=None, end_year=None):
    """Compute annual totals of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        First year to include (inclusive).
    end_year : int, optional
        Last year to include (inclusive).

    Returns
    -------
    pd.DataFrame or pd.Series
        Annual sums, indexed by year.
    """
    filtered = _filter_years(ts, start_year, end_year)
    return filtered.groupby(filtered.index.year).sum()


def monthly_totals(ts, start_year=None, end_year=None):
    """Compute monthly totals of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        First year to include (inclusive).
    end_year : int, optional
        Last year to include (inclusive).

    Returns
    -------
    pd.DataFrame or pd.Series
        Monthly sums.
    """
    filtered = _filter_years(ts, start_year, end_year)
    return filtered.groupby(
        [filtered.index.year, filtered.index.month]
    ).sum()


def yield_summary(load_ts, drainage_area, start_year=None, end_year=None):
    """Comprehensive yield summary: annual average, monthly averages, and full timeseries.

    Parameters
    ----------
    load_ts : pd.DataFrame or pd.Series
        Load timeseries.
    drainage_area : float or pd.Series
        Drainage area (same units as ``load_ts``).
    start_year : int, optional
        Start year for filtering (inclusive).
    end_year : int, optional
        End year for filtering (inclusive).

    Returns
    -------
    dict
        Dictionary with keys:

        ``'timeseries'``
            Full yield timeseries (``pd.DataFrame`` or ``pd.Series``).
        ``'annual_average'``
            Mean annual yield (``pd.Series`` or scalar).
        ``'monthly_average'``
            Mean monthly yield grouped by calendar month (``pd.DataFrame`` or
            ``pd.Series``).
    """
    yld = compute_yield(load_ts, drainage_area)
    return {
        'timeseries': yld,
        'annual_average': average_annual(yld, start_year, end_year),
        'monthly_average': average_monthly(yld, start_year, end_year),
    }

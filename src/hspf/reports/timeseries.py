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
    if months is None:
        months = range(1, 13)
    return ts.loc[ts.index.month.isin(months)]


def average_annual(ts, start_year=None, end_year=None, months=None):
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
    filtered = filter_months(filter_years(ts, start_year, end_year), months)
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
    filtered = filter_years(ts, start_year, end_year)
    return filtered.groupby(filtered.index.month).mean()


def average_seasonal(ts, start_year=None, end_year=None, season_map=None):
    """Compute average seasonal values of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        Start year for filtering (inclusive).
    end_year : int, optional
        End year for filtering (inclusive).
    season_map : dict, optional
        Custom mapping of month number (1-12) to season name.
        Defaults to DJF/MAM/JJA/SON.

    Returns
    -------
    pd.DataFrame or pd.Series
        Mean values grouped by season.
    """
    filtered = filter_years(ts, start_year, end_year)
    smap = season_map or _DEFAULT_SEASON_MAP
    seasons = filtered.index.month.map(smap)
    return filtered.groupby(seasons).mean()

def seasonal_totals(ts, start_year=None, end_year=None, season_map=None):
    """Compute seasonal totals of a timeseries.

    Parameters
    ----------
    ts : pd.DataFrame or pd.Series
        Timeseries with DatetimeIndex.
    start_year : int, optional
        Start year for filtering (inclusive).
    end_year : int, optional
        End year for filtering (inclusive).
    season_map : dict, optional
        Custom mapping of month number (1-12) to season name.
        Defaults to DJF/MAM/JJA/SON.

    Returns
    -------
    pd.DataFrame or pd.Series
        Seasonal sums.
    """
    filtered = filter_years(ts, start_year, end_year)
    smap = season_map or _DEFAULT_SEASON_MAP
    seasons = filtered.index.month.map(smap)
    return filtered.groupby(seasons).sum()

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
    filtered = filter_years(ts, start_year, end_year)
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
    filtered = filter_years(ts, start_year, end_year)
    return filtered.groupby(
        [filtered.index.year, filtered.index.month]
    ).sum()

def independent_peaks(ts, n=10, drainage_area_sqmi=None,
                      min_separation_days=None, trough_ratio=0.75,
                      method='uswrc'):
    """Return the largest independent peaks from a daily time series.

    Peak independence follows the USWRC criterion: accepted peaks must be
    separated by the required number of days and the intervening hydrograph
    must recede below *trough_ratio* times the lower peak.

    Parameters
    ----------
    ts : pd.Series
        Daily values with a unique DatetimeIndex.
    n : int, optional
        Maximum number of independent peaks to return.
    drainage_area_sqmi : float, optional
        Drainage area used to calculate ``ceil(5 + ln(area))`` days when no
        explicit separation is supplied.
    min_separation_days : int, optional
        Required number of days between independent peaks.
    trough_ratio : float, optional
        Required recession relative to the lower adjacent peak.
    method : str, optional
        ``'uswrc'`` or ``'cunnane'``. Cunnane uses a two-thirds trough ratio
        and requires an explicit separation representing three times the
        basin time to peak.

    Returns
    -------
    pd.DataFrame
        Rank, peak date and value, visible event boundaries, surrounding
        trough values, and days since the previous event.

    Notes
    -----
    The original USWRC separation interval is
    ``theta = ceil(5 + ln(A))`` days, where ``A`` is drainage area in square
    miles. Peaks ``Q1`` and ``Q2`` are independent only when both conditions
    hold: ``abs(date1 - date2) >= theta`` and
    ``min(Q between peaks) < trough_ratio * min(Q1, Q2)``. The default
    ``trough_ratio`` is ``0.75``. If either condition fails, the lower peak is
    treated as a secondary crest of the same flood event.
    """
    if not isinstance(ts, pd.Series):
        raise TypeError('ts must be a pandas Series')
    if not isinstance(ts.index, pd.DatetimeIndex):
        raise TypeError('ts must have a DatetimeIndex')
    if not ts.index.is_unique:
        raise ValueError('ts index must contain unique datetimes')
    if n < 1:
        raise ValueError('n must be at least 1')
    if not 0 < trough_ratio < 1:
        raise ValueError('trough_ratio must be between 0 and 1')
    method = method.lower()
    if method not in ['uswrc', 'cunnane']:
        raise ValueError("method must be 'uswrc' or 'cunnane'")
    if method == 'cunnane':
        trough_ratio = 2 / 3
        if min_separation_days is None:
            raise ValueError('cunnane requires min_separation_days=3*time_to_peak')
    if min_separation_days is None:
        if drainage_area_sqmi is None:
            min_separation_days = 5
        elif drainage_area_sqmi <= 0:
            raise ValueError('drainage_area_sqmi must be positive')
        else:
            min_separation_days = int(np.ceil(5 + np.log(drainage_area_sqmi)))
    if min_separation_days < 0:
        raise ValueError('min_separation_days cannot be negative')

    series = ts.sort_index().dropna().astype(float)
    columns = ['rank', 'datetime', 'value', 'event_start', 'event_end',
               'trough_before', 'trough_after', 'days_to_prev_event']
    if len(series) < 3:
        return pd.DataFrame(columns=columns)
    values = series.to_numpy()
    candidate_positions = np.flatnonzero(
        (values[1:-1] > values[:-2]) & (values[1:-1] >= values[2:])) + 1
    candidate_positions = candidate_positions[
        np.argsort(-values[candidate_positions], kind='stable')]
    accepted = []
    for position in candidate_positions:
        independent = True
        for other in accepted:
            left, right = sorted((position, other))
            gap = abs((series.index[position] - series.index[other]).days)
            between = values[left + 1:right]
            trough = between.min() if len(between) else np.inf
            lower_peak = min(values[position], values[other])
            if gap < min_separation_days or trough >= trough_ratio * lower_peak:
                independent = False
                break
        if independent:
            accepted.append(position)
            if len(accepted) == n:
                break

    chronological = sorted(accepted)
    previous_ends = {}
    boundaries = {}
    previous_end = None
    for position in chronological:
        threshold = trough_ratio * values[position]
        before = np.flatnonzero(values[:position] <= threshold)
        after = np.flatnonzero(values[position + 1:] <= threshold)
        start = int(before[-1]) if len(before) else 0
        end = position + 1 + int(after[0]) if len(after) else len(series) - 1
        days_to_previous = (series.index[start] - series.index[previous_end]).days if previous_end is not None else np.nan
        boundaries[position] = (start, end, days_to_previous)
        previous_ends[position] = previous_end
        previous_end = end

    rows = []
    for rank, position in enumerate(accepted, start=1):
        start, end, days_to_previous = boundaries[position]
        rows.append({
            'rank': rank,
            'datetime': series.index[position],
            'value': values[position],
            'event_start': series.index[start],
            'event_end': series.index[end],
            'trough_before': values[start],
            'trough_after': values[end],
            'days_to_prev_event': days_to_previous,
        })
    return pd.DataFrame(rows, columns=columns)


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
    """Map a grouping key name to an array-like grouper.

    Parameters
    ----------
    key : str
        Grouping key: ``'year'``, ``'month'``, or ``'season'``.
    index : pd.DatetimeIndex
        Index of the timeseries being grouped.
    season_map : dict, optional
        Custom month-to-season mapping.  Defaults to DJF/MAM/JJA/SON.

    Returns
    -------
    array-like
        Grouper array derived from *index*.

    Raises
    ------
    ValueError
        If *key* is not recognised.
    """
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

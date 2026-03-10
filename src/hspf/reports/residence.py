# -*- coding: utf-8 -*-
"""
Residence time analysis for HSPF reaches.

All functions accept pre-formatted pandas timeseries (Series or DataFrame)
indexed by a DatetimeIndex at hourly or daily timesteps.  No UCI or HBN
objects are required — callers are responsible for providing the data in the
expected format.

Key Concepts
------------
* **Nominal (instantaneous) residence time**:  τ(t) = V(t) / Q_out(t)
* **Turnover ratio**: cumulative throughput over a period divided by the
  mean storage volume for that period.
* **Exceedance probability**: fraction of time the residence time exceeds a
  given threshold.
* **Cumulative exposure (C·T)**: the product of constituent concentration
  and residence time, integrated over time.
* **Residence-time distribution (RTD)**: histogram / empirical PDF of the
  instantaneous residence time series.
"""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core residence-time timeseries
# ---------------------------------------------------------------------------

def residence_time(volume, outflow):
    """
    Compute the instantaneous residence time at each timestep.

    Parameters
    ----------
    volume : pd.Series
        Water volume stored in the reach at each timestep (e.g. acre-ft or m³).
        Must have a DatetimeIndex.
    outflow : pd.Series
        Volumetric outflow **per timestep interval** (same volume units as
        *volume*).  Must share the same DatetimeIndex as *volume*.

    Returns
    -------
    pd.Series
        Residence time in units of the timestep interval (e.g. hours if the
        index is hourly, days if daily).  Timesteps where outflow is zero or
        negative are set to ``NaN``.
    """
    _validate_timeseries(volume, "volume")
    _validate_timeseries(outflow, "outflow")
    _validate_aligned(volume, outflow)

    rt = volume / outflow.replace(0, np.nan)
    rt[outflow <= 0] = np.nan
    rt.name = "residence_time"
    return rt


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def residence_time_stats(volume, outflow, percentiles=None):
    """
    Descriptive statistics of the residence-time timeseries.

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries (DatetimeIndex).
    outflow : pd.Series
        Reach outflow-per-interval timeseries (DatetimeIndex).
    percentiles : list of float, optional
        Percentiles to include (0–100).  Defaults to
        ``[10, 25, 50, 75, 90]``.

    Returns
    -------
    pd.Series
        Named statistics: count, mean, std, min, max, and requested
        percentiles.
    """
    if percentiles is None:
        percentiles = [10, 25, 50, 75, 90]

    rt = residence_time(volume, outflow).dropna()

    stats = {
        "count": rt.count(),
        "mean": rt.mean(),
        "std": rt.std(),
        "min": rt.min(),
        "max": rt.max(),
    }
    for p in percentiles:
        stats[f"p{int(p)}"] = np.nanpercentile(rt.values, p)

    result = pd.Series(stats, name="residence_time_stats")
    return result


# ---------------------------------------------------------------------------
# Turnover ratio
# ---------------------------------------------------------------------------

def turnover_ratio(volume, outflow, freq="YE"):
    """
    Compute the turnover ratio for each period.

    The turnover ratio is the total volumetric throughput during a period
    divided by the mean storage volume for that period.  A value of 1 means
    the reach volume was completely replaced once during the period.

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries.
    outflow : pd.Series
        Reach outflow-per-interval timeseries.
    freq : str, default ``'YE'``
        Pandas offset alias for the aggregation period (e.g. ``'ME'`` for
        monthly, ``'YE'`` for annual).

    Returns
    -------
    pd.DataFrame
        Columns: ``mean_volume``, ``total_outflow``, ``turnover_ratio``.
    """
    _validate_timeseries(volume, "volume")
    _validate_timeseries(outflow, "outflow")
    _validate_aligned(volume, outflow)

    mean_vol = volume.resample(freq).mean()
    total_out = outflow.resample(freq).sum()

    df = pd.DataFrame({
        "mean_volume": mean_vol,
        "total_outflow": total_out,
    })
    df["turnover_ratio"] = df["total_outflow"] / df["mean_volume"].replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Exceedance probability
# ---------------------------------------------------------------------------

def exceedance_probability(volume, outflow):
    """
    Build a residence-time exceedance-probability table.

    Each row gives a residence-time value and the fraction of timesteps
    during which the residence time equalled or exceeded that value.

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries.
    outflow : pd.Series
        Reach outflow-per-interval timeseries.

    Returns
    -------
    pd.DataFrame
        Columns: ``residence_time``, ``exceedance_probability`` (0–1).
        Sorted by descending residence time.
    """
    rt = residence_time(volume, outflow).dropna().sort_values(ascending=False).reset_index(drop=True)
    n = len(rt)
    if n == 0:
        return pd.DataFrame(columns=["residence_time", "exceedance_probability"])

    prob = (np.arange(1, n + 1)) / (n + 1)  # Weibull plotting position
    return pd.DataFrame({
        "residence_time": rt.values,
        "exceedance_probability": prob,
    })


# ---------------------------------------------------------------------------
# Cumulative exposure (C·T)
# ---------------------------------------------------------------------------

def cumulative_exposure(volume, outflow, concentration):
    """
    Compute the cumulative exposure product (C × τ) at each timestep.

    This is useful for assessing the integrated effect of a constituent
    concentration over the time water resides in the reach (analogous to
    the C·T concept used in water-treatment design).

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries.
    outflow : pd.Series
        Reach outflow-per-interval timeseries.
    concentration : pd.Series
        Constituent concentration timeseries (same DatetimeIndex).

    Returns
    -------
    pd.DataFrame
        Columns: ``residence_time``, ``concentration``, ``ct``
        (concentration × residence time), and ``cumulative_ct``
        (running sum of *ct*).
    """
    _validate_timeseries(concentration, "concentration")
    rt = residence_time(volume, outflow)
    _validate_aligned(rt, concentration)

    ct = rt * concentration
    df = pd.DataFrame({
        "residence_time": rt,
        "concentration": concentration,
        "ct": ct,
        "cumulative_ct": ct.cumsum(),
    })
    return df


# ---------------------------------------------------------------------------
# Residence-time distribution (RTD)
# ---------------------------------------------------------------------------

def residence_time_distribution(volume, outflow, bins=50):
    """
    Estimate the empirical residence-time distribution (RTD).

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries.
    outflow : pd.Series
        Reach outflow-per-interval timeseries.
    bins : int, default 50
        Number of histogram bins.

    Returns
    -------
    pd.DataFrame
        Columns: ``bin_center`` (residence time), ``frequency`` (count),
        and ``density`` (normalised so the histogram integrates to 1).
    """
    rt = residence_time(volume, outflow).dropna()
    if len(rt) == 0:
        return pd.DataFrame(columns=["bin_center", "frequency", "density"])

    counts, edges = np.histogram(rt.values, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    widths = np.diff(edges)
    total = counts.sum()
    density = counts / (total * widths) if total > 0 else counts * 0.0

    return pd.DataFrame({
        "bin_center": centers,
        "frequency": counts,
        "density": density,
    })


# ---------------------------------------------------------------------------
# Seasonal / grouped residence-time summary
# ---------------------------------------------------------------------------

def seasonal_residence_time(volume, outflow, grouping="month"):
    """
    Summarise residence time by calendar grouping.

    Parameters
    ----------
    volume : pd.Series
        Reach volume timeseries.
    outflow : pd.Series
        Reach outflow-per-interval timeseries.
    grouping : str, default ``'month'``
        One of ``'month'``, ``'season'``, or ``'year'``.

    Returns
    -------
    pd.DataFrame
        Mean, median, std, and count of residence time per group.

    Raises
    ------
    ValueError
        If *grouping* is not one of the accepted values.
    """
    SEASON_MAP = {12: "DJF", 1: "DJF", 2: "DJF",
                  3: "MAM", 4: "MAM", 5: "MAM",
                  6: "JJA", 7: "JJA", 8: "JJA",
                  9: "SON", 10: "SON", 11: "SON"}

    rt = residence_time(volume, outflow)

    if grouping == "month":
        key = rt.index.month
    elif grouping == "season":
        key = rt.index.month.map(SEASON_MAP)
    elif grouping == "year":
        key = rt.index.year
    else:
        raise ValueError(
            f"grouping must be 'month', 'season', or 'year', got '{grouping}'"
        )

    grouped = rt.groupby(key)
    df = pd.DataFrame({
        "mean": grouped.mean(),
        "median": grouped.median(),
        "std": grouped.std(),
        "count": grouped.count(),
    })
    df.index.name = grouping
    return df


# ---------------------------------------------------------------------------
# Multi-reach convenience wrapper
# ---------------------------------------------------------------------------

def multi_reach_residence_time(volumes, outflows):
    """
    Compute residence-time statistics for multiple reaches at once.

    Parameters
    ----------
    volumes : pd.DataFrame
        Each column is a reach's volume timeseries (DatetimeIndex, columns
        are reach IDs).
    outflows : pd.DataFrame
        Each column is a reach's outflow-per-interval timeseries (same
        structure as *volumes*).

    Returns
    -------
    pd.DataFrame
        One row per reach with summary statistics (mean, median, std, min,
        max).
    """
    _validate_timeseries(volumes, "volumes")
    _validate_timeseries(outflows, "outflows")

    rows = []
    for reach_id in volumes.columns:
        if reach_id not in outflows.columns:
            continue
        rt = residence_time(volumes[reach_id], outflows[reach_id]).dropna()
        rows.append({
            "reach_id": reach_id,
            "mean": rt.mean(),
            "median": rt.median(),
            "std": rt.std(),
            "min": rt.min(),
            "max": rt.max(),
            "count": rt.count(),
        })

    return pd.DataFrame(rows).set_index("reach_id")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_timeseries(ts, name):
    """Raise if *ts* is not a pandas object with a DatetimeIndex."""
    if not isinstance(ts, (pd.Series, pd.DataFrame)):
        raise TypeError(f"'{name}' must be a pandas Series or DataFrame.")
    if not isinstance(ts.index, pd.DatetimeIndex):
        raise TypeError(f"'{name}' must have a DatetimeIndex.")


def _validate_aligned(a, b):
    """Raise if two timeseries do not share the same index."""
    if not a.index.equals(b.index):
        raise ValueError(
            "Input timeseries must share the same DatetimeIndex."
        )

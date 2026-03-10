# -*- coding: utf-8 -*-
"""
Residence time and travel time analysis for HSPF reaches.

This module contains two groups of functions:

**Static geometry-based travel time** — uses UCI tables and Manning's
equation to estimate steady-state travel times from channel geometry.

**Timeseries-based residence time analysis** — accepts pre-formatted
pandas timeseries (DatetimeIndex at hourly or daily timesteps) of reach
volume and outflow.  No UCI or HBN objects are required for these
functions; callers are responsible for providing data in the expected
format.

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

from hspf.parser import graph

# Calendar-month to meteorological-season mapping (used by seasonal_residence_time)
_SEASON_MAP = {12: "DJF", 1: "DJF", 2: "DJF",
               3: "MAM", 4: "MAM", 5: "MAM",
               6: "JJA", 7: "JJA", 8: "JJA",
               9: "SON", 10: "SON", 11: "SON"}

# Calculate the 2 year return period flow for each reach and use that to estimate the effective flow width and depth for travel time calculations. This is a common approach for estimating residence time under typical flow conditions, but it does not account for temporal variability in flow or the effects of backwater and storage areas. For more accurate residence time estimates, a dynamic hydrodynamic model would be needed.


def get_reach_hydraulics(uci,hbn):
    dfs = []
    parm2 = uci.table('RCHRES', 'HYDR-PARM2')
    for table_name in uci.table_names('FTABLES'):
        reach_id = int(table_name.replace('FTABLE', ''))
        if reach_id in parm2.index:
            
            flow = hbn.get_reach_constituent('Q',[reach_id],5).median()

            geometry = uci.table('FTABLES',f'FTABLE{reach_id}')
            bf_geometry = geometry.iloc[abs(geometry['Disch1'].dropna()-flow.values).argmin()]
            
            w = bf_geometry['Area'] / bf_geometry['Depth']
            d = bf_geometry['Depth']
            len_ft = parm2['LEN'].loc[reach_id] * 5280.0
            delth = parm2['DELTH'].loc[reach_id]
            ks = parm2['KS'].loc[reach_id]
            slope = np.maximum(delth / len_ft if len_ft > 0 else np.nan, 0.00001)
            hydr_radius = (w * d) / (w + 2 * d) if (w + 2 * d) != 0 else np.nan

            df = pd.DataFrame([{
                'OPNID': reach_id,
                'LEN': parm2['LEN'].loc[reach_id],
                'DEPTH': d,
                'WIDTH': w,
                'WETTED_PERIMETER': w + 2 * d,
                'LEN_FT': len_ft,
                'SLOPE': slope,
                'HYDR_RADIUS': hydr_radius,
                'DELTH': delth,
                'KS': ks
            }], index=[reach_id])
            dfs.append(df.set_index('OPNID'))
    return pd.concat(dfs)
    
def _is_invalid(v):
    """Return True if v is None, NaN, or non-positive."""
    if v is None:
        return True
    try:
        return np.isnan(float(v)) or float(v) <= 0
    except (TypeError, ValueError):
        return True


def mannings_velocity(ks, hydraulic_radius, slope):
    """Compute velocity (ft/s) using Manning's equation: V = (1.49/n) * R^(2/3) * S^(1/2)."""
    if _is_invalid(ks) or _is_invalid(hydraulic_radius) or _is_invalid(slope):
        return np.nan
    return (1.49 / ks) * (hydraulic_radius ** (2.0 / 3.0)) * (slope ** 0.5)


def reach_travel_time(length_ft, velocity):
    """Compute travel time in hours for a single reach: length / velocity / 3600."""
    if _is_invalid(velocity) or _is_invalid(length_ft):
        return np.nan
    return length_ft / velocity / 3600.0


def path_travel_time(uci, hbn, outlet_reach_id, source_reach_id):
    """Compute total travel time (hours) from source_reach_id to outlet_reach_id along the routing path."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    if source_reach_id not in all_paths:
        return np.nan
    hydraulics = get_reach_hydraulics(uci,hbn)
    total = 0.0
    for reach_id in all_paths[source_reach_id]:
        if reach_id not in hydraulics.index:
            return np.nan
        row = hydraulics.loc[reach_id]
        v = mannings_velocity(row['KS'], row['HYDR_RADIUS'], row['SLOPE'])
        tt = reach_travel_time(row['LEN_FT'], v)
        if np.isnan(tt):
            return np.nan
        total += tt
    return total


def travel_times(uci, hbn, outlet_reach_id):
    """Compute travel time from every upstream reach to the outlet. Returns a pd.Series indexed by reach_id."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    hydraulics = get_reach_hydraulics(uci,hbn)
    result = {outlet_reach_id: 0.0}
    for source_reach_id, path in all_paths.items():
        total = 0.0
        for reach_id in path:
            if reach_id not in hydraulics.index:
                total = np.nan
                break
            row = hydraulics.loc[reach_id]
            v = mannings_velocity(row['KS'], row['HYDR_RADIUS'], row['SLOPE'])
            tt = reach_travel_time(row['LEN_FT'], v)
            if np.isnan(tt):
                total = np.nan
                break
            total += tt
        result[source_reach_id] = total
    return pd.Series(result, name='travel_time_hours')


def travel_time_summary(uci, hbn,outlet_reach_id):
    """Return a DataFrame with travel time and catchment area for each upstream reach."""
    G = uci.network.G
    tt = travel_times(uci, hbn, outlet_reach_id)
    records = []
    for reach_id, travel_time_hours in tt.items():
        area = graph.catchment_area(G, reach_id)
        records.append({'reach_id': reach_id, 'travel_time_hours': travel_time_hours, 'catchment_area_acres': area})
    return pd.DataFrame(records)


# ===================================================================
# Timeseries-based residence time analysis
# ===================================================================
#
# The functions below operate on pre-formatted pandas timeseries
# (Series or DataFrame indexed by a DatetimeIndex at hourly or daily
# timesteps).  No UCI or HBN objects are required.
# ===================================================================

# ---------------------------------------------------------------------------
# Core residence-time timeseries
# ---------------------------------------------------------------------------

def nominal_residence_time(volume, outflow):
    """
    Compute the instantaneous (nominal) residence time at each timestep.

    Parameters
    ----------
    volume : pd.Series
        Water volume stored in the reach at each timestep (e.g. acre-ft
        or m³).  Must have a DatetimeIndex.
    outflow : pd.Series
        Volumetric outflow **per timestep interval** (same volume units
        as *volume*).  Must share the same DatetimeIndex as *volume*.

    Returns
    -------
    pd.Series
        Residence time in units of the timestep interval (e.g. hours if
        the index is hourly, days if daily).  Timesteps where outflow is
        zero or negative are set to ``NaN``.
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

    rt = nominal_residence_time(volume, outflow).dropna()

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
    rt = nominal_residence_time(volume, outflow).dropna().sort_values(ascending=False).reset_index(drop=True)
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
    rt = nominal_residence_time(volume, outflow)
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
    rt = nominal_residence_time(volume, outflow).dropna()
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
    rt = nominal_residence_time(volume, outflow)

    if grouping == "month":
        key = rt.index.month
    elif grouping == "season":
        key = rt.index.month.map(_SEASON_MAP)
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
        rt = nominal_residence_time(volumes[reach_id], outflows[reach_id]).dropna()
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
# Internal helpers (timeseries validation)
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



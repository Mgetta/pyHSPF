# -*- coding: utf-8 -*-
"""Static geometry-based channel travel time (residence time) calculations."""
import numpy as np
import pandas as pd

from hspf.parser import graph

ACFT_TO_FT3 = 43560.0  # 1 acre-ft = 43,560 ft³

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


# =============================================================================
# Helper
# =============================================================================

def _infer_timestep_hours(series):
    """Infer the timestep size in hours from a pd.Series or pd.DataFrame index.

    Returns 1.0 for hourly data, 24.0 for daily data.  Falls back to the
    median difference between consecutive index timestamps if pd.infer_freq()
    cannot determine the frequency.

    Multipliers on frequency strings (e.g. '2H' for 2-hourly) are parsed and
    applied so that irregular sub-daily frequencies are handled correctly.
    """
    try:
        freq = pd.infer_freq(series.index)
        if freq is not None:
            # Parse optional leading integer multiplier (e.g. '2H' → mult=2, base='H')
            import re
            m = re.match(r'^(\d*)(.+)$', freq)
            mult = int(m.group(1)) if m and m.group(1) else 1
            base = m.group(2) if m else freq
            mapping = {
                'H': 1.0, 'h': 1.0,
                'T': 1.0 / 60.0, 'min': 1.0 / 60.0,
                'D': 24.0, 'B': 24.0,
                'W': 168.0, 'M': 24.0 * 30.0, 'A': 24.0 * 365.0,
            }
            for key, val in mapping.items():
                if base.startswith(key):
                    return mult * val
    except Exception:
        pass
    # Fallback: median difference
    diffs = series.index.to_series().diff().dropna()
    if len(diffs) == 0:
        return 1.0
    median_ns = diffs.median().total_seconds()
    return median_ns / 3600.0


# =============================================================================
# Section 1: Core Timeseries Residence Time Analysis
# =============================================================================

def nominal_residence_time(volume, outflow):
    """Compute nominal residence time τ = V/Q at each timestep.

    Parameters
    ----------
    volume : pd.Series
        Reach or reservoir volume in **acre-ft**.
    outflow : pd.Series
        Outflow (discharge) in **cfs** (ft³/s).

    Returns
    -------
    pd.Series
        Residence time in **hours**.  NaN where outflow ≤ 0.
    """
    volume, outflow = volume.align(outflow, join='inner')
    volume_ft3 = volume * ACFT_TO_FT3
    q = outflow.copy().astype(float)
    q[q <= 0] = np.nan
    tau_hours = (volume_ft3 / q) / 3600.0
    return tau_hours.rename('residence_time_hours')


def turnover_rate(volume, outflow):
    """Compute the volumetric turnover rate 1/τ (per hour).

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    pd.Series
        Turnover rate in 1/hour.  NaN where τ ≤ 0.
    """
    tau = nominal_residence_time(volume, outflow)
    rate = 1.0 / tau
    rate[tau <= 0] = np.nan
    return rate.rename('turnover_rate_per_hour')


def residence_time_stats(volume, outflow):
    """Return summary statistics of the nominal residence time series.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    dict
        Keys: mean, median, std, min, max, p10, p25, p75, p90 (all in hours).
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return {k: np.nan for k in ['mean', 'median', 'std', 'min', 'max',
                                     'p10', 'p25', 'p75', 'p90']}
    return {
        'mean': tau.mean(),
        'median': tau.median(),
        'std': tau.std(),
        'min': tau.min(),
        'max': tau.max(),
        'p10': tau.quantile(0.10),
        'p25': tau.quantile(0.25),
        'p75': tau.quantile(0.75),
        'p90': tau.quantile(0.90),
    }


def monthly_residence_time(volume, outflow):
    """Compute mean, median, and std of residence time grouped by calendar month.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    pd.DataFrame
        Index = month number (1–12), columns = ['mean', 'median', 'std'].
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return pd.DataFrame(columns=['mean', 'median', 'std'])
    grouped = tau.groupby(tau.index.month)
    return grouped.agg(['mean', 'median', 'std']).rename_axis('month')


def seasonal_residence_time(volume, outflow, seasons=None):
    """Compute mean, median, and std of residence time grouped by season.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    seasons : dict, optional
        Mapping of season name → list of month numbers.  Defaults to
        ``{'DJF': [12, 1, 2], 'MAM': [3, 4, 5], 'JJA': [6, 7, 8],
        'SON': [9, 10, 11]}``.

    Returns
    -------
    pd.DataFrame
        Index = season name, columns = ['mean', 'median', 'std'].
    """
    if seasons is None:
        seasons = {
            'DJF': [12, 1, 2],
            'MAM': [3, 4, 5],
            'JJA': [6, 7, 8],
            'SON': [9, 10, 11],
        }
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return pd.DataFrame(columns=['mean', 'median', 'std'])
    month_to_season = {}
    for name, months in seasons.items():
        for m in months:
            month_to_season[m] = name
    season_labels = tau.index.month.map(month_to_season)
    records = {}
    for season_name in seasons:
        subset = tau[season_labels == season_name]
        if subset.empty:
            records[season_name] = {'mean': np.nan, 'median': np.nan, 'std': np.nan}
        else:
            records[season_name] = {
                'mean': subset.mean(),
                'median': subset.median(),
                'std': subset.std(),
            }
    return pd.DataFrame(records).T.rename_axis('season')


def flow_weighted_residence_time(volume, outflow):
    """Compute the flow-weighted mean residence time Σ(τᵢ·Qᵢ) / Σ(Qᵢ).

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    float
        Flow-weighted residence time in hours.
    """
    tau = nominal_residence_time(volume, outflow)
    volume, outflow = volume.align(outflow, join='inner')
    q = outflow.reindex(tau.index)
    valid = tau.notna() & q.notna() & (q > 0)
    if not valid.any():
        return np.nan
    return float((tau[valid] * q[valid]).sum() / q[valid].sum())


def constituent_residence_time(mass_stored, mass_outflow):
    """Compute the constituent residence time τ_c = M_stored / M_outflow.

    Parameters
    ----------
    mass_stored : pd.Series
        Mass stored in the reach (lb, mg, or any consistent unit).
    mass_outflow : pd.Series
        Mass leaving per timestep (same units per timestep).

    Returns
    -------
    pd.Series
        Constituent residence time in the same time units as the index
        frequency.  NaN where mass_outflow ≤ 0.
    """
    mass_stored, mass_outflow = mass_stored.align(mass_outflow, join='inner')
    m_out = mass_outflow.copy().astype(float)
    m_out[m_out <= 0] = np.nan
    tau_c = mass_stored / m_out
    return tau_c.rename('constituent_residence_time')


def residence_time_exceedance(volume, outflow, thresholds_hours=None):
    """Compute the fraction of time the nominal residence time exceeds each threshold.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    thresholds_hours : list of float, optional
        Threshold values in hours.  Defaults to [6, 12, 24, 48, 72, 168].

    Returns
    -------
    dict
        Keys = threshold (hours), values = fraction of valid timesteps where
        τ > threshold.
    """
    if thresholds_hours is None:
        thresholds_hours = [6, 12, 24, 48, 72, 168]
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return {t: np.nan for t in thresholds_hours}
    n = len(tau)
    return {t: float((tau > t).sum()) / n for t in thresholds_hours}


def residence_time_duration_curve(volume, outflow):
    """Build a residence time duration curve suitable for plotting.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    pd.DataFrame
        Columns: ``['residence_time_hours', 'exceedance_probability']``.
        Sorted descending by residence time.
    """
    tau = nominal_residence_time(volume, outflow).dropna().sort_values(ascending=False)
    n = len(tau)
    if n == 0:
        return pd.DataFrame(columns=['residence_time_hours', 'exceedance_probability'])
    exceedance = np.arange(1, n + 1) / n
    return pd.DataFrame({
        'residence_time_hours': tau.values,
        'exceedance_probability': exceedance,
    })


def compare_residence_times(volume, outflow, mass_stored, mass_outflow):
    """Compare hydraulic and constituent residence times side-by-side.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    mass_stored : pd.Series
        Mass stored (any consistent unit).
    mass_outflow : pd.Series
        Mass leaving per timestep (same unit).

    Returns
    -------
    pd.DataFrame
        Columns: ``['hydraulic_rt', 'constituent_rt', 'rt_ratio']`` where
        ``rt_ratio = constituent_rt / hydraulic_rt``.
    """
    hrt = nominal_residence_time(volume, outflow)
    crt = constituent_residence_time(mass_stored, mass_outflow)
    df = pd.concat([hrt.rename('hydraulic_rt'), crt.rename('constituent_rt')], axis=1)
    df['rt_ratio'] = df['constituent_rt'] / df['hydraulic_rt']
    return df


# =============================================================================
# Section 2: Residence Time Distributions
# =============================================================================

def residence_time_distribution(volume, outflow, bins=50):
    """Compute a histogram (PDF + CDF) of the nominal residence time.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    bins : int or array-like
        Number of histogram bins or explicit bin edges.

    Returns
    -------
    pd.DataFrame
        Columns: ``['bin_center_hours', 'count', 'density',
        'cumulative_density']``.
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return pd.DataFrame(columns=['bin_center_hours', 'count', 'density',
                                      'cumulative_density'])
    counts, edges = np.histogram(tau, bins=bins)
    density, _ = np.histogram(tau, bins=edges, density=True)
    bin_centers = 0.5 * (edges[:-1] + edges[1:])
    cum_density = np.cumsum(density * np.diff(edges))
    return pd.DataFrame({
        'bin_center_hours': bin_centers,
        'count': counts,
        'density': density,
        'cumulative_density': cum_density,
    })


def log_residence_time_distribution(volume, outflow, bins=50):
    """Compute a histogram of log₁₀(τ), useful for wide residence time ranges.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    bins : int or array-like
        Number of bins or explicit bin edges in log₁₀ space.

    Returns
    -------
    pd.DataFrame
        Columns: ``['bin_center_log10h', 'count', 'density',
        'cumulative_density']``.  ``bin_center_log10h`` is log₁₀(τ in hours).
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    tau = tau[tau > 0]
    if tau.empty:
        return pd.DataFrame(columns=['bin_center_log10h', 'count', 'density',
                                      'cumulative_density'])
    log_tau = np.log10(tau.values)
    counts, edges = np.histogram(log_tau, bins=bins)
    density, _ = np.histogram(log_tau, bins=edges, density=True)
    bin_centers = 0.5 * (edges[:-1] + edges[1:])
    cum_density = np.cumsum(density * np.diff(edges))
    return pd.DataFrame({
        'bin_center_log10h': bin_centers,
        'count': counts,
        'density': density,
        'cumulative_density': cum_density,
    })


def fit_residence_time_distribution(volume, outflow, distribution='lognormal'):
    """Fit a parametric distribution to the nominal residence time series.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    distribution : {'lognormal', 'exponential', 'gamma'}
        Name of the parametric distribution to fit.

    Returns
    -------
    dict
        Keys: ``'distribution'``, ``'parameters'`` (dict of named params),
        ``'ks_statistic'``, ``'p_value'``.

    Raises
    ------
    ImportError
        If ``scipy`` is not installed.
    ValueError
        If *distribution* is not one of the supported names.
    """
    try:
        from scipy import stats as _stats
    except ImportError as exc:
        raise ImportError(
            "scipy is required for fit_residence_time_distribution. "
            "Install it with: pip install scipy"
        ) from exc

    supported = {'lognormal', 'exponential', 'gamma'}
    if distribution not in supported:
        raise ValueError(
            f"distribution must be one of {sorted(supported)}, got '{distribution}'"
        )

    tau = nominal_residence_time(volume, outflow).dropna()
    tau = tau[tau > 0].values

    if distribution == 'lognormal':
        dist_obj = _stats.lognorm
        shape, loc, scale = dist_obj.fit(tau, floc=0)
        params = {'shape': shape, 'loc': loc, 'scale': scale}
    elif distribution == 'exponential':
        dist_obj = _stats.expon
        loc, scale = dist_obj.fit(tau, floc=0)
        params = {'loc': loc, 'scale': scale}
    else:  # gamma
        dist_obj = _stats.gamma
        shape, loc, scale = dist_obj.fit(tau, floc=0)
        params = {'shape': shape, 'loc': loc, 'scale': scale}

    ks_stat, p_val = _stats.kstest(tau, dist_obj.cdf, args=tuple(params.values()))
    return {
        'distribution': distribution,
        'parameters': params,
        'ks_statistic': float(ks_stat),
        'p_value': float(p_val),
    }


def residence_time_percentiles(volume, outflow, percentiles=None):
    """Return residence time values at the specified percentiles.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    percentiles : list of float, optional
        Percentile values in [0, 100].  Defaults to
        [1, 5, 10, 25, 50, 75, 90, 95, 99].

    Returns
    -------
    pd.Series
        Indexed by percentile value, values = τ in hours.
    """
    if percentiles is None:
        percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        return pd.Series({p: np.nan for p in percentiles}, name='residence_time_hours')
    return pd.Series(
        {p: float(tau.quantile(p / 100.0)) for p in percentiles},
        name='residence_time_hours',
    )


# =============================================================================
# Section 3: Cumulative Exposure
# =============================================================================

def cumulative_exposure(concentration, volume, outflow):
    """Compute the cumulative constituent exposure experienced during one residence time.

    For each timestep *t*, the exposure is the sum of C_i × Δt over the
    backward window [t − τ(t), t], where τ(t) is the nominal residence time.

    Parameters
    ----------
    concentration : pd.Series
        Constituent concentration (mg/L, or any consistent unit).
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    pd.Series
        Cumulative exposure in concentration·hour units (e.g., mg·hr/L).
    """
    tau = nominal_residence_time(volume, outflow)
    dt = _infer_timestep_hours(concentration)

    # Align all series to the concentration index
    tau = tau.reindex(concentration.index)
    conc = concentration.values.astype(float)
    tau_vals = tau.values.astype(float)
    n = len(conc)

    exposure = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(tau_vals[i]) or tau_vals[i] <= 0:
            continue
        steps_back = max(1, int(round(tau_vals[i] / dt)))
        start = max(0, i - steps_back)
        window = conc[start: i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            exposure[i] = float(np.sum(valid) * dt)

    return pd.Series(exposure, index=concentration.index, name='cumulative_exposure')


def cumulative_exposure_stats(concentration, volume, outflow):
    """Return summary statistics of the cumulative exposure series.

    Parameters
    ----------
    concentration : pd.Series
        Concentration (mg/L or consistent unit).
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    dict
        Keys: mean, median, std, max, p90, p95.
    """
    exp = cumulative_exposure(concentration, volume, outflow).dropna()
    if exp.empty:
        return {k: np.nan for k in ['mean', 'median', 'std', 'max', 'p90', 'p95']}
    return {
        'mean': float(exp.mean()),
        'median': float(exp.median()),
        'std': float(exp.std()),
        'max': float(exp.max()),
        'p90': float(exp.quantile(0.90)),
        'p95': float(exp.quantile(0.95)),
    }


def peak_exposure_events(concentration, volume, outflow, threshold_percentile=90):
    """Identify contiguous periods where cumulative exposure exceeds a threshold.

    Parameters
    ----------
    concentration : pd.Series
        Concentration (mg/L or consistent unit).
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    threshold_percentile : float
        Percentile of the exposure series used as the exceedance threshold
        (default 90).

    Returns
    -------
    pd.DataFrame
        Columns: ``['start', 'end', 'duration_hours', 'peak_exposure',
        'mean_exposure']``.  Each row is one contiguous exceedance event.
    """
    exp = cumulative_exposure(concentration, volume, outflow)
    dt = _infer_timestep_hours(concentration)
    valid = exp.dropna()
    if valid.empty:
        return pd.DataFrame(columns=['start', 'end', 'duration_hours',
                                      'peak_exposure', 'mean_exposure'])
    threshold = valid.quantile(threshold_percentile / 100.0)
    above = (exp >= threshold).fillna(False)

    events = []
    in_event = False
    event_start = None
    for ts, flag in above.items():
        if flag and not in_event:
            in_event = True
            event_start = ts
        elif not flag and in_event:
            in_event = False
            segment = exp[event_start:ts].iloc[:-1]
            events.append({
                'start': event_start,
                'end': segment.index[-1] if not segment.empty else ts,
                'duration_hours': len(segment) * dt,
                'peak_exposure': float(segment.max()),
                'mean_exposure': float(segment.mean()),
            })
    # Close an event that reaches the end of the series
    if in_event:
        segment = exp[event_start:]
        events.append({
            'start': event_start,
            'end': segment.index[-1],
            'duration_hours': len(segment) * dt,
            'peak_exposure': float(segment.max()),
            'mean_exposure': float(segment.mean()),
        })
    return pd.DataFrame(events)


def exposure_duration_curve(concentration, volume, outflow):
    """Build a duration curve of the cumulative exposure for plotting.

    Parameters
    ----------
    concentration : pd.Series
        Concentration (mg/L or consistent unit).
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.

    Returns
    -------
    pd.DataFrame
        Columns: ``['exposure', 'exceedance_probability']``.  Sorted
        descending by exposure.
    """
    exp = cumulative_exposure(concentration, volume, outflow).dropna()
    exp = exp.sort_values(ascending=False)
    n = len(exp)
    if n == 0:
        return pd.DataFrame(columns=['exposure', 'exceedance_probability'])
    exceedance = np.arange(1, n + 1) / n
    return pd.DataFrame({
        'exposure': exp.values,
        'exceedance_probability': exceedance,
    })


# =============================================================================
# Section 4: Network Travel Time (Timeseries-Based, Wishful Thinking)
# =============================================================================

def dynamic_reach_residence_time(reach_volumes, reach_outflows):
    """Compute per-reach, per-timestep residence time for every reach.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.

    Returns
    -------
    pd.DataFrame
        Same shape as inputs; values = τ in hours per reach per timestep.
    """
    reach_volumes, reach_outflows = reach_volumes.align(reach_outflows,
                                                        join='inner', axis=None)
    q = reach_outflows.copy().astype(float)
    q[q <= 0] = np.nan
    tau_df = (reach_volumes * ACFT_TO_FT3) / q / 3600.0
    return tau_df


def dynamic_path_travel_time(reach_volumes, reach_outflows, path):
    """Compute total travel time along a path at each timestep.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.
    path : list
        Ordered list of reach_ids from upstream to downstream.

    Returns
    -------
    pd.Series
        Total travel time in hours at each timestep.
    """
    tau_df = dynamic_reach_residence_time(reach_volumes, reach_outflows)
    path_cols = [r for r in path if r in tau_df.columns]
    if not path_cols:
        return pd.Series(np.nan, index=tau_df.index, name='travel_time_hours')
    return tau_df[path_cols].sum(axis=1, min_count=1).rename('travel_time_hours')


def dynamic_travel_times(reach_volumes, reach_outflows, routing_paths):
    """Compute travel times from every source reach to the target for all paths.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.
    routing_paths : dict
        Mapping of ``{source_reach_id: [reach_id, ...]}`` — same format as
        ``graph.paths()`` returns.

    Returns
    -------
    pd.DataFrame
        Columns = source_reach_ids, values = total travel time (hours).
    """
    tau_df = dynamic_reach_residence_time(reach_volumes, reach_outflows)
    result = {}
    for source_id, path in routing_paths.items():
        path_cols = [r for r in path if r in tau_df.columns]
        if path_cols:
            result[source_id] = tau_df[path_cols].sum(axis=1, min_count=1)
        else:
            result[source_id] = pd.Series(np.nan, index=tau_df.index)
    return pd.DataFrame(result)


def dynamic_travel_time_summary(reach_volumes, reach_outflows, routing_paths,
                                catchment_areas=None):
    """Summary statistics for each source reach's travel time to the target.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.
    routing_paths : dict
        ``{source_reach_id: [reach_id, ...]}``
    catchment_areas : pd.Series, optional
        Catchment area in acres indexed by reach_id.

    Returns
    -------
    pd.DataFrame
        Indexed by source_reach_id with columns
        ``['mean_travel_time_hours', 'median_travel_time_hours',
        'std_travel_time_hours', 'min_travel_time_hours',
        'max_travel_time_hours', 'catchment_area_acres']``.
    """
    tt_df = dynamic_travel_times(reach_volumes, reach_outflows, routing_paths)
    records = {}
    for source_id in tt_df.columns:
        series = tt_df[source_id].dropna()
        records[source_id] = {
            'mean_travel_time_hours': series.mean() if not series.empty else np.nan,
            'median_travel_time_hours': series.median() if not series.empty else np.nan,
            'std_travel_time_hours': series.std() if not series.empty else np.nan,
            'min_travel_time_hours': series.min() if not series.empty else np.nan,
            'max_travel_time_hours': series.max() if not series.empty else np.nan,
            'catchment_area_acres': (
                catchment_areas[source_id]
                if catchment_areas is not None and source_id in catchment_areas.index
                else np.nan
            ),
        }
    return pd.DataFrame(records).T.rename_axis('source_reach_id')


def dynamic_travel_time_exceedance(reach_volumes, reach_outflows, routing_paths,
                                   thresholds_hours=None):
    """Compute the fraction of time travel time exceeds each threshold.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.
    routing_paths : dict
        ``{source_reach_id: [reach_id, ...]}``
    thresholds_hours : list of float, optional
        Threshold values in hours.  Defaults to [6, 12, 24, 48, 72, 168].

    Returns
    -------
    pd.DataFrame
        Rows = source_reach_ids, columns = threshold values.
    """
    if thresholds_hours is None:
        thresholds_hours = [6, 12, 24, 48, 72, 168]
    tt_df = dynamic_travel_times(reach_volumes, reach_outflows, routing_paths)
    records = {}
    for source_id in tt_df.columns:
        series = tt_df[source_id].dropna()
        if series.empty:
            records[source_id] = {t: np.nan for t in thresholds_hours}
        else:
            n = len(series)
            records[source_id] = {
                t: float((series > t).sum()) / n for t in thresholds_hours
            }
    return pd.DataFrame(records).T.rename_axis('source_reach_id')

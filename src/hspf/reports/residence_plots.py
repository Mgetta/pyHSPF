# -*- coding: utf-8 -*-
"""
Visualization module for residence time and transit time distributions.

All plotting functions build on the analytical functions in
:mod:`hspf.reports.residence`.  They accept the same ``volume`` /
``outflow`` / ``concentration`` Series that the analytical layer uses and
return ``matplotlib.figure.Figure`` objects so callers can further
customise or save them.

Ten standard visualisation methods are provided:

1.  PDF – probability density of the residence time distribution
2.  CDF – cumulative distribution
3.  Survival (complementary CDF)
4.  Log-scale axes (semi-log PDF + log-log survival)
5.  Time-varying heatmap (age × calendar time)
6.  Quantile time-series with discharge context
7.  Young water fraction (Fyw)
8.  Box / violin plots by season
9.  Stacked age-composition bars
10. Spaghetti + envelope / fan chart
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from hspf.reports.residence import (
    nominal_residence_time,
    residence_time_distribution,
    log_residence_time_distribution,
    residence_time_duration_curve,
    residence_time_stats,
    residence_time_percentiles,
    fit_residence_time_distribution,
    monthly_residence_time,
    seasonal_residence_time,
    flow_weighted_residence_time,
    residence_time_exceedance,
    turnover_rate,
    dynamic_reach_residence_time,
    dynamic_travel_times,
)


# =========================================================================
# Helpers
# =========================================================================

def _get_fitted_curves(volume, outflow, time_axis):
    """Fit lognormal, exponential, and gamma distributions and return
    (label, pdf_values, cdf_values, sf_values) tuples."""
    from scipy import stats as _stats

    fits = []
    for dist_name in ('lognormal', 'exponential', 'gamma'):
        try:
            result = fit_residence_time_distribution(volume, outflow,
                                                     distribution=dist_name)
        except Exception:
            continue
        params = result['parameters']
        if dist_name == 'lognormal':
            rv = _stats.lognorm(s=params['shape'], loc=params['loc'],
                                scale=params['scale'])
        elif dist_name == 'exponential':
            rv = _stats.expon(loc=params['loc'], scale=params['scale'])
        else:
            rv = _stats.gamma(a=params['shape'], loc=params['loc'],
                              scale=params['scale'])
        label = (f"{dist_name.title()} "
                 f"(KS={result['ks_statistic']:.3f}, "
                 f"p={result['p_value']:.3f})")
        fits.append((label, rv.pdf(time_axis), rv.cdf(time_axis),
                      rv.sf(time_axis)))
    return fits


def _season_labels(index, seasons=None):
    """Map a DatetimeIndex to season names."""
    if seasons is None:
        seasons = {'DJF': [12, 1, 2], 'MAM': [3, 4, 5],
                   'JJA': [6, 7, 8], 'SON': [9, 10, 11]}
    m2s = {}
    for name, months in seasons.items():
        for m in months:
            m2s[m] = name
    return index.month.map(m2s)


# =========================================================================
# 1. PDF Plot
# =========================================================================

def plot_pdf(volume, outflow, bins=50, fit=True, ax=None, **kwargs):
    """Plot the probability density function of residence time.

    Parameters
    ----------
    volume : pd.Series
        Reach volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    bins : int
        Number of histogram bins (passed to
        :func:`~hspf.reports.residence.residence_time_distribution`).
    fit : bool
        If True, overlay fitted parametric distributions.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.  A new figure is created when *None*.

    Returns
    -------
    matplotlib.figure.Figure
    """
    rtd = residence_time_distribution(volume, outflow, bins=bins)
    if rtd.empty:
        raise ValueError("No valid residence time data to plot.")

    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))
    else:
        fig = ax.figure

    ax.bar(rtd['bin_center_hours'], rtd['density'], width=np.diff(
        np.concatenate([[0], rtd['bin_center_hours'].values])
    ).mean(), alpha=0.5, color='steelblue', label='Empirical', edgecolor='white')

    if fit:
        t = np.linspace(rtd['bin_center_hours'].min(),
                        rtd['bin_center_hours'].max(), 500)
        for label, pdf_vals, _, _ in _get_fitted_curves(volume, outflow, t):
            ax.plot(t, pdf_vals, linewidth=2, label=label)

    ax.set_xlabel("Residence Time (hours)", fontsize=12)
    ax.set_ylabel("Probability Density", fontsize=12)
    ax.set_title("Residence Time Distribution — PDF", fontsize=14)
    ax.legend(fontsize=9)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    return fig


# =========================================================================
# 2. CDF Plot
# =========================================================================

def plot_cdf(volume, outflow, bins=50, fit=True, ax=None, **kwargs):
    """Plot the cumulative distribution function of residence time.

    Parameters
    ----------
    volume, outflow, bins, fit, ax
        See :func:`plot_pdf`.

    Returns
    -------
    matplotlib.figure.Figure
    """
    rtd = residence_time_distribution(volume, outflow, bins=bins)
    if rtd.empty:
        raise ValueError("No valid residence time data to plot.")

    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))
    else:
        fig = ax.figure

    ax.step(rtd['bin_center_hours'], rtd['cumulative_density'],
            where='mid', linewidth=2, color='steelblue', label='Empirical CDF')

    if fit:
        t = np.linspace(rtd['bin_center_hours'].min(),
                        rtd['bin_center_hours'].max(), 500)
        for label, _, cdf_vals, _ in _get_fitted_curves(volume, outflow, t):
            ax.plot(t, cdf_vals, linewidth=2, label=label)

    ax.axhline(0.5, color='gray', linestyle='--', linewidth=0.8,
               label='Median (P=0.5)')
    ax.set_xlabel("Residence Time (hours)", fontsize=12)
    ax.set_ylabel("Cumulative Probability", fontsize=12)
    ax.set_title("Residence Time Distribution — CDF", fontsize=14)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


# =========================================================================
# 3. Survival Function (Complementary CDF)
# =========================================================================

def plot_survival(volume, outflow, bins=50, fit=True, ax=None, **kwargs):
    """Plot the survival function P(τ > t).

    Parameters
    ----------
    volume, outflow, bins, fit, ax
        See :func:`plot_pdf`.

    Returns
    -------
    matplotlib.figure.Figure
    """
    rtd = residence_time_distribution(volume, outflow, bins=bins)
    if rtd.empty:
        raise ValueError("No valid residence time data to plot.")

    survival = 1.0 - rtd['cumulative_density'].values

    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))
    else:
        fig = ax.figure

    ax.step(rtd['bin_center_hours'], survival, where='mid', linewidth=2,
            color='steelblue', label='Empirical')

    if fit:
        t = np.linspace(rtd['bin_center_hours'].min(),
                        rtd['bin_center_hours'].max(), 500)
        for label, _, _, sf_vals in _get_fitted_curves(volume, outflow, t):
            ax.plot(t, sf_vals, linewidth=2, label=label)

    ax.set_xlabel("Residence Time (hours)", fontsize=12)
    ax.set_ylabel("P(τ > t)", fontsize=12)
    ax.set_title("Survival Function (Complementary CDF)", fontsize=14)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


# =========================================================================
# 4. Log-Scale Axes (Semi-log PDF + Log-log Survival)
# =========================================================================

def plot_log_scale(volume, outflow, bins=50, fit=True, **kwargs):
    """Plot residence time PDF (semi-log) and survival function (log-log).

    Parameters
    ----------
    volume, outflow, bins, fit
        See :func:`plot_pdf`.

    Returns
    -------
    matplotlib.figure.Figure
    """
    log_rtd = log_residence_time_distribution(volume, outflow, bins=bins)
    rtd = residence_time_distribution(volume, outflow, bins=bins)
    if rtd.empty:
        raise ValueError("No valid residence time data to plot.")

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    # --- Left panel: semi-log PDF ---
    ax = axes[0]
    ax.bar(rtd['bin_center_hours'], rtd['density'],
           width=np.diff(np.concatenate(
               [[0], rtd['bin_center_hours'].values])).mean(),
           alpha=0.5, color='steelblue', label='Empirical')
    if fit:
        t = np.linspace(max(rtd['bin_center_hours'].min(), 0.01),
                        rtd['bin_center_hours'].max(), 500)
        for label, pdf_vals, _, _ in _get_fitted_curves(volume, outflow, t):
            ax.plot(t, pdf_vals, linewidth=2, label=label)
    ax.set_xscale('log')
    ax.set_xlabel("Residence Time (hours, log scale)", fontsize=12)
    ax.set_ylabel("Probability Density", fontsize=12)
    ax.set_title("Semi-Log PDF", fontsize=14)
    ax.legend(fontsize=8)

    # --- Right panel: log-log survival ---
    ax = axes[1]
    survival = 1.0 - rtd['cumulative_density'].values
    survival_pos = np.maximum(survival, 1e-10)
    ax.step(rtd['bin_center_hours'], survival_pos, where='mid',
            linewidth=2, color='steelblue', label='Empirical')
    if fit:
        t = np.linspace(max(rtd['bin_center_hours'].min(), 0.01),
                        rtd['bin_center_hours'].max(), 500)
        for label, _, _, sf_vals in _get_fitted_curves(volume, outflow, t):
            ax.plot(t, np.maximum(sf_vals, 1e-10), linewidth=2, label=label)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel("Residence Time (hours, log scale)", fontsize=12)
    ax.set_ylabel("P(τ > t)  (log scale)", fontsize=12)
    ax.set_title("Log-Log Survival Function", fontsize=14)
    ax.set_ylim(bottom=1e-4, top=1)
    ax.legend(fontsize=8)

    fig.tight_layout()
    return fig


# =========================================================================
# 5. Time-Varying Residence Time Heatmap
# =========================================================================

def plot_time_varying_heatmap(volume, outflow, max_age_hours=None,
                               n_age_bins=200, ax=None, **kwargs):
    """Heatmap of the residence time distribution evolving over calendar time.

    For each timestep the instantaneous nominal residence time is computed.
    The x-axis is calendar time, y-axis is "age" (binned), and colour
    encodes the density of timesteps falling in each age bin.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    max_age_hours : float, optional
        Upper limit of the y-axis.  Defaults to the 95th-percentile τ.
    n_age_bins : int
        Number of vertical bins.
    ax : matplotlib.axes.Axes, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        raise ValueError("No valid residence time data.")

    if max_age_hours is None:
        max_age_hours = float(tau.quantile(0.95))

    age_edges = np.linspace(0, max_age_hours, n_age_bins + 1)

    # Rolling window: group by month to get a smoother heatmap
    grouped = tau.groupby(tau.index.to_period('M'))
    calendar_labels = []
    density_columns = []

    for period, group in grouped:
        counts, _ = np.histogram(group.values, bins=age_edges, density=True)
        density_columns.append(counts)
        calendar_labels.append(period.start_time)

    if not density_columns:
        raise ValueError("Insufficient data for heatmap.")

    density_array = np.array(density_columns).T  # (n_age_bins, n_months)
    age_centers = 0.5 * (age_edges[:-1] + age_edges[1:])

    if ax is None:
        fig, ax = plt.subplots(figsize=(13, 6))
    else:
        fig = ax.figure

    vmin = max(density_array[density_array > 0].min(), 1e-6) \
        if (density_array > 0).any() else 1e-6
    pcm = ax.pcolormesh(
        calendar_labels, age_centers, density_array,
        shading='auto', cmap='viridis',
        norm=mcolors.LogNorm(vmin=vmin, vmax=density_array.max()),
    )
    fig.colorbar(pcm, ax=ax, label='Probability Density')
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Residence Time (hours)", fontsize=12)
    ax.set_title("Time-Varying Residence Time Distribution", fontsize=14)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


# =========================================================================
# 6. Quantile Time-Series with Discharge
# =========================================================================

def plot_quantile_timeseries(volume, outflow, discharge=None,
                              resample='M', ax=None, **kwargs):
    """Plot median and quantile bands of residence time over calendar time.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    discharge : pd.Series, optional
        Discharge series for a context panel.  If *None* the outflow series
        is used.
    resample : str
        Pandas resample frequency for smoothing (default ``'M'`` = monthly).
    ax : matplotlib.axes.Axes, optional
        If provided, discharge panel is skipped and only the quantile panel
        is drawn.

    Returns
    -------
    matplotlib.figure.Figure
    """
    tau = nominal_residence_time(volume, outflow)
    tau_valid = tau.dropna()
    if tau_valid.empty:
        raise ValueError("No valid residence time data.")

    grouped = tau_valid.resample(resample)
    q10 = grouped.quantile(0.10)
    q25 = grouped.quantile(0.25)
    q50 = grouped.quantile(0.50)
    q75 = grouped.quantile(0.75)
    q90 = grouped.quantile(0.90)

    if discharge is None:
        discharge = outflow

    if ax is not None:
        # Single-panel mode
        fig = ax.figure
        ax.fill_between(q10.index, q10, q90, alpha=0.2, color='#2e86c1',
                        label='10th–90th pctl')
        ax.fill_between(q25.index, q25, q75, alpha=0.4, color='#2e86c1',
                        label='25th–75th pctl')
        ax.plot(q50.index, q50, color='#1a5276', linewidth=2,
                label='Median')
        ax.set_ylabel("Residence Time (hours)", fontsize=12)
        ax.legend(fontsize=10)
        fig.tight_layout()
        return fig

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                              gridspec_kw={'height_ratios': [1, 2.5]})

    # Top: discharge
    q_resamp = discharge.resample(resample).mean()
    axes[0].fill_between(q_resamp.index, q_resamp, alpha=0.4,
                         color='steelblue')
    axes[0].plot(q_resamp.index, q_resamp, color='steelblue', linewidth=0.8)
    axes[0].set_ylabel("Discharge (cfs)", fontsize=12)
    axes[0].set_title("Discharge and Residence Time Quantiles", fontsize=14)

    # Bottom: quantile fan
    axes[1].fill_between(q10.index, q10, q90, alpha=0.2, color='#2e86c1',
                         label='10th–90th pctl')
    axes[1].fill_between(q25.index, q25, q75, alpha=0.4, color='#2e86c1',
                         label='25th–75th pctl')
    axes[1].plot(q50.index, q50, color='#1a5276', linewidth=2,
                 label='Median residence time')
    axes[1].set_xlabel("Date", fontsize=12)
    axes[1].set_ylabel("Residence Time (hours)", fontsize=12)
    axes[1].legend(fontsize=10, loc='upper right')

    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


# =========================================================================
# 7. Young Water Fraction (Fyw)
# =========================================================================

def plot_young_water_fraction(volume, outflow, threshold_hours=72,
                               resample='M', ax=None, **kwargs):
    """Plot the young water fraction over time.

    The young water fraction at each timestep is the probability that the
    residence time is shorter than *threshold_hours*.  Here it is computed
    empirically as the fraction of τ values within each *resample* period
    that fall below the threshold.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    threshold_hours : float
        Young-water threshold (default 72 h ≈ 3 days).
    resample : str
        Resampling frequency (default monthly).
    ax : matplotlib.axes.Axes, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        raise ValueError("No valid residence time data.")

    is_young = (tau < threshold_hours).astype(float)
    fyw = is_young.resample(resample).mean()
    mean_tau = tau.resample(resample).mean()

    if ax is not None:
        fig = ax.figure
        ax.bar(fyw.index, fyw, width=25, color='teal', alpha=0.7)
        ax.axhline(fyw.mean(), color='darkred', linestyle='--', linewidth=1.5,
                   label=f'Mean Fyw = {fyw.mean():.2f}')
        ax.set_ylabel("Young Water Fraction")
        ax.set_ylim(0, 1)
        ax.legend()
        fig.tight_layout()
        return fig

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

    # Fyw
    axes[0].bar(fyw.index, fyw, width=25, color='teal', alpha=0.7)
    axes[0].axhline(fyw.mean(), color='darkred', linestyle='--',
                    linewidth=1.5,
                    label=f'Mean Fyw = {fyw.mean():.2f}')
    axes[0].set_ylabel("Young Water Fraction (Fyw)", fontsize=12)
    axes[0].set_title(
        f"Young Water Fraction (threshold = {threshold_hours} hours)",
        fontsize=14)
    axes[0].set_ylim(0, 1)
    axes[0].legend(fontsize=10)

    # Mean residence time
    axes[1].plot(mean_tau.index, mean_tau, color='darkorange', linewidth=1.5)
    axes[1].set_xlabel("Date", fontsize=12)
    axes[1].set_ylabel("Mean Residence Time (hours)", fontsize=12)
    axes[1].set_title("Mean Residence Time Over Time", fontsize=14)

    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


# =========================================================================
# 8. Box Plots and Violin Plots by Season
# =========================================================================

def plot_seasonal_box_violin(volume, outflow, seasons=None,
                              ax=None, **kwargs):
    """Side-by-side box plot and violin plot of residence time by season.

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    seasons : dict, optional
        Mapping season name → list of month numbers.
    ax : matplotlib.axes.Axes, optional
        If given only a box plot is drawn (single panel).

    Returns
    -------
    matplotlib.figure.Figure
    """
    tau = nominal_residence_time(volume, outflow).dropna()
    if tau.empty:
        raise ValueError("No valid residence time data.")

    if seasons is None:
        seasons = {'DJF': [12, 1, 2], 'MAM': [3, 4, 5],
                   'JJA': [6, 7, 8], 'SON': [9, 10, 11]}

    slabels = _season_labels(tau.index, seasons)
    season_order = list(seasons.keys())
    data_by_season = [tau[slabels == s].values for s in season_order]
    colors = ['#5dade2', '#58d68d', '#f4d03f', '#eb984e']

    if ax is not None:
        fig = ax.figure
        bp = ax.boxplot(data_by_season, labels=season_order,
                        patch_artist=True, showfliers=False,
                        medianprops=dict(color='black', linewidth=2))
        for patch, c in zip(bp['boxes'], colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.7)
        ax.set_ylabel("Residence Time (hours)")
        fig.tight_layout()
        return fig

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Box plot
    bp = axes[0].boxplot(data_by_season, labels=season_order,
                         patch_artist=True, showfliers=False,
                         medianprops=dict(color='black', linewidth=2))
    for patch, c in zip(bp['boxes'], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    axes[0].set_ylabel("Residence Time (hours)", fontsize=12)
    axes[0].set_title("Residence Time by Season — Box Plot", fontsize=14)

    # Violin plot
    vp = axes[1].violinplot(data_by_season, showmedians=True,
                            showextrema=False)
    for i, body in enumerate(vp['bodies']):
        body.set_facecolor(colors[i])
        body.set_alpha(0.7)
    axes[1].set_xticks(range(1, len(season_order) + 1))
    axes[1].set_xticklabels(season_order)
    axes[1].set_ylabel("Residence Time (hours)", fontsize=12)
    axes[1].set_title("Residence Time by Season — Violin Plot", fontsize=14)

    fig.tight_layout()
    return fig


# =========================================================================
# 9. Stacked Age-Composition Bars
# =========================================================================

def plot_age_composition(volumes_dict, outflows_dict,
                         bin_edges_hours=None, labels=None,
                         ax=None, **kwargs):
    """Stacked bar chart showing the age-class composition for multiple
    reaches or scenarios.

    Parameters
    ----------
    volumes_dict : dict[str, pd.Series]
        ``{site_label: volume_series}``
    outflows_dict : dict[str, pd.Series]
        ``{site_label: outflow_series}``  (keys must match *volumes_dict*).
    bin_edges_hours : list of float, optional
        Bin edges in hours.  Defaults to
        ``[0, 6, 24, 72, 168, 720, np.inf]``.
    labels : list of str, optional
        Human-readable labels for each bin.
    ax : matplotlib.axes.Axes, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    if bin_edges_hours is None:
        bin_edges_hours = [0, 6, 24, 72, 168, 720, np.inf]
    if labels is None:
        labels = ['< 6 hr', '6–24 hr', '1–3 days',
                  '3–7 days', '7–30 days', '> 30 days']

    colors = ['#2ecc71', '#27ae60', '#f1c40f', '#e67e22', '#e74c3c', '#8e44ad']
    sites = list(volumes_dict.keys())
    n_bins = len(labels)
    fractions = np.zeros((len(sites), n_bins))

    for i, site in enumerate(sites):
        tau = nominal_residence_time(volumes_dict[site],
                                     outflows_dict[site]).dropna()
        if tau.empty:
            continue
        for j in range(n_bins):
            lo = bin_edges_hours[j]
            hi = bin_edges_hours[j + 1]
            fractions[i, j] = float(((tau >= lo) & (tau < hi)).sum()) / len(tau)

    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))
    else:
        fig = ax.figure

    x = np.arange(len(sites))
    bottom = np.zeros(len(sites))
    for j in range(n_bins):
        ax.bar(x, fractions[:, j], bottom=bottom, color=colors[j % len(colors)],
               label=labels[j], edgecolor='white', width=0.6)
        bottom += fractions[:, j]

    ax.set_xticks(x)
    ax.set_xticklabels(sites, fontsize=11)
    ax.set_ylabel("Fraction of Time", fontsize=12)
    ax.set_title("Residence Time Age Composition", fontsize=14)
    ax.legend(title="Age Class", bbox_to_anchor=(1.02, 1),
              loc='upper left', fontsize=10)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    return fig


# =========================================================================
# 10. Spaghetti + Envelope / Fan Chart
# =========================================================================

def plot_spaghetti_envelope(reach_volumes, reach_outflows, routing_paths,
                             max_hours=None, **kwargs):
    """Spaghetti plot and fan chart of network travel-time CDFs.

    Each source-to-outlet path provides one CDF.  The left panel overlays
    all CDFs ("spaghetti"); the right panel shows the percentile envelope.

    Parameters
    ----------
    reach_volumes : pd.DataFrame
        Columns = reach_ids, values = volume in acre-ft.
    reach_outflows : pd.DataFrame
        Columns = reach_ids, values = outflow in cfs.
    routing_paths : dict
        ``{source_reach_id: [reach_id, ...]}``
    max_hours : float, optional
        Upper x-axis limit.

    Returns
    -------
    matplotlib.figure.Figure
    """
    tt_df = dynamic_travel_times(reach_volumes, reach_outflows, routing_paths)
    if tt_df.empty:
        raise ValueError("No travel time data available.")

    # Build a CDF for each source reach (across time)
    all_values = []
    for col in tt_df.columns:
        vals = tt_df[col].dropna().values
        if len(vals) > 0:
            all_values.append(vals)

    if not all_values:
        raise ValueError("No valid travel-time realizations.")

    if max_hours is None:
        max_hours = float(np.percentile(
            np.concatenate(all_values), 95)) * 1.2

    time_axis = np.linspace(0, max_hours, 500)
    cdfs = np.zeros((len(all_values), len(time_axis)))
    for i, vals in enumerate(all_values):
        sorted_v = np.sort(vals)
        cdfs[i, :] = np.searchsorted(sorted_v, time_axis) / len(sorted_v)

    p05 = np.percentile(cdfs, 5, axis=0)
    p25 = np.percentile(cdfs, 25, axis=0)
    p50 = np.percentile(cdfs, 50, axis=0)
    p75 = np.percentile(cdfs, 75, axis=0)
    p95 = np.percentile(cdfs, 95, axis=0)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Spaghetti
    ax = axes[0]
    for i in range(len(cdfs)):
        ax.plot(time_axis, cdfs[i], color='steelblue', alpha=0.15,
                linewidth=0.5)
    ax.plot(time_axis, p50, color='darkred', linewidth=2, label='Median')
    ax.set_xlabel("Travel Time (hours)", fontsize=12)
    ax.set_ylabel("Cumulative Probability", fontsize=12)
    ax.set_title(f"Spaghetti Plot ({len(cdfs)} source reaches)", fontsize=14)
    ax.legend(fontsize=11)
    ax.set_xlim(0, max_hours)
    ax.set_ylim(0, 1)

    # Fan / envelope
    ax = axes[1]
    ax.fill_between(time_axis, p05, p95, alpha=0.2, color='#2e86c1',
                    label='5th–95th pctl')
    ax.fill_between(time_axis, p25, p75, alpha=0.4, color='#2e86c1',
                    label='25th–75th pctl')
    ax.plot(time_axis, p50, color='#1a5276', linewidth=2, label='Median')
    ax.set_xlabel("Travel Time (hours)", fontsize=12)
    ax.set_ylabel("Cumulative Probability", fontsize=12)
    ax.set_title("Fan / Envelope Plot", fontsize=14)
    ax.legend(fontsize=11)
    ax.set_xlim(0, max_hours)
    ax.set_ylim(0, 1)

    fig.tight_layout()
    return fig


# =========================================================================
# Convenience: Duration Curve
# =========================================================================

def plot_duration_curve(volume, outflow, ax=None, **kwargs):
    """Plot the residence-time duration curve (from
    :func:`~hspf.reports.residence.residence_time_duration_curve`).

    Parameters
    ----------
    volume : pd.Series
        Volume in acre-ft.
    outflow : pd.Series
        Outflow in cfs.
    ax : matplotlib.axes.Axes, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    dc = residence_time_duration_curve(volume, outflow)
    if dc.empty:
        raise ValueError("No valid data for duration curve.")

    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))
    else:
        fig = ax.figure

    ax.plot(dc['exceedance_probability'] * 100,
            dc['residence_time_hours'],
            color='steelblue', linewidth=2)
    ax.set_xlabel("Exceedance Probability (%)", fontsize=12)
    ax.set_ylabel("Residence Time (hours)", fontsize=12)
    ax.set_title("Residence Time Duration Curve", fontsize=14)
    ax.set_yscale('log')
    fig.tight_layout()
    return fig
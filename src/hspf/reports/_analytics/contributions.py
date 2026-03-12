# -*- coding: utf-8 -*-
"""
Model-agnostic channel contribution and fate analytics.

Pure computation functions that accept generic pandas objects.
No HSPF imports, no uci/hbn references.
"""
import pandas as pd
import numpy as np


def compute_fate_factors(inflow_ts, outflow_ts):
    """Compute per-reach fate factors: outflow / inflow.

    Parameters
    ----------
    inflow_ts : pd.DataFrame
        Timeseries of reach inflows. Columns are reach IDs, index is DatetimeIndex.
    outflow_ts : pd.DataFrame
        Timeseries of reach outflows. Same shape as inflow_ts.

    Returns
    -------
    pd.DataFrame
        Fate factors (dimensionless ratio), same shape as inputs.
    """
    return outflow_ts / inflow_ts


def compute_path_fate_factors(fate_ts, routing_paths):
    """Compute cumulative fate factors along routing paths.

    For each source reach, the path fate factor at each timestep is the product
    of the per-reach fate factors along the routing path from source to outlet.

    Parameters
    ----------
    fate_ts : pd.DataFrame
        Per-reach fate factors. Columns are reach IDs, index is DatetimeIndex.
    routing_paths : dict
        Mapping of {source_id: [list of reach_ids along path from source to outlet]}.
        The outlet itself should have a path of [outlet_id].

    Returns
    -------
    pd.DataFrame
        Cumulative path fate factors. Columns are source reach IDs,
        index is DatetimeIndex. Values are the product of fate factors
        along each source's path.
    """
    fate_factors = pd.concat(
        [fate_ts[path].prod(axis=1) for path in routing_paths.values()],
        axis=1,
    )
    fate_factors.columns = list(routing_paths.keys())
    return fate_factors


def compute_local_load(inflow_ts, outflow_ts, upstream_reach_map):
    """Compute local (incremental) load at each reach.

    Local load = reach total inflow - sum of upstream reach outflows.
    This represents the contribution entering from the local catchment only.

    Parameters
    ----------
    inflow_ts : pd.DataFrame
        Timeseries of reach inflows. Columns are reach IDs.
    outflow_ts : pd.DataFrame
        Timeseries of reach outflows. Columns are reach IDs.
    upstream_reach_map : dict
        Mapping of {reach_id: [list of immediately upstream reach_ids]}.
        Headwater reaches should map to an empty list.

    Returns
    -------
    pd.DataFrame
        Local load timeseries. Columns are reach IDs.
    """
    result = {}
    for reach_id in inflow_ts.columns:
        upstream_ids = upstream_reach_map.get(reach_id, [])
        if upstream_ids:
            upstream_out = outflow_ts[upstream_ids].sum(axis=1)
        else:
            upstream_out = 0
        result[reach_id] = inflow_ts[reach_id] - upstream_out
    return pd.DataFrame(result, index=inflow_ts.index)


def compute_contributions(local_loads, path_fate_factors):
    """Compute source contributions at the outlet.

    contribution = local_load * path_fate_factor (element-wise).

    Parameters
    ----------
    local_loads : pd.DataFrame
        Local load timeseries per reach. Columns are reach IDs.
    path_fate_factors : pd.DataFrame
        Cumulative path fate factors per reach. Columns are reach IDs.
        Must share the same columns as local_loads (or a subset).

    Returns
    -------
    pd.DataFrame
        Contribution timeseries per source reach.
    """
    common = local_loads.columns.intersection(path_fate_factors.columns)
    return local_loads[common].mul(path_fate_factors[common].values)


def compute_contribution_pct(contributions, target_load_ts):
    """Compute percentage contribution relative to the outlet load.

    Parameters
    ----------
    contributions : pd.DataFrame
        Contribution timeseries per source reach.
    target_load_ts : pd.DataFrame or pd.Series
        Total load timeseries at the target outlet.

    Returns
    -------
    pd.DataFrame
        Percentage contributions per source reach (0-100 scale).
    """
    return contributions.div(target_load_ts.values) * 100


def contribution_summary(contributions, local_loads, target_load_ts):
    """Aggregate contributions into a summary DataFrame.

    Parameters
    ----------
    contributions : pd.DataFrame
        Contribution timeseries per source reach.
    local_loads : pd.DataFrame
        Local load timeseries per reach.
    target_load_ts : pd.DataFrame or pd.Series
        Total load at the target outlet.

    Returns
    -------
    pd.DataFrame
        Summary with columns: source_id, load, contribution, contribution_pct.
        Values are the temporal means.
    """
    common = local_loads.columns.intersection(contributions.columns)
    pct = compute_contribution_pct(contributions[common], target_load_ts)

    df = contributions[common].mean().to_frame().reset_index()
    df.columns = ['source_id', 'contribution']
    df['load'] = local_loads[common].mean().values
    df['contribution_pct'] = pct[common].mean().values
    return df[['source_id', 'load', 'contribution', 'contribution_pct']]

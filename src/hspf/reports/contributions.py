# -*- coding: utf-8 -*-
"""
Channel contributions and allocation reports.
"""
import pandas as pd
from hspf.reports.loading import get_catchment_loading
from hspf.reports.timeseries import filter_years
from hspf.reports.timeseries import filter_months


ALLOCATION_SELECTOR = {'Q': {'input': ['IVOL'],
                             'output': ['ROVOL']},
                       'TP': {'input': ['PTOTIN'],
                              'output': ['PTOTOUT']},
                       'TSS': {'input': ['ISEDTOT'],
                              'output': ['ROSEDTOT']},
                       'OP': {'input': ['PO4INDIS'],
                              'output': ['PO4OUTDIS']},                      
                       'N': {'input': ['NO3INTOT','NO2INTOT'],
                              'output': ['NO2OUTTOT','NO3OUTTOT']},
                       'TKN': {'input': ['TAMINTOT','NTOTORGIN'],
                              'output': ['TAMOUTTOT', 'NTOTORGOUT']}
                       }

def channel_inflows(constituent,hbn,t_code,reach_ids = None):
    """Retrieve total channel inflow timeseries for a constituent.

    Parameters
    ----------
    constituent : str
        Constituent name (key in :data:`ALLOCATION_SELECTOR`).
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    reach_ids : list of int or None, optional
        Reach IDs to retrieve.  ``None`` retrieves all.

    Returns
    -------
    pd.DataFrame
        Inflow timeseries with DatetimeIndex and reach IDs as columns.
    """
    load_in =  sum([hbn.get_multiple_timeseries('RCHRES',
                                       t_code,
                                       t_cons,
                                       opnids = reach_ids)
               for t_cons in ALLOCATION_SELECTOR[constituent]['input']])
    
    if constituent == 'TSS':
        load_in = load_in*2000
    
    return load_in

def channel_outflows(constituent,hbn,t_code,reach_ids = None):
    """Retrieve total channel outflow timeseries for a constituent.

    Parameters
    ----------
    constituent : str
        Constituent name (key in :data:`ALLOCATION_SELECTOR`).
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    reach_ids : list of int or None, optional
        Reach IDs to retrieve.  ``None`` retrieves all.

    Returns
    -------
    pd.DataFrame
        Outflow timeseries with DatetimeIndex and reach IDs as columns.
    """
    load_out =  sum([hbn.get_multiple_timeseries('RCHRES',
                                       t_code,
                                       t_cons,
                                       opnids = reach_ids)
               for t_cons in ALLOCATION_SELECTOR[constituent]['output']])
    if constituent == 'TSS':
        load_out = load_out*2000
    return load_out

def channel_fate(constituent,hbn,t_code,reach_ids = None):
    """Compute channel fate factors (outflow / inflow ratio) per reach.

    Parameters
    ----------
    constituent : str
        Constituent name (key in :data:`ALLOCATION_SELECTOR`).
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    reach_ids : list of int or None, optional
        Reach IDs to compute.  ``None`` computes all.

    Returns
    -------
    pd.DataFrame
        Fate factor timeseries (outflow / inflow) with DatetimeIndex.
    """
    load_in = channel_inflows(constituent,hbn,t_code,reach_ids)
    load_out = channel_outflows(constituent,hbn,t_code,reach_ids)
    return load_out / load_in

def local_loading(constituent,uci,hbn,t_code,reach_ids = None):
    """Compute local (incremental) loading at each reach.

    Local load is the channel inflow minus the sum of upstream outflows,
    representing contributions from the local catchment only.

    Parameters
    ----------
    constituent : str
        Constituent name (key in :data:`ALLOCATION_SELECTOR`).
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    reach_ids : list of int or None, optional
        Reach IDs to compute.  ``None`` computes all.

    Returns
    -------
    pd.DataFrame
        Local load timeseries with reach IDs as columns.
    """
    load_in = channel_inflows(constituent,hbn,t_code,reach_ids)
    load_out = channel_outflows(constituent,hbn,t_code,reach_ids)
    upstream_reach_map = {reach_id: list(uci.network.upstream(reach_id)) for reach_id in load_in.columns}
    return _compute_local_load(load_in, load_out, upstream_reach_map)



def catchment_contributions(uci,hbn,constituent,target_reach_id, landcovers = None,start_year = 1996, end_year = 2100):
    """Compute per-catchment contributions to the target reach outlet.

    Combines edge-of-field loading with routing fate factors to estimate
    each catchment's contribution to the load at *target_reach_id*.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    target_reach_id : int
        Reach ID of the outlet where contributions are evaluated.
    landcovers : list of str or None, optional
        If provided, filter results to these land-cover types.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Contribution summary per catchment (and optionally per land cover)
        with columns including ``TVOLNO``, ``load``, ``contribution``, and
        ``contribution_perc``.
    """
    p = uci.network.paths(target_reach_id)
    p[target_reach_id] = [target_reach_id]
    fate = channel_fate(constituent,hbn,5)
    fate_factors = _compute_path_fate_factors(fate, p)
    target_load = channel_outflows(constituent,hbn,5,[target_reach_id])
    fate_factors = fate_factors.reset_index().melt(id_vars = 'datetime')
    
    df = get_catchment_loading(uci,hbn,constituent)
    df = df.loc[(df['datetime'].dt.year >= start_year) & (df['datetime'].dt.year <= end_year)]
    df = pd.merge(df,fate_factors,left_on = ['TVOLNO','datetime'],right_on = ['variable','datetime'])
    
    df['contribution'] = df['value']*df['load']

    
    df = pd.merge(df,target_load.reset_index().melt(id_vars='datetime',var_name = 'target_reach',value_name = 'target_load'),left_on='datetime',right_on='datetime')
    df['contribution_perc'] = df['contribution']/(df['target_load'])*100
    
    df = df.groupby(['TVOLNO','landcover','landcover_area'])[['load','contribution','contribution_perc','target_load']].mean().reset_index()

    if landcovers is not None:
        df = df.loc[df['landcover'].isin(landcovers)]

    else:
        df = df.groupby(['TVOLNO',])[['landcover_area','load','contribution','contribution_perc']].sum().reset_index()

    return df

def total_contributions(constituent,uci,hbn,target_reach_id, start_year = 1996, end_year = 2100):
    """Compute total reach-level contributions to the target outlet.

    Uses local loading and cumulative fate factors along routing paths
    to determine each reach's contribution.

    Parameters
    ----------
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    target_reach_id : int
        Reach ID of the outlet where contributions are evaluated.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Columns: ``TVOLNO``, ``load``, ``contribution``,
        ``contribution_perc``.
    """
    p = uci.network.paths(target_reach_id)
    p[target_reach_id] = [target_reach_id]
    fate = channel_fate(constituent,hbn,5)
    loads = local_loading(constituent,uci,hbn,5)
    fate_factors = _compute_path_fate_factors(fate, p)
    target_load = channel_outflows(constituent,hbn,5,[target_reach_id])

    contribution = _compute_contributions(loads, fate_factors)
    df = _summarize(contribution, loads, target_load,start_year, end_year)
    df = df.rename(columns={'source_id': 'TVOLNO', 'contribution_pct': 'contribution_perc'})
    return df[['TVOLNO','load','contribution','contribution_perc']]


def catchment_contribution_summary(uci,hbn,target_reach_id,landcovers = None,start_year = 1996, end_year = 2100):
    """Summarise catchment contributions for Q, TP, and TSS.

    Concatenates :func:`catchment_contributions` results for each of the
    default constituents (``'Q'``, ``'TP'``, ``'TSS'``).

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    target_reach_id : int
        Reach ID of the outlet where contributions are evaluated.
    landcovers : list of str or None, optional
        If provided, filter results to these land-cover types.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Combined contribution summary with an additional ``constituent``
        column.
    """
    dfs = []
    for constituent in ['Q','TP','TSS']:
        df = catchment_contributions(uci,hbn,constituent,target_reach_id,landcovers,start_year,end_year)
        df['constituent'] = constituent
        dfs.append(df)
    return pd.concat(dfs,axis = 0)



##% private Utility functions for contributions report

def _compute_path_fate_factors(fate_ts, routing_paths):
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


def _compute_local_load(inflow_ts, outflow_ts, upstream_reach_map):
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


def _compute_contributions(local_loads, path_fate_factors):
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


def _compute_contribution_pct(contributions, target_load_ts):
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


def _summarize(contributions, local_loads, target_load_ts,start_year = 1996, end_year = 2100, months = None):
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
    contributions = filter_months(filter_years(contributions, start_year, end_year), months)
    local_loads = filter_months(filter_years(local_loads, start_year, end_year), months)
    target_load_ts = filter_months(filter_years(target_load_ts, start_year, end_year), months)

    common = local_loads.columns.intersection(contributions.columns)
    pct = _compute_contribution_pct(contributions[common], target_load_ts)

    df = contributions[common].mean().to_frame().reset_index()
    df.columns = ['source_id', 'contribution']
    df['load'] = local_loads[common].mean().values
    df['contribution_pct'] = pct[common].mean().values
    return df[['source_id', 'load', 'contribution', 'contribution_pct']]

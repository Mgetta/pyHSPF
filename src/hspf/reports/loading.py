# -*- coding: utf-8 -*-
"""
Constituent loading reports — catchment and watershed edge-of-field loading.
"""
import pandas as pd

from hspf.reports.nutrients import (
    total_phosphorus, 
    total_nitrogen
)
from hspf.reports.utils import (
    validate_periods,
    add_temporal_groups,
    SIMULATION_PERIOD_TO_TIME_STEP
)

def get_constituent_loading(uci,hbn,constituent,time_step =5,start_year = 1996,end_year = 2100):
    """Retrieve per-OPNID constituent loading rates for PERLNDs and IMPLNDs.

    For ``'TP'`` the loading is computed via :func:`total_phosphorus`;
    For ``'TN'`` the loading is computed via :func:`total_nitrogen`;
    for all other constituents the HBN timeseries are read directly.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns ``datetime``, ``OPNID``,
        ``value``, and ``OPERATION``.
    """
    if constituent == 'TP':
        perlnds = total_phosphorus(uci,hbn,t_code=time_step,operation = 'PERLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
        implnds = total_phosphorus(uci,hbn,t_code=time_step,operation = 'IMPLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
    elif constituent == 'TN':
        perlnds = total_nitrogen(uci,hbn,t_code=time_step,operation = 'PERLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
        implnds = total_nitrogen(uci,hbn,t_code=time_step,operation = 'IMPLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
    else:
        perlnds = hbn.get_perlnd_constituent(constituent,time_step = time_step).reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
        implnds = hbn.get_implnd_constituent(constituent,time_step = time_step).reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
    
    perlnds['OPERATION'] = 'PERLND'
    implnds['OPERATION'] = 'IMPLND'

    df = pd.concat([perlnds,implnds],axis=0)
    df.rename(columns = {'index': 'datetime'}, inplace = True)

    
    # units = 'lb/acre'  
    if constituent == 'Q':
        df.loc[:, 'value'] = df['value']/12  # convert to ft/acre/month
    
    df = df.loc[(df['datetime'].dt.year >= start_year) & (df['datetime'].dt.year <= end_year)]

    
    return df


def _join_catchments(df,uci,constituent):
    """Join loading data with catchment and subwatershed metadata.

    Parameters
    ----------
    df : pd.DataFrame
        Loading data with ``OPERATION``, ``OPNID``, and ``value`` columns.
    uci : UCI
        Parsed UCI model object.
    constituent : str
        Constituent name used to label the output.

    Returns
    -------
    pd.DataFrame
        Input data enriched with ``load``, ``loading_rate``,
        ``landcover_area``, ``landcover``, ``catchment_area``, and
        ``constituent`` columns.
    """
    subwatersheds = uci.network.subwatersheds().reset_index()
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'].isin(['PERLND','IMPLND'])]
    areas = catchment_areas(uci)

    df = pd.merge(
        subwatersheds, df,
        left_on=['SVOL', 'SVOLNO'],
        right_on=['OPERATION', 'OPNID'],
        how='inner'
    )
    df = pd.merge(df, areas, on='TVOLNO', how='left')
    
    df['load'] = df['value'] * df['AFACTR']
    df = df.rename(columns={
        'value': 'loading_rate',
        'AFACTR': 'landcover_area',
        'LSID': 'landcover'
    })
    df['constituent'] = constituent
    return df

def get_catchment_loading(uci,hbn,constituent,time_step=5,start_year=1996,end_year=2100):
    """Compute catchment-level loading for a constituent.

    Combines :func:`get_constituent_loading` with catchment metadata via
    :func:`_join_catchments`.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Columns: ``datetime``, ``constituent``, ``TVOLNO``, ``SVOLNO``,
        ``SVOL``, ``landcover``, ``landcover_area``, ``catchment_area``,
        ``loading_rate``, ``load``.
    """
    df = get_constituent_loading(uci,hbn,constituent,time_step,start_year,end_year)
    df = _join_catchments(df,uci,constituent)
    df = df[['datetime','constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]
    return df


def monthly_loading(uci,hbn,constituent,aggregation_period = 'monthly',start_year = 1996,end_year = 2100):
    """Aggregate monthly constituent loading with flexible temporal grouping.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    aggregation_period : str or None, optional
        Period over which to aggregate: ``'monthly'``, ``'yearly'``,
        ``'seasonal'``, ``'simulation'``, or ``None`` (no aggregation).
        Default ``'monthly'``.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Aggregated loading rates with columns ``OPERATION``, ``OPNID``,
        ``value``, plus a temporal grouping column when applicable.
    """
    df = get_constituent_loading(uci,hbn,constituent,time_step=4,start_year=start_year,end_year=end_year)
    df = add_temporal_groups(df, 4)

    if aggregation_period == 'monthly':
        df = df.groupby(['month','OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period == 'simulation':
    # agg_period = simulation period
        df = df.groupby(['OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period == 'yearly':
        # agg_period = monthly
        df = df.groupby(['year','OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period == 'seasonal':
        # agg_period = seasonal
        df = df.groupby(['season','OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period is None:
        # agg_period = none
        df = df.groupby(['datetime','OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    else:
        raise ValueError(f"Unsupported aggregation_period '{aggregation_period}' for simulation_period 'monthly'")

    return df

def seasonal_loading(uci,hbn,constituent,season = None,aggregation_period = 'yearly',start_year = 1996,end_year = 2100):
    """Aggregate seasonal constituent loading.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    season : str or None, optional
        If provided, filter to a single season (e.g. ``'winter'``).
    aggregation_period : str or None, optional
        ``'yearly'`` averages across years per season; ``None`` keeps
        per-year seasonal totals.  Default ``'yearly'``.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Aggregated seasonal loading with columns ``season``,
        ``OPERATION``, ``OPNID``, ``value``, and optionally ``year``.
    """
    df = get_constituent_loading(uci,hbn,constituent,time_step=4,start_year=start_year,end_year=end_year)
    df = add_temporal_groups(df, 4)
    df = df.groupby(['season','year','OPNID','OPERATION'])['value'].aggregate('sum').reset_index()

    if season is not None:
        df = df.loc[df['season'] == season].copy()
        
    if aggregation_period is None:
        pass
    elif aggregation_period == 'yearly':
        df = df.groupby(['season','OPERATION','OPNID'])['value'].aggregate('mean').reset_index()
    else:
        raise ValueError(f"Unsupported aggregation_period '{aggregation_period}' for seasonal loading")
    
    return df

def annual_loading(uci,hbn,constituent,aggregation_period = None,start_year = 1996,end_year = 2100):
    """Aggregate annual constituent loading.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    aggregation_period : str or None, optional
        ``'yearly'`` or ``'simulation'`` averages across years;
        ``None`` keeps per-year values.  Default ``None``.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Aggregated annual loading with columns ``OPERATION``, ``OPNID``,
        ``value``, and optionally ``year``.
    """
    df = get_constituent_loading(uci,hbn,constituent,time_step=5,start_year=start_year,end_year=end_year)
    df = add_temporal_groups(df, 5)

    if aggregation_period == 'yearly':
            df = df.groupby(['OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period is None:
        df = df.groupby(['year','OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    elif aggregation_period == 'simulation':
        df = df.groupby(['OPERATION','OPNID'])['value'].aggregate(func='mean').reset_index()
    else:
        raise ValueError(f"Unsupported aggregation_period '{aggregation_period}' for annual loading")
    return df


def get_watershed_loading(uci,hbn,constituent,reach_ids=None,upstream_reach_ids = None,by_landcover = False,time_step = 5):
    """Edge-of-field loading for all catchments within a watershed.

    The watershed is defined by *reach_ids* and *upstream_reach_ids*.
    When *reach_ids* is ``None``, the network outlet(s) are used.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    reach_ids : list of int or None, optional
        Reach IDs defining the watershed outlet.
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    by_landcover : bool, optional
        Currently unused; reserved for future land-cover breakdown.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).

    Returns
    -------
    pd.DataFrame
        Catchment loading filtered to the specified watershed.
    """
    if reach_ids is None:
        reach_ids = uci.network.outlets()
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)

    df = get_catchment_loading(uci,hbn,constituent,time_step)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    return df

def constituent_loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean'):
    """
    Aggregate constituent loading rates with flexible temporal grouping and aggregation.

    Parameters
    ----------
    uci : UCI object
    hbn : HBN object
    constituent : str
        Constituent name (e.g. 'TP', 'TSS', 'Q')
    start_year, end_year : int
        Year range to filter
    simulation_period : str
        Resolution of model output: 'hourly', 'daily', 'monthly', 'yearly'.
    aggregation_period : str or None
        Period over which to aggregate: 'monthly', 'seasonal', 'yearly',
        'simulation', or ``None`` (no temporal aggregation).
        Must be ≥ *simulation_period*.
    agg_func : str or callable
        Aggregation function applied to 'value' column. Default 'mean'.
        Examples: 'mean', 'sum', 'max', 'min', 'median', 'std'

    Returns
    -------
    pd.DataFrame
        Columns: [OPERATION, OPNID, value] plus temporal grouping column if specified.
    """

    validate_periods(simulation_period, aggregation_period)
    
    # Get per-OPNID values
    df = get_constituent_loading(uci,hbn,constituent,simulation_period=simulation_period)   

    # Filter to selected years
    return df


def _filter_to_watershed(df,uci,reach_ids=None,upstream_reach_ids = None,drainage_area = None):
    """Filter a loading DataFrame to reaches within a watershed.

    Parameters
    ----------
    df : pd.DataFrame
        Loading data containing a ``TVOLNO`` column.
    uci : UCI
        Parsed UCI model object.
    reach_ids : list of int or None, optional
        Reach IDs defining the watershed outlet.
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    drainage_area : float or None, optional
        Custom drainage area.  If ``None``, computed from the network.

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame with an added ``watershed_area`` column.
    """
    if reach_ids is None:
        reach_ids = uci.network.outlets()
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if drainage_area is None:
        df['watershed_area'] = uci.network.drainage_area(reach_ids,upstream_reach_ids)
    else:
        df['watershed_area'] = drainage_area
    return df

def loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,
                    simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean',
                    reach_ids = None,upstream_reach_ids = None,
                    spatial_grouping = 'catchment',
                    by_landcover = False,landcovers = None,
                    drainage_area = None):
    """
    Unified loading summary with flexible temporal and spatial grouping.

    Parameters
    ----------
    uci : UCI object
    hbn : HBN object
    constituent : str
        Constituent name (e.g. 'TP', 'TSS', 'Q')
    start_year, end_year : int
        Year range to filter
    simulation_period : str
        Resolution of model output: 'hourly', 'daily', 'monthly', 'yearly'.
    aggregation_period : str or None
        Period over which to aggregate: 'monthly', 'seasonal', 'yearly',
        'simulation', or ``None`` (no temporal aggregation).
        Must be ≥ *simulation_period*.
    agg_func : str or callable
        Aggregation function. Default 'mean'.
    reach_ids : list of int, optional
        Reach IDs defining the watershed of interest.  Required when
        ``spatial_grouping='watershed'``.
    upstream_reach_ids : list of int, optional
        Upstream boundary reach IDs.
    spatial_grouping : str
        How to aggregate spatially.  One of:

        * ``'catchment'`` – one row per catchment (TVOLNO).
        * ``'watershed'`` – aggregate to a single value for the watershed
          defined by *reach_ids* (requires *reach_ids*).
        * ``'metzone'`` – one row per meteorological zone.
    by_landcover : bool
        If True, break out results by landcover type.
    landcovers : list of str, optional
        Filter to only these landcover names before aggregating.
    drainage_area : float, optional
        Custom drainage area for watershed-level loading rate.
        If None, calculated from the network.

    Returns
    -------
    pd.DataFrame
    """
    valid_spatial = ('catchment', 'watershed', 'metzone')
    if spatial_grouping not in valid_spatial:
        raise ValueError(
            f"spatial_grouping must be one of {valid_spatial}, got '{spatial_grouping}'"
        )

    validate_periods(simulation_period, aggregation_period)



    # Get per-OPNID values
    if simulation_period == 'monthly':
        df = monthly_loading(uci,hbn,constituent,aggregation_period, start_year, end_year)
    elif simulation_period == 'seasonal':
        df = seasonal_loading(uci,hbn,constituent,aggregation_period, start_year, end_year)
    elif simulation_period == 'yearly':
        df = annual_loading(uci,hbn,constituent,aggregation_period, start_year, end_year)
    else:
        raise ValueError(f"Unsupported simulation_period '{simulation_period}'")
    

    group_prefix = [col for col in df.columns if col not in ['OPERATION', 'OPNID', 'value']]
    
    df = _join_catchments(df,uci,constituent)


    # Filter to selected landcovers
    if landcovers is not None:
        df = df.loc[df['landcover'].isin(landcovers)].copy()

    # Filter to watershed if reach_ids or upstream_reach_ids provided, and add watershed area
    #if reach_ids is not None or upstream_reach_ids is not None:
    df = _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids,drainage_area)

    # --- spatial aggregation -------------------------------------------------
    if spatial_grouping == 'catchment':
        if by_landcover:
            df = df.groupby(group_prefix + ['TVOLNO','landcover','constituent'])[['landcover_area','load']].sum().reset_index()
            df['loading_rate'] = df['load'] / df['landcover_area']
        else:
            df = df.groupby(group_prefix + ['TVOLNO','constituent','catchment_area'])[['load']].sum().reset_index()
            df['loading_rate'] = df['load'] / df['catchment_area']

    elif spatial_grouping == 'watershed':
        ws_area = df['watershed_area'].iloc[0] if len(df) > 0 else None
        if by_landcover:
            df = df.groupby(group_prefix + ['landcover','constituent'])[['landcover_area','load']].sum().reset_index()
            df['loading_rate'] = df['load'] / df['landcover_area']
        else:
            grp = group_prefix + ['constituent']
            df = df.groupby(grp)[['load']].sum().reset_index()
            df['watershed_area'] = ws_area
            df['loading_rate'] = df['load'] / df['watershed_area']

    elif spatial_grouping == 'metzone':
        # Attach metzone metadata
        meta_frames = []
        for operation in ['PERLND', 'IMPLND']:
            if operation in uci.opnid_dict:
                meta = uci.opnid_dict[operation][['metzone']].copy()
                meta['SVOL'] = operation
                meta_frames.append(meta)
        if meta_frames:
            meta = pd.concat(meta_frames)
            df = pd.merge(df, meta, left_on=['SVOL', 'SVOLNO'], right_index=True, how='left')
        else:
            df['metzone'] = 'unknown'

        if by_landcover:
            grp = group_prefix + ['metzone', 'landcover', 'constituent']
            df = df.groupby(grp)[['landcover_area', 'load']].sum().reset_index()
            df['loading_rate'] = df['load'] / df['landcover_area']
        else:
            grp = group_prefix + ['metzone', 'constituent']
            df = df.groupby(grp)[['landcover_area', 'load']].sum().reset_index()
            df['loading_rate'] = df['load'] / df['landcover_area']

    return df


def catchment_loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False,simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean'):
    """Thin wrapper around :func:`loading_summary` with ``spatial_grouping='catchment'``."""
    return loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,simulation_period=simulation_period,aggregation_period=aggregation_period,agg_func=agg_func,spatial_grouping='catchment',by_landcover=by_landcover)

def watershed_loading_summary(uci,hbn,constituent,reach_ids=None,upstream_reach_ids = None,start_year = 1996,end_year = 2100,by_landcover = False,drainage_area = None,simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean'):
    """Thin wrapper around :func:`loading_summary` with ``spatial_grouping='watershed'``."""
    return loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,simulation_period=simulation_period,aggregation_period=aggregation_period,agg_func=agg_func,reach_ids=reach_ids,upstream_reach_ids=upstream_reach_ids,spatial_grouping='watershed',by_landcover=by_landcover,drainage_area=drainage_area)


def catchment_areas(uci):
    """Compute total catchment area for each TVOLNO (reach).

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.

    Returns
    -------
    pd.DataFrame
        Columns ``TVOLNO`` and ``catchment_area`` (sum of AFACTR values).
    """
    df = uci.network.subwatersheds().reset_index()
    df = df.groupby('TVOLNO')['AFACTR'].sum().reset_index()
    df.rename(columns = {'AFACTR':'catchment_area'},inplace = True)
    return df


# -*- coding: utf-8 -*-
"""
Constituent loading reports — catchment and watershed edge-of-field loading.
"""
import pandas as pd

from hspf.reports.phosphorus import total_phosphorous
from hspf.reports.utils import (
    validate_periods,
    aggregation_period_to_temporal_grouping,
)


def catchment_loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False,simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean'):
    """Thin wrapper around :func:`loading_summary` with ``spatial_grouping='catchment'``."""
    return loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,simulation_period=simulation_period,aggregation_period=aggregation_period,agg_func=agg_func,spatial_grouping='catchment',by_landcover=by_landcover)

def watershed_loading_summary(uci,hbn,constituent,reach_ids=None,upstream_reach_ids = None,start_year = 1996,end_year = 2100,by_landcover = False,drainage_area = None,simulation_period = 'yearly',aggregation_period = None,agg_func = 'mean'):
    """Thin wrapper around :func:`loading_summary` with ``spatial_grouping='watershed'``."""
    return loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,simulation_period=simulation_period,aggregation_period=aggregation_period,agg_func=agg_func,reach_ids=reach_ids,upstream_reach_ids=upstream_reach_ids,spatial_grouping='watershed',by_landcover=by_landcover,drainage_area=drainage_area)


def catchment_areas(uci):
    df = uci.network.subwatersheds().reset_index()
    df = df.groupby('TVOLNO')['AFACTR'].sum().reset_index()
    df.rename(columns = {'AFACTR':'catchment_area'},inplace = True)
    return df


def get_constituent_loading(uci,hbn,constituent,time_step = 5):
    if constituent == 'TP':
        perlnds = total_phosphorous(uci,hbn,t_code=time_step,operation = 'PERLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
        implnds = total_phosphorous(uci,hbn,t_code=time_step,operation = 'IMPLND').reset_index().melt(id_vars = ['datetime'],var_name = 'OPNID')
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
    
    return df


def _join_catchments(df,uci,constituent):
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

def get_catchment_loading(uci,hbn,constituent,time_step=5):
    df = get_constituent_loading(uci,hbn,constituent,time_step)
    df = _join_catchments(df,uci,constituent)
    df = df[['datetime','constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]
    return df


def get_watershed_loading(uci,hbn,constituent,reach_ids=None,upstream_reach_ids = None,by_landcover = False,time_step = 5):
    '''
    Edge of field loading for all catchments within a watershed defined by reach_ids and upstream_reach_ids
    
    
    '''
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

    df = get_constituent_loading(uci,hbn,constituent,time_step=simulation_period)
    df = df.loc[(df['datetime'].dt.year >= start_year) & (df['datetime'].dt.year <= end_year)]
    group_cols = ['OPERATION','OPNID']
    if aggregation_period is None:
        group_cols = ['datetime'] + group_cols
    elif aggregation_period == 'monthly':
        df['month'] = df['datetime'].dt.month
        group_cols = ['month'] + group_cols
    elif aggregation_period == 'yearly':
        df['year'] = df['datetime'].dt.year
        group_cols = ['year'] + group_cols
    elif aggregation_period == 'seasonal':
        df['season'] = df['datetime'].dt.month.map(
            {12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',
             6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'})
        group_cols = ['season'] + group_cols
    elif aggregation_period == 'simulation':
        pass  # no temporal grouping column — aggregate across all time
    else:
        raise ValueError(f"Unsupported aggregation_period '{aggregation_period}'")
    df = df.groupby(group_cols)['value'].agg(agg_func).reset_index()
    return df


def _filter_to_watershed(df,uci,reach_ids=None,upstream_reach_ids = None,drainage_area = None):
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

    # Get per-OPNID temporal summary
    df = constituent_loading_summary(uci,hbn,constituent,start_year,end_year,
                                     simulation_period=simulation_period,
                                     aggregation_period=aggregation_period,
                                     agg_func=agg_func)

    # Join to catchment metadata
    df = _join_catchments(df,uci,constituent)

    # Add relevant temporal grouping columns for spatial aggregation
    temporal_col = aggregation_period_to_temporal_grouping(simulation_period, aggregation_period)
    if temporal_col is not None:
        group_prefix = [temporal_col]
    elif aggregation_period is None:
        group_prefix = ['datetime']
    else:
        # aggregation_period='simulation' → aggregate across all time
        group_prefix = []

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

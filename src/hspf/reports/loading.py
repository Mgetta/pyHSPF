# -*- coding: utf-8 -*-
"""
Constituent loading reports — catchment and watershed edge-of-field loading.
"""
import pandas as pd

from hspf.reports.phosphorus import total_phosphorous
from hspf.reports.utils import (
    PERIOD_ORDER,
    simulation_period_to_time_step,
    validate_periods,
    aggregation_period_to_temporal_grouping,
)


def catchment_areas(uci):
    df = uci.network.subwatersheds().reset_index()
    df = df.groupby('TVOLNO')['AFACTR'].sum().reset_index()
    df.rename(columns = {'AFACTR':'catchment_area'},inplace = True)
    return df


def watershed_landcover_areas(uci,reach_ids,upstream_reach_ids = None):
    df = uci.network.drainage_area_landcover(reach_ids,upstream_reach_ids,group=True).reset_index()
    df['percent'] = 100*(df['area']/df['area'].sum())
    return df

def catchment_landcover_areas(uci,reach_ids = None):
    df = uci.network.subwatersheds().reset_index()[['TVOLNO','SVOL','LSID','AFACTR']]
    df.rename(columns = {'AFACTR':'area',
                         'TVOLNO':'catchment_id',
                         'LSID':'landcover',
                         'SVOL':'landcover_type'},inplace = True)
    if reach_ids is not None:
        df = df.loc[df['catchment_id'].isin(reach_ids)]
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

def get_catchment_loading(uci,hbn,constituent,time_step=5,by_landcover = False):
    df = get_constituent_loading(uci,hbn,constituent,time_step)
    df = _join_catchments(df,uci,constituent)
    df = df[['datetime','constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]
    return df



def get_watershed_loading(uci,hbn,reach_ids,constituent,upstream_reach_ids = None,by_landcover = False,time_step = 5):
    '''
    Edge of field loading for all catchments within a watershed defined by reach_ids and upstream_reach_ids
    
    
    '''
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)

    df = get_catchment_loading(uci,hbn,constituent,time_step)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    return df


def _average_constituent_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100,time_step = 5,group_by_month = False):
    """Backward-compatible wrapper. Prefer constituent_loading_summary() for new code."""
    if group_by_month:
        return constituent_loading_summary(uci,hbn,constituent,start_year,end_year,time_step=time_step,temporal_grouping='month')
    else:
        return constituent_loading_summary(uci,hbn,constituent,start_year,end_year,time_step=time_step)

def constituent_loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,time_step = 5,temporal_grouping = None,agg_func = 'mean',simulation_period = None,aggregation_period = None):
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
    time_step : int, optional
        HBN time code (4=monthly, 5=yearly).  Ignored when *simulation_period*
        is provided.
    temporal_grouping : str or None, optional
        Legacy temporal grouping for output.  Ignored when *aggregation_period*
        is provided.  One of:
        - None: aggregate over all time (overall summary)
        - 'month': group by calendar month
        - 'year': group by year
        - 'season': group by meteorological season (DJF, MAM, JJA, SON)
    agg_func : str or callable
        Aggregation function applied to 'value' column. Default 'mean'.
        Examples: 'mean', 'sum', 'max', 'min', 'median', 'std'
    simulation_period : str or None
        Resolution of model output: 'hourly', 'daily', 'monthly', 'yearly'.
        When provided this takes precedence over *time_step*.
    aggregation_period : str or None
        Period over which to aggregate: 'monthly', 'yearly', 'simulation', or
        ``None`` (same as *simulation_period*, i.e. no temporal aggregation).
        Must be ≥ *simulation_period*.  When provided this takes precedence
        over *temporal_grouping*.

    Returns
    -------
    pd.DataFrame
        Columns: [OPERATION, OPNID, value] plus temporal grouping column if specified.
    """
    # ---- resolve new-style period parameters --------------------------------
    if simulation_period is not None:
        validate_periods(simulation_period, aggregation_period)
        time_step = simulation_period_to_time_step(simulation_period)
        temporal_grouping = aggregation_period_to_temporal_grouping(
            simulation_period, aggregation_period
        )
    # -------------------------------------------------------------------------

    df = get_constituent_loading(uci,hbn,constituent,time_step=time_step)
    df = df.loc[(df['datetime'].dt.year >= start_year) & (df['datetime'].dt.year <= end_year)]
    group_cols = ['OPERATION','OPNID']
    if temporal_grouping == 'month':
        df['month'] = df['datetime'].dt.month
        group_cols = ['month'] + group_cols
    elif temporal_grouping == 'year':
        df['year'] = df['datetime'].dt.year
        group_cols = ['year'] + group_cols
    elif temporal_grouping == 'season':
        df['season'] = df['datetime'].dt.month.map(
            {12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',
             6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'})
        group_cols = ['season'] + group_cols
    elif temporal_grouping is not None:
        raise ValueError(f"temporal_grouping must be None, 'month', 'year', or 'season', got '{temporal_grouping}'")
    df = df.groupby(group_cols)['value'].agg(agg_func).reset_index()
    return df

def average_annual_constituent_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100):
    return constituent_loading_summary(uci,hbn,constituent,start_year,end_year,time_step=5)

def average_monthly_constituent_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100):
    return constituent_loading_summary(uci,hbn,constituent,start_year,end_year,time_step=4,temporal_grouping='month')

def _aggregate_catchment_loading(df,by_landcover = False,group_prefix = None):
    if group_prefix is None:
        group_prefix = []
    if by_landcover:
        df = df.groupby(group_prefix + ['TVOLNO','landcover','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    else:
        df = df.groupby(group_prefix + ['TVOLNO','constituent','catchment_area'])[['load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['catchment_area']
    return df


def _aggregate_catchment_by_metzone(df, uci, group_prefix=None):
    """Aggregate catchment loading grouped by meteorological zone."""
    if group_prefix is None:
        group_prefix = []
    # Attach metzone from opnid_dict
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

    grp = group_prefix + ['TVOLNO', 'metzone', 'constituent']
    df = df.groupby(grp)[['landcover_area', 'load']].sum().reset_index()
    df['loading_rate'] = df['load'] / df['landcover_area']
    return df


def _aggregate_catchment_by_landcover_group(df, landcover_names, group_prefix=None):
    """Aggregate catchment loading for a user-defined subset of landcovers.

    Only rows whose *landcover* value appears in *landcover_names* are kept.
    Those rows are then summed per catchment (like ``by_landcover=False`` but
    restricted to the given subset).
    """
    if group_prefix is None:
        group_prefix = []
    df = df.loc[df['landcover'].isin(landcover_names)].copy()
    grp = group_prefix + ['TVOLNO', 'constituent']
    df = df.groupby(grp)[['landcover_area', 'load']].sum().reset_index()
    df['loading_rate'] = df['load'] / df['landcover_area']
    return df

def average_annual_catchment_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False):
    return catchment_loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,by_landcover=by_landcover)

def average_monthly_catchment_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False):  
    return catchment_loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,by_landcover=by_landcover,temporal_grouping='month')

def catchment_loading_summary(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False,temporal_grouping = None,agg_func = 'mean',simulation_period = None,aggregation_period = None,spatial_grouping = None):
    """
    Aggregate catchment loading with flexible temporal and spatial grouping.

    Parameters
    ----------
    uci : UCI object
    hbn : HBN object
    constituent : str
        Constituent name (e.g. 'TP', 'TSS', 'Q')
    start_year, end_year : int
        Year range to filter
    by_landcover : bool
        If True, group by landcover type.  Ignored when *spatial_grouping* is
        provided.
    temporal_grouping : str or None
        Legacy temporal grouping: None (overall), 'month', 'year', 'season'.
        Ignored when *aggregation_period* is provided.
    agg_func : str or callable
        Aggregation function. Default 'mean'.
        Examples: 'mean', 'sum', 'max', 'min', 'median', 'std'
    simulation_period : str or None
        Resolution of model output.  See :func:`constituent_loading_summary`.
    aggregation_period : str or None
        Period over which to aggregate.  See :func:`constituent_loading_summary`.
    spatial_grouping : str, list of str, or None
        Categorical/spatial dimension(s) to group by.  Recognised values:

        * ``None`` – aggregate to a single value per catchment (default).
        * ``'landcover'`` – break out by landcover type (equivalent to
          ``by_landcover=True``).
        * ``'metzone'`` – break out by meteorological zone.
        * A list of landcover names – group those landcovers together.

    Returns
    -------
    pd.DataFrame
    """
    # ---- resolve new-style period parameters --------------------------------
    if simulation_period is not None:
        validate_periods(simulation_period, aggregation_period)
        time_step = simulation_period_to_time_step(simulation_period)
        temporal_grouping = aggregation_period_to_temporal_grouping(
            simulation_period, aggregation_period
        )
    else:
        time_step = 4 if temporal_grouping in ['month', 'season'] else 5

    # ---- resolve spatial_grouping vs by_landcover ---------------------------
    if spatial_grouping is not None:
        by_landcover = False  # spatial_grouping takes precedence

    df = constituent_loading_summary(uci,hbn,constituent,start_year,end_year,time_step=time_step,temporal_grouping=temporal_grouping,agg_func=agg_func)
    df = _join_catchments(df,uci,constituent)

    group_prefix = [temporal_grouping] if temporal_grouping is not None else []
    base_cols = ['constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']
    if temporal_grouping is not None:
        base_cols = [temporal_grouping] + base_cols
    df = df[df.columns.intersection(base_cols)]

    # ---- apply spatial grouping ---------------------------------------------
    if spatial_grouping == 'landcover':
        return _aggregate_catchment_loading(df, by_landcover=True, group_prefix=group_prefix)
    elif spatial_grouping == 'metzone':
        return _aggregate_catchment_by_metzone(df, uci, group_prefix=group_prefix)
    elif isinstance(spatial_grouping, list):
        return _aggregate_catchment_by_landcover_group(df, spatial_grouping, group_prefix=group_prefix)
    else:
        return _aggregate_catchment_loading(df, by_landcover=by_landcover, group_prefix=group_prefix)



def _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids = None,drainage_area = None):
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if drainage_area is None:
        df['watershed_area'] = uci.network.drainage_area(reach_ids,upstream_reach_ids)
    else:
        df['watershed_area'] = drainage_area
    return df

def average_annual_watershed_loading(uci,hbn,constituent,reach_ids, upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
    return watershed_loading_summary(uci,hbn,constituent,reach_ids,upstream_reach_ids=upstream_reach_ids,start_year=start_year,end_year=end_year,by_landcover=by_landcover,drainage_area=drainage_area)

def average_monthly_watershed_loading(uci,hbn,constituent,reach_ids, upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
    return watershed_loading_summary(uci,hbn,constituent,reach_ids,upstream_reach_ids=upstream_reach_ids,start_year=start_year,end_year=end_year,by_landcover=by_landcover,drainage_area=drainage_area,temporal_grouping='month')

def watershed_loading_summary(uci,hbn,constituent,reach_ids,upstream_reach_ids = None,start_year = 1996,end_year = 2100,by_landcover = False,drainage_area = None,temporal_grouping = None,agg_func = 'mean',simulation_period = None,aggregation_period = None,spatial_grouping = None):
    """
    Aggregate watershed loading with flexible temporal and spatial grouping.

    Parameters
    ----------
    uci : UCI object
    hbn : HBN object
    constituent : str
        Constituent name (e.g. 'TP', 'TSS', 'Q')
    reach_ids : list
        Reach IDs defining the watershed outlet
    upstream_reach_ids : list, optional
        Upstream boundary reach IDs
    start_year, end_year : int
        Year range to filter
    by_landcover : bool
        If True, group by landcover type.  Ignored when *spatial_grouping* is
        provided.
    drainage_area : float, optional
        Custom drainage area. If None, calculated from network.
    temporal_grouping : str or None
        Legacy temporal grouping: None (overall), 'month', 'year', 'season'.
        Ignored when *aggregation_period* is provided.
    agg_func : str or callable
        Aggregation function. Default 'mean'.
        Examples: 'mean', 'sum', 'max', 'min', 'median', 'std'
    simulation_period : str or None
        Resolution of model output.  See :func:`constituent_loading_summary`.
    aggregation_period : str or None
        Period over which to aggregate.  See :func:`constituent_loading_summary`.
    spatial_grouping : str, list of str, or None
        Categorical/spatial dimension(s) to group by.  See
        :func:`catchment_loading_summary` for recognised values.

    Returns
    -------
    pd.DataFrame
    """
    # ---- resolve new-style period parameters --------------------------------
    if simulation_period is not None:
        validate_periods(simulation_period, aggregation_period)
        temporal_grouping = aggregation_period_to_temporal_grouping(
            simulation_period, aggregation_period
        )

    df = catchment_loading_summary(uci,hbn,constituent,start_year=start_year,end_year=end_year,by_landcover=by_landcover,temporal_grouping=temporal_grouping,agg_func=agg_func,simulation_period=simulation_period,aggregation_period=aggregation_period,spatial_grouping=spatial_grouping)
    df = _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids,drainage_area)

    group_prefix = [temporal_grouping] if temporal_grouping is not None else []
    ws_area = df['watershed_area'].iloc[0] if len(df) > 0 else None

    if spatial_grouping == 'landcover' or (spatial_grouping is None and by_landcover):
        df = df.groupby(group_prefix + ['TVOLNO','landcover','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    elif spatial_grouping == 'metzone':
        grp = group_prefix + ['metzone', 'constituent']
        df = df.groupby(grp)[['load']].sum().reset_index()
        df['watershed_area'] = ws_area
        df['loading_rate'] = df['load'] / df['watershed_area']
    elif isinstance(spatial_grouping, list):
        grp = group_prefix + ['constituent']
        df = df.groupby(grp)[['load']].sum().reset_index()
        df['watershed_area'] = ws_area
        df['loading_rate'] = df['load'] / df['watershed_area']
    else:
        grp = group_prefix + ['constituent']
        df = df.groupby(grp)[['load']].sum().reset_index()
        df['watershed_area'] = ws_area
        df['loading_rate'] = df['load']/df['watershed_area']

    return df

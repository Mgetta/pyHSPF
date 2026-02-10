# -*- coding: utf-8 -*-
"""
Constituent loading reports.

Contains functions for calculating loading rates and yields.
"""
import pandas as pd

from .. import helpers
from .utils import weighted_describe


LOADING_MAP = {
    'Q': [{'t_opn': 'PERLND',
           't_con': 'PERO',
           't_code': 'yearly',
           'activity': 'PWATER'}],
    'TSS': [{'t_opn': 'PERLND',
             't_con': 'SOSED',
             't_code': 'yearly',
             'activity': 'SEDMNT'},
            {'t_opn': 'IMPLND',
             't_con': 'SOSED',
             't_code': 'yearly',
             'activity': 'SEDMNT'}]
}


def avg_subwatershed_loading(constituent, t_code, uci, hbn):
    """Calculate average subwatershed loading.
    
    Args:
        constituent: Constituent name
        t_code: Time code
        uci: UCI object
        hbn: HBN interface object
    """
    dfs = []
    for t_opn in ['PERLND', 'IMPLND']:
        t_cons = helpers.get_tcons(constituent, t_opn, 'lb')
        df = sum([hbn.get_multiple_timeseries(t_opn=t_opn,
                                              t_con=t_con,
                                              t_code=t_code) for t_con in t_cons])
        if constituent == 'TSS':
            df = df * 2000

        df = df.T.reset_index()
        df.loc[:, 'SVOL'] = t_opn
        df = df.rename(columns={'index': 'OPNID'})
        dfs.append(df)

    df = pd.concat(dfs)
    df.set_index(['SVOL', 'OPNID'], inplace=True)

    subwatersheds = uci.network.subwatersheds()

    loading_rates = []
    for catchment_id in set(subwatersheds.index):
        subwatershed = subwatersheds.loc[catchment_id].set_index(['SVOL', 'SVOLNO'])
        loading_rates.append(df.loc[subwatershed.index].sum().agg('mean') / subwatershed['AFACTR'].sum())


def monthly_avg_constituent_loading(constituent, uci, hbn):
    """Calculate monthly average constituent loading.
    
    Args:
        constituent: Constituent name
        uci: UCI object
        hbn: HBN interface object
        
    Returns:
        DataFrame with monthly loading
    """
    dfs = []
    for t_opn in ['PERLND', 'IMPLND']:
        t_cons = helpers.get_tcons(constituent, t_opn, 'lb')
        df = sum([hbn.get_multiple_timeseries(t_opn=t_opn,
                                              t_con=t_con,
                                              t_code='monthly') for t_con in t_cons])
        df = df.groupby(df.index.month).mean().T.reset_index()
        if constituent == 'TSS':
            df = df * 2000

        df.loc[:, 'SVOL'] = t_opn
        df = df.rename(columns={'index': 'OPNID'})
        dfs.append(df)

    df = pd.concat(dfs)

    subwatersheds = uci.network.subwatersheds().reset_index()

    df = pd.merge(subwatersheds, df, left_on=['SVOL', 'SVOLNO'], right_on=['SVOL', 'OPNID'], how='left')
    return df


def monthly_avg_subwatershed_loading(constituent, month, uci, hbn):
    """Calculate monthly average subwatershed loading.
    
    Args:
        constituent: Constituent name
        month: Month number
        uci: UCI object
        hbn: HBN interface object
        
    Returns:
        DataFrame with monthly subwatershed loading
    """
    df = monthly_avg_constituent_loading(constituent, uci, hbn)
    df = df.groupby(df['TVOLNO'])[[month, 'AFACTR']].apply(lambda x: weighted_describe(x, month, 'AFACTR')).droplevel(1)
    return df


def monthly_avg_watershed_loading(constituent, reach_ids, month, uci, hbn, by_landcover=False):
    """Calculate monthly average watershed loading.
    
    Args:
        constituent: Constituent name
        reach_ids: List of reach IDs
        month: Month number
        uci: UCI object
        hbn: HBN interface object
        by_landcover: Whether to group by landcover
        
    Returns:
        DataFrame with monthly watershed loading
    """
    df = monthly_avg_constituent_loading(constituent, uci, hbn)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if by_landcover:
        df = df.groupby(df['LSID'])[[month, 'AFACTR']].apply(lambda x: weighted_describe(x, month, 'AFACTR')).droplevel(1)
    else:
        df = weighted_describe(df, month, 'AFACTR')

    return df


def ann_avg_constituent_loading(constituent, uci, hbn):
    """Calculate annual average constituent loading.
    
    Args:
        constituent: Constituent name
        uci: UCI object
        hbn: HBN interface object
        
    Returns:
        DataFrame with annual loading
    """
    from .phosphorous import total_phosphorous
    
    if constituent == 'TP':
        df = total_phosphorous(uci, hbn, 5).mean().reset_index()
        df.loc[:, 'OPN'] = 'PERLND'
        df.columns = ['OPNID', constituent, 'SVOL']

    else:
        dfs = []
        for t_opn in ['PERLND', 'IMPLND']:
            t_cons = helpers.get_tcons(constituent, t_opn)
            df = sum([hbn.get_multiple_timeseries(t_opn=t_opn,
                                                  t_con=t_con,
                                                  t_code='yearly') for t_con in t_cons]).mean().reset_index()
            df.loc[:, 'OPN'] = t_opn
            df.columns = ['OPNID', constituent, 'SVOL']
            dfs.append(df)

        df = pd.concat(dfs)
        if constituent == 'TSS':
            df[constituent] = df[constituent] * 2000

    subwatersheds = uci.network.subwatersheds().reset_index()

    df = pd.merge(subwatersheds, df, left_on=['SVOL', 'SVOLNO'], right_on=['SVOL', 'OPNID'], how='left')
    return df


def ann_avg_subwatershed_loading(constituent, uci, hbn):
    """Calculate annual average subwatershed loading.
    
    Args:
        constituent: Constituent name
        uci: UCI object
        hbn: HBN interface object
        
    Returns:
        DataFrame with annual subwatershed loading
    """
    df = ann_avg_constituent_loading(constituent, uci, hbn)
    df = df.groupby(df['TVOLNO'])[[constituent, 'AFACTR']].apply(lambda x: weighted_describe(x, constituent, 'AFACTR')).droplevel(1)
    return df


def ann_avg_watershed_loading(constituent, reach_ids, uci, hbn, by_landcover=False):
    """Calculate annual average watershed loading.
    
    Args:
        constituent: Constituent name
        reach_ids: List of reach IDs
        uci: UCI object
        hbn: HBN interface object
        by_landcover: Whether to group by landcover
        
    Returns:
        DataFrame with annual watershed loading
    """
    reach_ids = [item for sublist in [uci.network._upstream(reach_id) for reach_id in reach_ids] for item in sublist]
    df = ann_avg_constituent_loading(constituent, uci, hbn)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if by_landcover:
        df = df.groupby(df['LSID'])[[constituent, 'AFACTR']].apply(lambda x: weighted_describe(x, constituent, 'AFACTR')).droplevel(1)
    else:
        df = weighted_describe(df, constituent, 'AFACTR')

    return df


def yield_flow(uci, hbn, constituent, reach_id):
    """Calculate flow yield.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        reach_id: Reach ID
    """
    hbn.get_rchres_data('Q', reach_id, 'cfs', 'yearly') / uci.network.drainage_area(reach_id)


def yield_sediment(uci, hbn, constituent, reach_id):
    """Calculate sediment yield.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        reach_id: Reach ID
    """
    hbn.get_rchres_data('TSS', reach_id, 'lb', 'yearly').mean() * 2000 / uci.network.drainage_area(reach_id)


def avg_ann_yield(uci, hbn, constituent, reach_ids):
    """Calculate average annual yield.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        reach_ids: List of reach IDs
        
    Returns:
        Series with average annual yield
    """
    _reach_ids = [uci.network._upstream(reach) for reach in reach_ids]
    _reach_ids = list(set([num for row in _reach_ids for num in row]))
    subwatersheds = uci.network.subwatersheds().loc[_reach_ids]
    area = subwatersheds['AFACTR'].sum()

    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    df = hbn.get_reach_constituent(constituent, reach_ids, 5, unit=units).mean()

    return df / area


def loading(uci, hbn, constituent, t_code=5):
    """Calculate loading for a constituent.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        t_code: Time code
        
    Returns:
        DataFrame with loading
    """
    from .phosphorous import total_phosphorous
    
    if constituent == 'TP':
        loads = total_phosphorous(uci, hbn, t_code=t_code)
    else:
        loads = hbn.get_perlnd_constituent(constituent, t_code, 'lb')

        if constituent == 'TSS':
            loads = loads * 2000

    return loads


def subwatershed_loading(uci, hbn, constituent, t_code, group_landcover=True, as_load=True):
    """Calculate subwatershed loading.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        t_code: Time code
        group_landcover: Whether to group by landcover
        as_load: Whether to return as load
        
    Returns:
        DataFrame with subwatershed loading
    """
    loads = loading(uci, hbn, constituent, t_code)

    subwatersheds = uci.network.subwatersheds()
    perlnds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND'].reset_index()

    total = loads[perlnds['SVOLNO'].to_list()]
    total = total.mul(perlnds['AFACTR'].values, axis=1)
    total = total.transpose()
    total['reach_id'] = perlnds['TVOLNO'].values
    total['landcover'] = uci.table('PERLND', 'GEN-INFO').loc[total.index, 'LSID'].to_list()
    total['area'] = perlnds['AFACTR'].to_list()
    total = total.reset_index().set_index(['index', 'landcover', 'area', 'reach_id']).transpose()
    total.columns.names = ['perlnd_id', 'landcover', 'area', 'reach_id']

    if group_landcover:
        total.columns = total.columns.droplevel(['landcover', 'perlnd_id'])
        total = total.T.reset_index().groupby('reach_id').sum().reset_index().set_index(['reach_id', 'area']).T

    if not as_load:
        total = total.div(total.columns.get_level_values('area').values, axis=1)

    total.index = pd.to_datetime(total.index)
    return total

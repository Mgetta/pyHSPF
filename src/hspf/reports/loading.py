# -*- coding: utf-8 -*-
"""
Constituent loading reports — catchment and watershed edge-of-field loading.
"""
import pandas as pd

from hspf.reports.phosphorus import total_phosphorous


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
    df = get_constituent_loading(uci,hbn,constituent,time_step=time_step)
    df = df.loc[(df['datetime'].dt.year >= start_year) & (df['datetime'].dt.year <= end_year)]
    group_cols = ['OPERATION','OPNID']
    if group_by_month:
        df['month'] = df['datetime'].dt.month
        group_cols = ['month'] + group_cols
    df = df.groupby(group_cols)['value'].mean().reset_index()
    return df

def average_annual_constituent_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100):
    return _average_constituent_loading(uci,hbn,constituent,start_year,end_year,time_step=5)

def average_monthly_constituent_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100):
    return _average_constituent_loading(uci,hbn,constituent,start_year,end_year,time_step=4,group_by_month=True)

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

def average_annual_catchment_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False):
    df = average_annual_constituent_loading(uci,hbn,constituent,start_year,end_year)    
    df = _join_catchments(df,uci,constituent)
    df = df[['constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]
    return _aggregate_catchment_loading(df,by_landcover)

def average_monthly_catchment_loading(uci,hbn,constituent,start_year = 1996,end_year = 2100,by_landcover = False):  
    df = average_monthly_constituent_loading(uci,hbn,constituent,start_year,end_year)    
    df = _join_catchments(df,uci,constituent)
    df = df[['month','constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]
    return _aggregate_catchment_loading(df,by_landcover,group_prefix=['month'])



def _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids = None,drainage_area = None):
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if drainage_area is None:
        df['watershed_area'] = uci.network.drainage_area(reach_ids,upstream_reach_ids)
    else:
        df['watershed_area'] = drainage_area
    return df

def average_annual_watershed_loading(uci,hbn,constituent,reach_ids, upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
    df = average_annual_catchment_loading(uci,hbn,constituent,by_landcover = by_landcover,start_year = start_year,end_year = end_year)
    df = _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids,drainage_area)

    if by_landcover:
        df = df.groupby(['landcover','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    else:
        df = df.groupby(['constituent','watershed_area'])[['load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['watershed_area']

    return df

def average_monthly_watershed_loading(uci,hbn,constituent,reach_ids, upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
    df = average_monthly_catchment_loading(uci,hbn,constituent,by_landcover = by_landcover,start_year = start_year,end_year = end_year)
    df = _filter_to_watershed(df,uci,reach_ids,upstream_reach_ids,drainage_area)

    if by_landcover:
        df = df.groupby(['month','TVOLNO','landcover','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    else:
        df = df.groupby(['month','constituent','watershed_area'])['load'].sum().reset_index()
        df['loading_rate'] = df['load']/df['watershed_area']
    return df

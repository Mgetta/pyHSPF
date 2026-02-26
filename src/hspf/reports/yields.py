# -*- coding: utf-8 -*-
"""
Landscape yield reports — constituent loads and yields at reach outlets.
"""


def _constituent_load(hbn,constituent,time_step = 5):
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    df = hbn.get_rchres_output(constituent,units,time_step)

    return df

def constituent_load(hbn,constituent,reach_ids,time_step = 5,upstream_reach_ids = None):
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    upstream_load = 0
    if upstream_reach_ids is not None:
        upstream_load = constituent_load(hbn,constituent,upstream_reach_ids,time_step)

    df = hbn.get_reach_constituent(constituent,reach_ids,time_step,unit =units) - upstream_load

    return df


def _constituent_yield(uci,hbn,constituent,time_step = 5):
    df = _constituent_load(hbn,constituent,time_step)

    areas = [uci.network.drainage_area([reach_id]) for reach_id in df.columns]
    return df/areas

def constituent_yield(uci,hbn,constituent,reach_ids,time_step = 5,upstream_reach_ids = None,drainage_area = None):

    if drainage_area is None:
        drainage_area = uci.network.drainage_area(reach_ids,upstream_reach_ids)

    df = constituent_load(hbn,constituent,reach_ids,time_step,upstream_reach_ids)/drainage_area
        
    return df

def average_annual_yield(uci,hbn,constituent,reach_ids,upstream_reach_ids = None,start_year = 1996,end_year = 2100,drainage_area = None): 
    df = constituent_yield(uci,hbn,constituent,reach_ids,5,upstream_reach_ids,drainage_area)
    df = df.loc[(df.index.year >= start_year) & (df.index.year <= end_year)].mean()
    return df

def average_monthly_yield(uci,hbn,constituent,reach_ids,upstream_reach_ids = None,start_year = 1996,end_year = 2100,drainage_area = None): 
    df = constituent_yield(uci,hbn,constituent,reach_ids,4,upstream_reach_ids,drainage_area)
    df = df.loc[(df.index.year >= start_year) & (df.index.year <= end_year)]
    df = df.groupby(df.index.month).mean()
    return df

# -*- coding: utf-8 -*-
"""
Legacy loading functions — older implementations kept for backward compatibility.
"""
import numpy as np
import pandas as pd
from hspf import helpers

from hspf.reports.phosphorus import total_phosphorous
from hspf.reports.utils import weighted_describe


def avg_subwatershed_loading(constituent,t_code,uci,hbn):
    dfs = []
    for t_opn in ['PERLND','IMPLND']:
        t_cons = helpers.get_tcons(constituent,t_opn,'lb')
        df = sum([hbn.get_multiple_timeseries(t_opn=t_opn, 
                                            t_con= t_con, 
                                            t_code = t_code) for t_con in t_cons])
        if constituent == 'TSS':
            df*2000
            
        df = df.T.reset_index()
        df.loc[:,'SVOL'] = t_opn
        df = df.rename(columns = {'index':'OPNID'})
        dfs.append(df)
    
    df = pd.concat(dfs)
    df.set_index(['SVOL','OPNID'],inplace=True)
    
    subwatersheds = uci.network.subwatersheds()
    
    
    
    loading_rates = []
    for catchment_id in set(subwatersheds.index):
        subwatershed = subwatersheds.loc[catchment_id].set_index(['SVOL','SVOLNO'])
        loading_rates.append(df.loc[subwatershed.index].sum().agg(agg_func)/subwatershed['AFACTR'].sum())


def monthly_avg_constituent_loading(constituent,uci,hbn):
    dfs = []
    for t_opn in ['PERLND','IMPLND']:
        t_cons = helpers.get_tcons(constituent,t_opn,'lb')
        df = sum([hbn.get_multiple_timeseries(t_opn=t_opn, 
                                            t_con= t_con, 
                                            t_code = 'monthly') for t_con in t_cons])
        df = df.groupby(df.index.month).mean().T.reset_index() 
        if constituent == 'TSS':
            df*2000
        
        df.loc[:,'SVOL'] = t_opn
        df = df.rename(columns = {'index':'OPNID'})
        dfs.append(df)
        
    df = pd.concat(dfs)

    
    subwatersheds = uci.network.subwatersheds().reset_index()
       
    df = pd.merge(subwatersheds,df,left_on = ['SVOL','SVOLNO'], right_on=['SVOL','OPNID'],how='left')
    return df  

def monthly_avg_subwatershed_loading(constituent,month,uci,hbn):
    df = monthly_avg_constituent_loading(constituent,uci,hbn)
    df = df.groupby(df['TVOLNO'])[[month,'AFACTR']].apply(lambda x: weighted_describe(x,month,'AFACTR')).droplevel(1)
    return df

def monthly_avg_watershed_loading(constituent,reach_ids,month,uci,hbn, by_landcover = False):
    df = monthly_avg_constituent_loading(constituent,uci,hbn)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if by_landcover:
        df = df.groupby(df['LSID'])[[month,'AFACTR']].apply(lambda x: weighted_describe(x,month,'AFACTR')).droplevel(1)
    else:
        
        df = weighted_describe(df,month,'AFACTR')
    
    return df


def ann_avg_constituent_loading(constituent,uci,hbn):
    
    if constituent == 'TP':
        df = total_phosphorous(uci,hbn,5).mean().reset_index()
        df.loc[:,'OPN'] = 'PERLND'
        df.columns = ['OPNID',constituent,'SVOL'] 
    
    else:
        dfs = []
        for t_opn in ['PERLND','IMPLND']:
            t_cons = helpers.get_tcons(constituent,t_opn)
            df = sum([hbn.get_multiple_timeseries(t_opn=t_opn, 
                                                t_con= t_con, 
                                                t_code = 'yearly') for t_con in t_cons]).mean().reset_index() 
            df.loc[:,'OPN'] = t_opn
            df.columns = ['OPNID',constituent,'SVOL']    
            dfs.append(df)
            
        df = pd.concat(dfs)
        if constituent == 'TSS':
            df[constituent] = df[constituent]*2000
    
    subwatersheds = uci.network.subwatersheds().reset_index()
       
    df = pd.merge(subwatersheds,df,left_on = ['SVOL','SVOLNO'], right_on=['SVOL','OPNID'],how='left')
    return df  

def ann_avg_subwatershed_loading(constituent,uci,hbn):
    df = ann_avg_constituent_loading(constituent,uci,hbn)
    df = df.groupby(df['TVOLNO'])[[constituent,'AFACTR']].apply(lambda x: weighted_describe(x,constituent,'AFACTR')).droplevel(1)
    return df

def ann_avg_watershed_loading(constituent,reach_ids,uci,hbn, by_landcover = False):
    reach_ids = [item for sublist in [uci.network._upstream(reach_id) for reach_id in reach_ids] for item in sublist]
    df = ann_avg_constituent_loading(constituent,uci,hbn)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if by_landcover:
        df = df.groupby(df['LSID'])[[constituent,'AFACTR']].apply(lambda x: weighted_describe(x,constituent,'AFACTR')).droplevel(1)
    else:
        
        df = weighted_describe(df,constituent,'AFACTR')
    
    return df

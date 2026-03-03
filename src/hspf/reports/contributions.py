# -*- coding: utf-8 -*-
"""
Channel contributions and allocation reports.
"""
import pandas as pd

from hspf.reports.loading import get_catchment_loading

allocation_selector = {'Q': {'input': ['IVOL'],
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

def channel_inflows(constituent,uci,hbn,t_code,reach_ids = None):
    load_in =  sum([hbn.get_multiple_timeseries('RCHRES',
                                       t_code,
                                       t_cons,
                                       opnids = reach_ids)
               for t_cons in allocation_selector[constituent]['input']])
    
    if constituent == 'TSS':
        load_in = load_in*2000
    
    return load_in

def channel_outflows(constituent,uci,hbn,t_code,reach_ids = None):
    load_out =  sum([hbn.get_multiple_timeseries('RCHRES',
                                       t_code,
                                       t_cons,
                                       opnids = reach_ids)
               for t_cons in allocation_selector[constituent]['output']])
    if constituent == 'TSS':
        load_out = load_out*2000
    return load_out

def channel_fate(constituent,uci,hbn,t_code,reach_ids = None):
    load_in = channel_inflows(constituent,uci,hbn,t_code,reach_ids)
    load_out = channel_outflows(constituent,uci,hbn,t_code,reach_ids)
    return load_out/load_in


def local_loading(constituent,uci,hbn,t_code,reach_ids = None):
    load_in = channel_inflows(constituent,uci,hbn,t_code,reach_ids)
    load_out = channel_outflows(constituent,uci,hbn,t_code,reach_ids)    
    df = pd.DataFrame({reach_id: load_in[reach_id] - load_out[uci.network.upstream(reach_id)].sum(axis=1) for reach_id in load_in.columns})
    return df



def catchment_contributions(uci,hbn,constituent,target_reach_id, landcover = None):
    p = uci.network.paths(target_reach_id)
    p[target_reach_id] = [target_reach_id]
    fate = channel_fate(constituent,uci,hbn,5)
    fate_factors = pd.concat([fate[v].prod(axis=1) for k,v in p.items()],axis=1)
    fate_factors.columns = list(p.keys())

    fate_factors = fate_factors.reset_index().melt(id_vars = 'index')

    df = get_catchment_loading(uci,hbn,constituent,by_landcover = True)
    df = pd.merge(df,fate_factors,left_on = ['TVOLNO','index'],right_on = ['variable','index'])
    
    df['contribution'] = df['value']*df['load']

    target_load = channel_outflows(constituent,uci,hbn,5,[target_reach_id])
    
    df = pd.merge(df,target_load.reset_index().melt(id_vars='index',var_name = 'target_reach',value_name = 'target_load'),left_on='index',right_on='index')
    df['contribution_perc'] = df['contribution']/(df['target_load'])*100
    
    df = df.groupby(['TVOLNO','landcover','landcover_area'])[['load','contribution','contribution_perc','target_load']].mean().reset_index()

    if landcover is not None:
        df = df.loc[df['landcover'] == landcover]

    else:
        df = df.groupby(['TVOLNO',])[['landcover_area','load','contribution','contribution_perc']].sum().reset_index()

    return df

def total_contributions(constituent,uci,hbn,target_reach_id, as_percent = True):
    p = uci.network.paths(target_reach_id)
    p[target_reach_id] = [target_reach_id]
    fate = channel_fate(constituent,uci,hbn,5)
    loads = local_loading(constituent,uci,hbn,5)
    fate_factors = pd.concat([fate[v].prod(axis=1) for k,v in p.items()],axis=1)
    fate_factors.columns = list(p.keys())
    loads = loads[loads.columns.intersection(fate_factors.columns)]
    contribution = loads[fate_factors.columns].mul(fate_factors.values)
    
    target_load = channel_outflows(constituent,uci,hbn,5,[target_reach_id])
    
    
    df = contribution.mean().to_frame().reset_index()
    df.columns = ['TVOLNO','contribution']

    df['load'] = loads.mean().values
    df['contribution_perc'] = (contribution.div(target_load.values)*100).mean().values
    return df[['TVOLNO','load','contribution','contribution_perc']]

# -*- coding: utf-8 -*-
"""
Created on Mon Apr 11 08:26:04 2022

@author: mfratki
"""
import numpy as np
import pandas as pd
from hspf import helpers
from pathlib import Path

#timeseries_catalog = pd.read_csv(Path(__file__).parent/'TIMESERIES_CATALOG.csv')

#ts_catalog = pd.read_csv('C:/Users/mfratki/Documents/GitHub/hspf_tools/parser/TIMESERIES_CATALOG.csv')


class Reports():
    def __init__(self,uci,hbns,wdms):
        self.hbns = hbns
        self.uci = uci
        self.wdms = wdms

#Sediment Reports        
    def scour(self,start_year = '1996',end_year = '2030'):
        return scour(self.hbns,self.uci,start_year = start_year,end_year=end_year)

# Hydrology Reports
    def landcover_area(self):
        return landcover_areas(self.uci)
    
    def annual_water_budget(self,operation):
        assert operation in ['PERLND','RCHRES','IMPLND']
        if operation =='PERLND':
            return annual_perlnd_water_budget(self.uci,self.hbns)
        elif operation == 'IMPLND':
            return annual_implnd_water_budget(self.uci,self.hbns)
        else:
            return annual_reach_water_budget(self.uci,self.hbns)
        
    def watershed_loading(self,constituent,reach_ids,upstream_reach_ids = None,by_landcover = False):
        '''
        Calculate the loading to channels from a watershed.
        
        Parameters
        ----------
        constituent : str
            Constituent to calculate loading for (e.g. 'TP', 'TSS', 'N', 'OP', 'Q', 'TKN')
        reach_ids : list
            List of reach IDs defining the watershed outlet
        upstream_reach_ids : list, optional
            List of reach IDs defining the upstream boundary of the watershed. The default is None.
        by_landcover : bool, optional
            If True, returns loading by landcover type. The default is False.
        '''
        return get_watershed_loading(self.uci,self.hbns,reach_ids,constituent,upstream_reach_ids,by_landcover)
    
    def catchment_loading(self,constituent,by_landcover = False):
        return get_catchment_loading(self.uci,self.hbns,constituent,by_landcover)
    
    def contributions(self,constituent,target_reach_id):
        return total_contributions(constituent,self.uci,self.hbns,target_reach_id)

    def landcover_contributions(self,constituent,target_reach_id,landcover = None):
        return catchment_contributions(self.uci,self.hbns,constituent,target_reach_id)
    
    def ann_avg_subwatershed_loading(self,constituent):
        return ann_avg_subwatershed_loading(constituent,self.uci, self.hbns)
    
    def ann_avg_watershed_loading(self,constituent,reach_ids):
        landcovers = ann_avg_watershed_loading(constituent,reach_ids,self.uci, self.hbns, True)
        total = ann_avg_watershed_loading(constituent,reach_ids,self.uci, self.hbns, False)
        total.index = ['Total']
        total = pd.concat([landcovers,total])
        total['volume'] = total['area']*total[f'weighted_mean_{constituent}']
        total['volume_percent'] = total['volume']/total.loc['Total','volume']*100
        total['area_percent'] = total['area']/total.loc['Total','area']*100
        total['share'] = total['volume_percent']/total['area_percent']
        return total
  
    def ann_avg_yield(self,constituent,reach_ids,upstream_reach_ids = None):
        df= avg_ann_yield(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids)
        return df
    
    def annual_precip(self):
        return avg_annual_precip(self.uci,self.wdms)
    
    def simulated_et(self):
        return simulated_et(self.uci,self.hbns)
    
 

#%% Channel Reports    
def scour(hbn,uci,start_year = '1996',end_year = '2030'):
    # Should eventually create an entire reports module or class indorder to calculate all of the different model checks
    # TODO: Incorporate IMPLNDS
    schematic = uci.table('SCHEMATIC').copy()
    schematic = schematic.astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR':float})
    schematic = schematic[(schematic['SVOL'] == 'PERLND') | (schematic['SVOL'] == 'IMPLND')]
    schematic = schematic[schematic['TVOL'] == 'RCHRES']        
    
    sosed = hbn.get_multiple_timeseries(t_opn = 'PERLND',
                                                     t_con = 'SOSED',
                                                     activity = 'SEDMNT',
                                                     t_code = 'yearly',
                                                     opnids = None)
    sosed = sosed.loc[(sosed.index > start_year) & (sosed.index < end_year)].mean().rename('mean').to_frame()

    sosld =  hbn.get_multiple_timeseries(t_opn = 'IMPLND',
                                             t_con = 'SOSLD',
                                             activity = 'SOLIDS',
                                             t_code = 'yearly',
                                             opnids = None)
    sosld = sosld.loc[(sosld.index > start_year) & (sosld.index < end_year)].mean().rename('mean').to_frame()

    depscr =  hbn.get_multiple_timeseries(t_opn = 'RCHRES',
                                                     t_con = 'DEPSCOURTOT',
                                                     activity = 'SEDTRN',
                                                     t_code = 'yearly',
                                                     opnids = None)
    depscr = depscr.loc[(depscr.index > start_year) & (depscr.index < end_year)].mean().rename('mean').to_frame()

    lakeflag =  uci.table('RCHRES','GEN-INFO').copy()[['RCHID','LKFG']]

    scour_report = []
    # schematic block will have all the possible perlands while sosed only has perlands that were simulated
    # in other words information from sosed is a subset of schematic
    for tvolno in lakeflag.index: #schematic['TVOLNO'].unique():
        reach_load = depscr.loc[tvolno].values[0]
        schem_sub = schematic[schematic['TVOLNO'] == tvolno]
        if len(schem_sub) == 0:
            scour_report.append((tvolno,np.nan,reach_load))
        else:
            #Only consider perlands that wer actually simulated in the model (binary flag in set to 0)
            # Calculate contributions from PERLNDS
            if 'PERLND' in schem_sub['SVOL'].values:
                schem_prlnd = schem_sub[schem_sub['SVOL'] == 'PERLND'].copy()
                sosed_match = [x for x in schem_prlnd['SVOLNO'] if x in sosed.index]
                schem_prlnd = schem_prlnd[schem_prlnd['SVOLNO'].isin(sosed_match)]
                sosed_sub = sosed.loc[sosed_match]
                prlnd_load = np.sum(schem_prlnd['AFACTR'].values*sosed_sub['mean'].values)#lb/yr
            
            # Calculate contributions from IMPLNDS
            if 'IMPLND' in schem_sub['SVOL'].values:
                schem_implnd = schem_sub[schem_sub['SVOL'] == 'IMPLND'].copy()
                sosld_match = [x for x in schem_implnd['SVOLNO'] if x in sosld.index]
                schem_implnd = schem_implnd[schem_implnd['SVOLNO'].isin(sosld_match)]
                sosld_sub = sosld.loc[sosld_match]
                implnd_load = np.sum(schem_implnd['AFACTR'].values*sosld_sub['mean'].values)#lb/yr
            
            watershed_load = prlnd_load + implnd_load
            scour_report.append((tvolno,watershed_load,reach_load))
    
    scour_report = pd.DataFrame(scour_report,columns = ['TVOLNO','nonpoint','depscour'])
    
    scour_report['ratio'] = scour_report['nonpoint']/(scour_report['nonpoint']+np.abs(scour_report['depscour']))
    
    scour_report = pd.merge(lakeflag, scour_report, left_index=True, right_on='TVOLNO').set_index('TVOLNO')
    return scour_report  


def get_catchments(uci,reach_ids):
    # Grab metadata information
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND',:].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR','LSID','metzone','TVOLNO','MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0,pd.NA)
    return landcover
    


#%% Landscape Yields

def yield_flow(uci,hbn,constituent,reach_id):
    hbn.get_rchres_data('Q',reach_id,'cfs','yearly')/uci.network.drainage_area(reach_id)


def yield_sediment(uci,hbn,constituent,reach_id):
    hbn.get_rchres_data('TSS',reach_id,'lb','yearly').mean()*2000/uci.network.drainage_area(reach_id)

def avg_ann_yield(uci,hbn,constituent,reach_ids,upstream_reach_ids = None):
    #reach_ids = uci.network.G.nodes
    
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)
    area = uci.network.drainage_area(reach_ids,upstream_reach_ids)
    
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'
        
    df = hbn.get_reach_constituent(constituent,reach_ids,5,unit =units).mean() # Gross

    return df/area

#%% Catchment and Watershed Loading
 
def landcover_areas(uci):
    df = uci.network.operation_area('PERLND').groupby('LSID').sum()    
    df['percent'] = 100*(df['AFACTR']/df['AFACTR'].sum())
    return df

def catchment_areas(uci):
    df = uci.network.subwatersheds().reset_index()
    df = df.groupby('TVOLNO')['AFACTR'].sum().reset_index()
    df.rename(columns = {'AFACTR':'catchment_area'},inplace = True)
    return df

def get_constituent_loading(uci,hbn,constituent,time_step = 5):

    
    if constituent == 'TP':
        perlnds = total_phosphorous(uci,hbn,t_code=time_step,operation = 'PERLND').reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
        implnds = total_phosphorous(uci,hbn,t_code=time_step,operation = 'IMPLND').reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    else:
        perlnds = hbn.get_perlnd_constituent(constituent,time_step = time_step).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
        implnds = hbn.get_implnd_constituent(constituent,time_step = time_step).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    
    perlnds['OPERATION'] = 'PERLND'
    implnds['OPERATION'] = 'IMPLND'

    df = pd.concat([perlnds,implnds],axis=0)

    #df = df.groupby(['OPNID','OPERATION'])['value'].mean().reset_index()

    
    # units = 'lb/acre'  
    if constituent == 'Q':
        df.loc[:, 'value'] = df['value']/12  # convert to ft/acre/month
        # units = 'ft/acre'
    
    # df['unit'] = units 
    # df.rename(columns = {'index':'datetime','value': 'loading_rate'},inplace = True)
    # df['constituent'] = constituent
    # df['time_step'] = time_step
    # df['year'] = pd.DatetimeIndex(df['datetime']).year
    # df['month'] = pd.DatetimeIndex(df['datetime']).month


    subwatersheds = uci.network.subwatersheds().reset_index()
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'].isin(['PERLND','IMPLND'])]
    areas = catchment_areas(uci)

    df = pd.merge(subwatersheds,df,left_on = ['SVOL','SVOLNO'], right_on=['OPERATION','OPNID'],how='right')
    df = pd.merge(df,areas,left_on = ['TVOLNO'], right_on='TVOLNO',how='left')
    df['load'] = df['value']*df['AFACTR']
    df = df.rename(columns = {'value':'loading_rate', 'AFACTR':'landcover_area','LSID':'landcover'})
    df['constituent'] = constituent
    return df[['index','constituent','TVOLNO','SVOLNO','SVOL','landcover','landcover_area','catchment_area','loading_rate','load']]


def get_catchment_loading(uci,hbn,constituent,by_landcover = False):
    df = get_constituent_loading(uci,hbn,constituent)
    if not by_landcover:
        df = df.groupby(['TVOLNO','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    return df

def get_watershed_loading(uci,hbn,reach_ids,constituent,upstream_reach_ids = None,by_landcover = False):
    reach_ids = uci.network.get_opnids('RCHRES',reach_ids,upstream_reach_ids)

    df = get_constituent_loading(uci,hbn,constituent)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]

    if by_landcover:
        df = df.groupby(['landcover','constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']
    else:
        df = df.groupby(['constituent'])[['landcover_area','load']].sum().reset_index()
        df['loading_rate'] = df['load']/df['landcover_area']

    return df


#%% Contributions
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
    #allocations = loads.mul(loss_factors[loads.columns.get_level_values('reach_id')].values)
    
    target_load = channel_outflows(constituent,uci,hbn,5,[target_reach_id])
    
    
    df = contribution.mean().to_frame().reset_index()
    df.columns = ['TVOLNO','contribution']

    df['load'] = loads.mean().values
    df['contribution_perc'] = (contribution.div(target_load.values)*100).mean().values
    return df[['TVOLNO','load','contribution','contribution_perc']]

#%% LEGACY Catchment Loading (ie. Direct contributions from perlnds/implnds, no losses)
# Q
# Subwatershed Weighted Mean Timeseries Output
# operation = 'PERLND'
# ts_name = 'PERO',
# time_code = 5


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

    
        
def weighted_describe(df, value_col, weight_col):
    weighted_mean = (df[value_col] * df[weight_col]).sum() / df[weight_col].sum()
    weighted_var = ((df[value_col] - weighted_mean) ** 2 * df[weight_col]).sum() / df[weight_col].sum()
    weighted_std = np.sqrt(weighted_var)


    return pd.DataFrame({
        'area' : df[weight_col].sum(),
        f'weighted_mean_{value_col}': [weighted_mean],
        f'weighted_std_{value_col}': [weighted_std]})
    #     'min': [df[value_col].min()],
    #     'max': [df[value_col].max()]
    # })


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


#%% Water Balance
def pevt_balance(mod,operation,opnid):
    extsources = mod.uci.table('EXT SOURCES')
    
    pevt_dsn = mod.uci.get_dsns(operation,opnid,'PEVT').reset_index()
    pevt_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PEVT'),'MFACTOR'].iat[0]
    pevt = mod.wdms.series(pevt_dsn.loc[0,'FILENAME'],pevt_dsn.loc[0,'SVOLNO'])
    
    prec_dsn = mod.uci.get_dsns(operation,opnid,'PREC').reset_index()
    prec_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PREC'),'MFACTOR'].iat[0]
    prec = mod.wdms.series(prec_dsn.loc[0,'FILENAME'],prec_dsn.loc[0,'SVOLNO'])

    df = pd.concat([(prec*prec_mfactor).resample('Y').sum(),
               (pevt*pevt_mfactor).resample('Y').sum()],axis=1)
    df = df[df>0]
    df.columns = ['PREC','PEVT']
    return df


# #simulate ET from perlnds
# taet = hbn.get_multiple_timeseries(t_opn='PERLND', 
#                                    t_con='TAET', 
#                                    t_code = 'monthly', 
#                                    activity = 'PWATER')

# taet = taet.groupby(taet.index.month).mean()

# precip = hbn.get_multiple_timeseries(t_opn='PERLND', 
#                                    t_con='SUPY', 
#                                    t_code = 'monthly', 
#                                    activity = 'PWATER')

# precip = precip.groupby(precip.index.month).mean()



# df = (precip-taet).T.join(uci.opnid_dict['PERLND'])



# precip = cal.model.wdms.series('Nemadji_Met.wdm',1100)
# precip = precip.loc[precip >=0]
# pevt = cal.model.wdms.series('Nemadji_Met.wdm',711)
# pevt = pevt.loc[pevt >=0]

# taet['Operation'] = 'PERLND' # without specifying the opnid, it grabs them all. 
# taet = taet.join(uci.network.operation_area('PERLND'))
# taet['PET'] = taet['EVAP']*taet['AFACTR']/12
# taet = taet.reset_index().rename(columns = {'index' : 'OPNID'})[['OPNID','Operation','PET']]


def simulated_et(uci,hbn):
    
    
    #simulate ET from perlnds
    taet = hbn.get_multiple_timeseries(t_opn='PERLND', 
                                       t_con='TAET', 
                                       t_code = 'yearly', 
                                       activity = 'PWATER').mean().to_frame().rename(columns = {0:'EVAP'})
    taet['Operation'] = 'PERLND' # without specifying the opnid, it grabs them all. 
    taet = taet.join(uci.network.operation_area('PERLND'))
    taet['PET'] = taet['EVAP']*taet['AFACTR']/12
    taet = taet.reset_index().rename(columns = {'index' : 'OPNID'})[['OPNID','Operation','PET']]

    #simulate ET from implnds
    impev = hbn.get_multiple_timeseries(t_opn='IMPLND', 
                                       t_con='IMPEV', 
                                       t_code = 'yearly').mean().to_frame().rename(columns = {0:'EVAP'})
    impev['Operation'] = 'IMPLND' # without specifying the opnid, it grabs them all. 
    impev = impev.join(uci.network.operation_area('IMPLND'))
    impev['PET'] = impev['EVAP']*impev['AFACTR']/12
    impev = impev.reset_index().rename(columns = {'index' : 'OPNID'})[['OPNID','Operation','PET']]
        
    # sum of agwo for each perlnd 
    volev = hbn.get_multiple_timeseries(t_opn='RCHRES', t_con='VOLEV', t_code = 'yearly').mean().to_frame().rename(columns = {0:'PET'})
    volev['Operation'] = 'RCHRES'
    volev = volev.reset_index().rename(columns = {'index' : 'OPNID'})
    
    return pd.concat([taet,impev,volev])
    


def inflows(uci,wdm): 
    # External inflows
    files = uci.table('FILES')
    ext_sources = uci.table('EXT SOURCES')

    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND','IMPLND','RCHRES']))]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    ext_sources = ext_sources[ext_sources['SMEMN'].isin(['ROVL','Flow'])]
    
    if len(ext_sources) == 0:
        inflows = pd.DataFrame(columns = ['OPNID','Operation','ROVL'])
    else:
    
        dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
        dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
        dsns['ROVL'] = pd.concat(dfs,axis=1).resample('Y').sum().mean()
        
        
        inflows = ext_sources.merge(dsns,left_on='SVOLNO',
                          right_on = 'SVOLNO')[['TOPFST','TVOL','ROVL']].rename(columns = {'TOPFST':'OPNID','TVOL':'Operation'})
    return inflows
    
def water_balance(uci,hbn,wdm,reach_ids):
    
    areas = []
    for operation in ['PERLND','IMPLND','RCHRES']:
        area = uci.network.operation_area(operation).reset_index()
        area.loc[:,'Operation'] = operation
        areas.append(area)
    areas = pd.concat(areas).set_index(['Operation','SVOLNO'])
    areas.index.names = ['Operation','OPNID']
        
    #areas = pd.concat([uci.network.operation_area(operation) for operation in ['PERLND','IMPLND','RCHRES']])
    
    pets = simulated_et(uci,hbn)
    _inflows = inflows(uci,wdm)
    precips = avg_annual_precip(uci,wdm)
    precips = precips.set_index(['Operation','OPNID']).join(areas)
    precips['PREC'] = precips['avg_ann_prec'] / 12 * precips['AFACTR']
    precips.reset_index(inplace=True)
    #outlets = uci.network.outlets()    
    rovols = hbn.get_multiple_timeseries(opnids = reach_ids,t_opn='RCHRES', t_con='ROVOL', t_code = 'yearly').mean().to_frame()
    #igwi = hbn.get_multiple_timeseries(t_opn='PERLND', t_con='IGWI', t_code = 'yearly').mean().to_frame()
    #igwi = igwi.join(areas['PERLND'])
    #igwi = igwi[0]/ 12 * igwi['AFACTR']
    
    rows = []
    for outlet in reach_ids:
        precip = 0
        inflow = 0
        pet = 0
        for operation in ['PERLND','IMPLND','RCHRES']:
            opnids = uci.network.get_opnids(operation,outlet)
            precip = precip + precips.loc[(precips['Operation'] == operation) & (precips['OPNID'].isin(opnids))]['PREC'].sum()
            inflow = inflow + _inflows.loc[(_inflows['Operation'] == operation) & (_inflows['OPNID'].isin(opnids))]['ROVL'].sum()
            pet = pet + pets.loc[(pets['Operation'] == operation) & (pets['OPNID'].isin(opnids))]['PET'].sum()
            rovol = rovols.loc[outlet].sum()
        balance = ((precip-pet)-(rovol - inflow))/(precip-pet)*100

        rows.append([outlet,precip,inflow,pet,rovol,balance])
    return pd.DataFrame(rows,columns = ['reach_id','precip','inflow','saet','rovol','balance'])
    

def meteorlogical(uci,wdm,operation,ts_name,time_step = 'Y',opnids = None,):
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM','WDM1',inplace=True)
    
    # Total preciptiation
    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM','WDM1',inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'] == operation) & (ext_sources['SMEMN'] == ts_name)]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
    dfs = [df.loc[df>=0] for df in dfs]
    df = pd.concat(dfs,axis=1).resample(time_step).sum()
    df.columns = dsns['SVOLNO']
    
    df = df[ext_sources['SVOLNO']]
    df.columns = ext_sources['TOPFST']
    
    if opnids is not None:
        df = df[opnids]
        
    return df
    

def avg_annual_precip(uci,wdm):
    #assert(var in ['PREC','WIND','PEVT','ATEM','DEWP','CLOU','SOLAR',])
    # average annual precipitation across for each PERLND, IMPLND, and Reach
    
    
    
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM','WDM1',inplace=True)
    
    # Total preciptiation
    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM','WDM1',inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND','IMPLND','RCHRES'])) & (ext_sources['SMEMN'] == 'PREC')]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
    dfs = [df.loc[df>=0] for df in dfs]
    df = pd.concat(dfs,axis=1).resample('Y').sum().mean()
   
    dsns['avg_ann_prec'] = pd.concat(dfs,axis=1).resample('Y').sum().mean()
    df = ext_sources.merge(dsns,left_on = 'SVOLNO',
                      right_on = 'SVOLNO',
                      how = 'left')
    df = df[['SVOLNO','TVOL','TOPFST','avg_ann_prec']]
    df.rename(columns = {'SVOLNO':'DSN','TVOL':'Operation','TOPFST':'OPNID'}, inplace=True)
    
    return df






#%%
#%%% Other Reports       




def weighted_mean(df,value_col,weight_col):
   weighted_mean = (df[value_col] * df[weight_col]).sum() / df[weight_col].sum()
   return pd.DataFrame({
       'AFACTR' : df[weight_col].sum(),
       value_col: [weighted_mean]})
                        
def annual_weighted_output(uci,hbn,ts_name,operation = 'PERLND',t_code = 5,opnids = None,group_by = None):
    assert (group_by in [None,'landcover','opnid'])
    df = hbn.get_multiple_timeseries(operation,t_code,ts_name,opnids = opnids).mean().reset_index()
    df.columns = ['SVOLNO',ts_name]
    subwatersheds = uci.network.subwatersheds().reset_index()
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'] == operation]
            
          
    df = pd.merge(subwatersheds,df,left_on = 'SVOLNO', right_on='SVOLNO',how='left')
    
    
    if group_by is None:
        df = weighted_mean(df,ts_name,'AFACTR')
    elif group_by == 'landcover':
        df = df.groupby('LSID')[[ts_name,'AFACTR']].apply(lambda x: weighted_mean(x,ts_name,'AFACTR')).droplevel(1)
    elif group_by == 'opnid':
        df = df.groupby(df['SVOLNO'])[[ts_name,'AFACTR']].apply(lambda x: weighted_mean(x,ts_name,'AFACTR')).droplevel(1)
    
    df = df.set_index([df.index,'AFACTR'])
    return df

                        
def monthly_weighted_output(uci,hbn,ts_name,operation = 'PERLND',opnids = None, as_rate = False, by_landcover = True, months = [1,2,3,4,5,6,7,8,9,10,11,12]):
    df = hbn.get_multiple_timeseries(operation,4,ts_name,opnids = opnids) 
    df = df.loc[df.index.month.isin(months)]

    areas = uci.network.operation_area(operation)
    areas.loc[areas.index.intersection(df.columns)]
    df = df[areas.index.intersection(df.columns)]
    
    df = (df.groupby(df.index.month).mean()*areas['AFACTR'])

    if by_landcover:
        df = df.T.groupby(areas['LSID']).sum().T
        if as_rate:
            df = df/areas['AFACTR'].groupby(areas['LSID']).sum().to_list()
    else:
        if as_rate:
            df = df/areas['AFACTR'].sum()

    df.columns.name = ts_name

    return df

def monthly_perlnd_runoff(uci,hbn):
    ts_names = ['PRECIP','PERO','AGWO','IFWO','SURO']
    df = pd.concat({ts_name:monthly_weighted_output(uci,hbn,ts_name,by_landcover=True,as_rate=True) for ts_name in ts_names},keys =ts_names)
    suro_perc = (df.loc['SURO']/df.loc['PERO'])*100
    suro_perc = suro_perc.reset_index()
    suro_perc['name'] = 'SURO_perc'
    suro_perc = suro_perc.set_index(['name','index'])
    return pd.concat([df,suro_perc])


def annual_perlnd_runoff(uci,hbn):
    ts_names = ['PRECIP','PERO','AGWO','IFWO','SURO']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,group_by='landcover') for ts_name in ts_names],axis = 1)
    df.columns = ts_names
    df['suro_perc'] = (df['SURO']/df['PERO'])*100
    return df


def annual_reach_water_budget(uci,hbn):
    ts_names = ['PRSUPY','IVOL','ROVOL','VOLEV']
    #df = pd.concat([annual_weighted_output(uci,hbn,ts_name,as_rate = True,by_landcover=True).mean() for ts_name in ts_names],axis = 1)
    df = pd.concat([hbn.get_multiple_timeseries('RCHRES',5,ts_name).mean() for ts_name in ts_names],axis=1)
    df.columns = ts_names
    # df = pd.concat([hbn.get_multiple_timeseries('RCHRES',5,'PRSUPY').mean(), #Inflow from Precipitation
    #                 hbn.get_multiple_timeseries('RCHRES',5,'IVOL').mean(),    #Total Inflow 
    #                 hbn.get_multiple_timeseries('RCHRES',5,'ROVOL').mean(),   #Total Outflow
    #                 hbn.get_multiple_timeseries('RCHRES',5,'VOLEV').mean()],axis=1) #Loss from Evaporation
    geninfo = uci.table('RCHRES','GEN-INFO')[['LKFG']]
    reach_intersection = geninfo.index.intersection(df.index)
    
    
    df = geninfo.loc[reach_intersection].join(df.loc[reach_intersection])
    #df.columns = ['LKFG','PRSUPY','IVOL','ROVOL','VOLEV']
    
    
    df['ROVOL_Input'] = 0.
    
    for reach_id in df.index:
        if reach_id in uci.network.G.nodes:
            upstream_ids = uci.network.upstream(reach_id)
            if len(upstream_ids) > 0:
                df.loc[reach_id,'ROVOL_Input'] = df.loc[upstream_ids]['ROVOL'].sum()
            
    df.index.name = 'OPNID'
    return df.reset_index()


def annual_implnd_water_budget(uci,hbn):
    ts_names = ['SUPY','SURO','IMPEV']
    #df = pd.concat([annual_weighted_output(uci,hbn,ts_name,as_rate = True,by_landcover=True).mean() for ts_name in ts_names],axis = 1)
    df = pd.concat([hbn.get_multiple_timeseries('IMPLND',5,ts_name).mean() for ts_name in ts_names],axis=1)
    df.columns = ts_names
    return df

def annual_perlnd_water_budget(uci,hbn):
    ts_names = ['PRECIP','TAET','PERO']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,group_by='landcover') for ts_name in ts_names],axis = 1)
    df.columns = ts_names
    return df

def annual_sediment_budget(uci,hbn):
    ts_names = ['SOSED']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,'PERLND', group_by='landcover')  for ts_name in ts_names],axis = 1)
    #df_rate = pd.concat([annual_weighted_output(uci,hbn,ts_name,'PERLND',as_rate = True, by_landcover=True).mean() for ts_name in ts_names],axis = 1)

    ts_names = ['SOSLD']
    sosld = pd.concat([annual_weighted_output(uci,hbn,ts_name,'IMPLND',group_by='landcover') for ts_name in ts_names],axis = 1)
    sosld.columns = ['SOSED']
    
    df = pd.concat([df,sosld])
    #df_rate = annual_weighted_output(uci,hbn,ts_name,'PERLND',as_rate = True, by_landcover=True).mean()

    df['Percentage'] = 100*(df['SOSED']*df.index.get_level_values('AFACTR')/sum(df['SOSED']*df.index.get_level_values('AFACTR')))
    
    df.columns = ['Sediment','Percentage']
    return df
    
# def annual_loading_rate():
    
    
# def annual_yield(uci,hbn,constituent):
    

def subwatershed_weighted_output(uci,hbn,reach_ids,ts_name,time_step,by_landcover=False,as_rate = True):
    subwatersheds = uci.network.subwatersheds(reach_ids)
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']
    
    areas = subwatersheds[['SVOLNO','AFACTR']].set_index('SVOLNO')
    areas = areas.join( uci.table('PERLND','GEN-INFO')['LSID'])
    opnids = subwatersheds['SVOLNO'].to_list()
    
    df = hbn.get_multiple_timeseries('PERLND',time_step,ts_name,opnids = opnids) 

    areas.loc[areas.index.intersection(df.columns)]
    df = df[areas.index.intersection(df.columns)]
    
    if by_landcover:
        df = (df*areas['AFACTR'].values).T.groupby(areas['LSID']).sum()
        if as_rate:
            df = df.T/areas['AFACTR'].groupby(areas['LSID']).sum().to_list()
        df.columns.name = ts_name
    else:
        df = (df * areas['AFACTR'].values).sum(axis=1)
        if as_rate:
            df = df/areas['AFACTR'].sum()
        df.name = ts_name    
        
    return df
            
        
    
    

# def perlnd_water_budget(uci,hbn,time_step = 5):
    
#     ts_names = ['SUPY','SURO','IFWO','AGWO','PERO','AGWI','IGWI','PET','UZET','LZET','AGWET','BASET','TAET']
#     dfs = [area_weighted_output(uci,hbn,ts_name,time_step) for ts_name in ts_names]
        
    


#%% Phosphorous Loading Calculations
def subwatershed_total_phosphorous_loading(uci,hbn,reach_ids = None,t_code=5, as_load = True,group_landcover = True):
    tp_loading = total_phosphorous(uci,hbn,t_code)
    if reach_ids is None:
        subwatersheds = uci.network.subwatersheds()
    else:
        subwatersheds = uci.network.subwatersheds(reach_ids)
    
    perlnds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']
    perlnds = perlnds['AFACTR'].groupby([perlnds.index,perlnds['SVOLNO']]).sum().reset_index()
    
    
    #perlnds = perlnds.set_index('SVOLNO').drop_duplicates()
    total = tp_loading[perlnds['SVOLNO']]
    
    total = total.mul(perlnds['AFACTR'].values,axis=1)       
    
    total = total.transpose()
    total['reach_id'] = perlnds['TVOLNO'].values
    total['landcover'] = uci.table('PERLND','GEN-INFO').loc[total.index,'LSID'].to_list()
    total['area'] = perlnds['AFACTR'].to_list() #perlnds.loc[total.index,'AFACTR'].to_list()
    total = total.reset_index().set_index(['index','landcover','area','reach_id']).transpose()
    total.columns.names = ['perlnd_id','landcover','area','reach_id']
    
    if group_landcover:
        total.columns = total.columns.droplevel(['landcover','perlnd_id'])
        total = total.T.reset_index().groupby('reach_id').sum().reset_index().set_index(['reach_id','area']).T
        
    if not as_load:
        total = total.div(total.columns.get_level_values('area').values,axis=1)       

    total.index = pd.to_datetime(total.index)
    return total

def total_phosphorous(uci,hbn,t_code,operation = 'PERLND'):
    #assert(isinstance(perlnd_ids (int,list,None)))
    opnids = uci.network.subwatersheds()
    opnids = opnids.loc[opnids['SVOL'] == operation].drop_duplicates(subset = ['SVOLNO','MLNO'])
    
    totals = []
    for mlno in opnids['MLNO'].unique():
        total = dissolved_orthophosphate(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate(uci,hbn,operation,mlno, t_code) + organic_refactory_phosphorous(uci,hbn,operation,mlno,t_code) + labile_oxygen_demand(uci,hbn,operation,mlno,t_code)*0.007326 # Conversation factor to P
        totals.append(total[opnids['SVOLNO'].loc[opnids['MLNO'] == mlno].to_list()])
    
    total = pd.concat(totals,axis=1)
    total = total.T.groupby(total.columns).sum().T
    return total


MASSLINK_SCHEME = {'dissolved_orthophosphate': {'tmemn': 'NUIF1',
                                                'tmemsb1': '4',
                                                'tmemsb2':''},
                'particulate_orthophosphate_sand': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '1',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_silt': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '2',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_clay': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '3',
                                                    'tmemsb2':'2'},
                'organic_refactory_phosphorous': {'tmemn': 'PKIF',
                                                  'tmemsb1' : '4',
                                                  'tmemsb2':''},
                'organic_refactory_carbon':{'tmemn' : 'PKIF',
                                            'tmemsb1': '5',
                                            'tmemsb2':''},
                'labile_oxygen_demand': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':''}}


def qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2 = '',t_code = 4):
    masslink = uci.table('MASS-LINK',f'MASS-LINK{mlno}')
    masslink = masslink.loc[(masslink['TMEMN'] == tmemn) & (masslink['TMEMSB1'] == tmemsb1) & (masslink['TMEMSB2'] == tmemsb2)]
    masslink.fillna({'MFACTOR': 1}, inplace=True)
    ts = 0
    for index,row in masslink.iterrows():
        hbn_name = uci.table(operation,'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
        hbn_name = row['SMEMN'] + hbn_name
        mfactor = row['MFACTOR']
        ts = hbn.get_multiple_timeseries(row['SVOL'],t_code,hbn_name)*mfactor + ts
    return ts




def dissolved_orthophosphate(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_sand(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_silt(uci,hbn,operation, mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate_clay(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def organic_refactory_phosphorous(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def organic_refactory_carbon(uci,hbn, operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['organic_refactory_carbon']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)
  
def labile_oxygen_demand(uci,hbn,operation,mlno,t_code = 4):
    tmemn = MASSLINK_SCHEME['labile_oxygen_demand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb2']
    return qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)

def particulate_orthophosphate(uci,hbn,operation,mlno,t_code = 4):
    ts = particulate_orthophosphate_sand(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate_silt(uci,hbn,operation,mlno,t_code) + particulate_orthophosphate_clay(uci,hbn,operation,mlno,t_code)
    return ts
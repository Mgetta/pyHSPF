# -*- coding: utf-8 -*-
"""
Legacy loading functions — older implementations kept for backward compatibility.
"""
import numpy as np
import pandas as pd
from hspf import helpers

from hspf.reports.phosphorus import total_phosphorous
from hspf.reports.utils import weighted_describe

from hspf.reports.loading import (
    catchment_loading_summary,
    watershed_loading_summary,
    get_watershed_loading,
    get_catchment_loading,
)
from hspf.reports.hydrology import (
    annual_perlnd_water_budget,
    annual_implnd_water_budget,
    annual_reach_water_budget,
    avg_annual_precip,
    simulated_et,
    annual_perlnd_runoff,
)
from hspf.reports.sediment import scour
from hspf.reports.contributions import (
    total_contributions,
    catchment_contributions,
)
from hspf.reports.yields import (
    average_annual_yield,
    average_monthly_yield,
)


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

def ann_avg_watershed_loading(constituent,uci,hbn,reach_ids=None, by_landcover = False):
    if reach_ids is None:
        reach_ids = uci.network.outlets()
    reach_ids = [item for sublist in [uci.network._upstream(reach_id) for reach_id in reach_ids] for item in sublist]
    df = ann_avg_constituent_loading(constituent,uci,hbn)
    df = df.loc[df['TVOLNO'].isin(reach_ids)]
    if by_landcover:
        df = df.groupby(df['LSID'])[[constituent,'AFACTR']].apply(lambda x: weighted_describe(x,constituent,'AFACTR')).droplevel(1)
    else:
        
        df = weighted_describe(df,constituent,'AFACTR')
    
    return df


class Reports():
    """Legacy convenience wrapper around report functions.

    .. deprecated::
        Prefer calling the individual report functions directly.
    """

    def __init__(self,uci,hbns,wdms):
        self.hbns = hbns
        self.uci = uci
        self.wdms = wdms


#Sediment Reports        
    def scour(self,start_year = '1996',end_year = '2030'):
        return scour(self.hbns,self.uci,start_year = start_year,end_year=end_year)

# Hydrology Reports
    def landcover_area(self,reach_ids=None,upstream_reach_ids = None):
        df = self.uci.network.drainage_area_landcover(reach_ids,upstream_reach_ids,group=True).reset_index()
        df['percent'] = 100*(df['area']/df['area'].sum())
        return df
    
    def annual_water_budget(self,operation):
        assert operation in ['PERLND','RCHRES','IMPLND']
        if operation =='PERLND':
            return annual_perlnd_water_budget(self.uci,self.hbns)
        elif operation == 'IMPLND':
            return annual_implnd_water_budget(self.uci,self.hbns)
        else:
            return annual_reach_water_budget(self.uci,self.hbns)

    def annual_precip(self):
        return avg_annual_precip(self.uci,self.wdms)
    
    def simulated_et(self):
        return simulated_et(self.uci,self.hbns)
    
    def annual_perlnd_runoff(self,reach_ids = None,upstream_reach_ids = None,start_year = 1996,end_year = 2100):
        if (reach_ids is None) and (upstream_reach_ids is None):
            opnids = None
        else:
            opnids = self.uci.network.get_opnids('PERLND',reach_ids,upstream_reach_ids)
        return annual_perlnd_runoff(self.uci,self.hbns,opnids,start_year,end_year)
    
    #% Catchment and Watershed Loading (Edge of Field Load) Reports 
    # 
    def average_annual_catchment_loading(self,constituent,by_landcover = False,start_year = 1996,end_year = 2100):
        return catchment_loading_summary(self.uci,self.hbns,constituent,start_year=start_year,end_year=end_year,by_landcover=by_landcover,simulation_period='yearly',aggregation_period='yearly',agg_func='mean')
    
    def average_monthly_catchment_loading(self,constituent,by_landcover = False,start_year = 1996,end_year = 2100):
        return catchment_loading_summary(self.uci,self.hbns,constituent,start_year=start_year,end_year=end_year,by_landcover=by_landcover,simulation_period='monthly',aggregation_period='monthly',agg_func='mean')
    
    def average_annual_watershed_loading(self,constituent,reach_ids=None,upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
        return watershed_loading_summary(self.uci,self.hbns,constituent,reach_ids=reach_ids,upstream_reach_ids=upstream_reach_ids,start_year=start_year,end_year=end_year,by_landcover=by_landcover,drainage_area=drainage_area,simulation_period='yearly',aggregation_period='yearly',agg_func='mean')
    
    def average_monthly_watershed_loading(self,constituent,reach_ids=None,upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
        return watershed_loading_summary(self.uci,self.hbns,constituent,reach_ids=reach_ids,upstream_reach_ids=upstream_reach_ids,start_year=start_year,end_year=end_year,by_landcover=by_landcover,drainage_area=drainage_area,simulation_period='monthly',aggregation_period='monthly',agg_func='mean')
        
    def watershed_loading(self,constituent,reach_ids,upstream_reach_ids = None,by_landcover = False):
        '''
        Calculate the edge of field loading to channels from each catchment within the watershed defined by reach_ids and upstream_reach_ids.
        
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
    
    # Contributions Reports
    def contributions(self,constituent,target_reach_id):
        return total_contributions(constituent,self.uci,self.hbns,target_reach_id)

    def landcover_contributions(self,constituent,target_reach_id,landcover = None):
        return catchment_contributions(self.uci,self.hbns,constituent,target_reach_id)
    
    # Landscape Yield Reports
  
    def average_annual_yield(self,constituent,reach_ids=None,upstream_reach_ids = None,start_year = 1996,end_year = 2100):
        df= average_annual_yield(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids,start_year,end_year)
        return df

    def average_monthly_yield(self,constituent,reach_ids=None,upstream_reach_ids = None,start_year = 1996,end_year = 2100):
        df= average_monthly_yield(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids,start_year,end_year)
        return df

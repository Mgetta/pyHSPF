# -*- coding: utf-8 -*-
"""
Reports package for HSPF model output analysis.

Submodules
----------
loading
    Constituent loading reports (catchment and watershed edge-of-field loading).
yields
    Landscape yield reports (constituent loads and yields at reach outlets).
contributions
    Channel contributions and allocation reports.
hydrology
    Water balance, precipitation, ET, runoff, and meteorological reports.
sediment
    Scour and sediment budget reports.
phosphorus
    TP-specific calculations (masslink scheme, qualprop transforms).
utils
    Utility functions for weighted statistics and time aggregation.
legacy
    Older loading implementations kept for backward compatibility.
"""

# --- loading ---
from hspf.reports.loading import (
    catchment_areas,
    catchment_landcover_areas,
    watershed_landcover_areas,
    get_constituent_loading,
    _join_catchments,
    get_catchment_loading,
    get_watershed_loading,
    _average_constituent_loading,
    constituent_loading_summary,
    average_annual_constituent_loading,
    average_monthly_constituent_loading,
    _aggregate_catchment_loading,
    catchment_loading_summary,
    average_annual_catchment_loading,
    average_monthly_catchment_loading,
    _filter_to_watershed,
    watershed_loading_summary,
    average_annual_watershed_loading,
    average_monthly_watershed_loading,
)

# --- yields ---
from hspf.reports.yields import (
    _constituent_load,
    constituent_load,
    _constituent_yield,
    constituent_yield,
    average_annual_yield,
    average_monthly_yield,
)

# --- contributions ---
from hspf.reports.contributions import (
    allocation_selector,
    channel_inflows,
    channel_outflows,
    channel_fate,
    local_loading,
    catchment_contributions,
    total_contributions,
)

# --- sediment ---
from hspf.reports.sediment import (
    scour,
    annual_sediment_budget,
)

# --- phosphorus ---
from hspf.reports.phosphorus import (
    MASSLINK_SCHEME,
    qualprop_transform,
    dissolved_orthophosphate,
    particulate_orthophosphate_sand,
    particulate_orthophosphate_silt,
    particulate_orthophosphate_clay,
    organic_refactory_phosphorous,
    organic_refactory_carbon,
    labile_oxygen_demand,
    particulate_orthophosphate,
    total_phosphorous,
    subwatershed_total_phosphorous_loading,
)

# --- hydrology ---
from hspf.reports.hydrology import (
    pevt_balance,
    simulated_et,
    inflows,
    water_balance,
    meteorlogical,
    avg_annual_precip,
    annual_perlnd_runoff,
    annual_reach_water_budget,
    perlnd_water_budget,
    annual_implnd_water_budget,
    annual_perlnd_water_budget,
    watershed_water_budget,
    metzone_watershed_budget,
)

# --- utils ---
from hspf.reports.utils import (
    weighted_describe,
    weighted_parameter,
    weighted_output,
    _apply_time_aggregation,
    weighted_mean,
    annual_weighted_output,
)

# --- residence ---
from hspf.reports.residence import (
    residence_time,
    residence_time_stats,
    turnover_ratio,
    exceedance_probability,
    cumulative_exposure,
    residence_time_distribution,
    seasonal_residence_time,
    multi_reach_residence_time,
)

# --- legacy ---
from hspf.reports.legacy import (
    avg_subwatershed_loading,
    monthly_avg_constituent_loading,
    monthly_avg_subwatershed_loading,
    monthly_avg_watershed_loading,
    ann_avg_constituent_loading,
    ann_avg_subwatershed_loading,
    ann_avg_watershed_loading,
)


class Reports():
    def __init__(self,uci,hbns,wdms):
        self.hbns = hbns
        self.uci = uci
        self.wdms = wdms


#Sediment Reports        
    def scour(self,start_year = '1996',end_year = '2030'):
        return scour(self.hbns,self.uci,start_year = start_year,end_year=end_year)

# Hydrology Reports
    def landcover_area(self,reach_ids,upstream_reach_ids = None):
        return watershed_landcover_areas(self.uci,reach_ids,upstream_reach_ids)
    
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
        return average_annual_catchment_loading(self.uci,self.hbns,constituent,by_landcover = by_landcover,start_year = start_year,end_year = end_year)
    
    def average_monthly_catchment_loading(self,constituent,by_landcover = False,start_year = 1996,end_year = 2100):
        return average_monthly_catchment_loading(self.uci,self.hbns,constituent,by_landcover = by_landcover,start_year = start_year,end_year = end_year)
    
    def average_annual_watershed_loading(self,constituent,reach_ids,upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
        return average_annual_watershed_loading(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids, start_year, end_year, by_landcover,drainage_area)
    
    def average_monthly_watershed_loading(self,constituent,reach_ids,upstream_reach_ids = None, start_year = 1996, end_year = 2100, by_landcover = False,drainage_area = None):
        return average_monthly_watershed_loading(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids, start_year, end_year, by_landcover,drainage_area)
        
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
  
    def average_annual_yield(self,constituent,reach_ids,upstream_reach_ids = None,start_year = 1996,end_year = 2100):
        df= average_annual_yield(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids,start_year,end_year)
        return df

    def average_monthly_yield(self,constituent,reach_ids,upstream_reach_ids = None,start_year = 1996,end_year = 2100):
        df= average_monthly_yield(self.uci,self.hbns,constituent,reach_ids,upstream_reach_ids,start_year,end_year)
        return df


# Remaining non-class helper kept at package level
def get_catchments(uci,reach_ids):
    # Grab metadata information
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND',:].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR','LSID','metzone','TVOLNO','MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0,pd.NA)
    return landcover


def _operation_metadata():
        # Add metadata
    from hspf import uci
    dfs = []
    for operation in ['PERLND','IMPLND','RCHRES']:
        df = uci.opnid_dict[operation].reset_index()
        df['OPERATION'] = operation
        dfs.append(df)
    df = pd.concat(dfs)

    # Merge with network data
    df = pd.merge(
        uci.network.subwatersheds().reset_index(),
        df[['TOPFST','OPERATION','metzone']],
        left_on=['SVOLNO', 'SVOL'],
        right_on=['TOPFST', 'OPERATION'],
        how='inner'
    )
    
    return df[['TVOLNO','SVOLNO','SVOL','AFACR','MLNO','LSID','metzone']]

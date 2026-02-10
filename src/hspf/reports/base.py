# -*- coding: utf-8 -*-
"""
Base Reports class.

This class provides a unified interface for generating various model summaries
that require information across the various objects (hbn, uci, wdm, and any
static datasources).
"""
import pandas as pd

from . import sediment
from . import hydrology
from . import loading
from . import phosphorous


class Reports:
    """Main interface for generating HSPF model reports.
    
    This class aggregates information from HBN, UCI, and WDM data sources
    to generate various model summaries and reports.
    
    Args:
        uci: UCI object containing model configuration
        hbns: HBN interface object for accessing binary output
        wdms: WDM interface object for accessing input data
    """
    
    def __init__(self, uci, hbns, wdms):
        self.hbns = hbns
        self.uci = uci
        self.wdms = wdms

    # Sediment Reports
    def scour(self, start_year='1996', end_year='2030'):
        """Generate scour report for reaches.
        
        Args:
            start_year: Start year for analysis
            end_year: End year for analysis
            
        Returns:
            DataFrame with scour analysis results
        """
        return sediment.scour(self.hbns, self.uci, start_year=start_year, end_year=end_year)

    def annual_sediment_budget(self):
        """Generate annual sediment budget by landcover.
        
        Returns:
            DataFrame with sediment budget by landcover
        """
        return sediment.annual_sediment_budget(self.uci, self.hbns)

    # Hydrology Reports
    def landcover_area(self):
        """Get landcover areas from the model.
        
        Returns:
            DataFrame with landcover areas and percentages
        """
        return hydrology.landcover_areas(self.uci)

    def annual_water_budget(self, operation):
        """Generate annual water budget for specified operation.
        
        Args:
            operation: Operation type ('PERLND', 'RCHRES', or 'IMPLND')
            
        Returns:
            DataFrame with water budget
        """
        assert operation in ['PERLND', 'RCHRES', 'IMPLND']
        if operation == 'PERLND':
            return hydrology.annual_perlnd_water_budget(self.uci, self.hbns)
        elif operation == 'IMPLND':
            return hydrology.annual_implnd_water_budget(self.uci, self.hbns)
        else:
            return hydrology.annual_reach_water_budget(self.uci, self.hbns)

    def simulated_et(self):
        """Calculate simulated evapotranspiration.
        
        Returns:
            DataFrame with simulated ET by operation
        """
        return hydrology.simulated_et(self.uci, self.hbns)

    def annual_precip(self):
        """Calculate average annual precipitation.
        
        Returns:
            DataFrame with average annual precipitation
        """
        return hydrology.avg_annual_precip(self.uci, self.wdms)

    # Loading Reports
    def ann_avg_subwatershed_loading(self, constituent):
        """Calculate annual average subwatershed loading.
        
        Args:
            constituent: Constituent name
            
        Returns:
            DataFrame with annual subwatershed loading
        """
        return loading.ann_avg_subwatershed_loading(constituent, self.uci, self.hbns)

    def ann_avg_watershed_loading(self, constituent, reach_ids):
        """Calculate annual average watershed loading.
        
        Args:
            constituent: Constituent name
            reach_ids: List of reach IDs
            
        Returns:
            DataFrame with annual watershed loading
        """
        landcovers = loading.ann_avg_watershed_loading(constituent, reach_ids, self.uci, self.hbns, True)
        total = loading.ann_avg_watershed_loading(constituent, reach_ids, self.uci, self.hbns, False)
        total.index = ['Total']
        total = pd.concat([landcovers, total])
        total['volume'] = total['area'] * total[f'weighted_mean_{constituent}']
        total['volume_percent'] = total['volume'] / total.loc['Total', 'volume'] * 100
        total['area_percent'] = total['area'] / total.loc['Total', 'area'] * 100
        total['share'] = total['volume_percent'] / total['area_percent']
        return total

    def ann_avg_yield(self, constituent, reach_ids):
        """Calculate average annual yield.
        
        Args:
            constituent: Constituent name
            reach_ids: List of reach IDs
            
        Returns:
            DataFrame with average annual yield
        """
        df = loading.avg_ann_yield(self.uci, self.hbns, constituent, reach_ids)
        return df

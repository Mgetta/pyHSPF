# -*- coding: utf-8 -*-
"""
Utility functions for the reports module.

Contains shared helper functions used across multiple report types.
"""
import numpy as np
import pandas as pd


def weighted_describe(df, value_col, weight_col):
    """Calculate weighted statistics for a DataFrame.
    
    Args:
        df: DataFrame containing the data
        value_col: Name of the column containing values
        weight_col: Name of the column containing weights
        
    Returns:
        DataFrame with weighted mean and standard deviation
    """
    weighted_mean = (df[value_col] * df[weight_col]).sum() / df[weight_col].sum()
    weighted_var = ((df[value_col] - weighted_mean) ** 2 * df[weight_col]).sum() / df[weight_col].sum()
    weighted_std = np.sqrt(weighted_var)

    return pd.DataFrame({
        'area': df[weight_col].sum(),
        f'weighted_mean_{value_col}': [weighted_mean],
        f'weighted_std_{value_col}': [weighted_std]
    })


def weighted_mean(df, value_col, weight_col):
    """Calculate weighted mean for a DataFrame.
    
    Args:
        df: DataFrame containing the data
        value_col: Name of the column containing values
        weight_col: Name of the column containing weights
        
    Returns:
        DataFrame with weighted mean and total area
    """
    wm = (df[value_col] * df[weight_col]).sum() / df[weight_col].sum()
    return pd.DataFrame({
        'AFACTR': df[weight_col].sum(),
        value_col: [wm]
    })


def get_catchments(uci, reach_ids):
    """Get catchment metadata for specified reach IDs.
    
    Args:
        uci: UCI object containing model configuration
        reach_ids: List of reach IDs to get catchments for
        
    Returns:
        DataFrame with catchment information
    """
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND', :].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR', 'LSID', 'metzone', 'TVOLNO', 'MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0, pd.NA)
    return landcover

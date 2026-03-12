# -*- coding: utf-8 -*-
"""
Model-agnostic loading analytics.

Pure computation functions for converting between loading rates and loads.
No HSPF imports, no uci/hbn references.
"""


def compute_load(loading_rate, area):
    """Compute load from a loading rate and contributing area.

    Parameters
    ----------
    loading_rate : pd.DataFrame or pd.Series
        Loading rate timeseries (e.g., lb/acre/timestep).
    area : float or pd.Series
        Contributing area. If float, applied uniformly.
        If pd.Series, indexed by the same IDs as loading_rate columns.

    Returns
    -------
    pd.DataFrame or pd.Series
        Load timeseries (rate × area).
    """
    return loading_rate * area


def compute_loading_rate(load, area):
    """Compute loading rate from a load and contributing area.

    Parameters
    ----------
    load : pd.DataFrame or pd.Series
        Load timeseries (e.g., lb/timestep).
    area : float or pd.Series
        Contributing area.

    Returns
    -------
    pd.DataFrame or pd.Series
        Loading rate timeseries (load / area).
    """
    return load / area

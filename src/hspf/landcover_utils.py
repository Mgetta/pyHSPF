# -*- coding: utf-8 -*-
"""
Landcover utilities module for working with model landcover data.

This module provides functions to query and retrieve landcover information
from the model_landcovers.csv file.
"""
import pandas as pd
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_landcover_data():
    """Load the model_landcovers.csv file and return a DataFrame.
    
    The DataFrame is cached to avoid repeated file I/O operations.
    """
    data_path = Path(__file__).parent / "data" / "model_landcovers.csv"
    return pd.read_csv(data_path)


def get_landcover(model_name, perlnd_id):
    """
    Get landcover information for a specific perlnd in a model.

    Parameters
    ----------
    model_name : str
        The name of the model (e.g., 'BigFork', 'BigSioux').
    perlnd_id : int
        The OPNID of the perlnd.

    Returns
    -------
    dict or None
        A dictionary containing all landcover information for the perlnd,
        or None if the perlnd is not found.
    """
    df = _load_landcover_data()
    result = df[(df['model'] == model_name) & (df['OPNID'] == perlnd_id)]
    if result.empty:
        return None
    return result.iloc[0].to_dict()


def get_agricultural_perlnds(model_name):
    """
    Get all agricultural perlnds for a model.

    Parameters
    ----------
    model_name : str
        The name of the model (e.g., 'BigFork', 'BigSioux').

    Returns
    -------
    list of int
        A list of OPNID values for all agricultural perlnds in the model.
    """
    df = _load_landcover_data()
    result = df[(df['model'] == model_name) & (df['Landcover'] == 'Agricultural')]
    return result['OPNID'].dropna().astype(int).tolist()


def get_forested_perlnds(model_name):
    """
    Get all forested perlnds for a model.

    Parameters
    ----------
    model_name : str
        The name of the model (e.g., 'BigFork', 'BigSioux').

    Returns
    -------
    list of int
        A list of OPNID values for all forested perlnds in the model.
    """
    df = _load_landcover_data()
    result = df[(df['model'] == model_name) & (df['Landcover'] == 'Forest')]
    return result['OPNID'].dropna().astype(int).tolist()


def get_cropland_perlnds(model_name):
    """
    Get all cropland perlnds for a model.

    Cropland perlnds are a subset of agricultural perlnds where
    the 'Agricultural Use' column is 'Cropland'.

    Parameters
    ----------
    model_name : str
        The name of the model (e.g., 'BigFork', 'BigSioux').

    Returns
    -------
    list of int
        A list of OPNID values for all cropland perlnds in the model.
    """
    df = _load_landcover_data()
    result = df[(df['model'] == model_name) & (df['Agricultural Use'] == 'Cropland')]
    return result['OPNID'].dropna().astype(int).tolist()

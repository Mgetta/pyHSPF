# -*- coding: utf-8 -*-
"""Landcover utilities module for working with model landcover data."""
import pandas as pd
from pathlib import Path

# Load landcover data as a global DataFrame on module import
_DATA_PATH = Path(__file__).parent / "data" / "model_landcovers.csv"
try:
    LANDCOVER_DF = pd.read_csv(_DATA_PATH)
except FileNotFoundError:
    raise FileNotFoundError(f"Landcover data file not found: {_DATA_PATH}")
except Exception as e:
    raise RuntimeError(f"Error loading landcover data from {_DATA_PATH}: {e}")


def get_landcover(model_name, perlnd_id):
    """Get landcover information for a specific perlnd in a model."""
    result = LANDCOVER_DF[(LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['OPNID'] == perlnd_id)]
    if result.empty:
        return None
    return result.iloc[0].to_dict()


def get_agricultural_perlnds(model_name):
    """Get all agricultural perlnds for a model."""
    result = LANDCOVER_DF[(LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['Landcover'] == 'Agricultural')]
    return result['OPNID'].dropna().astype(int).tolist()


def get_forested_perlnds(model_name):
    """Get all forested perlnds for a model."""
    result = LANDCOVER_DF[(LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['Landcover'] == 'Forest')]
    return result['OPNID'].dropna().astype(int).tolist()


def get_cropland_perlnds(model_name):
    """Get cropland perlnds (Agricultural Use == 'Cropland') for a model."""
    result = LANDCOVER_DF[(LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['Agricultural Use'] == 'Cropland')]
    return result['OPNID'].dropna().astype(int).tolist()


def get_perlnds_by_landcover(model_name, landcover):
    """Get all perlnds with a specific landcover type for a model."""
    result = LANDCOVER_DF[(LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['Landcover'] == landcover)]
    return result['OPNID'].dropna().astype(int).tolist()


def filter_perlnds_by_landcover(model_name, perlnd_ids, landcover):
    """Filter a list of perlnd IDs to only those matching a specific landcover type."""
    mask = (
        (LANDCOVER_DF['model'] == model_name) &
        (LANDCOVER_DF['OPNID'].isin(perlnd_ids)) &
        (LANDCOVER_DF['Landcover'] == landcover)
    )
    return LANDCOVER_DF[mask]['OPNID'].dropna().astype(int).tolist()


def get_all_models():
    """Get a list of all unique model names in the dataset."""
    return LANDCOVER_DF['model'].unique().tolist()


def get_model_perlnds(model_name):
    """Get all perlnd IDs for a model."""
    result = LANDCOVER_DF[LANDCOVER_DF['model'] == model_name]
    return result['OPNID'].dropna().astype(int).tolist()


def get_landcover_summary(model_name):
    """Get a count of perlnds by landcover type for a model."""
    result = LANDCOVER_DF[LANDCOVER_DF['model'] == model_name]
    return result['Landcover'].value_counts().to_dict()


def get_landcovers_for_perlnds(model_name, perlnd_ids):
    """Get landcover info for a list of perlnd IDs in a model."""
    mask = (LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF['OPNID'].isin(perlnd_ids))
    return LANDCOVER_DF[mask].to_dict('records')


def get_cross_model_summary(landcover):
    """Get count of perlnds with a specific landcover type across all models."""
    result = LANDCOVER_DF[LANDCOVER_DF['Landcover'] == landcover]
    return result.groupby('model')['OPNID'].count().to_dict()


def get_all_landcover_types():
    """Get a list of all unique landcover types in the dataset."""
    return LANDCOVER_DF['Landcover'].dropna().unique().tolist()


def get_perlnds_by_column_value(model_name, column, value):
    """Get perlnds where column matches value; returns empty list if column not found."""
    if column not in LANDCOVER_DF.columns:
        return []
    mask = (LANDCOVER_DF['model'] == model_name) & (LANDCOVER_DF[column] == value)
    return LANDCOVER_DF[mask]['OPNID'].dropna().astype(int).tolist()

# -*- coding: utf-8 -*-
"""Static geometry-based channel travel time (residence time) calculations."""
import numpy as np
import pandas as pd

from hspf.parser import graph


def get_reach_hydraulics(uci):
    """Extract HYDR-PARM2 properties needed for travel time calculations."""
    parm2 = uci.table('RCHRES', 'HYDR-PARM2')
    cols = ['LEN', 'FTBW', 'DELTH', 'KS']
    if 'FTBUCI' in parm2.columns:
        depth_col = 'FTBUCI'
    elif 'STCOR' in parm2.columns:
        depth_col = 'STCOR'
    else:
        depth_col = None
    if depth_col is not None:
        cols.append(depth_col)
    df = parm2[cols].copy()
    if depth_col == 'STCOR':
        df = df.rename(columns={'STCOR': 'FTBUCI'})
    elif depth_col is None:
        df['FTBUCI'] = np.nan

    df['LEN_FT'] = df['LEN'] * 5280.0
    slope = np.where(df['LEN_FT'] > 0, df['DELTH'] / df['LEN_FT'], np.nan)
    df['SLOPE'] = np.maximum(slope, 0.00001)

    w = df['FTBW'].replace(0, np.nan)
    d = df['FTBUCI'].replace(0, np.nan)
    df['HYDR_RADIUS'] = (w * d) / (w + 2 * d)

    return df


def _is_invalid(v):
    """Return True if v is None, NaN, or non-positive."""
    if v is None:
        return True
    try:
        return np.isnan(float(v)) or float(v) <= 0
    except (TypeError, ValueError):
        return True


def mannings_velocity(ks, hydraulic_radius, slope):
    """Compute velocity (ft/s) using Manning's equation: V = (1.49/n) * R^(2/3) * S^(1/2)."""
    if _is_invalid(ks) or _is_invalid(hydraulic_radius) or _is_invalid(slope):
        return np.nan
    return (1.49 / ks) * (hydraulic_radius ** (2.0 / 3.0)) * (slope ** 0.5)


def reach_travel_time(length_ft, velocity):
    """Compute travel time in hours for a single reach: length / velocity / 3600."""
    if _is_invalid(velocity) or _is_invalid(length_ft):
        return np.nan
    return length_ft / velocity / 3600.0


def path_travel_time(uci, outlet_reach_id, source_reach_id):
    """Compute total travel time (hours) from source_reach_id to outlet_reach_id along the routing path."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    if source_reach_id not in all_paths:
        return np.nan
    hydraulics = get_reach_hydraulics(uci)
    total = 0.0
    for reach_id in all_paths[source_reach_id]:
        if reach_id not in hydraulics.index:
            return np.nan
        row = hydraulics.loc[reach_id]
        v = mannings_velocity(row['KS'], row['HYDR_RADIUS'], row['SLOPE'])
        tt = reach_travel_time(row['LEN_FT'], v)
        if np.isnan(tt):
            return np.nan
        total += tt
    return total


def travel_times(uci, outlet_reach_id):
    """Compute travel time from every upstream reach to the outlet. Returns a pd.Series indexed by reach_id."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    hydraulics = get_reach_hydraulics(uci)
    result = {outlet_reach_id: 0.0}
    for source_reach_id, path in all_paths.items():
        total = 0.0
        for reach_id in path:
            if reach_id not in hydraulics.index:
                total = np.nan
                break
            row = hydraulics.loc[reach_id]
            v = mannings_velocity(row['KS'], row['HYDR_RADIUS'], row['SLOPE'])
            tt = reach_travel_time(row['LEN_FT'], v)
            if np.isnan(tt):
                total = np.nan
                break
            total += tt
        result[source_reach_id] = total
    return pd.Series(result, name='travel_time_hours')


def travel_time_summary(uci, outlet_reach_id):
    """Return a DataFrame with travel time and catchment area for each upstream reach."""
    G = uci.network.G
    tt = travel_times(uci, outlet_reach_id)
    records = []
    for reach_id, travel_time_hours in tt.items():
        area = graph.catchment_area(G, reach_id)
        records.append({'reach_id': reach_id, 'travel_time_hours': travel_time_hours, 'catchment_area_acres': area})
    return pd.DataFrame(records)

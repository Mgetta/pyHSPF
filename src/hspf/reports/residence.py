# -*- coding: utf-8 -*-
"""Static geometry-based channel travel time (residence time) calculations."""
import numpy as np
import pandas as pd

from hspf.parser import graph

# Calculate the 2 year return period flow for each reach and use that to estimate the effective flow width and depth for travel time calculations. This is a common approach for estimating residence time under typical flow conditions, but it does not account for temporal variability in flow or the effects of backwater and storage areas. For more accurate residence time estimates, a dynamic hydrodynamic model would be needed.


def get_reach_hydraulics(uci,hbn):
    dfs = []
    parm2 = uci.table('RCHRES', 'HYDR-PARM2')
    for table_name in uci.table_names('FTABLES'):
        reach_id = int(table_name.replace('FTABLE', ''))
        if reach_id in parm2.index:
            
            flow = hbn.get_reach_constituent('Q',[reach_id],5).median()

            geometry = uci.table('FTABLES',f'FTABLE{reach_id}')
            bf_geometry = geometry.iloc[abs(geometry['Disch1'].dropna()-flow.values).argmin()]
            
            w = bf_geometry['Area'] / bf_geometry['Depth']
            d = bf_geometry['Depth']
            len_ft = parm2['LEN'].loc[reach_id] * 5280.0
            delth = parm2['DELTH'].loc[reach_id]
            ks = parm2['KS'].loc[reach_id]
            slope = np.maximum(delth / len_ft if len_ft > 0 else np.nan, 0.00001)
            hydr_radius = (w * d) / (w + 2 * d) if (w + 2 * d) != 0 else np.nan

            df = pd.DataFrame([{
                'OPNID': reach_id,
                'LEN': parm2['LEN'].loc[reach_id],
                'DEPTH': d,
                'WIDTH': w,
                'WETTED_PERIMETER': w + 2 * d,
                'LEN_FT': len_ft,
                'SLOPE': slope,
                'HYDR_RADIUS': hydr_radius,
                'DELTH': delth,
                'KS': ks
            }], index=[reach_id])
            dfs.append(df.set_index('OPNID'))
    return pd.concat(dfs)
    
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


def path_travel_time(uci, hbn, outlet_reach_id, source_reach_id):
    """Compute total travel time (hours) from source_reach_id to outlet_reach_id along the routing path."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    if source_reach_id not in all_paths:
        return np.nan
    hydraulics = get_reach_hydraulics(uci,hbn)
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


def travel_times(uci, hbn, outlet_reach_id):
    """Compute travel time from every upstream reach to the outlet. Returns a pd.Series indexed by reach_id."""
    G = uci.network.G
    all_paths = graph.paths(G, outlet_reach_id)
    hydraulics = get_reach_hydraulics(uci,hbn)
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


def travel_time_summary(uci, hbn,outlet_reach_id):
    """Return a DataFrame with travel time and catchment area for each upstream reach."""
    G = uci.network.G
    tt = travel_times(uci, hbn, outlet_reach_id)
    records = []
    for reach_id, travel_time_hours in tt.items():
        area = graph.catchment_area(G, reach_id)
        records.append({'reach_id': reach_id, 'travel_time_hours': travel_time_hours, 'catchment_area_acres': area})
    return pd.DataFrame(records)



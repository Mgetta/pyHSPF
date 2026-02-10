# -*- coding: utf-8 -*-
"""
Sediment-related reports.

Contains functions for generating sediment budget and scour reports.
"""
import numpy as np
import pandas as pd

from .utils import weighted_mean


def scour(hbn, uci, start_year='1996', end_year='2030'):
    """Calculate scour report for reaches.
    
    Args:
        hbn: HBN interface object
        uci: UCI object containing model configuration
        start_year: Start year for analysis
        end_year: End year for analysis
        
    Returns:
        DataFrame with scour analysis results
    """
    schematic = uci.table('SCHEMATIC').copy()
    schematic = schematic.astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR': float})
    schematic = schematic[(schematic['SVOL'] == 'PERLND') | (schematic['SVOL'] == 'IMPLND')]
    schematic = schematic[schematic['TVOL'] == 'RCHRES']

    sosed = hbn.get_multiple_timeseries(t_opn='PERLND',
                                        t_con='SOSED',
                                        activity='SEDMNT',
                                        t_code='yearly',
                                        opnids=None)
    sosed = sosed.loc[(sosed.index > start_year) & (sosed.index < end_year)].mean().rename('mean').to_frame()

    sosld = hbn.get_multiple_timeseries(t_opn='IMPLND',
                                        t_con='SOSLD',
                                        activity='SOLIDS',
                                        t_code='yearly',
                                        opnids=None)
    sosld = sosld.loc[(sosld.index > start_year) & (sosld.index < end_year)].mean().rename('mean').to_frame()

    depscr = hbn.get_multiple_timeseries(t_opn='RCHRES',
                                         t_con='DEPSCOURTOT',
                                         activity='SEDTRN',
                                         t_code='yearly',
                                         opnids=None)
    depscr = depscr.loc[(depscr.index > start_year) & (depscr.index < end_year)].mean().rename('mean').to_frame()

    lakeflag = uci.table('RCHRES', 'GEN-INFO').copy()[['RCHID', 'LKFG']]

    scour_report = []
    for tvolno in lakeflag.index:
        reach_load = depscr.loc[tvolno].values[0]
        schem_sub = schematic[schematic['TVOLNO'] == tvolno]
        if len(schem_sub) == 0:
            scour_report.append((tvolno, np.nan, reach_load))
        else:
            prlnd_load = 0
            implnd_load = 0
            
            if 'PERLND' in schem_sub['SVOL'].values:
                schem_prlnd = schem_sub[schem_sub['SVOL'] == 'PERLND'].copy()
                sosed_match = [x for x in schem_prlnd['SVOLNO'] if x in sosed.index]
                schem_prlnd = schem_prlnd[schem_prlnd['SVOLNO'].isin(sosed_match)]
                sosed_sub = sosed.loc[sosed_match]
                prlnd_load = np.sum(schem_prlnd['AFACTR'].values * sosed_sub['mean'].values)

            if 'IMPLND' in schem_sub['SVOL'].values:
                schem_implnd = schem_sub[schem_sub['SVOL'] == 'IMPLND'].copy()
                sosld_match = [x for x in schem_implnd['SVOLNO'] if x in sosld.index]
                schem_implnd = schem_implnd[schem_implnd['SVOLNO'].isin(sosld_match)]
                sosld_sub = sosld.loc[sosld_match]
                implnd_load = np.sum(schem_implnd['AFACTR'].values * sosld_sub['mean'].values)

            watershed_load = prlnd_load + implnd_load
            scour_report.append((tvolno, watershed_load, reach_load))

    scour_report = pd.DataFrame(scour_report, columns=['TVOLNO', 'nonpoint', 'depscour'])
    scour_report['ratio'] = scour_report['nonpoint'] / (scour_report['nonpoint'] + np.abs(scour_report['depscour']))
    scour_report = pd.merge(lakeflag, scour_report, left_index=True, right_on='TVOLNO').set_index('TVOLNO')
    return scour_report


def annual_sediment_budget(uci, hbn):
    """Calculate annual sediment budget by landcover.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with sediment budget by landcover
    """
    from .hydrology import annual_weighted_output
    
    ts_names = ['SOSED']
    df = pd.concat([annual_weighted_output(uci, hbn, ts_name, 'PERLND', group_by='landcover') for ts_name in ts_names], axis=1)

    ts_names = ['SOSLD']
    sosld = pd.concat([annual_weighted_output(uci, hbn, ts_name, 'IMPLND', group_by='landcover') for ts_name in ts_names], axis=1)
    sosld.columns = ['SOSED']

    df = pd.concat([df, sosld])

    df['Percentage'] = 100 * (df['SOSED'] * df.index.get_level_values('AFACTR') / sum(df['SOSED'] * df.index.get_level_values('AFACTR')))

    df.columns = ['Sediment', 'Percentage']
    return df

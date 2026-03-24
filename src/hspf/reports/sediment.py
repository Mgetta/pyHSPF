# -*- coding: utf-8 -*-
"""
Sediment reports — scour and sediment budget.
"""
import numpy as np
import pandas as pd

from hspf.reports.utils import annual_weighted_output


def scour(hbn,uci,start_year = 1996,end_year = 2030):
    """Compute nonpoint vs. channel scour ratios for each reach.

    Compares edge-of-field sediment loading (PERLND SOSED + IMPLND SOSLD)
    against net in-channel deposition/scour (RCHRES DEPSCOURTOT).

    Parameters
    ----------
    hbn : hbnInterface
        HBN binary output interface.
    uci : UCI
        Parsed UCI model object.
    start_year, end_year : int, optional
        Year range for averaging (inclusive, defaults 1996–2030).

    Returns
    -------
    pd.DataFrame
        Indexed by ``TVOLNO`` with columns ``LKFG``, ``nonpoint``,
        ``depscour``, and ``ratio`` (nonpoint / total).
    """
    # Should eventually create an entire reports module or class indorder to calculate all of the different model checks
    # TODO: Incorporate IMPLNDS
    schematic = uci.table('SCHEMATIC').copy()
    schematic = schematic.astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR':float})
    schematic = schematic[(schematic['SVOL'] == 'PERLND') | (schematic['SVOL'] == 'IMPLND')]
    schematic = schematic[schematic['TVOL'] == 'RCHRES']        
    
    sosed = hbn.get_multiple_timeseries(t_opn = 'PERLND',
                                                     t_con = 'SOSED',
                                                     activity = 'SEDMNT',
                                                     t_code = 'yearly',
                                                     opnids = None)
    sosed = sosed.loc[(sosed.index.year >= start_year) & (sosed.index.year <= end_year)].mean().rename('mean').to_frame()

    sosld =  hbn.get_multiple_timeseries(t_opn = 'IMPLND',
                                             t_con = 'SOSLD',
                                             activity = 'SOLIDS',
                                             t_code = 'yearly',
                                             opnids = None)
    sosld = sosld.loc[(sosld.index.year >= start_year) & (sosld.index.year <= end_year)].mean().rename('mean').to_frame()

    depscr =  hbn.get_multiple_timeseries(t_opn = 'RCHRES',
                                                     t_con = 'DEPSCOURTOT',
                                                     activity = 'SEDTRN',
                                                     t_code = 'yearly',
                                                     opnids = None)
    depscr = depscr.loc[(depscr.index.year >= start_year) & (depscr.index.year <= end_year)].mean().rename('mean').to_frame()

    lakeflag =  uci.table('RCHRES','GEN-INFO').copy()[['RCHID','LKFG']]

    scour_report = []
    # schematic block will have all the possible perlands while sosed only has perlands that were simulated
    # in other words information from sosed is a subset of schematic
    for tvolno in lakeflag.index.intersection(uci.opnid_dict['RCHRES'].index): #schematic['TVOLNO'].unique():
        implnd_load = 0
        prlnd_load = 0
        reach_load = depscr.loc[tvolno].values[0]
        schem_sub = schematic[schematic['TVOLNO'] == tvolno]
        if len(schem_sub) == 0:
            scour_report.append((tvolno,np.nan,reach_load))
        else:
            #Only consider perlands that wer actually simulated in the model (binary flag in set to 0)
            # Calculate contributions from PERLNDS
            if 'PERLND' in schem_sub['SVOL'].values:
                schem_prlnd = schem_sub[schem_sub['SVOL'] == 'PERLND'].copy()
                sosed_match = [x for x in schem_prlnd['SVOLNO'] if x in sosed.index]
                schem_prlnd = schem_prlnd[schem_prlnd['SVOLNO'].isin(sosed_match)]
                sosed_sub = sosed.loc[sosed_match]
                prlnd_load = np.sum(schem_prlnd['AFACTR'].values*sosed_sub['mean'].values)#lb/yr
            
            # Calculate contributions from IMPLNDS
            if 'IMPLND' in schem_sub['SVOL'].values:
                schem_implnd = schem_sub[schem_sub['SVOL'] == 'IMPLND'].copy()
                sosld_match = [x for x in schem_implnd['SVOLNO'] if x in sosld.index]
                schem_implnd = schem_implnd[schem_implnd['SVOLNO'].isin(sosld_match)]
                sosld_sub = sosld.loc[sosld_match]
                implnd_load = np.sum(schem_implnd['AFACTR'].values*sosld_sub['mean'].values)#lb/yr
            
            watershed_load = prlnd_load + implnd_load
            scour_report.append((tvolno,watershed_load,reach_load))
    
    scour_report = pd.DataFrame(scour_report,columns = ['TVOLNO','nonpoint','depscour'])
    
    scour_report['ratio'] = scour_report['nonpoint']/(scour_report['nonpoint']+np.abs(scour_report['depscour']))
    
    scour_report = pd.merge(lakeflag, scour_report, left_index=True, right_on='TVOLNO').set_index('TVOLNO')
    return scour_report  


def annual_sediment_budget(uci,hbn):
    """Compute the area-weighted annual sediment budget by land cover.

    Combines PERLND (SOSED) and IMPLND (SOSLD) sediment outputs into
    a percentage breakdown by land-cover type.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``Sediment`` (weighted output) and ``Percentage``
        (percent of total), indexed by land cover and AFACTR.
    """
    ts_names = ['SOSED']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,'PERLND', group_by='landcover')  for ts_name in ts_names],axis = 1)

    ts_names = ['SOSLD']
    sosld = pd.concat([annual_weighted_output(uci,hbn,ts_name,'IMPLND',group_by='landcover') for ts_name in ts_names],axis = 1)
    sosld.columns = ['SOSED']
    
    df = pd.concat([df,sosld])
    df.fillna(0, inplace=True)
    df['Percentage'] = 100*(df['SOSED']*df.index.get_level_values('AFACTR')/sum(df['SOSED']*df.index.get_level_values('AFACTR')))
    
    df.columns = ['Sediment','Percentage']
    return df

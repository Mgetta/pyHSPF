# -*- coding: utf-8 -*-
"""
Hydrology reports — water balance, precipitation, ET, runoff, and meteorological data.
"""
import pandas as pd

from hspf.reports.utils import annual_weighted_output


def pevt_balance(mod,operation,opnid):
    """Compute annual precipitation and potential ET balance for an operation.

    Parameters
    ----------
    mod : hspfModel
        Model object providing access to UCI and WDM data.
    operation : str
        Operation type (e.g. ``'PERLND'``, ``'IMPLND'``).
    opnid : int
        Operation ID.

    Returns
    -------
    pd.DataFrame
        Annual timeseries with columns ``PREC`` and ``PEVT``, filtered
        to positive values only.
    """
    extsources = mod.uci.table('EXT SOURCES')
    
    pevt_dsn = mod.uci.get_dsns(operation,opnid,'PEVT').reset_index()
    pevt_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PEVT'),'MFACTOR'].iat[0]
    pevt = mod.wdms.series(pevt_dsn.loc[0,'FILENAME'],pevt_dsn.loc[0,'SVOLNO'])
    
    prec_dsn = mod.uci.get_dsns(operation,opnid,'PREC').reset_index()
    prec_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PREC'),'MFACTOR'].iat[0]
    prec = mod.wdms.series(prec_dsn.loc[0,'FILENAME'],prec_dsn.loc[0,'SVOLNO'])

    df = pd.concat([(prec*prec_mfactor).resample('Y').sum(),
               (pevt*pevt_mfactor).resample('Y').sum()],axis=1)
    df = df[df>0]
    df.columns = ['PREC','PEVT']
    return df


def simulated_et(uci,hbn):
    """Compute area-weighted simulated ET for all operations.

    Aggregates actual ET from PERLNDs (TAET), IMPLNDs (IMPEV), and
    RCHRESs (VOLEV) into a single table.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``OPNID``, ``Operation``, ``PET``.
    """
    
    
    #simulate ET from perlnds
    taet = hbn.get_multiple_timeseries(t_opn='PERLND', 
                                       t_con='TAET', 
                                       t_code = 'yearly', 
                                       activity = 'PWATER').mean().to_frame().rename(columns = {0:'EVAP'})
    taet['Operation'] = 'PERLND' # without specifying the opnid, it grabs them all. 
    taet = taet.join(uci.network.operation_area('PERLND'))
    taet['PET'] = taet['EVAP']*taet['AFACTR']/12
    taet = taet.reset_index().rename(columns = {'index' : 'OPNID'})[['OPNID','Operation','PET']]

    #simulate ET from implnds
    impev = hbn.get_multiple_timeseries(t_opn='IMPLND', 
                                       t_con='IMPEV', 
                                       t_code = 'yearly').mean().to_frame().rename(columns = {0:'EVAP'})
    impev['Operation'] = 'IMPLND' # without specifying the opnid, it grabs them all. 
    impev = impev.join(uci.network.operation_area('IMPLND'))
    impev['PET'] = impev['EVAP']*impev['AFACTR']/12
    impev = impev.reset_index().rename(columns = {'index' : 'OPNID'})[['OPNID','Operation','PET']]
        
    # sum of agwo for each perlnd 
    volev = hbn.get_multiple_timeseries(t_opn='RCHRES', t_con='VOLEV', t_code = 'yearly').mean().to_frame().rename(columns = {0:'PET'})
    volev['Operation'] = 'RCHRES'
    volev = volev.reset_index().rename(columns = {'index' : 'OPNID'})
    
    return pd.concat([taet,impev,volev])
    


def inflows(uci,wdm): 
    """Retrieve external inflow timeseries from WDM sources.

    Reads EXT SOURCES entries for ``'ROVL'`` or ``'Flow'`` and computes
    mean annual inflow volumes.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    wdm : wdmInterface
        WDM data-file interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``OPNID``, ``Operation``, ``ROVL``.  Empty DataFrame if
        no matching external sources exist.
    """
    # External inflows
    files = uci.table('FILES')
    ext_sources = uci.table('EXT SOURCES')

    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND','IMPLND','RCHRES']))]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    ext_sources = ext_sources[ext_sources['SMEMN'].isin(['ROVL','Flow'])]
    
    if len(ext_sources) == 0:
        _inflows = pd.DataFrame(columns = ['OPNID','Operation','ROVL'])
    else:
    
        dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
        dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
        dsns['ROVL'] = pd.concat(dfs,axis=1).resample('Y').sum().mean()
        
        
        _inflows = ext_sources.merge(dsns,left_on='SVOLNO',
                          right_on = 'SVOLNO')[['TOPFST','TVOL','ROVL']].rename(columns = {'TOPFST':'OPNID','TVOL':'Operation'})
    return _inflows
    
def water_balance(uci,hbn,wdm,reach_ids):
    """Compute a water balance for each outlet reach.

    Combines precipitation, external inflows, simulated ET, and reach
    outflow volumes to compute a percent balance error.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    wdm : wdmInterface
        WDM data-file interface.
    reach_ids : list of int
        Outlet reach IDs to evaluate.

    Returns
    -------
    pd.DataFrame
        Columns: ``reach_id``, ``precip``, ``inflow``, ``saet``,
        ``rovol``, ``balance`` (percent error).
    """
    
    areas = []
    for operation in ['PERLND','IMPLND','RCHRES']:
        area = uci.network.operation_area(operation).reset_index()
        area.loc[:,'Operation'] = operation
        areas.append(area)
    areas = pd.concat(areas).set_index(['Operation','SVOLNO'])
    areas.index.names = ['Operation','OPNID']
    
    pets = simulated_et(uci,hbn)
    _inflows = inflows(uci,wdm)
    precips = avg_annual_precip(uci,wdm)
    precips = precips.set_index(['Operation','OPNID']).join(areas)
    precips['PREC'] = precips['avg_ann_prec'] / 12 * precips['AFACTR']
    precips.reset_index(inplace=True)
    rovols = hbn.get_multiple_timeseries(opnids = reach_ids,t_opn='RCHRES', t_con='ROVOL', t_code = 'yearly').mean().to_frame()
    
    rows = []
    for outlet in reach_ids:
        precip = 0
        inflow = 0
        pet = 0
        for operation in ['PERLND','IMPLND','RCHRES']:
            opnids = uci.network.get_opnids(operation,outlet)
            precip = precip + precips.loc[(precips['Operation'] == operation) & (precips['OPNID'].isin(opnids))]['PREC'].sum()
            inflow = inflow + _inflows.loc[(_inflows['Operation'] == operation) & (_inflows['OPNID'].isin(opnids))]['ROVL'].sum()
            pet = pet + pets.loc[(pets['Operation'] == operation) & (pets['OPNID'].isin(opnids))]['PET'].sum()
            rovol = rovols.loc[outlet].sum()
        balance = ((precip-pet)-(rovol - inflow))/(precip-pet)*100

        rows.append([outlet,precip,inflow,pet,rovol,balance])
    return pd.DataFrame(rows,columns = ['reach_id','precip','inflow','saet','rovol','balance'])
    

def meteorlogical(uci,wdm,operation,ts_name,time_step = 'Y',opnids = None,):
    """Retrieve meteorological timeseries from WDM external sources.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    wdm : wdmInterface
        WDM data-file interface.
    operation : str
        Target operation type (e.g. ``'PERLND'``).
    ts_name : str
        Timeseries member name (e.g. ``'PREC'``, ``'PEVT'``).
    time_step : str, optional
        Pandas resample frequency string (default ``'Y'``).
    opnids : list of int or None, optional
        Operation IDs to filter.  ``None`` returns all.

    Returns
    -------
    pd.DataFrame
        Resampled meteorological data with operation IDs as columns.
    """
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM','WDM1',inplace=True)
    
    # Total preciptiation
    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM','WDM1',inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'] == operation) & (ext_sources['SMEMN'] == ts_name)]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
    dfs = [df.loc[df>=0] for df in dfs]
    df = pd.concat(dfs,axis=1).resample(time_step).sum()
    df.columns = dsns['SVOLNO']
    
    df = df[ext_sources['SVOLNO']]
    df.columns = ext_sources['TOPFST']
    
    if opnids is not None:
        df = df[opnids]
        
    return df
    

def avg_annual_precip(uci,wdm):
    """Compute average annual precipitation for all operations.

    Reads precipitation timeseries from WDM external sources and computes
    the mean annual total for each DSN/operation/OPNID combination.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    wdm : wdmInterface
        WDM data-file interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``DSN``, ``Operation``, ``OPNID``, ``avg_ann_prec``.
    """
    
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM','WDM1',inplace=True)
    
    # Total preciptiation
    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM','WDM1',inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND','IMPLND','RCHRES'])) & (ext_sources['SMEMN'] == 'PREC')]
    ext_sources = ext_sources.merge(files, left_on = 'SVOL',
                       right_on= 'FTYPE', 
                       how = 'left')   
    
    dsns = ext_sources[['SVOLNO','FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index,row in dsns.iterrows()]
    dfs = [df.loc[df>=0] for df in dfs]
    df = pd.concat(dfs,axis=1).resample('Y').sum().mean()
   
    dsns['avg_ann_prec'] = pd.concat(dfs,axis=1).resample('Y').sum().mean()
    df = ext_sources.merge(dsns,left_on = 'SVOLNO',
                      right_on = 'SVOLNO',
                      how = 'left')
    df = df[['SVOLNO','TVOL','TOPFST','avg_ann_prec']]
    df.rename(columns = {'SVOLNO':'DSN','TVOL':'Operation','TOPFST':'OPNID'}, inplace=True)
    
    return df


def annual_perlnd_runoff(uci,hbn,opnids = None,start_year=1996,end_year=2100):
    """Compute area-weighted annual PERLND runoff components.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    opnids : list of int or None, optional
        PERLND IDs to include.  ``None`` includes all.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Columns: ``PRECIP``, ``PERO``, ``AGWO``, ``IFWO``, ``SURO``,
        ``suro_perc`` (surface runoff as percent of total runoff).
    """
    ts_names = ['PRECIP','PERO','AGWO','IFWO','SURO']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,group_by='landcover',opnids=opnids,start_year=start_year,end_year=end_year) for ts_name in ts_names],axis = 1)
    df.columns = ts_names
    df['suro_perc'] = (df['SURO']/df['PERO'])*100
    return df


def annual_reach_water_budget(uci,hbn):
    """Compute the mean annual water budget for all RCHRES operations.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``OPNID``, ``LKFG``, ``PRSUPY``, ``IVOL``, ``ROVOL``,
        ``VOLEV``, ``ROVOL_Input`` (sum of upstream ROVOL).
    """
    ts_names = ['PRSUPY','IVOL','ROVOL','VOLEV']
    df = pd.concat([hbn.get_multiple_timeseries('RCHRES',5,ts_name).mean() for ts_name in ts_names],axis=1)
    df.columns = ts_names
    geninfo = uci.table('RCHRES','GEN-INFO')[['LKFG']]
    reach_intersection = geninfo.index.intersection(df.index)
    
    
    df = geninfo.loc[reach_intersection].join(df.loc[reach_intersection])
    
    
    df['ROVOL_Input'] = 0.
    
    for reach_id in df.index:
        if reach_id in uci.network.G.nodes:
            upstream_ids = uci.network.upstream(reach_id)
            if len(upstream_ids) > 0:
                df.loc[reach_id,'ROVOL_Input'] = df.loc[upstream_ids]['ROVOL'].sum()
            
    df.index.name = 'OPNID'
    return df.reset_index()

def perlnd_water_budget(uci,hbn,time_step = 5,start_year = 1996,end_year = 2100):
    """Compute the mean PERLND water budget over a year range.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Returns
    -------
    pd.DataFrame
        Columns: ``PRECIP``, ``SURO``, ``IFWO``, ``AGWO``, ``PERO``,
        ``TAET``.
    """
    ts_names = ['PRECIP','SURO','IFWO','AGWO','PERO','TAET']
    df = pd.concat([hbn.get_multiple_timeseries('PERLND',time_step,ts_name).loc[lambda x: (x.index.year >= start_year) & (x.index.year <= end_year)].mean() for ts_name in ts_names],axis=1)
    df.columns = ts_names
    return df

def annual_implnd_water_budget(uci,hbn):
    """Compute the mean annual IMPLND water budget.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``SUPY``, ``SURO``, ``IMPEV``.
    """
    ts_names = ['SUPY','SURO','IMPEV']
    df = pd.concat([hbn.get_multiple_timeseries('IMPLND',5,ts_name).mean() for ts_name in ts_names],axis=1)
    df.columns = ts_names
    return df

def annual_perlnd_water_budget(uci,hbn):
    """Compute the area-weighted annual PERLND water budget by land cover.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.

    Returns
    -------
    pd.DataFrame
        Columns: ``PRECIP``, ``TAET``, ``PERO``, indexed by land cover
        and AFACTR.
    """
    ts_names = ['PRECIP','TAET','PERO']
    df = pd.concat([annual_weighted_output(uci,hbn,ts_name,group_by='landcover') for ts_name in ts_names],axis = 1)
    df.columns = ts_names
    return df

def watershed_water_budget(uci,hbn,reach_ids,upstream_reach_ids = None, time_step = 5, by_landcover = True):
    """Compute a combined watershed water budget.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    reach_ids : list of int
        Reach IDs defining the watershed.
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    by_landcover : bool, optional
        If True, break out by land-cover type.

    Raises
    ------
    NotImplementedError
        This function is not yet implemented.
    """
    
    raise NotImplementedError("This function is not yet implemented. It will combine the reach, implnd, and perlnd water budgets for a given set of reaches and their upstream reaches.")   

def metzone_watershed_budget(uci,hbn,operation = None):
    """Compute a watershed water budget grouped by meteorological zone.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    operation : str or None, optional
        Operation type filter.

    Raises
    ------
    NotImplementedError
        This function is not yet implemented.
    """
    raise NotImplementedError("This function is not yet implemented. It will combine the reach, implnd, and perlnd water budgets for a given metzone or set of metzones.")


def catchment_precipitation(uci,hbn,time_step = 5, start_year = 1996, end_year = 2100):
    """Compute average annual precipitation for each catchment.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).

    Raises
    ------
    NotImplementedError
        This function is not yet implemented.
    """
    raise NotImplementedError("This function is not yet implemented. It will calculate the average annual precipitation for each catchment, potentially grouped by landcover or other attributes.")
# -*- coding: utf-8 -*-
"""
Hydrology-related reports.

Contains functions for water budget, runoff, precipitation, and ET reports.
"""
import pandas as pd

from .utils import weighted_mean


def landcover_areas(uci):
    """Get landcover areas from the model.
    
    Args:
        uci: UCI object containing model configuration
        
    Returns:
        DataFrame with landcover areas and percentages
    """
    df = uci.network.operation_area('PERLND').groupby('LSID').sum()
    df['percent'] = 100 * (df['AFACTR'] / df['AFACTR'].sum())
    return df


def annual_weighted_output(uci, hbn, ts_name, operation='PERLND', opnids=None, group_by=None):
    """Calculate annual weighted output for a time series.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        ts_name: Time series name
        operation: Operation type ('PERLND', 'IMPLND', etc.)
        opnids: Optional list of operation IDs
        group_by: Grouping option (None, 'landcover', 'opnid')
        
    Returns:
        DataFrame with weighted output
    """
    assert group_by in [None, 'landcover', 'opnid']
    df = hbn.get_multiple_timeseries(operation, 5, ts_name, opnids=opnids).mean().reset_index()
    df.columns = ['SVOLNO', ts_name]
    subwatersheds = uci.network.subwatersheds().reset_index()
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'] == operation]

    df = pd.merge(subwatersheds, df, left_on='SVOLNO', right_on='SVOLNO', how='left')

    if group_by is None:
        df = weighted_mean(df, ts_name, 'AFACTR')
    elif group_by == 'landcover':
        df = df.groupby('LSID')[[ts_name, 'AFACTR']].apply(lambda x: weighted_mean(x, ts_name, 'AFACTR')).droplevel(1)
    elif group_by == 'opnid':
        df = df.groupby(df['SVOLNO'])[[ts_name, 'AFACTR']].apply(lambda x: weighted_mean(x, ts_name, 'AFACTR')).droplevel(1)

    df = df.set_index([df.index, 'AFACTR'])
    return df


def monthly_weighted_output(uci, hbn, ts_name, operation='PERLND', opnids=None, as_rate=False, by_landcover=True, months=None):
    """Calculate monthly weighted output for a time series.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        ts_name: Time series name
        operation: Operation type
        opnids: Optional list of operation IDs
        as_rate: Whether to return as rate
        by_landcover: Whether to group by landcover
        months: List of months to include
        
    Returns:
        DataFrame with monthly weighted output
    """
    if months is None:
        months = list(range(1, 13))
        
    df = hbn.get_multiple_timeseries(operation, 4, ts_name, opnids=opnids)
    df = df.loc[df.index.month.isin(months)]

    areas = uci.network.operation_area(operation)
    areas.loc[areas.index.intersection(df.columns)]
    df = df[areas.index.intersection(df.columns)]

    df = (df.groupby(df.index.month).mean() * areas['AFACTR'])

    if by_landcover:
        df = df.T.groupby(areas['LSID']).sum().T
        if as_rate:
            df = df / areas['AFACTR'].groupby(areas['LSID']).sum().to_list()
    else:
        if as_rate:
            df = df / areas['AFACTR'].sum()

    df.columns.name = ts_name

    return df


def monthly_perlnd_runoff(uci, hbn):
    """Calculate monthly PERLND runoff.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with monthly runoff by component
    """
    ts_names = ['PRECIP', 'PERO', 'AGWO', 'IFWO', 'SURO']
    df = pd.concat({ts_name: monthly_weighted_output(uci, hbn, ts_name, by_landcover=True, as_rate=True) for ts_name in ts_names}, keys=ts_names)
    suro_perc = (df.loc['SURO'] / df.loc['PERO']) * 100
    suro_perc = suro_perc.reset_index()
    suro_perc['name'] = 'SURO_perc'
    suro_perc = suro_perc.set_index(['name', 'index'])
    return pd.concat([df, suro_perc])


def annual_perlnd_runoff(uci, hbn):
    """Calculate annual PERLND runoff.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with annual runoff by component
    """
    ts_names = ['PRECIP', 'PERO', 'AGWO', 'IFWO', 'SURO']
    df = pd.concat([annual_weighted_output(uci, hbn, ts_name, group_by='landcover') for ts_name in ts_names], axis=1)
    df.columns = ts_names
    df['suro_perc'] = (df['SURO'] / df['PERO']) * 100
    return df


def annual_reach_water_budget(uci, hbn):
    """Calculate annual reach water budget.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with reach water budget
    """
    ts_names = ['PRSUPY', 'IVOL', 'ROVOL', 'VOLEV']
    df = pd.concat([hbn.get_multiple_timeseries('RCHRES', 5, ts_name).mean() for ts_name in ts_names], axis=1)
    df.columns = ts_names
    
    geninfo = uci.table('RCHRES', 'GEN-INFO')[['LKFG']]
    reach_intersection = geninfo.index.intersection(df.index)

    df = geninfo.loc[reach_intersection].join(df.loc[reach_intersection])

    df['ROVOL_Input'] = 0.

    for reach_id in df.index:
        if reach_id in uci.network.G.nodes:
            upstream_ids = uci.network.upstream(reach_id)
            if len(upstream_ids) > 0:
                df.loc[reach_id, 'ROVOL_Input'] = df.loc[upstream_ids]['ROVOL'].sum()

    df.index.name = 'OPNID'
    return df.reset_index()


def annual_implnd_water_budget(uci, hbn):
    """Calculate annual IMPLND water budget.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with IMPLND water budget
    """
    ts_names = ['SUPY', 'SURO', 'IMPEV']
    df = pd.concat([hbn.get_multiple_timeseries('IMPLND', 5, ts_name).mean() for ts_name in ts_names], axis=1)
    df.columns = ts_names
    return df


def annual_perlnd_water_budget(uci, hbn):
    """Calculate annual PERLND water budget.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with PERLND water budget
    """
    ts_names = ['PRECIP', 'TAET', 'PERO']
    df = pd.concat([annual_weighted_output(uci, hbn, ts_name, group_by='landcover') for ts_name in ts_names], axis=1)
    df.columns = ts_names
    return df


def simulated_et(uci, hbn):
    """Calculate simulated evapotranspiration.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        
    Returns:
        DataFrame with simulated ET by operation
    """
    # Simulate ET from perlnds
    taet = hbn.get_multiple_timeseries(t_opn='PERLND',
                                       t_con='TAET',
                                       t_code='yearly',
                                       activity='PWATER').mean().to_frame().rename(columns={0: 'EVAP'})
    taet['Operation'] = 'PERLND'
    taet = taet.join(uci.network.operation_area('PERLND'))
    taet['PET'] = taet['EVAP'] * taet['AFACTR'] / 12
    taet = taet.reset_index().rename(columns={'index': 'OPNID'})[['OPNID', 'Operation', 'PET']]

    # Simulate ET from implnds
    impev = hbn.get_multiple_timeseries(t_opn='IMPLND',
                                        t_con='IMPEV',
                                        t_code='yearly').mean().to_frame().rename(columns={0: 'EVAP'})
    impev['Operation'] = 'IMPLND'
    impev = impev.join(uci.network.operation_area('IMPLND'))
    impev['PET'] = impev['EVAP'] * impev['AFACTR'] / 12
    impev = impev.reset_index().rename(columns={'index': 'OPNID'})[['OPNID', 'Operation', 'PET']]

    # Sum of agwo for each perlnd
    volev = hbn.get_multiple_timeseries(t_opn='RCHRES', t_con='VOLEV', t_code='yearly').mean().to_frame().rename(columns={0: 'PET'})
    volev['Operation'] = 'RCHRES'
    volev = volev.reset_index().rename(columns={'index': 'OPNID'})

    return pd.concat([taet, impev, volev])


def subwatershed_weighted_output(uci, hbn, reach_ids, ts_name, time_step, by_landcover=False, as_rate=True):
    """Calculate subwatershed weighted output.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        reach_ids: List of reach IDs
        ts_name: Time series name
        time_step: Time step code
        by_landcover: Whether to group by landcover
        as_rate: Whether to return as rate
        
    Returns:
        DataFrame or Series with subwatershed weighted output
    """
    subwatersheds = uci.network.subwatersheds(reach_ids)
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']

    areas = subwatersheds[['SVOLNO', 'AFACTR']].set_index('SVOLNO')
    areas = areas.join(uci.table('PERLND', 'GEN-INFO')['LSID'])
    opnids = subwatersheds['SVOLNO'].to_list()

    df = hbn.get_multiple_timeseries('PERLND', time_step, ts_name, opnids=opnids)

    areas.loc[areas.index.intersection(df.columns)]
    df = df[areas.index.intersection(df.columns)]

    if by_landcover:
        df = (df * areas['AFACTR'].values).T.groupby(areas['LSID']).sum()
        if as_rate:
            df = df.T / areas['AFACTR'].groupby(areas['LSID']).sum().to_list()
        df.columns.name = ts_name
    else:
        df = (df * areas['AFACTR'].values).sum(axis=1)
        if as_rate:
            df = df / areas['AFACTR'].sum()
        df.name = ts_name

    return df


def meteorological(uci, wdm, operation, ts_name, time_step='Y', opnids=None):
    """Get meteorological data.
    
    Args:
        uci: UCI object containing model configuration
        wdm: WDM interface object
        operation: Operation type
        ts_name: Time series name
        time_step: Time step for resampling
        opnids: Optional list of operation IDs
        
    Returns:
        DataFrame with meteorological data
    """
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM', 'WDM1', inplace=True)

    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM', 'WDM1', inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'] == operation) & (ext_sources['SMEMN'] == ts_name)]
    ext_sources = ext_sources.merge(files, left_on='SVOL',
                                    right_on='FTYPE',
                                    how='left')

    dsns = ext_sources[['SVOLNO', 'FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index, row in dsns.iterrows()]
    dfs = [df.loc[df >= 0] for df in dfs]
    df = pd.concat(dfs, axis=1).resample(time_step).sum()
    df.columns = dsns['SVOLNO']

    df = df[ext_sources['SVOLNO']]
    df.columns = ext_sources['TOPFST']

    if opnids is not None:
        df = df[opnids]

    return df


def avg_annual_precip(uci, wdm):
    """Calculate average annual precipitation.
    
    Args:
        uci: UCI object containing model configuration
        wdm: WDM interface object
        
    Returns:
        DataFrame with average annual precipitation
    """
    files = uci.table('FILES')
    files['FTYPE'].replace('WDM', 'WDM1', inplace=True)

    ext_sources = uci.table('EXT SOURCES')
    ext_sources['SVOL'].replace('WDM', 'WDM1', inplace=True)
    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND', 'IMPLND', 'RCHRES'])) & (ext_sources['SMEMN'] == 'PREC')]
    ext_sources = ext_sources.merge(files, left_on='SVOL',
                                    right_on='FTYPE',
                                    how='left')

    dsns = ext_sources[['SVOLNO', 'FILENAME']].drop_duplicates().reset_index(drop=True)
    dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index, row in dsns.iterrows()]
    dfs = [df.loc[df >= 0] for df in dfs]
    df = pd.concat(dfs, axis=1).resample('Y').sum().mean()

    dsns['avg_ann_prec'] = pd.concat(dfs, axis=1).resample('Y').sum().mean()
    df = ext_sources.merge(dsns, left_on='SVOLNO',
                           right_on='SVOLNO',
                           how='left')
    df = df[['SVOLNO', 'TVOL', 'TOPFST', 'avg_ann_prec']]
    df.rename(columns={'SVOLNO': 'DSN', 'TVOL': 'Operation', 'TOPFST': 'OPNID'}, inplace=True)

    return df


def pevt_balance(mod, operation, opnid):
    """Calculate potential evapotranspiration balance.
    
    Args:
        mod: Model object
        operation: Operation type
        opnid: Operation ID
        
    Returns:
        DataFrame with PREC and PEVT values
    """
    extsources = mod.uci.table('EXT SOURCES')

    pevt_dsn = mod.uci.get_dsns(operation, opnid, 'PEVT').reset_index()
    pevt_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PEVT'), 'MFACTOR'].iat[0]
    pevt = mod.wdms.series(pevt_dsn.loc[0, 'FILENAME'], pevt_dsn.loc[0, 'SVOLNO'])

    prec_dsn = mod.uci.get_dsns(operation, opnid, 'PREC').reset_index()
    prec_mfactor = extsources.loc[(extsources['TOPFST'] == opnid) &
                                  (extsources['TVOL'] == operation) &
                                  (extsources['SMEMN'] == 'PREC'), 'MFACTOR'].iat[0]
    prec = mod.wdms.series(prec_dsn.loc[0, 'FILENAME'], prec_dsn.loc[0, 'SVOLNO'])

    df = pd.concat([(prec * prec_mfactor).resample('Y').sum(),
                    (pevt * pevt_mfactor).resample('Y').sum()], axis=1)
    df = df[df > 0]
    df.columns = ['PREC', 'PEVT']
    return df


def inflows(uci, wdm):
    """Calculate external inflows.
    
    Args:
        uci: UCI object containing model configuration
        wdm: WDM interface object
        
    Returns:
        DataFrame with external inflows
    """
    files = uci.table('FILES')
    ext_sources = uci.table('EXT SOURCES')

    ext_sources = ext_sources.loc[(ext_sources['TVOL'].isin(['PERLND', 'IMPLND', 'RCHRES']))]
    ext_sources = ext_sources.merge(files, left_on='SVOL',
                                    right_on='FTYPE',
                                    how='left')

    ext_sources = ext_sources[ext_sources['SMEMN'].isin(['ROVL', 'Flow'])]

    if len(ext_sources) == 0:
        inflows_df = pd.DataFrame(columns=['OPNID', 'Operation', 'ROVL'])
    else:
        dsns = ext_sources[['SVOLNO', 'FILENAME']].drop_duplicates().reset_index(drop=True)
        dfs = [wdm.wdms[row['FILENAME']].series(row['SVOLNO']) for index, row in dsns.iterrows()]
        dsns['ROVL'] = pd.concat(dfs, axis=1).resample('Y').sum().mean()

        inflows_df = ext_sources.merge(dsns, left_on='SVOLNO',
                                       right_on='SVOLNO')[['TOPFST', 'TVOL', 'ROVL']].rename(columns={'TOPFST': 'OPNID', 'TVOL': 'Operation'})
    return inflows_df


def water_balance(uci, hbn, wdm, reach_ids):
    """Calculate water balance for reaches.
    
    Args:
        uci: UCI object containing model configuration
        hbn: HBN interface object
        wdm: WDM interface object
        reach_ids: List of reach IDs
        
    Returns:
        DataFrame with water balance results
    """
    areas = []
    for operation in ['PERLND', 'IMPLND', 'RCHRES']:
        area = uci.network.operation_area(operation).reset_index()
        area.loc[:, 'Operation'] = operation
        areas.append(area)
    areas = pd.concat(areas).set_index(['Operation', 'SVOLNO'])
    areas.index.names = ['Operation', 'OPNID']

    pets = simulated_et(uci, hbn)
    _inflows = inflows(uci, wdm)
    precips = avg_annual_precip(uci, wdm)
    precips = precips.set_index(['Operation', 'OPNID']).join(areas)
    precips['PREC'] = precips['avg_ann_prec'] / 12 * precips['AFACTR']
    precips.reset_index(inplace=True)
    
    rovols = hbn.get_multiple_timeseries(opnids=reach_ids, t_opn='RCHRES', t_con='ROVOL', t_code='yearly').mean().to_frame()

    rows = []
    for outlet in reach_ids:
        precip = 0
        inflow = 0
        pet = 0
        for operation in ['PERLND', 'IMPLND', 'RCHRES']:
            opnids = uci.network.get_opnids(operation, outlet)
            precip = precip + precips.loc[(precips['Operation'] == operation) & (precips['OPNID'].isin(opnids))]['PREC'].sum()
            inflow = inflow + _inflows.loc[(_inflows['Operation'] == operation) & (_inflows['OPNID'].isin(opnids))]['ROVL'].sum()
            pet = pet + pets.loc[(pets['Operation'] == operation) & (pets['OPNID'].isin(opnids))]['PET'].sum()
            rovol = rovols.loc[outlet].sum()
        balance = ((precip - pet) - (rovol - inflow)) / (precip - pet) * 100

        rows.append([outlet, precip, inflow, pet, rovol, balance])
    return pd.DataFrame(rows, columns=['reach_id', 'precip', 'inflow', 'saet', 'rovol', 'balance'])

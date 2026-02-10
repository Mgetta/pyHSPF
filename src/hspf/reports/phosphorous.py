# -*- coding: utf-8 -*-
"""
Phosphorous-specific reports.

Contains functions for calculating phosphorous loading and allocations.
"""
import pandas as pd


MASSLINK_SCHEME = {
    'dissolved_orthophosphate': {
        'tmemn': 'NUIF1',
        'tmemsb1': '4',
        'tmemsb2': ''
    },
    'particulate_orthophosphate_sand': {
        'tmemn': 'NUIF2',
        'tmemsb1': '1',
        'tmemsb2': '2'
    },
    'particulate_orthophosphate_silt': {
        'tmemn': 'NUIF2',
        'tmemsb1': '2',
        'tmemsb2': '2'
    },
    'particulate_orthophosphate_clay': {
        'tmemn': 'NUIF2',
        'tmemsb1': '3',
        'tmemsb2': '2'
    },
    'organic_refactory_phosphorous': {
        'tmemn': 'PKIF',
        'tmemsb1': '4',
        'tmemsb2': ''
    },
    'organic_refactory_carbon': {
        'tmemn': 'PKIF',
        'tmemsb1': '5',
        'tmemsb2': ''
    },
    'labile_oxygen_demand': {
        'tmemn': 'OXIF',
        'tmemsb1': '2',
        'tmemsb2': ''
    }
}


def qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2='', t_code=4):
    """Transform quality properties from masslink.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        tmemn: Target member name
        tmemsb1: Target member subscript 1
        tmemsb2: Target member subscript 2
        t_code: Time code
        
    Returns:
        DataFrame with transformed data
    """
    masslink = uci.table('MASS-LINK', f'MASS-LINK{mlno}')
    masslink = masslink.loc[(masslink['TMEMN'] == tmemn) & (masslink['TMEMSB1'] == tmemsb1) & (masslink['TMEMSB2'] == tmemsb2)]
    ts = 0
    for index, row in masslink.iterrows():
        hbn_name = uci.table('PERLND', 'QUAL-PROPS', int(row['SMEMSB1']) - 1).iloc[0]['QUALID']
        hbn_name = row['SMEMN'] + hbn_name
        mfactor = row['MFACTOR']
        ts = hbn.get_multiple_timeseries(row['SVOL'], t_code, hbn_name) * mfactor + ts
    return ts


def dissolved_orthophosphate(uci, hbn, mlno, t_code=4):
    """Calculate dissolved orthophosphate.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with dissolved orthophosphate
    """
    tmemn = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['dissolved_orthophosphate']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def particulate_orthophosphate(uci, hbn, mlno, t_code=4):
    """Calculate total particulate orthophosphate.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with particulate orthophosphate
    """
    ts = (particulate_orthophosphate_sand(uci, hbn, mlno, t_code) +
          particulate_orthophosphate_silt(uci, hbn, mlno, t_code) +
          particulate_orthophosphate_clay(uci, hbn, mlno, t_code))
    return ts


def particulate_orthophosphate_sand(uci, hbn, mlno, t_code=4):
    """Calculate particulate orthophosphate on sand.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with particulate orthophosphate on sand
    """
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_sand']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def particulate_orthophosphate_silt(uci, hbn, mlno, t_code=4):
    """Calculate particulate orthophosphate on silt.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with particulate orthophosphate on silt
    """
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_silt']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def particulate_orthophosphate_clay(uci, hbn, mlno, t_code=4):
    """Calculate particulate orthophosphate on clay.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with particulate orthophosphate on clay
    """
    tmemn = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['particulate_orthophosphate_clay']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def organic_refactory_phosphorous(uci, hbn, mlno, t_code=4):
    """Calculate organic refractory phosphorous.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with organic refractory phosphorous
    """
    tmemn = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_phosphorous']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def organic_refactory_carbon(uci, hbn, mlno, t_code=4):
    """Calculate organic refractory carbon.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with organic refractory carbon
    """
    tmemn = MASSLINK_SCHEME['organic_refactory_carbon']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['organic_refactory_carbon']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def labile_oxygen_demand(uci, hbn, mlno, t_code=4):
    """Calculate labile oxygen demand.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        mlno: Mass link number
        t_code: Time code
        
    Returns:
        DataFrame with labile oxygen demand
    """
    tmemn = MASSLINK_SCHEME['labile_oxygen_demand']['tmemn']
    tmemsb1 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME['labile_oxygen_demand']['tmemsb2']
    return qualprop_transform(uci, hbn, mlno, tmemn, tmemsb1, tmemsb2, t_code)


def total_phosphorous(uci, hbn, t_code):
    """Calculate total phosphorous loading.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        t_code: Time code
        
    Returns:
        DataFrame with total phosphorous loading
    """
    perlnds = uci.network.subwatersheds()
    perlnds = perlnds.loc[perlnds['SVOL'] == 'PERLND'].drop_duplicates(subset=['SVOLNO', 'MLNO'])

    totals = []
    for mlno in perlnds['MLNO'].unique():
        perlnd_ids = perlnds['SVOLNO'].loc[perlnds['MLNO'] == mlno].to_list()
        total = (dissolved_orthophosphate(uci, hbn, mlno, t_code) +
                 particulate_orthophosphate(uci, hbn, mlno, t_code) +
                 organic_refactory_phosphorous(uci, hbn, mlno, t_code) +
                 labile_oxygen_demand(uci, hbn, mlno, t_code) * 0.007326)  # Conversion factor to P
        totals.append(total[perlnd_ids])

    total = pd.concat(totals, axis=1)
    total = total.T.groupby(total.columns).sum().T
    return total


def subwatershed_total_phosphorous_loading(uci, hbn, reach_ids=None, t_code=5, as_load=True, group_landcover=True):
    """Calculate subwatershed total phosphorous loading.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        reach_ids: Optional list of reach IDs
        t_code: Time code
        as_load: Whether to return as load
        group_landcover: Whether to group by landcover
        
    Returns:
        DataFrame with subwatershed total phosphorous loading
    """
    tp_loading = total_phosphorous(uci, hbn, t_code)
    if reach_ids is None:
        subwatersheds = uci.network.subwatersheds()
    else:
        subwatersheds = uci.network.subwatersheds(reach_ids)

    perlnds = subwatersheds.loc[subwatersheds['SVOL'] == 'PERLND']
    perlnds = perlnds['AFACTR'].groupby([perlnds.index, perlnds['SVOLNO']]).sum().reset_index()

    total = tp_loading[perlnds['SVOLNO']]

    total = total.mul(perlnds['AFACTR'].values, axis=1)

    total = total.transpose()
    total['reach_id'] = perlnds['TVOLNO'].values
    total['landcover'] = uci.table('PERLND', 'GEN-INFO').loc[total.index, 'LSID'].to_list()
    total['area'] = perlnds['AFACTR'].to_list()
    total = total.reset_index().set_index(['index', 'landcover', 'area', 'reach_id']).transpose()
    total.columns.names = ['perlnd_id', 'landcover', 'area', 'reach_id']

    if group_landcover:
        total.columns = total.columns.droplevel(['landcover', 'perlnd_id'])
        total = total.T.reset_index().groupby('reach_id').sum().reset_index().set_index(['reach_id', 'area']).T

    if not as_load:
        total = total.div(total.columns.get_level_values('area').values, axis=1)

    total.index = pd.to_datetime(total.index)
    return total


def total_phosphorous_losses(uci, hbn, t_code=5):
    """Calculate total phosphorous losses.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        t_code: Time code
        
    Returns:
        DataFrame with total phosphorous loss factors
    """
    upstream_reachs = {reach_id: [reach_id] + uci.network.upstream(reach_id) for reach_id in uci.network.get_node_type_ids('RCHRES')}
    ptotout = hbn.get_multiple_timeseries('RCHRES', t_code, 'PTOTOUT', opnids=list(upstream_reachs.keys()))
    ptotin = pd.concat([ptotout[reach_ids].sum(axis=1) for reach_id, reach_ids in upstream_reachs.items()], axis=1)
    ptotin.columns = list(upstream_reachs.keys())
    return 1 - (ptotin - ptotout) / ptotin


def total_phosphorous_allocations(uci, hbn, reach_id, t_code=5, group_landcover=True):
    """Calculate total phosphorous allocations.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        reach_id: Reach ID
        t_code: Time code
        group_landcover: Whether to group by landcover
        
    Returns:
        DataFrame with total phosphorous allocations
    """
    p = uci.network.paths(reach_id)
    p[reach_id] = [reach_id]
    losses_df = total_phosphorous_losses(uci, hbn, t_code)
    loads = subwatershed_total_phosphorous_loading(uci, hbn, t_code=t_code, group_landcover=group_landcover)
    loss_factors = pd.concat([losses_df[v].prod(axis=1) for k, v in p.items()], axis=1)
    loss_factors.columns = list(p.keys())
    allocs = loads.mul(loss_factors[loads.columns.get_level_values('reach_id')].values)
    return allocs

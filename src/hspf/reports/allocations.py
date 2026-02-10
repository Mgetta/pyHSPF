# -*- coding: utf-8 -*-
"""
Allocation and fate analysis reports.

Contains functions for calculating constituent allocations, fate, and losses.
"""
import pandas as pd


ALLOCATION_SELECTOR = {
    'Q': {'input': ['IVOL'],
          'output': ['ROVOL']},
    'TP': {'input': ['PTOTIN'],
           'output': ['PTOTOUT']},
    'TSS': {'input': ['ISEDTOT'],
            'output': ['ROSEDTOT']},
    'OP': {'input': ['PO4INDIS'],
           'output': ['PO4OUTDIS']},
    'N': {'input': ['NO3INTOT', 'NO2INTOT'],
          'output': ['NO2OUTTOT', 'NO3OUTTOT']},
    'TKN': {'input': [],
            'output': ['TAMOUTTOT', 'NTOTORGOUT']}
}


def fate(hbn, constituent, t_code, reach_ids=None):
    """Calculate fate of a constituent.
    
    Args:
        hbn: HBN interface object
        constituent: Constituent name
        t_code: Time code
        reach_ids: Optional list of reach IDs
        
    Returns:
        DataFrame with fate ratios
    """
    if constituent == 'Q':
        fate_in = hbn.get_multiple_timeseries('RCHRES', t_code, 'ROVOL', opnids=reach_ids)
        fate_out = hbn.get_multiple_timeseries('RCHRES', t_code, 'IVOL', opnids=reach_ids)
    elif constituent == 'TP':
        fate_in = hbn.get_multiple_timeseries('RCHRES', t_code, 'PTOTOUT', opnids=reach_ids)
        fate_out = hbn.get_multiple_timeseries('RCHRES', t_code, 'PTOTIN', opnids=reach_ids)
    elif constituent == 'TSS':
        fate_in = hbn.get_multiple_timeseries('RCHRES', t_code, 'ISEDTOT', opnids=reach_ids)
        fate_out = hbn.get_multiple_timeseries('RCHRES', t_code, 'ROSEDTOT', opnids=reach_ids)
    return fate_out / fate_in


def losses(uci, hbn, constituent, t_code=5):
    """Calculate losses for a constituent.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        t_code: Time code
        
    Returns:
        DataFrame with loss percentages
    """
    upstream_reachs = {reach_id: uci.network.upstream(reach_id) for reach_id in uci.network.get_node_type_ids('RCHRES')}
    totout = sum([hbn.get_multiple_timeseries('RCHRES',
                                              t_code,
                                              t_cons,
                                              opnids=list(upstream_reachs.keys()))
                  for t_cons in ALLOCATION_SELECTOR[constituent]['output']])

    totin = sum([hbn.get_multiple_timeseries('RCHRES',
                                             t_code,
                                             t_cons,
                                             opnids=list(upstream_reachs.keys()))
                 for t_cons in ALLOCATION_SELECTOR[constituent]['input']])

    for reach_id in totin.columns:
        reach_ids = upstream_reachs[reach_id]
        if len(reach_ids) > 0:
            totin[reach_id] = totout[reach_ids].sum(axis=1)

    return (totout - totin) / totin * 100


def allocations(uci, hbn, constituent, reach_id, t_code, group_landcover=True):
    """Calculate allocations for a constituent.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        constituent: Constituent name
        reach_id: Reach ID
        t_code: Time code
        group_landcover: Whether to group by landcover
        
    Returns:
        DataFrame with allocations
    """
    from .loading import subwatershed_loading
    
    p = uci.network.paths(reach_id)
    p[reach_id] = [reach_id]
    loss = losses(uci, hbn, constituent, t_code)
    loads = subwatershed_loading(uci, hbn, constituent, t_code, group_landcover=group_landcover)
    loss_factors = pd.concat([loss[v].prod(axis=1) for k, v in p.items()], axis=1)
    loss_factors.columns = list(p.keys())
    allocs = loads.mul(loss_factors[loads.columns.get_level_values('reach_id')].values)
    return allocs


def flow_allocations(uci, hbn, reach_id, t_code=5):
    """Calculate flow allocations.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        reach_id: Reach ID
        t_code: Time code
        
    Raises:
        NotImplementedError: This function is not yet implemented
    """
    raise NotImplementedError()


def total_suspended_sediment_allocations(uci, hbn, reach_id, t_code):
    """Calculate total suspended sediment allocations.
    
    Args:
        uci: UCI object
        hbn: HBN interface object
        reach_id: Reach ID
        t_code: Time code
        
    Raises:
        NotImplementedError: This function is not yet implemented
    """
    raise NotImplementedError()

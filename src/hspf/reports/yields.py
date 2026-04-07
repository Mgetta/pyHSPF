# -*- coding: utf-8 -*-
"""
Landscape yield reports — constituent loads and yields at reach outlets.

HSPF-specific wrappers that extract data from uci/hbn objects and delegate
to the model-agnostic analytics in :mod:`hspf.reports._analytics.yields`.
"""
from hspf.reports.timeseries import (
    average_annual,
    average_monthly,
)



def constituent_load(hbn, constituent, reach_ids, time_step=5, upstream_reach_ids=None):
    """Extract net load timeseries for specific reaches from HBN.

    Parameters
    ----------
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    reach_ids : list of int
        Target reach IDs.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs whose load is subtracted.

    Returns
    -------
    pd.DataFrame
        Net load timeseries (total minus upstream contribution).
    """
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    load_ts = hbn.get_reach_constituent(constituent, reach_ids, time_step, unit=units)

    upstream_load_ts = 0
    if upstream_reach_ids is not None:
        upstream_load_ts = constituent_load(hbn, constituent, upstream_reach_ids, time_step)

    return load_ts - upstream_load_ts

def constituent_yield(uci, hbn, constituent, reach_ids, time_step=5,
                      upstream_reach_ids=None, drainage_area=None):
    """Compute yield (load per unit area) for specific reaches.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    reach_ids : list of int
        Target reach IDs.
    time_step : int, optional
        HBN time-step code (default 5 = yearly).
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    drainage_area : float or None, optional
        Custom drainage area (acres).  If ``None``, calculated from the
        network.

    Returns
    -------
    pd.DataFrame
        Yield timeseries (load / drainage area).
    """
    if drainage_area is None:
        drainage_area = uci.network.drainage_area(reach_ids, upstream_reach_ids)

    load_ts = constituent_load(hbn, constituent, reach_ids, time_step, upstream_reach_ids)
    
    return load_ts / drainage_area


def average_annual_yield(uci, hbn, constituent, reach_ids, upstream_reach_ids=None,
                         start_year=1996, end_year=2100, drainage_area=None):
    """Average annual yield for specific reaches.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    reach_ids : list of int
        Target reach IDs.
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).
    drainage_area : float or None, optional
        Custom drainage area (acres).

    Returns
    -------
    pd.Series or scalar
        Mean annual yield over the filtered period.
    """
    yld = constituent_yield(uci, hbn, constituent, reach_ids, 5,
                            upstream_reach_ids, drainage_area)
    return average_annual(yld, start_year, end_year)


def average_monthly_yield(uci, hbn, constituent, reach_ids, upstream_reach_ids=None,
                          start_year=1996, end_year=2100, drainage_area=None):
    """Average monthly yield for specific reaches.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    constituent : str
        Constituent name (e.g. ``'TP'``, ``'TSS'``, ``'Q'``).
    reach_ids : list of int
        Target reach IDs.
    upstream_reach_ids : list of int or None, optional
        Upstream boundary reach IDs.
    start_year, end_year : int, optional
        Year range filter (inclusive, defaults 1996–2100).
    drainage_area : float or None, optional
        Custom drainage area (acres).

    Returns
    -------
    pd.DataFrame or pd.Series
        Mean yield grouped by calendar month (1–12).
    """
    yld = constituent_yield(uci, hbn, constituent, reach_ids, 4,
                            upstream_reach_ids, drainage_area)
    return average_monthly(yld, start_year, end_year)


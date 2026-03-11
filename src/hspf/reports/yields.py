# -*- coding: utf-8 -*-
"""
Landscape yield reports — constituent loads and yields at reach outlets.

HSPF-specific wrappers that extract data from uci/hbn objects and delegate
to the model-agnostic analytics in :mod:`hspf.reports._analytics.yields`.
"""
from hspf.reports._analytics.yields import (
    compute_yield,
    compute_net_load,
    average_annual,
    average_monthly,
)


def _constituent_load(hbn, constituent, time_step=5):
    """Extract load timeseries for all reaches from HBN."""
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    df = hbn.get_rchres_output(constituent, units, time_step)

    return df


def constituent_load(hbn, constituent, reach_ids, time_step=5, upstream_reach_ids=None):
    """Extract net load timeseries for specific reaches from HBN."""
    if constituent == 'Q':
        units = 'acrft'
    else:
        units = 'lb'

    load_ts = hbn.get_reach_constituent(constituent, reach_ids, time_step, unit=units)

    upstream_load_ts = None
    if upstream_reach_ids is not None:
        upstream_load_ts = constituent_load(hbn, constituent, upstream_reach_ids, time_step)

    return compute_net_load(load_ts, upstream_load_ts)


def _constituent_yield(uci, hbn, constituent, time_step=5):
    """Compute yield for all reaches."""
    load_ts = _constituent_load(hbn, constituent, time_step)

    areas = [uci.network.drainage_area([reach_id]) for reach_id in load_ts.columns]
    return compute_yield(load_ts, areas)


def constituent_yield(uci, hbn, constituent, reach_ids, time_step=5,
                      upstream_reach_ids=None, drainage_area=None):
    """Compute yield for specific reaches."""
    if drainage_area is None:
        drainage_area = uci.network.drainage_area(reach_ids, upstream_reach_ids)

    load_ts = constituent_load(hbn, constituent, reach_ids, time_step, upstream_reach_ids)
    return compute_yield(load_ts, drainage_area)


def average_annual_yield(uci, hbn, constituent, reach_ids, upstream_reach_ids=None,
                         start_year=1996, end_year=2100, drainage_area=None):
    """Average annual yield for specific reaches."""
    yld = constituent_yield(uci, hbn, constituent, reach_ids, 5,
                            upstream_reach_ids, drainage_area)
    return average_annual(yld, start_year, end_year)


def average_monthly_yield(uci, hbn, constituent, reach_ids, upstream_reach_ids=None,
                          start_year=1996, end_year=2100, drainage_area=None):
    """Average monthly yield for specific reaches."""
    yld = constituent_yield(uci, hbn, constituent, reach_ids, 4,
                            upstream_reach_ids, drainage_area)
    return average_monthly(yld, start_year, end_year)

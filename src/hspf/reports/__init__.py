# -*- coding: utf-8 -*-
"""
Reports package for HSPF model output analysis.

Submodules
----------
loading
    Constituent loading reports (catchment and watershed edge-of-field loading).
yields
    Landscape yield reports (constituent loads and yields at reach outlets).
contributions
    Channel contributions and allocation reports.
hydrology
    Water balance, precipitation, ET, runoff, and meteorological reports.
sediment
    Scour and sediment budget reports.
phosphorus
    TP-specific calculations (masslink scheme, qualprop transforms).
utils
    Utility functions for weighted statistics and time aggregation.
legacy
    Older loading implementations kept for backward compatibility.
"""

import pandas as pd

# --- loading ---
from hspf.reports.loading import (
    catchment_areas,
    get_constituent_loading,
    _join_catchments,
    get_catchment_loading,
    get_watershed_loading,
    constituent_loading_summary,
    loading_summary,
    catchment_loading_summary,
    _filter_to_watershed,
    watershed_loading_summary,
)

# --- yields ---
from hspf.reports.yields import (
    _constituent_load,
    constituent_load,
    _constituent_yield,
    constituent_yield,
    average_annual_yield,
    average_monthly_yield,
)

# --- analytics (model-agnostic) ---
from hspf.reports._analytics.yields import (
    compute_yield,
    compute_net_load,
    average_annual,
    average_monthly,
    annual_totals,
    monthly_totals,
    yield_summary,
)

from hspf.reports._analytics.contributions import (
    compute_fate_factors,
    compute_path_fate_factors,
    compute_local_load,
    compute_contributions,
    compute_contribution_pct,
    contribution_summary,
)

# --- contributions ---
from hspf.reports.contributions import (
    allocation_selector,
    channel_inflows,
    channel_outflows,
    channel_fate,
    local_loading,
    catchment_contributions,
    total_contributions,
)

# --- sediment ---
from hspf.reports.sediment import (
    scour,
    annual_sediment_budget,
)

# --- phosphorus ---
from hspf.reports.phosphorus import (
    MASSLINK_SCHEME,
    qualprop_transform,
    dissolved_orthophosphate,
    particulate_orthophosphate_sand,
    particulate_orthophosphate_silt,
    particulate_orthophosphate_clay,
    organic_refactory_phosphorous,
    organic_refactory_carbon,
    labile_oxygen_demand,
    particulate_orthophosphate,
    total_phosphorous,
    subwatershed_total_phosphorous_loading,
)

# --- hydrology ---
from hspf.reports.hydrology import (
    pevt_balance,
    simulated_et,
    inflows,
    water_balance,
    meteorlogical,
    avg_annual_precip,
    annual_perlnd_runoff,
    annual_reach_water_budget,
    perlnd_water_budget,
    annual_implnd_water_budget,
    annual_perlnd_water_budget,
    watershed_water_budget,
    metzone_watershed_budget,
)

# --- utils ---
from hspf.reports.utils import (
    SIMULATION_PERIOD_TO_TIME_STEP,
    PERIOD_ORDER,
    simulation_period_to_time_step,
    validate_periods,
    aggregation_period_to_temporal_grouping,
    weighted_describe,
    weighted_parameter,
    weighted_output,
    _apply_time_aggregation,
    weighted_mean,
    annual_weighted_output,
)

# --- residence ---
from hspf.reports.residence import (
    get_reach_hydraulics,
    mannings_velocity,
    reach_travel_time,
    path_travel_time,
    travel_times,
    travel_time_summary,
)

# --- legacy ---
from hspf.reports.legacy import (
    avg_subwatershed_loading,
    monthly_avg_constituent_loading,
    monthly_avg_subwatershed_loading,
    monthly_avg_watershed_loading,
    ann_avg_constituent_loading,
    ann_avg_subwatershed_loading,
    ann_avg_watershed_loading,
    Reports,
)


# ---------------------------------------------------------------------------
# Lightweight accessor class
# ---------------------------------------------------------------------------

class ReportsAccessor:
    """Minimal wrapper providing method-style access to report functions.

    Designed for composition with :class:`hspfModel` or standalone use::

        accessor = ReportsAccessor(uci, hbns, wdms)
        accessor.catchment_loading('TP')

    All methods delegate to the corresponding module-level functions,
    automatically injecting the stored *uci*, *hbns* and *wdms* objects.
    """

    def __init__(self, uci, hbns, wdms=None):
        self.uci = uci
        self.hbns = hbns
        self.wdms = wdms

    # --- loading ---------------------------------------------------------
    def catchment_loading(self, constituent, time_step=5):
        return get_catchment_loading(self.uci, self.hbns, constituent, time_step)

    def watershed_loading(self, constituent, reach_ids=None,
                          upstream_reach_ids=None, by_landcover=False,
                          time_step=5):
        return get_watershed_loading(
            self.uci, self.hbns, constituent, reach_ids,
            upstream_reach_ids, by_landcover, time_step,
        )

    def loading_summary(self, constituent, **kwargs):
        return loading_summary(self.uci, self.hbns, constituent, **kwargs)

    def catchment_loading_summary(self, constituent, **kwargs):
        return catchment_loading_summary(
            self.uci, self.hbns, constituent, **kwargs,
        )

    def watershed_loading_summary(self, constituent, **kwargs):
        return watershed_loading_summary(
            self.uci, self.hbns, constituent, **kwargs,
        )

    # --- yields ----------------------------------------------------------
    def constituent_yield(self, constituent, reach_ids, **kwargs):
        return constituent_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    def average_annual_yield(self, constituent, reach_ids, **kwargs):
        return average_annual_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    def average_monthly_yield(self, constituent, reach_ids, **kwargs):
        return average_monthly_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    # --- contributions ---------------------------------------------------
    def total_contributions(self, constituent, target_reach_id, **kwargs):
        return total_contributions(
            constituent, self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def catchment_contributions(self, constituent, target_reach_id, **kwargs):
        return catchment_contributions(
            self.uci, self.hbns, constituent, target_reach_id, **kwargs,
        )

    # --- hydrology -------------------------------------------------------
    def water_balance(self, reach_ids):
        return water_balance(self.uci, self.hbns, self.wdms, reach_ids)

    def avg_annual_precip(self):
        return avg_annual_precip(self.uci, self.wdms)

    def simulated_et(self):
        return simulated_et(self.uci, self.hbns)

    def annual_perlnd_runoff(self, **kwargs):
        return annual_perlnd_runoff(self.uci, self.hbns, **kwargs)

    def annual_water_budget(self, operation):
        if operation == 'PERLND':
            return annual_perlnd_water_budget(self.uci, self.hbns)
        elif operation == 'IMPLND':
            return annual_implnd_water_budget(self.uci, self.hbns)
        elif operation == 'RCHRES':
            return annual_reach_water_budget(self.uci, self.hbns)
        raise ValueError(
            f"operation must be 'PERLND', 'IMPLND', or 'RCHRES', "
            f"got '{operation}'"
        )

    # --- sediment --------------------------------------------------------
    def scour(self, **kwargs):
        return scour(self.hbns, self.uci, **kwargs)

    def annual_sediment_budget(self):
        return annual_sediment_budget(self.uci, self.hbns)

    # --- phosphorus ------------------------------------------------------
    def total_phosphorous(self, t_code=5, operation='PERLND'):
        return total_phosphorous(self.uci, self.hbns, t_code, operation)


# Remaining non-class helper kept at package level
def get_catchments(uci, reach_ids):
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND', :].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR', 'LSID', 'metzone', 'TVOLNO', 'MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0, pd.NA)
    return landcover


def _operation_metadata():
    from hspf import uci
    dfs = []
    for operation in ['PERLND', 'IMPLND', 'RCHRES']:
        df = uci.opnid_dict[operation].reset_index()
        df['OPERATION'] = operation
        dfs.append(df)
    df = pd.concat(dfs)

    df = pd.merge(
        uci.network.subwatersheds().reset_index(),
        df[['TOPFST', 'OPERATION', 'metzone']],
        left_on=['SVOLNO', 'SVOL'],
        right_on=['TOPFST', 'OPERATION'],
        how='inner',
    )

    return df[['TVOLNO', 'SVOLNO', 'SVOL', 'AFACR', 'MLNO', 'LSID', 'metzone']]

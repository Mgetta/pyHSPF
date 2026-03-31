# -*- coding: utf-8 -*-
"""
Reports package for HSPF model output analysis.

This package provides a suite of functions for generating various reports and analyses
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
    constituent_load,
    constituent_yield,
    average_annual_yield,
    average_monthly_yield,
)


# --- contributions ---
from hspf.reports.contributions import (
    ALLOCATION_SELECTOR,
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

# --- analytics: timeseries ---
from hspf.reports.timeseries import (
    filter_years,
    filter_months,
    aggregate,
)
# --- residence ---
from hspf.reports.residence import (
    get_reach_hydraulics,
    mannings_velocity,
    reach_travel_time,
    path_travel_time,
    travel_times,
    travel_time_summary,
    water_age_distribution,
    water_age_summary,
    water_age_by_period,
    water_age_source_table,
    lagged_contributions,
    lagged_contribution_summary,
    lagrangian_travel_time,
    lagrangian_travel_times,
    lagrangian_travel_time_summary,
    lagrangian_travel_time_exceedance,
    compare_lagrangian_vs_dynamic,
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
        """Return catchment-level loading.  Delegates to :func:`get_catchment_loading`."""
        return get_catchment_loading(self.uci, self.hbns, constituent, time_step)

    def watershed_loading(self, constituent, reach_ids=None,
                          upstream_reach_ids=None, by_landcover=False,
                          time_step=5):
        """Return watershed-level loading.  Delegates to :func:`get_watershed_loading`."""
        return get_watershed_loading(
            self.uci, self.hbns, constituent, reach_ids,
            upstream_reach_ids, by_landcover, time_step,
        )

    def loading_summary(self, constituent, **kwargs):
        """Return unified loading summary.  Delegates to :func:`loading_summary`."""
        return loading_summary(self.uci, self.hbns, constituent, **kwargs)

    def catchment_loading_summary(self, constituent, **kwargs):
        """Return catchment loading summary.  Delegates to :func:`catchment_loading_summary`."""
        return catchment_loading_summary(
            self.uci, self.hbns, constituent, **kwargs,
        )

    def watershed_loading_summary(self, constituent, **kwargs):
        """Return watershed loading summary.  Delegates to :func:`watershed_loading_summary`."""
        return watershed_loading_summary(
            self.uci, self.hbns, constituent, **kwargs,
        )

    # --- yields ----------------------------------------------------------
    def constituent_yield(self, constituent, reach_ids, **kwargs):
        """Compute constituent yield.  Delegates to :func:`constituent_yield`."""
        return constituent_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    def average_annual_yield(self, constituent, reach_ids, **kwargs):
        """Compute average annual yield.  Delegates to :func:`average_annual_yield`."""
        return average_annual_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    def average_monthly_yield(self, constituent, reach_ids, **kwargs):
        """Compute average monthly yield.  Delegates to :func:`average_monthly_yield`."""
        return average_monthly_yield(
            self.uci, self.hbns, constituent, reach_ids, **kwargs,
        )

    # --- contributions ---------------------------------------------------
    def total_contributions(self, constituent, target_reach_id, **kwargs):
        """Compute total contributions.  Delegates to :func:`total_contributions`."""
        return total_contributions(
            constituent, self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def catchment_contributions(self, constituent, target_reach_id, **kwargs):
        """Compute catchment contributions.  Delegates to :func:`catchment_contributions`."""
        return catchment_contributions(
            self.uci, self.hbns, constituent, target_reach_id, **kwargs,
        )

    # --- water age -------------------------------------------------------
    def water_age_distribution(self, target_reach_id, **kwargs):
        """Return water age distribution.  Delegates to :func:`water_age_distribution`."""
        return water_age_distribution(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def water_age_summary(self, target_reach_id, **kwargs):
        """Return water age summary statistics.  Delegates to :func:`water_age_summary`."""
        return water_age_summary(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def water_age_by_period(self, target_reach_id, **kwargs):
        """Return water age histograms by period.  Delegates to :func:`water_age_by_period`."""
        return water_age_by_period(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def water_age_source_table(self, target_reach_id, **kwargs):
        """Return water age source table.  Delegates to :func:`water_age_source_table`."""
        return water_age_source_table(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def lagged_contributions(self, target_reach_id, **kwargs):
        """Return lagged contributions.  Delegates to :func:`lagged_contributions`."""
        return lagged_contributions(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    def lagged_contribution_summary(self, target_reach_id, **kwargs):
        """Return lagged contribution summary.  Delegates to :func:`lagged_contribution_summary`."""
        return lagged_contribution_summary(
            self.uci, self.hbns, target_reach_id, **kwargs,
        )

    # --- hydrology -------------------------------------------------------
    def water_balance(self, reach_ids):
        """Compute water balance.  Delegates to :func:`water_balance`."""
        return water_balance(self.uci, self.hbns, self.wdms, reach_ids)

    def avg_annual_precip(self):
        """Compute average annual precipitation.  Delegates to :func:`avg_annual_precip`."""
        return avg_annual_precip(self.uci, self.wdms)

    def simulated_et(self):
        """Compute simulated ET.  Delegates to :func:`simulated_et`."""
        return simulated_et(self.uci, self.hbns)

    def annual_perlnd_runoff(self, **kwargs):
        """Compute annual PERLND runoff.  Delegates to :func:`annual_perlnd_runoff`."""
        return annual_perlnd_runoff(self.uci, self.hbns, **kwargs)

    def annual_water_budget(self, operation):
        """Return the annual water budget for a given operation type.

        Delegates to :func:`annual_perlnd_water_budget`,
        :func:`annual_implnd_water_budget`, or
        :func:`annual_reach_water_budget` depending on *operation*.

        Parameters
        ----------
        operation : str
            One of ``'PERLND'``, ``'IMPLND'``, or ``'RCHRES'``.

        Returns
        -------
        pd.DataFrame
            Annual water budget for the requested operation.

        Raises
        ------
        ValueError
            If *operation* is not recognised.
        """
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
        """Compute scour report.  Delegates to :func:`scour`."""
        return scour(self.hbns, self.uci, **kwargs)

    def annual_sediment_budget(self):
        """Compute annual sediment budget.  Delegates to :func:`annual_sediment_budget`."""
        return annual_sediment_budget(self.uci, self.hbns)

    # --- phosphorus ------------------------------------------------------
    def total_phosphorous(self, t_code=5, operation='PERLND'):
        """Compute total phosphorous.  Delegates to :func:`total_phosphorous`."""
        return total_phosphorous(self.uci, self.hbns, t_code, operation)


# Remaining non-class helper kept at package level
def get_catchments(uci, reach_ids):
    """Extract PERLND catchment/landcover metadata for the given reaches.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    reach_ids : list of int
        Reach (RCHRES) IDs to extract catchment data for.

    Returns
    -------
    pd.DataFrame
        Indexed by SVOLNO with columns ``AFACTR``, ``LSID``, ``metzone``,
        ``TVOLNO``, and ``MLNO``.
    """
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND', :].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR', 'LSID', 'metzone', 'TVOLNO', 'MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0, pd.NA)
    return landcover


def _operation_metadata():
    """Build a metadata DataFrame merging operation info with subwatershed network data.

    Returns
    -------
    pd.DataFrame
        Columns: ``TVOLNO``, ``SVOLNO``, ``SVOL``, ``AFACR``, ``MLNO``,
        ``LSID``, ``metzone``.
    """
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

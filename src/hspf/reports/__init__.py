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

# --- loading ---
from hspf.reports.loading import (
    catchment_areas,
    catchment_landcover_areas,
    watershed_landcover_areas,
    get_constituent_loading,
    _join_catchments,
    get_catchment_loading,
    get_watershed_loading,
    _average_constituent_loading,
    constituent_loading_summary,
    average_annual_constituent_loading,
    average_monthly_constituent_loading,
    _aggregate_catchment_loading,
    _aggregate_catchment_by_metzone,
    _aggregate_catchment_by_landcover_group,
    catchment_loading_summary,
    average_annual_catchment_loading,
    average_monthly_catchment_loading,
    _filter_to_watershed,
    watershed_loading_summary,
    average_annual_watershed_loading,
    average_monthly_watershed_loading,
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


# Remaining non-class helper kept at package level
def get_catchments(uci,reach_ids):
    # Grab metadata information
    subwatersheds = uci.network.subwatersheds().loc[reach_ids].reset_index()
    landcover = subwatersheds.set_index('SVOL').loc['PERLND',:].set_index('SVOLNO')
    landcover = landcover.join(uci.opnid_dict['PERLND'])
    landcover = landcover[['AFACTR','LSID','metzone','TVOLNO','MLNO']]
    landcover['AFACTR'] = landcover['AFACTR'].replace(0,pd.NA)
    return landcover


def _operation_metadata():
        # Add metadata
    from hspf import uci
    dfs = []
    for operation in ['PERLND','IMPLND','RCHRES']:
        df = uci.opnid_dict[operation].reset_index()
        df['OPERATION'] = operation
        dfs.append(df)
    df = pd.concat(dfs)

    # Merge with network data
    df = pd.merge(
        uci.network.subwatersheds().reset_index(),
        df[['TOPFST','OPERATION','metzone']],
        left_on=['SVOLNO', 'SVOL'],
        right_on=['TOPFST', 'OPERATION'],
        how='inner'
    )
    
    return df[['TVOLNO','SVOLNO','SVOL','AFACR','MLNO','LSID','metzone']]

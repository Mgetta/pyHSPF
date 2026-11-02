"""Validation check functions grouped by validation concern."""

from hspf.validation.checks.gis_layer import (
    check_catchment_attributes,
    check_downstream_references,
    check_gis_reach_graph,
    check_reach_keys,
)
from hspf.validation.checks.uci_forcing import (
    check_copy_met_distribution,
    check_duplicate_precip_targets,
    check_ftable_coverage,
    check_lake_forcing_completeness,
    check_land_forcing_completeness,
    check_orphan_ftables,
    check_precip_factors,
    check_reach_classification_flags,
    check_subwatershed_dsn_coherence,
)
from hspf.validation.checks.uci_gis import (
    check_area_comparison_deferred,
    check_catchment_coverage,
    check_lake_concordance,
    check_precip_crosswalk,
    check_precip_metzones,
    check_reach_set_reconciliation,
    check_routing_edge_concordance,
    check_terminal_reach_concordance,
)
from hspf.validation.checks.uci_membership import (
    check_connection_membership,
    check_dangling_land_segments,
    check_external_input_targets,
    check_geninfo_reconciliation,
    check_unmatched_masslink_transfers,
)
from hspf.validation.checks.uci_routing import (
    check_disconnected_reach_networks,
    check_reach_outlet_count,
    check_reach_routing_acyclicity,
    check_schematic_network_overlap,
)


__all__ = [
    "check_catchment_attributes",
    "check_downstream_references",
    "check_gis_reach_graph",
    "check_reach_keys",
    "check_copy_met_distribution",
    "check_duplicate_precip_targets",
    "check_ftable_coverage",
    "check_lake_forcing_completeness",
    "check_land_forcing_completeness",
    "check_orphan_ftables",
    "check_precip_factors",
    "check_reach_classification_flags",
    "check_subwatershed_dsn_coherence",
    "check_area_comparison_deferred",
    "check_catchment_coverage",
    "check_lake_concordance",
    "check_precip_crosswalk",
    "check_precip_metzones",
    "check_reach_set_reconciliation",
    "check_routing_edge_concordance",
    "check_terminal_reach_concordance",
    "check_connection_membership",
    "check_dangling_land_segments",
    "check_external_input_targets",
    "check_geninfo_reconciliation",
    "check_unmatched_masslink_transfers",
    "check_disconnected_reach_networks",
    "check_reach_outlet_count",
    "check_reach_routing_acyclicity",
    "check_schematic_network_overlap",
]
